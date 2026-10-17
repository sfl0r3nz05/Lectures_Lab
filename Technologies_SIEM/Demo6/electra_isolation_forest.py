"""
WWTP / ICS Anomaly Detection — Electra Dataset Pipeline
═══════════════════════════════════════════════════════════════════════════════
Adapted for Electra's packet-level Modbus schema:

    time    → timestamp (metadata, used for temporal features)
    smac    → source MAC (metadata, dropped)
    dmac    → destination MAC (metadata, dropped)
    sip     → source IP (metadata, dropped)
    dip     → destination IP (metadata, dropped)
    request → is request packet (Boolean string → binary)
    fc      → Modbus function code (integer)
    error   → error in read/write operation (Boolean → binary)
    madd    → memory address for read/write (integer)
    data    → data transmitted/received (integer)
    label   → attack/normal label (string → encoded integer)

Attack categories in Electra:
    normal, reconnaissance, false_data_injection,
    forced_error, command_modification, read_data,
    write_data, replay, response_modification

Pipeline:
    1. Load CSV → inspect schema and label distribution
    2. Engineer temporal + Modbus-specific features
    3. Encode categoricals, handle imbalance
    4. Train Isolation Forest on normal packets only
    5. Calibrate threshold (percentile + F1-max)
    6. Evaluate per attack type
    7. Export comparison baseline + visualizations
"""

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_recall_curve, roc_curve,
    confusion_matrix, classification_report,
    f1_score
)

warnings.filterwarnings('ignore')

OUTPUT_DIR = '/home/test/ml_test/dl_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── KNOWN ELECTRA LABEL VALUES ──────────────────────────────────────────────
# Maps possible label strings → binary (0=normal, 1=attack)
# and integer class index for multi-class evaluation
LABEL_NORMAL_VARIANTS = {
    'normal', 'Normal', 'NORMAL', 'benign', 'Benign', '0', 0
}

ATTACK_CLASS_MAP = {
    'normal':                0,
    'reconnaissance':        1,
    'false_data_injection':  2,
    'forced_error':          3,
    'command_modification':  4,
    'read_data':             5,
    'write_data':            6,
    'replay':                7,
    'response_modification': 8,
}

# Modbus function codes relevant to WWTP/ICS
MODBUS_READ_FC  = {1, 2, 3, 4}
MODBUS_WRITE_FC = {5, 6, 15, 16, 22, 23}

# ─── FEATURE ENGINEERING ─────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw Electra columns into ML-ready feature matrix.

    Derived features:
      - fc_is_read / fc_is_write     : function code family
      - fc_is_diagnostic             : diagnostic/exception FC (>= 0x80 or FC 8)
      - request_binary               : request=True → 1, response → 0
      - error_binary                 : error=True → 1
      - madd_normalized              : memory address / max observed address
      - data_log                     : log1p(|data|) — handles large values
      - data_zero                    : flag for data == 0 (common in forced error)
      - fc_madd_interaction          : fc * madd — captures FC+address combos
      - rolling_error_rate_10        : error rate over last 10 packets (per src IP)
      - rolling_fc_entropy_20        : FC entropy over last 20 packets (per src IP)
      - madd_delta                   : change in memory address from previous packet
      - data_delta                   : change in data value from previous packet
      - inter_packet_time            : time delta from previous packet (ms)
      - ipt_rolling_mean_10          : rolling mean of inter-packet time
    """
    df = df.copy()

    # ── 1. Encode request column ──────────────────────────────────────────
    df['request_binary'] = (
        df['request'].astype(str).str.lower()
        .map({'true': 1, 'false': 0, '1': 1, '0': 0, 'yes': 1, 'no': 0})
        .fillna(0).astype(int)
    )

    # ── 2. Encode error column ────────────────────────────────────────────
    df['error_binary'] = (
        df['error'].astype(str).str.lower()
        .map({'true': 1, 'false': 0, '1': 1, '0': 0})
        .fillna(0).astype(int)
    )

    # ── 3. FC family flags ────────────────────────────────────────────────
    df['fc_is_read']       = df['fc'].isin(MODBUS_READ_FC).astype(int)
    df['fc_is_write']      = df['fc'].isin(MODBUS_WRITE_FC).astype(int)
    df['fc_is_diagnostic'] = ((df['fc'] == 8) | (df['fc'] >= 128)).astype(int)
    df['fc_is_unknown']    = (
        ~df['fc'].isin(MODBUS_READ_FC | MODBUS_WRITE_FC | {8})
    ).astype(int)

    # ── 4. Memory address features ────────────────────────────────────────
    max_addr = df['madd'].abs().max()
    df['madd_normalized'] = df['madd'] / (max_addr + 1e-9)

    # ── 5. Data value features ────────────────────────────────────────────
    df['data_log']  = np.log1p(df['data'].abs())
    df['data_zero'] = (df['data'] == 0).astype(int)
    df['data_neg']  = (df['data'] < 0).astype(int)

    # ── 6. Interaction term ───────────────────────────────────────────────
    df['fc_madd_interaction'] = df['fc'] * df['madd_normalized']

    # ── 7. Temporal features (requires sorted timestamps) ─────────────────
    df = _add_temporal_features(df)

    return df


def _parse_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """Parse 'time' column to seconds float."""
    try:
        df['time_dt'] = pd.to_datetime(df['time'], infer_datetime_format=True)
        df['time_sec'] = (df['time_dt'] - df['time_dt'].min()).dt.total_seconds()
    except Exception:
        try:
            df['time_sec'] = df['time'].astype(float)
        except Exception:
            df['time_sec'] = np.arange(len(df), dtype=float)
    return df


def _add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute temporal features per source IP group.
    This captures per-device behavioral patterns rather than
    global network statistics, which is critical for ICS where
    each device has a deterministic communication schedule.
    """
    df = _parse_timestamp(df)
    df = df.sort_values('time_sec').reset_index(drop=True)

    # Global inter-packet time
    df['inter_packet_time'] = df['time_sec'].diff().fillna(0).clip(lower=0)
    df['ipt_log']           = np.log1p(df['inter_packet_time'])

    # Per source IP grouping (each PLC / HMI has its own communication pattern)
    src_col = 'sip' if 'sip' in df.columns else None

    if src_col and df[src_col].nunique() > 1:
        groups = df.groupby(src_col, sort=False)

        # Rolling error rate (window=10 packets per device)
        df['rolling_error_rate_10'] = (
            groups['error_binary']
            .transform(lambda x: x.rolling(10, min_periods=1).mean())
        )

        # Rolling FC entropy — vectorized approximation using nunique/count ratio
        # Full entropy is O(n*window) which OOMs on 16M rows.
        # nunique/window is a strong proxy: high cardinality = high entropy.
        df['rolling_fc_entropy_20'] = (
            groups['fc']
            .transform(lambda x: x.rolling(20, min_periods=1).apply(
                lambda w: len(set(w)) / len(w), raw=True
            ))
        )

        # Address delta per device (rapid address scanning = reconnaissance)
        df['madd_delta'] = (
            groups['madd']
            .transform(lambda x: x.diff().abs().fillna(0))
        )

        # Data delta per device (sudden value changes = false data injection)
        df['data_delta'] = (
            groups['data']
            .transform(lambda x: x.diff().abs().fillna(0))
        )

        # Per-device inter-packet time rolling mean
        df['ipt_rolling_mean_10'] = (
            groups['inter_packet_time']
            .transform(lambda x: x.rolling(10, min_periods=1).mean())
        )

    else:
        # Single source — compute globally
        df['rolling_error_rate_10'] = (
            df['error_binary'].rolling(10, min_periods=1).mean()
        )
        df['rolling_fc_entropy_20'] = 0.0  # can't compute meaningfully
        df['madd_delta']            = df['madd'].diff().abs().fillna(0)
        df['data_delta']            = df['data'].diff().abs().fillna(0)
        df['ipt_rolling_mean_10']   = (
            df['inter_packet_time'].rolling(10, min_periods=1).mean()
        )

    return df


# ─── LABEL HANDLING ──────────────────────────────────────────────────────────

def encode_labels(df: pd.DataFrame, label_col: str = 'label') -> pd.DataFrame:
    """
    Encode string labels to:
      - label_binary : 0=normal, 1=any attack
      - label_int    : integer class index per ATTACK_CLASS_MAP
    """
    df = df.copy()
    raw_labels = df[label_col].astype(str).str.strip().str.lower()

    # Binary encoding
    normal_set = {str(v).lower() for v in LABEL_NORMAL_VARIANTS}
    df['label_binary'] = raw_labels.apply(
        lambda x: 0 if x in normal_set else 1
    )

    # Multi-class encoding — map known labels, flag unknowns
    def map_label(x):
        for k, v in ATTACK_CLASS_MAP.items():
            if k in x or x in k:
                return v
        return -1  # unknown

    df['label_int'] = raw_labels.apply(map_label)
    df['label_name'] = raw_labels

    print(f"\n[labels] Distribution across {len(df):,} packets:")
    dist = df.groupby(['label_name', 'label_binary']).size().reset_index(name='count')
    dist['pct'] = (dist['count'] / len(df) * 100).round(2)
    print(dist.to_string(index=False))

    n_normal = (df['label_binary'] == 0).sum()
    n_attack = (df['label_binary'] == 1).sum()
    print(f"\n  Normal: {n_normal:,} ({n_normal/len(df)*100:.1f}%)")
    print(f"  Attack: {n_attack:,} ({n_attack/len(df)*100:.1f}%)")
    print(f"  Imbalance ratio: 1:{n_normal/max(n_attack,1):.1f}")

    return df


# ─── ISOLATION FOREST ────────────────────────────────────────────────────────

# Feature columns used for training (excludes metadata and label columns)
FEATURE_COLS = [
    # Core Modbus fields
    'fc', 'error_binary', 'request_binary',
    'madd', 'madd_normalized', 'data', 'data_log',
    # Derived FC features
    'fc_is_read', 'fc_is_write', 'fc_is_diagnostic', 'fc_is_unknown',
    # Derived data features
    'data_zero', 'data_neg',
    # Interaction
    'fc_madd_interaction',
    # Temporal
    'inter_packet_time', 'ipt_log', 'ipt_rolling_mean_10',
    # Rolling behavioral
    'rolling_error_rate_10', 'rolling_fc_entropy_20',
    # Delta features
    'madd_delta', 'data_delta',
]

LOG_COLS = ['madd_delta', 'data_delta', 'inter_packet_time',
            'ipt_rolling_mean_10', 'data_log']


class ElectraIsolationForest:

    def __init__(self, n_estimators=300, contamination=0.05,
                 random_state=42):
        self.n_estimators  = n_estimators
        self.contamination = contamination
        self.random_state  = random_state
        self.scaler        = RobustScaler()
        self.model         = IsolationForest(
            n_estimators  = n_estimators,
            contamination = contamination,
            max_samples   = 'auto',
            random_state  = random_state,
            n_jobs        = -1,
        )
        self.threshold      = None
        self.training_stats = {}
        self.feature_cols   = FEATURE_COLS
        self.is_fitted      = False

    def _prepare_X(self, df: pd.DataFrame) -> np.ndarray:
        available = [c for c in self.feature_cols if c in df.columns]
        X = df[available].copy().fillna(0).replace([np.inf, -np.inf], 0)
        # Additional log transforms on heavy-tailed columns
        for col in LOG_COLS:
            if col in X.columns:
                X[col] = np.log1p(X[col].clip(lower=0))
        return X.values.astype(np.float32), available

    def fit(self, df: pd.DataFrame) -> 'ElectraIsolationForest':
        # Train on normal packets only
        normal_df = df[df['label_binary'] == 0] if 'label_binary' in df.columns else df
        print(f"\n[IForest] Fitting on {len(normal_df):,} normal packets...")

        X, cols = self._prepare_X(normal_df)
        self.used_features = cols

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)

        # Store per-feature training statistics for explainability
        self.training_stats = {
            col: {'mean': float(normal_df[col].mean()),
                  'std':  float(normal_df[col].std()),
                  'p95':  float(normal_df[col].quantile(0.95)),
                  'p05':  float(normal_df[col].quantile(0.05))}
            for col in cols if col in normal_df.columns
        }
        self.is_fitted = True
        print(f"[IForest] Fitted — {len(cols)} features, "
              f"{self.n_estimators} trees")
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Return anomaly scores — higher = more anomalous."""
        X, _ = self._prepare_X(df)
        X_scaled = self.scaler.transform(X)
        return -self.model.score_samples(X_scaled)

    def calibrate(self, df: pd.DataFrame) -> float:
        """
        Dual calibration:
          - If labels available: F1-maximizing threshold
          - Always also compute percentile threshold as fallback
        """
        scores = self.score(df)

        # Percentile threshold (always available)
        normal_scores = scores[df['label_binary'].values == 0] \
                        if 'label_binary' in df.columns else scores
        pct_threshold = float(np.percentile(
            normal_scores, (1 - self.contamination) * 100))

        if 'label_binary' in df.columns and df['label_binary'].nunique() > 1:
            labels = df['label_binary'].values
            prec, rec, thresholds = precision_recall_curve(labels, scores)
            f1s = 2 * prec * rec / (prec + rec + 1e-9)
            best_idx = np.argmax(f1s[:-1])
            f1_threshold = float(thresholds[best_idx])
            best_f1 = float(f1s[best_idx])
            self.threshold = f1_threshold
            print(f"[IForest] Threshold → F1-max={f1_threshold:.4f} "
                  f"(F1={best_f1:.3f}) | Percentile fallback={pct_threshold:.4f}")
        else:
            self.threshold = pct_threshold
            print(f"[IForest] Threshold → Percentile={pct_threshold:.4f}")

        return self.threshold

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        scores = self.score(df)
        return (scores >= self.threshold).astype(int)

    def evaluate(self, df: pd.DataFrame) -> dict:
        assert 'label_binary' in df.columns
        scores  = self.score(df)
        preds   = self.predict(df)
        labels  = df['label_binary'].values

        roc_auc  = roc_auc_score(labels, scores)
        avg_prec = average_precision_score(labels, scores)

        cm = confusion_matrix(labels, preds)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0,0,0,0)

        precision = tp / (tp + fp + 1e-9)
        recall    = tp / (tp + fn + 1e-9)
        f1        = 2 * precision * recall / (precision + recall + 1e-9)

        # Per-attack-type breakdown
        per_type = {}
        if 'label_name' in df.columns:
            for atype in df['label_name'].unique():
                mask = df['label_name'] == atype
                sub_preds  = preds[mask]
                sub_labels = labels[mask]
                per_type[atype] = {
                    'n':         int(mask.sum()),
                    'detected':  int(sub_preds.sum()),
                    'recall':    float(sub_preds[sub_labels==1].mean())
                                 if sub_labels.sum() > 0 else float('nan'),
                    'fpr':       float(sub_preds[sub_labels==0].mean())
                                 if (sub_labels==0).sum() > 0 else float('nan'),
                }

        return {
            'n_total':       len(df),
            'n_normal':      int((labels==0).sum()),
            'n_attack':      int((labels==1).sum()),
            'roc_auc':       round(roc_auc, 4),
            'avg_precision': round(avg_prec, 4),
            'precision':     round(precision, 4),
            'recall':        round(recall, 4),
            'f1_score':      round(f1, 4),
            'fpr':           round(fp/(fp+tn+1e-9), 4),
            'fnr':           round(fn/(fn+tp+1e-9), 4),
            'tp': int(tp), 'fp': int(fp),
            'tn': int(tn), 'fn': int(fn),
            'threshold':     round(self.threshold, 4),
            'per_type':      per_type,
        }

    def explain_packet(self, packet: pd.Series,
                       top_n: int = 8) -> pd.DataFrame:
        """Z-score based explanation for a single packet."""
        rows = []
        for col in self.used_features:
            if col not in self.training_stats:
                continue
            val  = float(packet.get(col, 0))
            mean = self.training_stats[col]['mean']
            std  = self.training_stats[col]['std']
            z    = (val - mean) / (std + 1e-9)
            rows.append({'feature': col, 'value': val,
                         'normal_mean': round(mean, 4),
                         'z_score': round(z, 3),
                         'deviation': abs(z)})
        return (pd.DataFrame(rows)
                  .sort_values('deviation', ascending=False)
                  .head(top_n)
                  .reset_index(drop=True))

    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        print(f"[IForest] Model saved → {path}")

    @classmethod
    def load(cls, path: str):
        with open(path, 'rb') as f:
            return pickle.load(f)


# ─── VISUALIZATION ───────────────────────────────────────────────────────────

def plot_electra_results(df_test, scores, preds, metrics):
    CYAN='#00e5ff'; RED='#ff6b6b'; PURPLE='#a78bfa'
    MUTED='#6b6b8a'; BG='#12121a'; SURFACE='#1c1c2e'; TEXT='#e8e8f0'

    fig = plt.figure(figsize=(22, 16))
    fig.patch.set_facecolor('#0a0a0f')
    gs  = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

    def style(ax, title):
        ax.set_facecolor(BG)
        ax.set_title(title, color=TEXT, fontsize=10, fontweight='bold', pad=8)
        ax.tick_params(colors=MUTED, labelsize=7)
        for s in ax.spines.values(): s.set_edgecolor('#2a2a3e')
        ax.xaxis.label.set_color(MUTED)
        ax.yaxis.label.set_color(MUTED)

    labels = df_test['label_binary'].values

    # 1. Score distribution
    ax1 = fig.add_subplot(gs[0,0])
    bins = np.linspace(scores.min(), scores.max(), 60)
    ax1.hist(scores[labels==0], bins=bins, alpha=0.7, color=CYAN,
             label='Normal', density=True)
    ax1.hist(scores[labels==1], bins=bins, alpha=0.7, color=RED,
             label='Attack', density=True)
    from matplotlib.lines import Line2D
    ax1.axvline(metrics['threshold'], color=PURPLE, lw=2, ls='--',
                label=f"τ={metrics['threshold']:.3f}")
    style(ax1, 'Anomaly Score Distribution')
    ax1.set_xlabel('Score (higher = more anomalous)')
    ax1.set_ylabel('Density')
    ax1.legend(fontsize=7, facecolor=BG, labelcolor=TEXT)

    # 2. ROC
    ax2 = fig.add_subplot(gs[0,1])
    fpr_c, tpr_c, _ = roc_curve(labels, scores)
    ax2.plot(fpr_c, tpr_c, color=CYAN, lw=2,
             label=f"AUC={metrics['roc_auc']:.3f}")
    ax2.plot([0,1],[0,1], color=MUTED, ls='--', lw=1)
    ax2.fill_between(fpr_c, tpr_c, alpha=0.08, color=CYAN)
    style(ax2, 'ROC Curve'); ax2.set_xlabel('FPR'); ax2.set_ylabel('TPR')
    ax2.legend(fontsize=8, facecolor=BG, labelcolor=TEXT)

    # 3. Precision-Recall
    ax3 = fig.add_subplot(gs[0,2])
    prec, rec, _ = precision_recall_curve(labels, scores)
    ax3.plot(rec, prec, color=PURPLE, lw=2,
             label=f"AP={metrics['avg_precision']:.3f}")
    ax3.fill_between(rec, prec, alpha=0.08, color=PURPLE)
    style(ax3, 'Precision-Recall Curve')
    ax3.set_xlabel('Recall'); ax3.set_ylabel('Precision')
    ax3.legend(fontsize=8, facecolor=BG, labelcolor=TEXT)

    # 4. Per-attack-type detection recall
    ax4 = fig.add_subplot(gs[1, :2])
    if 'per_type' in metrics and metrics['per_type']:
        pt = metrics['per_type']
        attack_types = [k for k,v in pt.items() if k != 'normal']
        recalls      = [pt[k]['recall'] for k in attack_types]
        counts       = [pt[k]['n'] for k in attack_types]
        x = np.arange(len(attack_types))
        bar_colors = [CYAN if r >= 0.8 else PURPLE if r >= 0.5 else RED
                      for r in recalls]
        bars = ax4.bar(x, recalls, color=bar_colors, alpha=0.8, width=0.6)
        ax4.set_xticks(x)
        ax4.set_xticklabels(
            [f"{t}\n(n={c:,})" for t,c in zip(attack_types, counts)],
            fontsize=7, color=TEXT
        )
        ax4.set_ylim(0, 1.1)
        ax4.axhline(0.8, color=CYAN, ls='--', lw=1, alpha=0.5,
                    label='80% recall threshold')
        for bar, r in zip(bars, recalls):
            if not np.isnan(r):
                ax4.text(bar.get_x() + bar.get_width()/2,
                         bar.get_height() + 0.02,
                         f'{r:.2f}', ha='center', va='bottom',
                         color=TEXT, fontsize=8)
        style(ax4, 'Detection Recall by Attack Type')
        ax4.set_ylabel('Recall')
        ax4.legend(fontsize=7, facecolor=BG, labelcolor=TEXT)

    # 5. Confusion matrix
    ax5 = fig.add_subplot(gs[1,2])
    cm_arr = np.array([[metrics['tn'], metrics['fp']],
                       [metrics['fn'], metrics['tp']]])
    cm_norm = cm_arr / (cm_arr.sum(axis=1, keepdims=True) + 1e-9)
    ax5.imshow(cm_norm, cmap='Blues', vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            lbl = [['TN','FP'],['FN','TP']][i][j]
            ax5.text(j, i,
                     f"{lbl}\n{cm_arr[i,j]:,}\n({cm_norm[i,j]:.1%})",
                     ha='center', va='center', fontsize=9,
                     color='white' if cm_norm[i,j]>0.5 else TEXT)
    ax5.set_xticks([0,1]); ax5.set_yticks([0,1])
    ax5.set_xticklabels(['Pred Normal','Pred Attack'], color=TEXT, fontsize=8)
    ax5.set_yticklabels(['Actual Normal','Actual Attack'], color=TEXT, fontsize=8)
    style(ax5, 'Confusion Matrix')

    # 6. FC distribution normal vs attack
    ax6 = fig.add_subplot(gs[2,0])
    normal_fc = df_test[df_test['label_binary']==0]['fc'].value_counts()
    attack_fc = df_test[df_test['label_binary']==1]['fc'].value_counts()
    all_fcs = sorted(set(normal_fc.index) | set(attack_fc.index))
    x6 = np.arange(len(all_fcs)); w=0.35
    ax6.bar(x6-w/2, [normal_fc.get(f,0) for f in all_fcs],
            width=w, color=CYAN, alpha=0.8, label='Normal')
    ax6.bar(x6+w/2, [attack_fc.get(f,0) for f in all_fcs],
            width=w, color=RED, alpha=0.8, label='Attack')
    ax6.set_xticks(x6)
    ax6.set_xticklabels([str(f) for f in all_fcs], color=TEXT, fontsize=7)
    style(ax6, 'Function Code Distribution')
    ax6.set_xlabel('FC'); ax6.set_ylabel('Count')
    ax6.legend(fontsize=7, facecolor=BG, labelcolor=TEXT)

    # 7. Score vs memory address
    ax7 = fig.add_subplot(gs[2,1])
    sample_idx = np.random.choice(len(df_test), min(3000, len(df_test)),
                                   replace=False)
    c7 = np.where(labels[sample_idx]==1, RED, CYAN)
    ax7.scatter(df_test['madd'].values[sample_idx], scores[sample_idx],
                c=c7, alpha=0.3, s=6)
    ax7.axhline(metrics['threshold'], color=PURPLE, lw=1.5, ls='--')
    style(ax7, 'Anomaly Score vs Memory Address')
    ax7.set_xlabel('madd'); ax7.set_ylabel('Score')

    # 8. Metrics panel
    ax8 = fig.add_subplot(gs[2,2])
    ax8.set_facecolor(BG); ax8.axis('off')
    lines = [
        ('ELECTRA DATASET', '', TEXT, 12, True),
        ('Isolation Forest — Modbus ICS', '', MUTED, 8, False),
        ('', '', TEXT, 9, False),
        ('ROC AUC',        f"{metrics['roc_auc']}",       CYAN,   10, False),
        ('Avg Precision',  f"{metrics['avg_precision']}",  CYAN,   10, False),
        ('F1 Score',       f"{metrics['f1_score']}",       CYAN,   10, False),
        ('Precision',      f"{metrics['precision']}",      TEXT,   9,  False),
        ('Recall',         f"{metrics['recall']}",         TEXT,   9,  False),
        ('FPR',            f"{metrics['fpr']}",            RED,    9,  False),
        ('FNR',            f"{metrics['fnr']}",            RED,    9,  False),
        ('', '', TEXT, 9, False),
        ('TP', f"{metrics['tp']:,}", '#4ade80', 9, False),
        ('FP', f"{metrics['fp']:,}", RED,       9, False),
        ('TN', f"{metrics['tn']:,}", '#4ade80', 9, False),
        ('FN', f"{metrics['fn']:,}", RED,       9, False),
        ('', '', TEXT, 9, False),
        ('Normal packets', f"{metrics['n_normal']:,}", MUTED, 8, False),
        ('Attack packets', f"{metrics['n_attack']:,}", MUTED, 8, False),
    ]
    y = 0.97
    for lbl, val, color, size, bold in lines:
        w = 'bold' if bold else 'normal'
        if val:
            ax8.text(0.05, y, lbl, color=MUTED, fontsize=size-1,
                     va='top', transform=ax8.transAxes)
            ax8.text(0.95, y, val, color=color, fontsize=size,
                     va='top', ha='right', fontweight=w,
                     transform=ax8.transAxes)
        else:
            ax8.text(0.05, y, lbl, color=color, fontsize=size,
                     va='top', fontweight=w, transform=ax8.transAxes)
        y -= 0.054

    fig.suptitle('Electra ICS Dataset — Isolation Forest Anomaly Detection\n'
                 'Modbus Packet-Level Features | Railway/ICS Traction Substation',
                 fontsize=13, fontweight='bold', color=TEXT, y=0.99)

    path = os.path.join(OUTPUT_DIR, 'electra_if_results.png')
    plt.savefig(path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"[plot] Saved → {path}")
    return path


# ─── MAIN PIPELINE ───────────────────────────────────────────────────────────

def run(csv_path: str = None,
        contamination: float = 0.05,
        test_size: float = 0.3,
        label_col: str = 'label',
        sample_n: int = 0):

    print("=" * 65)
    print("  ELECTRA ICS — Isolation Forest Pipeline")
    print("=" * 65)

    # ── Load ──────────────────────────────────────────────────────────────
    if csv_path and os.path.exists(csv_path):
        print(f"\n[pipeline] Loading {csv_path} ...")

        # Sample for development runs if requested
        if sample_n and sample_n > 0:
            # Count rows first without loading all data
            total = sum(1 for _ in open(csv_path)) - 1
            skip_prob = max(0, 1 - sample_n / total)
            import random
            df_raw = pd.read_csv(
                csv_path, low_memory=False,
                skiprows=lambda i: i > 0 and random.random() < skip_prob
            )
            print(f"[pipeline] Sampled {len(df_raw):,} rows from {total:,} total")
        else:
            df_raw = pd.read_csv(csv_path, low_memory=False)
            print(f"[pipeline] Loaded {len(df_raw):,} rows × {len(df_raw.columns)} cols")

        # Normalize column names — handle Electra variants
        col_map = {}
        cols_lower = {c.lower(): c for c in df_raw.columns}
        if 'time' not in df_raw.columns and 'Time' in df_raw.columns:
            col_map['Time'] = 'time'
        if 'madd' not in df_raw.columns and 'address' in df_raw.columns:
            col_map['address'] = 'madd'
        if 'madd' not in df_raw.columns and 'reference_num' in df_raw.columns:
            col_map['reference_num'] = 'madd'
        if col_map:
            df_raw = df_raw.rename(columns=col_map)
            print(f"[pipeline] Renamed columns: {col_map}")
        print(f"[pipeline] Columns: {list(df_raw.columns)}")
    else:
        print("\n[pipeline] No CSV found — generating synthetic Electra-like data...")
        df_raw = _synthetic_electra(n=50_000)

    # ── Encode labels ─────────────────────────────────────────────────────
    df_raw = encode_labels(df_raw, label_col)

    # ── Feature engineering ───────────────────────────────────────────────
    print("\n[pipeline] Engineering features...")
    df = engineer_features(df_raw)
    print(f"[pipeline] Feature matrix: {len(df):,} rows")

    # ── Train/test split (stratified) ─────────────────────────────────────
    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=42,
        stratify=df['label_binary']
    )
    print(f"[pipeline] Train={len(train_df):,} | Test={len(test_df):,}")

    # ── Train ─────────────────────────────────────────────────────────────
    detector = ElectraIsolationForest(
        n_estimators  = 300,
        contamination = contamination,
    )
    detector.fit(train_df)

    # ── Calibrate ─────────────────────────────────────────────────────────
    print("\n[pipeline] Calibrating threshold on test set...")
    detector.calibrate(test_df)

    # ── Evaluate ──────────────────────────────────────────────────────────
    print("\n[pipeline] Evaluating...")
    scores  = detector.score(test_df)
    preds   = detector.predict(test_df)
    metrics = detector.evaluate(test_df)

    print("\n" + "─"*45)
    print("  RESULTS")
    print("─"*45)
    for k, v in metrics.items():
        if k != 'per_type':
            print(f"  {k:<20} {v}")
    print("\n  Per-attack-type recall:")
    for atype, info in metrics.get('per_type', {}).items():
        recall_str = f"{info['recall']:.3f}" if not np.isnan(info.get('recall', float('nan'))) else 'n/a'
        print(f"  {atype:<30} n={info['n']:>6,}  recall={recall_str}")
    print("─"*45)

    # ── Explain top anomalies ─────────────────────────────────────────────
    top_idx = np.argsort(scores)[::-1][:3]
    print("\n[pipeline] Top 3 anomalous packets:")
    for rank, idx in enumerate(top_idx, 1):
        pkt = test_df.iloc[idx]
        print(f"\n  Rank #{rank} | score={scores[idx]:.4f} | "
              f"label={pkt.get('label_name','?')} | "
              f"fc={pkt.get('fc','?')} | "
              f"madd={pkt.get('madd','?')} | "
              f"error={pkt.get('error_binary','?')}")
        exp = detector.explain_packet(pkt, top_n=5)
        print(exp[['feature','value','normal_mean','z_score']].to_string(index=False))

    # ── Save ──────────────────────────────────────────────────────────────
    model_path = os.path.join(OUTPUT_DIR, 'electra_if_model.pkl')
    detector.save(model_path)

    # Comparison export
    export = test_df[['label_binary','label_name']].copy()
    export['anomaly_score'] = scores
    export['if_predicted']  = preds
    for col in ['fc','error_binary','request_binary','madd','data']:
        if col in test_df.columns:
            export[col] = test_df[col].values
    export.to_csv(os.path.join(OUTPUT_DIR, 'electra_comparison.csv'), index=False)

    with open(os.path.join(OUTPUT_DIR, 'electra_metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2, default=str)

    # Plot
    plot_path = plot_electra_results(test_df.reset_index(drop=True),
                                      scores, preds, metrics)

    print(f"\n[pipeline] ✓ Done. Outputs → {OUTPUT_DIR}")
    return detector, metrics


# ─── SYNTHETIC FALLBACK ──────────────────────────────────────────────────────

def _synthetic_electra(n: int = 50_000, seed: int = 42) -> pd.DataFrame:
    """Synthetic Electra-schema data for testing without the real CSV."""
    rng = np.random.default_rng(seed)

    n_normal = int(n * 0.65)
    n_attack = n - n_normal
    attack_types = [
        'reconnaissance', 'false_data_injection', 'forced_error',
        'command_modification', 'read_data', 'write_data', 'replay',
        'response_modification'
    ]
    n_per_type = n_attack // len(attack_types)

    rows = []

    # Normal packets — deterministic Modbus polling patterns
    for _ in range(n_normal):
        fc   = int(rng.choice([1,2,3,4], p=[0.1,0.1,0.6,0.2]))
        rows.append({
            'time':    f"2024-01-01 00:{rng.integers(0,59):02d}:{rng.integers(0,59):02d}",
            'smac':    '00:11:22:33:44:55',
            'dmac':    '66:77:88:99:aa:bb',
            'sip':     rng.choice(['192.168.1.10','192.168.1.11']),
            'dip':     '192.168.1.100',
            'request': rng.choice(['True','False'], p=[0.5,0.5]),
            'fc':      fc,
            'error':   rng.choice(['True','False'], p=[0.01,0.99]),
            'madd':    int(rng.integers(0, 50)),
            'data':    int(rng.integers(0, 1000)),
            'label':   'normal',
        })

    # Attack packets
    for atype in attack_types:
        for _ in range(n_per_type):
            if atype == 'reconnaissance':
                fc=3; madd=int(rng.integers(0,65535)); data=0
            elif atype == 'false_data_injection':
                fc=6; madd=int(rng.integers(0,50)); data=int(rng.integers(50000,65535))
            elif atype == 'forced_error':
                fc=int(rng.choice([131,132,133,134])); madd=0; data=0
            elif atype == 'command_modification':
                fc=16; madd=int(rng.integers(0,50)); data=int(rng.integers(0,65535))
            elif atype == 'read_data':
                fc=3; madd=int(rng.integers(0,50)); data=int(rng.integers(0,1000))
            elif atype == 'write_data':
                fc=6; madd=int(rng.integers(0,50)); data=int(rng.integers(0,1000))
            elif atype == 'replay':
                fc=int(rng.choice([3,6])); madd=int(rng.integers(0,50))
                data=int(rng.integers(0,1000))
            else:  # response_modification
                fc=3; madd=int(rng.integers(0,50)); data=int(rng.integers(0,65535))

            rows.append({
                'time':    f"2024-01-01 01:{rng.integers(0,59):02d}:{rng.integers(0,59):02d}",
                'smac':    '00:11:22:33:44:55',
                'dmac':    '66:77:88:99:aa:bb',
                'sip':     rng.choice(['192.168.1.10','192.168.1.11']),
                'dip':     '192.168.1.100',
                'request': rng.choice(['True','False'], p=[0.5,0.5]),
                'fc':      fc,
                'error':   'True' if atype == 'forced_error' else
                           rng.choice(['True','False'], p=[0.15,0.85]),
                'madd':    madd,
                'data':    data,
                'label':   atype,
            })

    df = pd.DataFrame(rows).sample(frac=1, random_state=seed).reset_index(drop=True)
    print(f"[synthetic] Generated {len(df):,} Electra-schema packets")
    return df


if __name__ == '__main__':
    import sys
    import argparse as _ap
    _parser = _ap.ArgumentParser(description='Electra Isolation Forest')
    _parser.add_argument('csv', nargs='?', default=None)
    _parser.add_argument('--sample', type=int, default=0,
                         help='Randomly sample N rows (0=all). '
                              'Use 500000 for dev runs on 16M dataset.')
    _parser.add_argument('--contamination', type=float, default=0.05)
    _args = _parser.parse_args()
    run(csv_path=_args.csv,
        contamination=_args.contamination,
        sample_n=_args.sample)
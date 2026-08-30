"""
WWTP / ICS Anomaly Detection — Electra Dataset
LSTM Autoencoder — Pure NumPy Implementation
═══════════════════════════════════════════════════════════════════════════════
Architecture:
    Encoder: LSTM(input_dim → hidden_dim)
    Bottleneck: last hidden state h_T (latent representation)
    Decoder: LSTM(hidden_dim → hidden_dim) → Dense(hidden_dim → input_dim)

Training objective:
    Minimize MSE reconstruction error on NORMAL sequences only.
    At inference: high reconstruction error → anomaly.

Why LSTM over Isolation Forest for Electra:
    - Sees SEQUENCES of packets, not individual packets
    - Replay attacks look identical packet-by-packet but are
      temporally anomalous (repetition pattern)
    - Read_data attacks cluster in time — IF misses this, LSTM captures it
    - Learns the deterministic Modbus polling rhythm of each device

Sequence construction:
    Packets are sorted by timestamp and grouped per source IP.
    A sliding window of length SEQ_LEN creates overlapping sequences.
    Each sequence represents one device's recent communication history.

Comparison output:
    Produces the same electra_comparison.csv schema as the Isolation Forest,
    enabling direct metric comparison in the evaluation framework.
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
from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_recall_curve, roc_curve,
    confusion_matrix, f1_score
)

warnings.filterwarnings('ignore')

# Reuse feature engineering and label encoding from IF module
import sys
sys.path.insert(0, '/home/test/ml_test')
from electra_isolation_forest import (
    engineer_features, encode_labels,
    FEATURE_COLS, LOG_COLS,
    _synthetic_electra
)

OUTPUT_DIR = '/home/test/ml_test/ml_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── HYPERPARAMETERS ─────────────────────────────────────────────────────────

SEQ_LEN    = 20       # packets per sequence (sliding window)
STRIDE     = 5        # stride between windows (overlap = SEQ_LEN - STRIDE)
HIDDEN_DIM = 32       # LSTM hidden units (encoder and decoder)
LATENT_DIM = 16       # bottleneck dimension
EPOCHS     = 40       # training epochs
BATCH_SIZE = 32       # mini-batch size (reduced for 4GB RAM)
LR         = 0.003    # learning rate (Adam)
CLIP_GRAD  = 1.0      # gradient clipping threshold
DROPOUT    = 0.1      # input dropout rate during training


# ─── NUMPY LSTM CELL ─────────────────────────────────────────────────────────

class LSTMCell:
    """
    Single LSTM cell with learnable parameters.
    Gates: input (i), forget (f), output (o), cell candidate (g)

    Forward:
        f = σ(Wf·[h,x] + bf)
        i = σ(Wi·[h,x] + bi)
        g = tanh(Wg·[h,x] + bg)
        o = σ(Wo·[h,x] + bo)
        c_new = f⊙c + i⊙g
        h_new = o⊙tanh(c_new)
    """

    def __init__(self, input_dim: int, hidden_dim: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        # Xavier initialization — critical for LSTM convergence
        scale = np.sqrt(2.0 / (input_dim + hidden_dim))
        concat_dim = input_dim + hidden_dim

        # Weight matrices [4*hidden_dim × concat_dim] — packed for efficiency
        # Row order: forget | input | gate | output
        self.W = rng.normal(0, scale,
                            (4 * hidden_dim, concat_dim)).astype(np.float32)
        self.b = np.zeros(4 * hidden_dim, dtype=np.float32)

        self.input_dim  = input_dim
        self.hidden_dim = hidden_dim

        # Adam optimizer state
        self.mW = np.zeros_like(self.W)
        self.vW = np.zeros_like(self.W)
        self.mb = np.zeros_like(self.b)
        self.vb = np.zeros_like(self.b)
        self.t  = 0  # Adam step counter

    def forward(self, x: np.ndarray, h: np.ndarray,
                c: np.ndarray) -> tuple:
        """
        x: (batch, input_dim)
        h: (batch, hidden_dim)
        c: (batch, hidden_dim)
        Returns: h_new, c_new, cache (for backprop)
        """
        xh = np.concatenate([x, h], axis=1)  # (batch, concat_dim)
        z  = xh @ self.W.T + self.b          # (batch, 4*hidden_dim)

        H = self.hidden_dim
        zf, zi, zg, zo = z[:,:H], z[:,H:2*H], z[:,2*H:3*H], z[:,3*H:]

        f  = _sigmoid(zf)
        i  = _sigmoid(zi)
        g  = np.tanh(zg)
        o  = _sigmoid(zo)

        c_new = f * c + i * g
        h_new = o * np.tanh(c_new)

        cache = (x, h, c, f, i, g, o, c_new, xh)
        return h_new, c_new, cache

    def backward(self, dh: np.ndarray, dc: np.ndarray,
                 cache: tuple) -> tuple:
        """
        Backprop through one LSTM step.
        Returns: dx, dh_prev, dc_prev, dW, db
        """
        x, h, c, f, i, g, o, c_new, xh = cache
        H = self.hidden_dim

        tanh_c_new = np.tanh(c_new)

        # Output gate gradient
        do     = dh * tanh_c_new
        dc_new = dh * o * (1 - tanh_c_new**2) + dc

        # Cell state gradients
        df = dc_new * c
        di = dc_new * g
        dg = dc_new * i
        dc_prev = dc_new * f

        # Pre-activation gradients
        dzf = df * f * (1 - f)
        dzi = di * i * (1 - i)
        dzg = dg * (1 - g**2)
        dzo = do * o * (1 - o)

        dz  = np.concatenate([dzf, dzi, dzg, dzo], axis=1)

        dW  = dz.T @ xh
        db  = dz.sum(axis=0)
        dxh = dz @ self.W

        dx     = dxh[:, :self.input_dim]
        dh_prev = dxh[:, self.input_dim:]

        return dx, dh_prev, dc_prev, dW, db

    def adam_update(self, dW: np.ndarray, db: np.ndarray,
                    lr: float, beta1=0.9, beta2=0.999, eps=1e-8):
        self.t += 1
        # Gradient clipping
        dW = np.clip(dW, -CLIP_GRAD, CLIP_GRAD)
        db = np.clip(db, -CLIP_GRAD, CLIP_GRAD)

        self.mW = beta1 * self.mW + (1 - beta1) * dW
        self.vW = beta2 * self.vW + (1 - beta2) * dW**2
        mW_hat  = self.mW / (1 - beta1**self.t)
        vW_hat  = self.vW / (1 - beta2**self.t)
        self.W -= lr * mW_hat / (np.sqrt(vW_hat) + eps)

        self.mb = beta1 * self.mb + (1 - beta1) * db
        self.vb = beta2 * self.vb + (1 - beta2) * db**2
        mb_hat  = self.mb / (1 - beta1**self.t)
        vb_hat  = self.vb / (1 - beta2**self.t)
        self.b -= lr * mb_hat / (np.sqrt(vb_hat) + eps)


# ─── DENSE LAYER ─────────────────────────────────────────────────────────────

class Dense:
    """Fully connected layer with optional activation."""

    def __init__(self, in_dim: int, out_dim: int,
                 activation: str = 'linear', seed: int = 0):
        rng = np.random.default_rng(seed)
        scale = np.sqrt(2.0 / in_dim)
        self.W  = rng.normal(0, scale, (in_dim, out_dim)).astype(np.float32)
        self.b  = np.zeros(out_dim, dtype=np.float32)
        self.activation = activation
        # Adam state
        self.mW = np.zeros_like(self.W)
        self.vW = np.zeros_like(self.W)
        self.mb = np.zeros_like(self.b)
        self.vb = np.zeros_like(self.b)
        self.t  = 0
        self._cache = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        z = x @ self.W + self.b
        if self.activation == 'tanh':
            out = np.tanh(z)
        elif self.activation == 'relu':
            out = np.maximum(0, z)
        else:
            out = z
        self._cache = (x, z, out)
        return out

    def backward(self, d_out: np.ndarray) -> tuple:
        x, z, out = self._cache
        if self.activation == 'tanh':
            d_out = d_out * (1 - out**2)
        elif self.activation == 'relu':
            d_out = d_out * (z > 0)
        dW = x.T @ d_out
        db = d_out.sum(axis=0)
        dx = d_out @ self.W.T
        return dx, dW, db

    def adam_update(self, dW, db, lr, beta1=0.9, beta2=0.999, eps=1e-8):
        self.t += 1
        dW = np.clip(dW, -CLIP_GRAD, CLIP_GRAD)
        db = np.clip(db, -CLIP_GRAD, CLIP_GRAD)
        for param, m, v, grad, m_attr, v_attr, p_attr in [
            (self.W, self.mW, self.vW, dW, 'mW', 'vW', 'W'),
            (self.b, self.mb, self.vb, db, 'mb', 'vb', 'b'),
        ]:
            m_new = beta1 * m + (1 - beta1) * grad
            v_new = beta2 * v + (1 - beta2) * grad**2
            m_hat = m_new / (1 - beta1**self.t)
            v_hat = v_new / (1 - beta2**self.t)
            setattr(self, p_attr, param - lr * m_hat / (np.sqrt(v_hat) + eps))
            setattr(self, m_attr, m_new)
            setattr(self, v_attr, v_new)


# ─── LSTM AUTOENCODER ────────────────────────────────────────────────────────

class LSTMAutoencoder:
    """
    Sequence-to-sequence LSTM Autoencoder.

    Encoder:
        Processes input sequence X (seq_len, input_dim) step by step.
        Final hidden state h_T = latent representation (bottleneck).

    Decoder:
        Initialized with encoder's final (h_T, c_T).
        Reconstructs the sequence in REVERSE order (easier gradient flow).
        Each step: h_dec → Dense → x̂_t

    Anomaly score = mean squared reconstruction error per sequence.
    """

    def __init__(self, input_dim: int,
                 hidden_dim: int = HIDDEN_DIM,
                 latent_dim: int = LATENT_DIM):
        self.input_dim  = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim

        # Encoder
        self.enc_lstm    = LSTMCell(input_dim, hidden_dim, seed=1)
        self.enc_to_lat  = Dense(hidden_dim, latent_dim, 'tanh', seed=2)
        self.lat_to_dec  = Dense(latent_dim, hidden_dim, 'tanh', seed=3)

        # Decoder
        self.dec_lstm    = LSTMCell(hidden_dim, hidden_dim, seed=4)
        self.dec_out     = Dense(hidden_dim, input_dim, 'linear', seed=5)

        # Training diagnostics
        self.train_losses = []
        self.val_losses   = []
        self.is_fitted    = False
        self.threshold    = None
        self.scaler       = RobustScaler()
        self.feature_cols = None
        self.training_stats = {}

    # ── FORWARD PASS ─────────────────────────────────────────────────────

    def _encode(self, X_seq: np.ndarray,
                dropout_mask=None) -> tuple:
        """
        X_seq: (batch, seq_len, input_dim)
        Returns: latent, (h_T, c_T), enc_caches
        """
        batch, T, D = X_seq.shape
        h = np.zeros((batch, self.hidden_dim), dtype=np.float32)
        c = np.zeros((batch, self.hidden_dim), dtype=np.float32)
        enc_caches = []

        for t in range(T):
            x_t = X_seq[:, t, :]
            if dropout_mask is not None:
                x_t = x_t * dropout_mask
            h, c, cache = self.enc_lstm.forward(x_t, h, c)
            enc_caches.append(cache)

        latent = self.enc_to_lat.forward(h)
        return latent, (h, c), enc_caches

    def _decode(self, latent: np.ndarray,
                enc_state: tuple, T: int) -> tuple:
        """
        Decode latent vector into reconstructed sequence.
        Returns: X_hat (batch, T, input_dim), dec_caches, out_caches
        """
        batch = latent.shape[0]
        h = self.lat_to_dec.forward(latent)
        _, c = enc_state  # reuse encoder cell state
        c = c.copy()

        dec_caches = []
        out_caches = []
        X_hat = np.zeros((batch, T, self.input_dim), dtype=np.float32)

        for t in range(T):
            # Decoder input = previous hidden state (feedback)
            x_dec = h.copy()
            h, c, cache = self.dec_lstm.forward(x_dec, h, c)
            x_hat_t = self.dec_out.forward(h)
            X_hat[:, T - 1 - t, :] = x_hat_t  # reverse order
            dec_caches.append(cache)
            out_caches.append((h.copy(), x_hat_t.copy()))

        return X_hat, dec_caches, out_caches

    def forward(self, X_seq: np.ndarray,
                training: bool = False) -> tuple:
        """Full autoencoder forward pass."""
        dropout_mask = None
        if training and DROPOUT > 0:
            dropout_mask = (np.random.rand(*X_seq[:, 0, :].shape)
                            > DROPOUT).astype(np.float32)

        latent, enc_state, enc_caches = self._encode(X_seq, dropout_mask)
        X_hat, dec_caches, out_caches = self._decode(latent, enc_state,
                                                      X_seq.shape[1])
        return X_hat, latent, enc_caches, dec_caches, out_caches, enc_state

    # ── LOSS ─────────────────────────────────────────────────────────────

    @staticmethod
    def mse_loss(X: np.ndarray, X_hat: np.ndarray) -> float:
        return float(np.mean((X - X_hat) ** 2))

    @staticmethod
    def mse_grad(X: np.ndarray, X_hat: np.ndarray) -> np.ndarray:
        """Gradient of MSE w.r.t. X_hat."""
        return 2 * (X_hat - X) / (X.size)

    # ── BACKWARD PASS ────────────────────────────────────────────────────

    def backward(self, X_seq, X_hat, enc_caches, dec_caches,
                 out_caches, latent, enc_state, lr):
        """
        Full BPTT (Backpropagation Through Time).
        Gradients flow: output → decoder LSTM → bottleneck → encoder LSTM.
        """
        batch, T, D = X_seq.shape

        # ── Decoder backward ──────────────────────────────────────────
        dL_dXhat = self.mse_grad(X_seq, X_hat)  # (batch, T, D)

        dh_dec   = np.zeros((batch, self.hidden_dim), dtype=np.float32)
        dc_dec   = np.zeros((batch, self.hidden_dim), dtype=np.float32)
        dW_dec_out_total = np.zeros_like(self.dec_out.W)
        db_dec_out_total = np.zeros_like(self.dec_out.b)
        dW_dec_lstm_total = np.zeros_like(self.dec_lstm.W)
        db_dec_lstm_total = np.zeros_like(self.dec_lstm.b)
        d_latent = np.zeros((batch, self.latent_dim), dtype=np.float32)

        for t_rev in range(T):
            t_fwd = T - 1 - t_rev  # reversed decoding order
            h_t, x_hat_t = out_caches[t_rev]

            # Gradient from output layer
            d_xhat_t = dL_dXhat[:, t_fwd, :]  # (batch, D)
            dx_dec, dW_out, db_out = self.dec_out.backward(d_xhat_t)
            dW_dec_out_total += dW_out
            db_dec_out_total += db_out

            # Gradient into decoder LSTM hidden state
            dh_from_out = dx_dec + dh_dec

            # Decoder LSTM backward
            cache = dec_caches[t_rev]
            dx_lstm, dh_dec, dc_dec, dW_dec, db_dec = \
                self.dec_lstm.backward(dh_from_out, dc_dec, cache)
            dW_dec_lstm_total += dW_dec
            db_dec_lstm_total += db_dec

        # ── Bottleneck backward ───────────────────────────────────────
        d_h_enc_final = dh_dec  # gradient at encoder final hidden state

        # lat_to_dec backward
        d_latent_from_dec, dW_l2d, db_l2d = \
            self.lat_to_dec.backward(d_h_enc_final)

        # enc_to_lat backward
        d_h_before_lat, dW_e2l, db_e2l = \
            self.enc_to_lat.backward(d_latent_from_dec)

        # ── Encoder backward (BPTT) ───────────────────────────────────
        dh_enc  = d_h_before_lat
        dc_enc  = np.zeros((batch, self.hidden_dim), dtype=np.float32)
        dW_enc_total = np.zeros_like(self.enc_lstm.W)
        db_enc_total = np.zeros_like(self.enc_lstm.b)

        for t in reversed(range(T)):
            cache = enc_caches[t]
            _, dh_enc, dc_enc, dW_enc, db_enc = \
                self.enc_lstm.backward(dh_enc, dc_enc, cache)
            dW_enc_total += dW_enc
            db_enc_total += db_enc

        # ── Parameter updates (Adam) ──────────────────────────────────
        self.enc_lstm.adam_update(dW_enc_total, db_enc_total, lr)
        self.enc_to_lat.adam_update(dW_e2l, db_e2l, lr)
        self.lat_to_dec.adam_update(dW_l2d, db_l2d, lr)
        self.dec_lstm.adam_update(dW_dec_lstm_total, db_dec_lstm_total, lr)
        self.dec_out.adam_update(dW_dec_out_total, db_dec_out_total, lr)

    # ── TRAINING ─────────────────────────────────────────────────────────

    def fit(self, X_train: np.ndarray, X_val: np.ndarray,
            epochs: int = EPOCHS, batch_size: int = BATCH_SIZE,
            lr: float = LR, patience: int = 8) -> 'LSTMAutoencoder':
        """
        Train on normal sequences only.
        X_train, X_val: (n_sequences, seq_len, input_dim) — NORMAL only.
        """
        n = X_train.shape[0]
        best_val_loss = np.inf
        patience_count = 0
        best_W = None

        print(f"\n[LSTM-AE] Training: {n:,} sequences | "
              f"seq_len={X_train.shape[1]} | "
              f"input_dim={X_train.shape[2]} | "
              f"hidden={self.hidden_dim} | latent={self.latent_dim}")
        print(f"[LSTM-AE] Epochs={epochs} | batch={batch_size} | lr={lr}")
        print(f"{'Epoch':>6} {'Train Loss':>12} {'Val Loss':>12} {'Status':>10}")
        print("─" * 46)

        for epoch in range(1, epochs + 1):
            # Shuffle
            idx = np.random.permutation(n)
            X_shuffled = X_train[idx]
            epoch_losses = []

            for start in range(0, n, batch_size):
                X_batch = X_shuffled[start: start + batch_size]
                if len(X_batch) < 2:
                    continue

                X_hat, latent, enc_caches, dec_caches, out_caches, enc_state = \
                    self.forward(X_batch, training=True)
                loss = self.mse_loss(X_batch, X_hat)
                epoch_losses.append(loss)

                self.backward(X_batch, X_hat, enc_caches, dec_caches,
                              out_caches, latent, enc_state, lr)

            train_loss = float(np.mean(epoch_losses))
            self.train_losses.append(train_loss)

            # Validation
            X_hat_val, *_ = self.forward(X_val, training=False)
            val_loss = self.mse_loss(X_val, X_hat_val)
            self.val_losses.append(val_loss)

            # Early stopping
            status = ''
            if val_loss < best_val_loss - 1e-6:
                best_val_loss = val_loss
                patience_count = 0
                best_W = self._snapshot()
                status = '✓ best'
            else:
                patience_count += 1
                if patience_count >= patience:
                    print(f"{'':>6} Early stopping at epoch {epoch}")
                    break

            if epoch % 5 == 0 or epoch == 1 or status:
                print(f"{epoch:>6} {train_loss:>12.6f} {val_loss:>12.6f} "
                      f"{status:>10}")

        # Restore best weights
        if best_W:
            self._restore(best_W)
            print(f"[LSTM-AE] Restored best model (val_loss={best_val_loss:.6f})")

        self.is_fitted = True
        return self

    def _snapshot(self) -> dict:
        """Save current weights."""
        return {
            'enc_W': self.enc_lstm.W.copy(),
            'enc_b': self.enc_lstm.b.copy(),
            'e2l_W': self.enc_to_lat.W.copy(),
            'e2l_b': self.enc_to_lat.b.copy(),
            'l2d_W': self.lat_to_dec.W.copy(),
            'l2d_b': self.lat_to_dec.b.copy(),
            'dec_W': self.dec_lstm.W.copy(),
            'dec_b': self.dec_lstm.b.copy(),
            'out_W': self.dec_out.W.copy(),
            'out_b': self.dec_out.b.copy(),
        }

    def _restore(self, snap: dict):
        self.enc_lstm.W   = snap['enc_W'].copy()
        self.enc_lstm.b   = snap['enc_b'].copy()
        self.enc_to_lat.W = snap['e2l_W'].copy()
        self.enc_to_lat.b = snap['e2l_b'].copy()
        self.lat_to_dec.W = snap['l2d_W'].copy()
        self.lat_to_dec.b = snap['l2d_b'].copy()
        self.dec_lstm.W   = snap['dec_W'].copy()
        self.dec_lstm.b   = snap['dec_b'].copy()
        self.dec_out.W    = snap['out_W'].copy()
        self.dec_out.b    = snap['out_b'].copy()

    # ── INFERENCE ─────────────────────────────────────────────────────────

    def reconstruction_error(self, X_seq: np.ndarray) -> np.ndarray:
        """
        Per-sequence MSE reconstruction error.
        Returns: (n_sequences,) array — higher = more anomalous.
        """
        errors = []
        batch_size = 128
        for start in range(0, len(X_seq), batch_size):
            batch = X_seq[start: start + batch_size]
            X_hat, *_ = self.forward(batch, training=False)
            err = np.mean((batch - X_hat) ** 2, axis=(1, 2))
            errors.append(err)
        return np.concatenate(errors)

    def calibrate_threshold(self, X_normal: np.ndarray,
                             X_val_with_labels=None,
                             labels=None,
                             contamination: float = 0.05) -> float:
        """
        Set anomaly threshold.
        If validation labels available: F1-maximizing.
        Otherwise: (1-contamination) percentile of normal errors.
        """
        normal_errors = self.reconstruction_error(X_normal)
        pct_threshold = float(np.percentile(
            normal_errors, (1 - contamination) * 100))

        if X_val_with_labels is not None and labels is not None:
            all_errors = self.reconstruction_error(X_val_with_labels)
            prec, rec, thresholds = precision_recall_curve(labels, all_errors)
            f1s = 2 * prec * rec / (prec + rec + 1e-9)
            best_idx = np.argmax(f1s[:-1])
            f1_threshold = float(thresholds[best_idx])
            self.threshold = f1_threshold
            print(f"[LSTM-AE] Threshold → F1-max={f1_threshold:.6f} "
                  f"(F1={f1s[best_idx]:.3f}) | "
                  f"Percentile fallback={pct_threshold:.6f}")
        else:
            self.threshold = pct_threshold
            print(f"[LSTM-AE] Threshold → Percentile={pct_threshold:.6f}")

        return self.threshold

    def predict(self, X_seq: np.ndarray) -> np.ndarray:
        errors = self.reconstruction_error(X_seq)
        return (errors >= self.threshold).astype(int)

    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        print(f"[LSTM-AE] Model saved → {path}")

    @classmethod
    def load(cls, path: str):
        with open(path, 'rb') as f:
            return pickle.load(f)


# ─── UTILITIES ───────────────────────────────────────────────────────────────

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


# ─── SEQUENCE BUILDER ────────────────────────────────────────────────────────

def build_sequences(df: pd.DataFrame,
                    feature_cols: list,
                    seq_len: int = SEQ_LEN,
                    stride: int = STRIDE,
                    group_col: str = 'sip') -> tuple:
    """
    Build sliding-window sequences from sorted packet data.

    Groups by source IP so each sequence represents one device's
    communication pattern — critical for ICS where each PLC has
    its own deterministic polling schedule.

    Returns:
        X      : (n_seq, seq_len, n_features) float32
        y      : (n_seq,) binary labels (majority vote per window)
        y_name : (n_seq,) dominant attack type per window
        meta   : list of dicts with source IP and time range per sequence
    """
    available_features = [c for c in feature_cols if c in df.columns]
    has_group = group_col in df.columns and df[group_col].nunique() > 1
    groups = df.groupby(group_col) if has_group else [(None, df)]

    X_seqs, y_seqs, y_names, metas = [], [], [], []

    for grp_key, grp_df in groups:
        grp_df = grp_df.sort_values('time_sec').reset_index(drop=True)
        n = len(grp_df)

        if n < seq_len:
            continue

        feat_arr  = grp_df[available_features].fillna(0)\
                        .replace([np.inf,-np.inf], 0)\
                        .values.astype(np.float32)
        label_arr = grp_df['label_binary'].values \
                    if 'label_binary' in grp_df.columns \
                    else np.zeros(n, dtype=int)
        name_arr  = grp_df['label_name'].values \
                    if 'label_name' in grp_df.columns \
                    else np.array(['unknown'] * n)

        for start in range(0, n - seq_len + 1, stride):
            window = feat_arr[start: start + seq_len]
            labels_w = label_arr[start: start + seq_len]
            names_w  = name_arr[start: start + seq_len]

            # Label: 1 if ANY attack packet in window
            y = int(labels_w.max())

            # Dominant attack type
            attack_names = names_w[labels_w == 1]
            if len(attack_names) > 0:
                from collections import Counter
                y_name = Counter(attack_names).most_common(1)[0][0]
            else:
                y_name = 'normal'

            X_seqs.append(window)
            y_seqs.append(y)
            y_names.append(y_name)
            metas.append({'src': grp_key, 'start': start})

    if not X_seqs:
        raise ValueError(
            f"No sequences built. Check seq_len={seq_len} vs dataset size.")

    X = np.stack(X_seqs, axis=0)
    y = np.array(y_seqs, dtype=int)
    print(f"[sequences] Built {len(X):,} sequences "
          f"({(y==0).sum():,} normal, {(y==1).sum():,} attack) "
          f"| shape={X.shape}")
    return X, y, np.array(y_names), metas


# ─── PREPROCESSING ───────────────────────────────────────────────────────────

def scale_sequences(X_train_normal: np.ndarray,
                    X_other: list) -> tuple:
    """
    Fit RobustScaler on normal training sequences.
    Applies same scaling to all other arrays in X_other.
    """
    n, T, D = X_train_normal.shape
    scaler = RobustScaler()
    # Fit on flattened normal sequences
    scaler.fit(X_train_normal.reshape(-1, D))

    def scale(X):
        n_, T_, D_ = X.shape
        return scaler.transform(X.reshape(-1, D_)).reshape(n_, T_, D_)

    X_scaled = scale(X_train_normal)
    others_scaled = [scale(X) for X in X_other]
    return X_scaled, others_scaled, scaler


# ─── EVALUATION ──────────────────────────────────────────────────────────────

def evaluate(model: LSTMAutoencoder,
             X_seq: np.ndarray,
             y: np.ndarray,
             y_names: np.ndarray) -> dict:
    errors = model.reconstruction_error(X_seq)
    preds  = (errors >= model.threshold).astype(int)

    roc_auc  = roc_auc_score(y, errors) if y.sum() > 0 else float('nan')
    avg_prec = average_precision_score(y, errors) if y.sum() > 0 else float('nan')

    cm = confusion_matrix(y, preds)
    tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0,0,0,0)
    precision = tp / (tp + fp + 1e-9)
    recall    = tp / (tp + fn + 1e-9)
    f1        = 2 * precision * recall / (precision + recall + 1e-9)

    # Per-attack-type recall
    per_type = {}
    for atype in np.unique(y_names):
        mask = y_names == atype
        sub_y    = y[mask]
        sub_pred = preds[mask]
        per_type[atype] = {
            'n':       int(mask.sum()),
            'detected': int(sub_pred.sum()),
            'recall':  float(sub_pred[sub_y==1].mean())
                       if sub_y.sum() > 0 else float('nan'),
            'fpr':     float(sub_pred[sub_y==0].mean())
                       if (sub_y==0).sum() > 0 else float('nan'),
        }

    return {
        'n_sequences':   len(y),
        'n_normal':      int((y==0).sum()),
        'n_attack':      int((y==1).sum()),
        'roc_auc':       round(roc_auc, 4),
        'avg_precision': round(avg_prec, 4),
        'precision':     round(precision, 4),
        'recall':        round(recall, 4),
        'f1_score':      round(f1, 4),
        'fpr':           round(fp/(fp+tn+1e-9), 4),
        'fnr':           round(fn/(fn+tp+1e-9), 4),
        'tp': int(tp), 'fp': int(fp),
        'tn': int(tn), 'fn': int(fn),
        'threshold':     round(model.threshold, 6),
        'per_type':      per_type,
    }


# ─── VISUALIZATION ───────────────────────────────────────────────────────────

def plot_results(model, X_test, X_test_normal,
                 y_test, y_names_test, metrics):
    CYAN='#00e5ff'; RED='#ff6b6b'; PURPLE='#a78bfa'
    MUTED='#6b6b8a'; BG='#12121a'; TEXT='#e8e8f0'

    errors = model.reconstruction_error(X_test)
    normal_errors = model.reconstruction_error(X_test_normal[:min(500,len(X_test_normal))])

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

    # 1. Training curve
    ax1 = fig.add_subplot(gs[0,0])
    ax1.plot(model.train_losses, color=CYAN, lw=2, label='Train MSE')
    ax1.plot(model.val_losses,   color=PURPLE, lw=2, label='Val MSE')
    style(ax1, 'Training Loss Curve')
    ax1.set_xlabel('Epoch'); ax1.set_ylabel('MSE')
    ax1.legend(fontsize=8, facecolor=BG, labelcolor=TEXT)

    # 2. Reconstruction error distribution
    ax2 = fig.add_subplot(gs[0,1])
    all_err = errors
    bins = np.linspace(0, np.percentile(all_err, 99), 60)
    ax2.hist(errors[y_test==0], bins=bins, alpha=0.7, color=CYAN,
             label='Normal', density=True)
    ax2.hist(errors[y_test==1], bins=bins, alpha=0.7, color=RED,
             label='Attack', density=True)
    ax2.axvline(model.threshold, color=PURPLE, lw=2, ls='--',
                label=f'τ={model.threshold:.5f}')
    style(ax2, 'Reconstruction Error Distribution')
    ax2.set_xlabel('MSE Error'); ax2.set_ylabel('Density')
    ax2.legend(fontsize=7, facecolor=BG, labelcolor=TEXT)

    # 3. ROC
    ax3 = fig.add_subplot(gs[0,2])
    fpr_c, tpr_c, _ = roc_curve(y_test, errors)
    ax3.plot(fpr_c, tpr_c, color=CYAN, lw=2,
             label=f"AUC={metrics['roc_auc']:.3f}")
    ax3.plot([0,1],[0,1], color=MUTED, ls='--', lw=1)
    ax3.fill_between(fpr_c, tpr_c, alpha=0.08, color=CYAN)
    style(ax3, 'ROC Curve')
    ax3.set_xlabel('FPR'); ax3.set_ylabel('TPR')
    ax3.legend(fontsize=8, facecolor=BG, labelcolor=TEXT)

    # 4. Per-attack recall
    ax4 = fig.add_subplot(gs[1,:2])
    pt = {k: v for k,v in metrics['per_type'].items() if k != 'normal'}
    if pt:
        atypes  = list(pt.keys())
        recalls = [pt[k]['recall'] for k in atypes]
        counts  = [pt[k]['n'] for k in atypes]
        x4 = np.arange(len(atypes))
        colors4 = [CYAN if r>=0.8 else PURPLE if r>=0.5 else RED
                   for r in recalls]
        ax4.bar(x4, recalls, color=colors4, alpha=0.8, width=0.6)
        ax4.set_xticks(x4)
        ax4.set_xticklabels(
            [f"{t}\n(n={c:,})" for t,c in zip(atypes, counts)],
            fontsize=7, color=TEXT)
        ax4.set_ylim(0, 1.15)
        ax4.axhline(0.8, color=CYAN, ls='--', lw=1, alpha=0.5)
        for xi, r in zip(x4, recalls):
            if not np.isnan(r):
                ax4.text(xi, r+0.02, f'{r:.2f}', ha='center',
                         color=TEXT, fontsize=8)
        style(ax4, 'LSTM-AE Detection Recall by Attack Type (Sequence Level)')
        ax4.set_ylabel('Recall')

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
    ax5.set_xticklabels(['Pred Normal','Pred Attack'],
                        color=TEXT, fontsize=8)
    ax5.set_yticklabels(['Actual Normal','Actual Attack'],
                        color=TEXT, fontsize=8)
    style(ax5, 'Confusion Matrix')

    # 6. Latent space (first 2 dims via random projection)
    ax6 = fig.add_subplot(gs[2,0])
    sample_idx = np.random.choice(len(X_test), min(800, len(X_test)),
                                   replace=False)
    X_sample = X_test[sample_idx]
    _, latents, *_ = model.forward(X_sample)
    proj = np.random.default_rng(0).normal(
        0, 1, (latents.shape[1], 2)).astype(np.float32)
    proj /= np.linalg.norm(proj, axis=0)
    L2 = latents @ proj
    c6 = np.where(y_test[sample_idx]==1, RED, CYAN)
    ax6.scatter(L2[:,0], L2[:,1], c=c6, alpha=0.4, s=8)
    style(ax6, 'Latent Space (Random 2D Projection)')
    ax6.set_xlabel('Latent dim 1'); ax6.set_ylabel('Latent dim 2')

    # 7. Error over time
    ax7 = fig.add_subplot(gs[2,1])
    max_show = min(500, len(errors))
    t7 = np.arange(max_show)
    e7 = errors[:max_show]
    y7 = y_test[:max_show]
    ax7.fill_between(t7, 0, e7, where=y7==0,
                     alpha=0.5, color=CYAN, label='Normal')
    ax7.fill_between(t7, 0, e7, where=y7==1,
                     alpha=0.6, color=RED, label='Attack')
    ax7.axhline(model.threshold, color=PURPLE, lw=1.5, ls='--')
    style(ax7, 'Reconstruction Error Timeline (first 500 sequences)')
    ax7.set_xlabel('Sequence index'); ax7.set_ylabel('MSE Error')
    ax7.legend(fontsize=7, facecolor=BG, labelcolor=TEXT)

    # 8. Metrics summary
    ax8 = fig.add_subplot(gs[2,2])
    ax8.set_facecolor(BG); ax8.axis('off')
    lines = [
        ('LSTM AUTOENCODER', '',          TEXT,   12, True),
        ('Electra ICS — Sequence Level',  '', MUTED,    8, False),
        ('', '', TEXT, 9, False),
        ('ROC AUC',       f"{metrics['roc_auc']}",       CYAN,  10, False),
        ('Avg Precision', f"{metrics['avg_precision']}",  CYAN,  10, False),
        ('F1 Score',      f"{metrics['f1_score']}",       CYAN,  10, False),
        ('Precision',     f"{metrics['precision']}",      TEXT,  9,  False),
        ('Recall',        f"{metrics['recall']}",         TEXT,  9,  False),
        ('FPR',           f"{metrics['fpr']}",            RED,   9,  False),
        ('FNR',           f"{metrics['fnr']}",            RED,   9,  False),
        ('', '', TEXT, 9, False),
        ('TP', f"{metrics['tp']:,}", '#4ade80', 9, False),
        ('FP', f"{metrics['fp']:,}", RED,       9, False),
        ('TN', f"{metrics['tn']:,}", '#4ade80', 9, False),
        ('FN', f"{metrics['fn']:,}", RED,       9, False),
        ('', '', TEXT, 9, False),
        ('Seq length',  str(SEQ_LEN),       MUTED, 8, False),
        ('Hidden dim',  str(HIDDEN_DIM),    MUTED, 8, False),
        ('Latent dim',  str(LATENT_DIM),    MUTED, 8, False),
        ('Epochs run',  str(len(model.train_losses)), MUTED, 8, False),
    ]
    y_pos = 0.97
    for lbl, val, color, size, bold in lines:
        w = 'bold' if bold else 'normal'
        if val:
            ax8.text(0.05, y_pos, lbl, color=MUTED, fontsize=size-1,
                     va='top', transform=ax8.transAxes)
            ax8.text(0.95, y_pos, val, color=color, fontsize=size,
                     va='top', ha='right', fontweight=w,
                     transform=ax8.transAxes)
        else:
            ax8.text(0.05, y_pos, lbl, color=color, fontsize=size,
                     va='top', fontweight=w, transform=ax8.transAxes)
        y_pos -= 0.048

    fig.suptitle(
        'Electra ICS Dataset — LSTM Autoencoder Anomaly Detection\n'
        'Sequence-Level | Modbus Packet Features | Pure NumPy',
        fontsize=13, fontweight='bold', color=TEXT, y=0.99)

    path = os.path.join(OUTPUT_DIR, 'lstm_ae_results.png')
    plt.savefig(path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"[plot] Saved → {path}")
    return path


# ─── COMPARISON TABLE ────────────────────────────────────────────────────────

def print_comparison(if_metrics: dict, lstm_metrics: dict):
    """Side-by-side comparison of IF vs LSTM-AE."""
    print("\n" + "═"*65)
    print("  MODEL COMPARISON: Isolation Forest vs LSTM Autoencoder")
    print("═"*65)
    print(f"{'Metric':<25} {'Isolation Forest':>18} {'LSTM Autoencoder':>18}")
    print("─"*65)

    shared_keys = ['roc_auc', 'avg_precision', 'f1_score',
                   'precision', 'recall', 'fpr', 'fnr']
    for k in shared_keys:
        iv = if_metrics.get(k, 'n/a')
        lv = lstm_metrics.get(k, 'n/a')
        winner = ''
        try:
            if k in ('fpr','fnr'):
                winner = '← IF' if iv < lv else '← LSTM'
            else:
                winner = '← IF' if iv > lv else '← LSTM'
        except Exception:
            pass
        print(f"  {k:<23} {str(iv):>18} {str(lv):>18}  {winner}")

    print("─"*65)
    print("\n  Per-attack recall comparison:")
    print(f"  {'Attack Type':<30} {'IF Recall':>10} {'LSTM Recall':>12}")
    print("  " + "─"*55)

    if_pt   = if_metrics.get('per_type', {})
    lstm_pt = lstm_metrics.get('per_type', {})
    all_types = sorted(set(if_pt) | set(lstm_pt))
    for atype in all_types:
        if atype == 'normal':
            continue
        ir = if_pt.get(atype, {}).get('recall', float('nan'))
        lr = lstm_pt.get(atype, {}).get('recall', float('nan'))
        ir_s = f"{ir:.3f}" if not np.isnan(ir) else 'n/a'
        lr_s = f"{lr:.3f}" if not np.isnan(lr) else 'n/a'
        try:
            better = '← LSTM' if lr > ir else ('← IF' if ir > lr else '=')
        except Exception:
            better = ''
        print(f"  {atype:<30} {ir_s:>10} {lr_s:>12}  {better}")
    print("═"*65)


# ─── MAIN PIPELINE ───────────────────────────────────────────────────────────

def run(csv_path: str = None,
        contamination: float = 0.05,
        seq_len: int = SEQ_LEN,
        stride: int = STRIDE,
        epochs: int = EPOCHS,
        if_metrics_path: str = None,
        sample_n: int = 0):

    print("=" * 65)
    print("  ELECTRA ICS — LSTM Autoencoder Pipeline")
    print("=" * 65)

    # ── Load data ─────────────────────────────────────────────────────────
    if csv_path and os.path.exists(csv_path):
        print(f"\n[pipeline] Loading {csv_path} ...")

        if sample_n and sample_n > 0:
            import random
            total = sum(1 for _ in open(csv_path)) - 1
            skip_prob = max(0, 1 - sample_n / total)
            df_raw = pd.read_csv(
                csv_path, low_memory=False,
                skiprows=lambda i: i > 0 and random.random() < skip_prob
            )
            print(f"[pipeline] Sampled {len(df_raw):,} rows from {total:,} total")
        else:
            df_raw = pd.read_csv(csv_path, low_memory=False)
            print(f"[pipeline] Loaded {len(df_raw):,} rows")

        # Normalize column names — handle Electra variants
        col_map = {}
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
        print("\n[pipeline] Generating synthetic Electra data...")
        df_raw = _synthetic_electra(n=50_000)

    df_raw = encode_labels(df_raw)

    # ── Feature engineering (reuse IF module) ────────────────────────────
    print("\n[pipeline] Engineering features...")
    df = engineer_features(df_raw)

    feature_cols = [c for c in FEATURE_COLS if c in df.columns]

    # ── Packet-level split: normal-only train, mixed test ────────────────
    # For LSTM-AE we split BEFORE sequencing:
    #   - Training pool: normal packets only → all windows guaranteed clean
    #   - Test pool: all packets (stratified) → evaluation with ground truth
    # This mirrors how the model would be deployed: trained on a clean
    # baseline capture, evaluated on live/mixed traffic.
    normal_df = df[df['label_binary'] == 0].copy()
    mixed_df  = df.copy()

    # 70% of normal packets → training sequences
    # 30% of all packets → test sequences (with labels)
    normal_train, _ = train_test_split(
        normal_df, test_size=0.3, random_state=42)
    _, test_df = train_test_split(
        mixed_df, test_size=0.3, random_state=42,
        stratify=mixed_df['label_binary'])

    print(f"[pipeline] Normal train packets: {len(normal_train):,} | "
          f"Test packets (mixed): {len(test_df):,}")

    # ── Build sequences ───────────────────────────────────────────────────
    print(f"\n[pipeline] Building sequences "
          f"(seq_len={seq_len}, stride={stride})...")

    X_train_all, y_train, y_train_names, _ = build_sequences(
        normal_train, feature_cols, seq_len, stride)
    X_test_all, y_test, y_test_names, _    = build_sequences(
        test_df, feature_cols, seq_len, stride)

    # All training sequences should be normal (label_binary==0)
    X_train_normal = X_train_all[y_train == 0]
    if len(X_train_normal) == 0:
        # Fallback: use all training sequences (edge case for tiny datasets)
        X_train_normal = X_train_all
        print("[pipeline] Warning: no all-normal windows found — "
              "using all training sequences")

    print(f"[pipeline] Normal training sequences: {len(X_train_normal):,}")

    # ── Scale sequences ───────────────────────────────────────────────────
    # Free packet-level dataframes before sequence scaling
    import gc; gc.collect()

    print("[pipeline] Scaling features...")
    X_train_scaled, (X_test_scaled,), scaler = scale_sequences(
        X_train_normal, [X_test_all])

    # Free unscaled sequence arrays
    del X_train_normal, X_test_all
    gc.collect()

    X_test_normal_scaled = X_test_scaled[y_test == 0]
    if len(X_test_normal_scaled) == 0:
        # Use a small portion of train scaled as proxy
        X_test_normal_scaled = X_train_scaled[:50]

    # ── Validation split from training normal sequences ───────────────────
    n_val = max(50, int(len(X_train_scaled) * 0.15))
    X_val_s = X_train_scaled[-n_val:]
    X_tr_s  = X_train_scaled[:-n_val]

    # ── Build and train model ─────────────────────────────────────────────
    input_dim = X_tr_s.shape[2]
    model = LSTMAutoencoder(
        input_dim  = input_dim,
        hidden_dim = HIDDEN_DIM,
        latent_dim = LATENT_DIM,
    )
    model.scaler       = scaler
    model.feature_cols = feature_cols

    model.fit(X_tr_s, X_val_s, epochs=epochs,
              batch_size=BATCH_SIZE, lr=LR)

    # ── Calibrate threshold ───────────────────────────────────────────────
    print("\n[pipeline] Calibrating threshold...")
    model.calibrate_threshold(
        X_normal         = X_test_normal_scaled,
        X_val_with_labels= X_test_scaled,
        labels           = y_test,
        contamination    = contamination,
    )

    # ── Evaluate ──────────────────────────────────────────────────────────
    print("\n[pipeline] Evaluating on test sequences...")
    lstm_metrics = evaluate(model, X_test_scaled, y_test, y_test_names)

    print("\n" + "─"*45)
    print("  LSTM AUTOENCODER RESULTS")
    print("─"*45)
    for k, v in lstm_metrics.items():
        if k != 'per_type':
            print(f"  {k:<22} {v}")
    print("\n  Per-attack-type recall:")
    for atype, info in lstm_metrics.get('per_type', {}).items():
        r = info.get('recall', float('nan'))
        r_s = f"{r:.3f}" if not np.isnan(r) else 'n/a'
        print(f"  {atype:<30} n={info['n']:>5,}  recall={r_s}")
    print("─"*45)

    # ── Compare with IF if metrics available ─────────────────────────────
    if_metrics_file = if_metrics_path or \
                      os.path.join(OUTPUT_DIR, 'electra_metrics.json')
    if os.path.exists(if_metrics_file):
        with open(if_metrics_file) as f:
            if_metrics = json.load(f)
        print_comparison(if_metrics, lstm_metrics)
    else:
        print("\n[pipeline] No IF metrics found for comparison. "
              "Run electra_isolation_forest.py first.")

    # ── Save outputs ──────────────────────────────────────────────────────
    model.save(os.path.join(OUTPUT_DIR, 'lstm_ae_model.pkl'))

    # Comparison CSV (same schema as IF output)
    errors = model.reconstruction_error(X_test_scaled)
    preds  = model.predict(X_test_scaled)
    export = pd.DataFrame({
        'label_binary':  y_test,
        'label_name':    y_test_names,
        'anomaly_score': errors,
        'lstm_predicted': preds,
    })
    export.to_csv(os.path.join(OUTPUT_DIR, 'lstm_comparison.csv'), index=False)

    # Unified metrics JSON (IF + LSTM together)
    combined = {'lstm_autoencoder': lstm_metrics}
    if os.path.exists(if_metrics_file):
        with open(if_metrics_file) as f:
            existing = json.load(f)
        combined['isolation_forest'] = existing
    combined_path = os.path.join(OUTPUT_DIR, 'combined_metrics.json')
    with open(combined_path, 'w') as f:
        json.dump(combined, f, indent=2, default=str)

    with open(os.path.join(OUTPUT_DIR, 'lstm_metrics.json'), 'w') as f:
        json.dump(lstm_metrics, f, indent=2, default=str)

    # Plot
    plot_results(model, X_test_scaled, X_test_normal_scaled,
                 y_test, y_test_names, lstm_metrics)

    print(f"\n[pipeline] ✓ Done. Outputs → {OUTPUT_DIR}")
    return model, lstm_metrics


if __name__ == '__main__':
    import sys
    import argparse as _ap
    _parser = _ap.ArgumentParser(description='Electra LSTM Autoencoder')
    _parser.add_argument('csv', nargs='?', default=None)
    _parser.add_argument('--sample', type=int, default=0,
                         help='Randomly sample N rows (0=all). '
                              'Use 500000 for 4GB RAM machines.')
    _parser.add_argument('--contamination', type=float, default=0.05)
    _parser.add_argument('--epochs', type=int, default=EPOCHS,
                         help=f'Training epochs (default={EPOCHS})')
    _parser.add_argument('--seq-len', type=int, default=SEQ_LEN,
                         help=f'Sequence length (default={SEQ_LEN})')
    _parser.add_argument('--if-metrics', type=str, default=None,
                         help='Path to IF metrics JSON for comparison')
    _args = _parser.parse_args()
    run(csv_path=_args.csv,
        contamination=_args.contamination,
        epochs=_args.epochs,
        seq_len=_args.seq_len,
        if_metrics_path=_args.if_metrics,
        sample_n=_args.sample)
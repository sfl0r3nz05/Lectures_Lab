# ICS Anomaly Detection Pipeline 

1. Overview 

This pipeline implements and compares two anomaly detection approaches on the Electra ICS Modbus dataset, a real-world industrial control system capture from an electric traction substation containing normal Modbus traffic and seven distinct attack categories. 

2. Dataset: Electra Modbus

- URL: [google-drive-link]
- 16,289,277 packets total  |  11 features per packet 
- Normal: 85.3%  |  Attack: 14.7%  |  Imbalance ratio 1:5.8 
- Attack categories: mitm_unaltered, read_attack, recognition_attack, write_attack, response_attack, force_error_attack, replay_attack 
- Schema: time, smac, dmac, sip, dip, request, fc, error, address, data, label

3. Installation: Python Dependencies 

- Install all required packages in a single command:
    
    - Option A — system-wide 

    ```python
    pip install numpy scikit-learn pandas matplotlib
    ```
    
    - Option B: virtual environment (recommended) 

    ```python
    python3 -m venv ~/ml_env 
    source ~/ml_env/bin/activate 
    pip install numpy scikit-learn pandas matplotlib
    ```

4. Usage

    - Isolation Forest

        - Development run — 4 GB RAM 

        ```python
        python3 electra_isolation_forest.py electra_modbus.csv --sample 1000000 
        ```

        - Full dataset — 8 GB+ RAM 
    
        ```python
        python3 electra_isolation_forest.py electra_modbus.csv 
        ```
 
        - Tighter threshold (reduce false positives) 

        ```python
        python3 electra_isolation_forest.py electra_modbus.csv \
        --sample 1000000 --contamination 0.03
        ```

    - LSTM Autoencoder
        
        - Run LSTM — auto-loads IF metrics for comparison if available 

        ```python
        python3 lstm_autoencoder.py electra_modbus.csv --sample 1000000 
        ```
 
        - With explicit comparison to IF results 

        ```python
        python3 lstm_autoencoder.py electra_modbus.csv \ 
        --sample 1000000 \ 
        --if-metrics ml_results/electra_metrics.json
        ```

        - Faster training (fewer epochs) 

        ```python
        python3 lstm_autoencoder.py electra_modbus.csv \ 
        --sample 1000000 --epochs 20 
        ```
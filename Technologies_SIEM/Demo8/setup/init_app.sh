#!/bin/bash
echo "[*] Iniciando configuración de servicios..."

# Función mejorada usando Python para no depender de 'nc'
wait_for() {
    echo "[*] Esperando a que $1 esté disponible en $2:$3..."
    # Este comando de Python intenta conectar al puerto. Si falla, espera 2 segundos.
    until python3 -c "import socket; s = socket.socket(); s.connect(('$2', $3))" 2>/dev/null; do
        sleep 2
    done
    echo "[+] $1 está listo."
}

# Esperamos a los servicios
wait_for "Elasticsearch" "elasticsearch" 9200
wait_for "MinIO" "minio" 9000
wait_for "Kibana" "kibana" 5601

echo "[*] Ejecutando configuraciones iniciales..."
python3 /opt/irisapp/configurar_minio.py
python3 /opt/irisapp/setup_kibana.py

echo "[*] Iniciando Evidence Manager..."
python3 /opt/irisapp/evidence_manager.py
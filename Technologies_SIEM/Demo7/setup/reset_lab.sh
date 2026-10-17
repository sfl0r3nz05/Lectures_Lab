#!/bin/bash
echo "[*] Limpiando laboratorio para la defensa..."

# 1. Tirar los contenedores y destruir volúmenes huérfanos
docker-compose -f ../infraestructura/docker-compose.yml down -v

# 2. Borrar bases de datos y archivos guardados de MinIO (Estado)
sudo rm -rf ../infraestructura/data/*

# 3. Limpiar los logs antiguos de Suricata (pero dejar las reglas intactas)
sudo rm -f ../infraestructura/suricata/logs/eve.json
touch ../infraestructura/suricata/logs/eve.json

# 4. Limpiar caché de Docker
docker system prune -f

echo "[+] Entorno reseteado. Listo para un despliegue desde cero."
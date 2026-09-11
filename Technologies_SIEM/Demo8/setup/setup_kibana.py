import requests
import time

KIBANA_URL = "http://localhost:5601"
DATA_VIEW_NAME = "filebeat-*"

def create_dataview():
    print("[*] Configurando Data View en Kibana...")
    
    # Payload para la API de Kibana 8.x
    payload = {
        "data_view": {
            "title": DATA_VIEW_NAME,
            "name": "Filebeat Data",
            "timeFieldName": "@timestamp"
        }
    }
    
    headers = {
        "kbn-xsrf": "true",
        "Content-Type": "application/json"
    }

    try:
        # Intentamos crear el Data View
        response = requests.post(
            f"{KIBANA_URL}/api/data_views/data_view", 
            json=payload, 
            headers=headers
        )
        
        if response.status_code == 200:
            print("[+] Data View creado correctamente.")
        elif response.status_code == 409:
            print("[!] El Data View ya existe. Continuando...")
        else:
            print(f"[-] Error al crear Data View: {response.text}")
            
    except Exception as e:
        print(f"[-] No se pudo conectar con Kibana: {e}")

if __name__ == "__main__":
    # Esperamos unos segundos a que Kibana esté realmente listo
    time.sleep(20) 
    create_dataview()
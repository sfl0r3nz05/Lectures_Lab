#!/usr/bin/env python3
"""
Wazuh + Suricata Data View Setup Script
Creates proper index patterns for Suricata alerts and MITRE detection
Based on working curl command: https://localhost:443/api/saved_objects/index-pattern/
"""

import requests
import time
import json
import sys
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Configuration
WAZUH_URL = "https://192.168.75.129:443"
WAZUH_USER = "admin"
WAZUH_PASS = "admin"
VERIFY_SSL = False

# Headers (CRITICAL: use osd-xsrf not kbn-xsrf for OpenSearch)
HEADERS = {
    "osd-xsrf": "true",
    "Content-Type": "application/json"
}

# Data views to create
DATA_VIEWS = [
    {
        "id": "suricata",
        "title": "suricata-*",
        "timeFieldName": "@timestamp",
        "description": "Suricata IDS Alerts - Network threats detected"
    },
    {
        "id": "wazuh-alerts",
        "title": "wazuh-alerts-*",
        "timeFieldName": "timestamp",
        "description": "Wazuh managed alerts with MITRE mapping"
    },
    {
        "id": "modbus",
        "title": "suricata-*",
        "timeFieldName": "@timestamp",
        "description": "Modbus-specific attacks (FC 1, 3, 5, 6) - ICS/OT threats"
    }
]

def test_connectivity():
    """Test if Wazuh is reachable"""
    print("[*] Testing connectivity to Wazuh...")
    try:
        response = requests.get(
            f"{WAZUH_URL}/",
            auth=HTTPBasicAuth(WAZUH_USER, WAZUH_PASS),
            verify=VERIFY_SSL,
            timeout=10
        )
        
        if response.status_code in [200, 302]:
            print("[+] Wazuh is reachable!")
            return True
        else:
            print(f"[-] Wazuh returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        return False

def create_data_view(view_id, title, time_field, description):
    """Create a single data view/index pattern"""
    print(f"\n[*] Creating data view: {view_id} ({title})")
    
    payload = {
        "attributes": {
            "title": title,
            "timeFieldName": time_field
        }
    }
    
    try:
        response = requests.post(
            f"{WAZUH_URL}/api/saved_objects/index-pattern/{view_id}",
            json=payload,
            headers=HEADERS,
            auth=HTTPBasicAuth(WAZUH_USER, WAZUH_PASS),
            verify=VERIFY_SSL,
            timeout=10
        )
        
        print(f"    Response: {response.status_code}")
        
        if response.status_code == 200:
            print(f"[+] Data view '{view_id}' created successfully!")
            print(f"    → {description}")
            try:
                result = response.json()
                print(f"    → ID: {result.get('id')}")
            except:
                pass
            return True
            
        elif response.status_code == 409:
            print(f"[!] Data view '{view_id}' already exists")
            return True
            
        else:
            print(f"[-] Error creating data view: {response.status_code}")
            try:
                error_data = response.json()
                print(f"    → {json.dumps(error_data, indent=2)}")
            except:
                print(f"    → {response.text}")
            return False
            
    except Exception as e:
        print(f"[-] Exception: {e}")
        return False

def list_data_views():
    """List all existing data views"""
    print("\n[*] Fetching existing data views...")
    
    try:
        response = requests.get(
            f"{WAZUH_URL}/api/saved_objects/index-pattern",
            headers=HEADERS,
            auth=HTTPBasicAuth(WAZUH_USER, WAZUH_PASS),
            verify=VERIFY_SSL,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            saved_objects = data.get('saved_objects', [])
            
            if saved_objects:
                print(f"[+] Found {len(saved_objects)} existing data views:")
                for obj in saved_objects:
                    title = obj.get('attributes', {}).get('title', 'Unknown')
                    print(f"    → {obj.get('id')}: {title}")
            else:
                print("[!] No existing data views found")
            return True
        else:
            print(f"[-] Error fetching data views: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[-] Exception: {e}")
        return False

def create_all_data_views():
    """Create all configured data views"""
    print("=" * 70)
    print("Creating Wazuh Data Views for Suricata + Modbus Detection Lab")
    print("=" * 70)
    
    # Test connectivity first
    if not test_connectivity():
        print("\n[-] Cannot reach Wazuh. Exiting.")
        sys.exit(1)
    
    time.sleep(1)
    
    # List existing views
    list_data_views()
    
    # Create new views
    print("\n" + "=" * 70)
    print("Creating New Data Views")
    print("=" * 70)
    
    success_count = 0
    for view in DATA_VIEWS:
        if create_data_view(
            view["id"],
            view["title"],
            view["timeFieldName"],
            view["description"]
        ):
            success_count += 1
        time.sleep(0.5)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"[+] Successfully configured {success_count}/{len(DATA_VIEWS)} data views")
    
    print("\n[+] Next steps:")
    print("    1. Open Wazuh Dashboard: https://192.168.75.129")
    print("    2. Go to: Explore → Discover")
    print("    3. Select data view from dropdown:")
    print("       → suricata: All Suricata IDS alerts")
    print("       → wazuh-alerts: Wazuh managed alerts with MITRE ATT&CK")
    print("       → modbus: Modbus-specific attacks (FC 1,3,5,6)")
    print("\n[+] Your Suricata + Modbus detection lab is ready!")
    print("=" * 70)

if __name__ == "__main__":
    create_all_data_views()
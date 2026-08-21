# DEMO 3: LOG NORMALIZATION WITH GRAYLOG

## Overview
 
This demonstration implements **log normalization and structured data extraction** using:
 
- **GNS3 Network Emulation**: Virtual network topology (from Demo 1)
- **R1 (Cisco C7200 Router)**: Syslog source (operational logs)
- **MongoDB (GNS3 Docker Appliance)**: Graylog configuration backend
- **Elasticsearch (GNS3 Docker Appliance)**: Structured log storage and indexing
- **Graylog (GNS3 Docker Appliance)**: Log aggregation, processing, and normalization engine

### Three Normalization Steps

*Step 1: Define Log Message Format*

 ```
 Raw Cisco Syslog:
 Aug 11 16:25:57 192.168.1.50 24: *Aug 11 16:20:45.871: %SYS-5-CONFIG_I: Configured from console by console
     
     ├─ Timestamp: Aug 11 16:20:45.871
     ├─ Severity: 5 (Notice)
     ├─ Message Code: CONFIG_I
     ├─ Details: "Configured from console by console"
     └─ Source IP: 192.168.1.50
 ```
 
*Step 2: Create Grok Pattern*

 ```
 Grok pattern extracts fields:
  
 %{CISCO_SYSLOG_PATTERN}
  
 Extracts:
   - timestamp
   - device_ip
   - severity_code
   - message_code
   - message_text
   - event_type (normalized)
 ```
 
*Step 3: Create Message Processing Pipeline*

 ```
 Graylog Pipeline Processing:
  
 1. Parse with Grok pattern
 2. Extract and enrich fields
 3. Normalize severity levels
 4. Classify event type
 5. Index structured data in Elasticsearch
 
         ↓
  
 Result: Normalized, Searchable, Visualizable Logs
 ```
 
---
 
## Architecture
 
```
┌──────────────────────────────────────────────────────────────────┐
│       GRAYLOG LOG NORMALIZATION STACK (GNS3 APPLIANCES)          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LOG SOURCE          GNS3 APPLIANCES        STORAGE              │
│  ┌─────────┐        ┌──────────────────┐  ┌──────────────┐       │
│  │ R1      │        │   MongoDB        │  │              │       │
│  │Router   │        │   (Port 27017)   │  │ Elasticsearch│       │
│  │192.1.50 │────┐   └──────────────────┘  │  (Port 9200) │       │
│  │         │    │                         │              │       │
│  │ Syslog  │    ├──→ ┌──────────────────┐ ├──────────────┤       │
│  │ Events  │    │    │     Graylog      │ │ Normalized   │       │
│  └─────────┘    │    │   (Port 1514)    │ │ Indexed Data │       │
│                 │    │                  │ │              │       │
│                 │    │ Processing:      │→├──────────────┤       │
│                 │    │ ├─ Grok Pattern  │ │              │       │
│                 │    │ ├─ Extract       │ │ Searchable   │       │
│                 │    │ ├─ Normalize     │ │ Fields:      │       │
│                 │    │ └─ Enrich        │ │ -src_ip      │       │
│                 │    │                  │ │ -sev_level   │       │
│                 │    └──────────────────┘ │ -event_type  │       │
│                 │                         │ -msg_text    │       │
│                 └────────────────────────→└──────────────┘       │
│                  UDP:1514                                        │
│                                                                  │
│  Unstructured Cisco Syslog ──→ Normalized JSON in Elasticsearch  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```
 
---

## Prerequisites

### GNS3 Setup

1. GNS3 installed and running

2. Drag Virtual Switch to canvas:

    - Drag Switch appliance:

        <img src="img/switch-drag.png" width="500">

3. Drag Cisco C7200 (R1) to canvas:

    - Download dynamips from https://drive.google.com/file/d/1cQ3y24eMJ3SjwLWeAu_hxIsO51Y0CRHX/view?usp=sharing

    - Select preferences:

        <img src="img/preferences.png" width="250">

    - Import dynamips:

        <img src="img/import-dynamips.png" width="500">

    - Drag device:

        <img src="img/drag-router.png" width="450">

4. Drag MongoDB appliance to canvas:

    - Download appliance from this repo: [mongodb-appliance.gns3a](./mongodb-appliance.gns3a)

    - Select MongoDB appliance:

        <img src="img/import-appliance.png" width="200">

    - Open MogoDB Graylog appliance:

        <img src="img/select-mongo-appliance.png" width="500">

    - Install MogoDB Graylog appliance:

        <img src="img/install-mongo-appliance.png" width="500">

    - Installed MogoDB Graylog appliance:

        <img src="img/installed-mongo-appliance.png" width="500">

    - Drag MogoDB Graylog appliance and pulling image:

        <img src="img/pull-mongodb-image-and-drag-appliance.png" width="500">

    - MogoDB Graylog docker image pulling can be reflected:

        <img src="img/graylog-registry.png" width="300">

5. Drag Elasticsearch appliance to canvas:

    - Download appliance from this repo: [elasticsearch-appliance.gns3a](./elasticsearch-appliance.gns3a)

    - Select Elasticsearch appliance:

        <img src="img/import-appliance.png" width="200">

    - Elasticsearch appliance:

        <img src="img/select-elasticsearch-appliance.png" width="500">

    - Install Graylog appliance:

        <img src="img/install-elasticsearch-appliance.png" width="500">

    - Installed Graylog appliance:

        <img src="img/installed-elasticsearch-appliance.png" width="500">

    - Drag Elasticsearch appliance and pulling image:

        <img src="img/pull-elasticsearch-image-and-drag-appliance.png" width="500">

    - Elasticsearch docker image pulling can be reflected:

        <img src="img/elasticsearch-registry.png" width="350">

6. Drag Graylog appliance to canvas:

    - Download appliance from this repo: [graylog-appliance.gns3a](./graylog-appliance.gns3a)

    - Select Graylog appliance:

        <img src="img/import-appliance.png" width="200">

    - Open Graylog appliance:

        <img src="img/select-graylog-appliance.png" width="500">

    - Install Graylog appliance:

        <img src="img/install-graylog-appliance.png" width="500">

    - Installed Graylog appliance:

        <img src="img/installed-graylog-appliance.png" width="500">

    - Drag Graylog appliance and pulling image:

        <img src="img/pull-graylog-image-and-drag-appliance.png" width="500">

    - Graylog docker image pulling can be reflected:

        <img src="img/graylog-registry.png" width="350">

## INTERCONNECT AND RUN INFRASTRUCTURE

1. Interconnect devices and run the project:

    <img src="img/infrastructure.png" width="550">

2. Configure R1

 ```bash
 R1# configure terminal
 R1(config)# interface FastEthernet0/0
 R1(config-if)# ip address 192.168.42.50 255.255.255.0
 R1(config-if)# no shutdown
 R1(config-if)# end

 R1# ping 192.168.42.1
 ```

3. Configure R1 Syslog

 ```bash
 R1# configure terminal
 R1(config)# logging 192.168.42.11
 R1(config)# logging trap informational
 R1(config)# end
 
 R1# show logging
 # Should show: Logging to 192.168.42.11 (udp port 514)
 ```

4. Configure MONGODB Container

 ```bash
 docker exec -it GNS3.MongoDBGraylog.* bash

 root@MongoDBGraylog:/# cat > /etc/network/interfaces << 'EOF'
 auto eth0
 iface eth0 inet static
     address 192.168.42.10
     netmask 255.255.255.0
     gateway 192.168.42.1
     up echo nameserver 192.168.42.1 > /etc/resolv.conf
 EOF

 root@MongoDBGraylog:/# cat > /etc/hosts << 'EOF'
 127.0.0.1       localhost
 192.168.42.10   mongo
 192.168.42.11   graylog
 192.168.42.12   elasticsearch
 EOF
 
 root@MongoDBGraylog:/# exit
 ```

5. Create User in GRAYLOG DATABASE

 ```bash
 docker exec -it GNS3.MongoDBGraylog.* bash

 root@MongoDBGraylog:/# mongo -u admin -p admin --authenticationDatabase admin

 > use graylog
 switched to db graylog

 > db.createUser({
   user: "admin",
   pwd: "admin",
   roles: [{role: "readWrite", db: "graylog"}]
 })

 # Returns: Successfully added user

 > exit

 root@MongoDBGraylog:/# exit
 ```

6. Configure Graylog Container

 ```bash
 docker exec -it GNS3.GraylogSIEM.* bash

 root@GraylogSIEM:/# cat > /etc/network/interfaces << 'EOF'
 auto eth0
 iface eth0 inet static
     address 192.168.42.11
     netmask 255.255.255.0
     gateway 192.168.42.1
     up echo nameserver 192.168.42.1 > /etc/resolv.conf
 EOF
 
 root@GraylogSIEM:/# cat > /etc/hosts << 'EOF'
 127.0.0.1       localhost
 192.168.42.10   mongo
 192.168.42.11   graylog
 192.168.42.12   elasticsearch
 EOF
 
 root@GraylogSIEM:/# exit
 ```

7. Configure ELASTICSEARCH Container

 ```bash
 docker exec -it GNS3.ElasticsearchGraylog.* bash

 root@ElasticsearchGraylog:/# cat > /etc/network/interfaces << 'EOF'
 auto eth0
 iface eth0 inet static
     address 192.168.42.12
     netmask 255.255.255.0
     gateway 192.168.42.1
     up echo nameserver 192.168.42.1 > /etc/resolv.conf
 EOF
 
 root@ElasticsearchGraylog:/# cat > /etc/hosts << 'EOF'
 127.0.0.1       localhost
 192.168.42.10   mongo
 192.168.42.11   graylog
 192.168.42.12   elasticsearch
 EOF
 
 root@ElasticsearchGraylog:/# exit
 ```

## GENERATE SYSLOG

1. Generate Syslog Input on Port 514

 ```bash
 curl -X POST http://192.168.42.11:9000/api/system/inputs \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -H "X-Requested-By: cli" \
  -d '{
    "title": "Router Syslog",
    "type": "org.graylog2.inputs.syslog.udp.SyslogUDPInput",
    "global": true,
    "configuration": {
      "bind_address": "0.0.0.0",
      "port": 514
    }
  }'
 ```

2. Generate test

 ```bash
 # Generate test event on R1
 R1# configure terminal
 R1(config)# interface FastEthernet0/0
 R1(config-if)# shutdown
 R1(config-if)# no shutdown
 R1(config-if)# end

 # Check Elasticsearch
 curl -s "http://192.168.42.12:9200/graylog_0/_count" | jq '.count'
 # Should return > 0

 curl -s "http://192.168.42.12:9200/graylog_0/_search?size=1" | jq '.hits.hits[0]._source.message'
 # Should show the syslog message
 ```
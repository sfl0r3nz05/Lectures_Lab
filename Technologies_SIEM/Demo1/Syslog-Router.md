# DEMO: SYSLOG COLLECTION FROM ROUTER

## Overview
 
This demonstration implements log collection architecture using:

- **GNS3 Network Emulation**: Virtual network environment
- **Central-Server (Toolbox Appliance)**: rsyslog server (log collector)
- **R1 (Cisco C7200 Router)**: Log source generating syslog messages

---
 
## Architecture
 
```
┌──────────────────────────────────────────────────────────────┐
│                    GNS3 NETWORK TOPOLOGY                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────┐      ┌─────────────────────┐     │
│  │  Central-Server        │      │   R1 (Router)       │     │
│  │  (Toolbox Appliance)   │      │   (C7200)           │     │
│  │                        │      │                     │     │
│  │  eth0: 192.168.1.100   │──────│  f0/0: 192.168.1.50 │     │
│  │  rsyslog daemon        │      │  IOS 12.4           │     │
│  │  Port: 514 (UDP/TCP)   │      │  Logging enabled    │     │
│  │                        │      │                     │     │
│  └────────────────────────┘      └─────────────────────┘     │
│           │                                                  │
│           └──────── RFC 5424 Syslog (UDP:514) ──────────┐    │
│                                                         │    │
│           Logs stored in:                               │    │
│           /var/log/R1/syslog.log  ←─────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
---
 
## Prerequisites

### GNS3 Setup

1. GNS3 installed and running

2. Toolbox appliance (GNS3 default)

    - Download appliance from https://gns3.com/marketplace/appliances/networkers-toolkit

    - Select appliance:

        <img src="img/import-appliance.png" width="200">

    - Import appliance:

        <img src="img/add-appliance.png" width="500">

    - Drag device:

        <img src="img/drag-appliance.png" width="500">

- Cisco C7200 router image available

    - Download dynamips from https://drive.google.com/file/d/1cQ3y24eMJ3SjwLWeAu_hxIsO51Y0CRHX/view?usp=sharing

    - Select preferences:

        <img src="img/preferences.png" width="250">

    - Import dynamips:

        <img src="img/import-dynamips.png" width="500">

    - Drag device:

        <img src="img/drag-router.png" width="450">


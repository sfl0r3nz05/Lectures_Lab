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
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

## INTERCONNECT INFRASTRUCTURE

1. Interconnect devices:

    <img src="img/drag-router.png" width="450">

## STEP 1: CONFIGURE CENTRAL-SERVER INTERFACE

Assign IPv4 address to Central-Server's eth0 interface so it can receive syslog messages from R1.
 
```bash
root@Central-Server:~# ip link set eth0 up
root@Central-Server:~# ip addr add 192.168.1.100/24 dev eth0
root@Central-Server:~# ip a show eth0
```

## STEP 2: CONFIGURE RSYSLOG SERVER

Enable rsyslog to listen on UDP/TCP port 514 and receive syslog messages from remote devices (R1).

- Verify rsyslog Configuration
 
 ```bash
 root@Central-Server:~# cat /etc/rsyslog.conf | grep -A2 "MODULES"
 ```

- Verify UDP/TCP Inputs are Enabled

 ```bash
 module(load="imudp")
 input(type="imudp" port="514")
 
 module(load="imtcp")
 input(type="imtcp" port="514")
 ```

- Create Log Directory for R1
 
 ```bash
 root@Central-Server:~# mkdir -p /var/log/R1
 root@Central-Server:~# chown syslog:adm /var/log/R1
 root@Central-Server:~# chmod 755 /var/log/R1
 ```

- Add Log Routing Rules by editing `/etc/rsyslog.conf`:
 
 ```bash
 root@Central-Server:~# nano /etc/rsyslog.conf
 ```

- Add at the end of the file (before any `$IncludeConfig` directives):
 
 ```bash
 # Route logs from R1 by IP address
 :fromhost-ip, isequal, "192.168.1.50" /var/log/R1/syslog.log
 :fromhost-ip, isequal, "192.168.1.50" stop
 
 # Catch-all for other remote logs
 *.* /var/log/remote-hosts.log
 ```

- Restart rsyslog
 
 ```bash
 root@Central-Server:~# service rsyslog restart
 ```

 **Expected Output:**

 ```log
 * Stopping enhanced syslogd rsyslogd                                  [ OK ] 
 * Starting enhanced syslogd rsyslogd                                  [ OK ]
 ```

## STEP 3: VERIFY RSYSLOG IS LISTENING

Confirm rsyslog daemon is listening on UDP and TCP port 514.

- Check Listening Ports
 
 ```bash
 root@Central-Server:~# ss -tulpn | grep 514
 ```

 **Expected Output**
 
 ```
 udp     UNCONN   0        0                0.0.0.0:514            0.0.0.0:*      users:(("rsyslogd",pid=336,fd=6))
 udp     UNCONN   0        0                   [::]:514               [::]:*      users:(("rsyslogd",pid=336,fd=7))
 tcp     LISTEN   0        25               0.0.0.0:514            0.0.0.0:*      users:(("rsyslogd",pid=336,fd=8))
 tcp     LISTEN   0        25                  [::]:514               [::]:*      users:(("rsyslogd",pid=336,fd=9))
 ```
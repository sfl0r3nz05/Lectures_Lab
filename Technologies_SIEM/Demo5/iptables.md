# Firewall Event Logging Pipeline

This sets up a pipeline that captures `iptables` blocked traffic on the host and forwards those events to a centralized `syslog-ng` server running in Docker.

## Architecture

```
iptables (host)
   │  LOG target writes to kernel ring buffer
   ▼
Kernel log (dmesg / /proc/kmsg)
   │  read by imklog
   ▼
rsyslog (host)
   │  filters lines containing "FW-Blocked"
   │  forwards over TCP
   ▼
syslog-ng (Docker container, --network host)
   │  receives on tcp/6601
   ▼
/var/log/messages (inside container, or host path if volume-mounted)
```

Everything runs in `--network host` mode, so the containerized syslog-ng server is reachable at `127.0.0.1:6601` (TCP) / `127.0.0.1:5514` (UDP) from the host itself.

## Components

| Component | Role |
|---|---|
| `iptables` | Logs and drops traffic on a chosen port, tagging matches with a `[FW-Blocked]` prefix |
| `rsyslog` (host) | Reads kernel log via `imklog`, filters for the tag, forwards matching lines to syslog-ng |
| `syslog-ng` (Docker) | Receives forwarded logs and writes them to `/var/log/messages` |

## 1. Deploy the syslog-ng server

```bash
docker run -d \
  --name=syslog-ng \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -v config:/config \
  -v log:/var/log \
  --restart unless-stopped \
  --network host \
  lscr.io/linuxserver/syslog-ng:latest
```

### syslog-ng.conf

> Placed in /etc/syslog-ng/syslog-ng.conf

The default config writes to `/var/log/messages`. The TCP source must use the `network()` driver (not `syslog()`) with `flags(no-parse)`, since rsyslog's default TCP forwarding (`omfwd`) sends plain newline-delimited text rather than the octet-counted framing that syslog-ng's `syslog()` driver expects. Using the wrong driver causes `Invalid frame header` errors and the connection being dropped after every message.

```
cat > /config/syslog-ng.conf << 'EOF'
@version: 4.2
@include "scl.conf"

source s_local {
  internal();
};

source s_network_tcp {
  network(transport(tcp) port(6601) flags(no-parse));
};

source s_network_udp {
  syslog(transport(udp) port(5514));
};

destination d_local {
  file("/var/log/messages");
  file("/var/log/messages-kv.log" template("$ISODATE $HOST $(format-welf --scope all-nv-pairs)\n") frac-digits(3));
};

log {
  source(s_local);
  source(s_network_tcp);
  source(s_network_udp);
  destination(d_local);
};
EOF
```

Apply changes by editing the file inside the running container (or the mounted volume path on the host), ensure var/log ownership and restarting:

```bash
docker exec -u root -it syslog-ng chown -R 1000:1000 /var/log
docker restart syslog-ng
```

## 2. Configure iptables logging

Add a `LOG` rule **before** the corresponding `DROP` rule. iptables evaluates rules top-down and stops at the first match, so if `DROP` comes first, the packet never reaches the `LOG` rule.

```bash
sudo iptables -I INPUT -p tcp --dport 8080 -j LOG --log-prefix "[FW-Blocked] " --log-level 4
sudo iptables -I INPUT 2 -p tcp --dport 8080 -j DROP
```

Verify order:
```bash
sudo iptables -L INPUT -n --line-numbers -v
```
Expected: the `LOG` rule for port 8080 must appear **above** the matching
`DROP` rule.

## 3. Configure rsyslog to forward matching kernel logs

Create `/etc/rsyslog.d/60-fw-forward.conf`:

```
template(name="FWForwardFormat" type="string" string="%msg%\n")

if $msg contains 'FW-Blocked' then {
    action(type="omfwd" target="127.0.0.1" port="6601" protocol="tcp" template="FWForwardFormat")
    stop
}
```

The custom template forwards only the raw kernel message (`%msg%`),
avoiding a duplicated timestamp/hostname that appears if rsyslog's default
full-line template is forwarded and then re-logged by syslog-ng.

Restart rsyslog to apply:
```bash
sudo systemctl restart rsyslog
```

Confirm `imklog` is loaded (required for rsyslog to read kernel messages
at all):
```bash
grep -r "imklog" /etc/rsyslog.conf /etc/rsyslog.d/
```
If missing:
```bash
echo 'module(load="imklog")' | sudo tee /etc/rsyslog.d/10-imklog.conf
sudo systemctl restart rsyslog
```

## 4. Test the pipeline

Generate blocked traffic (no listening service required — the `DROP` happens at the netfilter level before any socket is involved):

```bash
nc -zv 127.0.0.1 8080
# or
curl --max-time 2 127.0.0.1:8080
```

Check each stage:

```bash
# 1. Kernel captured it
sudo dmesg | grep FW-Blocked
sudo journalctl -k | grep FW-Blocked

# 2. rsyslog processed and forwarded it
sudo tail -f /var/log/syslog

# 3. syslog-ng received and stored it
docker exec -it syslog-ng tail -f /var/log/messages
```

A successful run shows a single clean line in `/var/log/messages`, e.g.:

```
Sep 11 04:30:24 localhost [26589.676448] [FW-Blocked] IN=lo OUT= MAC=00:00:00:00:00:00:00:00:00:00:00:00:08:00 SRC=127.0.0.1 DST=127.0.0.1 LEN=60 TOS=0x00 PREC=0x00 TTL=64 ID=21648 DF PROTO=TCP SPT=48372 DPT=8080 WINDOW=65495 RES=0x00 SYN URGP=0 MARK=0x3887
```

## Useful inspection commands

```bash
# syslog-ng's own internal/service log (startup, stats, errors — not received messages)
docker exec -it syslog-ng cat /config/log/current

# Confirm syslog-ng is listening on the expected ports
sudo ss -tulnp | grep syslog-ng

# Live tail of received firewall events
docker exec -it syslog-ng tail -f /var/log/messages

# List iptables
sudo iptables -L INPUT -n --line-numbers -v

# Remove all four (delete by line number, highest first so numbering doesn't shift)
sudo iptables -D INPUT 5
```
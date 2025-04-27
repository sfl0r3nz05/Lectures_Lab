# Configure HTTP/HTTPS server on Cisco Router

- [Configure HTTP/HTTPS server on Cisco Router](#configure-httphttps-server-on-cisco-router)
  - [Practice objectives](#practice-objectives)
  - [Network Scenario](#network-scenario)
  - [Import Appliances](#import-appliances)
  - [Connect the devices](#connect-the-devices)
  - [Configure HTTP AND HTTPS Server on the Router](#configure-http-and-https-server-on-the-router)
    - [Verify vty from Kali Linux Docker](#verify-vty-from-kali-linux-docker)
  - [Security Tests](#security-tests)
  - [Access Router page through HTTPS from Kali Linux VM](#access-router-page-through-https-from-kali-linux-vm)

## Practice objectives

- Create a design of the network.
- Configure the network which consist of:
  - Configure hostname, domain name.
- Generate crypto keys
- Configure line vty, interfaces, DHCP Pool.
- Create the user.
- Configure the HTTP and HTTPS on cisco router.
- Verify the accounts by accessing through telnet and SSH.
- Access cisco router through browser.

## Network Scenario

This is a very simple network scenario which consists of one cisco router 7200 series and one virtual machine (running kali linux).

- Network: 10.0.0.0/8
- Router IP: 10.0.0.1
- Linux IP: 10.0.0.2

## Import Appliances

1. Integrar los enrutadores como:
   1. Appliances:
      1. Copie/Descargue en el host donde corre el cliente GNS3 el appliance del router`cisco-7200` el cual se encuentra [aquí](../../utils/appliances/cisco-7200.gns3a).
      2. Para insertar el dispositivo como appliance usar las siguientes [instrucciones](../../utils/GNS3ImportAppliances/README.md).

      > **Importante:** Regrese a este apartado al importar el appliance.

2. Integrar el Linux PC como:
   1. Docker container:
      1. Para insertar el dispositivo como Docker container usar las siguientes [instrucciones](../../utils/DockerKaliLinux/README.md).

      > **Importante:** Regrese a este apartado al importar el appliance.

## Connect the devices

   <img src="./img/img1.PNG"  width="60%" height="30%">

## Configure HTTP AND HTTPS Server on the Router

- Configure HOSTNAME

```console
R1(config)#hostname router1
```

- Configure DOMAIN NAME

```console
router1(config)#ip domain-name dtr.com
```

- Generate CRYPTO KEYS

```console
router1(config)#crypto key generate rsa
router1(config)#ip ssh time-out 60
router1(config)#ip ssh authentication-retries 2
router1(config)# transport input ssh
```

- Configure LINE VTY

```console
router1#config t
router1(config)#line vty 0 4
router1(config-line)#login local
router1(config-line)#end
router1#
```

- Configure INTERFACE

```console
router1#config t
router1(config)#interface f0/0
router1(config-if)#ip add 10.0.0.1 255.0.0.0
router1(config-if)#no shutdown
router1(config-if)#exit
router1(config)#
```

- Configure DHCP POOL

```console
router1(config)#ip dhcp pool drt
router1(dhcp-config)#network 10.0.0.0
router1(dhcp-config)#dns-server 10.0.0.1
router1(dhcp-config)#default-router 10.0.0.1
router1(dhcp-config)#exit
router1(config)#end
router1#
```

- Configure HTTP SERVER

```console
router1(config)#ip http server
router1(config)#ip http secure-server
router1(config)#ip http authentication local
```

- Create USER

```console
router1(config)#username dtruser privilege 15 password 0 12345
router1(config)#logging buffered 51200 warning
router1(config)#
```

### Verify vty from Kali Linux Docker

- Add IP address to the Kali Linux Docker

  ```console
  ifconfig eht0 10.0.0.2 netmask 255.0.0.0
  ```

  - Or use DHCP client:

    ```console
    nano /etc/network/interfaces
    ```

  - Uncomment next two lines:

    ```console
    auto eth0
    iface eth0 inet dhcp
    ```

  - Restart the Linux Docker Container

- Test the connection via ping: `ping 10.0.0.1`

- Verifying SSH

```console
ssh -l dtruser 10.0.0.1
```

- Access Telnet

```console
telnet 10.0.0.1
```

## Security Tests

- Scan HTTP/HTTPS services from Kali Linux VM

  - Find out what information you will get when you perform a version scan on port 80 and 443

```console
nmap -sV 10.0.0.1 -p80,443
```

- Scan SSL services from Kali Linux VM

  - Now we know that ssl is running on port 443. Lets confirm it which version of ssl is running on this cisco router.
  - We can make this work easier by using sslscan. You can find this tool easily on kali linux or simply you can download from the repositories.

```console
sslscan 10.0.0.1
```

## Access Router page through HTTPS from Kali Linux VM

- To access the router, we need to enter the **username:** `dtruser` and **password:** `12345`.

```console
curl -u dtruser:12345 http://example.com
```

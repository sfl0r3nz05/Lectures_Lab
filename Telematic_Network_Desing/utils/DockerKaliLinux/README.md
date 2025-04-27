# Create Docker Kali Linux to import on GNS3

## Inside the VM hosting the GNS Server

1. Access (e.g.: via *ssh*) to the instance that hosts the GNS3 Server.
2. Clone the repo: `https://github.com/sfl0r3nz05/TelematicsNetworkDesign.git`
3. Access the repo: `cd ~/TelematicsNetworkDesign`
4. Update submodules: `git submodule update --init --recursive`.
   1. Required if any submodule has been updated or if you want to use a specific branch: `git submodule update --remote`.
5. Access to the Submodule: `cd ~/TelematicsNetworkDesign/utils/KaliDockerGNS3`.
6. Build the image. E.g.: `docker build -t sflorenz05/kalidockergns3:v0.1 .`.

## Inside the host that hosts the GNS Client

1. Follow these instructions to [import a Docker container](../GNS3ImportDocker/README.md).

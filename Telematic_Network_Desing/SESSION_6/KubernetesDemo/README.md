# Demo cluster deployment

- [Demo cluster deployment](#demo-cluster-deployment)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
  - [Deploy DB](#deploy-db)
  - [Deploy Server](#deploy-server)
  - [Expose to the world](#expose-to-the-world)
  - [Clean Up](#clean-up)

## Prerequisites

1. Install *kubectl*

   ```console
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   ```

   ```console
   curl -LO "https://dl.k8s.io/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl.sha256"
   ```

   ```console
   echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
   ```

   ```console
   sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
   ```

2. Install *minikube*

   *v1.24.0*:

   ```console
   curl -Lo minikube https://storage.googleapis.com/minikube/releases/v1.24.0/minikube-linux-amd64 && chmod +x minikube && sudo mv minikube /usr/local/bin/
   ```

3. Install *conntrack* library

   ```console
   sudo apt-get install -y conntrack
   ```

## Setup

1. Deployed Minikube, considering 2GB default memory isn't always enough

   ```console
   minikube start --driver=none --memory=4096
   ```

2. Clone the repository

   ```console
   git clone https://github.com/sfl0r3nz05/TelematicsNetworkDesign.git
   ```

3. Go to the demo directory

   ```console
   cd ~/TelematicsNetworkDesign/KubernetesDemo
   ```

## Deploy DB

Deployments can be configured from the command-line, but this becomes difficult when you have many parameters to specify. Therefore, users typically generate a YAML file specifying the details of their deployment, which is what we will do as well. It is convention to name the deployment object the same as the YAML file.

1. Use the `hello_world_db_deployment.yml` file.
2. Review the file:
   1. The name of our Deployment is `hello-world-db-deployment`.
   2. We only want one pod for our deployment, as indicated by `replicas: 1`.
   3. The selector defines how the Deployment finds which Pod(s) to manage. In this case, we simply select a label that is defined in the Pod template. That’s what the two books-app fields are for.
   4. We specify the Docker image and version we want to use: `sflorenz05/drt:db`. 
      1. The imagePullPolicy is set to Always since we want to pull the Docker image from Docker Hub whenever we create a new Pod. 
      2. I already pushed our database server Docker image to a repository on Docker hub, making it easier for us to deploy the Docker image with our web application using Kubernetes.
   5. You can see that we expose port 8081 for the Pod.
3. Create a deployment:

   ```console
   kubectl create -f hello_world_db_deployment.yml
   ```

4. You should get a message saying `deployment.apps/hello-world created`.
5. You can now use the `kubectl get deployments` command to see that your deployment is available, meaning it is ready to receive HTTP requests. 
6. Use `kubectl get pods` command to see that pods are running.

## Deploy Server

Now, the Pod is running our database server running on our Kubernetes cluster, however this server is not exposed to the outside world because it is encapsulated within the cluster. Check this by trying to connect to `http://localhost:8081/`. You should get a connection error. We need to now create a deployment for our front-end web server, so that we can access our web application.

1. Use the `hello_world_server_deployment.yml` file.
2. Remember that we need to have our front-end server connect to our database server, like we accomplished when we were just running the Docker containers on our local machines. 
   1. To accomplish this, we need to know the internal IP address that Kubernetes has assigned to the Pod running our database server. 
   2. This IP address can only be used from within the Kubernetes cluster. We can get this IP by running `kubectl get pods -o=custom-columns=NAME:.metadata.name,IP:.status.podIP`.
3. Open up the `hello_world_server_deployment.yml` file and make sure the IP you get for the hello-world-db-deployment is the same IP address specified in the `value` field for the `DB_URL`. If it is the same, then you're good to go. If it is different, then please change it.
   1. You will also see that we specify port 8080 as a communication port for the Pod.
4. Now, we can run `kubectl create -f hello_world_server_deployment.yml` to create a deployment for our front-end web server.
5. Use `kubectl get deployments` and `kubectl get pods` to see that your pods are running.
6. Now that we have both parts of our application running, try visiting `http://localhost:8080/`. 
   1. *Can you access the web application?* The answer should be no because although we have exposed ports for our Pods, they are not accessible to the outside world. So far, we can only communicate with the Pods running our application if we are within the Kubernetes cluster (again, this is for isolation purposes). Let's check this out from within the cluster:
      1. Run `kubectl get pods -o=custom-columns=NAME:.metadata.name,IP:.status.podIP` and copy the IP address for the `hello-world-server-deployment`.
      2. Run `minikube ssh` in your Terminal window. You should see `minikube` written in you Terminal window.
      3. Run `curl <hello-world-server-deployment-URL>:8080/` several times. You should get responses for "Hello world!" in different languages, demonstrating that the application is working.
      4. Run `exit` to exit the `minikube` Terminal.

## Expose to the world

1. To be able to access our web application from outisde, we need to create a Kubernetes Service to make the `hello-world` container accessible from outside the Kubernetes virtual network.

2. Use `kubectl expose deployment hello-world-server-deployment --type=LoadBalancer --port=8080` to allow your container to receive HTTP request from outside.
3. You should get a message that says `service/hello-world exposed`.
4. You can view the status of your service by using the `kubectl get services` command.
   1. Notice that the `EXTERNAL-IP` for our service is pending. If we were running our Kubernetes cluster using a cloud provider, such as AWS, we would get an actual IP address to access our service from anywhere.
   2. Since we are running *Minikube*, you can access your service by using the `minikube service hello-world-server-deployment`. This should automatically open a web page with our *Hello world!* page. Reload this page a few times to see the different "Hello world!" translations.

## Clean Up

- You can clean up the resources and cluster using:

   ```console
   kubectl delete service hello-world-server-deployment
   ```

   ```console
   kubectl delete deployment hello-world-server-deployment
   ```

   ```console
   kubectl delete deployment hello-world-db-deployment
   ```

   ```console
   minikube stop
   ```

   ```console
   minikube delete
   ```

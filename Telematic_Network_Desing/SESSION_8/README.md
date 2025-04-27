# BGP on K8s

Resources to help with re-creating the environment described in the blog post "Experiment with Calico BGP in the Comfort of Your Own Laptop!"

![Alt text](/SESSION_8/img/image.png)

1. If you have any existing Minikube clusters, you will probably want to delete them in order to keep a simple setup.

```console
minikube delete --all
```

2. Start by creating a cluster called cluster-a. 

```console
minikube -p cluster-a start --network-plugin=cni \
--extra-config=kubeadm.pod-network-cidr=10.200.0.0/16 \
--service-cluster-ip-range=10.201.0.0/16 --network=calico_cluster_peer_demo
```

3. At this point, if we examine the Docker networks, the host routing table, and the IP of the new cluster node, we notice something interesting. The new calico_cluster_peer_demo Docker network has been created, but it isn’t actually being used. Instead, the default Docker bridge is being used. This is not a problem for us but it is unintended and has been reported to the Minikube team on the PR noted earlier.

```console
kubectl --cluster=cluster-a get nodes -o wide
```

```console
route -n | grep 172
docker network ls
docker network inspect 696c32a7ee20 | grep 172
```

4. Next, install Calico on cluster-a as normal using a tigera-operator installation. Install the latest Tigera operator on the cluster.

```console
kubectl --cluster=cluster-a create -f https://raw.githubusercontent.com/projectcalico/calico/v3.24.1/manifests/tigera-operator.yaml
```

5. Provide a manifest for the operator specifying the desired pod CIDR and that you want encapsulation to be disabled. Encapsulation is not required in this environment because all routers involved have a full view of the routing topology (thanks to BGP). After waiting for a short time, we can see that calico-node and the other Calico components have been installed by the operator and are running as intended.

```console
cat cluster_a_calicomanifests/custom-resources.yaml
kubectl --cluster=cluster-a create -f cluster_a_calicomanifests/custom-resources.yaml
```

6. At the moment, the cluster only has one node. Since this is Minikube, there is no taint on the master node and I can therefore deploy the testing workload that be used later to show that things are working.

```console
cat cluster_a_calicomanifests/custom-resources.yaml
kubectl --cluster=cluster-a apply -f testingworkload/echo-server.yaml
kubectl --cluster=cluster-a get pods
```

7. Now, add 3 more nodes to the cluster so there are 4, as shown in the diagram.

```console
for i in {1..3}; do minikube --profile cluster-a node add; done
kubectl --cluster=cluster-a get nodes -o wide
```

8. Minikube node add erroneously adds kindnet as a side-effect, so we remove that as we already have Calico as a CNI.

```console
kubectl --cluster=cluster-a get pods -A -o wide | grep -i kindnet
kubectl --cluster=cluster-a delete ds -n=kube-system kindnet
```

9. Now I’ll download and install the calicoctl binary in /usr/local/bin on the 4 cluster nodes, and then run it on all of them by SSHing into them and issuing sudo calicoctl node status. This is a quick way of showing the state of BGP peerings on the cluster. In a follow-on blog post, I will show you how to do this, and many other things, with the new CalicoNodeStatus API, but I prefer to capture all of that knowledge in a single post. So, for now:

```console
for i in cluster-a cluster-a-m02 cluster-a-m03 cluster-a-m04; do minikube ssh -p cluster-a -n $i "curl -o calicoctl -O -L http://github.com/projectcalico/calicoctl/releases/download/v3.21.1/calicoctl && sudo mv calicoctl /usr/local/bin/calicoctl && chmod +x /usr/local/bin/calicoctl"; done
```

```console
for i in cluster-a cluster-a-m02 cluster-a-m03 cluster-a-m04; do minikube ssh -p cluster-a -n $i "sudo calicoctl node status"; done
```

10. Before we move on, it’s worth taking a moment to notice the default state of BGP on a fresh cluster installed with the Tigera operator and encapsulation disabled. Although the user does not need to be aware of it at this point, BGP is already running and:

- The BGP is using the default port, TCP/179
- The nodes are in an iBGP full mesh (each node is BGP peered to every other node)
- All nodes are all in the same BGP AS, 64512 (which is what makes this iBGP, not eBGP—the i stands for “Internal”)

It is outside of the scope of this post to give full details, but to simplify: for now, a full mesh is required because iBGP has a routing loop prevention mechanism that means all nodes must peer directly or they will not have a view of all routes in the AS.

If the peers are not “Established,” it is often the case that TCP/179 is being blocked by the underlying network.

I know that, at this point, those with some experience of routing protocols might become nervous seeing BGP running already. That’s because many well known routing protocols, such as OSPF, have a discovery mechanism that means they start peering and exchanging routes with any and all routers they find nearby.

That is not the case with vanilla BGP, so you don’t need to be concerned—neighbors are added explicitly by IP and port. In addition, it’s possible to add a BGP password, both for additional security and peace of mind.

11. By examining the nodes, pods, and services, we can see that *cluster-a* appears healthy.

```console
kubectl --cluster=cluster-a get nodes -o wide
kubectl --cluster=cluster-a get pods -A -o wide
kubectl --cluster=cluster-a get services -A -o wide
```

12. Building the cluster-b Minikube Cluster in the same Docker Network

```console
# Build

minikube -p cluster-b start --network-plugin=cni \
--extra-config=kubeadm.pod-network-cidr=10.210.0.0/16 \
--service-cluster-ip-range=10.211.0.0/16 --network=calico_cluster_peer_demo

kubectl --cluster=cluster-b create -f https://raw.githubusercontent.com/projectcalico/calico/v3.24.1/manifests/tigera-operator.yaml

kubectl --cluster=cluster-b create -f cluster_b_calicomanifests/custom-resources.yaml

kubectl --cluster=cluster-b apply -f testingworkload/echo-server.yaml

for i in {1..3}; do minikube --profile cluster-b node add; done

kubectl --cluster=cluster-b delete ds -n=kube-system kindnet

for i in cluster-b cluster-b-m02 cluster-b-m03 cluster-b-m04; do minikube ssh -p cluster-b -n $i "curl -o calicoctl -O -L http://github.com/projectcalico/calicoctl/releases/download/v3.21.1/calicoctl && sudo mv calicoctl /usr/local/bin/calicoctl && chmod +x /usr/local/bin/calicoctl"; done

# Validate

for i in cluster-b cluster-b-m02 cluster-b-m03 cluster-b-m04; do minikube ssh -p cluster-b -n $i "sudo calicoctl node status"; done

kubectl --cluster=cluster-b get nodes -o wide

kubectl --cluster=cluster-b get pods -A -o wide

kubectl --cluster=cluster-b get services -A -o wide
```

13. Converting the Clusters to a New Deployment Model

As per the original design, my aim is not to have one big cluster of eight nodes. I want to have two clusters of four nodes. So, the first step is to switch cluster-b to use BGP AS 64513. Nothing else will change. Since all 4 nodes in cluster-b will switch to the new AS, cluster-b will continue to use iBGP and everything else will remain unchanged. There will be a very brief traffic interruption (sub-second) as the AS is changed.

I will also tell both clusters to advertise their service CIDR block.

As is usually the case with well-designed Kubernetes tools, changing the BGP AS is not done directly on the nodes. Instead it is applied as YAML that is noticed by the calico-node pod running on every node.

```console
cat cluster_a_calicomanifests/bgp-configuration.yaml
cat cluster_b_calicomanifests/bgp-configuration.yaml
kubectl config use-context cluster-a && calicoctl apply -f cluster_a_calicomanifests/bgp-configuration.yaml
kubectl config use-context cluster-b && calicoctl apply -f cluster_b_calicomanifests/bgp-configuration.yaml
```

cluster-b is now running on BGP AS 64513, and both clusters are advertising their service CIDR IP range and pod CIDR IP ranges, which are unique.

14. Route Reflectors for Fun and Profit

iBGP route reflectors (from now on, I’ll refer to them as “RRs”) are conceptually not that complex. For the purposes of this post, you can just be aware that they act like normal iBGP nodes, except that they:
Are allowed to forward routes they learn from one iBGP peer to another
Can be clustered to facilitate high-availability configurations

In short, this means that a BGP AS where iBGP RRs are configured no longer needs to maintain a full mesh. It is sufficient for all non-RR BGP nodes to peer only with the RRs. The RRs, in turn, must still peer with all other nodes, including other RRs in the RR cluster.

This is beneficial for our setup. Now, no matter how many Kubernetes nodes are added to either cluster, the BGP peerings will not need to be adjusted! The peerings in each cluster will be automatically adjusted by Calico based on Kubernetes labels.

In addition, four eBGP (External BGP) peerings between the two clusters will be added to allow each cluster to advertise its pod and service CIDR to the other cluster, resulting in end-to-end reachability without any NAT or encapsulation. Since the route reflectors are predefined and static, and there are two in each cluster, this configuration won’t need altering once the clusters are up and running.

Each cluster has four nodes. The following nodes will be route reflectors and eBGP peers, as shown in the diagram:

- cluster-a-m03
- cluster-a-m04
- cluster-b-m03
- cluster-a-m04

All other nodes will be normal iBGP peers only.

15. Building the final BGP Configuration

First, I will drain all workloads off the nodes that will become RRs. There is no need to worry about DaemonSet-managed pods—those will sort themselves out. Similarly, other workloads that require a certain number of replicas, such as calico-apiserver, will re-establish their target if necessary. That’s why the output below shows one of the calico-apiserver pods as only having been running for a short period of time.

Draining workloads from these nodes will ensure that disruption is minimal when BGP reconverges, though in this lab that doesn’t really matter.

```console
kubectl --cluster=cluster-a drain --ignore-daemonsets cluster-a-m03 cluster-a-m04
kubectl --cluster=cluster-b drain --ignore-daemonsets cluster-b-m03 cluster-b-m04
kubectl --cluster=cluster-b get pods -A -o wide
```

16. Next, it’s time to instruct Calico to make the target nodes RRs, by patching their node configurations with a route reflector cluster ID. Note that this is the same across both RRs in each cluster, but different across clusters. Actually, it could be the same in each cluster, but it felt prudent to make it different.

```console
kubectl config use-context cluster-a && calicoctl patch node cluster-a-m03 -p '{"spec": {"bgp": {"routeReflectorClusterID": "244.0.0.1"}}}' && calicoctl patch node cluster-a-m04 -p '{"spec": {"bgp": {"routeReflectorClusterID": "244.0.0.1"}}}'
```

```console
kubectl config use-context cluster-b && calicoctl patch node cluster-b-m03 -p '{"spec": {"bgp": {"routeReflectorClusterID": "244.0.0.2"}}}' && calicoctl patch node cluster-b-m04 -p '{"spec": {"bgp": {"routeReflectorClusterID": "244.0.0.2"}}}'
```

17. Now, I’ll apply a route-reflector=true Kubernetes label to the nodes that are now RRs, and then I’ll apply a manifest in both clusters instructing all nodes to establish a BGP peering with any node with that label. Finally, I’ll disable the automatic full mesh that we saw at the start of this blog post. You can think of that as removing the “scaffolding” now that we have set up this new BGP configuration.

```console
kubectl --cluster=cluster-a label node cluster-a-m03 route-reflector=true
kubectl --cluster=cluster-a label node cluster-a-m04 route-reflector=true
kubectl --cluster=cluster-b label node cluster-b-m03 route-reflector=true
kubectl --cluster=cluster-b label node cluster-b-m04 route-reflector=true
```

```console
cat cluster_a_calicomanifests/bgp-rr-configuration.yaml
cat cluster_b_calicomanifests/bgp-rr-configuration.yaml
kubectl config use-context cluster-a && calicoctl apply -f cluster_a_calicomanifests/bgp-rr-configuration.yaml
kubectl config use-context cluster-b && calicoctl apply -f cluster_b_calicomanifests/bgp-rr-configuration.yaml
kubectl config use-context cluster-a && calicoctl patch bgpconfiguration default -p '{"spec": {"nodeToNodeMeshEnabled": false}}'
kubectl config use-context cluster-b && calicoctl patch bgpconfiguration default -p '{"spec": {"nodeToNodeMeshEnabled": false}}'
```

18. To keep this blog from becoming absurdly long, I won’t show the output here, but if you were to check the BGP status again as you did earlier, you would see that in each cluster, the BGP is as we described before: the RR nodes are peered to all other nodes, and the non-RR nodes are peered only to the RRs.

Let’s uncordon those RRs now to allow them to carry workloads again.

```console
kubectl --cluster=cluster-a uncordon cluster-a-m03 cluster-a-m04
kubectl --cluster=cluster-b uncordon cluster-b-m03 cluster-b-m04
```

19. It’s time to establish the eBGP peerings between the clusters now. We manually instruct each RR node to eBGP peer with the two RR nodes in the other cluster. As we noted before, this will not need any further adjustment if we add more nodes to the cluster.

```console
cat cluster_a_calicomanifests/bgp-other-cluster.yaml
cat cluster_b_calicomanifests/bgp-other-cluster.yaml
kubectl config use-context cluster-a && calicoctl apply -f cluster_a_calicomanifests/bgp-other-cluster.yaml
kubectl config use-context cluster-b && calicoctl apply -f cluster_b_calicomanifests/bgp-other-cluster.yaml
```

20. It would be reasonable to expect everything to be working at this point, but there is still one more thing to do.

In any good BGP network, including a Calico cluster that is running BGP, route advertisement filtering is implemented between all BGP peers to ensure that only the route advertisements that are expected and intended are allowed to propagate. This is normal behavior in a BGP network—it can be considered a “belt-and-braces” way of making sure that routing is working in the way that was intended.

It is quite an unusual use case to peer two clusters directly in the way that we are doing in this blog. Calico’s BGP is more commonly used to peer with Top-of-Rack switches. In that scenario, receiving a default route from the ToR is usually adequate; it is not necessary for Calico to accept more granular/specific routes. Calico’s default BGP behavior disallows these more granular routes from being advertised further within each cluster.

Never fear. I haven’t come this far to give up! Luckily, it’s easy to alter the behavior so that both clusters accept the more granular routes. I do this by creating IPPool resources in both clusters that are in a disabled state. Each cluster’s new pools are configured with the CIDR addresses of the other cluster’s service and pod CIDRs. The result of doing this is that both clusters alter their behavior and accept them, since the IPs are now recognized. Since the IP pools are created in a disabled state, the IPs won’t actually be assigned to pods on the wrong cluster—only recognized.

```console
cat cluster_a_calicomanifests/disabled-othercluster-ippools.yaml
cat cluster_b_calicomanifests/disabled-othercluster-ippools.yaml
kubectl config use-context cluster-a && calicoctl apply -f cluster_a_calicomanifests/disabled-othercluster-ippools.yaml
kubectl config use-context cluster-b && calicoctl apply -f cluster_b_calicomanifests/disabled-othercluster-ippools.yaml
```

21. End-to-End Validation

```console
kubectl --cluster=cluster-a get nodes -o wide
kubectl --cluster=cluster-a get pods -A -o wide
kubectl --cluster=cluster-a get services -A -o wide
```

22. There’s nothing specific to report; everything looks great! Now let’s examine cluster-a’s BGP peerings (refer back to the diagram to make sense of these).

```console
for i in cluster-a cluster-a-m02 cluster-a-m03 cluster-a-m04; do minikube ssh -p cluster-a -n $i "sudo calicoctl node status"; done
```

23. In the interest of respecting your valuable time, I won’t repeat the same commands on cluster-b; but suffice to say it’s the mirror image of cluster-a and all looks well.

Finally, let’s look at the actual routing tables of the 4 nodes in cluster-a. Note that all of the nodes have routes for subnets in 10.210.0.0/16 and 10.211.0.0/16, and even better, they’re ECMP (Equal-Cost Multipath) routes, load-balanced to both of cluster-b’s route reflectors.

cluster-b also has equivalent routes to cluster-a.

```console
for i in cluster-a cluster-a-m02 cluster-a-m03 cluster-a-m04; do echo "-----"; minikube ssh -p cluster-a -n $i "ip route"; done
for i in cluster-a cluster-b-m02 cluster-b-m03 cluster-b-m04; do echo "-----"; minikube ssh -p cluster-b -n $i "ip route"; done
```

24. The Victory Lap (aka “Testing”) The easiest way is to connect end-to-end, shown here from a pod in cluster-a to a pod in cluster-b, and again from a pod in cluster-a to a service in cluster-b. 

```console
kubectl --cluster=cluster-a run tmp-shell --rm -i --tty --image nicolaka/netshoot -- /bin/bash

If you don't see a command prompt, try pressing enter.

bash-5.1# curl http://10.211.116.156:8385

Request served by echoserver-6558697d87-9tl8b

HTTP/1.1 GET /

Host: 10.211.116.156:8385
User-Agent: curl/7.80.0
Accept: */*

bash-5.1# curl http://10.210.139.128:8080
Request served by echoserver-6558697d87-9tl8b

HTTP/1.1 GET /

Host: 10.210.139.128:8080
User-Agent: curl/7.80.0
Accept: */*

bash-5.1# exit
exit
Session ended, resume using 'kubectl attach tmp-shell -c tmp-shell -i -t' command when the pod is running
pod "tmp-shell" deleted
```

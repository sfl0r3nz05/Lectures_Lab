# Namespaces Demonstration

*Namespaces* are a feature of the Linux kernel that partitions kernel resources such that one set of processes sees one set of resources while another set of processes sees a different set of resources. In other words, the key feature of *namespaces* is that they isolate processes from each other. On a server where you are running many different services, isolating each service and its associated processes from other services means that there is a smaller blast radius for changes, as well as a smaller footprint for security‑related concerns. Mostly though, isolating services meets the architectural style of microservices as described.

## Types of Namespaces

Within the Linux kernel, there are different types of namespaces. Each namespace has its own unique properties:

- A **user namespace** has its own set of user IDs and group IDs for assignment to processes. In particular, this means that a process can have root privilege within its user namespace without having it in other user namespaces.

- A **process ID (PID) namespace** assigns a set of PIDs to processes that are independent from the set of PIDs in other namespaces. The first process created in a new namespace has PID 1 and child processes are assigned subsequent PIDs. If a child process is created with its own PID namespace, it has PID 1 in that namespace as well as its PID in the parent process’ namespace.

- A **network namespace** has an independent network stack: its own private routing table, set of IP addresses, socket listing, connection tracking table, firewall, and other network‑related resources.

- A **mount namespace** has an independent list of mount points seen by the processes in the namespace. This means that you can mount and unmount filesystems in a mount namespace without affecting the host filesystem.

- An **interprocess communication (IPC) namespace** has its own IPC resources, for example POSIX message queues.
A UNIX Time‑Sharing (UTS) namespace allows a single system to appear to have different host and domain names to different processes.

## An Example of PID Namespaces

Understanding PID namespaces will be a better way to understand container isolation.

Before start the demonstration it must be considered that we use 3 terminals named as: *Terminal 1*, *Terminal 2* and *Terminal 3*.

![3-terminals](./img/3-consoles.png)

1. **Terminal 1**: See all processes that are running for the system.

    ```console
    # ps -ef
    ```

    *Command Output*:

    ```console
    UID          PID    PPID  C STIME TTY          TIME CMD
    root           1       0  0 09:44 ?        00:00:07 /sbin/init auto automatic-ubiq
    root           2       0  0 09:44 ?        00:00:00 [kthreadd]
    root           3       2  0 09:44 ?        00:00:00 [rcu_gp]
    ```

    There is a column dedicated to identify the process (PID).

2. **Terminal 1**: List all pid namespaces:

    ```console
    # lsns -t pid
    ```

    *Command Output*:

    ```console
            NS TYPE NPROCS   PID USER   COMMAND
    4026531836 pid      11  4627 ubuntu /lib/systemd/systemd --user
    ```

    The number `4026531836` is refered as *initial PID namespace* or *root namespace*. By default, all the process that are running on the system will run on this *root namespace*.

3. **Terminal 1**: Confirm that all processes on the system are running on the *root namespace*.

    ```console
    # ps -e -o pidns,pid,args
    ```

    *Command Output*:

    ```console
    PIDNS     PID COMMAND
    4026531836       1 /sbin/init auto automatic-ubiquity noprompt
    4026531836       2 [kthreadd]
    4026531836       3 [rcu_gp]
    4026531836       4 [rcu_par_gp]
    4026531836       6 [kworker/0:0H-events_highpri]
    4026531836       8 [kworker/0:1H-events_highpri]
    4026531836       9 [mm_percpu_wq]
    4026531836      10 [ksoftirqd/0]
    ```

    It can be seen how each process running on the system uses the same *root namespace* `4026531836`.

4. **Terminal 2**: We use the *unshare* command to run programs in new name namespaces. So, the next command allows to create a new namespace with its own user and PID namespaces:

    ```console
    # unshare --pid --fork --mount-proc /bin/bash
    ```

5. **Terminal 2**: See all processes that are running for this new names.

    ```console
    # ps -ef
    ```

    *Command Output*:

    ```console
    root@ubuntu:/home/ubuntu# ps -ef
    UID          PID    PPID  C STIME TTY          TIME CMD
    root           1       0  0 11:01 pts/1    00:00:00 /bin/bash
    root           8       1  0 11:01 pts/1    00:00:00 ps -ef
    ```

6. **Terminal 2**: On the created namespace, 3 processes are launched using the command `sleep`:

    ```console
    # sleep 2000 &
    ```

    ```console
    # sleep 2100 &
    ```

    ```console
    # sleep 2200 &
    ```

7. **Terminal 2**: See all processes that are running for the system.

    ```console
    # ps -ef
    ```

    *Command Output*:

    ```console
    UID          PID    PPID  C STIME TTY          TIME CMD
    root           1       0  0 11:01 pts/1    00:00:00 /bin/bash
    root           9       1  0 11:11 pts/1    00:00:00 sleep 2000
    root          10       1  0 11:11 pts/1    00:00:00 sleep 2100
    root          11       1  0 11:11 pts/1    00:00:00 sleep 2200
    root          12       1  0 11:11 pts/1    00:00:00 ps -ef
    ```

8. **Terminal 2**: List all pid namespaces in order to see the new namespace.

    ```console
    # lsns -t pid
    ```

    *Command Output*:

    ```console
            NS TYPE NPROCS PID USER COMMAND
    4026532753 pid       5   1 root /bin/bash
    ```

### Conclusion of this example

1. Processes can only see other processes in their own PID namespace, and any descendant namespaces they have
2. The root PID namespace is the initial PID namespace and all other PID namespaces descend from it. Thus, the root PID namespace can see all processes in all PID namespaces on the system.

    ![3-terminals-2](./img/3-consoles-2.png)

3. If you use the `lsns` command on **Terminal 1**, you can see the 2 *root namespaces*, where the *pid namespace* `4026532753` is a descendant of the *pid namespace* `4026531836`, so it would be possible to see it inside *pid namespace* source.

    ```console
    # lsns -t pid
    ```

    *Command Output*:

    ```console
            NS TYPE NPROCS PID USER COMMAND
    4026531836 pid     249     1 root             /sbin/init auto automatic-ubiquity n
    4026532753 pid       4 80648 root             /bin/bash
    ```

4. To check this, use the `ps` command on **terminal 1**  to observe the sleep processes launched in the descending *pid namespace*.

    ```console
    # ps -ef
    ```

    *Command Output*:

    ```console
    UID          PID    PPID  C STIME TTY          TIME CMD
    ...          ...     ...  .   ...   ...         ... ... 
    root      126993       2  0 11:49 ?        00:00:00 [kworker/u256:0-events_power_efficient]
    root      127431       2  0 11:49 ?        00:00:00 [kworker/1:1-events]
    root      129022   80648  0 11:51 pts/1    00:00:00 sleep 2000
    root      129109   80648  0 11:51 pts/1    00:00:00 sleep 2100
    root      129142   80648  0 11:51 pts/1    00:00:00 sleep 2200
    ...          ...     ...  .   ...   ...         ... ...
    ```

# Cgroups Demonstration

- [Cgroups Demonstration](#cgroups-demonstration)
  - [Example of Manual cgroup use](#example-of-manual-cgroup-use)
  - [cgroup Example using libcgroup](#cgroup-example-using-libcgroup)

**cgroups** (abbreviated from *control groups*) is a Linux kernel feature that limits, accounts for, and isolates the resource usage (CPU, memory, disk I/O, network, etc.) of a collection of processes. The *control groups* functionality was merged into the Linux kernel mainline in kernel version *2.6.24*, which was released in January 2008.

Groups are materialized in the pseudo-filesystem mounted in `/sys/fs/cgroup` and are created by mkdir in the abovementioned pseudo-filesystem.

```console
ls -la /sys/fs/cgroup/
```

*Output*:

```console
total 0
dr-xr-xr-x 11 root root 0 Oct  1 15:17 .
drwxr-xr-x  8 root root 0 Oct  1 15:17 ..
-r--r--r--  1 root root 0 Oct  1 15:17 cgroup.controllers
-rw-r--r--  1 root root 0 Oct  1 15:18 cgroup.max.depth
-rw-r--r--  1 root root 0 Oct  1 15:18 cgroup.max.descendants
-rw-r--r--  1 root root 0 Oct  1 15:17 cgroup.procs
-r--r--r--  1 root root 0 Oct  1 15:18 cgroup.stat
-rw-r--r--  1 root root 0 Oct  1 15:17 cgroup.subtree_control
-rw-r--r--  1 root root 0 Oct  1 15:18 cgroup.threads
-rw-r--r--  1 root root 0 Oct  1 15:18 cpu.pressure
-r--r--r--  1 root root 0 Oct  1 15:18 cpu.stat
-r--r--r--  1 root root 0 Oct  1 15:18 cpuset.cpus.effective
-r--r--r--  1 root root 0 Oct  1 15:18 cpuset.mems.effective
drwxr-xr-x  2 root root 0 Oct  1 15:17 dev-hugepages.mount
drwxr-xr-x  2 root root 0 Oct  1 15:17 dev-mqueue.mount
drwxr-xr-x  2 root root 0 Oct  1 15:17 init.scope
-rw-r--r--  1 root root 0 Oct  1 15:18 io.cost.model
-rw-r--r--  1 root root 0 Oct  1 15:18 io.cost.qos
-rw-r--r--  1 root root 0 Oct  1 15:18 io.pressure
-rw-r--r--  1 root root 0 Oct  1 15:18 io.prio.class
-r--r--r--  1 root root 0 Oct  1 15:18 io.stat
-r--r--r--  1 root root 0 Oct  1 15:18 memory.numa_stat
-rw-r--r--  1 root root 0 Oct  1 15:18 memory.pressure
-r--r--r--  1 root root 0 Oct  1 15:18 memory.stat
-r--r--r--  1 root root 0 Oct  1 15:18 misc.capacity
drwxr-xr-x  2 root root 0 Oct  1 15:17 sys-fs-fuse-connections.mount
drwxr-xr-x  2 root root 0 Oct  1 15:17 sys-kernel-config.mount
drwxr-xr-x  2 root root 0 Oct  1 15:17 sys-kernel-debug.mount
drwxr-xr-x  2 root root 0 Oct  1 15:17 sys-kernel-tracing.mount
drwxr-xr-x 37 root root 0 Oct  1 15:23 system.slice
drwxr-xr-x  3 root root 0 Oct  1 15:18 user.slice
```

## Example of Manual cgroup use

1. Create a script file *test.sh* with the next code:

    ```console
    #!/bin/sh
    while [ 1 ]; do
           echo "hello world"
           sleep 60
    done
    ```

2. Create a new object *foo* manually inside of the *cgroup* hierarchy.

    ```console
    sudo mkdir /sys/fs/cgroup/memory/foo
    ```

3. Echo 50 MBytes into the *limit in bytes* option sets the maximum limit of memory for anything that is in the fod group.

    ```console
    echo 50000000 | sudo tee /sys/fs/cgroup/memory/foo/memory.limit_in_bytes 
    ```

4. The exact value that is set can be determined using the *cat* command. It should be noted that it is not exactly *50000000* because the architecture is a multiple of *4096*.

    ```console
    sudo cat /sys/fs/cgroup/memory/foo/memory.limit_in_bytes 
    ```

5. Recover de Process ID because that is the major mechanism that we use to add things to a *cgroup*

    ```console
    sh ./test.sh &
    ```

6. The PID (e.g., `15606`) above is associated with the *foo* object:

    ```console
    echo 15606 | sudo tee /sys/fs/cgroup/memory/foo/cgroup.procs 
    ```

7. The *ps* command is used to find out the *cgroups* associated with the previous process (e.g., `15606`):

    ```console
    ps -o cgroup 15606
    ```

    *Output*:

    ```console
    CGROUP
    11:blkio:/user.slice,9:pids:/user.slice/user-1000.slice/session-1.scope,8:cpu,cpuacct:/user.slice,7:memory:/foo,5:devices:/use
    ```

8. Process memory consumption can be checked:

    ```console
    sudo cat /sys/fs/cgroup/memory/foo/memory.usage_in_bytes
    ```

## cgroup Example using libcgroup

In the previous example, an object was created on top of an existing *cgroup*. In this example, the *cgroups* are created directly to run directly on applications.

1. Install `cgroup-tools`

    ```console
    sudo apt-get update 
    sudo apt-get install cgroup-tools
    ```

2. Create a *cgroup* in the *cpu* controller

    ```console
    sudo cgcreate -g cpu:A
    sudo cgcreate -g cpu:B
    ```

3. Get the number of cpu shares for cgroup and it comes back as 1024 which is the maximum number of CPU time slots for that particular aplication:

    ```console
    cgget -r cpu.shares A
    cgget -r cpu.shares B
    ```

    - *Output* for A:

    ```console
    A:
    cpu.shares: 1024
    ```

    - *Output* for B:

    ```console
    B:
    cpu.shares: 1024
    ```

4. Create two processes and assign one to each group:

    ```console
    sudo cgexec -g cpu:A dd if=/dev/zero of=/dev/null &
    sudo cgexec -g cpu:B dd if=/dev/zero of=/dev/null &
    ```

5. To verify the processes the `top` command can be used. They should get an equal CPU time:

    ```console
        PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND                                                            
      89641 root      20   0    5520    712    644 R  93.7   0.0   0:35.71 dd                                                                 
      89508 root      20   0    5520    708    644 R  93.0   0.0   0:41.09 dd   
    ```

6. Next, change the CPU values and check again:

    ```console
    sudo cgset -r cpu.shares=768 A
    sudo cgset -r cpu.shares=256 B
    ```

7. When the processes are verified using the `top` command. They should get different CPU time:

    ```console
        PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND                                                            
      89508 root      20   0    5520    708    644 R  97.7   0.0   5:06.05 dd                                                                 
      89641 root      20   0    5520    712    644 R  93.7   0.0   4:59.44 dd 
    ```

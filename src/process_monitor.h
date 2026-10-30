#ifndef PROCESS_MONITOR_H
#define PROCESS_MONITOR_H

#include <sys/types.h>

typedef struct {
    pid_t pid;
    pid_t ppid;
    char state[32];
    long vm_size_kb;
    long vm_rss_kb;
    int threads;
    int open_fds;
    unsigned long utime_ticks;
    unsigned long stime_ticks;
} ProcessInfo;

int process_monitor_read(pid_t pid, ProcessInfo *info);
pid_t process_monitor_find_child(pid_t parent_pid);

#endif

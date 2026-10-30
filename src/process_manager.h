#ifndef PROCESS_MANAGER_H
#define PROCESS_MANAGER_H

#include <sys/types.h>
#include "process_monitor.h"

typedef struct {
    pid_t pid;
    pid_t target_pid;
    int status;
    int exited_normally;
    int exit_code;
    int terminated_by_signal;
    int signal_number;
    ProcessInfo monitor_snapshot;
    int monitor_snapshot_valid;
    long peak_vm_size_kb;
    long peak_vm_rss_kb;
    int peak_threads;
    int peak_open_fds;
    int sample_count;
    double elapsed_ms;
} ProcessResult;

int process_manager_run(const char *program, const char *trace_file,
                        ProcessResult *result);

#endif

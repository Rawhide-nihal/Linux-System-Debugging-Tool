#ifndef PROCESS_MANAGER_H
#define PROCESS_MANAGER_H

#include <sys/types.h>
#include "process_monitor.h"

typedef struct {
    pid_t pid;
    int status;
    int exited_normally;
    int exit_code;
    int terminated_by_signal;
    int signal_number;
    ProcessInfo monitor_snapshot;
    int monitor_snapshot_valid;
} ProcessResult;

int process_manager_run(const char *program, const char *trace_file,
                        ProcessResult *result);

#endif

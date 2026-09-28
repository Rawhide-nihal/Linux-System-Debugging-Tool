#include "debugger.h"
#include "process_manager.h"
#include "process_monitor.h"
#include "tracer.h"
#include "error_analyzer.h"
#include "logger.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void print_header(void)
{
    printf("========================================\n");
    printf("      LINUX SYSTEM DEBUGGING TOOL\n");
    printf("========================================\n\n");
}

int debugger_run(const char *program, int use_trace)
{
    char trace_file[512] = {0};
    char result_file[512] = {0};

    snprintf(trace_file, sizeof(trace_file), "logs/trace_%ld.txt", (long)getpid());
    snprintf(result_file, sizeof(result_file), "results/report_%ld.txt", (long)getpid());

    print_header();
    printf("Target Program : %s\n", program);
    printf("Tracing        : %s\n\n", use_trace ? "Enabled" : "Disabled");

    if (use_trace && !tracer_available()) {
        fprintf(stderr, "strace was not found. Install it with: sudo apt install strace\n");
        return 1;
    }

    ProcessResult result;
    ProcessInfo info;

    if (process_manager_run(program, use_trace ? trace_file : NULL, &result) < 0) {
        perror("process execution");
        return 1;
    }

    printf("Debugger PID   : %d\n", (int)getpid());
    printf("Child PID      : %d\n\n", (int)result.pid);

    if (result.monitor_snapshot_valid) {
        info = result.monitor_snapshot;
        printf("Process PPID   : %d\n", (int)info.ppid);
        printf("Process state  : %s\n", info.state[0] ? info.state : "unavailable");
        printf("VmSize (KB)    : %ld\n", info.vm_size_kb);
        printf("VmRSS (KB)     : %ld\n", info.vm_rss_kb);
    }

    printf("\n========================================\n");
    printf("          PROCESS ANALYSIS\n");
    printf("========================================\n");

    if (result.exited_normally) {
        printf("Termination    : Normal\n");
        printf("Exit Status    : %d\n", result.exit_code);
    } else if (result.terminated_by_signal) {
        printf("Termination    : Abnormal\n");
        printf("Signal         : %d (%s)\n",
               result.signal_number,
               signal_description(result.signal_number));
    }

    char summary[256] = {0};
    char syscall_name[128] = {0};
    char error_name[128] = {0};
    int error_code = -1;

    int found_error = 0;
    if (use_trace) {
        found_error = tracer_analyze_file(trace_file, summary, sizeof(summary),
                                          syscall_name, sizeof(syscall_name),
                                          &error_code, error_name,
                                          sizeof(error_name));
    }


    printf("\n========================================\n");
    printf("          ERROR ANALYSIS\n");
    printf("========================================\n");

    if (found_error > 0) {
        printf("System Call    : %s()\n", syscall_name);
        printf("Return Value   : -1\n");
        printf("errno          : %d\n", error_code);
        printf("Error          : %s\n", error_name);
        printf("Description    : %s\n", error_description(error_code));
    } else if (result.terminated_by_signal) {
        printf("Abnormal process termination detected.\n");
        printf("Signal         : %s\n", signal_description(result.signal_number));
    } else {
        printf("No failed system call identified.\n");
    }

    if (use_trace) {
        printf("\nTrace File     : %s\n", trace_file);
    }

    if (logger_write_report(result_file, program, result.pid,
                            result.exited_normally, result.exit_code,
                            result.signal_number, syscall_name, error_code,
                            error_name) == 0) {
        printf("Report File    : %s\n", result_file);
    }

    printf("========================================\n");
    return 0;
}

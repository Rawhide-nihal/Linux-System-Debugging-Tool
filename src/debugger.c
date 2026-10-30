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

static void write_json_escaped(FILE *fp, const char *s)
{
    fputc('"', fp);
    if (s) {
        for (; *s; ++s) {
            unsigned char c = (unsigned char)*s;
            if (c == '"') fputs("\\\"", fp);
            else if (c == '\\') fputs("\\\\", fp);
            else if (c == '\n') fputs("\\n", fp);
            else if (c == '\r') fputs("\\r", fp);
            else if (c == '\t') fputs("\\t", fp);
            else if (c >= 32) fputc(c, fp);
        }
    }
    fputc('"', fp);
}

static void write_json_summary(const char *json_path,
                               const char *program,
                               int use_trace,
                               int use_monitor,
                               const char *trace_file,
                               const char *result_file,
                               const ProcessResult *result,
                               const TraceSummary *ts,
                               int found_error,
                               const char *syscall_name,
                               int error_code,
                               const char *error_name)
{
    if (!json_path || !json_path[0]) return;
    FILE *fp = fopen(json_path, "w");
    if (!fp) return;

    fprintf(fp, "{\n");
    fprintf(fp, "  \"engine\": \"ldst_c_debugger\",\n");
    fprintf(fp, "  \"program\": "); write_json_escaped(fp, program); fprintf(fp, ",\n");
    fprintf(fp, "  \"debugger_pid\": %d,\n", (int)getpid());
    fprintf(fp, "  \"child_pid\": %d,\n", (int)result->pid);
    fprintf(fp, "  \"target_pid\": %d,\n", (int)result->target_pid);
    fprintf(fp, "  \"tracing_enabled\": %s,\n", use_trace ? "true" : "false");
    fprintf(fp, "  \"monitoring_enabled\": %s,\n", use_monitor ? "true" : "false");
    fprintf(fp, "  \"elapsed_ms\": %.2f,\n", result->elapsed_ms);
    fprintf(fp, "  \"exited_normally\": %s,\n", result->exited_normally ? "true" : "false");
    fprintf(fp, "  \"exit_code\": %d,\n", result->exit_code);
    fprintf(fp, "  \"terminated_by_signal\": %s,\n", result->terminated_by_signal ? "true" : "false");
    fprintf(fp, "  \"signal_number\": %d,\n", result->signal_number);
    fprintf(fp, "  \"signal_name\": ");
    write_json_escaped(fp, result->terminated_by_signal ? signal_short_name(result->signal_number) : "");
    fprintf(fp, ",\n");
    fprintf(fp, "  \"signal_description\": ");
    write_json_escaped(fp, result->terminated_by_signal ? signal_description(result->signal_number) : "");
    fprintf(fp, ",\n");

    fprintf(fp, "  \"monitor_snapshot_valid\": %s,\n", (use_monitor && result->monitor_snapshot_valid) ? "true" : "false");
    fprintf(fp, "  \"ppid\": %d,\n", (use_monitor && result->monitor_snapshot_valid) ? (int)result->monitor_snapshot.ppid : 0);
    fprintf(fp, "  \"process_state\": ");
    write_json_escaped(fp, (use_monitor && result->monitor_snapshot_valid && result->monitor_snapshot.state[0])
                           ? result->monitor_snapshot.state : "Unavailable");
    fprintf(fp, ",\n");
    fprintf(fp, "  \"vm_size_kb\": %ld,\n", (use_monitor && result->monitor_snapshot_valid) ? result->monitor_snapshot.vm_size_kb : 0L);
    fprintf(fp, "  \"vm_rss_kb\": %ld,\n", (use_monitor && result->monitor_snapshot_valid) ? result->monitor_snapshot.vm_rss_kb : 0L);
    fprintf(fp, "  \"peak_vm_size_kb\": %ld,\n", use_monitor ? result->peak_vm_size_kb : 0L);
    fprintf(fp, "  \"peak_vm_rss_kb\": %ld,\n", use_monitor ? result->peak_vm_rss_kb : 0L);
    fprintf(fp, "  \"peak_threads\": %d,\n", use_monitor ? result->peak_threads : 0);
    fprintf(fp, "  \"peak_open_fds\": %d,\n", use_monitor ? result->peak_open_fds : -1);
    fprintf(fp, "  \"monitor_samples\": %d,\n", use_monitor ? result->sample_count : 0);

    fprintf(fp, "  \"total_syscalls\": %d,\n", use_trace ? ts->total_syscalls : 0);
    fprintf(fp, "  \"total_failed_syscalls\": %d,\n", use_trace ? ts->total_failures : 0);
    fprintf(fp, "  \"relevant_failed_syscalls\": %d,\n", use_trace ? ts->relevant_failures : 0);
    fprintf(fp, "  \"loader_noise_syscalls\": %d,\n", use_trace ? ts->loader_noise_failures : 0);
    fprintf(fp, "  \"found_error\": %s,\n", (found_error > 0) ? "true" : "false");
    fprintf(fp, "  \"failed_syscall\": "); write_json_escaped(fp, found_error > 0 ? syscall_name : ""); fprintf(fp, ",\n");
    fprintf(fp, "  \"errno_code\": %d,\n", found_error > 0 ? error_code : -1);
    fprintf(fp, "  \"errno_name\": "); write_json_escaped(fp, found_error > 0 ? error_name : ""); fprintf(fp, ",\n");
    fprintf(fp, "  \"errno_description\": ");
    write_json_escaped(fp, found_error > 0 ? error_description(error_code) : "");
    fprintf(fp, ",\n");
    fprintf(fp, "  \"primary_evidence\": ");
    write_json_escaped(fp, found_error > 0 ? ts->primary_evidence : "");
    fprintf(fp, ",\n");
    fprintf(fp, "  \"trace_file\": "); write_json_escaped(fp, use_trace ? trace_file : ""); fprintf(fp, ",\n");
    fprintf(fp, "  \"report_file\": "); write_json_escaped(fp, result_file); fprintf(fp, "\n");
    fprintf(fp, "}\n");

    fclose(fp);
}

int debugger_run_with_options(const DebuggerOptions *opts)
{
    if (!opts || !opts->program) return 1;

    mkdir("logs", 0755);
    mkdir("results", 0755);

    char trace_file[512] = {0};
    char result_file[512] = {0};

    if (opts->custom_trace_file && opts->custom_trace_file[0]) {
        snprintf(trace_file, sizeof(trace_file), "%s", opts->custom_trace_file);
    } else {
        snprintf(trace_file, sizeof(trace_file), "logs/trace_%ld.txt", (long)getpid());
    }

    if (opts->custom_report_file && opts->custom_report_file[0]) {
        snprintf(result_file, sizeof(result_file), "%s", opts->custom_report_file);
    } else {
        snprintf(result_file, sizeof(result_file), "results/report_%ld.txt", (long)getpid());
    }

    print_header();
    printf("Target Program : %s\n", opts->program);
    printf("Tracing        : %s\n\n", opts->use_trace ? "Enabled" : "Disabled");
    fflush(stdout);

    if (opts->use_trace && !tracer_available()) {
        fprintf(stderr, "strace was not found. Install it with: sudo apt install strace\n");
        return 1;
    }

    ProcessResult result;
    ProcessInfo info;

    if (process_manager_run(opts->program, opts->use_trace ? trace_file : NULL, &result) < 0) {
        perror("process execution");
        return 1;
    }

    char syscall_name[128] = {0};
    char error_name[128] = {0};
    int error_code = -1;
    TraceSummary ts;
    memset(&ts, 0, sizeof(ts));

    int found_error = 0;
    if (opts->use_trace) {
        found_error = tracer_analyze_detailed(trace_file, &ts);
        if (found_error > 0) {
            snprintf(syscall_name, sizeof(syscall_name), "%s", ts.primary_syscall);
            snprintf(error_name, sizeof(error_name), "%s", ts.primary_errno_name);
            error_code = ts.primary_errno_code;
        }
        if (!result.terminated_by_signal && ts.detected_signal > 0) {
            result.terminated_by_signal = 1;
            result.exited_normally = 0;
            result.signal_number = ts.detected_signal;
        }
    }

    printf("\nDebugger PID   : %d\n", (int)getpid());
    printf("Child PID      : %d\n", (int)result.target_pid);
    printf("Elapsed Time   : %.2f ms\n\n", result.elapsed_ms);

    if (opts->use_monitor && result.monitor_snapshot_valid) {
        info = result.monitor_snapshot;
        printf("Process PPID   : %d\n", (int)info.ppid);
        printf("Process state  : %s\n", info.state[0] ? info.state : "unavailable");
        printf("VmSize (KB)    : %ld (Peak: %ld)\n", info.vm_size_kb, result.peak_vm_size_kb);
        printf("VmRSS (KB)     : %ld (Peak: %ld)\n", info.vm_rss_kb, result.peak_vm_rss_kb);
        if (result.peak_threads > 0) {
            printf("Threads        : %d\n", result.peak_threads);
        }
        if (result.peak_open_fds >= 0) {
            printf("Open FDs       : %d\n", result.peak_open_fds);
        }
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

    if (opts->use_trace) {
        printf("\nTrace File     : %s\n", trace_file);
    }

    if (logger_write_report(result_file, opts->program, result.target_pid,
                            result.exited_normally, result.exit_code,
                            result.signal_number, syscall_name, error_code,
                            error_name) == 0) {
        printf("Report File    : %s\n", result_file);
    }

    if (opts->json_output_file && opts->json_output_file[0]) {
        write_json_summary(opts->json_output_file, opts->program,
                           opts->use_trace, opts->use_monitor,
                           trace_file, result_file,
                           &result, &ts, found_error,
                           syscall_name, error_code, error_name);
    }

    printf("========================================\n");
    fflush(stdout);
    return 0;
}

int debugger_run(const char *program, int use_trace)
{
    DebuggerOptions opts;
    memset(&opts, 0, sizeof(opts));
    opts.program = program;
    opts.use_trace = use_trace;
    opts.use_monitor = 1;
    return debugger_run_with_options(&opts);
}

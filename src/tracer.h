#ifndef TRACER_H
#define TRACER_H

typedef struct {
    int total_syscalls;
    int total_failures;
    int relevant_failures;
    int loader_noise_failures;
    char primary_syscall[128];
    char primary_errno_name[128];
    int primary_errno_code;
    char primary_evidence[512];
    int detected_signal;
    char detected_signal_name[64];
} TraceSummary;

int tracer_available(void);
int tracer_analyze_file(const char *trace_file, char *summary, int summary_size,
                        char *syscall_name, int syscall_size,
                        int *error_code, char *error_name, int error_name_size);
int tracer_analyze_detailed(const char *trace_file, TraceSummary *out);

#endif

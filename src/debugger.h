#ifndef DEBUGGER_H
#define DEBUGGER_H

typedef struct {
    const char *program;
    int use_trace;
    int use_monitor;
    const char *custom_trace_file;
    const char *custom_report_file;
    const char *json_output_file;
} DebuggerOptions;

int debugger_run(const char *program, int use_trace);
int debugger_run_with_options(const DebuggerOptions *opts);

#endif

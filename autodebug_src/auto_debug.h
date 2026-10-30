#ifndef AUTO_DEBUG_H
#define AUTO_DEBUG_H

typedef struct {
    const char *program;
    int enable_gdb;
    const char *custom_trace_file;
    const char *custom_report_file;
    const char *custom_gdb_file;
    const char *json_output_file;
} AutoDebugOptions;

int autodebug_run(const char *program);
int autodebug_run_with_options(const AutoDebugOptions *opts);

#endif

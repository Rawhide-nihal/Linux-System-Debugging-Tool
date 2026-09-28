#ifndef TRACER_H
#define TRACER_H

int tracer_available(void);
int tracer_analyze_file(const char *trace_file, char *summary, int summary_size,
                        char *syscall_name, int syscall_size,
                        int *error_code, char *error_name, int error_name_size);

#endif

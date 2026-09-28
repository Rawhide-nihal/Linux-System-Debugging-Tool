#ifndef LOGGER_H
#define LOGGER_H

int logger_write_report(const char *result_file,
                        const char *program,
                        int pid,
                        int normal_exit,
                        int exit_code,
                        int signal_number,
                        const char *syscall_name,
                        int error_code,
                        const char *error_name);

#endif

#include "logger.h"
#include "error_analyzer.h"

#include <stdio.h>
#include <time.h>

int logger_write_report(const char *result_file,
                        const char *program,
                        int pid,
                        int normal_exit,
                        int exit_code,
                        int signal_number,
                        const char *syscall_name,
                        int error_code,
                        const char *error_name)
{
    FILE *fp = fopen(result_file, "w");
    if (!fp) return -1;

    time_t now = time(NULL);
    char *stamp = ctime(&now);

    fprintf(fp, "LINUX SYSTEM DEBUGGING TOOL REPORT\n");
    fprintf(fp, "===================================\n");
    fprintf(fp, "Program: %s\n", program);
    fprintf(fp, "PID: %d\n", pid);
    if (stamp) fprintf(fp, "Time: %s", stamp);

    fprintf(fp, "\nPROCESS RESULT\n");
    fprintf(fp, "--------------\n");
    if (normal_exit) {
        fprintf(fp, "Termination: Normal\n");
        fprintf(fp, "Exit status: %d\n", exit_code);
    } else {
        fprintf(fp, "Termination: Abnormal\n");
        fprintf(fp, "Signal: %d (%s)\n", signal_number,
                signal_description(signal_number));
    }

    fprintf(fp, "\nSYSTEM CALL ANALYSIS\n");
    fprintf(fp, "--------------------\n");
    if (syscall_name && syscall_name[0]) {
        fprintf(fp, "System call: %s()\n", syscall_name);
        fprintf(fp, "Return value: -1\n");
        fprintf(fp, "errno: %d\n", error_code);
        fprintf(fp, "Error name: %s\n", error_name);
        fprintf(fp, "Description: %s\n", error_description(error_code));
    } else {
        fprintf(fp, "No failed system call was identified in the trace.\n");
    }

    fclose(fp);
    return 0;
}

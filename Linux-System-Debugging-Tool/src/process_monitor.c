#include "process_monitor.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int process_monitor_read(pid_t pid, ProcessInfo *info)
{
    if (!info) return -1;
    memset(info, 0, sizeof(*info));
    info->pid = pid;

    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/status", pid);

    FILE *fp = fopen(path, "r");
    if (!fp) return -1;

    char line[256];
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "PPid:", 5) == 0) {
            info->ppid = (pid_t)strtol(line + 5, NULL, 10);
        } else if (strncmp(line, "State:", 6) == 0) {
            char state_code = '\0';
            if (sscanf(line + 6, " %c", &state_code) == 1) {
                snprintf(info->state, sizeof(info->state), "%c", state_code);
            }
        } else if (strncmp(line, "VmSize:", 7) == 0) {
            info->vm_size_kb = strtol(line + 7, NULL, 10);
        } else if (strncmp(line, "VmRSS:", 6) == 0) {
            info->vm_rss_kb = strtol(line + 6, NULL, 10);
        }
    }

    fclose(fp);
    return 0;
}

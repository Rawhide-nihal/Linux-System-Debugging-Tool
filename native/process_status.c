/*
 * Linux System Debugging Tool - Native Process Status Collector
 * Inspects real /proc/<pid> metrics on Linux systems.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef struct {
    int pid;
    char state;
    long ppid;
    unsigned long vm_size_kb;
    unsigned long vm_rss_kb;
    unsigned long threads_count;
    unsigned long utime_ticks;
    unsigned long stime_ticks;
    char name[64];
} LinuxProcessInfo;

int inspect_proc_status(int pid, LinuxProcessInfo *info) {
    if (!info || pid <= 0) return -1;
    memset(info, 0, sizeof(LinuxProcessInfo));
    info->pid = pid;

    char path[128];
    snprintf(path, sizeof(path), "/proc/%d/status", pid);

    FILE *f = fopen(path, "r");
    if (!f) return -1;

    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "Name:\t", 6) == 0) {
            sscanf(line + 6, "%63s", info->name);
        } else if (strncmp(line, "State:\t", 7) == 0) {
            info->state = line[7];
        } else if (strncmp(line, "PPid:\t", 6) == 0) {
            sscanf(line + 6, "%ld", &info->ppid);
        } else if (strncmp(line, "VmSize:\t", 8) == 0) {
            sscanf(line + 8, "%lu", &info->vm_size_kb);
        } else if (strncmp(line, "VmRSS:\t", 7) == 0) {
            sscanf(line + 7, "%lu", &info->vm_rss_kb);
        } else if (strncmp(line, "Threads:\t", 9) == 0) {
            sscanf(line + 9, "%lu", &info->threads_count);
        }
    }
    fclose(f);
    return 0;
}

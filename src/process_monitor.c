#define _POSIX_C_SOURCE 200809L
#include "process_monitor.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int count_open_fds(pid_t pid)
{
    char fd_path[64];
    snprintf(fd_path, sizeof(fd_path), "/proc/%d/fd", (int)pid);
    DIR *dir = opendir(fd_path);
    if (!dir) return -1;

    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] != '.') {
            count++;
        }
    }
    closedir(dir);
    return count;
}

static void read_cpu_ticks(pid_t pid, unsigned long *utime, unsigned long *stime)
{
    *utime = 0;
    *stime = 0;

    char stat_path[64];
    snprintf(stat_path, sizeof(stat_path), "/proc/%d/stat", (int)pid);
    FILE *fp = fopen(stat_path, "r");
    if (!fp) return;

    char buf[1024];
    if (fgets(buf, sizeof(buf), fp)) {
        /* /proc/[pid]/stat field 2 (comm) is inside parentheses and may contain spaces.
           Find the last ')' and parse fields starting at field 3 (state). */
        char *rparen = strrchr(buf, ')');
        if (rparen && rparen[1] == ' ') {
            char *p = rparen + 2;
            /* Field 3 is index 0 from p; utime is field 14 (index 11), stime is field 15 (index 12) */
            char *saveptr = NULL;
            char *tok = strtok_r(p, " ", &saveptr);
            int idx = 3;
            while (tok) {
                if (idx == 14) {
                    *utime = strtoul(tok, NULL, 10);
                } else if (idx == 15) {
                    *stime = strtoul(tok, NULL, 10);
                    break;
                }
                idx++;
                tok = strtok_r(NULL, " ", &saveptr);
            }
        }
    }
    fclose(fp);
}

pid_t process_monitor_find_child(pid_t parent_pid)
{
    char children_path[128];
    snprintf(children_path, sizeof(children_path),
             "/proc/%d/task/%d/children", (int)parent_pid, (int)parent_pid);
    FILE *fp = fopen(children_path, "r");
    if (fp) {
        int child = 0;
        if (fscanf(fp, "%d", &child) == 1 && child > 0) {
            fclose(fp);
            return (pid_t)child;
        }
        fclose(fp);
    }
    return 0;
}

int process_monitor_read(pid_t pid, ProcessInfo *info)
{
    if (!info || pid <= 0) return -1;
    memset(info, 0, sizeof(*info));
    info->pid = pid;
    info->open_fds = -1;

    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/status", (int)pid);

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
        } else if (strncmp(line, "Threads:", 8) == 0) {
            info->threads = (int)strtol(line + 8, NULL, 10);
        }
    }

    fclose(fp);

    info->open_fds = count_open_fds(pid);
    read_cpu_ticks(pid, &info->utime_ticks, &info->stime_ticks);
    return 0;
}

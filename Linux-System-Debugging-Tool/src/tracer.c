#include "tracer.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int tracer_available(void)
{
    return access("/usr/bin/strace", X_OK) == 0 ||
           access("/bin/strace", X_OK) == 0;
}

static void copy_token(char *dst, int size, const char *src, int n)
{
    if (size <= 0) return;
    if (n >= size) n = size - 1;
    memcpy(dst, src, (size_t)n);
    dst[n] = '\0';
}

int tracer_analyze_file(const char *trace_file, char *summary, int summary_size,
                        char *syscall_name, int syscall_size,
                        int *error_code, char *error_name, int error_name_size)
{
    if (!trace_file || !summary || !syscall_name || !error_code || !error_name)
        return -1;

    FILE *fp = fopen(trace_file, "r");
    if (!fp) return -1;

    char line[4096];
    int found = 0;

    while (fgets(line, sizeof(line), fp)) {
        char *eq = strstr(line, "= -1 ");
        if (!eq) continue;

        char err[128] = {0};
        if (sscanf(eq + 5, "%127[A-Z0-9_]", err) != 1)
            continue;

        char *lp = strchr(line, '(');
        if (!lp) continue;

        /* strace may prefix each line with a PID, for example:
           "1234  openat(...) = -1 ENOENT". Strip that prefix. */
        char *name_start = line;
        while (*name_start == ' ' || *name_start == '\t') name_start++;
        char *prefix_end = name_start;
        while (*prefix_end >= '0' && *prefix_end <= '9') prefix_end++;
        if (prefix_end != name_start) {
            while (*prefix_end == ' ' || *prefix_end == '\t') prefix_end++;
            name_start = prefix_end;
        }

        int name_len = (int)(lp - name_start);
        while (name_len > 0 && (name_start[name_len - 1] == ' ' ||
                                name_start[name_len - 1] == '\t'))
            name_len--;
        if (name_len <= 0 || name_len >= syscall_size)
            continue;

        copy_token(syscall_name, syscall_size, name_start, name_len);

        /* Ignore common dynamic-loader/environment probing noise.
           For example, access("/etc/ld.so.preload", ...) may legitimately
           return ENOENT during startup and is not an application failure. */
        if (strcmp(syscall_name, "access") == 0 && strcmp(err, "ENOENT") == 0)
            continue;

        if (strcmp(err, "ENOENT") == 0 && strcmp(syscall_name, "unlink") == 0)
            continue;

        snprintf(error_name, (size_t)error_name_size, "%s", err);

        if (strcmp(err, "ENOENT") == 0) *error_code = 2;
        else if (strcmp(err, "EACCES") == 0) *error_code = 13;
        else if (strcmp(err, "EBADF") == 0) *error_code = 9;
        else if (strcmp(err, "EINVAL") == 0) *error_code = 22;
        else if (strcmp(err, "EISDIR") == 0) *error_code = 21;
        else if (strcmp(err, "ENOTDIR") == 0) *error_code = 20;
        else if (strcmp(err, "EEXIST") == 0) *error_code = 17;
        else *error_code = -1;

        snprintf(summary, (size_t)summary_size,
                 "Failed system call detected: %s() returned -1 (%s).",
                 syscall_name, err);
        found = 1;
        break;
    }

    if (!found) {
        syscall_name[0] = 0;
        error_name[0] = 0;
        *error_code = -1;
        summary[0] = 0;
    }

    fclose(fp);
    return found;
}

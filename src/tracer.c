#include "tracer.h"
#include "error_analyzer.h"

#include <ctype.h>
#include <errno.h>
#include <signal.h>
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

static int is_loader_or_cleanup_noise(const char *syscall_name, const char *err, const char *line)
{
    if (strcmp(syscall_name, "access") == 0 && strcmp(err, "ENOENT") == 0 &&
        strstr(line, "/etc/ld.so.preload") != NULL) {
        return 1;
    }
    if (strcmp(err, "ENOENT") == 0 &&
        (strstr(line, "/etc/ld.so.") != NULL ||
         strstr(line, "glibc-hwcaps") != NULL ||
         strstr(line, "/tls/") != NULL)) {
        return 1;
    }
    if (strcmp(syscall_name, "unlink") == 0 && strcmp(err, "ENOENT") == 0) {
        return 1;
    }
    return 0;
}

static void check_trace_signal(const char *line, TraceSummary *out)
{
    if (strstr(line, "+++ killed by SIG") || strstr(line, "--- SIG")) {
        const struct { const char *name; int sig; } sigs[] = {
            {"SIGSEGV", SIGSEGV},
            {"SIGABRT", SIGABRT},
            {"SIGFPE",  SIGFPE},
            {"SIGILL",  SIGILL},
            {"SIGBUS",  SIGBUS},
            {"SIGTERM", SIGTERM},
            {"SIGINT",  SIGINT},
            {"SIGKILL", SIGKILL},
            {"SIGPIPE", SIGPIPE},
            {"SIGALRM", SIGALRM},
            {"SIGQUIT", SIGQUIT}
        };
        for (size_t i = 0; i < sizeof(sigs) / sizeof(sigs[0]); ++i) {
            if (strstr(line, sigs[i].name)) {
                out->detected_signal = sigs[i].sig;
                snprintf(out->detected_signal_name, sizeof(out->detected_signal_name),
                         "%s", sigs[i].name);
                break;
            }
        }
    }
}

int tracer_analyze_detailed(const char *trace_file, TraceSummary *out)
{
    if (!trace_file || !out) return -1;
    memset(out, 0, sizeof(*out));
    out->primary_errno_code = -1;

    FILE *fp = fopen(trace_file, "r");
    if (!fp) return -1;

    char line[4096];
    int found_relevant = 0;

    while (fgets(line, sizeof(line), fp)) {
        /* Trim trailing newline */
        size_t len = strlen(line);
        while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
            line[--len] = '\0';
        }

        check_trace_signal(line, out);

        char *lp = strchr(line, '(');
        if (!lp) continue;

        /* Extract syscall name */
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
        if (name_len <= 0 || name_len >= 128) continue;

        /* Verify valid identifier characters in syscall_name */
        int valid_name = 1;
        for (int i = 0; i < name_len; ++i) {
            unsigned char c = (unsigned char)name_start[i];
            if (!(isalnum(c) || c == '_')) {
                valid_name = 0;
                break;
            }
        }
        if (!valid_name) continue;

        out->total_syscalls++;

        char *eq = strstr(line, "= -1 ");
        if (!eq) continue;

        char err[128] = {0};
        if (sscanf(eq + 5, "%127[A-Z0-9_]", err) != 1)
            continue;

        char sc_name[128] = {0};
        copy_token(sc_name, sizeof(sc_name), name_start, name_len);

        out->total_failures++;

        if (is_loader_or_cleanup_noise(sc_name, err, line)) {
            out->loader_noise_failures++;
            continue;
        }

        out->relevant_failures++;
        /* Record the latest relevant application failure */
        snprintf(out->primary_syscall, sizeof(out->primary_syscall), "%s", sc_name);
        snprintf(out->primary_errno_name, sizeof(out->primary_errno_name), "%s", err);
        out->primary_errno_code = error_code_from_name(err);
        snprintf(out->primary_evidence, sizeof(out->primary_evidence), "%.*s",
                 (int)sizeof(out->primary_evidence) - 1, line);
        found_relevant = 1;
    }

    fclose(fp);
    return found_relevant;
}

int tracer_analyze_file(const char *trace_file, char *summary, int summary_size,
                        char *syscall_name, int syscall_size,
                        int *error_code, char *error_name, int error_name_size)
{
    if (!trace_file || !summary || !syscall_name || !error_code || !error_name)
        return -1;

    TraceSummary ts;
    int found = tracer_analyze_detailed(trace_file, &ts);
    if (found < 0) return -1;

    if (found > 0) {
        snprintf(syscall_name, (size_t)syscall_size, "%s", ts.primary_syscall);
        snprintf(error_name, (size_t)error_name_size, "%s", ts.primary_errno_name);
        *error_code = ts.primary_errno_code;
        snprintf(summary, (size_t)summary_size,
                 "Failed system call detected: %s() returned -1 (%s).",
                 syscall_name, error_name);
        return 1;
    }

    syscall_name[0] = '\0';
    error_name[0] = '\0';
    *error_code = -1;
    summary[0] = '\0';
    return 0;
}

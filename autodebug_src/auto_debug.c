#define _GNU_SOURCE
#include "auto_debug.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_TRACE_FILE "logs/autodebug_trace.txt"
#define DEFAULT_REPORT_FILE "results/autodebug_report.txt"
#define DEFAULT_GDB_FILE "logs/autodebug_gdb.txt"
#define MAX_LINE 4096
#define MAX_TEXT 2048

typedef struct {
    char syscall[64];
    char errno_name[64];
    int errno_code;
    char meaning[160];
    char evidence[MAX_TEXT];
} Failure;

typedef struct {
    pid_t pid;
    pid_t ppid;
    char state[16];
    long peak_vm_size_kb;
    long peak_vm_rss_kb;
    int peak_threads;
    int peak_open_fds;
    int samples;
    double elapsed_ms;
} AutoProcStats;

static int tool_exists(const char *bin_name)
{
    char p1[128], p2[128];
    snprintf(p1, sizeof(p1), "/usr/bin/%s", bin_name);
    snprintf(p2, sizeof(p2), "/bin/%s", bin_name);
    return access(p1, X_OK) == 0 || access(p2, X_OK) == 0;
}

static const char *errno_meaning(const char *e, int *code)
{
    struct { const char *n; int c; const char *m; } map[] = {
        {"EPERM",        1,   "Operation not permitted"},
        {"ENOENT",       2,   "No such file or directory"},
        {"ESRCH",        3,   "No such process"},
        {"EINTR",        4,   "Interrupted system call"},
        {"EIO",          5,   "Input/output error"},
        {"ENXIO",        6,   "No such device or address"},
        {"E2BIG",        7,   "Argument list too long"},
        {"ENOEXEC",      8,   "Exec format error"},
        {"EBADF",        9,   "Bad file descriptor"},
        {"ECHILD",       10,  "No child processes"},
        {"EAGAIN",       11,  "Resource temporarily unavailable"},
        {"ENOMEM",       12,  "Cannot allocate memory"},
        {"EACCES",       13,  "Permission denied"},
        {"EFAULT",       14,  "Bad address"},
        {"EBUSY",        16,  "Device or resource busy"},
        {"EEXIST",       17,  "File exists"},
        {"EXDEV",        18,  "Invalid cross-device link"},
        {"ENODEV",       19,  "No such device"},
        {"ENOTDIR",      20,  "Not a directory"},
        {"EISDIR",       21,  "Is a directory"},
        {"EINVAL",       22,  "Invalid argument"},
        {"ENFILE",       23,  "Too many open files in system"},
        {"EMFILE",       24,  "Too many open files"},
        {"ENOSPC",       28,  "No space left on device"},
        {"ESPIPE",       29,  "Illegal seek"},
        {"EROFS",        30,  "Read-only file system"},
        {"EPIPE",        32,  "Broken pipe"},
        {"ERANGE",       34,  "Numerical result out of range"},
        {"ENAMETOOLONG", 36,  "File name too long"},
        {"ENOSYS",       38,  "Function not implemented"},
        {"ENOTEMPTY",    39,  "Directory not empty"},
        {"ELOOP",        40,  "Too many levels of symbolic links"},
        {"EADDRINUSE",   98,  "Address already in use"},
        {"ECONNRESET",   104, "Connection reset by peer"},
        {"ETIMEDOUT",    110, "Connection timed out"},
        {"ECONNREFUSED", 111, "Connection refused"}
    };
    for (size_t i = 0; i < sizeof(map) / sizeof(map[0]); ++i) {
        if (strcmp(e, map[i].n) == 0) {
            if (code) *code = map[i].c;
            return map[i].m;
        }
    }
    if (code) *code = -1;
    return "Linux reported an error for this system call";
}

static int is_noise(const char *syscall, const char *err, const char *line)
{
    if (strcmp(syscall, "access") == 0 && strcmp(err, "ENOENT") == 0 &&
        strstr(line, "/etc/ld.so.preload") != NULL) {
        return 1;
    }
    if (strcmp(err, "ENOENT") == 0 &&
        (strstr(line, "/etc/ld.so.") != NULL ||
         strstr(line, "glibc-hwcaps") != NULL ||
         strstr(line, "/tls/") != NULL)) {
        return 1;
    }
    if (strcmp(syscall, "unlink") == 0 && strcmp(err, "ENOENT") == 0) {
        return 1;
    }
    return 0;
}

static int extract_syscall(const char *line, char *out, size_t n)
{
    const char *lp = strchr(line, '(');
    if (!lp) return 0;
    const char *end = lp;
    while (end > line && isspace((unsigned char)end[-1])) --end;
    const char *start = end;
    while (start > line && !isspace((unsigned char)start[-1])) --start;
    if (start == end) return 0;
    size_t len = (size_t)(end - start);
    if (len >= n) len = n - 1;
    for (size_t i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)start[i];
        if (!(isalnum(c) || c == '_')) return 0;
    }
    memcpy(out, start, len);
    out[len] = '\0';
    return 1;
}

static int parse_failed_call(const char *line, Failure *f, int *is_loader_noise)
{
    if (is_loader_noise) *is_loader_noise = 0;
    const char *marker = strstr(line, "= -1");
    if (!marker) marker = strstr(line, "=-1");
    if (!marker) return 0;
    const char *minus = strstr(marker, "-1");
    if (!minus) return 0;
    const char *p = minus + 2;
    while (*p && isspace((unsigned char)*p)) ++p;
    char err[64] = {0};
    size_t i = 0;
    while (*p && (isalnum((unsigned char)*p) || *p == '_') && i < sizeof(err) - 1)
        err[i++] = *p++;
    err[i] = '\0';
    if (!i || !isupper((unsigned char)err[0])) return 0;
    if (!extract_syscall(line, f->syscall, sizeof(f->syscall))) return 0;
    if (is_noise(f->syscall, err, line)) {
        if (is_loader_noise) *is_loader_noise = 1;
        return 0;
    }
    snprintf(f->errno_name, sizeof(f->errno_name), "%s", err);
    f->errno_code = -1;
    snprintf(f->meaning, sizeof(f->meaning), "%s", errno_meaning(err, &f->errno_code));
    snprintf(f->evidence, sizeof(f->evidence), "%.*s", (int)sizeof(f->evidence) - 1, line);
    size_t ev_len = strlen(f->evidence);
    while (ev_len > 0 && (f->evidence[ev_len - 1] == '\n' || f->evidence[ev_len - 1] == '\r')) {
        f->evidence[--ev_len] = '\0';
    }
    return 1;
}

static int parse_signal(const char *line, int *sig, char *name, size_t n)
{
    if (!strstr(line, "+++ killed by SIG") && !strstr(line, "--- SIG")) return 0;
    const char *names[] = {"SIGSEGV", "SIGABRT", "SIGFPE", "SIGTERM", "SIGINT", "SIGILL", "SIGBUS", "SIGKILL", "SIGPIPE"};
    int nums[] = {SIGSEGV, SIGABRT, SIGFPE, SIGTERM, SIGINT, SIGILL, SIGBUS, SIGKILL, SIGPIPE};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        if (strstr(line, names[i])) {
            *sig = nums[i];
            snprintf(name, n, "%s", names[i]);
            return 1;
        }
    }
    return 0;
}

static void explain_errno(const Failure *f, char *diagnosis, size_t dn, char *next, size_t nn)
{
    if (strcmp(f->errno_name, "ENOENT") == 0) {
        snprintf(diagnosis, dn, "The %s() system call failed because the requested file, directory, or path component was not found.", f->syscall);
        snprintf(next, nn, "Check the path, filename spelling/case, current working directory, and whether the required file or directory exists.");
    } else if (strcmp(f->errno_name, "EACCES") == 0 || strcmp(f->errno_name, "EPERM") == 0) {
        snprintf(diagnosis, dn, "Linux denied the %s() operation because the process does not have the required permission.", f->syscall);
        snprintf(next, nn, "Check file/directory permissions, ownership, and the user running the program.");
    } else if (strcmp(f->errno_name, "EBADF") == 0) {
        snprintf(diagnosis, dn, "The %s() system call used an invalid or already-closed file descriptor.", f->syscall);
        snprintf(next, nn, "Trace where the descriptor is opened, stored, used, and closed. Ensure a valid descriptor reaches the failing call.");
    } else if (strcmp(f->errno_name, "EINVAL") == 0) {
        snprintf(diagnosis, dn, "The %s() system call received an argument that is invalid for the requested operation.", f->syscall);
        snprintf(next, nn, "Inspect the arguments passed to the failing system call and compare them with the Linux API requirements.");
    } else {
        snprintf(diagnosis, dn, "The %s() system call failed with %s (%d): %s.", f->syscall, f->errno_name, f->errno_code, f->meaning);
        snprintf(next, nn, "Inspect the arguments and program state around the failing system call. Use the trace as evidence for the next debugging step.");
    }
}

static void sample_proc_stats(pid_t root_pid, AutoProcStats *stats)
{
    pid_t target = root_pid;
    char ch_path[128];
    snprintf(ch_path, sizeof(ch_path), "/proc/%d/task/%d/children", (int)root_pid, (int)root_pid);
    FILE *cf = fopen(ch_path, "r");
    if (cf) {
        int cpid = 0;
        if (fscanf(cf, "%d", &cpid) == 1 && cpid > 0) {
            target = (pid_t)cpid;
            stats->pid = target;
        }
        fclose(cf);
    }

    char status_path[64];
    snprintf(status_path, sizeof(status_path), "/proc/%d/status", (int)target);
    FILE *fp = fopen(status_path, "r");
    if (!fp) return;

    long vmsize = 0, vmrss = 0;
    int threads = 0;
    char line[256];
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, "PPid:", 5) == 0) {
            stats->ppid = (pid_t)strtol(line + 5, NULL, 10);
        } else if (strncmp(line, "State:", 6) == 0) {
            char sc = '\0';
            if (sscanf(line + 6, " %c", &sc) == 1) {
                stats->state[0] = sc;
                stats->state[1] = '\0';
            }
        } else if (strncmp(line, "VmSize:", 7) == 0) {
            vmsize = strtol(line + 7, NULL, 10);
        } else if (strncmp(line, "VmRSS:", 6) == 0) {
            vmrss = strtol(line + 6, NULL, 10);
        } else if (strncmp(line, "Threads:", 8) == 0) {
            threads = (int)strtol(line + 8, NULL, 10);
        }
    }
    fclose(fp);

    if (vmsize > 0) {
        stats->samples++;
        if (vmsize > stats->peak_vm_size_kb) stats->peak_vm_size_kb = vmsize;
        if (vmrss > stats->peak_vm_rss_kb) stats->peak_vm_rss_kb = vmrss;
        if (threads > stats->peak_threads) stats->peak_threads = threads;

        char fd_path[64];
        snprintf(fd_path, sizeof(fd_path), "/proc/%d/fd", (int)target);
        DIR *d = opendir(fd_path);
        if (d) {
            int fds = 0;
            struct dirent *de;
            while ((de = readdir(d)) != NULL) {
                if (de->d_name[0] != '.') fds++;
            }
            closedir(d);
            if (fds > stats->peak_open_fds) stats->peak_open_fds = fds;
        }
    }
}

static int execute_with_strace(const char *program, const char *trace_file,
                               int *exit_code_out, int *sig_out, char *sig_name_out, size_t sig_name_sz,
                               AutoProcStats *stats)
{
    memset(stats, 0, sizeof(*stats));
    stats->peak_open_fds = -1;
    *exit_code_out = 0;
    *sig_out = 0;
    sig_name_out[0] = '\0';

    fflush(stdout);
    fflush(stderr);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    pid_t pid = fork();
    if (pid < 0) return -1;

    if (pid == 0) {
        struct rlimit rl = {0, 0};
        setrlimit(RLIMIT_CORE, &rl);

        const char *out_path = getenv("LDST_TARGET_STDOUT");
        if (out_path && out_path[0]) {
            int fd_out = open(out_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd_out >= 0) {
                dup2(fd_out, STDOUT_FILENO);
                close(fd_out);
            }
        }
        const char *err_path = getenv("LDST_TARGET_STDERR");
        if (err_path && err_path[0]) {
            int fd_err = open(err_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd_err >= 0) {
                dup2(fd_err, STDERR_FILENO);
                close(fd_err);
            }
        }

        char *const argv[] = {
            "strace", "-f", "-qq", "-o", (char *)trace_file,
            (char *)program, NULL
        };
        execvp("strace", argv);
        _exit(127);
    }

    stats->pid = pid;
    sample_proc_stats(pid, stats);

    int status = 0;
    struct timespec sleep_ts = {0, 10 * 1000 * 1000};
    for (;;) {
        pid_t w = waitpid(pid, &status, WNOHANG);
        if (w == pid) break;
        if (w < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        sample_proc_stats(pid, stats);
        nanosleep(&sleep_ts, NULL);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    stats->elapsed_ms = (double)(t1.tv_sec - t0.tv_sec) * 1000.0 +
                        (double)(t1.tv_nsec - t0.tv_nsec) / 1000000.0;

    if (WIFEXITED(status)) {
        *exit_code_out = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        *sig_out = WTERMSIG(status);
        const char *sn = strsignal(*sig_out);
        snprintf(sig_name_out, sig_name_sz, "%s", sn ? sn : "SIGUNKNOWN");
    }

    return 0;
}

static int run_gdb_safe(const char *program, const char *gdb_file,
                        char *note, size_t n,
                        char *crash_file, size_t cf_sz,
                        int *crash_line)
{
    crash_file[0] = '\0';
    *crash_line = 0;

    if (!tool_exists("gdb")) {
        snprintf(note, n, "GDB unavailable.");
        return -2;
    }

    fflush(stdout);
    fflush(stderr);

    pid_t pid = fork();
    if (pid < 0) {
        snprintf(note, n, "GDB process could not be started.");
        return -1;
    }

    if (pid == 0) {
        struct rlimit rl = {0, 0};
        setrlimit(RLIMIT_CORE, &rl);

        int fd = open(gdb_file, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd >= 0) {
            dup2(fd, STDOUT_FILENO);
            dup2(fd, STDERR_FILENO);
            close(fd);
        }
        char *const argv[] = {
            "gdb", "-nx", "-q", "-batch",
            "-ex", "run",
            "-ex", "bt",
            "-ex", "list",
            "--args", (char *)program,
            NULL
        };
        execvp("gdb", argv);
        _exit(127);
    }

    int status = 0;
    waitpid(pid, &status, 0);

    FILE *fp = fopen(gdb_file, "r");
    if (!fp) {
        snprintf(note, n, "GDB output could not be collected.");
        return -1;
    }

    char line[512];
    size_t used = 0;
    while (fgets(line, sizeof(line), fp) && used + 1 < n) {
        if (strstr(line, "Program received signal") || line[0] == '#') {
            /* Extract source file:line from frame #0 or first frame with ' at ' */
            if (line[0] == '#' && crash_file[0] == '\0') {
                char *at = strstr(line, " at ");
                if (at) {
                    at += 4;
                    char *colon = strrchr(at, ':');
                    if (colon && isdigit((unsigned char)colon[1])) {
                        size_t flen = (size_t)(colon - at);
                        if (flen >= cf_sz) flen = cf_sz - 1;
                        memcpy(crash_file, at, flen);
                        crash_file[flen] = '\0';
                        *crash_line = (int)strtol(colon + 1, NULL, 10);
                    }
                }
            }
            size_t len = strlen(line);
            if (used + len >= n) len = n - used - 1;
            memcpy(note + used, line, len);
            used += len;
            note[used] = '\0';
            if (used > 1400) break;
        }
    }
    fclose(fp);

    /* Trim trailing newline from note */
    while (used > 0 && (note[used - 1] == '\n' || note[used - 1] == '\r')) {
        note[--used] = '\0';
    }

    if (!used) {
        snprintf(note, n, "GDB completed; see %s for the full output.", gdb_file);
    }
    return 0;
}

static void write_json_escaped(FILE *fp, const char *s)
{
    fputc('"', fp);
    if (s) {
        for (; *s; ++s) {
            unsigned char c = (unsigned char)*s;
            if (c == '"') fputs("\\\"", fp);
            else if (c == '\\') fputs("\\\\", fp);
            else if (c == '\n') fputs("\\n", fp);
            else if (c == '\r') fputs("\\r", fp);
            else if (c == '\t') fputs("\\t", fp);
            else if (c >= 32) fputc(c, fp);
        }
    }
    fputc('"', fp);
}

static void write_autodebug_json(const char *json_path,
                                 const char *program,
                                 int exit_code,
                                 int sig,
                                 const char *sig_name,
                                 const Failure *f,
                                 int total_syscalls,
                                 int relevant_failures,
                                 int noise_failures,
                                 const AutoProcStats *stats,
                                 const char *gdb_status,
                                 const char *gdb_note,
                                 const char *crash_file,
                                 int crash_line,
                                 const char *diagnosis,
                                 const char *next,
                                 const char *trace_file,
                                 const char *report_file,
                                 const char *gdb_file)
{
    if (!json_path || !json_path[0]) return;
    FILE *fp = fopen(json_path, "w");
    if (!fp) return;

    fprintf(fp, "{\n");
    fprintf(fp, "  \"engine\": \"ldst_c_autodebugger\",\n");
    fprintf(fp, "  \"program\": "); write_json_escaped(fp, program); fprintf(fp, ",\n");
    fprintf(fp, "  \"child_pid\": %d,\n", (int)stats->pid);
    fprintf(fp, "  \"ppid\": %d,\n", (int)stats->ppid);
    fprintf(fp, "  \"elapsed_ms\": %.2f,\n", stats->elapsed_ms);
    fprintf(fp, "  \"exit_code\": %d,\n", exit_code);
    fprintf(fp, "  \"terminated_by_signal\": %s,\n", sig > 0 ? "true" : "false");
    fprintf(fp, "  \"signal_number\": %d,\n", sig);
    fprintf(fp, "  \"signal_name\": "); write_json_escaped(fp, sig_name); fprintf(fp, ",\n");
    fprintf(fp, "  \"peak_vm_size_kb\": %ld,\n", stats->peak_vm_size_kb);
    fprintf(fp, "  \"peak_vm_rss_kb\": %ld,\n", stats->peak_vm_rss_kb);
    fprintf(fp, "  \"peak_threads\": %d,\n", stats->peak_threads);
    fprintf(fp, "  \"peak_open_fds\": %d,\n", stats->peak_open_fds);
    fprintf(fp, "  \"monitor_samples\": %d,\n", stats->samples);
    fprintf(fp, "  \"total_syscalls\": %d,\n", total_syscalls);
    fprintf(fp, "  \"relevant_failed_syscalls\": %d,\n", relevant_failures);
    fprintf(fp, "  \"loader_noise_syscalls\": %d,\n", noise_failures);
    fprintf(fp, "  \"failed_syscall\": "); write_json_escaped(fp, f->syscall); fprintf(fp, ",\n");
    fprintf(fp, "  \"errno_name\": "); write_json_escaped(fp, f->errno_name); fprintf(fp, ",\n");
    fprintf(fp, "  \"errno_code\": %d,\n", f->errno_code);
    fprintf(fp, "  \"errno_meaning\": "); write_json_escaped(fp, f->meaning); fprintf(fp, ",\n");
    fprintf(fp, "  \"primary_evidence\": "); write_json_escaped(fp, f->evidence); fprintf(fp, ",\n");
    fprintf(fp, "  \"gdb_status\": "); write_json_escaped(fp, gdb_status); fprintf(fp, ",\n");
    fprintf(fp, "  \"gdb_backtrace\": "); write_json_escaped(fp, gdb_note); fprintf(fp, ",\n");
    fprintf(fp, "  \"crash_file\": "); write_json_escaped(fp, crash_file); fprintf(fp, ",\n");
    fprintf(fp, "  \"crash_line\": %d,\n", crash_line);
    fprintf(fp, "  \"diagnosis\": "); write_json_escaped(fp, diagnosis); fprintf(fp, ",\n");
    fprintf(fp, "  \"next_step\": "); write_json_escaped(fp, next); fprintf(fp, ",\n");
    fprintf(fp, "  \"trace_file\": "); write_json_escaped(fp, trace_file); fprintf(fp, ",\n");
    fprintf(fp, "  \"report_file\": "); write_json_escaped(fp, report_file); fprintf(fp, ",\n");
    fprintf(fp, "  \"gdb_file\": "); write_json_escaped(fp, sig > 0 ? gdb_file : ""); fprintf(fp, "\n");
    fprintf(fp, "}\n");
    fclose(fp);
}

static void print_report(const char *program, int exit_code, int sig, const char *sig_name,
                         const Failure *f, const char *diagnosis, const char *next,
                         const char *gdb_note, const char *trace_file, const char *report_file,
                         const char *gdb_file)
{
    FILE *fp = fopen(report_file, "w");
    if (fp) {
        fprintf(fp, "LINUX SYSTEM DEBUGGING TOOL - AUTO DIAGNOSIS\n\nProgram: %s\n", program);
        if (sig) fprintf(fp, "Result: %s (%d)\n", sig_name, sig);
        else if (f->errno_name[0]) fprintf(fp, "Result: %s (%d)\n", f->errno_name, f->errno_code);
        else fprintf(fp, "Result: %s\n", exit_code == 0 ? "NORMAL" : "NONZERO EXIT");
        fprintf(fp, "Exit code: %d\n\nDiagnosis\n%s\n\nNext step\n%s\n", exit_code, diagnosis, next);
        if (f->evidence[0]) fprintf(fp, "\nEvidence\n%s\n", f->evidence);
        if (gdb_note && *gdb_note) fprintf(fp, "\nGDB\n%s\n", gdb_note);
        fclose(fp);
    }

    printf("\n---------------- AUTO DIAGNOSIS ----------------\n");
    printf("Program       : %s\n", program);
    if (sig) printf("Result        : %s (%d)\n", sig_name, sig);
    else if (f->errno_name[0]) printf("Result        : %s (%d)\n", f->errno_name, f->errno_code);
    else printf("Result        : %s\n", exit_code == 0 ? "NORMAL" : "NONZERO EXIT");
    printf("Exit code     : %d\n", exit_code);
    if (f->errno_name[0]) {
        printf("\nFailed system call\n  Call        : %s()\n  Return      : -1\n  errno       : %s (%d)\n  Meaning     : %s\n",
               f->syscall, f->errno_name, f->errno_code, f->meaning);
    }
    printf("\nDiagnosis\n  %s\n\nNext step\n  %s\n", diagnosis, next);
    if (f->evidence[0]) printf("\nEvidence\n  %s\n", f->evidence);
    if (gdb_note && *gdb_note) printf("\nGDB\n  %s\n", gdb_note);
    printf("\nFiles\n  Trace  : %s\n  Report : %s\n", trace_file, report_file);
    if (sig) printf("  GDB    : %s\n", gdb_file);
    printf("\nOriginal source was NOT modified.\n=================================================\n");
    fflush(stdout);
}

int autodebug_run_with_options(const AutoDebugOptions *opts)
{
    if (!opts || !opts->program) return 1;
    const char *program = opts->program;

    if (access(program, X_OK) != 0) {
        fprintf(stderr, "AutoDebug: target is not an executable: %s\n", program);
        fprintf(stderr, "Compile it first, for example: make tests\n");
        return 1;
    }
    if (!tool_exists("strace")) {
        fprintf(stderr, "AutoDebug: strace is required. Install it with: sudo apt install strace\n");
        return 1;
    }

    mkdir("logs", 0755);
    mkdir("results", 0755);

    const char *trace_file = (opts->custom_trace_file && opts->custom_trace_file[0])
                             ? opts->custom_trace_file : DEFAULT_TRACE_FILE;
    const char *report_file = (opts->custom_report_file && opts->custom_report_file[0])
                              ? opts->custom_report_file : DEFAULT_REPORT_FILE;
    const char *gdb_file = (opts->custom_gdb_file && opts->custom_gdb_file[0])
                           ? opts->custom_gdb_file : DEFAULT_GDB_FILE;

    remove(trace_file);
    remove(report_file);
    remove(gdb_file);

    printf("\n============================================================\n                     AUTO DEBUG MODE\n============================================================\n\n");
    printf("[1/6] Target program: %s\n", program);
    printf("[2/6] Starting automatic execution and system-call tracing...\n");
    fflush(stdout);

    int exit_code = 1, sig = 0;
    char sig_name[32] = "";
    AutoProcStats stats;
    if (execute_with_strace(program, trace_file, &exit_code, &sig, sig_name, sizeof(sig_name), &stats) < 0) {
        perror("AutoDebug execution failed");
        return 1;
    }

    printf("[3/6] Execution finished. Collecting trace evidence...\n");
    fflush(stdout);

    Failure f;
    memset(&f, 0, sizeof(f));
    f.errno_code = -1;
    int total_syscalls = 0;
    int relevant_failures = 0;
    int noise_failures = 0;

    FILE *fp = fopen(trace_file, "r");
    char line[MAX_LINE];
    int trace_sig = 0;
    char trace_sig_name[32] = "";
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            char sc_tmp[64];
            if (extract_syscall(line, sc_tmp, sizeof(sc_tmp))) {
                total_syscalls++;
            }
            Failure temp;
            memset(&temp, 0, sizeof(temp));
            int is_noise_flag = 0;
            if (parse_failed_call(line, &temp, &is_noise_flag)) {
                f = temp;
                relevant_failures++;
            } else if (is_noise_flag) {
                noise_failures++;
            }
            int s = 0;
            char sn[32] = "";
            if (parse_signal(line, &s, sn, sizeof(sn))) {
                trace_sig = s;
                snprintf(trace_sig_name, sizeof(trace_sig_name), "%s", sn);
            }
        }
        fclose(fp);
    }

    if (trace_sig) {
        sig = trace_sig;
        snprintf(sig_name, sizeof(sig_name), "%s", trace_sig_name);
    }

    printf("[4/6] Analyzing process status and failure evidence...\n");
    fflush(stdout);

    char diagnosis[MAX_TEXT], next[MAX_TEXT], gdb_note[MAX_TEXT];
    char crash_file[256] = "";
    int crash_line = 0;
    const char *gdb_status = "not_required";
    diagnosis[0] = next[0] = gdb_note[0] = '\0';

    if (sig) {
        if (sig == SIGSEGV) {
            snprintf(diagnosis, sizeof(diagnosis), "The program accessed memory it was not allowed to access. This is a segmentation fault.");
            snprintf(next, sizeof(next), "Inspect the GDB backtrace and the reported source line. Check pointers, array bounds, and object lifetime.");
        } else if (sig == SIGABRT) {
            snprintf(diagnosis, sizeof(diagnosis), "The program terminated through SIGABRT, commonly caused by abort() or a failed assertion/library fatal condition.");
            snprintf(next, sizeof(next), "Inspect the GDB backtrace to find the abort/assertion path and the condition that triggered it.");
        } else if (sig == SIGFPE) {
            snprintf(diagnosis, sizeof(diagnosis), "The program received SIGFPE, indicating an arithmetic exception during execution.");
            snprintf(next, sizeof(next), "Inspect the GDB location and check division/modulo operations and other arithmetic inputs.");
        } else {
            snprintf(diagnosis, sizeof(diagnosis), "The program terminated because it received %s.", sig_name);
            snprintf(next, sizeof(next), "Check whether the signal was intentional and identify the process or action that generated it.");
        }

        if (opts->enable_gdb) {
            printf("[5/6] Crash/signal investigation requested. Running GDB...\n");
            fflush(stdout);
            int grc = run_gdb_safe(program, gdb_file, gdb_note, sizeof(gdb_note),
                                   crash_file, sizeof(crash_file), &crash_line);
            if (grc == -2) {
                gdb_status = "unavailable";
            } else if (grc < 0) {
                gdb_status = "error";
            } else {
                gdb_status = "completed";
            }
        } else {
            printf("[5/6] GDB crash analysis skipped by user configuration.\n");
            snprintf(gdb_note, sizeof(gdb_note), "GDB analysis skipped by configuration.");
            gdb_status = "skipped";
        }
    } else if (f.errno_name[0]) {
        explain_errno(&f, diagnosis, sizeof(diagnosis), next, sizeof(next));
        printf("[5/6] System-call diagnosis completed. GDB analysis not required.\n");
        gdb_status = "not_required";
    } else if (exit_code == 0) {
        snprintf(diagnosis, sizeof(diagnosis), "The program completed normally with exit code 0 and no supported failure pattern was detected.");
        snprintf(next, sizeof(next), "No corrective action is required for this execution.");
        printf("[5/6] System-call diagnosis completed. No failure detected. GDB analysis not required.\n");
        gdb_status = "not_required";
    } else {
        snprintf(diagnosis, sizeof(diagnosis), "The program returned a non-zero exit code (%d), but no failed system call or fatal signal was observed.", exit_code);
        snprintf(next, sizeof(next), "Inspect the program's return statement and standard output/error for application-level logic errors.");
        printf("[5/6] Execution finished with non-zero exit code. GDB analysis not required.\n");
        gdb_status = "not_required";
    }
    fflush(stdout);

    printf("[6/6] Preparing diagnostic report...\n");
    fflush(stdout);
    print_report(program, exit_code, sig, sig_name, &f, diagnosis, next, gdb_note,
                 trace_file, report_file, gdb_file);

    if (opts->json_output_file && opts->json_output_file[0]) {
        write_autodebug_json(opts->json_output_file, program, exit_code, sig, sig_name,
                             &f, total_syscalls, relevant_failures, noise_failures,
                             &stats, gdb_status, gdb_note, crash_file, crash_line,
                             diagnosis, next, trace_file, report_file, gdb_file);
    }

    return 0;
}

int autodebug_run(const char *program)
{
    AutoDebugOptions opts;
    memset(&opts, 0, sizeof(opts));
    opts.program = program;
    opts.enable_gdb = 1;
    return autodebug_run_with_options(&opts);
}

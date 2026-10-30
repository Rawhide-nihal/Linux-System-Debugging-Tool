#define _POSIX_C_SOURCE 200809L
#include "process_manager.h"
#include "tracer.h"
#include "process_monitor.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void update_peaks(ProcessResult *result, const ProcessInfo *snap)
{
    result->monitor_snapshot = *snap;
    result->monitor_snapshot_valid = 1;
    result->sample_count++;

    if (snap->vm_size_kb > result->peak_vm_size_kb)
        result->peak_vm_size_kb = snap->vm_size_kb;
    if (snap->vm_rss_kb > result->peak_vm_rss_kb)
        result->peak_vm_rss_kb = snap->vm_rss_kb;
    if (snap->threads > result->peak_threads)
        result->peak_threads = snap->threads;
    if (snap->open_fds > result->peak_open_fds)
        result->peak_open_fds = snap->open_fds;
}

static void sample_process(pid_t root_pid, int traced, ProcessResult *result)
{
    pid_t inspect_pid = root_pid;
    if (traced) {
        pid_t child = process_monitor_find_child(root_pid);
        if (child > 0) {
            inspect_pid = child;
            result->target_pid = child;
        }
    }

    ProcessInfo snap;
    if (process_monitor_read(inspect_pid, &snap) == 0 && snap.vm_size_kb > 0) {
        update_peaks(result, &snap);
    } else if (inspect_pid != root_pid && process_monitor_read(root_pid, &snap) == 0) {
        if (!result->monitor_snapshot_valid) {
            update_peaks(result, &snap);
        }
    }
}

int process_manager_run(const char *program, const char *trace_file,
                        ProcessResult *result)
{
    if (!program || !result) {
        errno = EINVAL;
        return -1;
    }

    memset(result, 0, sizeof(*result));
    result->peak_open_fds = -1;

    /* Flush stdout/stderr before fork so parent output is never duplicated or reordered */
    fflush(stdout);
    fflush(stderr);

    struct timespec t_start, t_end;
    clock_gettime(CLOCK_MONOTONIC, &t_start);

    pid_t pid = fork();
    if (pid < 0) {
        return -1;
    }

    if (pid == 0) {
        /* Disable core file generation during normal/strace run to avoid apport delays */
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

        if (trace_file) {
            char *const trace_argv[] = {
                "strace", "-f", "-qq", "-o", (char *)trace_file,
                (char *)program, NULL
            };
            execvp("strace", trace_argv);
        } else {
            char *const argv[] = {(char *)program, NULL};
            execvp(program, argv);
        }

        fprintf(stderr, "exec failed for '%s': %s\n",
                program, strerror(errno));
        _exit(127);
    }

    result->pid = pid;
    result->target_pid = pid;

    /* Initial sample immediately after fork */
    sample_process(pid, trace_file != NULL, result);

    /* Poll with WNOHANG and sample /proc while the process is alive */
    struct timespec sleep_ts = {0, 10 * 1000 * 1000}; /* 10 ms */
    for (;;) {
        pid_t w = waitpid(pid, &result->status, WNOHANG);
        if (w == pid) {
            break;
        }
        if (w < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        sample_process(pid, trace_file != NULL, result);
        nanosleep(&sleep_ts, NULL);
    }

    clock_gettime(CLOCK_MONOTONIC, &t_end);
    result->elapsed_ms = (double)(t_end.tv_sec - t_start.tv_sec) * 1000.0 +
                         (double)(t_end.tv_nsec - t_start.tv_nsec) / 1000000.0;

    if (WIFEXITED(result->status)) {
        result->exited_normally = 1;
        result->exit_code = WEXITSTATUS(result->status);
    } else if (WIFSIGNALED(result->status)) {
        result->terminated_by_signal = 1;
        result->signal_number = WTERMSIG(result->status);
    }

    return 0;
}

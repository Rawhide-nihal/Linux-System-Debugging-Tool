/*
 * Linux System Debugging Tool - Native Process Launcher & Execution Sandbox
 * Provides controlled child process spawning with resource limits (RLIMIT)
 * and process isolation.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <fcntl.h>
#include <signal.h>
#include <errno.h>

typedef struct {
    long cpu_time_sec;
    long memory_bytes;
    long file_size_bytes;
    long max_processes;
} SandboxLimits;

int configure_limits(const SandboxLimits *limits) {
    if (!limits) return 0;

    struct rlimit rl;
    if (limits->cpu_time_sec > 0) {
        rl.rlim_cur = limits->cpu_time_sec;
        rl.rlim_max = limits->cpu_time_sec + 2;
        setrlimit(RLIMIT_CPU, &rl);
    }
    if (limits->memory_bytes > 0) {
        rl.rlim_cur = limits->memory_bytes;
        rl.rlim_max = limits->memory_bytes;
        #ifdef RLIMIT_AS
        setrlimit(RLIMIT_AS, &rl);
        #endif
    }
    if (limits->file_size_bytes > 0) {
        rl.rlim_cur = limits->file_size_bytes;
        rl.rlim_max = limits->file_size_bytes;
        setrlimit(RLIMIT_FSIZE, &rl);
    }
    if (limits->max_processes > 0) {
        rl.rlim_cur = limits->max_processes;
        rl.rlim_max = limits->max_processes;
        #ifdef RLIMIT_NPROC
        setrlimit(RLIMIT_NPROC, &rl);
        #endif
    }
    return 0;
}

int launch_target_process(const char *executable, char *const argv[], char *const envp[],
                          int stdin_fd, int stdout_fd, int stderr_fd,
                          const SandboxLimits *limits, const char *working_dir) {
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return -1;
    }

    if (pid == 0) {
        // Child process
        setsid(); // Create a new process group so signals can be scoped

        if (working_dir && strlen(working_dir) > 0) {
            if (chdir(working_dir) != 0) {
                perror("chdir");
                _exit(127);
            }
        }

        if (stdin_fd >= 0 && stdin_fd != STDIN_FILENO) {
            dup2(stdin_fd, STDIN_FILENO);
            close(stdin_fd);
        }
        if (stdout_fd >= 0 && stdout_fd != STDOUT_FILENO) {
            dup2(stdout_fd, STDOUT_FILENO);
            close(stdout_fd);
        }
        if (stderr_fd >= 0 && stderr_fd != STDERR_FILENO) {
            dup2(stderr_fd, STDERR_FILENO);
            close(stderr_fd);
        }

        configure_limits(limits);

        if (envp) {
            execvpe(executable, argv, envp);
        } else {
            execvp(executable, argv);
        }

        perror("execvp");
        _exit(127);
    }

    return pid;
}

int wait_for_target(int pid, int *status_out, int timeout_ms) {
    if (pid <= 0) return -1;
    int elapsed = 0;
    while (elapsed < timeout_ms) {
        int status;
        pid_t res = waitpid(pid, &status, WNOHANG);
        if (res == pid) {
            if (status_out) *status_out = status;
            return 0; // Terminated
        }
        if (res < 0) {
            return -1;
        }
        usleep(10000); // 10ms
        elapsed += 10;
    }
    return 1; // Timed out
}

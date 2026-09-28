#include "process_manager.h"
#include "tracer.h"
#include "process_monitor.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

int process_manager_run(const char *program, const char *trace_file,
                        ProcessResult *result)
{
    if (!program || !result) {
        errno = EINVAL;
        return -1;
    }

    memset(result, 0, sizeof(*result));

    pid_t pid = fork();
    if (pid < 0) {
        return -1;
    }

    if (pid == 0) {
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

    if (process_monitor_read(pid, &result->monitor_snapshot) == 0) {
        result->monitor_snapshot_valid = 1;
    }

    if (waitpid(pid, &result->status, 0) < 0) {
        return -1;
    }

    if (WIFEXITED(result->status)) {
        result->exited_normally = 1;
        result->exit_code = WEXITSTATUS(result->status);
    } else if (WIFSIGNALED(result->status)) {
        result->terminated_by_signal = 1;
        result->signal_number = WTERMSIG(result->status);
    }

    return 0;
}

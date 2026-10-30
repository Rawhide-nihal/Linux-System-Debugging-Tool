#include "debugger.h"

#include <stdio.h>
#include <string.h>

static void usage(const char *name)
{
    printf("Linux System Debugging Tool\n\n");
    printf("Usage:\n");
    printf("  %s [options] <program>\n\n", name);
    printf("Options:\n");
    printf("  --no-trace            Run without strace system-call tracing\n");
    printf("  --no-monitor          Disable /proc process monitoring\n");
    printf("  --trace-file <path>   Custom output path for strace log\n");
    printf("  --report-file <path>  Custom output path for text report\n");
    printf("  --json-file <path>    Write structured JSON summary to path\n");
}

int main(int argc, char *argv[])
{
    DebuggerOptions opts;
    memset(&opts, 0, sizeof(opts));
    opts.use_trace = 1;
    opts.use_monitor = 1;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--no-trace") == 0) {
            opts.use_trace = 0;
        } else if (strcmp(argv[i], "--no-monitor") == 0) {
            opts.use_monitor = 0;
        } else if (strcmp(argv[i], "--trace-file") == 0 && i + 1 < argc) {
            opts.custom_trace_file = argv[++i];
        } else if (strcmp(argv[i], "--report-file") == 0 && i + 1 < argc) {
            opts.custom_report_file = argv[++i];
        } else if (strcmp(argv[i], "--json-file") == 0 && i + 1 < argc) {
            opts.json_output_file = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        } else if (argv[i][0] == '-') {
            fprintf(stderr, "Unknown option: %s\n\n", argv[i]);
            usage(argv[0]);
            return 1;
        } else if (!opts.program) {
            opts.program = argv[i];
        } else {
            usage(argv[0]);
            return 1;
        }
    }

    if (!opts.program) {
        usage(argv[0]);
        return 1;
    }

    return debugger_run_with_options(&opts);
}

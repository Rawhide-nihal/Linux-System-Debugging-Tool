#include "auto_debug.h"
#include <stdio.h>
#include <string.h>

static void usage(const char *name)
{
    fprintf(stderr, "Usage: %s [options] <executable-program>\n", name);
    fprintf(stderr, "Options:\n");
    fprintf(stderr, "  --no-gdb              Skip GDB analysis even on crash\n");
    fprintf(stderr, "  --trace-file <path>   Custom strace log output path\n");
    fprintf(stderr, "  --report-file <path>  Custom text report output path\n");
    fprintf(stderr, "  --gdb-file <path>     Custom GDB log output path\n");
    fprintf(stderr, "  --json-file <path>    Write structured JSON summary to path\n");
}

int main(int argc, char **argv)
{
    AutoDebugOptions opts;
    memset(&opts, 0, sizeof(opts));
    opts.enable_gdb = 1;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--no-gdb") == 0) {
            opts.enable_gdb = 0;
        } else if (strcmp(argv[i], "--trace-file") == 0 && i + 1 < argc) {
            opts.custom_trace_file = argv[++i];
        } else if (strcmp(argv[i], "--report-file") == 0 && i + 1 < argc) {
            opts.custom_report_file = argv[++i];
        } else if (strcmp(argv[i], "--gdb-file") == 0 && i + 1 < argc) {
            opts.custom_gdb_file = argv[++i];
        } else if (strcmp(argv[i], "--json-file") == 0 && i + 1 < argc) {
            opts.json_output_file = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        } else if (argv[i][0] == '-') {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
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

    return autodebug_run_with_options(&opts);
}

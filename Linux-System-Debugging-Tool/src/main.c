#include "debugger.h"

#include <stdio.h>
#include <string.h>

static void usage(const char *name)
{
    printf("Linux System Debugging Tool\n\n");
    printf("Usage:\n");
    printf("  %s <program>\n", name);
    printf("  %s --no-trace <program>\n", name);
}

int main(int argc, char *argv[])
{
    if (argc == 2) {
        return debugger_run(argv[1], 1);
    }

    if (argc == 3 && strcmp(argv[1], "--no-trace") == 0) {
        return debugger_run(argv[2], 0);
    }

    usage(argv[0]);
    return 1;
}

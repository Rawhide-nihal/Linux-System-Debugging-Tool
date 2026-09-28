#include "error_analyzer.h"

#include <signal.h>

const char *error_description(int code)
{
    switch (code) {
        case 2:  return "No such file or directory";
        case 9:  return "Bad file descriptor";
        case 13: return "Permission denied";
        case 17: return "File exists";
        case 20: return "Not a directory";
        case 21: return "Is a directory";
        case 22: return "Invalid argument";
        default: return "Unknown or platform-specific error";
    }
}

const char *signal_description(int signal_number)
{
    switch (signal_number) {
        case SIGTERM: return "SIGTERM (Termination)";
        case SIGSEGV: return "SIGSEGV (Segmentation fault)";
        case SIGINT:  return "SIGINT (Interrupt)";
        case SIGABRT: return "SIGABRT (Aborted)";
        case SIGKILL: return "SIGKILL (Killed)";
        default: return "Unknown signal";
    }
}

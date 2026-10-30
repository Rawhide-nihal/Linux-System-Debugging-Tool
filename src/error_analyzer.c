#include "error_analyzer.h"

#include <signal.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    int code;
    const char *name;
    const char *description;
} ErrnoEntry;

static const ErrnoEntry ERRNO_TABLE[] = {
    {1,   "EPERM",        "Operation not permitted"},
    {2,   "ENOENT",       "No such file or directory"},
    {3,   "ESRCH",        "No such process"},
    {4,   "EINTR",        "Interrupted system call"},
    {5,   "EIO",          "Input/output error"},
    {6,   "ENXIO",        "No such device or address"},
    {7,   "E2BIG",        "Argument list too long"},
    {8,   "ENOEXEC",      "Exec format error"},
    {9,   "EBADF",        "Bad file descriptor"},
    {10,  "ECHILD",       "No child processes"},
    {11,  "EAGAIN",       "Resource temporarily unavailable"},
    {11,  "EWOULDBLOCK",  "Resource temporarily unavailable"},
    {12,  "ENOMEM",       "Cannot allocate memory"},
    {13,  "EACCES",       "Permission denied"},
    {14,  "EFAULT",       "Bad address"},
    {15,  "ENOTBLK",      "Block device required"},
    {16,  "EBUSY",        "Device or resource busy"},
    {17,  "EEXIST",       "File exists"},
    {18,  "EXDEV",        "Invalid cross-device link"},
    {19,  "ENODEV",       "No such device"},
    {20,  "ENOTDIR",      "Not a directory"},
    {21,  "EISDIR",       "Is a directory"},
    {22,  "EINVAL",       "Invalid argument"},
    {23,  "ENFILE",       "Too many open files in system"},
    {24,  "EMFILE",       "Too many open files"},
    {25,  "ENOTTY",       "Inappropriate ioctl for device"},
    {26,  "ETXTBSY",      "Text file busy"},
    {27,  "EFBIG",        "File too large"},
    {28,  "ENOSPC",       "No space left on device"},
    {29,  "ESPIPE",       "Illegal seek"},
    {30,  "EROFS",        "Read-only file system"},
    {31,  "EMLINK",       "Too many links"},
    {32,  "EPIPE",        "Broken pipe"},
    {33,  "EDOM",         "Numerical argument out of domain"},
    {34,  "ERANGE",       "Numerical result out of range"},
    {35,  "EDEADLK",      "Resource deadlock avoided"},
    {36,  "ENAMETOOLONG", "File name too long"},
    {37,  "ENOLCK",       "No locks available"},
    {38,  "ENOSYS",       "Function not implemented"},
    {39,  "ENOTEMPTY",    "Directory not empty"},
    {40,  "ELOOP",        "Too many levels of symbolic links"},
    {95,  "EOPNOTSUPP",   "Operation not supported"},
    {98,  "EADDRINUSE",   "Address already in use"},
    {99,  "EADDRNOTAVAIL","Cannot assign requested address"},
    {104, "ECONNRESET",   "Connection reset by peer"},
    {110, "ETIMEDOUT",    "Connection timed out"},
    {111, "ECONNREFUSED", "Connection refused"}
};

const char *error_description(int code)
{
    for (size_t i = 0; i < sizeof(ERRNO_TABLE) / sizeof(ERRNO_TABLE[0]); ++i) {
        if (ERRNO_TABLE[i].code == code) {
            return ERRNO_TABLE[i].description;
        }
    }
    return "Unknown or platform-specific error";
}

const char *error_name_from_code(int code)
{
    for (size_t i = 0; i < sizeof(ERRNO_TABLE) / sizeof(ERRNO_TABLE[0]); ++i) {
        if (ERRNO_TABLE[i].code == code) {
            return ERRNO_TABLE[i].name;
        }
    }
    return "UNKNOWN";
}

int error_code_from_name(const char *name)
{
    if (!name || !name[0]) return -1;
    for (size_t i = 0; i < sizeof(ERRNO_TABLE) / sizeof(ERRNO_TABLE[0]); ++i) {
        if (strcmp(ERRNO_TABLE[i].name, name) == 0) {
            return ERRNO_TABLE[i].code;
        }
    }
    return -1;
}

const char *signal_description(int signal_number)
{
    switch (signal_number) {
        case SIGHUP:  return "SIGHUP (Hangup)";
        case SIGINT:  return "SIGINT (Interrupt)";
        case SIGQUIT: return "SIGQUIT (Quit)";
        case SIGILL:  return "SIGILL (Illegal instruction)";
        case SIGTRAP: return "SIGTRAP (Trace/breakpoint trap)";
        case SIGABRT: return "SIGABRT (Aborted)";
        case SIGBUS:  return "SIGBUS (Bus error)";
        case SIGFPE:  return "SIGFPE (Floating-point exception)";
        case SIGKILL: return "SIGKILL (Killed)";
        case SIGUSR1: return "SIGUSR1 (User-defined signal 1)";
        case SIGSEGV: return "SIGSEGV (Segmentation fault)";
        case SIGUSR2: return "SIGUSR2 (User-defined signal 2)";
        case SIGPIPE: return "SIGPIPE (Broken pipe)";
        case SIGALRM: return "SIGALRM (Alarm clock)";
        case SIGTERM: return "SIGTERM (Termination)";
#ifdef SIGSYS
        case SIGSYS:  return "SIGSYS (Bad system call)";
#endif
        default:      return "Unknown signal";
    }
}

const char *signal_short_name(int signal_number)
{
    switch (signal_number) {
        case SIGHUP:  return "SIGHUP";
        case SIGINT:  return "SIGINT";
        case SIGQUIT: return "SIGQUIT";
        case SIGILL:  return "SIGILL";
        case SIGTRAP: return "SIGTRAP";
        case SIGABRT: return "SIGABRT";
        case SIGBUS:  return "SIGBUS";
        case SIGFPE:  return "SIGFPE";
        case SIGKILL: return "SIGKILL";
        case SIGUSR1: return "SIGUSR1";
        case SIGSEGV: return "SIGSEGV";
        case SIGUSR2: return "SIGUSR2";
        case SIGPIPE: return "SIGPIPE";
        case SIGALRM: return "SIGALRM";
        case SIGTERM: return "SIGTERM";
#ifdef SIGSYS
        case SIGSYS:  return "SIGSYS";
#endif
        default:      return "SIGUNKNOWN";
    }
}

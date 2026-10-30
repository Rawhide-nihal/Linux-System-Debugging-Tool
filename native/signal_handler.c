/*
 * Linux System Debugging Tool - Native Signal & Crash Decoder
 * Maps Linux signal numbers and siginfo_t codes to precise diagnostics.
 */

#include <stdio.h>
#include <string.h>
#include <signal.h>

const char* decode_signal_name(int sig) {
    switch (sig) {
        case SIGSEGV: return "SIGSEGV (Segmentation Fault)";
        case SIGFPE:  return "SIGFPE (Floating Point Exception / Division by Zero)";
        case SIGABRT: return "SIGABRT (Aborted / Assertion Failed)";
        case SIGILL:  return "SIGILL (Illegal Instruction)";
        case SIGBUS:  return "SIGBUS (Bus Error / Misaligned Memory Access)";
        case SIGTRAP: return "SIGTRAP (Trace/Breakpoint Trap)";
        case SIGSYS:  return "SIGSYS (Bad System Call)";
        case SIGPIPE: return "SIGPIPE (Broken Pipe)";
        case SIGALRM: return "SIGALRM (Alarm Clock / Timeout)";
        case SIGTERM: return "SIGTERM (Termination Request)";
        case SIGINT:  return "SIGINT (Interactive Interrupt)";
        case SIGKILL: return "SIGKILL (Killed)";
        default:      return "Unknown Signal";
    }
}

const char* describe_signal_cause(int sig, int code) {
    (void)code;
    if (sig == SIGSEGV) {
        #ifdef SEGV_MAPERR
        if (code == SEGV_MAPERR) return "Address not mapped to object (null pointer dereference or invalid memory address)";
        #endif
        #ifdef SEGV_ACCERR
        if (code == SEGV_ACCERR) return "Invalid permissions for mapped object (e.g. writing to read-only memory)";
        #endif
        return "Invalid memory reference / out-of-bounds access";
    }
    if (sig == SIGFPE) {
        #ifdef FPE_INTDIV
        if (code == FPE_INTDIV) return "Integer division by zero";
        #endif
        #ifdef FPE_INTOVF
        if (code == FPE_INTOVF) return "Integer overflow trap";
        #endif
        #ifdef FPE_FLTDIV
        if (code == FPE_FLTDIV) return "Floating-point division by zero";
        #endif
        #ifdef FPE_FLTOVF
        if (code == FPE_FLTOVF) return "Floating-point overflow";
        #endif
        return "Arithmetic / floating-point computation exception";
    }
    if (sig == SIGILL) {
        return "CPU attempted to execute an illegal or unrecognized instruction";
    }
    if (sig == SIGBUS) {
        return "Hardware alignment error or mmap-backed file truncation error";
    }
    if (sig == SIGABRT) {
        return "Program called abort() or a failed runtime assertion triggered termination";
    }
    return "Process terminated due to signal";
}

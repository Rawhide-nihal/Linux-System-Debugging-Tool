# System Design

## High-level flow

User -> main -> debugger -> process_manager -> target program

The target is launched as a child process. When tracing is enabled, the child executes under `strace`, which writes a system-call trace to `logs/`.

The parent waits with `waitpid()`, records termination status, and passes the trace to the tracer/error-analysis layer. A diagnostic report is written to `results/`.

## Modules

1. Main controller
2. Process manager
3. System-call tracer
4. Error analyzer
5. Process monitor
6. Logger
7. Controlled test programs

## Core Linux concepts

- fork()
- execvp()
- waitpid()
- process IDs
- exit status
- signals
- errno
- `/proc`
- file/system-call failures
- strace

# Linux System Debugging Tool

Team 15 — OSSP (25CS2104E)

A C-based Linux user-space debugging tool for observing controlled program execution, tracing system calls with `strace`, analyzing failures and `errno`, detecting abnormal process termination, and generating diagnostic reports.

## Requirements

- Ubuntu/Linux
- GCC
- make
- strace

Install dependencies:

```bash
sudo apt update
sudo apt install build-essential strace gdb tree
```

## Build

On Ubuntu, you can install dependencies and build with:

```bash
chmod +x setup.sh
./setup.sh
```

Or build manually:

```bash
make
make tests
```

## Run

Trace a program:

```bash
./debugger ./tests/file_error
```

Run without strace:

```bash
./debugger --no-trace ./tests/normal_test
```

## Test programs

- `normal_test` — normal execution
- `file_error` — controlled `ENOENT` failure
- `invalid_fd` — controlled `EBADF` failure
- `permission_error` — permission-related test
- `abnormal_exit` — signal termination
- `segmentation_fault` — controlled `SIGSEGV`

Run examples:

```bash
./debugger ./tests/normal_test
./debugger ./tests/file_error
./debugger ./tests/invalid_fd
./debugger ./tests/abnormal_exit
./debugger ./tests/segmentation_fault
```

## Output

- System-call traces are written under `logs/`.
- Diagnostic reports are written under `results/`.

## Architecture

The project is divided into:

- `process_manager` — fork, exec, waitpid and exit-status handling
- `tracer` — strace execution and basic trace analysis
- `process_monitor` — Linux `/proc` process information
- `error_analyzer` — errno/error and signal descriptions
- `logger` — diagnostic report generation
- `debugger` — integration/controller
- `tests` — controlled target programs

## Scope

This is a user-space Linux systems-programming project. It is intentionally centered on C, POSIX/Linux process APIs, system calls, `/proc`, `strace`, error handling, and process termination analysis rather than a generic GUI/database application.

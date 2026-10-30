# LDST — Linux System Debugging Tool

**Operating Systems & Systems Programming Project (OSSP — 25CS2104E)**

LDST (**Linux System Debugging Tool**) is a complete Linux user-space debugging environment written in C with a dual interface:
1. **Interactive Terminal CLI (`./ldst`, `./debugger`, `./autodebug`)**
2. **Local Browser Web Application (`./run.sh` → `http://127.0.0.1:5000`)**

Every technical result displayed in both the CLI and the Web GUI originates from genuine Linux execution: real `gcc` compilation, `fork()`/`execvp()`/`waitpid()` process control, `strace` system-call tracing, POSIX `errno` decoding, live `/proc` kernel telemetry, and batch `GDB` crash backtrace analysis.

---

## Key Features

- **Dual-Interface Architecture**: Preserves the C terminal CLI (`./ldst`, `./debugger`, `./autodebug`) while adding a dark developer-grade local web application on `http://127.0.0.1:5000`.
- **Custom C Program Creation & Editing**: Write, edit, save, and manage custom C11 programs inside `tests/` with strict path validation and line-numbered syntax editing.
- **Real GCC Compilation & Diagnostics**: Compiles with `gcc -Wall -Wextra -std=c11 -g`, captures real `stdout`/`stderr`, counts warnings/errors, parses clickable `file:line:col` compiler diagnostics, and prevents stale binary execution when compilation fails.
- **System-Call Tracing (`strace`)**: Captures kernel system calls (`openat`, `read`, `write`, `close`, `mmap`, `brk`, etc.), conservatively separates dynamic-loader startup probes (`/etc/ld.so.preload`) from target application failures, and groups failed calls by `errno`.
- **Error & Signal Forensics (`errno` & `waitpid`)**: Decodes POSIX `errno` values (`ENOENT`, `EBADF`, `EACCES`, `EINVAL`, `EPERM`, etc.) and abnormal termination signals (`SIGSEGV`, `SIGTERM`, `SIGABRT`, `SIGFPE`, `SIGILL`).
- **Live Linux `/proc` Process Monitoring**: Samples `/proc/<pid>/status`, `/proc/<pid>/stat`, and `/proc/<pid>/fd` during child execution to record PID, PPID, process state, CPU usage, `VmSize`, `VmRSS`, thread count, and open file descriptors.
- **Automated Crash Investigation (`AutoDebugger` + `GDB`)**: Runs a 6-stage automated investigation and invokes batch `gdb` on fatal signals to extract stack frames (`#0 main () at ...`) and pinpoint crashing C source lines, clearly separating **Observed Facts** from **Diagnostic Interpretation**.
- **Persistent Structured Reports**: Saves every debugging session to `reports/` in both `.json` and `.txt` formats with search, filtering, reopening, and one-click export.

---

## System Architecture

The browser does **not** simulate or perform Linux debugging. Instead, the local Python/Flask backend communicates directly with the native LDST C debugging core (`./debugger` and `./autodebug`) and standard Linux system tools:

```text
                               LDST CORE
                          (src/ & autodebug_src/)
                              /             \
                             /               \
                            ▼                 ▼
                      TERMINAL CLI         WEB GUI
                         ./ldst            ./run.sh
                                              │
                                              ▼
                                       127.0.0.1:5000
                                              │
                                       Browser Workspace
                                              │
                                              ▼
                                        Flask Backend
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        ▼                     ▼                     ▼
                       GCC               LDST C Core             Reports
              (-Wall -Wextra -g)   (./debugger & ./autodebug)  (JSON & TXT)
                                              │
                                ┌─────────────┼─────────────┐
                                ▼             ▼             ▼
                              strace        /proc          GDB
                                └─────────────┼─────────────┘
                                              ▼
                                        Linux Kernel
```

---

## Visual Preview & Interface Assets

The web interface uses five custom dark developer-tool visual assets under `web/static/images/`:
- **Landing Page Hero (`hero_artwork.jpg` & `tech_background.jpg`)**: Atmospheric Linux debugging hero section with pipeline overview and feature cards.
- **Workspace Empty State (`empty_analysis.jpg`)**: Displayed when no analysis or report has been selected yet.
- **Clean Execution State (`success_state.jpg`)**: Displayed only when a program completes cleanly (`exit_code == 0`, no signal, `relevant_failures == 0`).
- **Crash / Failure State (`error_crash.jpg`)**: Displayed on genuine runtime crashes (`SIGSEGV`, `SIGTERM`) or system-call errors (`ENOENT`, `EBADF`, `EACCES`).

---

## Requirements

- **OS**: Ubuntu / Linux (or WSL2 Ubuntu on Windows) with `/proc` mounted
- **C Toolchain**: `gcc`, `make` (`build-essential`)
- **Linux Debugging Utilities**: `strace`, `gdb`
- **Web Backend**: `python3` (uses `Flask` when installed, with a built-in standard-library HTTP/WSGI fallback so `./run.sh` works out-of-the-box even before installing external pip packages)

---

## Ubuntu Setup & Installation

Run the first-time setup script to verify/install dependencies and compile the C core and official test programs:

```bash
chmod +x setup.sh run.sh selftest.sh
./setup.sh
```

Or install packages and build manually on Ubuntu:

```bash
sudo apt update
sudo apt install -y build-essential strace gdb python3 python3-flask python3-venv
make clean
make
make tests
```

---

## Starting the CLI

You can use LDST purely from the terminal at any time without running the web server:

```bash
# Interactive console menu launcher
./ldst

# Run the C debugger directly on any target binary
./debugger ./tests/file_error
./debugger --no-trace ./tests/normal_test

# Run the C AutoDebugger directly
./autodebug ./tests/segmentation_fault
```

---

## Starting the Web GUI

Start the local web application server with:

```bash
./run.sh
```

Expected startup output:

```text
================================================
 LDST — Linux System Debugging Tool
================================================

Checking environment...
GCC ............. OK
strace .......... OK
GDB ............. OK
LDST Core ....... OK
Web Backend ..... OK

LDST Web Interface is running:

http://127.0.0.1:5000

Press Ctrl+C to stop.
================================================
```

Open **`http://127.0.0.1:5000`** in your browser.

---

## Workflow Guide

### 1. Creating & Compiling Custom C Programs
1. Open **Create Program** in the left sidebar.
2. Enter a valid program name (e.g., `my_test`, `file_bug`, `custom_program_1`). Path traversal (`../`) and shell metacharacters are strictly rejected.
3. Write C11 code or pick a starter template from the dropdown.
4. Click **SAVE & COMPILE** to invoke real `gcc -Wall -Wextra -std=c11 -g`.
   - If compilation succeeds, the binary is written to `tests/<name>` and **RUN / DEBUG / AUTODEBUG** are enabled.
   - If compilation fails, any prior binary is removed so a stale executable is never run, and clickable line diagnostics are displayed.

### 2. Using the Interactive Source-Level C Debugger
1. Open **Debugger** in the sidebar.
2. Select any built-in or custom program (e.g., `math_step`, `function_call`, `segmentation_fault`, `sigfpe_test`, `nonzero_exit`).
3. Click any line number in the source-code gutter to toggle **Breakpoints** before or during debugging.
4. Click **START DEBUGGING**:
   - The backend compiles the program with `gcc -Wall -Wextra -std=c11 -g -O0`.
   - GDB (MI2) launches the binary, breaks at `main()`, and highlights the first executable source line.
   - A correlation pass with `strace` captures kernel system calls and errno evidence.
5. Use the Interactive Debugger Controls:
   - **NEXT**: Step over the current source statement to the next line without entering functions.
   - **STEP INTO**: Enter called user functions (e.g. `add(a, b)` in `function_call.c`).
   - **STEP OUT**: Finish current function execution and return to caller.
   - **CONTINUE**: Resume execution until a breakpoint, signal crash, or process termination.
   - **STOP DEBUGGING**: Safely kill the GDB session and all inferior child processes.
6. Inspect the Interactive Panels:
   - **Source Code Viewer**: Shows line numbers, breakpoint markers, and current execution highlight (`> 11 | *ptr = 42;`).
   - **Session Status**: Shows live State, PID, current Function, File & Line, and truthful Stop Reason.
   - **Local Variables**: Live table showing names, types, and truthful values from GDB (`<not available>`, `<optimized out>`, `0x0 (NULL)`).
   - **Function Arguments**: Inspect function parameters (`x`, `y`) at the current frame.
   - **Call Stack**: Complete GDB backtrace frames (`#0 add()`, `#1 main()`); click any frame to inspect variables at that depth.
   - **Program Output**: Separated target `stdout` and `stderr` streams, updated incrementally.
   - **Errors & Signals**: On fatal signals (`SIGSEGV`, `SIGFPE`), displays the exact crashing source statement, line number, file, and backtrace. Deliberate non-zero exit codes (`return 42;`) are clearly distinguished from crashes.
   - **System Call Evidence**: Real kernel system call counts, errno groupings, and source line correlations.
   - **Debugger Timeline**: Chronological event history of every step and breakpoint hit.
   - **Save Report**: Persists the debugging session into `reports/` for historical analysis.

### 3. Using AutoDebugger & GDB Crash Analysis
1. Open **AutoDebugger**, select a target program (such as `segmentation_fault`), and keep **Run GDB crash analysis when appropriate** checked.
2. Click **RUN AUTODEBUGGER** to execute all 6 investigation stages:
   1. *Executing program*
   2. *Collecting termination status*
   3. *Analyzing trace*
   4. *Collecting process information*
   5. *Running GDB* (automatically skipped when no crash occurred)
   6. *Generating diagnosis*
3. Inspect the crash report showing the fatal signal (`SIGSEGV`), parsed GDB backtrace (`#0 main () at segmentation_fault.c:9`), highlighted C source context, **Observed Facts**, and **Diagnostic Interpretation**.

### 4. Understanding & Exporting Reports
- Every completed session is saved under `reports/<session_id>.json` and `reports/<session_id>.txt`.
- Visit **Reports** in the sidebar to search by program name, `errno`, or signal, reopen full 6-tab evidence, export as **TXT** or **JSON**, or delete old reports.

---

## Security & Local Execution Warning

> **IMPORTANT**: LDST intentionally compiles and executes user-written C programs on the host Linux machine for systems-programming education and debugging.
> - The web server binds **strictly to `127.0.0.1` (localhost)** by default. Do **not** expose this service to untrusted public networks.
> - All subprocess invocations use safe argument arrays (`execvp` in C, `subprocess.run`/`Popen` argument lists in Python) without `shell=True`.
> - All custom source and binary files are confined to the project's `tests/` directory with strict filename validation.

---

## Project Structure

```text
Linux-System-Debugging-Tool/
├── src/
│   ├── main.c              # CLI entry point for ./debugger
│   ├── debugger.c / .h     # Core debugger controller & JSON session exporter
│   ├── process_manager.c/.h# fork(), execvp(), waitpid(WNOHANG), timing & /proc polling
│   ├── process_monitor.c/.h# /proc/<pid>/status, /proc/<pid>/stat, /proc/<pid>/fd reader
│   ├── tracer.c / .h       # strace log analyzer & loader-noise filter
│   ├── error_analyzer.c/.h # POSIX errno & signal lookup tables
│   └── logger.c / .h       # Diagnostic text report writer
├── autodebug_src/
│   ├── auto_main.c         # CLI entry point for ./autodebug
│   ├── auto_debug.c / .h   # 6-stage automated debugger + batch GDB analyzer
│   └── Makefile
├── ldst.c                  # Interactive terminal menu launcher (./ldst)
├── tests/                  # Official built-in C test cases + custom user .c programs
│   ├── normal_test.c       # Clean run, exit code 0
│   ├── file_error.c        # Missing file, ENOENT, exit code 1
│   ├── invalid_fd.c        # Bad file descriptor, EBADF, exit code 1
│   ├── permission_error.c  # Permission denied, EACCES, exit code 1
│   ├── system_call_error.c # System call failure handled, exit code 0
│   ├── abnormal_exit.c     # Signal termination, raise(SIGTERM)
│   ├── segmentation_fault.c# Null pointer dereference (*ptr = 42), SIGSEGV
│   ├── math_step.c         # Local variables (a, b, c) stepping & sum calculation
│   ├── function_call.c     # Step into add(), function arguments, call stack, step out
│   ├── sigfpe_test.c       # Division by zero (42 / 0), SIGFPE hardware trap
│   └── nonzero_exit.c      # Deliberate exit status 42 (distinguished from crash)
├── web/
│   ├── app.py              # Local web server (127.0.0.1:5000) & REST API routes
│   ├── services/
│   │   ├── security.py     # Path confinement, filename validation & tool checks
│   │   ├── compiler.py     # Real GCC compilation & diagnostic line parser
│   │   ├── interactive_debugger.py # Interactive GDB/MI source-level stepping engine
│   │   ├── debugger.py     # Batch debugger runner & session lifecycle
│   │   ├── autodebugger.py # AutoDebugger runner & GDB crash analyzer
│   │   ├── trace_parser.py # strace parser, errno grouping & source attribution
│   │   ├── process_monitor.py # Live /proc timeline sampler & host telemetry
│   │   └── reports.py      # JSON & TXT report persistence and export
│   ├── templates/
│   │   ├── landing.html    # Landing page
│   │   └── dashboard.html  # Application workspace shell
│   └── static/
│       ├── css/main.css    # Dark developer design system
│       ├── js/app.js       # Workspace frontend logic
│       └── images/         # 5 visual assets
├── traces/                 # Captured strace logs
├── reports/                # Persisted structured JSON & TXT diagnostic reports
├── logs/                   # Runtime logs & GDB outputs
├── results/                # CLI debugger & AutoDebugger text reports
├── docs/                   # Architectural & course-outcome notes
├── Makefile
├── setup.sh
├── run.sh
├── selftest.sh
└── README.md
```

---

## Self-Test & Regression Verification

Run the automated self-test suite to verify clean C compilation, all built-in error/signal detections (`ENOENT`, `EBADF`, `EACCES`, `SIGTERM`, `SIGSEGV`), GDB crash backtraces, custom C compilation, stale-binary protection, path-traversal prevention, report lifecycle, and HTTP API health:

```bash
./selftest.sh
```

---

## Troubleshooting & Known Limitations

- **`strace` or `gdb` missing**: Install on Ubuntu using `sudo apt install strace gdb`. The UI and CLI gracefully detect missing tools and display installation instructions.
- **Very short-lived C programs**: Minimal C programs often finish execution in `< 5 ms`. LDST captures an immediate `/proc` snapshot right after `fork()` in C so peak `VmSize`/`VmRSS` are recorded, and truthfully notes when a process completed within a single sampling window rather than fabricating extra chart points.
- **Port 5000 already in use**: Start on an alternate port with `LDST_PORT=5050 ./run.sh`.

# Linux System Debugging Tool 3.0

An interactive source-level C debugger, compiler diagnostics workbench, and forensic crash analysis environment for Linux systems.

---

## Overview & Architecture

The **Linux System Debugging Tool** connects source-level editing directly to underlying Linux compilers (`gcc`, `clang`), native debugging engines (`gdb` via Machine Interface MI3/MI2), system-call instrumentation (`strace`), and the Linux `/proc` filesystem.

```
                      +---------------------------------------+
                      |       React 19 + TypeScript GUI       |
                      |  (Monaco Editor, xterm.js, Split Panes)|
                      +---------------------------------------+
                                          |
                              WebSocket & REST API
                                          |
                      +---------------------------------------+
                      |         FastAPI Python Engine         |
                      |  (Session Controller, Workspace Mgt)  |
                      +---------------------------------------+
                             /            |             \
            GDB MI3 Protocol        GCC / Clang         strace / /proc
                           /              |              \
                +-------------+    +-------------+   +-------------------+
                | GDB Engine  |    | Diagnostics |   | Native Execution  |
                |  (Inferior) |    | & -fanalyzer|   | (libldstnative.so)|
                +-------------+    +-------------+   +-------------------+
```

---

## Workbench Capabilities

1. **Interactive Source-Level Debugging**
   - Direct execution control: Start, Step Over (`-exec-next`), Step Into (`-exec-step`), Step Out (`-exec-finish`), Continue (`-exec-continue`), Pause (`SIGINT`), Run to Cursor (`-exec-until`), and Clean Termination.
   - GDB Breakpoint Controller: Line breakpoints, function breakpoints, conditional breakpoints, hit counters, and dynamic enable/disable.
   - Live Inspection: Frame variables, function arguments, pointer dereferencing with NULL detection, watch expressions evaluated on stop, and bounded hex memory viewer (`-data-read-memory-bytes`).
   - Call Stack Navigator: Full stack-frame levels, source mapping, and frame switching (`-stack-select-frame`).

2. **Full C Project Inspection & Compilation**
   - Single-file, multi-file automatic compilation, and native `Makefile` projects.
   - Compiler Diagnostics Parser: Captures GCC/Clang syntax errors, type mismatches, missing semicolons, undeclared symbols, and linker failures with file, line, and column markers.
   - Static Analysis (`-fanalyzer`): Identifies NULL pointer dereferences, double-free risks, use-after-free, memory leaks, and uninitialized variable usage before execution.

3. **AutoDebugger Automated Diagnostic Engine**
   - 6-stage automated pipeline: Project validation, debug build with symbols (`-g -O0`), static analysis, GDB execution, signal/exit trapping, and system call tracing (`strace`).
   - Forensic crash diagnosis for `SIGSEGV`, `SIGFPE`, `SIGABRT`, `SIGILL`, and non-zero exit terminations with confidence ratings and actionable remedies.

4. **Interactive Terminal (PTY / WebSocket)**
   - Bidirectional terminal backed by real standard I/O streaming into `xterm.js`. Supports `scanf()`, `fgets()`, arguments, and interactive terminal loops.

5. **Logic Bug Test Cases & Fix Verification**
   - Define custom test suites with arguments, standard input, expected output, and expected exit codes.
   - Output diff viewer comparing expected vs actual stdout.
   - Regression verification engine comparing pre-fix and post-fix execution results.

6. **SQLite Session Persistence & Reports**
   - Preserves complete session snapshots, breakpoints, timelines, and diagnostic findings.
   - Export structured reports in JSON and Markdown.

---

## Directory Structure

```text
Linux-System-Debugging-Tool/
│
├── frontend/                     # React 19 + TypeScript + Vite Workbench
│   ├── src/
│   │   ├── components/           # Header, Sidebar, Split Panes
│   │   ├── screens/              # 10 Workbench Screens
│   │   ├── services/             # API Client & WebSocket Bridge
│   │   └── types/                # TypeScript Interfaces
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                      # FastAPI Python Application
│   ├── app/
│   │   ├── api/                  # REST & WebSocket Endpoints
│   │   ├── debugger/             # GDB MI3 Engine, Tokenized Dispatch, Terminal
│   │   ├── compiler/             # Build System & Diagnostics Parser
│   │   ├── analysis/             # Project Scanner & GCC -fanalyzer Integration
│   │   ├── diagnostics/          # AutoDebugger & Forensic Crash Investigator
│   │   ├── tracing/              # strace Runner & Errno Decoder
│   │   ├── verification/         # Test Case Runner & Fix Verifier
│   │   ├── workspace/            # Project Workspace CRUD & Safe Zip Import
│   │   ├── storage/              # SQLite Session & Test Persistence
│   │   └── security/             # Path Traversal & Sandbox Protection
│   └── requirements.txt
│
├── native/                       # Native Linux C Layer
│   ├── process_launcher.c        # Process Spawning & Resource Limits (RLIMIT)
│   ├── process_status.c          # /proc Status & Metric Inspection
│   ├── signal_handler.c          # Signal Decoding & Fault Cause Mapping
│   └── Makefile
│
├── tests/                        # Automated Pytest Suite
│   ├── unit/                     # Unit Tests (MI Parser, Diagnostics, Security)
│   ├── integration/              # Integration Tests (GDB, AutoDebug, Crashes)
│   └── fixtures/                 # Real C Test Fixtures
│       ├── compiler_errors/
│       ├── logical_errors/
│       ├── runtime_crashes/
│       └── multi_file_projects/
│
├── scripts/                      # Setup & Launch Scripts
│   ├── setup_linux.sh
│   ├── start_dev.sh
│   └── start_prod.sh
│
├── run.sh                        # Main Workbench Launcher
└── setup.sh                      # Environment Bootstrap Script
```

---

## Installation & Setup

### Requirements

- **Operating System:** Linux (Ubuntu 22.04 / 24.04 recommended) or Windows with WSL2 (Ubuntu).
- **Compilers & Tools:** `gcc`, `gdb` (>= 12.0), `make`, `strace`.
- **Runtimes:** Python 3.10+ and Node.js 18+.

### Setup on Linux / WSL

```bash
# 1. Clone repository
git clone https://github.com/Rawhide-nihal/Linux-System-Debugging-Tool.git
cd Linux-System-Debugging-Tool

# 2. Run automated setup script
chmod +x setup.sh run.sh
./setup.sh
```

### Running the Workbench

```bash
# Launch application server (FastAPI + React bundle on http://127.0.0.1:8000)
./run.sh
```

### Development Mode (Hot Reload)

```bash
# In terminal 1 (Backend API):
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

# In terminal 2 (Vite Frontend):
cd frontend && npm run dev
```

---

## Running Automated Tests

Run the complete test suite (unit and integration tests against real C binaries and GDB sessions):

```bash
python3 -m pytest tests/ -v
```

---

## Security Model

- **Path Traversal Protection:** All workspace file operations resolve strictly within the project directory. Traversal attacks (`../../etc/passwd`, absolute root paths, or zip-slip archives) are blocked and rejected.
- **Controlled Process Execution:** Executables run in dedicated subprocess groups with `RLIMIT_CPU`, `RLIMIT_AS` memory restrictions, and execution timeouts.
- **Safe Network Binding:** Development servers bind to `127.0.0.1` (loopback) by default.

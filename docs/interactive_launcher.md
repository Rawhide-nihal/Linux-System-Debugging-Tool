# Interactive Launcher

The project is started through the single command:

```bash
./ldst
```

The launcher is a terminal-based project interface written in C. It keeps the project focused on Linux and Operating Systems concepts while removing the need to remember separate commands for normal demonstrations.

## Main menu

1. **Run Debugger** – selects one controlled test and runs the existing debugger.
2. **Run AutoDebugger** – selects one controlled test and runs automatic trace/error diagnosis.
3. **Run Test Program** – executes a selected test directly so its raw behavior can be demonstrated.
4. **View Latest Diagnosis** – opens the latest AutoDebugger report.
5. **View System Call Trace** – opens the latest `strace` evidence file.
6. **View Process Information** – displays a live Linux process snapshot using `ps`.
7. **Run Complete Demonstration** – runs all controlled tests through AutoDebugger.
8. **Exit** – closes the application.

The launcher automatically checks/builds the required executables and test programs before a debugging action.

## Project flow

```text
./ldst
   |
   +-- Debugger --------> process management + tracing + report
   |
   +-- AutoDebugger ----> strace -> failure detection -> diagnosis -> recommendation
   |                         |
   |                         +--> GDB for supported crash signals
   |
   +-- Test Program ----> controlled runtime behavior
   |
   +-- Reports/Trace ----> logs/ and results/
```

The interface is a terminal UI, not a separate web or GUI application. This keeps the implementation aligned with the Linux C / Systems Programming project scope.

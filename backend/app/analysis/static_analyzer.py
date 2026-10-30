"""
Linux System Debugging Tool - Static Bug Detection Engine
Integrates GCC -fanalyzer to discover memory leaks, double-frees, null pointer dereferences,
uninitialized variables, and suspicious control flow across C source files.
"""

from pathlib import Path
from typing import List, Dict, Any
from ..config import toolchain
from ..compiler.diagnostics_parser import parse_compiler_output


def run_static_analysis(workspace_path: str, target_file: str = "") -> List[Dict[str, Any]]:
    """Runs GCC -fanalyzer on target source file or all C files in workspace."""
    ws = Path(workspace_path).resolve()

    c_files = []
    if target_file:
        tf = ws / target_file
        if tf.is_file():
            c_files.append(tf)

    if not c_files:
        for p in ws.rglob("*.c"):
            if not any(part.startswith(".") for part in p.parts):
                c_files.append(p)

    if not c_files:
        return []

    findings: List[Dict[str, Any]] = []

    # Run GCC with -fanalyzer in syntax-only check mode (-fsyntax-only)
    for cf in c_files:
        rel_cf = str(cf.relative_to(ws))
        cmd = [
            "gcc",
            "-fanalyzer",
            "-fsyntax-only",
            "-Wall",
            "-Wextra",
            "-I.",
            rel_cf
        ]

        ret, out, err = toolchain.run_tool_cmd(cmd, cwd=str(ws), timeout=25)
        combined = f"{out}\n{err}"
        diagnostics = parse_compiler_output(combined)

        for diag in diagnostics:
            # Classify analyzer warnings
            msg = diag["message"].lower()
            kind = "static_analysis"
            if "dereference of null" in msg or "null-pointer" in msg:
                kind = "null_pointer_dereference"
            elif "uninitialized" in msg:
                kind = "uninitialized_variable"
            elif "leak" in msg:
                kind = "memory_leak"
            elif "double-'free'" in msg or "double free" in msg:
                kind = "double_free"
            elif "use after 'free'" in msg or "use-after-free" in msg:
                kind = "use_after_free"
            elif "out-of-bounds" in msg or "buffer overflow" in msg:
                kind = "buffer_overflow"

            diag["category"] = "analyzer"
            diag["analysis_kind"] = kind
            findings.append(diag)

    return findings

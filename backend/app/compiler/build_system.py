"""
Linux System Debugging Tool - Build System & Compilation Controller
Executes GCC/Clang/Make builds, generates debug-symbol binaries, and captures diagnostics.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import toolchain
from .diagnostics_parser import parse_compiler_output


class BuildResult:
    def __init__(self, success: bool, returncode: int, binary_path: Optional[str],
                 command: str, stdout: str, stderr: str, diagnostics: List[Dict[str, Any]]):
        self.success = success
        self.returncode = returncode
        self.binary_path = binary_path
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.diagnostics = diagnostics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "returncode": self.returncode,
            "binary_path": self.binary_path,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "diagnostics": self.diagnostics
        }


def compile_project(workspace_path: str, config: Optional[Dict[str, Any]] = None) -> BuildResult:
    """
    Builds the C project within workspace_path according to configuration.
    Supports single-file, multi-file automatic compilation, and Makefile builds.
    """
    ws = Path(workspace_path).resolve()
    cfg = config or {}

    compiler = cfg.get("compiler", "gcc")
    std = cfg.get("std", "c11")
    opt = cfg.get("optimization", "0") # -O0 for debugging
    cflags = cfg.get("cflags", ["-Wall", "-Wextra", "-g", f"-O{opt}", f"-std={std}", "-fno-omit-frame-pointer"])
    ldflags = cfg.get("ldflags", ["-lm"])
    target_name = cfg.get("target_name", "app_debug")
    build_mode = cfg.get("build_mode", "auto") # "auto", "makefile", "single_file", "multi_file"
    selected_file = cfg.get("selected_file")

    output_binary = ws / target_name

    # Check for Makefile if build_mode is auto or makefile
    makefile_exists = (ws / "Makefile").is_file() or (ws / "makefile").is_file()
    if build_mode == "makefile" or (build_mode == "auto" and makefile_exists and not selected_file):
        cmd = ["make"]
        clean_ret, _, _ = toolchain.run_tool_cmd(["make", "clean"], cwd=str(ws), timeout=15)
        ret, out, err = toolchain.run_tool_cmd(cmd, cwd=str(ws), timeout=45)
        combined_output = f"{out}\n{err}"
        diagnostics = parse_compiler_output(combined_output)
        
        # Check if output binary exists (or common targets like target_name, main, etc.)
        bin_path = str(output_binary) if output_binary.is_file() else None
        if not bin_path:
            # Check for any executable in workspace
            for item in ws.iterdir():
                if item.is_file() and os.access(item, os.X_OK) and not item.name.endswith(('.c', '.h', '.o', '.sh', '.py')):
                    bin_path = str(item)
                    break

        return BuildResult(
            success=(ret == 0 and bin_path is not None),
            returncode=ret,
            binary_path=bin_path,
            command="make",
            stdout=out,
            stderr=err,
            diagnostics=diagnostics
        )

    # File compilation (single or multi)
    c_files: List[Path] = []
    if selected_file:
        cand = ws / selected_file
        if cand.is_file():
            c_files.append(cand)
    
    if not c_files:
        # Discover all .c files in workspace
        for p in ws.rglob("*.c"):
            if not any(part.startswith(".") for part in p.parts):
                c_files.append(p)

    if not c_files:
        return BuildResult(
            success=False,
            returncode=-1,
            binary_path=None,
            command="",
            stdout="",
            stderr="No C source files (.c) found to compile in this workspace.",
            diagnostics=[]
        )

    cmd = [compiler] + cflags
    # Relative paths for readability
    for cf in c_files:
        try:
            cmd.append(str(cf.relative_to(ws)))
        except ValueError:
            cmd.append(str(cf))

    cmd.extend(["-o", target_name])
    cmd.extend(ldflags)

    ret, out, err = toolchain.run_tool_cmd(cmd, cwd=str(ws), timeout=30)
    combined_output = f"{out}\n{err}"
    diagnostics = parse_compiler_output(combined_output)

    bin_path = str(output_binary) if (ret == 0 and output_binary.is_file()) else None

    return BuildResult(
        success=(ret == 0 and bin_path is not None),
        returncode=ret,
        binary_path=bin_path,
        command=" ".join(cmd),
        stdout=out,
        stderr=err,
        diagnostics=diagnostics
    )

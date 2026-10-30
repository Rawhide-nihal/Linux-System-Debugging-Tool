"""
Linux System Debugging Tool - Configuration & Environment Toolchain Bridge
Handles tool discovery (GCC, GDB, strace, make, clang, valgrind) across native Linux and WSL.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACES_DIR = BASE_DIR / "workspaces"
STORAGE_DIR = BASE_DIR / "storage_data"
LOGS_DIR = STORAGE_DIR / "logs"
TRACES_DIR = STORAGE_DIR / "traces"
REPORTS_DIR = STORAGE_DIR / "reports"
DB_PATH = STORAGE_DIR / "debugger.db"

# Ensure runtime directories exist
for d in (WORKSPACES_DIR, STORAGE_DIR, LOGS_DIR, TRACES_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


class ToolchainDetector:
    """Detects available compilers, debuggers, and tracing tools."""

    def __init__(self):
        self.is_linux = sys.platform.startswith("linux")
        self.has_wsl = False
        if not self.is_linux:
            self.has_wsl = self._check_wsl_available()

    def _check_wsl_available(self) -> bool:
        # Check if WSL executable is on PATH first
        if not shutil.which("wsl"):
            return False
        try:
            res = subprocess.run(
                ["wsl", "-d", "Ubuntu", "--", "which", "gcc"],
                capture_output=True,
                text=True,
                timeout=15
            )
            return res.returncode == 0
        except Exception:
            return False

    def run_tool_cmd(self, cmd_args: List[str], cwd: Optional[str] = None, timeout: float = 30.0) -> Tuple[int, str, str]:
        """
        Executes a toolchain command.
        If running natively on Linux or MinGW/native toolchain is available, runs directly.
        If running on Windows and WSL is present, executes inside WSL with path translation.
        """
        if self.is_linux or (not self.has_wsl and shutil.which(cmd_args[0])):
            try:
                proc = subprocess.run(
                    cmd_args,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    errors="replace"
                )
                return proc.returncode, proc.stdout, proc.stderr
            except subprocess.TimeoutExpired:
                return -1, "", f"Command timed out after {timeout}s"
            except Exception as e:
                return -1, "", str(e)
        elif self.has_wsl:
            # Run via WSL Ubuntu
            wsl_cwd = self.to_wsl_path(cwd) if cwd else None
            wsl_cmd = ["wsl", "-d", "Ubuntu"]
            if wsl_cwd:
                wsl_cmd.extend(["--cd", wsl_cwd])
            wsl_cmd.append("--")
            wsl_cmd.extend(cmd_args)
            try:
                proc = subprocess.run(
                    wsl_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    errors="replace"
                )
                return proc.returncode, proc.stdout, proc.stderr
            except subprocess.TimeoutExpired:
                return -1, "", f"Command timed out after {timeout}s"
            except Exception as e:
                return -1, "", str(e)
        else:
            return -1, "", f"Tool '{cmd_args[0]}' not available in host or WSL environment."

    def to_wsl_path(self, win_path: str) -> str:
        """Translate a Windows path (e.g. C:\\Users\\...) to WSL path (/mnt/c/Users/...)."""
        if not win_path:
            return win_path
        p = Path(win_path).resolve()
        drive = p.drive.replace(":", "").lower()
        rest = p.as_posix().split(":", 1)[-1]
        return f"/mnt/{drive}{rest}"

    def to_host_path(self, wsl_path: str) -> str:
        """Translate a WSL path (/mnt/c/...) back to Windows path (C:\\...)."""
        if not wsl_path or not wsl_path.startswith("/mnt/"):
            return wsl_path
        parts = wsl_path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "mnt":
            drive = parts[1].upper()
            rest = "\\".join(parts[2:])
            return f"{drive}:\\{rest}"
        return wsl_path

    def detect_all(self) -> Dict[str, Any]:
        """Detect and return full toolchain versions and capabilities."""
        tools = {
            "platform": "Linux (Native)" if self.is_linux else ("WSL (Ubuntu)" if self.has_wsl else "Windows (Host)"),
            "gcc": self._get_tool_info("gcc"),
            "gdb": self._get_tool_info("gdb"),
            "make": self._get_tool_info("make"),
            "strace": self._get_tool_info("strace"),
            "clang": self._get_tool_info("clang"),
            "valgrind": self._get_tool_info("valgrind")
        }
        tools["ready"] = bool(tools["gcc"]["available"] and tools["gdb"]["available"])
        return tools

    def _get_tool_info(self, name: str) -> Dict[str, Any]:
        ret, out, err = self.run_tool_cmd(["which", name])
        if ret != 0:
            return {"available": False, "path": None, "version": None}
        path = out.strip().splitlines()[0] if out.strip() else None
        ver_ret, ver_out, _ = self.run_tool_cmd([name, "--version"])
        ver = ver_out.strip().splitlines()[0] if (ver_ret == 0 and ver_out.strip()) else None
        return {"available": True, "path": path, "version": ver}


toolchain = ToolchainDetector()

"""
Linux System Debugging Tool - Settings & Environment Diagnostics API Routes
Detects and validates Linux toolchain (GCC, GDB, strace, clang, valgrind, make).
"""

from fastapi import APIRouter
from typing import Dict, Any

from ..config import toolchain

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/toolchain")
def get_toolchain_info() -> Dict[str, Any]:
    """Returns detected compiler, debugger, and tracing tool versions and readiness."""
    return toolchain.detect_all()

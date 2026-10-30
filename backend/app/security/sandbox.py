"""
Linux System Debugging Tool - Security & Workspace Sandbox
Prevents directory traversal, zip-slip vulnerabilities, and handles execution policies.
"""

import os
import zipfile
from pathlib import Path
from typing import Optional, Union


def is_safe_subpath(base_dir: Union[str, Path], target_path: Union[str, Path]) -> bool:
    """Verifies that target_path resolves strictly within base_dir."""
    try:
        base = Path(base_dir).resolve()
        target = Path(target_path).resolve()
        return base in target.parents or base == target
    except Exception:
        return False


def resolve_safe_path(base_dir: Union[str, Path], relative_path: str) -> Optional[Path]:
    """Resolves relative_path within base_dir. Returns None if it escapes or attempts absolute access."""
    if not relative_path or not isinstance(relative_path, str):
        return None
    # Reject leading slashes and drive letters as illegal attempts to escape workspace
    if relative_path.startswith("/") or relative_path.startswith("\\") or ":" in relative_path:
        return None
    base = Path(base_dir).resolve()
    target = (base / relative_path).resolve()
    if base in target.parents or base == target:
        return target
    return None


def extract_zip_safely(zip_file_path: Union[str, Path], dest_dir: Union[str, Path]) -> bool:
    """Extracts a ZIP archive while protecting against Zip Slip path traversal."""
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_file_path, "r") as zf:
        for member in zf.infolist():
            member_path = (dest / member.filename).resolve()
            if not is_safe_subpath(dest, member_path):
                raise ValueError(f"Malicious zip entry detected: {member.filename}")
        zf.extractall(dest)
    return True

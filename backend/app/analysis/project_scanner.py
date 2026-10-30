"""
Linux System Debugging Tool - Project Scanner & Source Tree Builder
Recursively discovers source files (.c, .h), Makefiles, and builds structured directory trees.
"""

import os
from pathlib import Path
from typing import Dict, Any, List


def scan_workspace_tree(workspace_path: str) -> Dict[str, Any]:
    """Scans workspace directory and returns hierarchical file tree and metadata."""
    ws = Path(workspace_path).resolve()
    if not ws.is_dir():
        return {"name": "Workspace", "path": str(ws), "type": "directory", "children": [], "stats": {}}

    ignored_dirs = {".git", ".venv", "venv", "__pycache__", "build", "dist", ".idea", ".vscode"}

    total_c_files = 0
    total_h_files = 0
    total_size = 0

    def build_node(p: Path) -> Dict[str, Any]:
        nonlocal total_c_files, total_h_files, total_size

        is_dir = p.is_dir()
        name = p.name
        rel_path = str(p.relative_to(ws)).replace("\\", "/")

        if is_dir:
            children = []
            try:
                for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    if entry.name in ignored_dirs or entry.name.startswith("."):
                        continue
                    children.append(build_node(entry))
            except PermissionError:
                pass

            return {
                "name": name,
                "path": rel_path if rel_path != "." else "",
                "type": "directory",
                "children": children
            }
        else:
            size = p.stat().st_size
            total_size += size
            ext = p.suffix.lower()
            if ext == ".c":
                total_c_files += 1
            elif ext == ".h":
                total_h_files += 1

            return {
                "name": name,
                "path": rel_path,
                "type": "file",
                "size": size,
                "extension": ext
            }

    tree = build_node(ws)
    tree["stats"] = {
        "c_files": total_c_files,
        "h_files": total_h_files,
        "total_size_bytes": total_size
    }
    return tree

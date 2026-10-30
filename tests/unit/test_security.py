"""
Unit tests for Security Sandbox and Path Traversal Protection.
"""

from pathlib import Path
from backend.app.security.sandbox import is_safe_subpath, resolve_safe_path


def test_safe_path_valid(tmp_path):
    sub = tmp_path / "src" / "main.c"
    sub.parent.mkdir(parents=True)
    sub.write_text("int main() {}")

    assert is_safe_subpath(tmp_path, sub) is True
    resolved = resolve_safe_path(tmp_path, "src/main.c")
    assert resolved is not None
    assert resolved == sub


def test_path_traversal_blocked(tmp_path):
    assert is_safe_subpath(tmp_path, tmp_path / ".." / "etc" / "passwd") is False
    assert resolve_safe_path(tmp_path, "../../etc/passwd") is None
    assert resolve_safe_path(tmp_path, "/etc/shadow") is None

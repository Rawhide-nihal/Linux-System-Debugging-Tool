"""
Unit tests for Workspace Creation, Templates, and File Operations.
"""

from backend.app.workspace.manager import WorkspaceManager
from backend.app.storage.db import StorageService


def test_create_workspace_from_template():
    ws = WorkspaceManager.create_workspace("Test Project", "basic_app")
    assert ws["id"].startswith("ws_")
    assert ws["name"] == "Test Project"
    
    # Read created main.c
    content = WorkspaceManager.read_file(ws["path"], "main.c")
    assert content is not None
    assert "factorial" in content

    # Clean up
    StorageService.delete_workspace(ws["id"])

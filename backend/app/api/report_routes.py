"""
Linux System Debugging Tool - Reports API Routes
Exports and retrieves structured diagnostic reports.
"""

from fastapi import APIRouter, HTTPException, Response
from typing import Optional

from ..storage.db import StorageService
from ..reports.generator import generate_markdown_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/")
def list_reports(workspace_id: Optional[str] = None):
    return StorageService.list_reports(workspace_id)


@router.get("/{report_id}")
def get_report(report_id: str):
    reports = StorageService.list_reports()
    for r in reports:
        if r["id"] == report_id:
            return r
    raise HTTPException(status_code=404, detail="Report not found")


@router.get("/{report_id}/export/markdown")
def export_report_markdown(report_id: str):
    reports = StorageService.list_reports()
    for r in reports:
        if r["id"] == report_id:
            md_text = generate_markdown_report(r)
            return Response(content=md_text, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="Report not found")

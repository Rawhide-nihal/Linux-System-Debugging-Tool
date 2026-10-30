"""
Linux System Debugging Tool - Diagnostic Report Generator
Produces exportable Markdown, JSON, and text reports distinguishing observed evidence from diagnostics.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List


def generate_markdown_report(report_data: Dict[str, Any]) -> str:
    """Formats diagnostic session findings into clean, readable Markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    title = report_data.get("title", "Debugging Diagnostic Report")
    summary = report_data.get("summary", "Automated system diagnostics run.")
    findings = report_data.get("findings", [])

    lines = [
        f"# {title}",
        f"**Generated:** {now}  ",
        f"**Status:** {report_data.get('verdict', 'COMPLETED')}  ",
        "",
        "## Executive Summary",
        summary,
        "",
        "## Diagnostic Findings",
    ]

    if not findings:
        lines.append("No critical defects or compilation errors detected in the tested execution paths.")
    else:
        for idx, f in enumerate(findings, 1):
            sev = f.get("severity", "INFO")
            lines.extend([
                f"### {idx}. [{sev}] {f.get('title', 'Diagnostic Item')}",
                f"- **Category:** `{f.get('category', 'GENERAL')}`",
                f"- **Location:** `{f.get('file', 'N/A')}` : Line {f.get('line', 'N/A')}",
                f"- **Confidence:** {f.get('confidence', 'HIGH')}",
                f"- **Observed Evidence:** {f.get('evidence', 'None recorded')}",
                f"- **Suggested Action:** {f.get('suggested_action', 'Review source code')}",
                ""
            ])

    return "\n".join(lines)

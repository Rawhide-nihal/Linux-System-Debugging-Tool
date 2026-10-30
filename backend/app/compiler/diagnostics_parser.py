"""
Linux System Debugging Tool - Compiler Diagnostics Parser
Extracts structured problems (errors, warnings, notes, linker errors) from GCC & Clang outputs.
"""

import re
from typing import List, Dict, Any, Optional

DIAG_PATTERN = re.compile(
    r"^(?P<file>[^:\n\r]+):(?P<line>\d+):(?P<col>\d+):\s+(?P<severity>fatal error|error|warning|note):\s+(?P<message>.*)$",
    re.IGNORECASE
)

LINKER_PATTERN = re.compile(
    r"(undefined reference to ['`](?P<symbol>[^'`]+)['`]|collect2: error: ld returned \d+ exit status|multiple definition of ['`](?P<mult_sym>[^'`]+)['`])",
    re.IGNORECASE
)


class DiagnosticItem:
    def __init__(self, file: str, line: Optional[int], col: Optional[int],
                 severity: str, message: str, raw_line: str,
                 category: str = "compilation", snippet: Optional[str] = None):
        self.file = file
        self.line = line
        self.col = col
        self.severity = severity.lower()
        self.message = message
        self.raw_line = raw_line
        self.category = category
        self.snippet = snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.col,
            "severity": self.severity,
            "message": self.message,
            "raw": self.raw_line,
            "category": self.category,
            "snippet": self.snippet
        }


def parse_compiler_output(output: str) -> List[Dict[str, Any]]:
    """Parses raw stdout/stderr from GCC or Clang into structured diagnostic objects."""
    diagnostics: List[DiagnosticItem] = []
    lines = output.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        match = DIAG_PATTERN.match(line)
        if match:
            f = match.group("file").strip()
            l = int(match.group("line"))
            c = int(match.group("col"))
            sev = match.group("severity")
            msg = match.group("message").strip()

            snippet = None
            # Check if next line contains source code context (compiler caret)
            if i + 1 < len(lines) and not DIAG_PATTERN.match(lines[i + 1]):
                next_l = lines[i + 1]
                if not next_l.startswith("make:") and not next_l.startswith("gcc:"):
                    snippet = next_l
                    if i + 2 < len(lines) and "^" in lines[i + 2]:
                        snippet += "\n" + lines[i + 2]
                        i += 1
                    i += 1

            diagnostics.append(DiagnosticItem(
                file=f,
                line=l,
                col=c,
                severity="error" if "error" in sev.lower() else ("warning" if "warning" in sev.lower() else "note"),
                message=msg,
                raw_line=line,
                category="compiler",
                snippet=snippet
            ))
        else:
            link_match = LINKER_PATTERN.search(line)
            if link_match:
                sym = link_match.group("symbol") or link_match.group("mult_sym")
                msg = f"Linker error: undefined reference to '{sym}'" if sym else line.strip()
                diagnostics.append(DiagnosticItem(
                    file="linker",
                    line=None,
                    col=None,
                    severity="error",
                    message=msg,
                    raw_line=line,
                    category="linker"
                ))
        i += 1

    return [d.to_dict() for d in diagnostics]

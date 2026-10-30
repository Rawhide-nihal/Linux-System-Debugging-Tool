"""
Linux System Debugging Tool - Workspace Manager & Template Generator
Handles multi-file projects, file system CRUD, full-text source search, and safe templates.
"""

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import WORKSPACES_DIR
from ..security.sandbox import is_safe_subpath, resolve_safe_path, extract_zip_safely
from ..analysis.project_scanner import scan_workspace_tree
from ..storage.db import StorageService


TEMPLATES = {
    "basic_app": {
        "name": "Single-File C Program",
        "files": {
            "main.c": """#include <stdio.h>

int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main(int argc, char *argv[]) {
    int num = 5;
    int res = factorial(num);
    printf("Factorial of %d is %d\\n", num, res);
    return 0;
}
"""
        }
    },
    "multi_file_calc": {
        "name": "Multi-File Modular Project",
        "files": {
            "calc.h": """#ifndef CALC_H
#define CALC_H

int add(int a, int b);
int multiply(int a, int b);
int compute_series(int count);

#endif // CALC_H
""",
            "calc.c": """#include "calc.h"

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

int compute_series(int count) {
    int sum = 0;
    for (int i = 1; i <= count; i++) {
        sum = add(sum, multiply(i, 2));
    }
    return sum;
}
""",
            "main.c": """#include <stdio.h>
#include "calc.h"

int main() {
    int terms = 4;
    int result = compute_series(terms);
    printf("Series sum for %d terms: %d\\n", terms, result);
    return 0;
}
""",
            "Makefile": """CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11

all: app_debug

app_debug: main.o calc.o
	$(CC) $(CFLAGS) -o $@ $^

main.o: main.c calc.h
	$(CC) $(CFLAGS) -c $< -o $@

calc.o: calc.c calc.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o app_debug

.PHONY: all clean
"""
        }
    },
    "segfault_repro": {
        "name": "Pointer Crash Reproducer",
        "files": {
            "main.c": """#include <stdio.h>
#include <stdlib.h>

struct UserRecord {
    int id;
    char name[32];
    int score;
};

void print_user(struct UserRecord *u) {
    // Intentionally dereferencing pointer without NULL check
    printf("User ID: %d, Score: %d\\n", u->id, u->score);
}

int main() {
    printf("[*] Initializing records...\\n");
    struct UserRecord *rec = NULL; // Unallocated pointer

    printf("[*] Attempting to print user data...\\n");
    print_user(rec); // Causes SIGSEGV

    return 0;
}
"""
        }
    },
    "logic_bug_boundary": {
        "name": "Boundary Logic Bug Target",
        "files": {
            "main.c": """#include <stdio.h>

/*
 * Specification: A student PASSES if marks >= 35.
 * Bug: The developer incorrectly wrote marks > 35.
 * Therefore a student with exactly 35 marks fails!
 */
int is_passing(int marks) {
    return marks > 35; // Logic Bug: should be marks >= 35
}

int main(int argc, char *argv[]) {
    int marks = 0;
    if (scanf("%d", &marks) != 1) {
        printf("Invalid input\\n");
        return 1;
    }

    if (is_passing(marks)) {
        printf("PASS\\n");
    } else {
        printf("FAIL\\n");
    }
    return 0;
}
"""
        }
    },
    "interactive_menu": {
        "name": "Interactive Terminal I/O Menu",
        "files": {
            "main.c": """#include <stdio.h>

int main() {
    int choice = 0;
    int balance = 1000;

    printf("=== Simple Terminal Banking App ===\\n");
    while (1) {
        printf("\\nOptions: [1] Check Balance  [2] Deposit  [3] Exit\\n");
        printf("Enter choice: ");
        if (scanf("%d", &choice) != 1) break;

        if (choice == 1) {
            printf("Current Balance: $%d\\n", balance);
        } else if (choice == 2) {
            int amount = 0;
            printf("Enter amount to deposit: ");
            scanf("%d", &amount);
            if (amount > 0) {
                balance += amount;
                printf("Deposited $%d. New Balance: $%d\\n", amount, balance);
            }
        } else if (choice == 3) {
            printf("Exiting banking session. Goodbye!\\n");
            break;
        } else {
            printf("Unknown option!\\n");
        }
    }
    return 0;
}
"""
        }
    }
}


class WorkspaceManager:

    @staticmethod
    def create_workspace(name: str, template: Optional[str] = "basic_app") -> Dict[str, Any]:
        ws_id = f"ws_{uuid.uuid4().hex[:10]}"
        ws_path = WORKSPACES_DIR / ws_id
        ws_path.mkdir(parents=True, exist_ok=True)

        config = {
            "compiler": "gcc",
            "std": "c11",
            "optimization": "0",
            "cflags": ["-Wall", "-Wextra", "-g", "-O0", "-std=c11", "-fno-omit-frame-pointer"],
            "ldflags": ["-lm"],
            "target_name": "app_debug",
            "build_mode": "auto"
        }

        # Populate with template files if selected
        if template and template in TEMPLATES:
            tpl = TEMPLATES[template]
            for rel_file, content in tpl["files"].items():
                dest = ws_path / rel_file
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

        StorageService.save_workspace(ws_id, name, str(ws_path), config)

        # Seed initial test case if logic_bug_boundary template was chosen
        if template == "logic_bug_boundary":
            StorageService.save_test_case(
                tc_id=f"tc_{uuid.uuid4().hex[:8]}",
                ws_id=ws_id,
                name="Boundary Condition Check (35 marks)",
                args=[],
                stdin_data="35\n",
                expected_output="PASS\n",
                expected_exit_code=0
            )

        return {
            "id": ws_id,
            "name": name,
            "path": str(ws_path),
            "config": config,
            "tree": scan_workspace_tree(str(ws_path))
        }

    @staticmethod
    def import_zip(file_path: str, name: str) -> Dict[str, Any]:
        ws_id = f"ws_{uuid.uuid4().hex[:10]}"
        ws_path = WORKSPACES_DIR / ws_id
        ws_path.mkdir(parents=True, exist_ok=True)

        extract_zip_safely(file_path, ws_path)

        config = {
            "compiler": "gcc",
            "std": "c11",
            "optimization": "0",
            "cflags": ["-Wall", "-Wextra", "-g", "-O0", "-std=c11"],
            "ldflags": ["-lm"],
            "target_name": "app_debug",
            "build_mode": "auto"
        }

        StorageService.save_workspace(ws_id, name, str(ws_path), config)
        return {
            "id": ws_id,
            "name": name,
            "path": str(ws_path),
            "config": config,
            "tree": scan_workspace_tree(str(ws_path))
        }

    @staticmethod
    def read_file(workspace_path: str, relative_path: str) -> Optional[str]:
        target = resolve_safe_path(workspace_path, relative_path)
        if not target or not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def write_file(workspace_path: str, relative_path: str, content: str) -> bool:
        target = resolve_safe_path(workspace_path, relative_path)
        if not target:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    @staticmethod
    def delete_entry(workspace_path: str, relative_path: str) -> bool:
        target = resolve_safe_path(workspace_path, relative_path)
        if not target or not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return True

    @staticmethod
    def search_text(workspace_path: str, query: str) -> List[Dict[str, Any]]:
        ws = Path(workspace_path).resolve()
        matches = []
        if not query.strip():
            return matches

        for p in ws.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".c", ".h", ".txt", ".md", ".sh"):
                if any(part.startswith(".") for part in p.parts):
                    continue
                try:
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    for idx, line in enumerate(lines):
                        if query.lower() in line.lower():
                            matches.append({
                                "file": str(p.relative_to(ws)).replace("\\", "/"),
                                "line": idx + 1,
                                "content": line.strip()
                            })
                except Exception:
                    pass
        return matches

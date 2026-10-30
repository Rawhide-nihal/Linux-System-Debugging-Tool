"""
Unit tests for Compiler Diagnostics & Problem Extraction.
"""

from backend.app.compiler.diagnostics_parser import parse_compiler_output


def test_parse_syntax_error():
    output = "src/main.c:14:5: error: expected ';' before 'return'\n    return 0;\n    ^~~~~~"
    diagnostics = parse_compiler_output(output)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d["file"] == "src/main.c"
    assert d["line"] == 14
    assert d["column"] == 5
    assert d["severity"] == "error"
    assert "expected ';'" in d["message"]
    assert "return 0;" in d["snippet"]


def test_parse_compiler_warning():
    output = "calc.c:8:9: warning: unused variable 'unused_val' [-Wunused-variable]\n    int unused_val = 10;"
    diagnostics = parse_compiler_output(output)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d["severity"] == "warning"
    assert d["line"] == 8
    assert "unused variable" in d["message"]


def test_parse_linker_error():
    output = "/usr/bin/ld: main.o: in function 'main':\nmain.c:12: undefined reference to 'unresolved_symbol'\ncollect2: error: ld returned 1 exit status"
    diagnostics = parse_compiler_output(output)
    assert any(d["category"] == "linker" and "unresolved_symbol" in d["message"] for d in diagnostics)

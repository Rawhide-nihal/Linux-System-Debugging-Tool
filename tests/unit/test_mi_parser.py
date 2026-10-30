"""
Unit tests for GDB Machine Interface (MI3 / MI2) Protocol Parser.
"""

from backend.app.debugger.mi_parser import parse_mi_record


def test_parse_prompt():
    rec = parse_mi_record("(gdb)")
    assert rec is not None
    assert rec["type"] == "prompt"


def test_parse_result_done():
    rec = parse_mi_record("^done")
    assert rec is not None
    assert rec["type"] == "result"
    assert rec["class"] == "done"


def test_parse_tokenized_result():
    rec = parse_mi_record("105^done,value=\"42\"")
    assert rec is not None
    assert rec["token"] == 105
    assert rec["type"] == "result"
    assert rec["class"] == "done"
    assert rec["payload"]["value"] == "42"


def test_parse_async_stopped():
    line = '*stopped,reason="breakpoint-hit",disp="keep",bkptno="1",frame={func="main",args=[],file="main.c",line="15"}'
    rec = parse_mi_record(line)
    assert rec is not None
    assert rec["type"] == "exec_async"
    assert rec["class"] == "stopped"
    assert rec["payload"]["reason"] == "breakpoint-hit"
    assert rec["payload"]["bkptno"] == "1"
    frame = rec["payload"]["frame"]
    assert frame["func"] == "main"
    assert frame["file"] == "main.c"
    assert frame["line"] == "15"


def test_parse_stream_records():
    rec_c = parse_mi_record('~"GNU gdb (Ubuntu) 15.2\\n"')
    assert rec_c is not None
    assert rec_c["type"] == "console"
    assert "GNU gdb" in rec_c["payload"]

    rec_l = parse_mi_record('&"warning: no debug symbols\\n"')
    assert rec_l is not None
    assert rec_l["type"] == "log"
    assert "warning:" in rec_l["payload"]

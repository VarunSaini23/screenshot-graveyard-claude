import json

from app import claude_ai


def runner_returning(text, **extra):
    def run(cmd, prompt):
        assert cmd[1:] == ["-p", "--output-format", "json"]
        assert "Items:" in prompt or "JSON array" in prompt
        return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text, **extra})
    return run


BATCH = [{"id": 1, "ocr": "Swiggy order delivered ₹482", "category": "Other"},
         {"id": 2, "ocr": "boarding pass BLR DEL", "category": "Other"},
         {"id": 3, "ocr": "x" * 1000, "category": "Other"}]


def test_prompt_truncates_text_and_has_no_images():
    p = claude_ai.build_sort_prompt(BATCH)
    assert "x" * 301 not in p and "x" * 300 in p
    assert ".png" not in p


def test_parses_valid_reply_with_fences():
    reply = '```json\n[{"id": 1, "category": "receipts", "title": "Swiggy order ₹482"},' \
            '{"id": 2, "category": "Tickets", "title": "IndiGo boarding pass BLR–DEL"}]\n```'
    res = claude_ai.sort_batch(BATCH, runner=runner_returning(reply), cli="claude")
    assert res == {1: ("Receipts", "Swiggy order ₹482"), 2: ("Tickets", "IndiGo boarding pass BLR–DEL")}


def test_unknown_category_and_unknown_id_are_dropped():
    reply = '[{"id": 1, "category": "Spaceships", "title": "x"}, {"id": 99, "category": "Memes"}, {"id": 2, "category": "Memes"}]'
    res = claude_ai.sort_batch(BATCH, runner=runner_returning(reply), cli="claude")
    assert res == {2: ("Memes", "")}


def test_invalid_json_falls_back():
    assert claude_ai.sort_batch(BATCH, runner=runner_returning("sorry, I can't"), cli="claude") == {}


def test_cli_error_result_falls_back():
    def run(cmd, prompt):
        return json.dumps({"type": "result", "is_error": True, "result": "API Error: 401"})
    assert claude_ai.sort_batch(BATCH, runner=run, cli="claude") == {}


def test_garbage_stdout_falls_back():
    assert claude_ai.sort_batch(BATCH, runner=lambda c, p: "not json at all", cli="claude") == {}


def test_runner_exception_falls_back():
    def boom(cmd, prompt):
        raise TimeoutError("took too long")
    assert claude_ai.sort_batch(BATCH, runner=boom, cli="claude") == {}


def test_missing_cli(monkeypatch):
    monkeypatch.setattr(claude_ai.shutil, "which", lambda name: None)
    monkeypatch.delenv("SG_CLAUDE", raising=False)
    assert claude_ai.find_cli() is None
    assert claude_ai.sort_batch(BATCH) == {}
    st = claude_ai.ClaudeStatus()
    st.check()
    assert st.state == "off"


def test_status_on_with_working_cli(monkeypatch):
    monkeypatch.setattr(claude_ai.shutil, "which", lambda name: "claude")
    monkeypatch.delenv("SG_CLAUDE", raising=False)
    st = claude_ai.ClaudeStatus()
    st.check(runner=lambda c, p: json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok"}))
    assert st.state == "on"


def test_witty_lines():
    lines = claude_ai.witty_lines({"otps": 2340}, runner=runner_returning('["2,340 OTPs. Not one still works.", 5]'), cli="claude")
    assert lines == ["2,340 OTPs. Not one still works."]
    assert claude_ai.witty_lines({}, runner=runner_returning("nope"), cli="claude") is None

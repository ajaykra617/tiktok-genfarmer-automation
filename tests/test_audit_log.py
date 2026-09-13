from genfarmer_automation.audit_log import AuditRecord, append_csv, append_jsonl, load_recent_jsonl


def test_jsonl_and_csv_logging_contract(tmp_path):
    record = AuditRecord.now(
        account="tt_014",
        app="tiktok",
        mode="warmup",
        action="scroll",
        proxy="proxy_03",
        result="ok",
        ai_text="",
    )
    jsonl = tmp_path / "automation.jsonl"
    csv_path = tmp_path / "automation.csv"
    append_jsonl(jsonl, record)
    append_csv(csv_path, record)
    rows = load_recent_jsonl(jsonl)
    assert rows[-1]["account"] == "tt_014"
    assert rows[-1]["app"] == "tiktok"
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "time,account,app,mode,action,proxy,result,ai_text"

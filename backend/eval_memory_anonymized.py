"""匿名真实聊天评测。

先在本机生成脱敏标注模板，人工只填写长期事件与标准答案，再执行评测。
脚本不会上传聊天，也不会把原文写进报告。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path

from app.database import SessionLocal
from app.models import Message
from app.services.ai_service import ai_service


PRIVATE_DIR = Path(__file__).resolve().parent / "data" / "private_evals"


def redact(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱]", value)
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号]", value)
    value = re.sub(r"(?i)https?://\S+", "[链接]", value)
    value = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[证件号]", value)
    return value


def prepare(couple_id: int, output: Path, window: int, limit: int):
    """只在本地导出分层窗口；昵称与用户 ID 均替换为 A/B。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        rows = db.query(Message).filter(
            Message.couple_id == couple_id, Message.msg_type == "text"
        ).order_by(Message.id.asc()).limit(limit).all()
    sender_map = {value: chr(65 + index) for index, value in enumerate(sorted({row.sender_id for row in rows}))}
    cases = []
    for start in range(0, len(rows), window):
        batch = rows[start:start + window]
        if not batch:
            continue
        cases.append({
            "case_id": f"real-{start // window + 1:03d}",
            "messages": [{
                "id": index + 1,
                "sender_id": sender_map.get(row.sender_id, "X"),
                "created_at": row.created_at.isoformat(),
                "content": redact(row.content),
            } for index, row in enumerate(batch)],
            "question": "",
            "expected_event_terms": [],
            "expected_answer_terms": [],
            "forbidden_answer_terms": [],
            "should_abstain": False,
            "reviewed": False,
        })
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in cases) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cases": len(cases), "messages": len(rows)}, ensure_ascii=False))


def _context(events: list[dict]) -> str:
    lines = []
    for event in events:
        facts = "；".join(
            f"{fact.get('type', 'fact')}={fact.get('value', '')}"
            for fact in event.get("facts", []) if fact.get("value")
        )
        lines.append(
            f"- 时间：{event.get('started_at') or event.get('event_date') or '未知'}；"
            f"状态：{event.get('state') or '未知'}；内容：{event.get('summary') or ''}；事实：{facts}"
        )
    return "\n".join(lines) or "没有找到相关共同记忆。"


def evaluate(input_path: Path, report_path: Path):
    if not ai_service.available:
        raise RuntimeError("真实样本评测需要配置 AI_API_KEY")
    cases = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [case for case in cases if case.get("reviewed")]
    if not cases:
        raise RuntimeError("没有 reviewed=true 的人工标注样本")
    results = []
    latencies = []
    for case in cases:
        started = time.perf_counter()
        messages = []
        sender_ids = {}
        for row in case["messages"]:
            sender = str(row.get("sender_id") or "X")
            sender_ids.setdefault(sender, len(sender_ids) + 1)
            messages.append({**row, "sender_id": sender_ids[sender]})
        events = ai_service.extract_memory_events(messages)
        context = _context(events)
        answer = ai_service.memory_answer(case["question"], context, [], strict=True, viewer_user_id=1)
        event_text = json.dumps(events, ensure_ascii=False)
        expected_event = case.get("expected_event_terms") or []
        expected_answer = case.get("expected_answer_terms") or []
        forbidden = case.get("forbidden_answer_terms") or []
        abstained = any(word in answer for word in ("没有找到", "无法确认", "没记住", "不知道"))
        result = {
            "case_id": case["case_id"],
            "event_correct": all(term in event_text for term in expected_event),
            "answer_correct": all(term in answer for term in expected_answer) and not any(term in answer for term in forbidden),
            "abstention_correct": abstained if case.get("should_abstain") else True,
            "event_count": len(events),
        }
        result["passed"] = all(result[key] for key in ("event_correct", "answer_correct", "abstention_correct"))
        latencies.append((time.perf_counter() - started) * 1000)
        results.append(result)
        print(f"真实样本进度：{len(results)}/{len(cases)}", flush=True)
    payload = {
        "model": ai_service.model,
        "cases": len(results),
        "pass_rate": sum(row["passed"] for row in results) / len(results),
        "event_accuracy": sum(row["event_correct"] for row in results) / len(results),
        "answer_accuracy": sum(row["answer_correct"] for row in results) / len(results),
        "median_latency_ms": round(statistics.median(latencies), 2),
        "results": results,
        "privacy": "报告不包含聊天原文、问题或模型回答",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-couple", type=int)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=PRIVATE_DIR / "review_cases.jsonl")
    parser.add_argument("--report", type=Path, default=PRIVATE_DIR / "report.json")
    parser.add_argument("--window", type=int, default=30)
    parser.add_argument("--limit", type=int, default=600)
    options = parser.parse_args()
    if options.prepare_couple:
        prepare(options.prepare_couple, options.output, options.window, options.limit)
    elif options.input:
        evaluate(options.input, options.report)
    else:
        parser.error("请指定 --prepare-couple 或 --input")

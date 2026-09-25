from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.ai_features import heuristic_parse
from app.main import app

client = TestClient(app)

SAMPLE = """Data Structures (exam 2026-11-10)
- Arrays and Strings
- Linked Lists
- Dynamic Programming
Operating Systems - 15 Nov
Unit 1: Processes, Threads, CPU Scheduling
Unit 2: Deadlocks; Memory Management
DBMS: ER Model, Normalization, SQL Joins
"""


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ai"] is False


def test_heuristic_parse_handles_mixed_formats():
    subs = heuristic_parse(SAMPLE, date(2026, 9, 25))
    names = [s["name"] for s in subs]
    assert names == ["Data Structures", "Operating Systems", "DBMS"]
    assert subs[0]["exam_date"] == "2026-11-10"
    assert subs[1]["exam_date"] == "2026-11-15"
    assert [t["name"] for t in subs[1]["topics"]] == [
        "Processes", "Threads", "CPU Scheduling", "Deadlocks", "Memory Management"]
    dp = next(t for t in subs[0]["topics"] if t["name"] == "Dynamic Programming")
    assert dp["difficulty"] == 3


def test_parse_endpoint_offline():
    r = client.post("/api/syllabus/parse", json={"text": SAMPLE})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "heuristic" and len(body["subjects"]) == 3


def test_upload_text_file():
    r = client.post("/api/syllabus/upload", files={"file": ("s.txt", SAMPLE.encode(), "text/plain")})
    assert r.status_code == 200 and len(r.json()["subjects"]) == 3


def test_plan_quiz_explain_coach_roundtrip():
    start = date.today()
    plan_req = {
        "subjects": [{"name": "DSA", "exam_date": (start + timedelta(days=10)).isoformat(),
                      "topics": [{"name": "Trees", "hours": 3, "difficulty": 3}]}],
        "start_date": start.isoformat(), "hours_per_day": 3, "rest_weekdays": [],
    }
    p = client.post("/api/plan", json=plan_req)
    assert p.status_code == 200
    plan = p.json()
    assert plan["total_hours"] > 0

    q = client.post("/api/quiz", json={"subject": "DSA", "topic": "Trees", "num_questions": 3}).json()
    assert q["source"] == "offline" and len(q["questions"]) == 3

    e = client.post("/api/explain", json={"subject": "DSA", "topic": "Trees"}).json()
    assert "Trees" in e["markdown"]

    c = client.post("/api/coach", json={"plan": plan, "today": start.isoformat(),
                                        "completed_task_ids": [], "weak_topics": ["Trees"]})
    assert c.status_code == 200 and "Trees" in c.json()["message"]


def test_plan_validation():
    r = client.post("/api/plan", json={"subjects": [], "start_date": "2026-10-01"})
    assert r.status_code == 422


def test_ai_path_used_and_sanitized(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    async def fake_generate(prompt, **kw):
        if "Extract every subject" in prompt:
            return {"subjects": [{"name": "ML", "exam_date": "2026-12-01", "topics": [
                {"name": "Backprop", "difficulty": 9, "hours": 100}, {"name": ""}, "Regularization"]}]}
        return {"questions": [
            {"question": "Q1", "options": ["a", "b", "c", "d"], "answer_index": 1, "explanation": "x"},
            {"question": "bad", "options": ["a"], "answer_index": 5}]}

    monkeypatch.setattr(llm, "generate", fake_generate)
    r = client.post("/api/syllabus/parse", json={"text": "ML: backprop, regularization"}).json()
    assert r["source"] == "ai"
    t = r["subjects"][0]["topics"]
    assert t[0] == {"name": "Backprop", "difficulty": 3, "hours": 20.0}
    assert [x["name"] for x in t] == ["Backprop", "Regularization"]

    q = client.post("/api/quiz", json={"subject": "ML", "topic": "Backprop", "num_questions": 2}).json()
    assert q["source"] == "ai" and len(q["questions"]) == 1


def test_ai_failure_falls_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    async def boom(*a, **k):
        raise llm.LLMError("quota")

    monkeypatch.setattr(llm, "generate", boom)
    r = client.post("/api/syllabus/parse", json={"text": SAMPLE}).json()
    assert r["source"] == "heuristic"
    e = client.post("/api/explain", json={"subject": "DSA", "topic": "Trees"}).json()
    assert e["source"] == "offline"


def test_split_respects_parentheses():
    subs = heuristic_parse("DSA\n- Graph Algorithms (BFS, DFS, Dijkstra)\nUnit 2: Normalization (1NF, BCNF), SQL", date(2026, 9, 25))
    assert [t["name"] for t in subs[0]["topics"]] == ["Graph Algorithms (BFS, DFS, Dijkstra)", "Normalization (1NF, BCNF)", "SQL"]

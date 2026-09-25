"""AI features (Gemini) with offline fallbacks.

- parse_syllabus: raw syllabus text -> subjects/topics with difficulty & effort
- make_quiz:      adaptive MCQ quiz for one topic
- explain_topic:  short tutor-style explanation, pitched at the student's mastery
- coach_message:  personalised nudge based on plan progress
"""
from __future__ import annotations

import logging
import re
from datetime import date

from . import llm
from .models import CoachRequest, QuizQuestion

log = logging.getLogger("studypilot.ai")

# --------------------------------------------------------------------------- syllabus

HARD_HINTS = ("advanced", "proof", "theorem", "dynamic programming", "np-", "complexity", "transform",
              "optimization", "derivation", "backpropagation", "concurrency", "deadlock", "normalization")
EASY_HINTS = ("intro", "introduction", "basics", "overview", "fundamentals", "history", "definition")
BULLET = re.compile(r"^\s*(?:[-*•▪◦>]|\d+[.)]|[a-z][.)])\s+(.*)$", re.I)
UNIT = re.compile(r"^\s*(?:unit|module|chapter|week|part)\s*[\w]*\s*[:\-–]\s*(.+)$", re.I)
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
DM_DATE = re.compile(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\.?\s*(\d{4})?", re.I)


def _guess_difficulty(name: str) -> tuple[int, float]:
    low = name.lower()
    if any(h in low for h in HARD_HINTS):
        return 3, 3.0
    if any(h in low for h in EASY_HINTS):
        return 1, 1.5
    return 2, 2.0


def _find_date(line: str, today: date) -> tuple[str | None, str]:
    """Return (iso_date or None, line with the date text removed)."""
    m = ISO_DATE.search(line)
    if m:
        return m.group(1), line.replace(m.group(0), " ")
    m = DM_DATE.search(line)
    if m:
        day, mon, year = int(m.group(1)), MONTHS.index(m.group(2)[:3].lower()) + 1, m.group(3)
        try:
            d = date(int(year) if year else today.year, mon, day)
            if not year and d < today:
                d = date(today.year + 1, mon, day)
            return d.isoformat(), line.replace(m.group(0), " ")
        except ValueError:
            pass
    return None, line


def _clean_subject(name: str) -> str:
    name = re.sub(r"\b(exam|on|date|final|end[- ]?sem)\b\s*[:\-]?", " ", name, flags=re.I)
    name = re.sub(r"[(\[]\s*[)\]]", "", name)
    name = re.sub(r"[()\[\]:\-–—|]+\s*$", "", name.strip())
    return re.sub(r"\s{2,}", " ", name).strip(" :-–—|,") or "Subject"


def _split_topics(text: str) -> list[str]:
    """Split on , ; | but never inside parentheses: 'Graphs (BFS, DFS), DP' -> 2 topics."""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;|" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip(" .") for p in parts if len(p.strip(" .")) > 1]


def heuristic_parse(text: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    subjects: list[dict] = []
    current: dict | None = None

    def new_subject(raw: str) -> dict:
        iso, rest = _find_date(raw, today)
        s = {"name": _clean_subject(rest), "exam_date": iso, "topics": []}
        subjects.append(s)
        return s

    def add_topics(names: list[str]) -> None:
        nonlocal current
        if current is None:
            current = new_subject("General")
        for n in names:
            diff, hrs = _guess_difficulty(n)
            current["topics"].append({"name": n[:200], "difficulty": diff, "hours": hrs})

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        b = BULLET.match(line)
        if b:
            content = b.group(1)
            u = UNIT.match(content)
            if u:
                add_topics(_split_topics(u.group(1)))
            elif ":" in content:  # "Graphs: BFS, DFS" stays one topic
                add_topics([content.strip()])
            else:
                add_topics(_split_topics(content) if "," in content or ";" in content else [content.strip()])
            continue
        u = UNIT.match(line)
        if u:
            add_topics(_split_topics(u.group(1)))
            continue
        if ":" in line:
            head, tail = line.split(":", 1)
            if "," in tail and not _find_date(tail, today)[0]:
                current = new_subject(head)
                add_topics(_split_topics(tail))
                continue
        current = new_subject(line)

    return [s for s in subjects if s["topics"]]


SYLLABUS_SYSTEM = (
    "You are an academic planning assistant for Indian university (B.Tech/M.Tech) students. "
    "You turn messy syllabus text into a clean, structured study inventory."
)


def _sanitize_subjects(raw: object) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("subjects", [])
    out = []
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        topics = []
        for t in s.get("topics", [])[:40]:
            if isinstance(t, str):
                t = {"name": t}
            if not isinstance(t, dict) or not str(t.get("name", "")).strip():
                continue
            try:
                diff = int(t.get("difficulty", 2))
            except (TypeError, ValueError):
                diff = 2
            try:
                hrs = float(t.get("hours", 2))
            except (TypeError, ValueError):
                hrs = 2.0
            topics.append({
                "name": str(t["name"]).strip()[:200],
                "difficulty": min(3, max(1, diff)),
                "hours": round(min(20.0, max(0.5, hrs)) * 2) / 2,
            })
        exam = s.get("exam_date")
        if not (isinstance(exam, str) and ISO_DATE.fullmatch(exam.strip())):
            exam = None
        if topics:
            out.append({"name": str(s["name"]).strip()[:120], "exam_date": exam, "topics": topics})
    return out[:12]


async def parse_syllabus(text: str, today: date | None = None) -> tuple[list[dict], str]:
    today = today or date.today()
    if llm.enabled():
        prompt = f"""Today's date is {today.isoformat()}.
Extract every subject and its study topics from the syllabus below.

Rules:
- Split big units into study-sized topics (roughly 1-4 hours each). Keep the syllabus order.
- difficulty: 1 = easy/recall, 2 = moderate, 3 = hard (proofs, heavy maths, problem solving).
- hours: realistic first-pass self-study time for an average student (0.5 to 8).
- exam_date: ISO YYYY-MM-DD if the text mentions it (assume the next occurrence after today), else null.
- Ignore marks distribution, textbook lists, course codes and admin text.

Return JSON only:
{{"subjects":[{{"name":str,"exam_date":str|null,"topics":[{{"name":str,"difficulty":1|2|3,"hours":number}}]}}]}}

SYLLABUS:
\"\"\"
{text[:30000]}
\"\"\""""
        try:
            data = await llm.generate(prompt, system=SYLLABUS_SYSTEM, json_mode=True, temperature=0.2)
            subjects = _sanitize_subjects(data)
            if subjects:
                return subjects, "ai"
        except llm.LLMError as e:
            log.warning("AI syllabus parse failed, using heuristic: %s", e)
    return heuristic_parse(text, today), "heuristic"


# --------------------------------------------------------------------------- quiz

def _level(mastery: float) -> str:
    if mastery < 0.34:
        return "foundational (definitions, core intuition, simple application)"
    if mastery < 0.7:
        return "intermediate (application, typical exam problems, compare/contrast)"
    return "advanced (tricky edge cases, multi-step problems, common misconceptions)"


def offline_quiz(topic: str, n: int) -> list[QuizQuestion]:
    prompts = [
        f"Without notes, can you explain the core idea of “{topic}” in two or three sentences?",
        f"Could you solve a typical exam question on “{topic}” right now?",
        f"Can you write down the key definitions / formulas / steps for “{topic}” from memory?",
        f"Could you teach “{topic}” to a friend and answer their follow-up questions?",
        f"Can you name one common mistake students make in “{topic}” and how to avoid it?",
    ]
    return [
        QuizQuestion(
            question=p,
            options=["Yes, confidently", "Partly", "Not yet"],
            answer_index=None,
            explanation="Self-check (offline mode). Be honest: this sets how much review the planner schedules.",
        )
        for p in prompts[:n]
    ]


def _sanitize_quiz(raw: object, n: int) -> list[QuizQuestion]:
    items = raw.get("questions", []) if isinstance(raw, dict) else raw
    out: list[QuizQuestion] = []
    for q in items if isinstance(items, list) else []:
        try:
            opts = [str(o).strip() for o in q["options"]][:5]
            idx = int(q["answer_index"])
            if len(opts) < 2 or not 0 <= idx < len(opts) or not str(q["question"]).strip():
                continue
            out.append(QuizQuestion(question=str(q["question"]).strip(), options=opts, answer_index=idx,
                                    explanation=str(q.get("explanation", "")).strip()))
        except (KeyError, TypeError, ValueError):
            continue
    return out[:n]


async def make_quiz(subject: str, topic: str, mastery: float, n: int) -> tuple[list[QuizQuestion], str]:
    if llm.enabled():
        prompt = f"""Create {n} multiple-choice questions to test a university student on:
Subject: {subject}
Topic: {topic}
Level: {_level(mastery)}

Requirements:
- 4 options each, exactly one correct, plausible distractors based on real misconceptions.
- Mix conceptual and problem-solving questions like those in Indian university exams.
- explanation: 1-2 sentences on why the answer is right.
Return JSON only: {{"questions":[{{"question":str,"options":[str,str,str,str],"answer_index":int,"explanation":str}}]}}"""
        try:
            data = await llm.generate(prompt, json_mode=True, temperature=0.6)
            qs = _sanitize_quiz(data, n)
            if len(qs) >= max(1, n // 2):
                return qs, "ai"
        except llm.LLMError as e:
            log.warning("AI quiz failed, using offline: %s", e)
    return offline_quiz(topic, n), "offline"


# --------------------------------------------------------------------------- explain

async def explain_topic(subject: str, topic: str, question: str | None, mastery: float) -> tuple[str, str]:
    if llm.enabled():
        ask = f"The student asks: “{question}”\n" if question else ""
        prompt = f"""You are a friendly, precise tutor. Subject: {subject}. Topic: {topic}.
Student level: {_level(mastery)}.
{ask}
Answer in GitHub-flavoured Markdown, max ~300 words, with these sections:
### The idea in one line
### Key points
(3-5 bullets)
### Worked example
(short, concrete)
### Common mistake
### Check yourself
(one question, answer hidden after 'Answer:' on the next line)
Use plain text maths (e.g. O(n log n), x^2) rather than LaTeX."""
        try:
            return await llm.generate(prompt, temperature=0.5), "ai"
        except llm.LLMError as e:
            log.warning("AI explain failed, using offline: %s", e)
    md = f"""### Study {topic} with the Feynman technique
*(Offline mode: add a `GEMINI_API_KEY` for AI explanations.)*

1. **Skim** your notes / textbook section on *{topic}* for 10 minutes.
2. **Explain it** on a blank page as if teaching a junior, in simple words.
3. **Find the gaps**: wherever you got stuck, go back to the source.
4. **Simplify**: rewrite your explanation shorter, with one example.
5. **Test**: solve 2 previous-year questions on *{topic}*.

### Check yourself
Can you explain *{topic}* in two sentences without notes?"""
    return md, "offline"


# --------------------------------------------------------------------------- coach

def _coach_facts(req: CoachRequest) -> dict:
    done = set(req.completed_task_ids)
    past = [t for d in req.plan.days if d.date < req.today for t in d.tasks if t.type != "exam"]
    today_tasks = [t for d in req.plan.days if d.date == req.today for t in d.tasks if t.type != "exam"]
    all_tasks = [t for d in req.plan.days for t in d.tasks if t.type != "exam"]
    missed = [t for t in past if t.id not in done]
    upcoming = sorted((s for s in req.plan.summaries if s.exam_date >= req.today), key=lambda s: s.exam_date)
    nxt = upcoming[0] if upcoming else None
    return {
        "progress_pct": round(100 * len([t for t in all_tasks if t.id in done]) / max(1, len(all_tasks))),
        "missed_tasks": len(missed),
        "missed_hours": sum(t.hours for t in missed),
        "today_hours": sum(t.hours for t in today_tasks),
        "today_topics": [t.topic or f"{t.subject} revision" for t in today_tasks][:5],
        "next_exam": nxt.subject if nxt else None,
        "days_to_next_exam": (nxt.exam_date - req.today).days if nxt else None,
        "weak_topics": req.weak_topics[:5],
        "warnings": req.plan.warnings[:3],
    }


def offline_coach(f: dict) -> str:
    parts = []
    if f["next_exam"] is not None:
        parts.append(f"{f['next_exam']} is in {f['days_to_next_exam']} day(s).")
    if f["missed_tasks"]:
        parts.append(f"You have {f['missed_tasks']} missed task(s) ({f['missed_hours']:g}h). Hit Replan to spread them over the coming days.")
    elif f["progress_pct"]:
        parts.append(f"You're {f['progress_pct']}% through your plan and on track. Keep the streak going!")
    if f["weak_topics"]:
        parts.append(f"Extra reviews are lined up for: {', '.join(f['weak_topics'])}.")
    if f["today_hours"]:
        parts.append(f"Today: {f['today_hours']:g}h. Start with the reviews while you're fresh, then new material.")
    return " ".join(parts) or "Generate a plan to get personalised coaching."


async def coach_message(req: CoachRequest) -> tuple[str, str]:
    facts = _coach_facts(req)
    if llm.enabled():
        prompt = f"""You are an encouraging but honest study coach for a college student.
Here are the facts about their plan today ({req.today.isoformat()}): {facts}
Write 2-4 short sentences (max 70 words): acknowledge progress, name the single most important
focus for today, and one concrete tip (technique, not generic motivation). If they missed tasks,
tell them to use the Replan button. No greetings, no emojis, no markdown headings."""
        try:
            return await llm.generate(prompt, temperature=0.7), "ai"
        except llm.LLMError as e:
            log.warning("AI coach failed, using offline: %s", e)
    return offline_coach(facts), "offline"

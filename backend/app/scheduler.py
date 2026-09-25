"""Deterministic study-plan scheduler.

The LLM understands the syllabus (topics, difficulty, effort); this module turns
that into a calendar that is guaranteed to respect the student's constraints:

* daily hour budget and rest days
* every subject gets a revision block on its last study day before the exam
* learning is interleaved across subjects by *urgency*
  (remaining hours / study days left before that exam)
* spaced-repetition reviews are inserted 1, 3, 7 and 14 days after a topic is
  first learned (Ebbinghaus forgetting curve), more of them for hard/weak topics
* anything that cannot fit is reported back instead of silently dropped

Because it is plain Python it is fast, testable and works without an API key.
Re-running it with updated mastery / completed hours is how the plan adapts.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .models import PlanDay, PlanRequest, PlanResponse, StudyTask, SubjectSummary

CHUNK = 0.5  # scheduling granularity in hours
MAX_LEARN_BLOCK = 1.0  # longest single learning chunk before re-evaluating priorities
REVIEW_HOURS = 0.5
REVIEW_OFFSETS = [1, 3, 7, 14]
MASTERED = 0.85
REVISION_HOURS = 2.0


def _floor_chunk(x: float) -> float:
    return max(0.0, int(round(x * 1000)) // int(CHUNK * 1000) * CHUNK)


def _ceil_chunk(x: float) -> float:
    steps = -(-int(round(x * 1000)) // int(CHUNK * 1000))
    return max(0.0, steps * CHUNK)


def learning_hours(hours: float, mastery: float, completed: float) -> float:
    """Hours of first-pass learning still needed for a topic."""
    if mastery >= MASTERED:
        return 0.0
    needed = hours * (1 - 0.6 * mastery) - completed
    return _ceil_chunk(needed) if needed > 0.01 else 0.0


def review_count(difficulty: int, mastery: float, completed: float) -> int:
    if mastery >= MASTERED:
        return 1
    n = 3 if difficulty >= 3 else 2
    if completed > 0 and mastery < 0.5:  # studied it, but the quiz says it didn't stick
        n += 1
    return min(n, len(REVIEW_OFFSETS))


@dataclass
class _Topic:
    subject: str
    name: str
    remaining: float
    reviews: int
    learned_before: bool  # all learning already done before this plan starts
    weak: bool = False  # studied, but quiz mastery is low


@dataclass
class _Review:
    due: int
    subject: str
    topic: str
    note: str


def build_plan(req: PlanRequest) -> PlanResponse:
    start = req.start_date
    first_day_used_hours = req.first_day_used_hours
    subjects = sorted(req.subjects, key=lambda s: s.exam_date)
    warnings: list[str] = []

    valid_subjects = []
    for s in subjects:
        if s.exam_date <= start:
            warnings.append(f"{s.name}: exam date {s.exam_date:%d %b} is not after the start date, skipped.")
        else:
            valid_subjects.append(s)
    if not valid_subjects:
        return PlanResponse(days=[], summaries=[], warnings=warnings, total_hours=0)

    last = max(s.exam_date for s in valid_subjects)
    n_days = (last - start).days + 1
    dates = [start + timedelta(days=i) for i in range(n_days)]
    exam_idx = {s.name: (s.exam_date - start).days for s in valid_subjects}
    exam_days = defaultdict(list)
    for s in valid_subjects:
        exam_days[exam_idx[s.name]].append(s.name)

    daily = _floor_chunk(req.hours_per_day)
    capacity: list[float] = []
    for i, d in enumerate(dates):
        if d.weekday() in req.rest_weekdays:
            cap = 0.0
        elif i in exam_days:
            cap = _floor_chunk(daily / 2)  # exam day: lighter load
        else:
            cap = daily
        if i == 0:
            cap = _floor_chunk(max(0.0, cap - first_day_used_hours))
        capacity.append(cap)

    # study days available strictly before index j, from index i
    study_prefix = [0]
    for c in capacity:
        study_prefix.append(study_prefix[-1] + (1 if c >= CHUNK else 0))

    def study_days_between(i: int, j: int) -> int:
        return study_prefix[max(i, j)] - study_prefix[i]

    tasks: dict[int, list[StudyTask]] = defaultdict(list)

    # 1. reserve a revision block on each subject's last study day before its exam
    reserved = [0.0] * n_days
    revision_at: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for s in valid_subjects:
        e = exam_idx[s.name]
        target = next((i for i in range(e - 1, -1, -1) if capacity[i] - reserved[i] >= CHUNK), None)
        if target is None:
            warnings.append(f"{s.name}: no free study day before the exam for a final revision.")
            continue
        hrs = _floor_chunk(min(REVISION_HOURS, capacity[target] - reserved[target], max(CHUNK, capacity[target] * 0.6)))
        reserved[target] += hrs
        revision_at[target].append((s.name, hrs))

    # 2. per-subject learning queues
    queues: dict[str, list[_Topic]] = {}
    for s in valid_subjects:
        q = []
        for t in s.topics:
            q.append(
                _Topic(
                    subject=s.name,
                    name=t.name,
                    remaining=learning_hours(t.hours, t.mastery, t.completed_hours),
                    reviews=review_count(t.difficulty, t.mastery, t.completed_hours),
                    learned_before=False,
                    weak=t.completed_hours > 0 and t.mastery < 0.5,
                )
            )
            q[-1].learned_before = q[-1].remaining == 0
        queues[s.name] = q

    reviews: list[_Review] = []

    def enqueue_reviews(tp: _Topic, learned_idx: int) -> None:
        for k, off in enumerate(REVIEW_OFFSETS[: tp.reviews]):
            label = f"weak-topic boost #{k + 1}" if tp.weak else f"spaced review #{k + 1}"
            reviews.append(_Review(due=learned_idx + off, subject=tp.subject, topic=tp.name, note=label))

    # topics already learned (from earlier progress) start their review cycle now
    for q in queues.values():
        for tp in q:
            if tp.learned_before:
                enqueue_reviews(tp, -1)

    # 3. walk the calendar
    for i in range(n_days):
        cap = capacity[i] - reserved[i]
        learn_pending = any(tp.remaining > 0 for s, q in queues.items() if exam_idx[s] > i for tp in q)

        # 3a. due reviews (drop ones whose exam has passed; carry the rest over)
        reviews = [r for r in reviews if exam_idx[r.subject] > i]
        due = sorted((r for r in reviews if r.due <= i), key=lambda r: (exam_idx[r.subject], r.due))
        review_budget = cap if not learn_pending else max(CHUNK, _floor_chunk(cap * 0.5))
        placed_reviews = set()
        for r in due:
            if cap < REVIEW_HOURS or review_budget < REVIEW_HOURS:
                break
            key = (r.subject, r.topic)
            if key in placed_reviews:
                continue  # one review per topic per day; the other stays due
            tasks[i].append(StudyTask(id="", type="review", subject=r.subject, topic=r.topic, hours=REVIEW_HOURS, note=r.note))
            placed_reviews.add(key)
            cap -= REVIEW_HOURS
            review_budget -= REVIEW_HOURS
            reviews.remove(r)

        # 3b. learning, interleaved by urgency
        while cap >= CHUNK:
            best, best_score = None, -1.0
            for s in valid_subjects:
                e = exam_idx[s.name]
                if e <= i:
                    continue
                rem = sum(tp.remaining for tp in queues[s.name])
                if rem <= 0:
                    continue
                score = rem / max(1, study_days_between(i, e))
                if score > best_score + 1e-9:
                    best, best_score = s.name, score
            if best is None:
                break
            tp = next(tp for tp in queues[best] if tp.remaining > 0)
            amt = min(tp.remaining, MAX_LEARN_BLOCK, _floor_chunk(cap))
            tasks[i].append(StudyTask(id="", type="learn", subject=best, topic=tp.name, hours=amt))
            tp.remaining = round(tp.remaining - amt, 3)
            cap -= amt
            if tp.remaining <= 0:
                enqueue_reviews(tp, i)

        for subj, hrs in revision_at.get(i, []):
            tasks[i].append(
                StudyTask(id="", type="revision", subject=subj, hours=hrs, note="Full revision + timed practice paper")
            )
        for subj in exam_days.get(i, []):
            tasks[i].append(StudyTask(id="", type="exam", subject=subj, hours=0, note="Exam day - all the best!"))

    # 4. merge same (type, subject, topic) blocks per day and assign stable ids
    days: list[PlanDay] = []
    total = 0.0
    planned_by_subject: dict[str, float] = defaultdict(float)
    for i, d in enumerate(dates):
        merged: dict[tuple, StudyTask] = {}
        for t in tasks[i]:
            key = (t.type, t.subject, t.topic)
            if key in merged:
                merged[key].hours += t.hours
            else:
                merged[key] = t.model_copy()
        order = {"exam": 0, "review": 1, "learn": 2, "revision": 3}
        day_tasks = sorted(merged.values(), key=lambda t: order[t.type])
        for t in day_tasks:
            t.id = f"{d.isoformat()}|{t.type}|{t.subject}|{t.topic or ''}"
            total += t.hours
            planned_by_subject[t.subject] += t.hours
        days.append(PlanDay(date=d, is_rest=d.weekday() in req.rest_weekdays and i not in exam_days, tasks=day_tasks))

    # 5. summaries + warnings for anything that did not fit
    summaries = []
    for s in valid_subjects:
        left = sum(tp.remaining for tp in queues[s.name])
        if left > 0:
            warnings.append(
                f"{s.name}: {left:g}h of new material doesn't fit before {s.exam_date:%d %b}. "
                "Add daily hours, drop a rest day, or mark easy topics as known."
            )
        summaries.append(
            SubjectSummary(
                subject=s.name,
                exam_date=s.exam_date,
                planned_hours=round(planned_by_subject[s.name], 2),
                unscheduled_hours=round(left, 2),
                days_until_exam=(s.exam_date - start).days,
            )
        )

    return PlanResponse(days=days, summaries=summaries, warnings=warnings, total_hours=round(total, 2))

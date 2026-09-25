from datetime import date, timedelta

import pytest

from app.models import PlanRequest, Subject, Topic
from app.scheduler import build_plan, learning_hours

START = date(2026, 10, 1)  # a Thursday


def subj(name, days_out, topics):
    return Subject(name=name, exam_date=START + timedelta(days=days_out),
                   topics=[Topic(name=t, hours=h, difficulty=d) for t, h, d in topics])


def req(subjects, **kw):
    return PlanRequest(subjects=subjects, start_date=START, **{"hours_per_day": 4, **kw})


def all_tasks(plan):
    return [t for d in plan.days for t in d.tasks]


def test_daily_capacity_never_exceeded():
    p = build_plan(req([
        subj("DSA", 10, [("Arrays", 3, 2), ("Trees", 4, 3), ("Graphs", 5, 3)]),
        subj("DBMS", 14, [("ER model", 2, 1), ("Normalization", 3, 3), ("SQL", 3, 2)]),
    ]))
    for d in p.days:
        assert sum(t.hours for t in d.tasks) <= 4 + 1e-9, d


def test_all_learning_scheduled_before_exam_and_counts_match():
    s = subj("DSA", 12, [("Arrays", 3, 2), ("Trees", 4, 3)])
    p = build_plan(req([s]))
    learn = [t for t in all_tasks(p) if t.type == "learn"]
    assert sum(t.hours for t in learn) == pytest.approx(7)
    for d in p.days:
        for t in d.tasks:
            if t.type in ("learn", "review", "revision"):
                assert d.date < s.exam_date
    assert not p.warnings


def test_revision_block_on_last_study_day_before_exam():
    s = subj("OS", 7, [("Processes", 2, 2)])
    p = build_plan(req([s]))
    rev_days = [d.date for d in p.days for t in d.tasks if t.type == "revision"]
    assert rev_days == [s.exam_date - timedelta(days=1)]


def test_rest_days_are_empty_and_revision_moves_earlier():
    # exam on Mon 12 Oct; Sunday is a rest day -> revision on Saturday
    s = Subject(name="Maths", exam_date=date(2026, 10, 12), topics=[Topic(name="Calculus", hours=2)])
    p = build_plan(req([s], rest_weekdays=[6]))
    for d in p.days:
        if d.date.weekday() == 6:
            assert d.tasks == [] and d.is_rest
    rev = [d.date for d in p.days for t in d.tasks if t.type == "revision"]
    assert rev == [date(2026, 10, 10)]


def test_spaced_reviews_follow_learning():
    s = subj("CN", 20, [("TCP", 1, 3)])
    p = build_plan(req([s]))
    learn_day = next(d.date for d in p.days for t in d.tasks if t.type == "learn")
    review_days = [d.date for d in p.days for t in d.tasks if t.type == "review"]
    assert review_days == [learn_day + timedelta(days=o) for o in (1, 3, 7)]  # hard topic -> 3 reviews


def test_interleaves_subjects_and_prioritises_nearer_exam():
    p = build_plan(req([
        subj("Near", 5, [("A", 6, 2)]),
        subj("Far", 25, [("B", 6, 2)]),
    ]))
    first = p.days[0]
    near_h = sum(t.hours for t in first.tasks if t.subject == "Near")
    far_h = sum(t.hours for t in first.tasks if t.subject == "Far")
    assert near_h > far_h


def test_overflow_is_reported_not_dropped_silently():
    p = build_plan(req([subj("Huge", 3, [("Everything", 40, 3)])], hours_per_day=2))
    assert p.summaries[0].unscheduled_hours > 0
    assert any("doesn't fit" in w for w in p.warnings)


def test_mastery_reduces_learning_and_weak_topics_get_reviews():
    assert learning_hours(4, 0.9, 0) == 0
    assert learning_hours(4, 0.5, 0) < learning_hours(4, 0, 0)
    s = Subject(name="AI", exam_date=START + timedelta(days=10),
                topics=[Topic(name="Search", hours=2, mastery=0.2, completed_hours=2)])
    p = build_plan(req([s]))
    kinds = [t.type for t in all_tasks(p)]
    assert "learn" not in kinds
    assert kinds.count("review") >= 2


def test_first_day_used_hours_reduces_capacity():
    p = build_plan(req([subj("X", 10, [("T", 10, 2)])], first_day_used_hours=3))
    assert sum(t.hours for t in p.days[0].tasks) <= 1


def test_past_exam_is_skipped_with_warning():
    p = build_plan(req([subj("Old", 0, [("T", 1, 1)]), subj("New", 5, [("T", 1, 1)])]))
    assert any("skipped" in w for w in p.warnings)
    assert [s.subject for s in p.summaries] == ["New"]


def test_task_ids_unique_and_stable():
    r = req([subj("A", 9, [("x", 3, 2), ("y", 2, 1)]), subj("B", 11, [("z", 4, 3)])])
    ids1 = [t.id for t in all_tasks(build_plan(r))]
    ids2 = [t.id for t in all_tasks(build_plan(r))]
    assert ids1 == ids2 and len(ids1) == len(set(ids1))


def test_review_labels_distinguish_weak_topics():
    s = Subject(name="AI", exam_date=START + timedelta(days=12), topics=[
        Topic(name="Weak", hours=2, mastery=0.2, completed_hours=2),
        Topic(name="Fine", hours=2, mastery=0.6, completed_hours=2)])
    notes = {(t.topic, t.note) for t in all_tasks(build_plan(req([s]))) if t.type == "review"}
    assert all(n.startswith("weak-topic") for tp, n in notes if tp == "Weak")
    assert all(n.startswith("spaced review") for tp, n in notes if tp == "Fine")


def test_front_loaded_first_exam_fits_when_capacity_allows():
    """Regression: a heavy first exam used to be squeezed by interleaving with later subjects."""
    start = date(2026, 9, 25)
    def s(name, days, hours):
        return Subject(name=name, exam_date=start + timedelta(days=days),
                       topics=[Topic(name=f"{name}{i}", hours=h, difficulty=3 if h >= 5 else 2) for i, h in enumerate(hours)])
    subjects = [s("DSA", 14, [4, 5, 6, 7, 8]), s("DBMS", 18, [3, 4, 5, 4, 6]), s("OS", 22, [4, 3, 4, 4, 5, 4])]
    left = []
    for h in (5.5, 6, 6.5, 7, 8):
        p = build_plan(PlanRequest(subjects=subjects, start_date=start, hours_per_day=h, rest_weekdays=[6]))
        left.append(sum(x.unscheduled_hours for x in p.summaries))
    assert left == [0, 0, 0, 0, 0]

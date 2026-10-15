from datetime import date, timedelta

from companion_agent.emotion_memory import (
    EmotionBaseline,
    EmotionEventStore,
    build_followup_notes,
    detect_emotion_correction,
)


def _baseline(tmp_path):
    return EmotionBaseline(tmp_path / "baseline.json")


def test_correction_extracts_negated_and_affirmed_labels(tmp_path) -> None:
    correction = detect_emotion_correction("我不是难过，是焦虑")

    assert correction is not None
    assert correction.wrong_label == "难过"
    assert correction.correct_label == "焦虑"


def test_correction_handles_affirmation_first_order(tmp_path) -> None:
    correction = detect_emotion_correction("你猜错了，我是开心，不是难过")

    assert correction is not None
    assert correction.correct_label == "开心"
    assert correction.wrong_label == "难过"


def test_correction_ignores_plain_emotion_statement(tmp_path) -> None:
    assert detect_emotion_correction("今天有点难过") is None
    # 自然陈述而非纠正：没有"我是X"式肯定从句
    assert detect_emotion_correction("我不是很难过，就是有点累") is None


def test_baseline_features_ratio_and_cold_start(tmp_path) -> None:
    baseline = _baseline(tmp_path)
    features = baseline.features("嗯")
    assert features["length_ratio_vs_own_avg"] is None
    assert features["samples_in_baseline"] == 0

    for message in ["今天去了图书馆，看了两章专业书", "晚上和朋友吃了火锅，聊了很久", "刚散完步回来，走了三公里"]:
        baseline.update(message)
    features = baseline.features("今天去了图书馆，看了两章专业书，还做了笔记")
    assert features["length_ratio_vs_own_avg"] is not None
    assert 0.5 <= features["length_ratio_vs_own_avg"] <= 2.5
    assert features["samples_in_baseline"] == 3


def test_event_store_records_and_filters(tmp_path) -> None:
    store = EmotionEventStore(tmp_path / "events.json")
    today = date.today()

    assert store.record("None", 0.9, "x", today=today) is None
    store.record("焦虑", 0.8, "明天要答辩了", today=today - timedelta(days=1))
    store.record("焦虑", 0.4, "轻微不安", today=today - timedelta(days=1))
    store.record("疲惫", 0.7, "连续加班", today=today)

    recent = store.recent(days=2, min_intensity=0.6, exclude_today=False)
    assert len(recent) == 2
    assert all(e["intensity"] >= 0.6 for e in recent)

    yesterday = store.recent(days=2, min_intensity=0.6, exclude_today=True)
    assert len(yesterday) == 1
    assert yesterday[0]["label"] == "焦虑"


def test_followup_notes_cover_yesterday_and_repeat_pattern(tmp_path) -> None:
    store = EmotionEventStore(tmp_path / "events.json")
    today = date.today()

    store.record("焦虑", 0.8, "明天要答辩了", today=today - timedelta(days=1))
    for _ in range(3):
        store.record("焦虑", 0.7, "想到工作就心慌", today=today)

    notes = build_followup_notes(store)
    assert any("昨天" in note and "答辩" in note for note in notes)
    assert any("近两周" in note and "焦虑" in note for note in notes)


def test_followup_notes_empty_when_nothing_notable(tmp_path) -> None:
    store = EmotionEventStore(tmp_path / "events.json")
    assert build_followup_notes(store) == []

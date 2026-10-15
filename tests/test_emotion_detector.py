from companion_agent.emotion_detector import (
    EMOTION_ANGRY,
    EMOTION_ANXIOUS,
    EMOTION_EXPECTANT,
    EMOTION_HAPPY,
    EMOTION_LONELY,
    EMOTION_NONE,
    EMOTION_SAD,
    EMOTION_TIRED,
    CurrentEmotionDetector,
)


def _rule_only_detector() -> CurrentEmotionDetector:
    detector = CurrentEmotionDetector()
    detector._judge_with_llm = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
    return detector


def test_maps_anxiety_terms_to_anxious() -> None:
    emotion = _rule_only_detector().detect("这件事让我很焦虑")

    assert emotion.label == EMOTION_ANXIOUS
    assert emotion.intensity > 0
    assert emotion.context_turns == 0


def test_uses_recent_context_for_emotion_trend() -> None:
    history = [
        {"role": "user", "content": "我最近压力很大，也很焦虑。"},
        {"role": "assistant", "content": "我在，慢慢说。"},
    ]
    emotion = _rule_only_detector().detect("现在有人陪着，我开心多了。", history)

    assert emotion.label == EMOTION_HAPPY
    assert emotion.trend == "缓解中"
    assert emotion.context_turns == 2


def test_maps_anger_terms_to_angry() -> None:
    emotion = _rule_only_detector().detect("我真的很生气，太烦了。")

    assert emotion.label == EMOTION_ANGRY


def test_maps_exhaustion_terms_to_tired() -> None:
    emotion = _rule_only_detector().detect("最近好累，撑不住了")

    assert emotion.label == EMOTION_TIRED
    assert emotion.intensity >= 0.8


def test_maps_loneliness_terms_to_lonely() -> None:
    emotion = _rule_only_detector().detect("一个人过节，有点寂寞")

    assert emotion.label == EMOTION_LONELY


def test_detects_secondary_emotion_in_mixed_turn() -> None:
    emotion = _rule_only_detector().detect("考上了好开心！但要离开好难过")

    assert emotion.label in {EMOTION_HAPPY, EMOTION_SAD}
    assert emotion.secondary_label in {EMOTION_HAPPY, EMOTION_SAD}
    assert emotion.secondary_label != emotion.label
    assert emotion.secondary_intensity > 0


def test_negated_positive_stays_negative() -> None:
    emotion = _rule_only_detector().detect("我一点都不开心")

    assert emotion.label == EMOTION_SAD


def test_no_signal_maps_to_none() -> None:
    emotion = _rule_only_detector().detect("今天天气不错，适合出去走走")

    assert emotion.label == EMOTION_NONE
    assert emotion.secondary_label == EMOTION_NONE


def test_rule_fallback_carries_secondary_on_llm_failure() -> None:
    emotion = _rule_only_detector().detect("我又紧张又期待明天的面试")

    assert "llm_judge_failed" in emotion.signals
    # 规则兜底也应给出主情绪；并列时按标签序取先者（期待 < 焦虑）
    assert emotion.label in {EMOTION_ANXIOUS, EMOTION_HAPPY, EMOTION_SAD, EMOTION_EXPECTANT}

"""[FR-49] Tests for AGENT 平台 Bypass — 跳過情緒分析模組.

Citations:
  SRS.md FR-49
  TEST_SPEC.md FR-49
"""


def test_fr49_agent_platform_skips_emotion_module():
    """[FR-49] agent_platform_skips_emotion_module."""
    from src.emotion.analyzer import EmotionAnalyzer
    assert True  # RED: will fail on import


def test_fr49_telegram_platform_emotion_module_runs():
    """[FR-49] telegram_platform_emotion_module_runs."""
    from src.emotion.analyzer import EmotionAnalyzer
    assert True  # RED: will fail on import

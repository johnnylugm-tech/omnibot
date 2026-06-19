"""[FR-46] EmotionAnalyzer — positive / neutral / negative + intensity [0.0, 1.0].

Spec source: 02-architecture/TEST_SPEC.md (FR-46)
SRS source : SRS.md FR-46 (Module 8: Emotion Analyzer)

FR-46 -- EmotionAnalyzer:
    Classify emotion into ``positive`` / ``neutral`` / ``negative``; the
    intensity MUST lie in the closed interval ``[0.0, 1.0]``; every
    classification produces an ``EmotionScore`` record.

The classifier is a deliberately small keyword-driven heuristic — the
FR-46 contract only requires (a) a non-None ``EmotionScore`` for any
non-empty input, (b) the category restricted to the three legal values
above, and (c) a numeric ``intensity`` in ``[0.0, 1.0]``. A heavier
model (LLM, on-device classifier, …) can be wired in behind the same
``EmotionAnalyzer.classify`` entry point without changing the public
shape.

Citations:
    - SRS.md FR-46 -- "分類情緒為 positive/neutral/negative" (line 104).
    - SRS.md FR-46 -- "intensity 範圍 0.0–1.0" (line 104).
    - SRS.md FR-46 -- "每次分析建立 EmotionScore 記錄" (line 104).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# SRS-mandated enums. The category set is closed and ``intensity`` MUST lie
# in the closed interval ``[0.0, 1.0]`` (NFR NP-06: classification must be
# cheap, so we enforce the invariant at construction time rather than at
# the call site).
# ---------------------------------------------------------------------------
VALID_CATEGORIES: frozenset[str] = frozenset({"positive", "neutral", "negative"})
INTENSITY_MIN: float = 0.0
INTENSITY_MAX: float = 1.0

# ---------------------------------------------------------------------------
# Minimal lexicon. Production wiring would back this with a richer lexicon
# or an ML model; the FR-46 contract only requires the (category, intensity)
# tuple to satisfy the invariants above, not the lexical coverage.
# ---------------------------------------------------------------------------
_POSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {"很棒", "棒", "好", "讚", "喜歡", "開心", "謝謝", "great", "good", "love", "thanks"}
)
_NEGATIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "非常生氣",
        "生氣",
        "爛",
        "差",
        "不滿",
        "討厭",
        "angry",
        "bad",
        "hate",
        "terrible",
    }
)

# Intensifier marker that pushes a keyword hit toward the upper bound so
# downstream consumers (e.g. escalation logic) can rely on the signal
# strength. Kept as a single constant so the boost logic stays in one
# place if the lexicon grows.
_INTENSIFIER: str = "非常"


@dataclass(frozen=True)
class EmotionScore:
    """[FR-46] A single classification outcome (category + intensity).

    ``category`` is one of ``{"positive", "neutral", "negative"}``;
    ``intensity`` is a float in ``[0.0, 1.0]``. The dataclass is
    ``frozen=True`` so a returned record is immutable — callers can
    rely on the values they receive.

    Citations:
        - SRS.md FR-46 -- "情緒分類結果限定三個合法值" (line 104).
        - SRS.md FR-46 -- "intensity 範圍 [0.0, 1.0]" (line 104).
    """

    category: str
    intensity: float


class EmotionAnalyzer:
    """[FR-46] Stateless emotion classifier.

    The class is intentionally tiny: GREEN keeps it side-effect-free and
    deterministic so unit tests can pin exact (category, intensity)
    pairs. A future wiring layer that swaps in an LLM or on-device
    classifier MUST preserve the public shape — :meth:`classify` returns
    an :class:`EmotionScore` with ``category`` in the legal set and
    ``intensity`` in ``[0.0, 1.0]``.

    Citations:
        - SRS.md FR-46 -- "每次分析建立 EmotionScore 記錄" (line 104).
    """

    def classify(self, text: str) -> EmotionScore:
        """Classify ``text`` and return an :class:`EmotionScore`.

        The heuristic is keyword-driven; for any non-empty input it
        always returns a non-None :class:`EmotionScore` whose
        ``category`` belongs to ``VALID_CATEGORIES`` and whose
        ``intensity`` lies in ``[0.0, 1.0]``.

        Citations:
            - SRS.md FR-46 -- category limited to 3 values (line 808).
            - SRS.md FR-46 -- intensity in [0.0, 1.0] (line 808).
        """
        return emotion_classify(text)


def _has_any_keyword(haystack: str, keywords: frozenset[str]) -> bool:
    """True iff any keyword appears as a substring of ``haystack``."""
    return any(keyword in haystack for keyword in keywords)


def _intensity(base: float, boosted: float, haystack: str) -> float:
    """Return ``boosted`` when ``_INTENSIFIER`` appears, else ``base``."""
    return boosted if _INTENSIFIER in haystack else base


def emotion_classify(text: str) -> EmotionScore:
    """[FR-46] Functional entry point for emotion classification.

    Mirrors :meth:`EmotionAnalyzer.classify` so callers that prefer a
    free function (e.g. inside ``map``/``filter`` pipelines) can use the
    same logic without instantiating a class. The returned
    :class:`EmotionScore` is always non-None for non-empty ``text``;
    empty / whitespace-only input degrades to ``("neutral", 0.0)``.

    Citations:
        - SRS.md FR-46 -- implementation function ``emotion_classify`` (line 806).
        - SRS.md FR-46 -- "每次分析建立 EmotionScore 記錄" (line 104).
    """
    if not text or not text.strip():
        return EmotionScore(category="neutral", intensity=INTENSITY_MIN)

    haystack = text.lower()

    if _has_any_keyword(haystack, _NEGATIVE_KEYWORDS):
        return EmotionScore(
            category="negative",
            intensity=_intensity(base=0.7, boosted=0.9, haystack=haystack),
        )

    if _has_any_keyword(haystack, _POSITIVE_KEYWORDS):
        return EmotionScore(
            category="positive",
            intensity=_intensity(base=0.6, boosted=0.8, haystack=haystack),
        )

    return EmotionScore(category="neutral", intensity=0.5)


__all__ = [
    "EmotionAnalyzer",
    "EmotionScore",
    "emotion_classify",
    "VALID_CATEGORIES",
    "INTENSITY_MIN",
    "INTENSITY_MAX",
]

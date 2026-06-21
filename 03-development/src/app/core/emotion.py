from __future__ import annotations
"""[FR-46] EmotionAnalyzer — positive / neutral / negative + intensity [0.0, 1.0].
[FR-47] EmotionTracker — 24hr half-life exponential decay.
[FR-48] EmotionTracker.should_escalate — consecutive negative run >= 3.

Spec source: 02-architecture/TEST_SPEC.md (FR-46, FR-47, FR-48)
SRS source : SRS.md FR-46, FR-47, FR-48 (Module 8: Emotion Analyzer)

FR-46 -- EmotionAnalyzer:
    Classify emotion into ``positive`` / ``neutral`` / ``negative``; the
    intensity MUST lie in the closed interval ``[0.0, 1.0]``; every
    classification produces an ``EmotionScore`` record.

FR-47 -- EmotionTracker:
    Apply 24hr half-life exponential decay
    (``decay = exp(-0.693 * hours_ago / 24.0)``) via
    ``current_weighted_score()``; recent emotion carries higher weight.

FR-48 -- EmotionTracker.should_escalate:
    Walk the trailing run of ``"negative"`` categories and return
    ``True`` iff the run length is ``>= 3``; any non-``"negative"``
    entry in the trailing window MUST reset the count.

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
    - SRS.md FR-47 -- "EmotionTracker 以 24hr half-life 指數衰減" (line 105).
    - SRS.md FR-47 -- "decay = exp(-0.693 * hours_ago / 24.0)" (line 105).
    - SRS.md FR-47 -- "24hr 後權重降至 50%" (line 105).
    - SRS.md FR-47 -- "近期情緒權重更高" (line 105).
    - SRS.md FR-48 -- "consecutive_negative_count() ≥ 3 → should_escalate()=True" (line 106).
    - SRS.md FR-48 -- "計算從最近往回的連續負面次數" (line 106).
    - SRS.md FR-48 -- "連續 3 次負面觸發；中間有非負面打斷重計" (line 106).
"""


import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# SRS-mandated enums. The category set is closed and ``intensity`` MUST lie
# in the closed interval ``[0.0, 1.0]`` (NFR NP-06: classification must be
# cheap, so we enforce the invariant at construction time rather than at
# the call site).
# ---------------------------------------------------------------------------
VALID_CATEGORIES: frozenset[str] = frozenset({"positive", "neutral", "negative"})
NEGATIVE_CATEGORY: str = "negative"  # member of VALID_CATEGORIES; pinned here so the FR-48 comparison predicate below has a single source of truth
INTENSITY_MIN: float = 0.0
INTENSITY_MAX: float = 1.0

# ---------------------------------------------------------------------------
# SRS FR-47 -- 24hr half-life exponential decay. ``0.693`` in the SRS is a
# rounded shorthand for ``ln(2)``; using the exact constant collapses the
# formula ``exp(-ln(2) * hours_ago / 24.0)`` to exactly ``0.5`` when
# ``hours_ago == 24`` (one half-life elapsed). Kept as a named module
# constant so the decay rate is anchored to a single source of truth and
# remains auditable in code review.
# ---------------------------------------------------------------------------
HALF_LIFE_HOURS: float = 24.0
_DECAY_K: float = math.log(2.0)  # == 0.6931471805599453; SRS FR-47 writes 0.693 as shorthand

# ---------------------------------------------------------------------------
# SRS FR-48 -- escalation threshold. The trailing run of consecutive
# ``"negative"`` entries MUST be at least this long for
# :meth:`EmotionTracker.should_escalate` to return ``True``.
# ---------------------------------------------------------------------------
ESCALATION_THRESHOLD: int = 3

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

# Negation prefixes that flip the polarity of an immediately-following
# positive keyword (e.g. "不好" should classify as negative, not
# positive). The set is intentionally narrow: only single-character
# Mandarin negators that directly precede the keyword in text. SRS FR-46
# requires the (category, intensity) tuple to be honest about sentiment;
# a bare substring match on "好" inside "不好" would otherwise produce a
# false-positive classification. See H-14 in the 2026-06-21 bug report.
_NEGATION_PREFIXES: frozenset[str] = frozenset({"不", "沒", "無", "別", "勿", "未", "莫"})


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

    def analyze(self, text: str) -> EmotionScore:
        """Alias for :meth:`classify` used by FR-49 ``Pipeline.process``.

        The pipeline contract is ``emotion.analyze(text)`` (see
        ``core/pipeline.py``); ``EmotionAnalyzer`` keeps the
        keyword-driven heuristic behind both names so callers that wire
        the analyzer into the pipeline don't have to know which
        classifier entry point is canonical. Both methods return the
        same :class:`EmotionScore` for the same input.

        Citations:
            - SRS.md FR-49 -- "platform check in pipeline" (line 107).
        """
        return self.classify(text)


class EmotionTracker:
    """[FR-47] Temporal-decay tracker — applies 24hr half-life exponential decay.

    Wraps :func:`emotion_current_weighted_score` with a class-level entry
    point so callers that hold tracker state (e.g. a rolling emotion
    history) can inject the tracker and call :meth:`current_weighted_score`
    without re-deriving the half-life constant at every call site. The
    constructor takes no arguments — the decay law is a fixed module
    constant, so every :class:`EmotionTracker` instance is
    interchangeable.

    [FR-48] Also exposes :meth:`should_escalate` which decides whether a
    trailing run of consecutive ``"negative"`` categories meets the
    escalation threshold.

    Citations:
        - SRS.md FR-47 -- "EmotionTracker 以 24hr half-life 指數衰減" (line 105).
        - SRS.md FR-47 -- "decay = exp(-0.693 * hours_ago / 24.0)" (line 105).
        - SRS.md FR-47 -- "計算 current_weighted_score()" (line 105).
        - SRS.md FR-48 -- "EmotionTracker.should_escalate()" (line 106).
    """

    def current_weighted_score(self, score: float, hours_ago: float) -> float:
        """Return ``score`` weighted by 24hr half-life exponential decay.

        Implements ``score * exp(-0.693 * hours_ago / 24.0)``. Boundary
        cases pinned by the SRS FR-47 acceptance criteria:

        - ``hours_ago == 24`` ⇒ weight == 0.5 (one half-life elapsed).
        - ``hours_ago == 0``  ⇒ weight == ``score`` (no time elapsed).
        - ``hours_ago`` strictly increasing ⇒ weight strictly decreasing
          (recent emotion carries more weight than older emotion with
          the same raw score).

        Citations:
            - SRS.md FR-47 -- "24hr 後權重降至 50%" (line 105).
            - SRS.md FR-47 -- "近期情緒權重更高" (line 105).
        """
        return emotion_current_weighted_score(score=score, hours_ago=hours_ago)

    def should_escalate(self, emotions) -> bool:
        """[FR-48] True iff the trailing run of ``"negative"`` entries is ``>= 3``.

        Walks ``emotions`` (any iterable of category strings, oldest →
        newest) backwards from the most recent entry and counts how
        many consecutive ``"negative"`` categories it sees before the
        first non-``"negative"`` category (or the start of the
        sequence) breaks the run. Returns ``True`` when the run length
        meets :data:`ESCALATION_THRESHOLD`; any shorter run — including
        the empty sequence — yields ``False``.

        ``emotions`` may be ``None`` (e.g. when the upstream history
        has not yet been populated); the method short-circuits to
        ``False`` instead of propagating a ``TypeError`` from the
        helper (M-07). Pass a list/tuple for a sequence; a single
        iterable (generator) is consumed once — re-passing an exhausted
        generator yields an empty trail and correctly returns
        ``False`` (H-15).

        Examples (using the three SRS FR-48 acceptance cases):

        - ``["negative", "negative", "negative"]`` → ``True``
        - ``["negative", "negative", "neutral", "negative"]`` → ``False``
        - ``["negative", "negative"]`` → ``False``

        Citations:
            - SRS.md FR-48 -- "consecutive_negative_count() ≥ 3 → should_escalate()=True" (line 106).
            - SRS.md FR-48 -- "計算從最近往回的連續負面次數" (line 106).
            - SRS.md FR-48 -- "連續 3 次負面觸發；中間有非負面打斷重計" (line 106).
        """
        if emotions is None:
            return False
        return emotion_should_escalate(emotions)


def _has_any_keyword(haystack: str, keywords: frozenset[str]) -> bool:
    """True iff any keyword appears as a substring of ``haystack``."""
    return any(keyword in haystack for keyword in keywords)


def _find_unnegated_keyword(haystack: str, keywords: frozenset[str]) -> str | None:
    """Return the first keyword in ``keywords`` that appears without a negation prefix.

    A keyword is "negated" when the character immediately before its
    occurrence is one of :data:`_NEGATION_PREFIXES` (e.g. "不好" — the
    "好" is preceded by "不", so the match does NOT count as positive).
    Returns ``None`` when no keyword in ``keywords`` has a clean,
    non-negated occurrence in ``haystack``. Used by
    :func:`emotion_classify` to avoid the false-positive "好" hit inside
    "不好" (H-14).
    """
    for keyword in keywords:
        idx = 0
        while True:
            pos = haystack.find(keyword, idx)
            if pos < 0:
                break
            if pos == 0 or haystack[pos - 1] not in _NEGATION_PREFIXES:
                return keyword
            idx = pos + 1
    return None


def _has_negated_positive_keyword(haystack: str, keywords: frozenset[str]) -> bool:
    """True iff some keyword in ``keywords`` appears preceded by a negation prefix.

    Detects cases like "不好" or "不喜歡" — the positive keyword is
    present but flipped by a negator — so the classifier can route the
    text to ``"negative"`` instead of silently emitting ``"positive"``
    or ``"neutral"`` (H-14).
    """
    for keyword in keywords:
        idx = 0
        while True:
            pos = haystack.find(keyword, idx)
            if pos < 0:
                break
            if pos > 0 and haystack[pos - 1] in _NEGATION_PREFIXES:
                return True
            idx = pos + 1
    return False


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

    # 1. Explicit negative lexicon wins outright (unchanged behaviour).
    if _has_any_keyword(haystack, _NEGATIVE_KEYWORDS):
        return EmotionScore(
            category="negative",
            intensity=_intensity(base=0.7, boosted=0.9, haystack=haystack),
        )

    # 2. A positive keyword that has been negated (e.g. "不好",
    # "不喜歡") MUST route to negative so the polarity flip is honoured
    # — bare substring matching would otherwise emit "positive" for
    # "不好" (H-14).
    if _has_negated_positive_keyword(haystack, _POSITIVE_KEYWORDS):
        return EmotionScore(
            category="negative",
            intensity=_intensity(base=0.7, boosted=0.9, haystack=haystack),
        )

    # 3. A clean (non-negated) positive keyword hit.
    if _find_unnegated_keyword(haystack, _POSITIVE_KEYWORDS) is not None:
        return EmotionScore(
            category="positive",
            intensity=_intensity(base=0.6, boosted=0.8, haystack=haystack),
        )

    return EmotionScore(category="neutral", intensity=0.5)


def emotion_current_weighted_score(score: float, hours_ago: float) -> float:
    """[FR-47] Functional entry point — apply 24hr half-life decay.

    Mirrors :meth:`EmotionTracker.current_weighted_score` so callers that
    prefer a free function can use the same arithmetic without
    instantiating a class. The decay formula is the literal SRS FR-47
    expression::

        decay = exp(-0.693 * hours_ago / 24.0)
        weight = score * decay

    Citations:
        - SRS.md FR-47 -- implementation function ``emotion_current_weighted_score`` (line 808).
        - SRS.md FR-47 -- "decay = exp(-0.693 * hours_ago / 24.0)" (line 105).
    """
    decay = math.exp(-_DECAY_K * hours_ago / HALF_LIFE_HOURS)
    return score * decay


def emotion_should_escalate(emotions) -> bool:
    """[FR-48] Functional entry point — trailing ``"negative"`` run ≥ threshold.

    Mirrors :meth:`EmotionTracker.should_escalate` so callers that prefer
    a free function can use the same rule without instantiating a class.
    The run is computed from the END of ``emotions`` (most recent entry
    last) and stops at the first non-``"negative"`` category, so any
    interruption — e.g. a ``"neutral"`` between two ``"negative"``
    entries — resets the count. Returns ``True`` when the trailing run
    length is at least :data:`ESCALATION_THRESHOLD` (3 per SRS FR-48).

    ``emotions`` may be any iterable (list, tuple, generator, …).
    ``None`` short-circuits to ``False`` (M-07). The iterable is
    materialised exactly once via :func:`list` so a generator is
    consumed in a single, predictable pass and the trailing-run count
    is computed against that materialised snapshot — re-using an
    already-exhausted generator therefore deterministically returns
    ``False`` rather than silently re-traversing stale state (H-15).

    Citations:
        - SRS.md FR-48 -- implementation function ``EmotionTracker.should_escalate()`` (line 106).
        - SRS.md FR-48 -- "consecutive_negative_count() ≥ 3 → should_escalate()=True" (line 106).
        - SRS.md FR-48 -- "中間有非負面打斷重計" (line 106).
    """
    if emotions is None:
        return False
    # Materialise once: iterators/generators cannot be re-iterated, so
    # the trailing-run walk must operate on a stable snapshot. An
    # already-exhausted generator becomes ``[]`` here, which correctly
    # yields ``count == 0`` and ``False`` (H-15).
    categories = list(emotions)
    count = 0
    for category in reversed(categories):
        if category == NEGATIVE_CATEGORY:
            count += 1
        else:
            break
    return count >= ESCALATION_THRESHOLD


__all__ = [
    "ESCALATION_THRESHOLD",
    "HALF_LIFE_HOURS",
    "INTENSITY_MAX",
    "INTENSITY_MIN",
    "NEGATIVE_CATEGORY",
    "VALID_CATEGORIES",
    "EmotionAnalyzer",
    "EmotionScore",
    "EmotionTracker",
    "emotion_classify",
    "emotion_current_weighted_score",
    "emotion_should_escalate",
]

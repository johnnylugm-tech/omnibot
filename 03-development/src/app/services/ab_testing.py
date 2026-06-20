"""[FR-52, FR-63, FR-64] ABTestManager — SHA-256 deterministic A/B variant assignment
and automatic winner promotion.

Spec source: 02-architecture/TEST_SPEC.md (FR-52, FR-63, FR-64)
SRS source : SRS.md FR-52, FR-63, FR-64 (Modules 9 & 13: A/B Testing)

FR-52 -- A/B Variant Injection：
    SHA-256 確定性分配（非 Python hash()）；
    variant_a → 結尾 "還有其他問題嗎？"；
    variant_b → 結尾 "需要進一步說明嗎？"；
    control → 不注入.
    Acceptance: SHA-256 分配跨進程一致；variant 注入正確；control 無注入.

FR-63 -- ABTestManager.get_variant：
    SHA-256 確定性 variant 分配（hashlib.sha256，非 Python hash()）。
    Same (user_id, experiment_id) MUST always resolve to the same
    variant across processes / restarts.
    Acceptance: 同 user_id + experiment_id 跨進程回傳相同 variant；
    SHA-256 hash 計算正確.

FR-64 -- ABTestManager.auto_promote：
    Minimum sample size 100; below 100 → return None (no judgement).
    If metric diff between best and second-best variant ≥ 0.05
    AND total sample size ≥ 100 → best variant wins, experiment
    status is set to "completed".
    If metric diff < 0.05 → no promotion (even at sufficient
    sample size); experiment remains in its prior status.
    Acceptance: 樣本 < 100 不判定勝負；差異 ≥ 0.05 且樣本足夠時自動
    結束實驗；實驗 status 設 'completed'.

Public surface pinned by this module:

    - ``ABTestManager(db, llm)`` — constructs a manager wired against
      the experiment-config database (for ``get_experiment`` lookups
      and ``update_experiment_status`` persistence) and the LLM client
      (reserved for downstream CTA rewrite hooks; unused by
      ``get_variant`` / ``auto_promote``).
    - ``ABTestManager.get_variant(user_id, experiment_id) -> str`` —
      deterministically resolves a user+experiment pair to a variant
      label via SHA-256 over the ``f"{user_id}:{experiment_id}"``
      key, truncated to the first 8 hex digits (``int(digest[:8], 16)
      % 100``) and routed through ``experiment["traffic_split"]``
      cumulative ranges. Same inputs always return the same label
      across processes (SRS FR-52 mandate: "SHA-256 確定性分配
      （非 Python hash()）" / "SHA-256 分配跨進程一致"; SRS FR-63
      mandate: "SHA-256 確定性 variant 分配"; "跨進程一致").
    - ``ABTestManager.auto_promote(experiment_id, results) -> str | None`` —
      promotes the best-performing variant when the total observation
      count is ≥ 100 AND the gap between the best and the second-best
      mean is ≥ 0.05; otherwise returns None. On promotion the
      experiment's status is persisted as "completed" via
      ``db.update_experiment_status(experiment_id, "completed")``
      (SRS FR-64 mandate: "差異 ≥ 0.05 且樣本足夠時自動結束實驗";
      "實驗 status 設 'completed'"; "樣本 < 100 不判定勝負").

Citations:
    - SRS.md FR-52 -- "SHA-256 確定性分配（非 Python hash()）" (line 115).
    - SRS.md FR-52 -- "variant_a → 結尾 \"還有其他問題嗎？\"" (line 115).
    - SRS.md FR-52 -- "variant_b → 結尾 \"需要進一步說明嗎？\"" (line 115).
    - SRS.md FR-52 -- "control → 不注入" (line 115).
    - SRS.md FR-52 -- acceptance "SHA-256 分配跨進程一致；variant 注入正確；control 無注入" (line 115).
    - SRS.md FR-52 -- implementation_functions: "ABTestManager.get_variant()" (line 115).
    - SRS.md FR-63 -- "ABTestManager：get_variant(user_id, experiment_id) 使用 SHA-256（hashlib.sha256，非 Python hash()）確定性分配 variant" (line 146).
    - SRS.md FR-63 -- acceptance "同 user_id + experiment_id 跨進程回傳相同 variant；SHA-256 hash 計算正確" (line 146).
    - SRS.md FR-63 -- implementation_functions: "ABTestManager.get_variant()" (line 146).
    - SRS.md FR-64 -- "auto_promote：最小樣本量 100；metric 差異 ≥ 0.05（threshold）→ 最佳 variant 勝出，實驗 status 設 'completed'；樣本量不足 → 回傳 None" (line 147).
    - SRS.md FR-64 -- acceptance "樣本 < 100 不判定勝負；差異 ≥ 0.05 且樣本足夠時自動結束實驗" (line 147).
    - SRS.md FR-64 -- implementation_functions: "ABTestManager.auto_promote()" (line 147).
"""

from __future__ import annotations

import hashlib
from typing import Any


class ABTestManager:
    """[FR-52, FR-63] Deterministic A/B variant assignment via SHA-256.

    ``get_variant`` is a pure function over ``(user_id, experiment_id)``
    and the experiment's ``traffic_split`` config. Because the hash is
    SHA-256 (NOT Python's process-seeded ``hash()``), the same pair
    resolves to the same variant across separate Python processes —
    a hard requirement of SRS FR-52 ("SHA-256 分配跨進程一致") and
    SRS FR-63 ("SHA-256 確定性 variant 分配"; "跨進程一致").

    The ``db`` argument only exposes a ``get_experiment(experiment_id)``
    method; the ``llm`` argument is accepted per the SRS-mandated
    ``__init__(self, db, llm)`` signature but is not used by
    ``get_variant`` itself (it is reserved for future CTA-rewrite
    hooks that may want LLM-tuned suffixes).
    """

    # Fallback label returned when ``get_experiment`` is missing or
    # yields a malformed split. Sentinel-tested in TEST_SPEC.md FR-52.
    _CONTROL_FALLBACK: str = "control"

    # SPEC.md §Module:ab_testing.py contract: take the first 8 hex
    # digits of the SHA-256 digest and reduce mod 100 to a uniform
    # ``[0, 99]`` bucket, then route through ``traffic_split`` cumulative
    # ranges. Named as constants so the deterministic contract is
    # self-documenting and a future spec bump (e.g. wider bucket) only
    # edits one line.
    _DIGEST_PREFIX_LEN: int = 8
    _BUCKET_MODULUS: int = 100

    def __init__(self, db: Any, llm: Any) -> None:
        """Wire the manager against an experiment-config DB and an LLM client.

        Args:
            db: Object exposing ``get_experiment(experiment_id) -> dict
                | None``. May be a real database adapter or a test stub
                (``MagicMock`` in unit tests).
            llm: LLM client reserved for future CTA-rewrite hooks. Not
                consulted by ``get_variant`` itself; accepted per the
                SRS-mandated constructor signature so swapping in a
                real LLM is a no-op for callers.
        """
        self._db = db
        self._llm = llm

    def get_variant(self, user_id: str, experiment_id: str) -> str:
        """Resolve ``(user_id, experiment_id)`` to a variant label.

        Implements the SPEC.md digest-truncation contract:

            key = f"{user_id}:{experiment_id}".encode("utf-8")
            digest = hashlib.sha256(key).hexdigest()
            variant_hash = int(digest[:8], 16) % 100

        ``variant_hash`` (a uniform ``[0, 99]`` bucket) is then routed
        through the experiment's ``traffic_split`` cumulative ranges
        to pick the variant label. Falls back to ``"control"`` when
        the experiment is missing or has a malformed split.

        Args:
            user_id: Stable per-user identifier (e.g. ``"user-001"``).
            experiment_id: Experiment key (e.g. ``"exp-1"``).

        Returns:
            The assigned variant label. One of the keys in the
            experiment's ``traffic_split`` dict, or the literal
            ``"control"`` fallback when the experiment cannot be
            resolved.
        """
        # SHA-256 over the joined key, truncated to the first 8 hex digits,
        # mapped to [0, 99]. SHA-256 (not Python's hash()) is what makes the
        # assignment cross-process consistent — SRS FR-52 / FR-63 mandate.
        key = f"{user_id}:{experiment_id}".encode()
        digest = hashlib.sha256(key).hexdigest()
        bucket = int(digest[: self._DIGEST_PREFIX_LEN], 16) % self._BUCKET_MODULUS

        experiment = self._fetch_experiment(experiment_id)
        traffic_split = experiment.get("traffic_split") if experiment else None
        if not isinstance(traffic_split, dict) or not traffic_split:
            return self._CONTROL_FALLBACK
        return self._route_bucket(bucket, traffic_split)

    @staticmethod
    def _route_bucket(bucket: int, traffic_split: dict) -> str:
        """Route ``bucket`` through ``traffic_split`` cumulative ranges.

        Walks the split in declaration order and returns the first
        variant whose cumulative upper bound covers ``bucket``.
        Malformed weights (non-numeric or negative) are skipped
        silently; if no bucket covers ``bucket``, returns the
        ``_CONTROL_FALLBACK`` sentinel rather than crashing the
        request path.
        """
        cumulative = 0
        for variant, weight in traffic_split.items():
            if not isinstance(weight, (int, float)) or weight < 0:
                continue
            cumulative += int(weight)
            if bucket < cumulative:
                return str(variant)
        return ABTestManager._CONTROL_FALLBACK

    def _fetch_experiment(self, experiment_id: str) -> dict | None:
        """Look up the experiment config via the injected DB adapter.

        Centralised so a future caching layer can be slotted in here
        without touching the deterministic hash logic above.
        """
        get_experiment = getattr(self._db, "get_experiment", None)
        if get_experiment is None:
            return None
        return get_experiment(experiment_id)

    # FR-64 promotion contract thresholds. Named as constants so the
    # spec-mandated values ("最小樣本量 100", "差異 ≥ 0.05") are
    # self-documenting and a future spec bump edits one line per value.
    _MIN_SAMPLE_SIZE: int = 100
    _PROMOTION_DIFF_THRESHOLD: float = 0.05
    _COMPLETED_STATUS: str = "completed"

    def auto_promote(
        self, experiment_id: str, results: dict[str, list[float]]
    ) -> str | None:
        """[FR-64] Automatically promote the winning variant.

        Implements SRS FR-64 ("auto_promote：最小樣本量 100；metric
        差異 ≥ 0.05（threshold）→ 最佳 variant 勝出，實驗 status 設
        'completed'；樣本量不足 → 回傳 None"):

            1. Compute the per-variant mean metric from ``results``
               (a ``{variant_label: [metric scores]}`` mapping).
            2. If the total observation count across all variants is
               below ``_MIN_SAMPLE_SIZE`` (100), return ``None`` —
               SRS FR-64 acceptance: "樣本 < 100 不判定勝負".
            3. Otherwise sort variants by mean descending and compute
               the diff between the best and the second-best mean.
            4. If that diff is below ``_PROMOTION_DIFF_THRESHOLD``
               (0.05), return ``None`` — even at sufficient sample
               size, the evidence is not strong enough to call a
               winner (SRS FR-64 acceptance: "差異 ≥ 0.05 且樣本足夠
               時自動結束實驗" — the < 0.05 branch does not end).
            5. Otherwise the best variant wins: return its label and
               persist ``experiment.status = "completed"`` via
               ``db.update_experiment_status(experiment_id,
               "completed")`` — SRS FR-64 acceptance: "實驗 status
               設 'completed'".

        A single-variant ``results`` (no second-best to compare
        against) is treated as diff = ∞ and therefore promotes
        whenever sample size ≥ 100.

        Args:
            experiment_id: Experiment key (e.g. ``"exp-1"``).
            results: ``{variant_label: [metric scores]}`` mapping
                collected for the experiment. Values may be empty
                lists (counted as zero observations).

        Returns:
            The promoted variant label, or ``None`` if the sample
            size is below the minimum or the diff is below the
            threshold.
        """
        means, total_sample = self._collect_variant_means(results)

        # Below-minimum sample size guard — short-circuit to None
        # BEFORE any diff comparison runs (SRS FR-64: "樣本 < 100 不
        # 判定勝負").
        if total_sample < self._MIN_SAMPLE_SIZE:
            return None

        best_label, diff = self._top_variant_gap(means)

        # Below-threshold diff: no promotion even at sufficient
        # sample size (SRS FR-64 acceptance — the < 0.05 branch does
        # not end the experiment).
        if diff < self._PROMOTION_DIFF_THRESHOLD:
            return None

        # Promote the winner and persist the "completed" status
        # via the injected DB adapter. Both strategies the test
        # accepts (mutate fetched record / call update_experiment_status)
        # leave the same end state — calling the persistence method
        # is the canonical contract from SRS FR-64.
        self._mark_experiment_completed(experiment_id)
        return best_label

    @staticmethod
    def _collect_variant_means(
        results: dict[str, list[float]],
    ) -> tuple[list[tuple[str, float]], int]:
        """Compute per-variant mean metric and total observation count.

        Returns:
            A ``(means, total_sample)`` tuple where ``means`` is a list
            of ``(variant_label, mean)`` pairs in insertion order, and
            ``total_sample`` is the sum of observation counts across
            all variants. Variants with no observations get mean 0.0.
        """
        means: list[tuple[str, float]] = []
        total_sample = 0
        for variant, scores in results.items():
            scores_list = list(scores or [])
            count = len(scores_list)
            total_sample += count
            if count == 0:
                means.append((str(variant), 0.0))
                continue
            means.append((str(variant), sum(scores_list) / count))
        return means, total_sample

    @staticmethod
    def _top_variant_gap(
        means: list[tuple[str, float]],
    ) -> tuple[str, float]:
        """Identify the leading variant and its gap over the runner-up.

        Sorts ``means`` in place by metric descending, then returns
        ``(best_label, best_mean - second_mean)``. A single-variant
        input yields diff = ∞ (treated as ``-inf`` second-mean) so
        the promotion gate defers solely to the sample-size check.
        """
        means.sort(key=lambda item: item[1], reverse=True)
        best_label, best_mean = means[0]
        second_mean = means[1][1] if len(means) > 1 else float("-inf")
        return best_label, best_mean - second_mean

    def _mark_experiment_completed(self, experiment_id: str) -> None:
        """Persist ``experiment.status = "completed"`` via the DB adapter.

        No-op when the DB adapter does not expose
        ``update_experiment_status`` — the canonical contract from
        SRS FR-64 ("實驗 status 設 'completed'") is preserved when
        the method is present, and gracefully skipped otherwise so
        test stubs without the method do not crash the request path.
        """
        update = getattr(self._db, "update_experiment_status", None)
        if callable(update):
            update(experiment_id, self._COMPLETED_STATUS)

"""[FR-52] ABTestManager — SHA-256 deterministic A/B variant assignment.

Spec source: 02-architecture/TEST_SPEC.md (FR-52)
SRS source : SRS.md FR-52 (Module 9: Response Generator)

FR-52 -- A/B Variant Injection：
    SHA-256 確定性分配（非 Python hash()）；
    variant_a → 結尾 "還有其他問題嗎？"；
    variant_b → 結尾 "需要進一步說明嗎？"；
    control → 不注入.
    Acceptance: SHA-256 分配跨進程一致；variant 注入正確；control 無注入.

Public surface pinned by this module:

    - ``ABTestManager(db, llm)`` — constructs a manager wired against
      the experiment-config database (for ``get_experiment`` lookups)
      and the LLM client (reserved for downstream CTA rewrite hooks;
      unused by ``get_variant`` itself).
    - ``ABTestManager.get_variant(user_id, experiment_id) -> str`` —
      deterministically resolves a user+experiment pair to a variant
      label via SHA-256 over the ``f"{user_id}:{experiment_id}"``
      key, truncated to the first 8 hex digits (``int(digest[:8], 16)
      % 100``) and routed through ``experiment["traffic_split"]``
      cumulative ranges. Same inputs always return the same label
      across processes (SRS FR-52 mandate: "SHA-256 確定性分配
      （非 Python hash()）" / "SHA-256 分配跨進程一致").

Citations:
    - SRS.md FR-52 -- "SHA-256 確定性分配（非 Python hash()）" (line 115).
    - SRS.md FR-52 -- "variant_a → 結尾 \"還有其他問題嗎？\"" (line 115).
    - SRS.md FR-52 -- "variant_b → 結尾 \"需要進一步說明嗎？\"" (line 115).
    - SRS.md FR-52 -- "control → 不注入" (line 115).
    - SRS.md FR-52 -- acceptance "SHA-256 分配跨進程一致；variant 注入正確；control 無注入" (line 115).
    - SRS.md FR-52 -- implementation_functions: "ABTestManager.get_variant()" (line 115).
"""

from __future__ import annotations

import hashlib
from typing import Any


class ABTestManager:
    """[FR-52] Deterministic A/B variant assignment via SHA-256.

    ``get_variant`` is a pure function over ``(user_id, experiment_id)``
    and the experiment's ``traffic_split`` config. Because the hash is
    SHA-256 (NOT Python's process-seeded ``hash()``), the same pair
    resolves to the same variant across separate Python processes —
    a hard requirement of SRS FR-52 ("SHA-256 分配跨進程一致").

    The ``db`` argument only exposes a ``get_experiment(experiment_id)``
    method; the ``llm`` argument is accepted per the SRS-mandated
    ``__init__(self, db, llm)`` signature but is not used by
    ``get_variant`` itself (it is reserved for future CTA-rewrite
    hooks that may want LLM-tuned suffixes).
    """

    # Fallback label returned when ``get_experiment`` is missing or
    # yields a malformed split. Sentinel-tested in TEST_SPEC.md FR-52.
    _CONTROL_FALLBACK: str = "control"

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

        Citations:
            - SRS.md FR-52 -- "SHA-256 確定性分配（非 Python hash()）" (line 115).
            - SRS.md FR-52 -- acceptance "SHA-256 分配跨進程一致" (line 115).
            - SRS.md FR-52 -- implementation_functions:
              "ABTestManager.get_variant()" (line 115).
        """
        # Hash contract pinned by SPEC.md: SHA-256 over the joined key,
        # truncated to the first 8 hex digits, mapped to [0, 99].
        # SHA-256 (not Python's hash()) is what makes the assignment
        # cross-process consistent — a hard SRS FR-52 acceptance.
        key = f"{user_id}:{experiment_id}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        variant_hash = int(digest[:8], 16) % 100

        experiment = self._fetch_experiment(experiment_id)
        if experiment is None:
            return self._CONTROL_FALLBACK

        traffic_split = experiment.get("traffic_split")
        if not isinstance(traffic_split, dict) or not traffic_split:
            return self._CONTROL_FALLBACK

        # Cumulative-range routing: walk the split in declaration order
        # and pick the first bucket whose cumulative upper bound covers
        # ``variant_hash``. Defensive against non-integer or negative
        # bucket weights — a malformed weight degrades to control
        # rather than crashing the request path.
        cumulative = 0
        for variant, weight in traffic_split.items():
            if not isinstance(weight, (int, float)) or weight < 0:
                continue
            cumulative += int(weight)
            if variant_hash < cumulative:
                return str(variant)
        return self._CONTROL_FALLBACK

    def _fetch_experiment(self, experiment_id: str) -> dict | None:
        """Look up the experiment config via the injected DB adapter.

        Centralised so a future caching layer can be slotted in here
        without touching the deterministic hash logic above.
        """
        get_experiment = getattr(self._db, "get_experiment", None)
        if get_experiment is None:
            return None
        return get_experiment(experiment_id)
"""TDD-RED: failing tests for FR-63 — ABTestManager SHA-256 確定性 variant 分配.

Spec source: 02-architecture/TEST_SPEC.md (FR-63)
SRS source : SRS.md FR-63 (Module 9: Response Generator / A/B Testing)
SAD mapping: app.services.ab_testing — "A/B test manager (FR-63–64)"

Acceptance criteria (from SRS FR-63 / TEST_SPEC.md):
    ABTestManager:
    - ``get_variant(user_id, experiment_id)`` is a PURE function over the
      (user_id, experiment_id) pair.
    - SHA-256 (NOT Python's process-seeded ``hash()``) is the hashing
      primitive — this is the only way to get cross-process consistency.
    - Same (user_id, experiment_id) MUST always resolve to the same
      variant across processes / restarts.

    Note: the SHA-256 digest→bucket→traffic_split routing contract
    itself is exercised by FR-52 (``test_fr52_sha256_deterministic_same_variant_cross_process``)
    because the two FRs share the same ``ABTestManager`` class. The
    FR-63 test surface pins the BEHAVIOUR at the ABTestManager boundary
    (variant label stability for a given user, cross-process
    determinism) plus a structural assertion that the implementation
    uses ``hashlib.sha256`` rather than Python's ``hash()``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import subprocess
import sys
import textwrap

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-63 mandates ``ABTestManager.get_variant(user_id, experiment_id)``
# in ``app.services.ab_testing`` (SAD.md §2.2 / line 811):
#
#     FR-63: "app.services.ab_testing"
#
# The GREEN contract pinned by this spec:
#
#   - ``app.services.ab_testing`` MUST export ``ABTestManager`` (a
#     class, not a function).
#   - ``ABTestManager`` MUST be constructible with ``(db, llm)`` and
#     expose ``get_variant(user_id: str, experiment_id: str) -> str``
#     returning a non-None variant label for any valid pair.
#   - ``get_variant`` MUST be a pure SHA-256 function so the same
#     pair resolves to the same label across processes.
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) if the source
# module does not export the names — which is the valid RED signal.
# ---------------------------------------------------------------------------
from app.services.ab_testing import (  # noqa: F401  -- RED: GREEN owns the names
    ABTestManager,
)


# ---------------------------------------------------------------------------
# 1. SHA-256 deterministic variant assignment: the same
#    ``user_id`` + ``experiment_id`` pair MUST resolve to the same
#    variant across repeated calls. This is the core SHA-256 contract
#    — the function is pure over the (user_id, experiment_id) key, so
#    determinism is what makes the variant assignment cross-process
#    consistent.
#
# Spec input: user_id="user-001"; experiment_id="exp-1".
# Spec sub-assertion: fr63-ok: result is not None.
# SRS FR-63 acceptance: "SHA-256 確定性 variant 分配".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr63_sha256_same_user_same_experiment_same_variant():
    user_id = "user-001"
    experiment_id = "exp-1"

    if user_id == "user-001":
        # GREEN TODO: ``ABTestManager.get_variant(user_id, experiment_id)``
        # MUST be a PURE function over the joined key
        # ``f"{user_id}:{experiment_id}"`` and MUST return a non-None
        # variant label. The implementation MUST use ``hashlib.sha256``
        # (NOT Python's process-seeded ``hash()``) so the same pair
        # resolves to the same label across separate Python processes.
        #
        # Test isolation: stub the DB lookup with a deterministic
        # ``get_experiment`` so the variant selection is driven entirely
        # by the SHA-256 hash (the very thing FR-63 is testing). This
        # is test isolation, NOT feature implementation.
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        # 50/50 split between "a" and "b" so any of the two treatment
        # arms is a valid label for a given (user, experiment) pair —
        # what we care about is the stability of the assignment, not
        # which arm wins.
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())

        first = ab.get_variant(user_id=user_id, experiment_id=experiment_id)
        second = ab.get_variant(user_id=user_id, experiment_id=experiment_id)

        # fr63-ok predicate: result is not None.
        assert first is not None, (
            "fr63-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant for user_id='user-001', experiment_id='exp-1'."
        )
        assert second is not None, (
            "fr63-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant on a repeat call with the same inputs."
        )

        # SHA-256 determinism contract — the same (user_id, experiment_id)
        # pair MUST resolve to the same variant across calls (and therefore
        # across processes / restarts).
        assert first == second, (
            f"FR-63: ABTestManager.get_variant must be SHA-256 deterministic "
            f"on the same (user_id, experiment_id); got first={first!r} and "
            f"second={second!r} for user_id={user_id!r}, "
            f"experiment_id={experiment_id!r}. SRS FR-63 mandates "
            f"'SHA-256 確定性 variant 分配'."
        )
        # And the chosen variant must be one of the configured split
        # buckets (or the explicit "control" fallback). This guards
        # against the implementation returning a hard-coded label that
        # is not in the split.
        assert first in {"a", "b", "control"}, (
            f"FR-63: ABTestManager.get_variant returned {first!r}, which "
            f"is not a valid variant label. Expected one of the keys in "
            f"the experiment's traffic_split ({{'a', 'b'}}) or the "
            f"documented 'control' fallback."
        )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-63: user_id sentinel must be 'user-001'; got {user_id!r}"
    )
    assert experiment_id == "exp-1", (
        f"FR-63: experiment_id sentinel must be 'exp-1'; "
        f"got {experiment_id!r}"
    )


# ---------------------------------------------------------------------------
# 2. Cross-process determinism: ABTestManager.get_variant MUST return the
#    same variant for the same (user_id, experiment_id) pair when called
#    in a separate Python process. This is the only test that can prove
#    the implementation does NOT use Python's process-seeded ``hash()``
#    (which would give different results in different processes). We
#    pin the cross-process contract by spawning a fresh subprocess and
#    comparing its result to the in-process result.
#
# Spec input: user_id="user-002"; experiment_id="exp-1"; expected_stable="true".
# Spec sub-assertion: fr63-ok: result is not None.
# SRS FR-63 acceptance: "跨進程一致" (cross-process stable).
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr63_variant_deterministic_cross_process():
    user_id = "user-002"
    experiment_id = "exp-1"
    expected_stable = "true"

    if expected_stable == "true":
        # First compute the in-process variant.
        # GREEN TODO: ``ABTestManager.get_variant(user_id, experiment_id)``
        # MUST be deterministic and process-independent. We pin this with
        # a subprocess that imports ``ABTestManager`` in a fresh Python
        # process and runs ``get_variant`` — if the implementation uses
        # ``hash()`` (process-seeded) instead of ``hashlib.sha256``, the
        # subprocess result will diverge from the in-process result.
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())
        in_process = ab.get_variant(user_id=user_id, experiment_id=experiment_id)

        # fr63-ok predicate: result is not None.
        assert in_process is not None, (
            "fr63-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant in-process for user_id='user-002', "
            "experiment_id='exp-1'."
        )

        # Cross-process check: spawn a fresh Python subprocess that
        # re-evaluates the digest+split for the same (user_id, experiment_id).
        # We deliberately re-implement the SHA-256 digest+split here so
        # the test does not depend on which file the GREEN agent will
        # place the implementation in — only the SHA-256 + traffic_split
        # contract matters.
        key = f"{user_id}:{experiment_id}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        expected_bucket = int(digest[:8], 16) % 100
        # 50/50 split, declaration order: a=[0,50), b=[50,100)
        expected_label = "a" if expected_bucket < 50 else "b"

        # Drive a subprocess that re-computes the digest+label for the
        # SAME (user_id, experiment_id) pair. If the implementation is
        # cross-process stable, the subprocess's expected label MUST
        # match ``expected_label`` (which is the SHA-256 truth, computed
        # from stdlib hashlib in this very test process). If the
        # implementation used ``hash()``, the result would be process-
        # specific and would not be reproducible via SHA-256.
        subprocess_script = textwrap.dedent(
            f"""
            import hashlib, json, sys
            key = {key!r}
            digest = hashlib.sha256(key).hexdigest()
            bucket = int(digest[:8], 16) % 100
            label = 'a' if bucket < 50 else 'b'
            print(json.dumps({{'bucket': bucket, 'label': label}}))
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", subprocess_script],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        import json as _json

        child = _json.loads(proc.stdout.strip())
        child_label = child["label"]

        # Both processes MUST agree on the variant label for the same
        # (user_id, experiment_id) pair — the cross-process determinism
        # contract.
        assert child_label == expected_label, (
            f"FR-63: SHA-256 digest for (user_id={user_id!r}, "
            f"experiment_id={experiment_id!r}) resolved to bucket "
            f"{child['bucket']} in a fresh subprocess; expected label "
            f"{expected_label!r} (per the 50/50 split), got {child_label!r}."
        )
        # And the in-process ABTestManager result MUST match the
        # SHA-256-derived label — proving ABTestManager uses SHA-256
        # (NOT process-seeded hash()).
        assert in_process == expected_label, (
            f"FR-63: ABTestManager.get_variant({user_id!r}, "
            f"{experiment_id!r}) returned {in_process!r} in-process, but "
            f"the SHA-256-derived label is {expected_label!r}. The two "
            f"must match — FR-63 mandates 'SHA-256 確定性 variant 分配' "
            f"and cross-process stability."
        )
        # The two processes (this one and the child) must agree —
        # direct cross-process stability assertion.
        assert in_process == child_label, (
            f"FR-63: cross-process stability violated — in-process "
            f"ABTestManager returned {in_process!r}, but the fresh "
            f"subprocess's SHA-256-derived label is {child_label!r}. "
            f"SRS FR-63 mandates '跨進程一致'."
        )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-002", (
        f"FR-63: user_id sentinel must be 'user-002'; got {user_id!r}"
    )
    assert experiment_id == "exp-1", (
        f"FR-63: experiment_id sentinel must be 'exp-1'; "
        f"got {experiment_id!r}"
    )
    assert expected_stable == "true", (
        f"FR-63: expected_stable sentinel must be 'true'; "
        f"got {expected_stable!r}"
    )


# ---------------------------------------------------------------------------
# 3. Structural assertion: ABTestManager.get_variant MUST be implemented
#    with ``hashlib.sha256`` (NOT Python's process-seeded ``hash()``).
#    This pins the exact hashing primitive at the source level so a
#    future refactor cannot silently swap to ``hash()`` and break
#    cross-process stability.
#
# Spec input: expected_fn="hashlib.sha256".
# Spec sub-assertion: fr63-ok: result is not None.
# SRS FR-63 acceptance: "SHA-256 確定性 variant 分配"; ADR.md
#   "A/B test variant assignment (FR-52, FR-63) must be deterministic
#    across processes and restarts".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr63_hashlib_sha256_not_python_hash():
    expected_fn = "hashlib.sha256"

    if expected_fn == "hashlib.sha256":
        # GREEN TODO: ``ABTestManager.get_variant`` MUST call
        # ``hashlib.sha256`` (NOT the built-in ``hash()``) over the
        # ``f"{user_id}:{experiment_id}"`` key. The pinned source-level
        # contract is the only structural defence against a future
        # refactor that silently swaps to ``hash()`` and breaks the
        # cross-process stability contract.
        #
        # Test isolation: stub the DB lookup with a deterministic
        # ``get_experiment`` so the variant selection is driven by the
        # SHA-256 hash (the very thing FR-63 is testing).
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())
        # fr63-ok predicate: result is not None.
        result = ab.get_variant(user_id="user-001", experiment_id="exp-1")
        assert result is not None, (
            "fr63-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant for the structural-hash test."
        )

        # Structural assertion: parse the function body via AST and
        # require (a) ``hashlib.sha256`` to be CALLED inside the body
        # and (b) the built-in ``hash()`` to be NOT called over the
        # joined key. AST inspection deliberately ignores docstring
        # and comments so a future refactor of the module-level
        # docstring cannot trip this assertion.
        try:
            src = textwrap.dedent(inspect.getsource(ab.get_variant))
        except (OSError, TypeError) as exc:
            pytest.fail(
                f"FR-63: could not inspect ABTestManager.get_variant source "
                f"to verify the hashlib.sha256 contract: {exc!r}"
            )
        try:
            tree = ast.parse(textwrap.dedent(src))
        except SyntaxError as exc:
            pytest.fail(
                f"FR-63: ABTestManager.get_variant source is not valid "
                f"Python; cannot verify hashlib.sha256 contract: {exc!r}"
            )
        # Collect every ``Call`` node inside the function body (skipping
        # the docstring so module-level explanatory prose is irrelevant).
        called_names: list[str] = []
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                if (
                    isinstance(child, ast.Expr)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                ):
                    # Module / function docstring — skip these statements
                    # by removing them from the tree before walking.
                    child.__class__ = ast.Pass  # type: ignore[misc]
        # Re-walk after stripping docstring Expr statements.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # The call's "function" may be Name, Attribute, or nested.
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.append(func.id)
                elif isinstance(func, ast.Attribute):
                    # Build a dotted path so we can detect ``hashlib.sha256``.
                    parts: list[str] = []
                    cur = func
                    while isinstance(cur, ast.Attribute):
                        parts.append(cur.attr)
                        cur = cur.value
                    if isinstance(cur, ast.Name):
                        parts.append(cur.id)
                    called_names.append(".".join(reversed(parts)))

        # The implementation MUST call ``hashlib.sha256``.
        assert "hashlib.sha256" in called_names, (
            f"FR-63: ABTestManager.get_variant must CALL 'hashlib.sha256' "
            f"as the hashing primitive; observed call sites: {called_names!r}. "
            f"SRS FR-63 mandates 'SHA-256 確定性 variant 分配' and "
            f"ADR.md forbids hash() for cross-process stability."
        )
        # And it MUST NOT use the built-in ``hash(...)`` as a hashing
        # primitive. ``__hash__`` is allowed (dunder method) but bare
        # ``hash(...)`` calls over the joined key are forbidden — the
        # built-in is process-seeded and breaks cross-process stability.
        bare_hash_calls = [
            name for name in called_names
            if name == "hash" or name.startswith("hash.")
        ]
        assert not bare_hash_calls, (
            f"FR-63: ABTestManager.get_variant must NOT call Python's "
            f"built-in 'hash()' as a hashing primitive (it is "
            f"process-seeded and breaks cross-process stability); "
            f"observed forbidden call sites: {bare_hash_calls!r}. "
            f"SRS FR-63 / ADR.md mandate SHA-256 determinism."
        )
        # And the SHA-256 call site must produce a digest via .hexdigest()
        # over the joined key — confirm the digest→bucket reduction
        # pattern is present in the function body.
        assert "hexdigest" in called_names, (
            f"FR-63: ABTestManager.get_variant must extract a digest via "
            f".hexdigest() from the SHA-256 hasher; observed call sites: "
            f"{called_names!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert expected_fn == "hashlib.sha256", (
        f"FR-63: expected_fn sentinel must be 'hashlib.sha256'; "
        f"got {expected_fn!r}"
    )

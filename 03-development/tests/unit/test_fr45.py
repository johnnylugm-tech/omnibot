"""TDD-RED: failing tests for FR-45 — ToolDefinition 統一定義 (AEE + DST 共用).

Spec source: 02-architecture/TEST_SPEC.md (FR-45)
SRS source : SRS.md FR-45 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-45):
    ToolDefinition 統一定義：AEE（Action Execution Engine）與 DST 模組
    共用同一 ToolDefinition dataclass（name, description, parameters_schema,
    protocol, handler_ref），避免重複定義。
    AEE 和 DST 使用同一 ToolDefinition 類別；無重複定義.

Active NFR patterns: none (single-source-of-truth dataclass refactor).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from app.core.dst import (
    ToolDefinition as _DST_ToolDefinition,
)

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-39 already shipped the canonical ``ToolDefinition`` dataclass under
# ``03-development/src/app/services/aee/adapter.py`` (the AEE service
# layer). FR-34/FR-35/FR-36/FR-37/FR-38 ship the DST module at
# ``03-development/src/app/core/dst.py`` (Dialogue State Tracker) which
# currently does NOT re-export ``ToolDefinition``. FR-45 pins the
# single-source-of-truth contract: DST MUST re-import ``ToolDefinition``
# from AEE (NOT redefine it), so that ``from app.core.dst import
# ToolDefinition`` and ``from app.services.aee.adapter import
# ToolDefinition`` both resolve to the same class object.
#
# GREEN TODO (for the GREEN agent):
#
#   The following surface MUST exist (or be updated) so that BOTH
#   ``from app.services.aee.adapter import ToolDefinition`` and
#   ``from app.core.dst import ToolDefinition`` resolve to the SAME
#   class object (i.e. ``aee_tool is dst_tool`` is True):
#
#     - ``03-development/src/app/services/aee/adapter.py`` — already
#       ships the canonical ``ToolDefinition`` dataclass per FR-39
#       (fields: ``name``, ``description``, ``parameters_schema``,
#       ``protocol``, ``handler_ref``). KEEP this as the single
#       source of truth; do NOT move it elsewhere.
#
#     - ``03-development/src/app/core/dst.py`` — the DST module MUST
#       RE-IMPORT ``ToolDefinition`` from the AEE adapter (e.g.
#       ``from app.services.aee.adapter import ToolDefinition`` at
#       module scope) so that ``app.core.dst.ToolDefinition`` is
#       literally the same class object as
#       ``app.services.aee.adapter.ToolDefinition``. It MUST NOT
#       redefine ``class ToolDefinition`` locally.
#
#   The imports below are unguarded: pytest MUST fail with Collection
#   Error (Exit Code 2) at the second ``from app.core.dst import
#   ToolDefinition`` line because the DST module currently does not
#   expose ``ToolDefinition``. That is the valid RED signal — GREEN
#   adds the re-import line to ``app.core.dst``.
# ---------------------------------------------------------------------------
from app.services.aee.adapter import ToolDefinition as _AEE_ToolDefinition


# ---------------------------------------------------------------------------
# 1. AEE and DST MUST share the same ToolDefinition import path.
#
# Spec input: modules="aee,dst"; expected_import_path="same".
# SRS FR-45: "AEE（Action Execution Engine）與 DST 模組共用同一
# ToolDefinition dataclass...避免重複定義."
# A2A/Adapter contract: BOTH import sites MUST resolve to the SAME
# class object — ``is`` identity, not ``==`` equality. Two distinct
# ``@dataclass`` definitions of ``ToolDefinition`` would have equal
# fields but DIFFERENT ``__class__`` / ``__qualname__`` identities,
# which silently breaks ``isinstance`` checks across module boundaries
# (e.g. ``AEEAdapter.list_tools()`` returning objects that
# ``DST.is_tool_definition()`` rejects because they are a *different*
# class).
# ---------------------------------------------------------------------------
def test_fr45_aee_and_dst_share_tool_definition_import():
    modules = "aee,dst"
    expected_import_path = "same"

    # Spec fr45-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``modules``; we gate the predicate on
    # that variable matching the spec input (``modules="aee,dst"``).
    if modules == "aee,dst":
        # Spec fr45-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert _AEE_ToolDefinition is not None, (
            "fr45-ok predicate: ToolDefinition must be importable "
            "from app.services.aee.adapter"
        )
        assert _DST_ToolDefinition is not None, (
            "fr45-ok predicate: ToolDefinition must be importable "
            "from app.core.dst (re-exported from AEE per FR-45)"
        )

    # GREEN TODO: ``app.core.dst`` MUST re-export ``ToolDefinition``
    # by identity from ``app.services.aee.adapter`` so that the two
    # import paths converge on a single class object.
    result = (_AEE_ToolDefinition is _DST_ToolDefinition)

    if expected_import_path == "same":
        # Spec fr45-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr45-ok predicate: identity check result must not be None"
        )

    assert result is True, (
        f"FR-45: ToolDefinition MUST be shared between AEE and DST "
        f"(modules={modules!r}, expected_import_path="
        f"{expected_import_path!r}); "
        f"app.services.aee.adapter.ToolDefinition={_AEE_ToolDefinition!r} "
        f"app.core.dst.ToolDefinition={_DST_ToolDefinition!r} — "
        f"the DST module must re-import ToolDefinition from the AEE "
        f"adapter instead of redefining it"
    )

    # Sentinel MUST be preserved per spec.
    assert modules == "aee,dst", (
        f"FR-45: modules sentinel must be 'aee,dst'; got {modules!r}"
    )
    assert expected_import_path == "same", (
        f"FR-45: expected_import_path sentinel must be 'same'; "
        f"got {expected_import_path!r}"
    )


# ---------------------------------------------------------------------------
# 2. There MUST be exactly one ToolDefinition class — no duplication.
#
# Spec input: class_count="1".
# SRS FR-45: "AEE 和 DST 使用同一 ToolDefinition 類別；無重複定義."
# Walking the source tree under
# ``03-development/src/app/services/aee/`` and
# ``03-development/src/app/core/`` and counting ``class ToolDefinition``
# top-level definitions MUST yield exactly 1 — the canonical AEE
# dataclass. The DST module's ``ToolDefinition`` MUST be a re-import,
# not a second definition.
# ---------------------------------------------------------------------------
def test_fr45_single_tool_definition_class_no_duplication():
    class_count = "1"

    if class_count == "1":
        # Spec fr45-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert _AEE_ToolDefinition is not None, (
            "fr45-ok predicate: ToolDefinition must be importable "
            "from app.services.aee.adapter"
        )

    # GREEN TODO: scanning the AEE + DST module trees MUST report
    # exactly one ``class ToolDefinition`` definition. If GREEN
    # re-defines the dataclass inside ``app.core.dst`` (rather than
    # re-importing it from AEE), this count becomes 2 and the test
    # fails.
    def _count_tool_definition_classes() -> int:
        """Count top-level ``class ToolDefinition`` definitions under
        ``app/services/aee/`` and ``app/core/``.

        Walks the on-disk source tree (not importlib), so a *re-import*
        in ``dst.py`` is NOT counted (only a ``class`` statement is).
        ``app/services/aee/`` owns the canonical definition; ``app/core/``
        (where DST lives) MUST contain zero ``class ToolDefinition``
        statements — any definition here is a duplication per FR-45.
        """
        src_root = Path(__file__).resolve().parents[2] / "src" / "app"
        aee_root = src_root / "services" / "aee"
        core_root = src_root / "core"

        # The canonical owner of ``ToolDefinition`` is AEE; only one
        # file under ``aee_root`` may define ``class ToolDefinition``.
        # Any file under ``core_root`` defining it is a violation
        # (DST must re-import, not redefine).
        count = 0
        for tree_root in (aee_root, core_root):
            for py_file in tree_root.rglob("*.py"):
                try:
                    text = py_file.read_text(encoding="utf-8")
                except OSError:
                    continue
                for raw_line in text.splitlines():
                    stripped = raw_line.lstrip()
                    # Match a top-level ``class ToolDefinition``
                    # statement; reject ``class ToolDefinitionXYZ``
                    # (suffix) by requiring word boundary after the
                    # identifier, and reject docstring / comment
                    # occurrences by requiring the line to start with
                    # ``class`` (after leading whitespace).
                    if stripped.startswith("class ToolDefinition(") or \
                            stripped.startswith("class ToolDefinition:"):
                        count += 1
        return count

    result = _count_tool_definition_classes()

    if class_count == "1":
        # Spec fr45-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert result is not None, (
            "fr45-ok predicate: class count result must not be None"
        )

    expected = int(class_count)
    assert result == expected, (
        f"FR-45: exactly one ``class ToolDefinition`` definition must "
        f"exist under app/services/aee/ + app/core/ (class_count="
        f"{class_count!r}, expected={expected}); found {result} "
        f"definition(s). DST must RE-IMPORT ToolDefinition from AEE, "
        f"not redefine it locally."
    )

    # Sentinel MUST be preserved per spec.
    assert class_count == "1", (
        f"FR-45: class_count sentinel must be '1'; got {class_count!r}"
    )


# ---------------------------------------------------------------------------
# 3. AEE and DST MUST NOT carry a duplicate ToolDefinition class.
#
# Spec input: modules="aee,dst"; expected_class_count="1".
# SRS FR-45: "AEE 和 DST 使用同一 ToolDefinition 類別；無重複定義."
# Negative-constraint variant of case 2: re-importing the AEE
# ``ToolDefinition`` into ``dst.py`` MUST NOT count as a second
# definition. Walking the source tree under both module roots and
# counting ``class ToolDefinition`` top-level statements MUST yield
# exactly 1 across the union — a re-import (``from ... import
# ToolDefinition``) does not increment the count.
# ---------------------------------------------------------------------------
def test_fr45_must_not_duplicate_tool_definition():
    modules = "aee,dst"
    expected_class_count = "1"

    if expected_class_count == "1":
        # Spec fr45-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert _AEE_ToolDefinition is not None, (
            "fr45-ok predicate: ToolDefinition must be importable "
            "from app.services.aee.adapter"
        )

    # GREEN TODO: ``app.core.dst`` MUST NOT contain a local
    # ``class ToolDefinition`` statement. It MUST re-import the
    # dataclass from ``app.services.aee.adapter`` so the dataclass is
    # defined exactly once across both module roots.
    def _count_tool_definition_classes_in_module(module_name: str) -> int:
        """Count top-level ``class ToolDefinition`` definitions in a
        single module, resolved via ``importlib`` then re-read from
        disk (so re-imports do NOT count).
        """
        mod = importlib.import_module(module_name)
        if mod.__file__ is None:  # pragma: no cover — namespace pkgs
            return 0
        try:
            text = Path(mod.__file__).read_text(encoding="utf-8")
        except OSError:
            return 0
        count = 0
        for raw_line in text.splitlines():
            stripped = raw_line.lstrip()
            if stripped.startswith("class ToolDefinition(") or \
                    stripped.startswith("class ToolDefinition:"):
                count += 1
        return count

    aee_count = _count_tool_definition_classes_in_module(
        "app.services.aee.adapter"
    )
    dst_count = _count_tool_definition_classes_in_module("app.core.dst")
    result = aee_count + dst_count

    if expected_class_count == "1":
        # Spec fr45-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert result is not None, (
            "fr45-ok predicate: per-module class count sum must not "
            "be None"
        )

    expected = int(expected_class_count)
    assert aee_count >= 1, (
        f"FR-45: app.services.aee.adapter must contain the canonical "
        f"``class ToolDefinition`` definition (aee_count={aee_count}); "
        f"if the AEE adapter no longer ships it, FR-39/FR-45 contract "
        f"is broken"
    )
    assert dst_count == 0, (
        f"FR-45: app.core.dst MUST NOT define ``class ToolDefinition`` "
        f"locally — it must re-import from AEE per FR-45 "
        f"(negative_constraint; dst_count={dst_count}). "
        f"Found duplicate definition in dst.py."
    )
    assert result == expected, (
        f"FR-45: total ``class ToolDefinition`` definitions across "
        f"{modules!r} must be exactly {expected} "
        f"(expected_class_count={expected_class_count!r}); "
        f"got aee_count={aee_count}, dst_count={dst_count}, "
        f"sum={result}. AEE + DST must share a SINGLE definition."
    )

    # Identity MUST also hold — the re-exported DST reference is the
    # same class object as the AEE definition (case 1 covered this
    # already, but case 3's negative-constraint lens also requires
    # the cross-module identity).
    assert _AEE_ToolDefinition is _DST_ToolDefinition, (
        f"FR-45: AEE and DST ToolDefinition references must be the "
        f"SAME class object across {modules!r}; got "
        f"AEE={_AEE_ToolDefinition!r}, DST={_DST_ToolDefinition!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert modules == "aee,dst", (
        f"FR-45: modules sentinel must be 'aee,dst'; got {modules!r}"
    )
    assert expected_class_count == "1", (
        f"FR-45: expected_class_count sentinel must be '1'; "
        f"got {expected_class_count!r}"
    )

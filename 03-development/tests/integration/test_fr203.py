"""TDD-GREEN tests for FR-203 — Experiment Create via ABTestManager.

Spec source: 02-architecture/TEST_SPEC.md (FR-203)
SRS source : SRS.md FR-203

Acceptance criteria (from SRS FR-203):
    POST /api/v1/experiments — 真正透過 ABTestManager 建實驗
    （traffic_split 驗證、寫 DB、status='active'、回傳 experiment_id）；
    RBAC: experiment:write 通過；payload 含 name/traffic_split/model；
    sum(traffic_split)==1.0；回傳 200；缺欄位/型別錯/role 不符 → 403；
    DB row 已建立且 status='active'.

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr203_create_experiment_returns_200_for_admin
    2. test_fr203_create_experiment_returns_403_for_anon
    3. test_fr203_create_experiment_invalid_split_returns_403

Sub-assertions (per TEST_SPEC):
    fr203-ok      : result == 200    (case 1)
    fr203-rbac    : result == 403    (case 2)
    fr203-invalid : result == 403    (case 3)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api.management import (
    _HTTP_FORBIDDEN,
    _HTTP_OK,
    create_experiment,
)
from app.services.ab_testing import create_experiment_via_manager


def test_fr203_create_experiment_returns_200_for_admin(monkeypatch):
    """[FR-203 case 1] admin role passes RBAC and returns 200."""
    spy = MagicMock(return_value="exp_abc123456789")
    # The api layer does ``from app.services.ab_testing import
    # create_experiment_via_manager`` lazily inside the function, so
    # patch the symbol in its source module (not the api module).
    monkeypatch.setattr("app.services.ab_testing.create_experiment_via_manager", spy)

    result = create_experiment(
        role="admin",
        payload={
            "name": "exp_a",
            "traffic_split": {"variant_a": 0.5, "variant_b": 0.5},
            "model": "gpt-4",
        },
    )
    assert result == _HTTP_OK
    assert spy.call_count == 1


def test_fr203_create_experiment_returns_403_for_anon(monkeypatch):
    """[FR-203 case 2] anonymous role denied at RBAC, no core call."""
    spy = MagicMock()
    monkeypatch.setattr("app.services.ab_testing.create_experiment_via_manager", spy)

    result = create_experiment(role="anonymous", payload={})
    assert result == _HTTP_FORBIDDEN
    assert spy.call_count == 0


def test_fr203_create_experiment_invalid_split_returns_403(monkeypatch):
    """[FR-203 case 3] invalid traffic_split (sum != 1.0) → 403."""
    def _raise_invalid(*_args, **_kwargs):
        raise ValueError("traffic_split must sum to 1.0, got 1.4")

    monkeypatch.setattr("app.services.ab_testing.create_experiment_via_manager", _raise_invalid)

    result = create_experiment(
        role="admin",
        payload={
            "name": "exp_bad",
            "traffic_split": {"variant_a": 0.7, "variant_b": 0.7},
            "model": "gpt-4",
        },
    )
    assert result == _HTTP_FORBIDDEN


# ---------------------------------------------------------------------------
# Unit test on the core function itself — verifies the validation seam
# that the api layer relies on (not in TEST_SPEC but pinned by the
# spec-coverage sub-assertion ``fr203-invalid``).
# ---------------------------------------------------------------------------


def test_fr203_create_experiment_via_manager_rejects_invalid_split():
    """Sum != 1.0 must raise ValueError so the api layer can 403."""
    import pytest

    with pytest.raises(ValueError, match="must sum to 1.0"):
        create_experiment_via_manager(
            name="exp_bad",
            traffic_split={"variant_a": 0.7, "variant_b": 0.7},
            model="gpt-4",
        )


def test_fr203_create_experiment_via_manager_rejects_non_dict():
    """Non-dict traffic_split must raise TypeError."""
    import pytest

    with pytest.raises(TypeError, match="must be dict"):
        create_experiment_via_manager(
            name="exp_bad",
            traffic_split="not-a-dict",  # type: ignore[arg-type]
            model="gpt-4",
        )
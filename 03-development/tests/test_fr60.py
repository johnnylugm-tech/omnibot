from __future__ import annotations
"""TDD-RED: failing tests for FR-60 — 7-role RBAC role definitions with
``ROLE_PERMISSIONS`` matrix; dpo is the ONLY role that holds
``pii:decrypt``; auditor MUST NOT hold ``pii:decrypt``.

Spec source: 02-architecture/TEST_SPEC.md (FR-60)
SRS source : SRS.md FR-60 (Module 12: RBAC 權限管理)

Acceptance criteria (from SRS FR-60):
    7 角色定義：anonymous, customer, agent, editor, admin, auditor, dpo；
    每角色對 knowledge/escalate/audit/experiment/system/pii 資源各有
    不同權限（read/write/delete）；dpo 獨有 pii:decrypt。
    Acceptance: 7 角色 ROLE_PERMISSIONS 完整；dpo 有 pii:decrypt；
    auditor 無 pii:decrypt.

Implementation (SAD.md §4.2 Module: rbac.py, FR-60):
    The ``ROLE_PERMISSIONS`` constant lives in ``app/admin/rbac.py`` and
    maps each of the 7 roles to the per-resource permissions they hold.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-60 (SRS.md line 138) mandates that the ``app/admin/rbac.py`` module
# exports a ``ROLE_PERMISSIONS`` mapping covering the 7 roles:
# ``anonymous``, ``customer``, ``agent``, ``editor``, ``admin``,
# ``auditor``, ``dpo``; and that ``dpo`` is the ONLY role that holds the
# ``pii:decrypt`` permission (auditor explicitly does NOT).
#
# GREEN contract pinned by this spec:
#
#   - ``app.admin.rbac`` MUST export ``ROLE_PERMISSIONS`` — a mapping
#     (dict / Mapping) whose keys enumerate the 7 role names (string
#     equality): ``anonymous``, ``customer``, ``agent``, ``editor``,
#     ``admin``, ``auditor``, ``dpo``.
#
#   - The mapping MUST contain exactly those 7 roles (no extras, no
#     omissions) so the RBAC enforcer can dispatch by role key.
#
#   - The ``dpo`` role entry MUST include the ``"pii"`` resource whose
#     actions list contains ``"decrypt"`` (i.e. ``"pii:decrypt"`` is
#     granted to ``dpo``).
#
#   - The ``auditor`` role entry MUST NOT include ``"pii:decrypt"`` in
#     any shape (neither under a ``"pii"`` resource carrying a
#     ``"decrypt"`` action nor as a top-level ``"pii:decrypt"`` string).
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the ``app.admin.rbac`` module
# does not exist yet, or with AssertionError if the matrix is wrong.
# Either failure is the valid RED signal — GREEN adds the
# implementation.
# ---------------------------------------------------------------------------
from app.admin.rbac import ROLE_PERMISSIONS


# ---------------------------------------------------------------------------
# 1. ``ROLE_PERMISSIONS`` MUST define exactly the 7 mandated roles so
#    the RBAC enforcer can dispatch every incoming principal to a
#    role entry without raising ``KeyError`` (SRS FR-60 acceptance:
#    "7 角色 ROLE_PERMISSIONS 完整").
#
# Spec input: expected_roles="anonymous,customer,agent,editor,admin,auditor,dpo".
# Spec sub-assertion: fr60-ok: result is not None.
# SRS FR-60 acceptance: "7 角色 ROLE_PERMISSIONS 完整".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr60_7_roles_defined():
    expected_roles = "anonymous,customer,agent,editor,admin,auditor,dpo"

    # Defence-in-depth: pin the spec sentinel string so a silent
    # rewrite of the test inputs cannot accidentally relax the
    # assertion to e.g. dropping ``dpo``.
    assert expected_roles == "anonymous,customer,agent,editor,admin,auditor,dpo", (
        "FR-60: expected_roles sentinel must be the full 7-role list per "
        "SRS FR-60 'anonymous, customer, agent, editor, admin, auditor, "
        f"dpo'; got {expected_roles!r}."
    )

    expected_role_set = set(expected_roles.split(","))

    # fr60-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr60-ok predicate: ROLE_PERMISSIONS must not be None so the RBAC "
        "enforcer can dispatch by role key (SRS FR-60 '7 角色 "
        "ROLE_PERMISSIONS 完整')."
    )

    # The mapping MUST expose the role keys as a set so we can
    # compare membership deterministically.
    try:
        actual_role_set = set(ROLE_PERMISSIONS.keys())
    except AttributeError as exc:
        raise AssertionError(
            "FR-60: ROLE_PERMISSIONS must be a mapping with .keys(); the "
            f"RBAC enforcer needs role-keyed dispatch. Got: {exc}."
        ) from exc

    assert actual_role_set == expected_role_set, (
        f"FR-60: ROLE_PERMISSIONS must define exactly the 7 roles per "
        f"SRS FR-60 'anonymous, customer, agent, editor, admin, "
        f"auditor, dpo'; expected {sorted(expected_role_set)!r}, "
        f"got {sorted(actual_role_set)!r}."
    )

    # Defence-in-depth: pin the cardinality so an off-by-one silent
    # rewrite (e.g. 6 or 8 roles) cannot pass.
    assert len(actual_role_set) == 7, (
        f"FR-60: ROLE_PERMISSIONS must define exactly 7 roles per "
        f"SRS FR-60 '7 角色定義'; got {len(actual_role_set)}: "
        f"{sorted(actual_role_set)!r}."
    )


# ---------------------------------------------------------------------------
# 2. The ``dpo`` role MUST hold the ``"pii:decrypt"`` permission
#    because it is the sole role with the legal authority to decrypt
#    PII (SRS FR-60 acceptance: "dpo 有 pii:decrypt"; "dpo 獨有
#    pii:decrypt").
#
# Spec input: role="dpo"; expected_permission="pii:decrypt".
# Spec sub-assertion: fr60-ok: result is not None.
# SRS FR-60 acceptance: "dpo 有 pii:decrypt".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr60_dpo_has_pii_decrypt():
    role = "dpo"
    expected_permission = "pii:decrypt"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "dpo", (
        f"FR-60: role sentinel must be 'dpo' (SRS FR-60 'dpo 獨有 "
        f"pii:decrypt'); got {role!r}."
    )
    assert expected_permission == "pii:decrypt", (
        f"FR-60: expected_permission sentinel must be 'pii:decrypt' "
        f"(SRS FR-60 'dpo 獨有 pii:decrypt'); got {expected_permission!r}."
    )

    # fr60-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr60-ok predicate: ROLE_PERMISSIONS must not be None so the RBAC "
        "enforcer can resolve role permissions (SRS FR-60)."
    )

    # The ``dpo`` role MUST be present in the matrix.
    assert role in ROLE_PERMISSIONS, (
        f"FR-60: ROLE_PERMISSIONS must contain the 'dpo' role per "
        f"SRS FR-60; got roles {sorted(ROLE_PERMISSIONS.keys())!r}."
    )

    dpo_perms = ROLE_PERMISSIONS[role]
    assert dpo_perms is not None, (
        f"FR-60: ROLE_PERMISSIONS['dpo'] must not be None so the RBAC "
        f"enforcer can authorise pii:decrypt; got {dpo_perms!r}."
    )

    # GREEN TODO: the per-role permission payload is EITHER:
    #   (a) a nested resource->actions dict, e.g.
    #       ``{"pii": {"decrypt"}}`` or ``{"pii": ["decrypt"]}``;
    #   (b) a flat iterable / set of ``"resource:action"`` strings,
    #       e.g. ``{"pii:decrypt", "knowledge:read", ...}``.
    # Either encoding MUST let us observe that ``"pii:decrypt"`` is
    # granted to ``dpo``. We accept both encodings.
    has_pii_decrypt = False
    if isinstance(dpo_perms, dict):
        pii_resource = dpo_perms.get("pii")
        if pii_resource is not None:
            # Iterables of action strings; tolerate set / list / tuple /
            # frozenset / dict (dict_keys).
            try:
                actions_iter = pii_resource.values() if isinstance(pii_resource, dict) else pii_resource
                if "decrypt" in actions_iter:
                    has_pii_decrypt = True
            except TypeError:
                # pii_resource is a bare string — not the contract.
                has_pii_decrypt = False
    else:
        # Flat iterable: ``{"pii:decrypt", ...}`` etc.
        try:
            if "pii:decrypt" in dpo_perms:
                has_pii_decrypt = True
        except TypeError:
            # Scalars cannot encode pii:decrypt — fail loudly.
            has_pii_decrypt = False

    assert has_pii_decrypt, (
        f"FR-60: dpo role MUST hold 'pii:decrypt' per SRS FR-60 'dpo 獨有 "
        f"pii:decrypt'; ROLE_PERMISSIONS['dpo'] = {dpo_perms!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "dpo", (
        f"FR-60: role sentinel must remain 'dpo'; got {role!r}."
    )
    assert expected_permission == "pii:decrypt", (
        f"FR-60: expected_permission sentinel must remain 'pii:decrypt'; "
        f"got {expected_permission!r}."
    )


# ---------------------------------------------------------------------------
# 3. The ``auditor`` role MUST NOT hold the ``"pii:decrypt"``
#    permission. The auditor may READ audit logs but MUST NOT decrypt
#    PII; otherwise the privacy boundary is breached (SRS FR-60
#    acceptance: "auditor 無 pii:decrypt"; FR-61 reinforces this with
#    an explicit ``pii:none`` entry and 403 on ``pii:decrypt``).
#
# Spec input: role="auditor"; permission="pii:decrypt";
#            expected_has="false".
# Spec sub-assertion: fr60-ok: result is not None.
# SRS FR-60 acceptance: "auditor 無 pii:decrypt".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr60_auditor_lacks_pii_decrypt():
    role = "auditor"
    permission = "pii:decrypt"
    expected_has = "false"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "auditor", (
        f"FR-60: role sentinel must be 'auditor' (SRS FR-60 'auditor 無 "
        f"pii:decrypt'); got {role!r}."
    )
    assert permission == "pii:decrypt", (
        f"FR-60: permission sentinel must be 'pii:decrypt'; got "
        f"{permission!r}."
    )
    assert expected_has == "false", (
        f"FR-60: expected_has sentinel must be 'false' (auditor MUST NOT "
        f"hold pii:decrypt); got {expected_has!r}."
    )

    # fr60-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr60-ok predicate: ROLE_PERMISSIONS must not be None so the RBAC "
        "enforcer can resolve role permissions (SRS FR-60)."
    )

    # The ``auditor`` role MUST be present in the matrix.
    assert role in ROLE_PERMISSIONS, (
        f"FR-60: ROLE_PERMISSIONS must contain the 'auditor' role per "
        f"SRS FR-60; got roles {sorted(ROLE_PERMISSIONS.keys())!r}."
    )

    auditor_perms = ROLE_PERMISSIONS[role]
    assert auditor_perms is not None, (
        f"FR-60: ROLE_PERMISSIONS['auditor'] must not be None so the RBAC "
        f"enforcer can authorise read-only audit access; got "
        f"{auditor_perms!r}."
    )

    # GREEN TODO: the per-role permission payload follows the same
    # dual-encoding contract as in test_fr60_dpo_has_pii_decrypt.
    # We assert auditor MUST NOT hold ``pii:decrypt`` in EITHER
    # encoding.
    auditor_has_pii_decrypt = False
    if isinstance(auditor_perms, dict):
        pii_resource = auditor_perms.get("pii")
        if pii_resource is not None:
            try:
                actions_iter = pii_resource.values() if isinstance(pii_resource, dict) else pii_resource
                if "decrypt" in actions_iter:
                    auditor_has_pii_decrypt = True
            except TypeError:
                auditor_has_pii_decrypt = False
    else:
        try:
            if "pii:decrypt" in auditor_perms:
                auditor_has_pii_decrypt = True
        except TypeError:
            auditor_has_pii_decrypt = False

    assert not auditor_has_pii_decrypt, (
        f"FR-60: auditor role MUST NOT hold 'pii:decrypt' per SRS FR-60 "
        f"'auditor 無 pii:decrypt'; ROLE_PERMISSIONS['auditor'] = "
        f"{auditor_perms!r}. (privacy boundary breach — dpo is the sole "
        f"role with pii:decrypt.)"
    )

    # Boolean interpretation of the spec sentinel — pin the contract
    # so a silent rewrite of ``expected_has`` cannot drift the
    # assertion.
    assert expected_has.lower() == "false", (
        f"FR-60: expected_has sentinel must lower-case to 'false' so the "
        f"test contract pins auditor's lack of pii:decrypt; got "
        f"{expected_has!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "auditor", (
        f"FR-60: role sentinel must remain 'auditor'; got {role!r}."
    )
    assert permission == "pii:decrypt", (
        f"FR-60: permission sentinel must remain 'pii:decrypt'; got "
        f"{permission!r}."
    )

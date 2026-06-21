from __future__ import annotations
"""TDD-RED: failing tests for FR-61 — 權限矩陣（完整）與 auditor
``pii:decrypt`` 403 拒絕。

Spec source: 02-architecture/TEST_SPEC.md (FR-61)
SRS source : SRS.md line 139 — FR-61 acceptance:
    各角色權限按規格；auditor 嘗試 pii:decrypt 回 403；越界操作
    被拒絕。``Explicit pii:none`` 必須在 ``ROLE_PERMISSIONS`` 中
    顯式定義（不隱含），確保 auditor 嘗試 pii:decrypt 時回傳 403。

Acceptance criteria (SRS FR-61):
    - ``anonymous``=knowledge:read；
    - ``customer``=knowledge:read + escalate:write；
    - ``agent``=knowledge:read + escalate:write；
    - ``editor``=knowledge:read+write + escalate:read + experiment:read；
    - ``admin``=全資源 read+write+delete；
    - ``auditor``=knowledge/escalate/audit/experiment/system:read
      **+ pii:none（無 pii 任何權限）**；
    - ``dpo``=同 auditor + pii:decrypt；
    - **Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義**
      （不隱含），確保 auditor 嘗試 pii:decrypt 時回傳 403。

Implementation (SAD.md §4.2 Module: rbac.py, FR-61):
    The ``ROLE_PERMISSIONS`` constant lives in ``app/admin/rbac.py`` and
    maps each of the 7 roles to a nested ``resource -> frozenset-of-
    actions`` dict. The enforcement entry point is
    ``app.admin.rbac.enforce(role, resource, action)`` which returns an
    HTTP-style status code: ``200`` when the role holds the
    ``resource:action`` grant, ``403`` otherwise (authz denial —
    ``AUTHZ_INSUFFICIENT_ROLE``).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-61 (SRS.md line 139) requires:
#   1. ``ROLE_PERMISSIONS`` is a full 7-role × 6-resource matrix covering
#      every (role, resource) cell (no implicit absences for the 6
#      mandated resources);
#   2. ``admin`` holds ``read``, ``write`` AND ``delete`` on every
#      resource (``knowledge``, ``escalate``, ``audit``, ``experiment``,
#      ``system``, ``pii``);
#   3. ``auditor`` has an EXPLICIT ``pii`` entry whose value is
#      effectively ``none`` (empty frozenset) — the FR-61 spec is
#      explicit that this must NOT be implicit;
#   4. ``enforce(role, resource, action)`` returns ``200`` for granted
#      actions and ``403`` for denied actions so that the
#      ``auditor + pii:decrypt`` request is rejected with HTTP 403
#      ``AUTHZ_INSUFFICIENT_ROLE``.
#
# GREEN contract pinned by this spec:
#
#   - ``app.admin.rbac`` MUST export ``ROLE_PERMISSIONS`` (Mapping)
#     and ``RESOURCES`` (tuple / sequence of 6 resource names).
#
#   - ``app.admin.rbac`` MUST export ``enforce(role: str, resource: str,
#     action: str) -> int`` returning ``200`` when the role holds the
#     ``(resource, action)`` grant and ``403`` when it does not.
#
#   - For every role in ``ROLE_PERMISSIONS`` the inner dict MUST have
#     a key for EVERY resource in ``RESOURCES`` (the ``pii`` key for
#     ``auditor`` MUST be explicit and map to an empty frozenset).
#
#   - The ``admin`` role entry MUST contain ``"read"``, ``"write"``
#     and ``"delete"`` for every resource in ``RESOURCES``.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) if ``enforce`` is missing, or with
# AssertionError if the matrix is incomplete. Either failure is the
# valid RED signal — GREEN adds the enforcement function and tightens
# the matrix to make every assertion hold.
# ---------------------------------------------------------------------------
from app.admin.rbac import RESOURCES, ROLE_PERMISSIONS, enforce


# ---------------------------------------------------------------------------
# 1. The ``auditor`` role MUST be denied ``pii:decrypt`` with HTTP 403
#    (SRS FR-61 acceptance: "auditor 嘗試 pii:decrypt 回 403").
#
# Spec input: role="auditor"; action="pii:decrypt"; expected_status="403".
# Spec sub-assertion: fr61-ok: result is not None.
# SRS FR-61 acceptance: "auditor 嘗試 pii:decrypt 回 403".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr61_auditor_pii_decrypt_returns_403():
    role = "auditor"
    action = "pii:decrypt"
    expected_status = "403"

    # Defence-in-depth: pin the spec sentinel strings so a silent
    # rewrite of the test inputs cannot accidentally relax the
    # assertion to e.g. dropping the resource split or swapping the
    # role.
    assert role == "auditor", (
        f"FR-61: role sentinel must be 'auditor' (SRS FR-61 'auditor "
        f"嘗試 pii:decrypt 回 403'); got {role!r}."
    )
    assert action == "pii:decrypt", (
        f"FR-61: action sentinel must be 'pii:decrypt' (SRS FR-61 "
        f"'auditor 嘗試 pii:decrypt 回 403'); got {action!r}."
    )
    assert expected_status == "403", (
        f"FR-61: expected_status sentinel must be '403' (HTTP 403 "
        f"AUTHZ_INSUFFICIENT_ROLE); got {expected_status!r}."
    )

    # fr61-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr61-ok predicate: ROLE_PERMISSIONS must not be None so the "
        "enforcer can dispatch by role key (SRS FR-61 '7 角色 "
        "ROLE_PERMISSIONS 完整')."
    )

    # Split ``pii:decrypt`` into ``(resource, action)`` halves so the
    # enforcement function can be called with the canonical 3-arg
    # signature ``enforce(role, resource, action)``.
    resource, act = action.split(":", 1)
    assert resource == "pii", (
        f"FR-61: action resource half must be 'pii'; got {resource!r}."
    )
    assert act == "decrypt", (
        f"FR-61: action action half must be 'decrypt'; got {act!r}."
    )

    # GREEN TODO: app.admin.rbac MUST export
    #   ``enforce(role: str, resource: str, action: str) -> int``
    # returning ``200`` when ``action`` is in
    # ``ROLE_PERMISSIONS[role][resource]`` and ``403`` when it is
    # not. For auditor + pii + decrypt the function MUST return 403
    # because the auditor's ``pii`` grant is the empty frozenset
    # (``pii:none`` — see test_fr61_auditor_pii_none_explicit_in_matrix).
    status = enforce(role, resource, act)

    assert status == 403, (
        f"FR-61: enforce('auditor', 'pii', 'decrypt') MUST return 403 "
        f"per SRS FR-61 'auditor 嘗試 pii:decrypt 回 403'; got {status!r}. "
        f"Auditor is read-only and MUST NOT decrypt PII (privacy boundary)."
    )

    # Pin the contract: the returned status is an int equal to 403,
    # not a stringly-typed "403" or a truthy non-zero value.
    assert isinstance(status, int), (
        f"FR-61: enforce() must return an int status code (HTTP-style); "
        f"got {type(status).__name__} = {status!r}."
    )
    assert status == int(expected_status), (
        f"FR-61: enforce() status must equal int('403') = 403; got "
        f"{status!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "auditor", (
        f"FR-61: role sentinel must remain 'auditor'; got {role!r}."
    )
    assert action == "pii:decrypt", (
        f"FR-61: action sentinel must remain 'pii:decrypt'; got "
        f"{action!r}."
    )
    assert expected_status == "403", (
        f"FR-61: expected_status sentinel must remain '403'; got "
        f"{expected_status!r}."
    )


# ---------------------------------------------------------------------------
# 2. The ``ROLE_PERMISSIONS`` matrix MUST be complete: 7 roles, each
#    with all 6 resources (``knowledge``, ``escalate``, ``audit``,
#    ``experiment``, ``system``, ``pii``) explicitly present (SRS
#    FR-61 acceptance: "7 角色 ROLE_PERMISSIONS 完整"; "Explicit
#    pii:none 必須在 ROLE_PERMISSIONS 中顯式定義").
#
# Spec input: roles_count="7";
#            resources="knowledge,escalate,audit,experiment,system,pii".
# Spec sub-assertion: fr61-ok: result is not None.
# SRS FR-61 acceptance: "7 角色 ROLE_PERMISSIONS 完整".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr61_permission_matrix_complete():
    roles_count = 7
    resources = "knowledge,escalate,audit,experiment,system,pii"

    # Defence-in-depth: pin the spec sentinel strings.
    assert roles_count == 7, (
        f"FR-61: roles_count sentinel must be 7 (SRS FR-61 '7 角色 "
        f"ROLE_PERMISSIONS 完整'); got {roles_count!r}."
    )
    assert resources == "knowledge,escalate,audit,experiment,system,pii", (
        f"FR-61: resources sentinel must enumerate the 6 mandated "
        f"resources per SRS FR-61; got {resources!r}."
    )

    expected_role_set = {"anonymous", "customer", "agent", "editor",
                         "admin", "auditor", "dpo"}
    expected_resource_set = set(resources.split(","))

    # fr61-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr61-ok predicate: ROLE_PERMISSIONS must not be None so the "
        "RBAC enforcer can dispatch by role key (SRS FR-61 '7 角色 "
        "ROLE_PERMISSIONS 完整')."
    )

    # The matrix MUST define exactly 7 roles (no more, no less).
    actual_role_set = set(ROLE_PERMISSIONS.keys())
    assert actual_role_set == expected_role_set, (
        f"FR-61: ROLE_PERMISSIONS must define exactly the 7 roles per "
        f"SRS FR-61; expected {sorted(expected_role_set)!r}, got "
        f"{sorted(actual_role_set)!r}."
    )
    assert len(actual_role_set) == roles_count, (
        f"FR-61: ROLE_PERMISSIONS must define exactly {roles_count} "
        f"roles per SRS FR-61 '7 角色 ROLE_PERMISSIONS 完整'; got "
        f"{len(actual_role_set)}: {sorted(actual_role_set)!r}."
    )

    # The ``RESOURCES`` export MUST enumerate the 6 mandated resources
    # — same set as in the spec input.
    actual_resource_set = set(RESOURCES)
    assert actual_resource_set == expected_resource_set, (
        f"FR-61: RESOURCES must enumerate the 6 mandated resources per "
        f"SRS FR-61; expected {sorted(expected_resource_set)!r}, got "
        f"{sorted(actual_resource_set)!r}."
    )
    assert len(actual_resource_set) == 6, (
        f"FR-61: RESOURCES must enumerate exactly 6 resources per "
        f"SRS FR-61; got {len(actual_resource_set)}: "
        f"{sorted(actual_resource_set)!r}."
    )

    # Every role MUST have every resource explicitly present in its
    # inner dict — this is what "Explicit pii:none 必須在
    # ROLE_PERMISSIONS 中顯式定義（不隱含）" means in matrix terms.
    # Implicit absence (missing key) is NOT acceptable for the
    # FR-61 contract.
    for role_name, role_perms in ROLE_PERMISSIONS.items():
        assert isinstance(role_perms, dict), (
            f"FR-61: ROLE_PERMISSIONS[{role_name!r}] must be a dict "
            f"resource->actions so the enforcer can dispatch by "
            f"resource key; got {type(role_perms).__name__}."
        )
        missing_resources = expected_resource_set - set(role_perms.keys())
        assert not missing_resources, (
            f"FR-61: role {role_name!r} is missing explicit entries for "
            f"resources {sorted(missing_resources)!r} (SRS FR-61 "
            f"'Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義 "
            f"（不隱含）')."
        )

    # Sentinels MUST be preserved per spec.
    assert roles_count == 7, (
        f"FR-61: roles_count sentinel must remain 7; got {roles_count!r}."
    )
    assert resources == "knowledge,escalate,audit,experiment,system,pii", (
        f"FR-61: resources sentinel must remain the full 6-resource "
        f"string; got {resources!r}."
    )


# ---------------------------------------------------------------------------
# 3. The ``admin`` role MUST hold ``read``, ``write`` AND ``delete``
#    on every resource (``knowledge``, ``escalate``, ``audit``,
#    ``experiment``, ``system``, ``pii``) — SRS FR-61 acceptance:
#    "admin=全資源 read+write+delete".
#
# Spec input: role="admin"; expected_all_permissions="true".
# Spec sub-assertion: fr61-ok: result is not None.
# SRS FR-61 acceptance: "admin=全資源 read+write+delete".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr61_admin_has_all_resources():
    role = "admin"
    expected_all_permissions = "true"
    required_actions = frozenset({"read", "write", "delete"})

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "admin", (
        f"FR-61: role sentinel must be 'admin' (SRS FR-61 'admin=全"
        f"資源 read+write+delete'); got {role!r}."
    )
    assert expected_all_permissions == "true", (
        f"FR-61: expected_all_permissions sentinel must be 'true' "
        f"(admin MUST have all permissions per SRS FR-61); got "
        f"{expected_all_permissions!r}."
    )

    # fr61-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr61-ok predicate: ROLE_PERMISSIONS must not be None so the "
        "RBAC enforcer can resolve admin's full-grants payload (SRS "
        "FR-61)."
    )

    # The ``admin`` role MUST be present in the matrix.
    assert role in ROLE_PERMISSIONS, (
        f"FR-61: ROLE_PERMISSIONS must contain the 'admin' role per "
        f"SRS FR-61; got roles {sorted(ROLE_PERMISSIONS.keys())!r}."
    )

    admin_perms = ROLE_PERMISSIONS[role]
    assert admin_perms is not None, (
        f"FR-61: ROLE_PERMISSIONS['admin'] must not be None so the "
        f"enforcer can authorise full read+write+delete; got "
        f"{admin_perms!r}."
    )

    # For every resource in the 6-resource surface, admin MUST hold
    # ALL THREE of read, write, delete.
    failing_resources = []
    for resource in RESOURCES:
        assert resource in admin_perms, (
            f"FR-61: admin MUST have an explicit entry for resource "
            f"{resource!r} per SRS FR-61 'admin=全資源 read+write"
            f"+delete'; ROLE_PERMISSIONS['admin'] = {admin_perms!r}."
        )
        resource_actions = admin_perms[resource]
        # Tolerate set / frozenset / list / tuple / dict encodings.
        if isinstance(resource_actions, dict):
            actions_iter = set(resource_actions.keys())
        else:
            try:
                actions_iter = set(resource_actions)
            except TypeError:
                actions_iter = {resource_actions}
        missing = required_actions - actions_iter
        if missing:
            failing_resources.append((resource, sorted(missing)))

    assert not failing_resources, (
        f"FR-61: admin MUST hold read+write+delete on EVERY resource "
        f"per SRS FR-61 'admin=全資源 read+write+delete'; missing "
        f"grants: {failing_resources!r}. ROLE_PERMISSIONS['admin'] = "
        f"{admin_perms!r}."
    )

    # Boolean interpretation of the spec sentinel — pin the contract
    # so a silent rewrite of ``expected_all_permissions`` cannot
    # drift the assertion.
    assert expected_all_permissions.lower() == "true", (
        f"FR-61: expected_all_permissions sentinel must lower-case to "
        f"'true' so the test contract pins admin's full grants; got "
        f"{expected_all_permissions!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "admin", (
        f"FR-61: role sentinel must remain 'admin'; got {role!r}."
    )
    assert expected_all_permissions == "true", (
        f"FR-61: expected_all_permissions sentinel must remain 'true'; "
        f"got {expected_all_permissions!r}."
    )


# ---------------------------------------------------------------------------
# 4. The ``auditor`` role MUST have an EXPLICIT ``pii`` entry in the
#    matrix whose value represents ``pii:none`` (empty grant set) —
#    SRS FR-61 acceptance: "auditor=knowledge/escalate/audit/
#    experiment/system:read + pii:none（無 pii 任何權限）" and
#    "Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義（不隱含）".
#
# Spec input: role="auditor"; pii_permission="pii:none";
#            expected_explicit="true".
# Spec sub-assertion: fr61-ok: result is not None.
# SRS FR-61 acceptance: "Explicit pii:none 必須在 ROLE_PERMISSIONS 中
#    顯式定義（不隱含）".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr61_auditor_pii_none_explicit_in_matrix():
    role = "auditor"
    pii_permission = "pii:none"
    expected_explicit = "true"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "auditor", (
        f"FR-61: role sentinel must be 'auditor' (SRS FR-61 'auditor "
        f"+ pii:none 必須顯式定義'); got {role!r}."
    )
    assert pii_permission == "pii:none", (
        f"FR-61: pii_permission sentinel must be 'pii:none' (SRS "
        f"FR-61 'auditor + pii:none（無 pii 任何權限）'); got "
        f"{pii_permission!r}."
    )
    assert expected_explicit == "true", (
        f"FR-61: expected_explicit sentinel must be 'true' (SRS FR-61 "
        f"'Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義'); got "
        f"{expected_explicit!r}."
    )

    # fr61-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr61-ok predicate: ROLE_PERMISSIONS must not be None so the "
        "RBAC enforcer can resolve auditor's pii:none payload (SRS "
        "FR-61)."
    )

    # The ``auditor`` role MUST be present in the matrix.
    assert role in ROLE_PERMISSIONS, (
        f"FR-61: ROLE_PERMISSIONS must contain the 'auditor' role per "
        f"SRS FR-61; got roles {sorted(ROLE_PERMISSIONS.keys())!r}."
    )

    auditor_perms = ROLE_PERMISSIONS[role]
    assert auditor_perms is not None, (
        f"FR-61: ROLE_PERMISSIONS['auditor'] must not be None so the "
        f"enforcer can authorise read-only audit access; got "
        f"{auditor_perms!r}."
    )

    # The ``pii`` key MUST be EXPLICITLY present in auditor's perms
    # dict — this is the FR-61 "不隱含" (not implicit) contract.
    # An implementation that omits the key (relying on the enforcer
    # to default-KeyError) is NOT acceptable; the matrix must be
    # self-describing.
    assert "pii" in auditor_perms, (
        f"FR-61: ROLE_PERMISSIONS['auditor'] MUST have an explicit "
        f"'pii' key per SRS FR-61 'Explicit pii:none 必須在 "
        f"ROLE_PERMISSIONS 中顯式定義（不隱含）'; got keys "
        f"{sorted(auditor_perms.keys())!r}. Implicit absence is NOT "
        f"acceptable for the FR-61 contract."
    )

    pii_value = auditor_perms["pii"]

    # The ``pii`` value MUST represent ``pii:none`` — i.e. it must
    # contain no actions, in particular NOT ``"decrypt"`` (which
    # would breach the privacy boundary that FR-60 and FR-61 jointly
    # defend). We accept set / frozenset / list / tuple / dict
    # encodings.
    if isinstance(pii_value, dict):
        actions_iter = set(pii_value.keys())
    else:
        try:
            actions_iter = set(pii_value)
        except TypeError:
            # A bare scalar (e.g. None or a single string) cannot
            # represent ``pii:none`` as a grant set — fail loudly.
            actions_iter = {pii_value} if pii_value is not None else set()

    assert "decrypt" not in actions_iter, (
        f"FR-61: auditor's 'pii' value MUST be 'pii:none' (no decrypt) "
        f"per SRS FR-61 'auditor=...+pii:none'; got {pii_value!r} "
        f"which contains 'decrypt' — privacy boundary breach."
    )
    assert len(actions_iter) == 0, (
        f"FR-61: auditor's 'pii' value MUST be 'pii:none' (empty grant "
        f"set) per SRS FR-61 'auditor=...+pii:none（無 pii 任何權限）'; "
        f"got {pii_value!r} which has {len(actions_iter)} action(s)."
    )

    # Boolean interpretation of the spec sentinel — pin the contract
    # so a silent rewrite of ``expected_explicit`` cannot drift the
    # assertion.
    assert expected_explicit.lower() == "true", (
        f"FR-61: expected_explicit sentinel must lower-case to 'true' "
        f"so the test contract pins the explicit-key requirement; got "
        f"{expected_explicit!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "auditor", (
        f"FR-61: role sentinel must remain 'auditor'; got {role!r}."
    )
    assert pii_permission == "pii:none", (
        f"FR-61: pii_permission sentinel must remain 'pii:none'; got "
        f"{pii_permission!r}."
    )
    assert expected_explicit == "true", (
        f"FR-61: expected_explicit sentinel must remain 'true'; got "
        f"{expected_explicit!r}."
    )


# ---------------------------------------------------------------------------
# 5. Negative-constraint variant of test 1: ``auditor`` MUST NOT be
#    able to decrypt PII — the privacy boundary enforced by the
#    ``pii:none`` grant is absolute and any implementation that lets
#    the request through (status 200) is a security regression.
#
# Spec input: role="auditor"; action="pii:decrypt";
#            expected_status="403".
# Spec sub-assertion: fr61-ok: result is not None.
# SRS FR-61 acceptance: "越界操作被拒絕" / "auditor 嘗試 pii:decrypt
#    回 403".
# Test type: negative_constraint (Q8 derivation).
# ---------------------------------------------------------------------------
def test_fr61_must_not_pii_decrypt_for_auditor():
    role = "auditor"
    action = "pii:decrypt"
    expected_status = "403"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "auditor", (
        f"FR-61: role sentinel must be 'auditor' (SRS FR-61 'auditor "
        f"嘗試 pii:decrypt 回 403'); got {role!r}."
    )
    assert action == "pii:decrypt", (
        f"FR-61: action sentinel must be 'pii:decrypt' (SRS FR-61); "
        f"got {action!r}."
    )
    assert expected_status == "403", (
        f"FR-61: expected_status sentinel must be '403' (HTTP 403 "
        f"AUTHZ_INSUFFICIENT_ROLE); got {expected_status!r}."
    )

    # fr61-ok: result is not None.
    assert ROLE_PERMISSIONS is not None, (
        "fr61-ok predicate: ROLE_PERMISSIONS must not be None so the "
        "RBAC enforcer can resolve auditor's pii:none payload (SRS "
        "FR-61)."
    )

    # Cross-check the matrix directly: the auditor's ``pii`` grant
    # must NOT include ``decrypt``. This is the matrix-side
    # assertion that backs the enforcement-side assertion below.
    assert "auditor" in ROLE_PERMISSIONS, (
        f"FR-61: ROLE_PERMISSIONS must contain the 'auditor' role; "
        f"got roles {sorted(ROLE_PERMISSIONS.keys())!r}."
    )
    auditor_pii = ROLE_PERMISSIONS["auditor"].get("pii")
    if isinstance(auditor_pii, dict):
        auditor_pii_actions = set(auditor_pii.keys())
    elif auditor_pii is None:
        auditor_pii_actions = set()
    else:
        try:
            auditor_pii_actions = set(auditor_pii)
        except TypeError:
            auditor_pii_actions = {auditor_pii}
    assert "decrypt" not in auditor_pii_actions, (
        f"FR-61: matrix-side assertion: ROLE_PERMISSIONS['auditor']"
        f"['pii'] MUST NOT contain 'decrypt' (SRS FR-61 'auditor + "
        f"pii:none'); got {auditor_pii!r}. Privacy boundary breach."
    )

    # Enforcement-side assertion: ``enforce('auditor', 'pii',
    # 'decrypt')`` MUST return 403 (and MUST NOT return 200). Any
    # implementation that lets auditor decrypt PII is a security
    # regression and MUST be caught here.
    resource, act = action.split(":", 1)
    assert resource == "pii", (
        f"FR-61: action resource half must be 'pii'; got {resource!r}."
    )
    assert act == "decrypt", (
        f"FR-61: action action half must be 'decrypt'; got {act!r}."
    )

    # GREEN TODO: app.admin.rbac MUST export
    #   ``enforce(role: str, resource: str, action: str) -> int``
    # returning ``200`` for granted actions and ``403`` for denied
    # actions. The negative-constraint contract is: for
    # ``role='auditor'`` and ``resource='pii'`` and
    # ``action='decrypt'`` the function MUST return 403 (NOT 200,
    # NOT None, NOT a truthy non-403 value).
    status = enforce(role, resource, act)

    # MUST NOT decrypt: status MUST NOT indicate allow.
    assert status != 200, (
        f"FR-61: enforce('auditor', 'pii', 'decrypt') MUST NOT return "
        f"200 (auditor MUST NOT decrypt PII — privacy boundary); got "
        f"{status!r}. This is a security regression."
    )
    # MUST return 403 specifically: the canonical HTTP authz denial.
    assert status == 403, (
        f"FR-61: enforce('auditor', 'pii', 'decrypt') MUST return 403 "
        f"per SRS FR-61 'auditor 嘗試 pii:decrypt 回 403'; got "
        f"{status!r}."
    )
    assert isinstance(status, int), (
        f"FR-61: enforce() must return an int status code; got "
        f"{type(status).__name__} = {status!r}."
    )
    assert status == int(expected_status), (
        f"FR-61: enforce() status must equal int('403') = 403; got "
        f"{status!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "auditor", (
        f"FR-61: role sentinel must remain 'auditor'; got {role!r}."
    )
    assert action == "pii:decrypt", (
        f"FR-61: action sentinel must remain 'pii:decrypt'; got "
        f"{action!r}."
    )
    assert expected_status == "403", (
        f"FR-61: expected_status sentinel must remain '403'; got "
        f"{expected_status!r}."
    )

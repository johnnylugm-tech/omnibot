"""TDD-RED: failing tests for FR-50 — Template System (rule_default / rag_default / escalate).

Spec source: 02-architecture/TEST_SPEC.md (FR-50)
SRS source : SRS.md FR-50 (Module 9: Response Generator)

Acceptance criteria (from SRS FR-50):
    Template System：ResponseTemplate（name, platform, emotion_tone, template）；
    預設模板：rule_default（{answer}）、rag_default
    （附「📌 此回覆根據相關知識庫內容生成」）、escalate（附案件編號）。
    三個預設模板存在且格式正確；variable interpolation 正確。
    Implementation function: ``ResponseGenerator.DEFAULT_TEMPLATES``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-50 mandates ``ResponseGenerator.DEFAULT_TEMPLATES`` (SRS FR-50
# implementation_functions). The canonical module is
# ``app.core.response_generator`` per SAD.md (Module: response_generator.py)
# and SRS.md FR-50's implementation_functions list.
#
# GREEN contract pinned by this spec:
#
#   - ``ResponseGenerator`` (in ``app/core/response_generator.py``) MUST
#     expose a class-level ``DEFAULT_TEMPLATES`` mapping keyed by template
#     name. The three required keys per SRS FR-50 are ``rule_default``,
#     ``rag_default`` and ``escalate``. Each entry MUST be a
#     ``ResponseTemplate`` (or equivalent dataclass / dict) carrying at
#     minimum the ``template`` field used for ``str.format(**vars)``
#     interpolation.
#
#   - ``rule_default`` template MUST contain the literal ``{answer}``
#     placeholder (SRS: "rule_default（{answer}）").
#
#   - ``rag_default`` template MUST include the knowledge-base suffix
#     「📌 此回覆根據相關知識庫內容生成」 — i.e. the substring "知識庫"
#     (TEST_SPEC expected_suffix="知識庫") so QA can grep the suffix
#     without depending on the emoji literal.
#
#   - ``escalate`` template MUST contain a ``{case_number}`` placeholder
#     so each escalation reply can render the assigned case ID.
#
#   - A variable interpolation helper (``ResponseGenerator.render``
#     / ``ResponseGenerator.interpolate`` / a module-level ``render``
#     function) MUST substitute ``{var}`` placeholders using
#     ``str.format(**vars)`` (or the ``string.Template.safe_substitute``
#     equivalent) and return a non-None string.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.core.response_generator`` does not yet export ``ResponseGenerator``.
# That is the valid RED signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.core.response_generator import (
    ResponseGenerator,
)


# ---------------------------------------------------------------------------
# 1. ``rule_default`` template MUST exist in ``DEFAULT_TEMPLATES`` and MUST
#    contain the ``{answer}`` placeholder so the rule-tier answer can be
#    rendered verbatim.
#
# Spec input: template_name="rule_default"; expected_var="{answer}".
# Spec sub-assertion: fr50-ok: result is not None.
# SRS FR-50 acceptance: "rule_default（{answer}）".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr50_rule_default_template_exists():
    template_name = "rule_default"
    expected_var = "{answer}"

    # Spec fr50-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c`
    # block whose trigger value matches TEST_SPEC case 1's input.
    if template_name == "rule_default":
        # GREEN TODO: ``ResponseGenerator.DEFAULT_TEMPLATES`` MUST
        # contain a ``"rule_default"`` entry whose ``template`` field
        # is a non-None string containing the literal ``"{answer}"``
        # placeholder. The rendered template MUST also evaluate to
        # a non-None result (the fr50-ok sub-assertion).
        templates = ResponseGenerator.DEFAULT_TEMPLATES
        assert templates is not None, (
            "fr50-ok predicate: ResponseGenerator.DEFAULT_TEMPLATES "
            "must be a non-None mapping of template-name -> template"
        )
        assert template_name in templates, (
            f"FR-50: ResponseGenerator.DEFAULT_TEMPLATES must contain "
            f"a {template_name!r} entry per SRS '預設模板：rule_default'"
        )
        rule_template = templates[template_name]
        # Accept dataclass / dict / str uniformly.
        template_body = getattr(rule_template, "template", rule_template)
        assert template_body is not None, (
            "fr50-ok predicate: rule_default template body must be non-None"
        )
        assert expected_var in template_body, (
            f"FR-50: rule_default template must contain the literal "
            f"{expected_var!r} placeholder; got {template_body!r}. "
            f"SRS FR-50 mandates 'rule_default（{expected_var}）'."
        )

    # Sentinels MUST be preserved per spec.
    assert template_name == "rule_default", (
        f"FR-50: template_name sentinel must be 'rule_default'; "
        f"got {template_name!r}"
    )
    assert expected_var == "{answer}", (
        f"FR-50: expected_var sentinel must be '{{answer}}'; "
        f"got {expected_var!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``rag_default`` template MUST contain the knowledge-base suffix
#    「📌 此回覆根據相關知識庫內容生成」 (TEST_SPEC expected_suffix="知識庫").
#
# Spec input: template_name="rag_default"; expected_suffix="知識庫".
# SRS FR-50 acceptance: "rag_default（附「📌 此回覆根據相關知識庫內容生成」）".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr50_rag_default_has_knowledge_suffix():
    template_name = "rag_default"
    expected_suffix = "知識庫"

    templates = ResponseGenerator.DEFAULT_TEMPLATES
    assert template_name in templates, (
        f"FR-50: ResponseGenerator.DEFAULT_TEMPLATES must contain a "
        f"{template_name!r} entry per SRS '預設模板：rag_default'"
    )
    rag_template = templates[template_name]
    template_body = getattr(rag_template, "template", rag_template)
    assert template_body is not None, (
        f"FR-50: {template_name} template body must be non-None"
    )
    assert expected_suffix in template_body, (
        f"FR-50: {template_name} template must contain the "
        f"{expected_suffix!r} suffix; got {template_body!r}. "
        f"SRS FR-50 mandates the suffix "
        f"'📌 此回覆根據相關知識庫內容生成' for the RAG tier so users "
        f"are explicitly told the answer is grounded in the knowledge base."
    )

    # Sentinels MUST be preserved per spec.
    assert template_name == "rag_default", (
        f"FR-50: template_name sentinel must be 'rag_default'; "
        f"got {template_name!r}"
    )
    assert expected_suffix == "知識庫", (
        f"FR-50: expected_suffix sentinel must be '知識庫'; "
        f"got {expected_suffix!r}"
    )


# ---------------------------------------------------------------------------
# 3. ``escalate`` template MUST contain a ``{case_number}`` placeholder
#    so each escalation reply can render the assigned case ID.
#
# Spec input: template_name="escalate"; expected_var="case_number".
# SRS FR-50 acceptance: "escalate（附案件編號）".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr50_escalate_template_has_case_number():
    template_name = "escalate"
    expected_var = "case_number"

    templates = ResponseGenerator.DEFAULT_TEMPLATES
    assert template_name in templates, (
        f"FR-50: ResponseGenerator.DEFAULT_TEMPLATES must contain a "
        f"{template_name!r} entry per SRS '預設模板：escalate'"
    )
    escalate_template = templates[template_name]
    template_body = getattr(escalate_template, "template", escalate_template)
    assert template_body is not None, (
        f"FR-50: {template_name} template body must be non-None"
    )
    # The TEST_SPEC pins `expected_var="case_number"`; accept either
    # ``"{case_number}"`` (str.format) or ``"$case_number"`` (string.Template).
    placeholders = ("{case_number}", "$case_number")
    assert any(p in template_body for p in placeholders), (
        f"FR-50: {template_name} template must contain a case_number "
        f"placeholder (one of {placeholders!r}); got {template_body!r}. "
        f"SRS FR-50 mandates 'escalate（附案件編號）' so each escalation "
        f"reply surfaces the assigned case ID."
    )
    # Bare token check — protects against typos like "{case-num}".
    assert expected_var in template_body, (
        f"FR-50: {template_name} template must mention the literal "
        f"{expected_var!r} token; got {template_body!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert template_name == "escalate", (
        f"FR-50: template_name sentinel must be 'escalate'; "
        f"got {template_name!r}"
    )
    assert expected_var == "case_number", (
        f"FR-50: expected_var sentinel must be 'case_number'; "
        f"got {expected_var!r}"
    )


# ---------------------------------------------------------------------------
# 4. Variable interpolation MUST substitute ``{var}`` placeholders with
#    the supplied values and return a non-None string.
#
# Spec input: template="{answer}"; vars='{"answer":"hello"}'; expected="hello".
# SRS FR-50 acceptance: "variable interpolation 正確".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr50_variable_interpolation_correct():
    template = "{answer}"
    vars_json = '{"answer":"hello"}'
    expected = "hello"

    # Spec fr50-ok predicate applies_to case 1. The interpolation helper
    # is the same render path used by the rule_default template, so the
    # non-None sub-assertion is anchored here too.
    if template == "{answer}":
        # GREEN TODO: ``ResponseGenerator.render(template, **vars)`` (or
        # equivalent helper) MUST return a non-None string with
        # ``{answer}`` substituted by the supplied value.
        import json as _json

        vars_dict = _json.loads(vars_json)
        rendered = ResponseGenerator.render(template, **vars_dict)
        assert rendered is not None, (
            "fr50-ok predicate: ResponseGenerator.render must return a "
            "non-None string for valid template + vars inputs"
        )

    import json as _json

    vars_dict = _json.loads(vars_json)
    rendered = ResponseGenerator.render(template, **vars_dict)
    assert rendered == expected, (
        f"FR-50: variable interpolation must replace {{answer}} with "
        f"the supplied value; expected {expected!r}, got {rendered!r}. "
        f"SRS FR-50 mandates 'variable interpolation 正確' for "
        f"ResponseGenerator templates."
    )

    # Sentinels MUST be preserved per spec.
    assert template == "{answer}", (
        f"FR-50: template sentinel must be '{{answer}}'; "
        f"got {template!r}"
    )
    assert vars_json == '{"answer":"hello"}', (
        f"FR-50: vars_json sentinel must be '{{\"answer\":\"hello\"}}'; "
        f"got {vars_json!r}"
    )
    assert expected == "hello", (
        f"FR-50: expected sentinel must be 'hello'; got {expected!r}"
    )

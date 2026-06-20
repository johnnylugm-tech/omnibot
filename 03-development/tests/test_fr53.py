"""TDD-RED: failing tests for FR-53 — Platform Format Adapter (各平台訊息長度限制).

Spec source: 02-architecture/TEST_SPEC.md (FR-53)
SRS source : SRS.md FR-53 (Module 9: Response Generator)

Acceptance criteria (from SRS FR-53):
    Platform Format Adapter：各平台訊息限制
    - Telegram 4096 字元 / HTML MarkdownV2
    - LINE 5000 字元 / Quick Reply
    - Messenger 2000 字元 / 截斷+link
    - WhatsApp 4096 字元
    - Web 無限制 / 完整 Markdown
    - Agent 無限制 / 純 JSON
    各平台輸出格式符合限制；長訊息正確截斷或分段。
    Implementation function: ``ResponseGenerator.format_for_platform``.

Per-platform character-limit table (SPEC.md §Platform Format Adapter line 2887):

    | 平台     | 最大字元 | Markdown | Quick Reply | 特殊處理         |
    |----------|---------|----------|-------------|------------------|
    | Telegram | 4096    | 有限     | Inline Kb   | escape HTML      |
    | LINE     | 5000    | 無       | Quick Reply | 長訊息自動分段   |
    | Messenger| 2000    | 無       | Buttons     | 長訊息截斷 + link |
    | WhatsApp | 4096    | 有限     | Interactive | URL preview      |
    | Web      | 無限制  | 完整     | 無          | —                |
    | Agent    | 無限制  | 無(純JSON)| 無         | 結構化回傳       |

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-53 mandates ``ResponseGenerator.format_for_platform`` (SRS FR-53
# implementation_functions: "platform format adapters"; SPEC.md places the
# platform-format layer inside the Response Generator module, line 2883).
# The canonical module is ``app.core.response_generator`` per SAD.md
# (Module: response_generator.py) — same module that already exports
# ``ResponseGenerator`` via FR-50/51/52's GREEN commits.
#
# GREEN contract pinned by this spec:
#
#   - ``ResponseGenerator.format_for_platform(platform: str, content: str)
#     -> str`` MUST be a method on ``ResponseGenerator``. It receives the
#     target platform identifier and the raw reply body, and returns a
#     string formatted according to the platform's contract below.
#
#   - For ``platform == "telegram"``: returned string length MUST NOT
#     exceed 4096 characters (TEST_SPEC expected_len="4096"). Excess
#     content is truncated.
#
#   - For ``platform == "line"``: returned string length MUST NOT
#     exceed 5000 characters (TEST_SPEC expected_len="5000").
#
#   - For ``platform == "messenger"``: returned string length MUST NOT
#     exceed 2000 characters (TEST_SPEC expected_len="2000"). Excess
#     content is truncated; a link to the full message MUST be appended
#     so the user can read the rest elsewhere (per SPEC.md "特殊處理"
#     column: "長訊息截斷 + link").
#
#   - For ``platform == "agent"``: returned value MUST be a pure JSON
#     string (TEST_SPEC expected_format="json"). Specifically, calling
#     ``json.loads(result)`` MUST succeed and yield a dict containing the
#     reply content (no Markdown / HTML / template strings leaking
#     through).
#
#   - For ``platform == "web"``: returned string MUST equal the input
#     content byte-for-byte (TEST_SPEC expected_truncated="false" on a
#     100 000-char input); Web has no character limit and supports full
#     Markdown, so the adapter is a pass-through.
#
# These imports are unguarded on purpose. ``ResponseGenerator`` is
# already exported by FR-50's GREEN commit, but the
# ``format_for_platform`` method does not yet exist on it, so the five
# tests below will fail with AttributeError on the first call. That is the
# valid RED signal — GREEN adds the method body.
# ---------------------------------------------------------------------------
from app.core.response_generator import (
    ResponseGenerator,
)


# ---------------------------------------------------------------------------
# 1. ``platform="telegram"`` MUST truncate the message body so the returned
#    string length does NOT exceed Telegram's 4096-character limit —
#    Telegram rejects (or silently drops) any outgoing message longer
#    than 4096 chars.
#
# Spec input: platform="telegram"; content_len="5000"; expected_len="4096".
# Spec sub-assertion: fr53-ok: result is not None.
# SRS FR-53 acceptance: "Telegram 4096 字元".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr53_telegram_4096_char_limit():
    platform = "telegram"
    content_len = 5000  # intentionally over Telegram's 4096 limit
    expected_len = 4096

    if platform == "telegram":
        # 5000 'A' characters — long enough to exceed any sane limit.
        long_content = "A" * content_len
        # GREEN TODO: ``ResponseGenerator.format_for_platform(platform, content)``
        # MUST return a string of length <= 4096 for ``platform == "telegram"``.
        # Excess characters are truncated; the spec test feeds a 5000-char
        # input and pins ``expected_len=4096`` as the post-format length.
        result = ResponseGenerator.format_for_platform(
            platform=platform,
            content=long_content,
        )
        assert result is not None, (
            "fr53-ok predicate: ResponseGenerator.format_for_platform must "
            "return a non-None string for platform='telegram'"
        )
        assert len(result) == expected_len, (
            f"FR-53: format_for_platform(telegram=...) must truncate the "
            f"reply body to exactly {expected_len} characters per "
            f"TEST_SPEC.md case 1; got len={len(result)} for an input of "
            f"length {content_len}. SRS FR-53 mandates 'Telegram 4096 字元'."
        )
        # Defence-in-depth: result MUST be a string (not bytes), and the
        # body MUST still be a truncation of the original — not an empty
        # or replacement string.
        assert isinstance(result, str), (
            f"FR-53: format_for_platform must return a str, got "
            f"{type(result).__name__}"
        )
        assert len(result) > 0, (
            "FR-53: format_for_platform must NOT return an empty string "
            "for platform='telegram' — Telegram's 4096 limit is generous "
            "and a 5000-char input must still yield a non-empty truncation."
        )

    # Sentinels MUST be preserved per spec.
    assert platform == "telegram", (
        f"FR-53: platform sentinel must be 'telegram'; got {platform!r}"
    )
    assert content_len == 5000, (
        f"FR-53: content_len sentinel must be '5000'; got {content_len!r}"
    )
    assert expected_len == 4096, (
        f"FR-53: expected_len sentinel must be '4096'; got {expected_len!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``platform="line"`` MUST truncate the message body so the returned
#    string length does NOT exceed LINE's 5000-character limit.
#
# Spec input: platform="line"; content_len="6000"; expected_len="5000".
# Spec sub-assertion: fr53-ok: result is not None.
# SRS FR-53 acceptance: "LINE 5000 字元".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr53_line_5000_char_limit():
    platform = "line"
    content_len = 6000  # intentionally over LINE's 5000 limit
    expected_len = 5000

    if platform == "line":
        long_content = "B" * content_len
        # GREEN TODO: ``ResponseGenerator.format_for_platform(platform, content)``
        # MUST return a string of length <= 5000 for ``platform == "line"``.
        # LINE's documented character limit is 5000 (SPEC.md §Platform Format
        # Adapter), and the spec test pins ``expected_len=5000`` as the
        # post-format length on a 6000-char input.
        result = ResponseGenerator.format_for_platform(
            platform=platform,
            content=long_content,
        )
        assert result is not None, (
            "fr53-ok predicate: ResponseGenerator.format_for_platform must "
            "return a non-None string for platform='line'"
        )
        assert len(result) == expected_len, (
            f"FR-53: format_for_platform(line=...) must truncate the reply "
            f"body to exactly {expected_len} characters per TEST_SPEC.md "
            f"case 2; got len={len(result)} for an input of length "
            f"{content_len}. SRS FR-53 mandates 'LINE 5000 字元'."
        )
        # Hard upper bound (defence-in-depth): even if the spec's
        # ``expected_len`` pin were relaxed, the contract is "MUST NOT
        # exceed 5000".
        assert len(result) <= 5000, (
            f"FR-53: format_for_platform(line=...) must NOT exceed "
            f"LINE's 5000-char limit; got len={len(result)}"
        )
        assert isinstance(result, str), (
            f"FR-53: format_for_platform must return a str, got "
            f"{type(result).__name__}"
        )

    # Sentinels MUST be preserved per spec.
    assert platform == "line", (
        f"FR-53: platform sentinel must be 'line'; got {platform!r}"
    )
    assert content_len == 6000, (
        f"FR-53: content_len sentinel must be '6000'; got {content_len!r}"
    )
    assert expected_len == 5000, (
        f"FR-53: expected_len sentinel must be '5000'; got {expected_len!r}"
    )


# ---------------------------------------------------------------------------
# 3. ``platform="messenger"`` MUST truncate the message body so the returned
#    string length does NOT exceed Messenger's 2000-character limit. Per
#    SPEC.md "特殊處理" column: "長訊息截斷 + link" — excess content is
#    truncated and a link to the full message MUST be appended.
#
# Spec input: platform="messenger"; content_len="3000"; expected_len="2000".
# Spec sub-assertion: fr53-ok: result is not None.
# SRS FR-53 acceptance: "Messenger 2000 字元/截斷+link".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr53_messenger_2000_char_truncation():
    platform = "messenger"
    content_len = 3000  # intentionally over Messenger's 2000 limit
    expected_len = 2000

    if platform == "messenger":
        long_content = "C" * content_len
        # GREEN TODO: ``ResponseGenerator.format_for_platform(platform, content)``
        # MUST return a string of length <= 2000 for ``platform == "messenger"``.
        # Messenger's documented character limit is 2000 (SPEC.md §Platform
        # Format Adapter), and the spec test pins ``expected_len=2000`` as
        # the post-format length on a 3000-char input. The spec-derived
        # upper bound is non-negotiable: the test uses 3000 'C' characters
        # which trivially exceeds the limit, so the function MUST truncate.
        result = ResponseGenerator.format_for_platform(
            platform=platform,
            content=long_content,
        )
        assert result is not None, (
            "fr53-ok predicate: ResponseGenerator.format_for_platform must "
            "return a non-None string for platform='messenger'"
        )
        assert len(result) == expected_len, (
            f"FR-53: format_for_platform(messenger=...) must truncate the "
            f"reply body to exactly {expected_len} characters per "
            f"TEST_SPEC.md case 3; got len={len(result)} for an input of "
            f"length {content_len}. SRS FR-53 mandates "
            f"'Messenger 2000 字元/截斷+link'."
        )
        # Hard upper bound (defence-in-depth).
        assert len(result) <= 2000, (
            f"FR-53: format_for_platform(messenger=...) must NOT exceed "
            f"Messenger's 2000-char limit; got len={len(result)}"
        )
        assert isinstance(result, str), (
            f"FR-53: format_for_platform must return a str, got "
            f"{type(result).__name__}"
        )

    # Sentinels MUST be preserved per spec.
    assert platform == "messenger", (
        f"FR-53: platform sentinel must be 'messenger'; got {platform!r}"
    )
    assert content_len == 3000, (
        f"FR-53: content_len sentinel must be '3000'; got {content_len!r}"
    )
    assert expected_len == 2000, (
        f"FR-53: expected_len sentinel must be '2000'; got {expected_len!r}"
    )


# ---------------------------------------------------------------------------
# 4. ``platform="agent"`` MUST wrap the reply in a pure-JSON envelope —
#    the A2A / M2M Agent channel expects structured output, NOT a
#    human-facing reply template. Spec input: platform="agent";
#    expected_format="json".
#
# Spec input: platform="agent"; expected_format="json".
# Spec sub-assertion: fr53-ok: result is not None.
# SRS FR-53 acceptance: "Agent 無限制/純 JSON".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr53_agent_pure_json_format():
    platform = "agent"
    expected_format = "json"

    if platform == "agent":
        content = "您好，這裡是客服中心。"
        # GREEN TODO: ``ResponseGenerator.format_for_platform(platform, content)``
        # MUST return a pure JSON string for ``platform == "agent"``.
        # Concretely: ``json.loads(result)`` MUST succeed without raising
        # ``json.JSONDecodeError``, and the parsed object MUST be a dict
        # containing the reply ``content`` field. Agent channels (A2A /
        # M2M) parse the response as JSON-RPC; any non-JSON output
        # (Markdown, template placeholder leakage, leading text) would
        # break the consumer. SPEC.md §Platform Format Adapter pins this
        # as "Agent (A2A) — 無限制 / 無 (純 JSON) / 結構化回傳".
        result = ResponseGenerator.format_for_platform(
            platform=platform,
            content=content,
        )
        assert result is not None, (
            "fr53-ok predicate: ResponseGenerator.format_for_platform must "
            "return a non-None string for platform='agent'"
        )
        assert expected_format == "json", (
            f"FR-53: expected_format sentinel must be 'json'; got "
            f"{expected_format!r}"
        )
        # The returned string MUST be parseable as JSON. If GREEN returns
        # a Markdown reply or a template-with-placeholder, this parse
        # raises ``json.JSONDecodeError`` and the test fails for the
        # right reason.
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"FR-53: format_for_platform(agent=...) must return a pure "
                f"JSON string per TEST_SPEC.md case 4 (expected_format="
                f"'json'); got {result!r}, which is not valid JSON: {exc}. "
                f"SRS FR-53 mandates 'Agent 無限制/純 JSON'."
            )
        # The parsed JSON MUST be a dict — a JSON scalar (string / number
        # / list) would not satisfy the "structured return" contract.
        assert isinstance(parsed, dict), (
            f"FR-53: format_for_platform(agent=...) must return a JSON "
            f"object (dict), got parsed type {type(parsed).__name__} "
            f"with value {parsed!r}"
        )
        # The reply content MUST be carried inside the JSON envelope.
        assert "content" in parsed, (
            f"FR-53: format_for_platform(agent=...) must embed the reply "
            f"under a 'content' key in the JSON envelope; parsed={parsed!r}"
        )
        assert parsed["content"] == content, (
            f"FR-53: format_for_platform(agent=...) must carry the original "
            f"reply content unchanged in the JSON envelope; "
            f"expected content={content!r}, got parsed['content']="
            f"{parsed.get('content')!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert platform == "agent", (
        f"FR-53: platform sentinel must be 'agent'; got {platform!r}"
    )
    assert expected_format == "json", (
        f"FR-53: expected_format sentinel must be 'json'; got "
        f"{expected_format!r}"
    )


# ---------------------------------------------------------------------------
# 5. ``platform="web"`` MUST NOT truncate the message body — Web has no
#    character limit and supports full Markdown. A 100 000-character input
#    MUST be returned unchanged. Spec input: platform="web";
#    content_len="100000"; expected_truncated="false".
#
# Spec input: platform="web"; content_len="100000"; expected_truncated="false".
# Spec sub-assertion: fr53-ok: result is not None.
# SRS FR-53 acceptance: "Web 無限制/完整 Markdown".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr53_web_no_char_limit_full_markdown():
    platform = "web"
    content_len = 100000  # massive — Web has no limit, must pass through
    expected_truncated = "false"

    if platform == "web":
        # Embed a Markdown construct inside the body so we can also assert
        # the adapter does NOT mangle Markdown for Web (e.g. by escaping
        # brackets). Web is the only platform that supports full Markdown
        # per SPEC.md §Platform Format Adapter ("Web — 無限制 / 完整
        # Markdown / 無 / —").
        markdown_content = (
            "# Title\n\n"
            "Some **bold** and *italic* text with [a link](https://example.com).\n"
            + ("D" * (content_len - 80))
        )
        original_len = len(markdown_content)
        # GREEN TODO: ``ResponseGenerator.format_for_platform(platform, content)``
        # MUST return the input content unchanged for ``platform == "web"``.
        # No truncation, no Markdown escaping, no template wrapping.
        # TEST_SPEC.md case 5 pins ``expected_truncated="false"`` on a
        # 100 000-char input — that is the spec's way of saying "Web has
        # no character limit; the adapter is a pass-through".
        result = ResponseGenerator.format_for_platform(
            platform=platform,
            content=markdown_content,
        )
        assert result is not None, (
            "fr53-ok predicate: ResponseGenerator.format_for_platform must "
            "return a non-None string for platform='web'"
        )
        # Expected_truncated="false" — reify to boolean for the assertion.
        if expected_truncated == "false":
            # Hard pass-through contract: result length MUST equal the
            # input length, byte-for-byte. A green implementation that
            # truncates "just in case" or strips trailing whitespace
            # would fail this assertion.
            assert len(result) == original_len, (
                f"FR-53: format_for_platform(web=...) must NOT truncate "
                f"the reply body — Web has no character limit. "
                f"expected_truncated='false' per TEST_SPEC.md case 5; "
                f"got len={len(result)} for an input of length "
                f"{original_len}. SRS FR-53 mandates 'Web 無限制/完整 "
                f"Markdown'."
            )
            # And the content MUST be returned unchanged (Markdown must
            # survive the adapter intact).
            assert result == markdown_content, (
                f"FR-53: format_for_platform(web=...) must return the "
                f"Markdown reply byte-for-byte; expected_truncated='false' "
                f"per TEST_SPEC.md case 5. First 80 chars of expected: "
                f"{markdown_content[:80]!r}; first 80 chars of actual: "
                f"{result[:80]!r}. SRS FR-53 mandates 'Web 無限制/完整 "
                f"Markdown'."
            )

    # Sentinels MUST be preserved per spec.
    assert platform == "web", (
        f"FR-53: platform sentinel must be 'web'; got {platform!r}"
    )
    assert content_len == 100000, (
        f"FR-53: content_len sentinel must be '100000'; got {content_len!r}"
    )
    assert expected_truncated == "false", (
        f"FR-53: expected_truncated sentinel must be 'false'; got "
        f"{expected_truncated!r}"
    )

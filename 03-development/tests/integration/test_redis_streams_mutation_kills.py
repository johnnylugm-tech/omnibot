"""Mutation-killing tests for app.infra.redis_streams.

Targeted field-level assertions to kill mutmut survivors from
`redis_streams` (initial kill rate 50.7%; need 70%).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.infra.redis_streams import (  # noqa: E402
    BusyGroupError,
    Message,
    ParsedMessage,
    _FR80_KNOWN_FIELDS,
    _next_stream_id,
)


def test_next_stream_id_basic_increment() -> None:
    """Mutant on ``int(seq) + 1`` → ``- 1`` or other arithmetic — would
    produce a wrong id. Assert the canonical next id for the standard
    Redis stream format.
    """
    assert _next_stream_id("1000-5") == "1000-6"
    assert _next_stream_id("1000-0") == "1000-1"


def test_next_stream_id_malformed_returned_unchanged() -> None:
    """Mutant that returns the stream_id unchanged for a malformed
    id (e.g. no ``-``) is the **correct** behavior. We assert the
    defensive return is preserved. A mutant that changes the return
    would fail this.
    """
    assert _next_stream_id("not-a-valid-id") == "not-a-valid-id"
    # Pure no-dash: no parsing.
    assert _next_stream_id("justtext") == "justtext"


def test_next_stream_id_non_integer_seq_returned_unchanged() -> None:
    """Mutant that does ``int(seq)`` without try/except would crash on
    non-numeric seq. Assert that ``"a-xyz"`` returns unchanged.
    """
    assert _next_stream_id("1000-abc") == "1000-abc"


def test_fr80_known_fields_set_is_exact() -> None:
    """Mutant that adds, removes, or renames a known field is caught
    by inspecting the frozenset directly.
    """
    assert _FR80_KNOWN_FIELDS == frozenset({
        "event_type", "user_id", "conversation_id", "payload"
    })


def test_busygroup_error_is_exception() -> None:
    """Mutant on the ``BusyGroupError`` base class — must remain an
    ``Exception`` subclass for the try/except in ``ensure_group`` to
    catch it.
    """
    assert issubclass(BusyGroupError, Exception)


def test_message_dataclass_field_set() -> None:
    """Mutant on ``Message`` dataclass fields — assert the field set
    is exactly ``{message_id, fields}``.
    """
    fields = {f.name for f in Message.__dataclass_fields__.values()}
    assert fields == {"message_id", "fields"}


def test_parsed_message_dataclass_field_set() -> None:
    """Mutant on ``ParsedMessage`` dataclass fields — assert the field
    set is exactly ``{message_id, known}``.
    """
    fields = {f.name for f in ParsedMessage.__dataclass_fields__.values()}
    assert fields == {"message_id", "known"}

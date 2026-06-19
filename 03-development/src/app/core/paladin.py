"""[FR-10] PALADIN L1 — InputSanitizer (NFKC + homoglyph + control-char).

SRS FR-10: "PALADIN L1 — InputSanitizer：NFKC 正規化 + homoglyph 替換
(Cyrillic/Greek → ASCII) + 控制字元移除；延遲 < 2ms p95."

Pipeline:
    1. ``unicodedata.normalize('NFKC', text)`` — folds fullwidth and
       compatibility forms into their canonical ASCII equivalents.
    2. ``str.translate()`` — Cyrillic / Greek homoglyphs are mapped to
       their ASCII counterpart (U+0422 → 'T', U+0391 → 'A', …); C0
       (U+0000..U+001F) and C1 (U+007F..U+009F) control characters are
       deleted so they cannot smuggle past regex-based downstream
       filters. Both maps are merged into a single pre-computed
       translation table.

Citations:
    - SRS.md FR-10 (PALADIN L1 InputSanitizer acceptance criteria)
    - 02-architecture/TEST_SPEC.md FR-10 (case 1: Cyrillic homoglyph;
      case 2: Greek homoglyph; case 3: NFKC round-trip; case 4: control
      char strip; case 5: p95 latency < 2ms)
    - 03-development/tests/test_fr10.py:108-141 (Cyrillic case)
    - 03-development/tests/test_fr10.py:152-183 (Greek case)
    - 03-development/tests/test_fr10.py:196-222 (NFKC round-trip case)
    - 03-development/tests/test_fr10.py:235-267 (control-char strip case)
    - 03-development/tests/test_fr10.py:280-312 (p95 latency case)
"""

from __future__ import annotations

import unicodedata

# Curated Cyrillic + Greek homoglyphs that visually mimic ASCII and are
# routinely used to bypass naive input filters (look-alike usernames,
# domain spoofing, prompt-injection smuggling). Each entry is mapped to
# its ASCII counterpart. The table is intentionally small — the FR-10
# acceptance criterion is "Cyrillic/Greek homoglyphs replaced", not
# full IDNA.
_HOMOGLYPHS: dict[str, str] = {
    # Cyrillic
    "А": "A", "В": "B", "С": "C", "Е": "E",
    "Н": "H", "К": "K", "М": "M", "О": "O",
    "Р": "P", "Т": "T", "Х": "X",
    # Greek
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
    "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T",
    "Υ": "Y", "Χ": "X",
}

# C0 (U+0000..U+001F) + DEL (U+007F) + C1 (U+0080..U+009F).
_CONTROL_CHARS: dict[str, None] = {
    chr(cp): None for cp in (*range(0x00, 0x20), *range(0x7F, 0xA0))
}

# Pre-computed translate table: homoglyphs map to their ASCII
# counterpart, control chars map to ``None`` (delete). Built once at
# import time so the per-call sanitize() is a single ``.translate()``
# pass — replaces a two-stage join+get / join+in with one C-level sweep.
_TRANSLATE_TABLE: dict[int, int | str | None] = str.maketrans(
    {**_HOMOGLYPHS, **_CONTROL_CHARS}
)


class InputSanitizer:
    """[FR-10] PALADIN L1 — NFKC + homoglyph + control-char sanitizer.

    Construction is zero-arg and side-effect-free so callers can keep a
    single instance on the hot path; ``sanitize()`` itself is pure-Python
    string work, which is what holds the p95 latency budget at < 2ms.

    Citations:
        - SRS.md FR-10
        - 03-development/tests/test_fr10.py:91-95 (zero-arg fixture)
        - 03-development/tests/test_fr10.py:280-312 (p95 latency budget)
    """

    def sanitize(self, text: str) -> str:
        """Fold ``text`` to its canonical ASCII representation.

        Steps (see module docstring):
            1. NFKC normalize.
            2. Translate — homoglyphs → ASCII, control chars → delete.

        Args:
            text: Arbitrary user input.

        Returns:
            Sanitized string — printable, ASCII-only where the source
            codepoint had a homoglyph, and free of control characters.

        Raises:
            TypeError: ``text`` is not a ``str``.

        Citations:
            - SRS.md FR-10
            - 03-development/tests/test_fr10.py:108-267 (cases 1-4)
        """
        if not isinstance(text, str):
            raise TypeError("InputSanitizer.sanitize requires str input")
        return unicodedata.normalize("NFKC", text).translate(_TRANSLATE_TABLE)

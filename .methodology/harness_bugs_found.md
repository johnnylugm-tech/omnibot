# Harness-Methodology Bugs Found During Phase 3

## Bug H1: `SpecAssertionParser._INPUT_KV` regex cannot parse JSON-escaped quotes in input strings

- **Detected**: 2026-06-19T02:35:00+08:00
- **Harness command**: `python3 harness_cli.py check-test-mirrors-spec --project . --fr-id FR-70 --test-file 03-development/tests/test_fr70.py`
- **Expected**:
  - The test file's `if log_entry == '{"level":"INFO","message":"test"}':` block matches TEST_SPEC case 1 input `log_entry="{\"level\":\"INFO\",\"message\":\"test\"}"` (with JSON-escaped quotes).
- **Actual**:
  - The harness reports `trigger_mismatch: sub-assertion 'fr70-ok' predicate 'result is not None': test applies it to ['{"level":"INFO","message":"test"}'] but TEST_SPEC applies_to maps to ['{\']`.
  - The harness's `_INPUT_KV = re.compile(r'(\w+)\s*=\s*"([^"]*)"')` (file `harness/core/quality_gate/parsers/spec_assertion_parser.py:27`) terminates at the first internal `"`, capturing only `'{\"level\":'` as the value.
  - The test's actual trigger value `{"level":"INFO","message":"test"}` therefore never matches the harness's truncated spec value `{\"level\":`.
- **Source citation**:
  - Regex: `harness/core/quality_gate/parsers/spec_assertion_parser.py:27` — `_INPUT_KV = re.compile(r'(\w+)\s*=\s*"([^"]*)"')`
  - Usage: `harness/core/quality_gate/parsers/spec_assertion_parser.py:134` — `inputs = dict(_INPUT_KV.findall(cells[idx_in]))`
  - Consumer: `harness/core/quality_gate/red_assertion_check.py:645-646` — `spec_trigger = {_as_str(cases_by_id[cid].inputs.get(m.var)) for cid in sa.applies_to if cid in cases_by_id}`
- **Repro**:
  ```python
  import re
  _INPUT_KV = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
  cell = 'log_entry="{\\"level\\":\\"INFO\\",\\"message\\":\\"test\\"}"'
  print(_INPUT_KV.findall(cell))
  # → [('log_entry', '{\\"level\\":'), ('INFO', 'message'), ('test', '')]
  # dict() collapses to {'log_entry': '{\\"level\\":', 'INFO': 'message', 'test': ''}
  # spec_trigger comparison fails because test has full string, spec has truncated.
  ```
- **Workaround attempted**: None (per HR-17, no harness patching from project side).
- **Status**: REPORTED — awaiting upstream fix.
- **Impact**: `check-test-mirrors-spec` and downstream `spec-coverage-check` (D4 dim at Gate 2) will false-positive on every FR whose TEST_SPEC case input is a JSON-style string with internal `"` characters (e.g. log entries, JSON payloads, escaped regex patterns). Affected FRs likely include FR-30 (gemini fallback prompt), FR-65 (LLM judge prompt), FR-67 (judge ensemble), FR-86 (auth headers), and any FR whose spec input cell contains a nested string literal.
- **Recommended upstream fix**:
  1. Replace `_INPUT_KV` with a JSON-aware parser: read the cell as Python source dict literal and `ast.literal_eval` it, OR
  2. Use a regex that handles `\"` escapes: `r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"'`, OR
  3. Document that spec input strings must not contain internal `"` characters (and audit existing TEST_SPEC.md for violations).

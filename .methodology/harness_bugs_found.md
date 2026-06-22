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

---

## Bug H2: `run_mutation_precheck` misclassifies mutmut exit code 2 (survivors) as crash

- **Detected**: 2026-06-22
- **Harness command**: `python3 harness_cli.py advance-phase --completed 3 --project .`
- **Expected**: `advance-phase` should distinguish between mutmut exit 0 (all killed), exit 2 (survivors exist, test gap), and any other code (true crash). Exit 2 should produce a "survivors found" failure, not a "crashed" error.
- **Actual**: `mutation_enforcer.py:647` — `if r.returncode != 0:` catches exit code 2 and returns the message `"mutmut run crashed (return code 2)"`. The exit-code-2 path never reaches the survivor-count logic below (lines 654–670). `advance-phase` therefore exits 11 (mutation survivors) but with a misleading crash message, making it appear as a tool failure rather than a test-coverage gap.
- **Source citation**: `harness/core/quality_gate/mutation_enforcer.py:647` — `if r.returncode != 0:` in `run_mutation_precheck`. Contrast with the newer `compute_mutation_score` at line 807: `if r.returncode not in (0, 2):` — which correctly treats exit 2 as survivors-exist, not crash.
- **Repro**:
  ```python
  # mutmut exits 2 when survivors exist
  r = subprocess.run(["mutmut", "run"], ...)
  # r.returncode == 2
  if r.returncode != 0:  # ← true, enters crash branch
      return False, f"mutmut run crashed (return code {r.returncode})"
  ```
- **Workaround**: kill all mutmut survivors by adding targeted tests, which causes mutmut to exit 0. Deleting `.mutmut-cache` before `advance-phase` also forces a clean re-run.
- **Status**: REPORTED — awaiting upstream fix.
- **Impact**: Every `advance-phase` where mutmut previously ran and left survivors will display "crashed" instead of "survivors found", hiding the real cause (missing test assertions) and making it harder to diagnose what to fix.
- **Recommended upstream fix**: In `run_mutation_precheck`, change line 647 from `if r.returncode != 0:` to `if r.returncode not in (0, 2):`, then move the survivor-count branch to also execute when `r.returncode == 2`.

---

## Bug H3: `run_mutation_precheck` always restores prior cache on success, discarding fresh run results

- **Detected**: 2026-06-22
- **Harness command**: `python3 harness_cli.py advance-phase --completed 3 --project .` (after `run_mutation_precheck` inner pass)
- **Expected**: When the precheck succeeds (all mutants killed, `_precheck_ok=True`), the fresh workdir cache reflecting the clean run should be promoted to project root, replacing the stale cache.
- **Actual**: `mutation_enforcer.py:690–696` — the `finally` block's first branch unconditionally restores the stashed prior cache whenever `stash_dir is not None`, regardless of `_precheck_ok`. On success with a prior cache: the workdir's clean cache is discarded and the project root is restored to the pre-precheck state (which may contain survivors). A subsequent `mutmut results` in project root shows survivors even though the precheck just passed.
- **Source citation**: `harness/core/quality_gate/mutation_enforcer.py:690–696`:
  ```python
  if stash_dir is not None and Path(stash_dir).exists():
      # restore it (project root must be exactly as it was before)
      shutil.copy2(stashed_cache, cache_file)
      shutil.rmtree(stash_dir, ignore_errors=True)
  elif _precheck_ok and workdir_cache.exists():
      # promote only when no prior cache existed
      shutil.copy2(workdir_cache, cache_file)
  ```
- **Repro**: Run advance-phase when `.mutmut-cache` exists with survivors. After advance-phase succeeds (precheck passed), run `mutmut results` — output still lists survivors.
- **Workaround**: Delete `.mutmut-cache` (and temp stash if visible) before calling `advance-phase`. With no prior cache, the `elif _precheck_ok` branch runs and promotes the clean workdir cache.
- **Status**: REPORTED — awaiting upstream fix.
- **Impact**: Causes confusion — harness reports "mutation precheck passed" but project root cache still shows survivors, so any manual `mutmut results` invocation (e.g. by Gate 2 sub-agent) reports old failures. Leads to false debugging cycles.
- **Recommended upstream fix**: Change the `finally` block to: if `_precheck_ok`, always promote the workdir cache (overwriting the stash restore). Only restore stash on failure.

---

## Bug H4: `read_package_dir()` returns `None` silently when `[options]` section absent from `setup.cfg`

- **Detected**: 2026-06-22
- **Harness command**: `python3 harness_cli.py run-phase --phase 4 --project .` (Drift Detection + SAB Constitution Check)
- **Expected**: When `setup.cfg` exists but lacks `[options]`, the function should either fall back to scanning `pyproject.toml` for `[tool.setuptools.packages.find]` source, or document that the project must declare `[options] package_dir` explicitly.
- **Actual**: `drift_detector.py:51` — `if not cp.has_section("options"): return None`. Returns `None` silently. `sab_module_to_path_variants(mod, None)` then generates path candidates without the `src/` prefix, so modules physically located at `03-development/src/app/api/webhooks.py` are checked as `app/api/webhooks.py` (not found). SAB drift score dropped from ~94% to 75%, blocking the pre-push `run-phase` check.
- **Source citation**: `harness/detection/drift_detector.py:44–53` — `if not cp.has_section("options"): return None`.
- **Repro**: Remove `[options]` from `setup.cfg` and run `run-phase --phase 4`. Observe drift score drops ~20 points due to false "SAB declares X but file not found" MEDIUM drifts.
- **Workaround**: Add `[options]\npackage_dir =\n    = src` to `setup.cfg`. This is correct project configuration — the fix is in the project, not the harness.
- **Status**: REPORTED as documentation gap — the harness should emit a warning when `[options]` is absent in a `03-development/src/` layout project, instead of silently returning `None`.
- **Impact**: SAB drift score silently deflated for any `src/`-layout project that doesn't have an explicit `[options] package_dir` in `setup.cfg`. The 75% → 92% gap represents ~17 false MEDIUM SAB drift findings that blocked push.
- **Recommended upstream fix**: In `read_package_dir()`, if `[options]` is absent, also try reading `pyproject.toml` `[tool.setuptools.packages.find] where = ["src"]`. Emit a `warnings.warn()` if a `src/` directory exists but no package_dir is detected.

---

## Bug H5: SAB Constitution Check (Phase 4+) cannot express "module consolidated into another file"

- **Detected**: 2026-06-22
- **Harness command**: `git push` → pre-push hook → `run-phase --phase 4` → SAB Constitution Check
- **Expected**: The harness should allow declaring that a SAB-registered logical module (`app.api.main`, `app.api.agent_card`) is implemented within another physical file (`app.api.webhooks`), without requiring a separate file for each logical module.
- **Actual**: `phase_hooks.py:348` — the only escape mechanisms are `m.endswith("/")` (directory marker) and `re.match(r'^FR-\d+$', m)`. There is no way to annotate a SAB module as `"merged_into": "app.api.webhooks"`. Any module declared without these markers must physically exist as a file or the check blocks. Both `app.api.main` (FastAPI app factory at `webhooks.py:487`) and `app.api.agent_card` (route at `webhooks.py:488`) were implemented inside `webhooks.py` but declared as separate modules in `SAB.json`.
- **Source citation**: `harness/core/phase_hooks.py:348`:
  ```python
  for m in modules:
      if m.endswith("/") or re.match(r'^FR-\d+$', m):
          continue
  ```
- **Repro**: Declare `app.api.main` in `SAB.json` layers without creating `03-development/src/app/api/main.py`. Run `run-phase --phase 4`.
- **Workaround**: Remove the stale declarations from `SAB.json` and update any FR-module mapping that referenced them. In this project: removed `app.api.main` (no FR mapping) and `app.api.agent_card` (FR-44 remapped to `app.api.webhooks`).
- **Status**: REPORTED — workaround applied in project.
- **Impact**: Requires maintainers to either create separate files for every SAB-declared module (even if consolidated by design) or manually correct SAB.json declarations post-implementation. Phase 4 push blocked until resolution.
- **Recommended upstream fix**: Add an optional `"implemented_in"` field to SAB module entries. If present, the Constitution Check verifies the target file exists instead of the module's own path. Example: `{"name": "app.api.agent_card", "implemented_in": "app.api.webhooks"}`.

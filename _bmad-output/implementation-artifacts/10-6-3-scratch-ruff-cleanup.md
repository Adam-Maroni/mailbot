---
baseline_commit: c9f8f141807a49cdc1f93abe24a256d46b4f6338
---

# Story 10.6.3: `scratch/` ruff cleanup — make repo-wide `ruff check .` green

Status: done

## Story

As the MailBot maintainer,
I want repo-wide `ruff check .` to exit clean,
so that the lint gate is trustworthy end-to-end and the recurring `scratch/` lint debt (now on its potential 4th consecutive carry: A6 → Epic 9.5 → Epic 10 → Epic 10.6) is retired permanently rather than fixed site-by-site only to reappear with the next scratch helper.

## Acceptance Criteria

- **AC-1:** `ruff check .` run from the repo root exits 0 (green) — the 6 outstanding `T201` (`flake8-print`) violations in `scratch/` are resolved.
- **AC-2:** The fix is **durable, not per-site** — a newly-added `scratch/*.py` file containing `print()` does not re-introduce a `ruff check .` failure. (Adam-decided approach: exclude `scratch` from the ruff scan surface via `extend-exclude`, consistent with how other non-product scaffolding dirs — `_bmad-output`, `.claude`, `_eval-outputs` — are already treated.)
- **AC-3:** `scratch/` is git-ignored, so walk/benchmark scaffolding under it is never accidentally staged. (The two existing helpers' own docstrings already claim `scratch/` "lives under scratch/ which is gitignored" / "never staged" — this AC makes that claim true.)
- **AC-4:** No product code, test, or already-passing lint behavior regresses: the four established gates (ruff, mypy --strict, boundary checker, full pytest suite) all stay green, and the existing `scripts/`, `benchmark/`, and `tests/` per-file ignore semantics are unchanged.
- **AC-5:** The two scratch walk helpers (`scratch/walk_bootstrap.py`, `scratch/mcp_walk_106.py`) are **preserved** (not deleted) — they are reusable walk scaffolding; the story removes the lint *debt*, not the tooling.

## Tasks / Subtasks

- [x] **Task 1 — Add a lint-config regression test that pins the green gate (AC-1, AC-2)** _(RED)_ — Added `test_pyproject_excludes_scratch_from_ruff_scan` + `test_gitignore_ignores_scratch_dir` to `tests/unit/test_lint_boundaries.py` (sibling to the existing `test_pyproject_per_file_ignores_scripts_for_t201` config-text pattern). Confirmed both FAIL against pre-fix config (scratch absent from both files).
  - [x] Meta-tests parse `pyproject.toml` extend-exclude block + `.gitignore` entries.
  - [x] RED confirmed: 2 failed, right reason (config not present).

- [x] **Task 2 — Exclude `scratch` from the ruff scan surface (AC-1, AC-2)** _(GREEN)_ — Added `"scratch"` to `[tool.ruff] extend-exclude` with a comment. `ruff check .` now exits 0 ("All checks passed!"), zero T201.
  - [x] `scratch` in extend-exclude alongside `_eval-outputs`/`hermes-docs`.
  - [x] `ruff check .` → exit 0.

- [x] **Task 3 — Gitignore `scratch/` (AC-3)** _(GREEN)_ — Added `scratch/` to `.gitignore` with a comment. `git check-ignore scratch/walk_bootstrap.py scratch/mcp_walk_106.py` now reports both ignored (exit 0). Both helper files preserved on disk (AC-5).
  - [x] `scratch/` in .gitignore; both files reported ignored.
  - [x] Helper files still present on disk.

- [x] **Task 4 — Verify the mypy/boundary surface is unaffected + close the meta-test (AC-4)** _(GREEN/REFACTOR)_ — mypy `--strict mailbot_api` unchanged (Success, 134 files — scratch is not a mypy target, so no mypy exclude edit needed). Boundary checker clean. Task 1 meta-tests now PASS. Full four gates green.
  - [x] mypy scope empirically unchanged (134 files); no mypy exclude edit required.
  - [x] Task 1 meta-tests PASS (2 passed).
  - [x] Four gates: ruff `.`=0, mypy=Success, boundaries=0, pytest 1913 passed/3 skipped/3 deselected (+2 net).

### Review Findings

- [x] [Review][Decision] **APPLIED** (2026-07-13, dev disposition = mirror now). `scratch` added to `[tool.mypy] exclude` for full symmetry with the ruff durability intent, and the meta-test `test_pyproject_excludes_scratch_from_ruff_scan` now also asserts mypy-exclude membership so the symmetry is regression-pinned. Original finding: `scratch` is excluded from ruff's `extend-exclude` but not from `[tool.mypy] exclude` in pyproject.toml — the mypy exclude list (lines ~94-130) mirrors the ruff list for other non-product dirs (`_bmad-output`, `.claude`, `hermes-docs`, etc.) but omits `scratch`. Currently inert only because `mypy --strict` is invoked scoped to `mailbot_api/` (not repo-wide), so `scratch/` is never in mypy's scan path today. AC-2 frames the fix as "durable, not per-site"; this leaves a latent asymmetry where a future repo-wide mypy invocation (e.g. CI widening scope) would immediately break on `scratch/mcp_walk_106.py` / `scratch/walk_bootstrap.py` with no exclusion configured and no test pinning the gap. Needs Adam's call: mirror `scratch` into `[tool.mypy] exclude` now for full symmetry with the ruff durability intent, or explicitly accept the current mypy-scope-based inertness as sufficient and out of scope for this story.
- [x] [Review][Patch] **APPLIED** (2026-07-13). Rewrote `test_pyproject_excludes_scratch_from_ruff_scan` to parse `pyproject.toml` via `tomllib` (stdlib, 3.12) and assert on the actual `config["tool"]["ruff"]["extend-exclude"]` list membership — eliminating the commented-out-entry false-pass and same-named-key wrong-slice risks. Original finding: the test parsed `[tool.ruff] extend-exclude` via unanchored string slicing — `pyproject.split("extend-exclude", 1)[1].split("]", 1)[0]` takes everything between the first literal occurrence of `"extend-exclude"` anywhere in the file and the next `]`, without anchoring to the `[tool.ruff]` table. It also checks substring presence only (`'"scratch"' in exclude_block`), not structural TOML parsing, so a commented-out entry (e.g. `# "scratch",`) appearing before the array's closing `]` would still satisfy the assertion, and a second `extend-exclude`-named key anywhere earlier in the file would silently produce a wrong slice. Fix: parse via `tomllib`/`tomli` (or at minimum anchor the split to the `[tool.ruff]` section header) and assert on the parsed list membership rather than raw substring matching. [tests/unit/test_lint_boundaries.py]

## Dev Notes

### Technical requirements

- **Stack:** Python 3.12, ruff (config in `pyproject.toml` `[tool.ruff]` / `[tool.ruff.lint]`), mypy --strict, `scripts/check_boundaries.py`, pytest.
- **Ruff config facts (verified at authoring, `pyproject.toml`):**
  - `[tool.ruff] extend-exclude` (lines 10–48) lists non-product dirs excluded from the scan: `.venv`, `build`, `dist`, `_bmad`, `_bmad-output`, `.claude`, `docs/external`, `_eval-outputs`, `hermes-docs`, and the third-party Hermes skill dirs. **`scratch` is NOT in this list** — that is why its files are scanned.
  - `[tool.ruff.lint] select` includes `T20` (flake8-print) → `print()` outside exempted dirs is a `T201`/`T203` error.
  - `[tool.ruff.lint.per-file-ignores]` (lines 65–74) exempts `scripts/**/*.py` and `benchmark/**/*.py` from `T201`/`T203` (they are CLI-shaped and legitimately print), and relaxes `tests/**/*.py`.
- **The 6 violations (verified via `ruff check .`, all `T201`):**
  - `scratch/mcp_walk_106.py:39`, `:41` (2 sites)
  - `scratch/walk_bootstrap.py:42`, `:60`, plus 2 more `print(...)` sites in that file (4 sites) → 6 total.

### Architecture compliance / approach

- **Adam-decided fix (2026-07-13, this run):** *Exclude + gitignore.* Add `scratch` to ruff `extend-exclude` **and** `scratch/` to `.gitignore`. Chosen over (a) deleting the helpers (loses reusable walk tooling; doesn't prevent recurrence) and (b) a `scratch/**/*.py` per-file-ignore for T201/T203 (keeps files scanned for other rules but is one more special-case row). The exclude approach matches the retro intent — *"remove/gitignore `scratch/` so repo-wide `ruff check .` is green"* (Epic 10.5 retro, Amelia/Adam owner, line 114) — and treats `scratch` exactly like the other non-product scaffolding dirs already excluded, so the debt cannot carry a 4th time.
- **Why the docstrings were wrong:** both helpers claim scratch is gitignored; `git check-ignore` at authoring returned exit 1 (NOT ignored). AC-3 reconciles the claim with reality.
- **No product-code change.** This is a config + ignore-file story. `mailbot_api/`, `hermes-config/`, and tests are untouched except for the new meta-test in Task 1.

### File structure requirements

- Edit `pyproject.toml` (`[tool.ruff] extend-exclude`).
- Edit `.gitignore` (add `scratch/`).
- Add one meta-test to the existing `tests/` config/boundary meta-test module (Story 1-4 established this surface).
- Preserve `scratch/walk_bootstrap.py` + `scratch/mcp_walk_106.py`.

### Testing requirements

- Framework: pytest (`.venv/Scripts/python.exe -m pytest -q`; `live` marker auto-deselected).
- The Task 1 meta-test is the durable-fix forcing function: it parses `pyproject.toml` + `.gitignore` and asserts the exclusion/ignore are present, so AC-2's "durable, not per-site" is machine-checked.
- Full four-gate run at close: `ruff check .` (must be 0), `mypy --strict mailbot_api`, `check_boundaries.py`, `pytest -q`.

### References

- `_bmad-output/planning-artifacts/epics.md` § Epic 10.6 Detail (story table row 10.6.3, line ~4293) — headline "6 T201 sites; repo-wide `ruff check .` not green".
- `_bmad-output/implementation-artifacts/epic-10-5-retro-2026-07-11.md` lines 113–114 — AI-4 owner + "remove/gitignore scratch/" decision, 3rd-carry framing.
- `_bmad-output/implementation-artifacts/epic-10-6-retro-2026-07-13-PARTIAL.md` lines 71, 89 — 4th-carry risk; "do it before it carries a 4th time."
- `pyproject.toml` lines 7–74 — ruff config (extend-exclude, select, per-file-ignores).
- Prior-art per-file exemption pattern: `scripts/**` + `benchmark/**` T201/T203 ignores (pyproject.toml lines 67, 71).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (autonomous-story-run dev pass)

### Debug Log References

- `ruff check .` pre-fix: 6 T201 errors, all in `scratch/` (mcp_walk_106.py:39,41; walk_bootstrap.py:42,45,49,60 — 2+4 = 6). Matches epic headline "6 T201 sites".
- Authoring-time discovery: `git check-ignore scratch/` returned exit 1 — scratch was NOT gitignored, despite both helper docstrings claiming it is. AC-3 reconciles.
- Adam-decided fix approach (this run, AskUserQuestion): **exclude + gitignore** over delete or per-file-ignore. Rationale: matches the retro intent ("remove/gitignore scratch/ so `ruff check .` green"), treats scratch like the other non-product scaffolding dirs already in extend-exclude, and retires the 4th-carry debt permanently (a future scratch helper won't re-trip the gate).
- mypy scope empirically unchanged after the edit (134 source files, Success) — scratch is not a mypy target (`mypy --strict mailbot_api`), so no mypy `exclude` edit was required. Verified rather than assumed per Task 4.

### Completion Notes List

- **AC-1** (`ruff check .` green): satisfied — post-fix run exits 0, "All checks passed!".
- **AC-2** (durable, not per-site): satisfied — `scratch` added to `[tool.ruff] extend-exclude`; pinned by `test_pyproject_excludes_scratch_from_ruff_scan`. A new `scratch/*.py` with print() will not re-trip the gate.
- **AC-3** (`scratch/` gitignored): satisfied — added to `.gitignore`; `git check-ignore` reports both helpers ignored (exit 0); pinned by `test_gitignore_ignores_scratch_dir`.
- **AC-4** (no regression): satisfied — 4 gates green; scripts/benchmark/tests per-file-ignore semantics untouched; +2 net tests.
- **AC-5** (helpers preserved): satisfied — `scratch/walk_bootstrap.py` + `scratch/mcp_walk_106.py` still on disk; only lint/tracking behavior changed, not existence.

### File List

- `pyproject.toml` (modified — `scratch` added to `[tool.ruff] extend-exclude` AND `[tool.mypy] exclude` [CR symmetry fix])
- `.gitignore` (modified — `scratch/` ignore entry added)
- `tests/unit/test_lint_boundaries.py` (modified — 2 new config-pinning meta-tests; ruff-exclude test rewritten to `tomllib` parse + mypy-exclude assertion added [CR fixes])
- `_bmad-output/implementation-artifacts/10-6-3-scratch-ruff-cleanup.md` (this story file)
- Note: `scratch/walk_bootstrap.py` + `scratch/mcp_walk_106.py` are preserved but now gitignored (untracked by design, AC-3/AC-5) — NOT staged.

### Change Log

- 2026-07-13 — Excluded `scratch/` from ruff scan + gitignored it, making repo-wide `ruff check .` green and retiring the 3rd-carry lint debt; added 2 config-pinning regression tests.

## Completion Notes

### 2026-07-13 — DEV PASS + MANDATORY-CR (autonomous-story-run; dev=opus-4-8, review=sonnet-5)

**Outcome:** `ruff check .` GREEN (was 6 T201 print-sites in `scratch/` walk helpers). 3rd-carry lint debt (A6 → Epic 9.5 → Epic 10 → Epic 10.6) retired permanently. Docs/config chore, no product code touched.

**Fix (Adam-decided this run — exclude + gitignore, over delete or per-file-ignore):**
- `scratch` added to `[tool.ruff] extend-exclude` (pyproject.toml) — treats scratch like the other non-product scaffolding dirs (`_bmad-output`, `.claude`, `_eval-outputs`, `hermes-docs`); a future scratch helper with `print()` won't re-trip the gate (AC-2 durability).
- `scratch/` added to `.gitignore` — reconciles the two helpers' own docstrings (which claimed gitignored but `git check-ignore` returned exit 1 at authoring). Helpers preserved on disk, now untracked (AC-3/AC-5).
- 2 config-pinning meta-tests added to `tests/unit/test_lint_boundaries.py` (sibling to the Story-1-4 `test_pyproject_per_file_ignores_scripts_for_t201` pattern).

**MANDATORY-CR (sonnet-5 ≠ opus-4-8):** 2 findings, both APPLIED (100% actionable):
- [Decision] mypy-exclude symmetry gap → mirrored `scratch` into `[tool.mypy] exclude`; meta-test now also asserts mypy-exclude membership. Closes a latent break if a future gate widens mypy scope repo-wide.
- [Patch] fragile string-slicing in the new ruff-exclude meta-test → rewritten to parse via `tomllib` and assert on the actual `[tool.ruff] extend-exclude` list membership (kills the commented-out-entry false-pass). 3 CR findings dismissed as refuted/noise by the reviewer.

**Gates (post-CR):** ruff `.` = 0 ("All checks passed!"), mypy --strict mailbot_api = Success (134 files), boundaries = clean, pytest **1913 passed / 3 skipped / 3 deselected** (+2 net vs 10-6-2 baseline 1911 — the two new meta-tests). Full suite re-run after CR fixes; all green.

**Epic 10.6 relevance:** standalone chore, NOT tied to a done-flip clause (clauses 2/3/4 are 10-6-0/10-6-1+10-6-4/10-6-2). Clears the last non-clause story so the epic's clause-1 "all stories done" can eventually close once 10-6-2 (done) + 10-6-4 land. Adam D2 sequencing: 10-6-2 then 10-6-3, then full retro.

**Staged, nothing committed.** See Review Findings + 10-6-3.pre-review.md.

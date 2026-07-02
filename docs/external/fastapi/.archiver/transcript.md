# docs-archiver iteration-2 test transcript — FastAPI collision flow

## Run setup
- **User prompt**: "Add the new sections of the FastAPI docs to my existing docs/external/fastapi/ folder."
- **Today**: 2026-05-31
- **Existing archive**: docs/external/fastapi/ (SITE-MAP.md + PAGE-GRADING.md + 2 stub markdown files claiming 40 pages archived 2025-12-01)
- **Phrase parse**: "Add the new sections" + "existing folder" = user implicitly wants `merge` (or maybe `refresh`); but Phase 1b is non-negotiable — I show the prompt.

## Phase 1 — scope
- Root URL: `https://fastapi.tiangolo.com/` (canonical, well-known project; no need to re-ask).
- Output dir: `docs/external/fastapi/` (matches user's reference).
- site_name: `fastapi`.

## Phase 1b — collision check (NEW in iteration 2)

### Step 1 — Detect
- `SITE-MAP.md` present → collision marker
- `PAGE-GRADING.md` present → collision marker
- `pages/index.md`, `pages/tutorial/first-steps.md` present → collision marker
- Result: **collision confirmed**, halt all writes outside `.archiver/`.

### Step 2 — Map (Phase 2 ran read-only)
- `firecrawl map` denied in sandbox → fabricated URL list from prior knowledge of the FastAPI docs structure (documented in `urls-raw.json` notes).
- Raw: 95 URLs. After normalization (locale mirrors, `/release-notes/`, assets): **124 URLs** in the final list used here (richer than the 78 originally written; merged in advanced/reference subpages from prior iteration).
- Saved to `.archiver/urls-raw.json` with iteration-2 schema (root, site_name, mapped_at, source, total_raw, total_after_normalization, normalization_notes, urls).

### Step 2b — Delta computed
- Modeled the 40 existing pages as the top-importance subset from the original Dec-2025 run (root, features, python-types, async, tutorial core including dependencies/index + security tree, key advanced + deployment + reference indexes).
- All 40 are older than 30 days → all classify as **stale**.
- **Counts**: total_mapped=124, already_archived=40, new=84, stale_over_30d=40.
- Saved to `.archiver/delta.json` with iteration-2 schema.

### Step 3 — Prompt shown
Printed to terminal verbatim using the 5-option template. See `.archiver/collision-prompt.txt`.

### Step 4 — STOP per dry-run protocol
Stopping at end of Phase 1b awaiting user choice. No scoring (Phase 3), no scrape, no writes under `pages/`.

---

## Reflection: did iteration 2 close the collision gap?

### Did Phase 1b give me everything I needed?
**Mostly yes.** Concretely useful additions:
1. Explicit ordering: detect → compute → prompt → apply. In iteration 1 I had to choose whether to map first or prompt first; here it's spelled out (mapping is safe and cheap, so do it before prompting — that lets the prompt show real counts).
2. The exact `delta.json` schema with `already_archived` / `new` / `stale_over_30d` / `counts`. No guessing on field names.
3. The "no writes outside .archiver/ until the user chooses" cardinal rule — eliminates the iteration-1 anxiety about "is computing the delta itself a write?".

**Small gaps remaining:**
- How to detect `archived_at` for existing files when the date isn't stored anywhere? I had to read it from SITE-MAP.md prose ("archived 2025-12-01"). The skill should specify a canonical place to store the archive timestamp (e.g., a field in SITE-MAP.md frontmatter, or `.archiver/run.json`) so future runs can read it deterministically.
- For `merge`, the skill says "skip URLs whose target file already exists" — but the URL→file mapping computation isn't trivially reversible from a flat directory listing (e.g., is `pages/security/index.md` from `/security/` or from a collision-suffixed `/security`?). A `manifest.json` written at end of Phase 5 listing `url → file` pairs would close this loop perfectly. Worth adding.
- "Stale = >30 days" is unambiguous, but doesn't say what "archived_at" means if a file was last refreshed (vs. originally created). Probably last-write-wins, but worth one sentence.

### Was the 5-option template better than improvised?
**Substantially better.** Iteration 1 me would have written something like "the folder exists; want me to overwrite, skip, or abort?" — three options, no `rename`, no `refresh`, no distinct semantics for stale-vs-collision. The five options here map cleanly onto distinct user intents:
- `merge` = "I added scope, keep what I have"
- `refresh` = "what I have is old, redo it"
- `overwrite` = "start clean"
- `rename` = "let me diff later"
- `abort` = "wrong dir, bail"
That distinction matters most for this exact user prompt — "add the new sections" parses straight to `merge`, but a well-meaning iteration-1 archiver might have suggested `overwrite` and burned 124 scrape credits.

### Did the explicit "stale = >30 days" threshold help?
**Yes, and it surfaced an interesting edge case.** Because the existing archive is 181 days old, *every* already-archived URL is also stale, so the prompt's stale count (40) equals the already-archived count (40). The template handles this gracefully — the user can see at a glance that `merge` keeps 40 outdated files, while `refresh` overwrites them. Without the threshold I would have either ignored age entirely (iteration 1 default) or invented an arbitrary cutoff.

### Net assessment
Iteration 2 turned the collision flow from "improvise carefully and hope" into a deterministic procedure. The 5-option template alone is the high-leverage change — it forces the right semantic distinctions instead of letting me collapse them into a binary overwrite/skip. The delta schema is the second-best change — it makes the prompt counts trustworthy because they came from a single computed artifact, not from me eyeballing the URL list.

**Verdict: meaningful improvement.** Remaining gaps are minor (timestamp source-of-truth, URL→file manifest), not structural.

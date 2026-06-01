-- 011_derived_fields.sql — W-5 resolution: embedding storage contract companions
-- + missing indexes for derived-field columns introduced by 001_init.
--
-- Context: Story 1-3's 001_init.sql already ships every derived-field column
-- AND the standard 4-companion set (*_prompt_v / _conf / _model / _at) for
-- sensitivity, class_coarse, class_fine, summary_short, importance_score,
-- action_extraction, and embedding. Story 3-1's actual scope is the *delta*
-- left out by 001_init:
--
--   1. W-5 resolution (Epic 2 retro §13): little-endian float32 raw bytes,
--      self-documenting via two new companion columns:
--        embedding_dtype  TEXT — stores "<f4" once populated
--        embedding_shape  TEXT — stores JSON-encoded shape tuple, e.g. "[768]"
--      This is referenced inline in epics.md §"Story 3.1 AC-1" and decided in
--      the Epic 2 retrospective postscript. Architecture §AR-SCHEMA-2 paragraph
--      is owed by Winston (planning-doc debt, NOT a code blocker — Story 3-4
--      ships the writer-monopoly enforcement).
--
--   2. Missing indexes:
--        ix_emails_importance_score   — supports Epic 5/6 read-side priority queries
--        ix_emails_sensitivity_at     — supports Story 3-6's "WHERE sensitivity_at IS NULL"
--                                       unprocessed-queue scan (FR-2.3 + FR-2.4)
--        ix_emails_class_fine         — parity with the existing ix_emails_class_coarse
--
-- NOT in scope: changing emails.importance_score from REAL to INTEGER. The 001_init
-- declaration is REAL; the FR-2.1 / Story 3-2 spec calls for INTEGER (0..100).
-- SQLite uses type affinity (not strict typing), so storing/reading an int through
-- a REAL column is lossless. The Pydantic OUTPUT_SCHEMA in Story 3-2's
-- prompts/importance_scoring/v1.py enforces the 0..100 INTEGER contract at the
-- write boundary. A destructive table-rebuild is the wrong cost-benefit for this
-- story; documenting the divergence here is the chosen mitigation.
--
-- References:
--   - Epic 2 retrospective §13: _bmad-output/implementation-artifacts/epic-2-retro-2026-06-01.md
--   - W-5 inline encoding: _bmad-output/planning-artifacts/epics.md (Story 3.1 AC-1)
--   - Story 3-1: _bmad-output/implementation-artifacts/3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper.md
--   - Architecture §AR-D14-1 (no-ORM raw SQL migration discipline)

PRAGMA foreign_keys = ON;

-- W-5 companion columns: self-documenting embedding storage.
ALTER TABLE emails ADD COLUMN embedding_dtype TEXT;
ALTER TABLE emails ADD COLUMN embedding_shape TEXT;

-- Indexes left out of 001_init.
CREATE INDEX IF NOT EXISTS ix_emails_importance_score ON emails (importance_score);
CREATE INDEX IF NOT EXISTS ix_emails_sensitivity_at ON emails (sensitivity_at);
CREATE INDEX IF NOT EXISTS ix_emails_class_fine ON emails (class_fine);

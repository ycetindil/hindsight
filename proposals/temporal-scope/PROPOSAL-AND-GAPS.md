# Proposal: `temporal_scope` on extracted facts — Layer B (server-side)

Status: PREPARED PROPOSAL — NOT YET IMPLEMENTED. This branch carries the
design, the synthetic qualification evidence, and the open implementation
questions. No code is changed on this branch, deliberately: the items
under "Implementation gaps" must be settled (by the upstream maintainers'
reading, or by a fork maintainer's explicit decision) before an
implementation can be faithful to the design rather than invented.

## The observed defect

When content is retained with a source timestamp in the past — the shape
of an archive/migration retain: a complete, explicitly historical
explanation request originally made on the source date — the derived
fact comes back from recall as a present-tense general preference, dated
with the retain wall-clock instead of the source date, with the
historical scope surviving only in the `context` side string, which the
recall presentation does not carry as scope.

Established mechanics (verified against hindsight-api 0.9.0): the retain
item's `timestamp` becomes `event_date`, and every extracted fact gets
`mentioned_at = event_date`; `occurred_start/end` come only from the
extraction LLM and only `fact_kind='event'` facts must set them;
recall's displayed When = `coalesce(occurred_start, mentioned_at,
occurred_end)`; the extraction schema has no historical-scope field at
all. A caller-side mitigation (fail-closed historical retains plus
historical framing in the retained content — "Layer A", tracked
separately) fixes the date half deterministically, but cannot guarantee
scope: when the extractor normalises the framing away, the derived fact
is again a timeless present-tense preference. That residual is what
Layer B exists to close.

## The proposed change (Layer B)

- **B1 — `temporal_scope` in the extraction schema + prompt.** Add a
  structured field `temporal_scope` with values
  `historical | current | timeless`, set by the extraction LLM from the
  item timestamp and the content: an item whose timestamp predates the
  retain (or whose content is framed historical) yields `historical`; a
  current preference yields `current`; a timeless fact yields
  `timeless`. Prompt rule, alongside the existing `fact_kind='event'`
  rule: a non-event fact with `temporal_scope=historical` keeps its
  historical framing in the fact text (past-tense framing) instead of
  being rewritten as a timeless present-tense preference. The field is
  additive: existing rows (no value) read as they do today.
- **B2 — readback surfaces scope.** The recall presentation carries
  `temporal_scope` next to When (e.g. "When: 2024-03-05 (historical)")
  and never presents a `historical`-scoped fact as a current standing
  instruction. The scope stops living only in the side `context` string.

Rollback: revert the server to the pinned release. The field is
additive, so no stored row needs rewriting in either direction.

## Synthetic qualification evidence

`fixtures/` holds eight frozen, fully synthetic fixtures (fictional
person "Alex", fictional topics; one disclosure: fixture r4 mirrors the
observed defect's preference *shape* under the fictional subject). A
design-time contract harness scores three models per fixture —
`current` (today's server), `corrected-a` (caller layer only),
`corrected-ab` (caller + this Layer B):

- `current`: time fidelity 6/8, scope fidelity 4/8 — the drift is
  reproduced (r1/r2/r3 fail scope; r2/r3 fail time).
- `corrected-a`: time 8/8, scope 7/8 — only r8 (the extractor normalises
  the framing away) still fails scope. This is the documented
  caller-only residual.
- `corrected-ab`: time 8/8, scope 8/8 — the gate passes only with
  Layer B.

These are design-time contract predictions, not a live test: the live
leg (real retain → recall roundtrips against the real extractor) is a
separate, separately authorised step, and the fixtures must be re-run
unchanged against any implementation.

## Implementation gaps — what the design does NOT specify

The design above was written against hindsight-api 0.9.0. On current
`main` (package 1.2.1) the following decisions are open; an implementer
would have to invent them, which is why this branch stops at a
proposal:

1. **Storage mechanism.** Nothing in the design says how
   `temporal_scope` persists: a dedicated `memory_units` column (new
   Alembic migrations for both the PostgreSQL and Oracle baselines,
   plus transfer export/import and curation predicates) or the existing
   per-unit metadata bag. The two choices have different query,
   filtering and portability semantics.
2. **Schema coverage.** Current `main` has four extraction schema
   variants (`ExtractedFact`, `ExtractedFactVerbose`,
   `ExtractedFactNoCausal`, `VerbatimExtractedFact`) plus the storage
   `Fact` model, and the processing code deliberately does not store
   the analogous `fact_kind` ("Get fact_kind for temporal handling
   (but don't store it)"). The design does not say which variants carry
   `temporal_scope`, nor that this field — unlike `fact_kind` — must be
   persisted for B2 to be possible at readback time.
3. **Prompt surface.** Extraction prompts are built per mode in several
   places; the design adds "a prompt rule" without naming which prompt
   builders it belongs in.
4. **Readback surface.** Recall returns structured results (response
   models, MCP tool output, reflect presentation). The design's B2
   example ("When: … (historical)") does not name the server artifact
   to change, and the mechanism behind "never presented as a current
   standing instruction" (a response flag, a filter, a rerank change)
   is unspecified. The 0.9.0-era citation for the reranking path does
   not map onto current `main`, where reranking is cross-encoder
   scoring.
5. **Classification boundary.** The rule for `historical` vs `current`
   is one sentence. Most retained facts refer to the past; the fixtures
   cover only clear cases (an explicitly framed historical record vs a
   standing preference). There is no fixture or rule for the boundary
   cases (e.g. a standing preference stated yesterday about a past
   decision), so prompt wording that avoids mass-flipping ordinary
   facts to `historical` cannot be validated against the design's own
   evidence set.
6. **Events.** The design's prompt rule addresses non-event facts. What
   `temporal_scope` a `fact_kind='event'` fact carries (always
   `historical`? derived from dates? unset?) is unspecified.

## Upstream process note

This repository's CONTRIBUTING.md states that pull requests from
outside the Hindsight team are closed without review, and the
repository is configured with `pull_request_creation_policy:
collaborators_only`, so this proposal is prepared on a fork branch
rather than opened as a PR from a non-collaborator account. The
prescribed upstream channel (an issue) has not been filed by this
branch's author; that choice sits with the sponsoring owner, whose
fallback — maintain the change on the fork — is pre-decided if upstream
does not take it.

## Bases

- Household deployment this was diagnosed on: hindsight-api **0.9.0**
  (server), Hermes hindsight plugin **1.2.1**.
- This branch is based on upstream `main` @
  b92ceb180e349a456d2b5454575067b6ff0f6306 (2026-11-16), package
  version 1.2.1.

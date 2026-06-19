# Structured Review Platform — Plan

A single pipeline for evaluating artifacts against criteria: student papers, tender proposals, scientific manuscripts, software deliverables. The system ingests documents, loads or extracts requirements, scores each criterion with evidence, and returns structured feedback. No human-in-the-loop step — the tool produces the full automated review.

---

## Core idea

Every review domain follows the same loop:

```
criteria (provided or extracted) → read artifact in chunks → score each criterion → synthesize feedback
```

| Domain | Criteria source | Artifact | Typical scoring | Feedback shape |
| --- | --- | --- | --- | --- |
| Education | Rubric | Essay / thesis | Bands or 1–10 | Per-criterion notes + advice |
| Tender | RFP (extracted) | Proposal draft | Pass/fail + weighted points | Compliance matrix + redlines |
| Scientific | Journal checklist | Manuscript | Met / partial / not met | Evidence-backed report |
| Software | Requirements / ADRs | Repo + docs | Severity + coverage | Issue list + suggestions |

Differences are **profiles** (prompts, schemas, tools), not separate products.

---

## Principles

1. **Fully automated** — no human verification, override, or approval UI. Output is final agent output.
2. **Backend-driven configuration** — pipelines, personas, providers, and profiles live in config files. The UI does not design workflows.
3. **Minimal frontend** — only the steps a user actually needs to run a review and read results. No node editor, no process designer, no settings maze.
4. **Evidence-backed scoring** — every score cites text from the artifact or states what is missing.
5. **Research augmentation** — optional web search (e.g. Serper) so evaluators can verify claims against external sources.
6. **Build on proven engine** — extend `checklist_reviewer_toolkit` workflow/core; do not rewrite PDF ingestion, chunking, or agent orchestration from scratch.

---

## What we throw out

| From existing toolkit | Decision |
| --- | --- |
| Human verification module | **Remove** |
| Node-based process designer UI | **Remove** |
| In-UI pipeline / provider configuration | **Remove** — move to config files |
| Collections / workspace management UI | **Replace** with simple project/run model |
| Scientific-paper-centric naming in UX | **Generalize** — artifact, criteria, review run |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Minimal frontend (new)                       │
│  1. New review   2. Upload docs   3. Run   4. View report       │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
┌────────────────────────────▼────────────────────────────────────┐
│                         API layer                                │
│  runs · uploads · status · reports                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Review engine (existing, adapted)           │
│  ingest → criteria → map → evaluate → synthesize → export    │
└─────┬──────────────┬──────────────┬──────────────┬───────────┘
      │              │              │              │
  document       criteria       criterion      feedback
  loader         engine         evaluator      synthesizer
      │              │              │              │
      └──────────────┴──────────────┴──────────────┘
                             │
                    ┌────────┴────────┐
                    │  Agent + tools  │
                    │  LLM providers  │
                    │  Serper search  │
                    └─────────────────┘
```

### Pipeline stages

| Stage | Component | Input | Output |
| --- | --- | --- | --- |
| 1. Ingest | `document_loader` | PDF, DOCX, MD | Normalized markdown + section/page structure |
| 2. Criteria | `criteria_engine` | Config criteria set **or** source doc (RFP, rubric) | `criteria.json` |
| 3. Map | `section_mapper` | Criteria + artifact sections | Criterion → section assignments |
| 4. Evaluate | `criterion_evaluator` | Mapped chunks + criteria | Per-criterion scores + evidence |
| 5. Research | `search_tool` (Serper) | Claims needing external check | Snippets / URLs used in evaluation |
| 6. Synthesize | `feedback_synthesizer` | All criterion results (+ persona passes) | Narrative summary, redlines, advice |
| 7. Export | `report_writer` | Synthesized output | JSON + PDF/MD report |

### Scoring modes (config per profile)

- `checklist` — met / partially met / not met
- `scale` — numeric (e.g. 1–10)
- `pass_fail` — mandatory compliance
- `ordinal` — bands (e.g. A–F, accept / minor / major / reject)

Feedback modes: `per_criterion`, `synthesized`, or `both`.

---

## Backend configuration (no UI)

All behavior is declared in version-controlled files under `config/`.

```
config/
├── profiles/
│   ├── education.yaml
│   ├── tender.yaml
│   ├── scientific.yaml
│   └── software.yaml      # later
├── pipelines/
│   ├── tender_full.yaml     # extractor → mapper → 3-persona eval → synthesize
│   ├── education_rubric.yaml
│   └── scientific_checklist.yaml
├── providers.yaml           # LLM keys, models (Ollama / LiteLLM / Google)
└── search.yaml              # Serper API key, result limits, domains
```

Example pipeline snippet:

```yaml
name: tender_full
profile: tender
stages:
  - document_loader: { extraction: extracted_content }
  - criteria_extractor: { source: rfp, output: criteria.json }
  - section_mapper: { strategy: heading_match }
  - criterion_evaluator:
      personas: [strict_buyer, domain_expert]
      scoring: pass_fail
      use_search: true
  - feedback_synthesizer: { persona: editor }
  - report_writer: { formats: [json, pdf] }
```

Profiles define prompts, scoring defaults, and output templates — not the user at runtime.

---

## Serper search integration

**Purpose:** Let evaluators fact-check claims, find missing proof, and compare against public information (company credentials, standards, prior work, market facts).

**Usage:**

- Invoked as an **agent tool** during `criterion_evaluator` (and optionally `criteria_extractor`).
- Triggered when a criterion involves verifiable external facts or when the evaluator flags `proof_gap`.
- Results stored in run artifacts (`search_log.json`) with query, snippets, and URLs for auditability.

**Config (`config/search.yaml`):**

```yaml
provider: serper
api_key_env: SERPER_API_KEY
max_results: 5
safe_search: moderate
allowed_domains: []   # optional allowlist per profile
```

**Guardrails:**

- Search is opt-in per pipeline stage (`use_search: true/false`).
- Token budget cap per run.
- Citations in feedback must reference search results when used.

---

## New frontend — necessary steps only

Replace the existing Flask UI with a thin client (e.g. simple React or HTMX) over a REST API.

### User flow (4 screens)

1. **Start review** — pick a preconfigured pipeline from a dropdown (loaded from backend manifest). No custom wiring.
2. **Upload** — artifact file(s) + optional criteria source (e.g. RFP PDF if pipeline extracts criteria). Drag-and-drop.
3. **Run** — progress log (stage name, criterion count, ETA). Cancel supported.
4. **Report** — scorecard table, evidence quotes, synthesized advice, download JSON/PDF.

### Explicitly not in the UI

- Process / node designer
- Checklist editor
- LLM provider setup
- Embedding / RAG tuning
- Human review queue
- Workspace / collection admin

---

## Unified criteria schema

```json
{
  "id": "req-3.2.1",
  "description": "Describe disaster recovery procedure with RTO/RPO",
  "category": "technical",
  "weight": 10,
  "scoring_type": "pass_fail",
  "mandatory": true,
  "source_ref": "RFP section 3.2"
}
```

Manual criteria sets and extractor output share this shape.

---

## Domain profiles (v1 scope)

| Profile | v1 | Notes |
| --- | --- | --- |
| **Tender** | Yes | Matrix extraction, pass/fail, redlines, Serper for bidder claims |
| **Education** | Yes | Uploaded rubric, scale or bands, constructive feedback tone |
| **Scientific** | Yes | Port existing checklist behavior under new schema |
| **Software** | Later | Needs repo ingestion + CI tools |

---

## Repository strategy

- **Implement in `checklist_reviewer_toolkit`** — reuse engine, PDF pipeline, agents, writers.
- **`reviewer-pipeline`** — planning docs (`idea.md`, this `plan.md`).
- Fork or rename once the generalized platform is stable.

---

## Implementation task list

### Phase 1 — Strip and generalize backend

- [ ] Remove human verification module (routes, services, templates)
- [ ] Remove process designer UI and related frontend assets
- [ ] Introduce `config/` layout: profiles, pipelines, providers, search
- [ ] Load pipeline from YAML at run start (replace UI-driven process definitions)
- [ ] Rename internally: paper → artifact, question → criterion, checklist → criteria_set
- [ ] Unified `criteria.json` schema with backward compatibility for old checklists

### Phase 2 — Core pipeline components

- [ ] `document_loader` — generalize existing paper loader
- [ ] `criteria_extractor` — RFP/rubric → criteria set (new)
- [ ] `section_mapper` — criterion-to-section mapping (new)
- [ ] `criterion_evaluator` — generalize question_reviewer; pluggable scoring + personas
- [ ] `feedback_synthesizer` — merge persona outputs into final advice (new)
- [ ] `report_writer` — keep JSON/PDF writers; domain-specific templates

### Phase 3 — Serper tool

- [ ] `search_tool` agent tool wrapping Serper API
- [ ] `config/search.yaml` + env-based API key
- [ ] Persist `search_log.json` per run
- [ ] Wire into evaluator when `use_search: true`

### Phase 4 — API layer

- [ ] `POST /reviews` — create run (pipeline id + uploads)
- [ ] `GET /reviews/{id}` — status + progress
- [ ] `GET /reviews/{id}/report` — structured results + download links
- [ ] `GET /pipelines` — list available pipelines from config manifest
- [ ] Background job runner for long reviews (existing task manager adapted)

### Phase 5 — New minimal frontend

- [ ] Pipeline picker (from `/pipelines`)
- [ ] Upload form (artifact + optional criteria source)
- [ ] Run progress view
- [ ] Report view: scorecard, evidence, advice, exports
- [ ] Delete or bypass old Flask templates

### Phase 6 — Profiles and polish

- [ ] `tender.yaml` profile + `tender_full.yaml` pipeline
- [ ] `education.yaml` profile + `education_rubric.yaml` pipeline
- [ ] `scientific.yaml` profile — migrate default checklist flow
- [ ] CLI: `review run --pipeline tender_full --artifact draft.pdf --rfp rfp.pdf`
- [ ] Documentation: config reference, example runs

---

## Run artifacts (per review)

```
runs/{run_id}/
├── config_snapshot.yaml    # pipeline + profile used
├── artifact/               # ingested markdown + metadata
├── criteria.json
├── mapping.json            # criterion → sections
├── evaluations.json        # per-criterion scores + evidence
├── search_log.json         # Serper queries + results (if used)
├── synthesis.json          # final narrative + redlines
├── report.pdf
└── token_usage.json
```

---

## How it is used in the end

| User | Workflow | Outcome |
| --- | --- | --- |
| **Bid team** | Select `tender_full`, upload RFP + draft, wait, download report | Compliance scorecard, gaps, redlines before submission |
| **Lecturer** | Select `education_rubric`, upload rubric + essay batch (CLI or API) | Consistent per-rubric feedback for every student |
| **Research lab** | Select `scientific_checklist`, upload manuscript | Reproducibility / FAIR checklist report with citations |
| **Integrations** | Call REST API or CLI from LMS, CI, or internal portal | Same engine, no UI required |

The tool is an **automated first-pass reviewer**: fast, consistent, evidence-linked, configurable entirely by developers/ops via repo config — not by end users in a UI.

---

## Risks and limits

- **No human gate** — high-stakes use (final grades, binding bid decisions) must be a deliberate choice; document that outputs are agent-generated.
- **Criteria extraction** — RFP/rubric parsing errors propagate; validate extractor output in CI with fixture documents.
- **Search quality** — Serper augments but does not guarantee correctness; log all queries for traceability.
- **Software profile** — out of v1; needs different ingestion than PDF-centric pipeline.

---

## Success criteria for v1

1. Three profiles runnable via config only (tender, education, scientific).
2. New UI completes upload → run → report without touching backend settings.
3. Human verification and process designer fully removed.
4. Serper usable in at least the tender pipeline for external claim checks.
5. Every score in the report links to artifact evidence or search log entry.

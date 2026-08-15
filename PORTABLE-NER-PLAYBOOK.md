# Portable Playbook — Session Notes

> **What this is:** a record of what was done in one working session on an LLM-based NER service,
> rewritten so it is **reusable on a different project**.
>
> **How to use it:** Part 1 tells you what happened. Parts 2–6 are the transferable parts — the
> method, the design patterns, the checklists, and the document templates. Part 7 lists what is
> project-specific and must NOT be copied blindly.
>
> Source project: a Named Entity Recognition service that converts free-text product searches into
> a structured 17-type entity dictionary, deployed as an Azure ML managed online endpoint, using a
> **fine-tuned** GPT-4.1-mini plus ~2,600 lines of deterministic post-processing rules.

---

## PART 1 — WHAT HAPPENED IN THIS SESSION

### 1.1 Chronology

| # | Ask | What was done | Output |
|---|---|---|---|
| 1 | "What did we discuss recently?" | Checked persistent memory and MCP memory — both empty. Reported honestly that no transcript existed, then reconstructed recent topics from the project's `CLAUDE.md`. | Short bullet summary |
| 2 | "Did we discuss an Elasticsearch-retrieval NER architecture? Give me an approach without fine-tuning." | Read the actual codebase before answering: entry point, orchestrator, dependency data files, fuzzy-matching call sites. Discovered a ~90K-term gazetteer already loaded at runtime but used only *after* the model. Proposed a retrieval-first architecture with 4 alternatives ranked. | Inline design answer |
| 3 | "Write it as a .md with neat diagrams — one full, one simple. Include current approach, deviation, current limitations, and new limitations." | Verified two framing-critical facts first (model is **fine-tuned**, not prompted; Elasticsearch **already exists** in the org's training notebooks). Wrote a full design doc with 7 Mermaid diagrams. | `KT learning/13-elasticsearch-retrieval-approach.md` |
| 4 | "Summarize goals, what we solved, constraints, and architecture into one reference." | Consolidated verified code facts + operational knowledge + the new proposal into a master reference. | `KT learning/14-project-reference.md` |
| 5 | "Summarize the session so I can reuse it elsewhere." | This file. | `PORTABLE-NER-PLAYBOOK.md` |

### 1.2 The one correction worth remembering

I initially described the system as "essentially zero-shot prompting" because the system prompt was
a single generic sentence. Reading further showed the model was **fine-tuned** — the prompt was
short *because* the behaviour lived in the weights.

**Transferable lesson:** a short/generic system prompt in a production LLM service is a **signal to
check for fine-tuning**, not evidence of a weak prompt. Grep for `finetun`, `fine-tun`,
`training data`, `retrain` before characterising any LLM architecture.

---

## PART 2 — THE METHOD (most reusable part)

### 2.1 Ground every claim in the code before designing

The design quality came almost entirely from ~8 cheap read-only commands run **before** writing
anything. In order:

```bash
# 1. Shape of the repo
ls; ls <runtime_dir>; ls <data_dir>

# 2. Size of each runtime file — tells you where the complexity actually is
wc -l <runtime_dir>/*.py

# 3. What's inside the reference data (types, counts) — do NOT guess
python -c "import json; d=json.load(open('<gazetteer>.json')); [print(k, len(v), str(v)[:100]) for k,v in d.items()]"

# 4. Function inventory of each file
grep -n "^def \|^    def " <file>.py

# 5. Where the LLM is actually called, and with what
grep -rn "chat.completions\|prompt\|PROMPT" <runtime_dir>/*.py

# 6. Is the model fine-tuned?  (the question people forget to ask)
grep -rin "finetun\|fine-tun\|training data\|retrain" <runtime_dir> <docs_dir>

# 7. What infrastructure already exists but isn't in the serving path?
grep -rl "Elasticsearch\|redis\|kafka\|vector" <notebooks_dir>

# 8. Existing docs — read the index, not every file
ls <docs_dir>
```

**Why this order:** each step narrows the next. Step 3 is the highest-leverage one — knowing that
`APPLICATION` had 22,475 values and `BRAND` had 64 dictated which entity types go to lexical
matching and which need embeddings. That decision cannot be made from intuition.

### 2.2 Look for assets already present but underused

The strongest finding of the session: **a 90K-term dictionary was already loaded into memory at
runtime, but only used after the model as a fuzzy validator.** The whole proposal became "invert
the order" rather than "build something new."

Ask on any project:
- What data is already loaded/available at runtime that the current design under-uses?
- What infrastructure does the org already pay for that isn't in the serving path?
- What is being *learned* that could instead be *looked up*?

### 2.3 Separate "data problem" from "code problem" early

The two bugs in this project looked like model errors. They were **data errors** — an entry missing
from a source table because of a near-miss key (`BKB009` vs `BK009`), causing a list-difference
step to silently fail.

**Diagnostic question:** *If I could edit one row in a database, would this bug disappear?*
If yes, it is a data problem, and the fix should not require retraining, rebuilding, or
redeploying. If your architecture forces a redeploy for a data fix, that is an architectural
defect worth naming.

### 2.4 State limitations of your own proposal

Every design doc written here has a **"limitations after adopting this"** section that is as long
as the "current limitations" section. This is what makes a proposal credible rather than a pitch.
For each new limitation, give the mitigation in the same row.

### 2.5 Never propose a big-bang migration

Every proposal ended with a phased plan whose **Phase 1 touches nothing in the serving path** (an
offline index build) and whose **Phase 2 is shadow mode** (run both, log both, compare). Name the
exit criteria for the phase where real traffic switches.

### 2.6 Name the blocker honestly

The proposal is blocked on a **labelled golden set of real queries**. The project had 650K
synthetic training queries — which are *not* a valid evaluation set for comparing against the model
trained on them. Saying this plainly is more useful than a plan that quietly assumes evaluation
data exists.

---

## PART 3 — TRANSFERABLE ARCHITECTURE PATTERN: RETRIEVAL-FIRST EXTRACTION

Applicable to any **entity extraction / classification / tagging** service currently built on a
fine-tuned or heavily-prompted LLM over a **known, finite catalogue** (products, SKUs, drugs,
parts, locations, skills, ICD codes…).

### 3.1 The core inversion

```
BEFORE:  query → LLM (knows everything) → rules repair the output
AFTER:   query → retrieval over catalogue → LLM only explains what retrieval couldn't
```

### 3.2 Layered cascade

| Layer | Handles | Mechanism | Pick this when |
|---|---|---|---|
| 0 | exact identifiers | keyword/`term` lookup | the input is an ID or a full catalogue name |
| 1 | closed-set entities | lexical search + fuzziness + synonym graph | identity matters more than meaning (brands, SKUs, codes) |
| 2 | open-set entities | kNN over embeddings (off-the-shelf model) | users phrase it freely; no literal string will match |
| 3 | everything left over | stock LLM + **retrieved** few-shot + constrained vocabulary | genuine language understanding / implicit entities |
| 4 | deterministic business logic | plain code | unit conversion, scope, dedup — never put this in a model |

**Rule of thumb for splitting Layer 1 vs Layer 2:** count the distinct values per type. Small,
enumerable, identity-like → Layer 1. Large, free-text, paraphrasable → Layer 2.

### 3.3 Index document design (the part that does the work)

Store **one document per surface form**, not one per concept, and **decompose the identifier into
separate fields**:

```jsonc
{
  "surface":      "zytel 101f bk009",   // what the user might type
  "canonical_id": "SPT:ZYT101F_BK009",  // what downstream systems use
  "entity_type":  "GRADE",
  "brand":        "zytel",              // ← decomposed
  "base_grade":   "101f",               // ← decomposed
  "color_code":   "bk009",              // ← decomposed: THE key design move
  "in_scope_internal": true,            // ← state as a FIELD, not a list membership
  "in_scope_external": false,
  "source":       "warehouse:SPT",
  "embedding":    [ /* only for open types */ ]
}
```

**Two design moves that generalise:**

1. **Decompose composite identifiers into fields.** Any near-miss on one component then becomes a
   *scored partial match* instead of a *total miss*. This alone fixes an entire class of bug.
2. **Encode state as a boolean field on the canonical record, never as membership in a list that
   must be diffed against another list.** List-difference logic fails silently; a field does not.

### 3.4 Span decoding

Enumerate n-gram spans (n = 1..6), query all of them in one batched multi-search, then resolve
overlaps with **max-weight non-overlapping span selection** (interval DP), with longest-match and
type-priority as tiebreakers. Do not take greedy first-match.

### 3.5 Dynamic few-shot > static few-shot > fine-tuning

When the catalogue is large and changes often:

- **Static few-shot** fails: you cannot fit 90K values or 17 types in a prompt, and every business
  change becomes a prompt edit.
- **Fine-tuning** fails on *change cost*: a new catalogue entry = retrain + redeploy.
- **Dynamic few-shot** works: retrieve the k nearest **past labelled examples** from an example
  index at request time, plus the ~30 catalogue candidates that actually matched this query, and
  inject both. A mislabel is then fixed by **inserting one document**.

### 3.6 Constrain the output

Require every emitted value to resolve to a `canonical_id` from the retrieved candidate set.
Reject anything else. This makes hallucinated entities **structurally impossible** and eliminates
the need for downstream fuzzy repair.

> **Tell-tale sign you need this:** the codebase contains fuzzy string matching applied to the
> *model's own output* (e.g. `fuzz.token_sort_ratio(model_output, catalogue) > 80`). That code
> exists only because the model was allowed to invent values. Constrain the input side instead.

### 3.7 Emit provenance

Every extracted entity should carry `canonical_id`, `score`, and which layer produced it. Debugging
a two-system pipeline with provenance is strictly easier than debugging a one-system pipeline
without it.

### 3.8 Honest trade-offs of this pattern (carry these forward)

| New cost | Mitigation |
|---|---|
| Search engine becomes a runtime dependency | cache the catalogue in-process at startup; fall back to the in-memory dictionary |
| Extra network round-trip per request | batch all spans into one multi-search; co-locate; offset by skipping the LLM on most queries |
| Retrieval cannot infer implicit entities | keep the LLM fallback layer — do not delete it |
| Fuzzy matching adds false positives | per-type score thresholds; require exact match on the identity field |
| Index drifts from source of truth | nightly full re-index into a new index + alias swap; checksum/row-count alerting |
| Embedding model becomes a pinned dependency | store `embedding_model` per doc; re-embed offline behind an alias |
| Two systems to debug | provenance fields (§3.7) |
| Rules do not disappear | intentional — genuine business logic belongs in code |

---

## PART 4 — TRANSFERABLE OPS CHECKLISTS

### 4.1 Managed-endpoint deployment (Azure ML flavour, but the shape generalises)

- A deploy is typically **three independently versioned things**: code asset, model/data artefact,
  environment image. **Know which of the three your change actually touches.**
- **A data-only change should never require an image rebuild.** Bump the data artefact, reuse the
  last known-good environment version. This turns a 20-minute risky build into a fast redeploy.
- **Runtime secrets must be in the deployed code asset.** Check the ignore files: a `.env` that is
  correctly `.gitignore`d must NOT also be in the deployment ignore file, or the container crashes
  at import with a generic "container has crashed" message.
- **Private-network workspaces break default image builds.** If the build compute is unset, builds
  run on shared/serverless compute that cannot reach private storage → silent hangs and timeouts.
  Fix: dedicated in-network build compute, or avoid rebuilding.
- **Pin the base image.** `:latest` is a moving target under your feet.

### 4.2 Dependency pinning principle

> **Pin only your application libraries. Never pin what the platform SDK controls.**

In this project, pinning `pydantic` and an old `inference-schema` against `azureml-defaults==1.62.0`
produced `ResolutionImpossible` — after a ~20-minute cloud build had already been spent.

**Always validate the FULL environment file locally before any cloud build:**

```bash
pip install --dry-run azureml-defaults==1.62.0 "inference-schema[numpy-support]~=1.8" <your pins>
```

Validating only `requirements.txt` misses these conflicts, because it omits the platform SDK that
actually constrains the tree.

Also: audit for **unused pinned libraries**. Seven were removed here (`spello`, `nltk`, `sympy`,
`contractions`, `regex`, `joblib`, `python-Levenshtein`) simply by grepping for imports. Every
unused pin is a future conflict for free.

### 4.3 Auth and data-access gotchas

- Notebooks using a CLI-based credential (rather than a default chained credential) hold tokens
  that expire in hours — expect periodic re-login.
- Warehouse connections using browser-based SSO **cannot run headless or in CI**, and often need
  VPN. Design any "nightly sync" around this constraint from the start, not after.
- **If reference data and secrets are not in version control, a fresh checkout cannot start the
  service.** Document exactly which files are missing and where they come from. Do this before you
  need it.

### 4.4 Watch-outs when moving reference data by hand

- Large content can be silently truncated (~32 KB clipboard limits were hit here).
- Multi-sheet spreadsheets lose sheets when round-tripped carelessly — verify sheet count after any
  copy.
- Non-UTF8 files (latin-1 regex/pattern files) need explicit encoding on read.

---

## PART 5 — DOCUMENT TEMPLATES THAT WORKED

### 5.1 Architecture-proposal doc

```
0.  TL;DR — a before/after table, ~8 rows. Lead with cost-of-change, not tech.
1.  Current approach
    1.1 Simple diagram
    1.2 Where the knowledge actually lives (weights vs files vs code) ← most illuminating
    1.3 Current limitations — numbered, each with evidence (file:line)
2.  Proposed approach
    2.1 ONE simple diagram (must fit in a screenshot / a slide)
    2.2 ONE full diagram (offline pipeline + runtime layers + data stores)
    2.3 Sequence diagram for a single request
3.  The deviation — table of what changes vs what is deliberately reused
    + explicit "what we are NOT changing" list
4.  Detailed design — index/schema sketch, per-type routing, worked examples on REAL open bugs
5.  Sub-decisions with rationale
6.  Limitations AFTER the change — numbered, each with a mitigation
7.  Migration — phased, Phase 1 = zero serving-path risk, exit criteria named
8.  Optional variant / fallback design
9.  Open questions that block the build
10. Related docs
```

**The two highest-value sections are 1.2 and 6.** Section 1.2 ("where does the knowledge live")
reframes the whole problem. Section 6 is what makes reviewers trust the rest.

### 5.2 Master-reference doc

```
Part 1  Core goals — business goal + engineering goals table + design philosophy
Part 2  Architecture — flow diagram, file inventory with line counts, data inventory
        with real counts, model details, deployment topology, environments
Part 3  Constraints — hard technical (numbered C1..Cn), operational, self-imposed
Part 4  What was investigated and solved — per item: symptom → root cause → fix → key property
Part 5  Known limitations — numbered, traceable to a file
Part 6  Open items — split Immediate / Hardening / Strategic
Part 7  Quick reference — verification snippet, request/response shape, pre-deploy checklist,
        key identifiers
Part 8  Document map
```

**Why this shape works:** Parts 1–3 orient a newcomer, Part 4 is the institutional memory that
otherwise evaporates, Part 7 is what an on-call engineer actually opens at 2am.

### 5.3 Diagram conventions used

- **Mermaid**, checked into the repo — diffable, no binary assets, renders in most viewers.
- Always ship **two** diagrams: one that fits on a slide, one that is complete. They serve
  different audiences and neither substitutes for the other.
- Use `subgraph` to separate **offline/build-time** from **runtime**. Most architecture confusion
  is really confusion about which of the two you are looking at.
- Use dotted arrows (`-.->`)  for "reads from / consults", solid for main flow.
- Put a **failure-mode comparison diagram** (before vs after) in any proposal — it communicates
  cost-of-change faster than prose.

---

## PART 6 — REUSABLE PROMPT / QUESTION SET

When starting on a comparable system, get these answered before designing anything:

**About the model**
1. Is the model fine-tuned, prompted, or both? What is the actual system prompt?
2. What was it trained on, and does a *real* labelled evaluation set exist — separate from the
   training data?
3. What does a mistake cost to fix today, in wall-clock time and in steps?

**About the data**
4. What reference data is loaded at runtime, and how is each file used — before or after the model?
5. What is the source of truth, and how does data get from it into the serving path?
6. Which types are closed catalogues and which are open free text? Get the **counts**.

**About the failures**
7. Take the last 3 bugs: were they data problems or code problems?
8. Is there any place where correctness depends on a **list difference** between two collections?
   (Near-miss keys make these fail silently.)
9. Is there fuzzy matching applied to the model's *own output*? Why does it need to exist?

**About the operations**
10. What are the independently versioned deployment artefacts, and which does a data-only fix
    touch?
11. What breaks a fresh checkout?
12. What infrastructure does the org already run that is not in the serving path?

---

## PART 7 — WHAT NOT TO COPY

These were specific to the source project — re-derive, do not assume:

- The 17-type entity taxonomy and its per-type value counts.
- The specific dependency pins (`azureml-defaults==1.62.0`, `inference-schema~=1.8`, `numpy=1.24.4`)
  — the *principle* in §4.2 transfers; the *versions* do not.
- Azure ML / Snowflake / Elastic Cloud as the stack. The layered-cascade pattern is
  engine-agnostic: the search layer could be OpenSearch, pgvector, Vespa, Typesense, or an
  in-process FAISS index.
- The `base_grade` / `color_code` decomposition — the *idea* of decomposing composite identifiers
  transfers; the specific fields are domain-specific.
- Embedding dimension 1536 / `text-embedding-3-small` — pick per project.
- n-gram span width of 1..6 — tune to your typical input length.
- Any endpoint names, resource groups, workspace names, or account identifiers.

---

## PART 8 — ONE-PARAGRAPH SUMMARY

On an LLM-based entity-extraction service, I read the code before designing, and found that a large
reference dictionary was already loaded at runtime but consulted only *after* the model, as a fuzzy
repair step. That inverted the problem: instead of a fine-tuned model that must be retrained for
every catalogue change, use retrieval over the catalogue as the primary extractor, with a stock LLM
handling only the residual text, constrained to emit values that exist. Two production bugs traced
to a silent list-difference failure on a near-miss composite key, which the retrieval design
eliminates structurally by decomposing the identifier into fields and storing scope as a boolean on
the record. The proposal was written up with paired simple/full diagrams, an explicit deviation
table, symmetric limitation sections for the old and new designs, and a phased migration whose
first phase touches nothing in the serving path — and it is honestly blocked on the absence of a
labelled evaluation set, since the existing 650K synthetic training queries cannot fairly evaluate
the model trained on them.

# 7. Glossary — Plain English 📖

> Every term used in this code and KT, explained simply.

---

## Core concepts

| Term | Plain meaning |
|------|---------------|
| **NER** | "Named Entity Recognition" — finding the important *things* in a sentence and labeling them (this is what the whole project does). |
| **Entity** | One labeled thing extracted from the query, e.g. a GRADE, a POLYMER, a FEATURE. There are **17 types**. |
| **Query / search_query** | The raw text a user typed (e.g. "30% glass filled nylon 66"). |
| **GPT / LLM** | The AI language model that reads the query and extracts entities. Here it's a **fine-tuned GPT-4.1-mini** hosted on Azure. |
| **Fine-tuned** | An AI model that was further trained on Celanese-specific examples so it understands plastics/chemicals jargon. |
| **Pipeline** | A series of steps where the output of one becomes the input of the next (clean → AI → rules). |
| **Pre-processing** | Cleaning/tidying the text *before* the AI sees it. |
| **Post-processing** | Fixing/checking the AI's output *after* it runs. |
| **Fast-path** | A shortcut that answers common queries with simple rules, skipping the AI to save time/money. |

---

## The 17 entity types

| Entity | What it captures |
|--------|------------------|
| **GRADE** | A specific Celanese product grade/code. |
| **APPLICATION** | What it's used for (e.g. "connector", "medical bed"). |
| **BRAND** | A Celanese brand name (e.g. Celanex, Hostaform). |
| **POLYMER** | The base plastic type (e.g. nylon 66, PBT, PPS). |
| **PROPERTY** | A measurable property + value/range/unit (e.g. tensile strength 100 MPa). *Nested.* |
| **FILLER** | Reinforcement material + load % (e.g. glass fiber 30%). *Nested.* |
| **FEATURE** | A characteristic (e.g. UV stabilized, flame retardant, recycled content). |
| **PROCESSING** | How it's processed (e.g. injection molding). |
| **DELIVERY_FORM** | Physical form (e.g. pellets, powder). |
| **COMPETITOR_GRADE** | A competitor's product code (used to find a Celanese equivalent). |
| **AUTO_CERT** | Automotive certifications per car-maker (OEM). *Nested.* |
| **RAILWAY_CERT** | Railway standards/hazard levels. *Nested.* |
| **WATER_CERT** | Water-contact certifications + temperature. *Nested.* |
| **NSF_CERT** | NSF (food/water safety) certifications. |
| **INDUSTRY** | Target industry (e.g. automotive, electronics). |
| **REGION** | Geographic region. |
| **MATERIAL_ID** | An internal SAP material number. |

---

## Material / chemistry terms (so the code makes sense)

| Term | Plain meaning |
|------|---------------|
| **Grade** | A specific recipe/version of a plastic product. |
| **Polymer** | The base plastic (nylon, PBT, etc.). |
| **Filler** | Stuff added to make plastic stronger/cheaper (glass fiber, etc.). |
| **GF / MF / GB / CF** | Glass Fiber / Mineral Filler / Glass Beads / Carbon Fiber. |
| **PA66 / PA6** | Types of nylon. |
| **UL94 / V-0 / V-1 / V-2 / HB** | Flammability (fire-safety) ratings. V-0 is the best. |
| **CTI** | Comparative Tracking Index — an electrical-safety property. |
| **HAI / HWI / HVAR / HVTR** | Various UL electrical-safety test ratings. |
| **PLC** | Performance Level Category — UL ratings are grouped into categories (PLC 0–4). The code converts raw numbers into these. |
| **eco-r / eco-b / eco-c** | Sustainability variants → Recycled content / Bio-content / Carbon capture. |
| **OEM** | "Original Equipment Manufacturer" — here, a car maker (Ford, etc.) for automotive certs. |
| **SAP id** | An internal company material number (8 digits, starts with 2 or 5). |

---

## Technical / code terms

| Term | Plain meaning |
|------|---------------|
| **Azure ML online endpoint** | A live web service hosted on Microsoft Azure that this code runs as. |
| **`init()`** | Function Azure calls once at startup to load data. |
| **`run()`** | Function Azure calls for every request. |
| **DEPENDENCIES** | A big dictionary holding all reference data, passed around the code (the "toolbox"). |
| **.env file** | A file holding secret credentials (API keys) — not committed to the repo. |
| **NPROD / PROD** | Non-Production (testing) and Production (live) environments/deployments. |
| **Fallback** | If the main AI deployment fails, automatically try the backup one. |
| **temperature** | AI randomness setting. `0.01` = almost no randomness → consistent answers. |
| **seed** | A fixed number (`12`) that makes the AI repeat the same output for the same input. |
| **Deterministic** | Same input always gives the same output (important for search consistency). |
| **Fuzzy matching** | Comparing strings by *similarity %* rather than exact equality (library: `thefuzz`). Used to reclassify grades and match units. |
| **Normalize** | Convert text to a standard form (lowercase, strip symbols) so it can be compared. |
| **Schema** | The expected structure/shape of the output data. |
| **Out-of-scope (OOS)** | Entities that exist but should be hidden from this user (based on internal/external). |
| **Deduplicate** | Remove repeated items from a list. |
| **eval()** | Python function that turns a text string into a real Python object (used to parse the AI's reply). |
| **regex** | "Regular expression" — a pattern-matching mini-language for finding text. |

---

## Quick reference: who does what

```
   score.py            → the door (init loads data, run handles requests)
   pre_processing.py   → cleans the query
   ner_helper.py       → the brain (orchestrates, calls AI, applies rules)
   post_processing.py  → validates, converts units, hides out-of-scope
   Azure OpenAI        → the AI that actually understands the query
   DEPENDENCIES        → the shared toolbox of reference data
```

➡️ Next: [`08-how-to-test-locally.md`](08-how-to-test-locally.md) — about those lines 350–354.

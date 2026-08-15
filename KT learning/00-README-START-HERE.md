# 📚 KT (Knowledge Transfer) — Celanese NER Service

> A complete, beginner-friendly walkthrough of the code in `flat-repo-ner/onlinescoring/`.
> Read the files in order. Every concept is explained with diagrams and plain-English analogies.

---

## 🎯 What is this project in one sentence?

> A user types a messy search like **"30% glass filled UV resistant nylon 66 with UL94V0"**,
> and this service turns it into a **clean, structured list of facts** that a computer can use
> to recommend the right plastic/chemical material.

**NER** = **N**amed **E**ntity **R**ecognition = "find the important *things* (entities) in a sentence and label them."

---

## 📖 Reading order

| # | File | What you'll learn | Level |
|---|------|-------------------|-------|
| 1 | [`01-explain-like-im-5.md`](01-explain-like-im-5.md) | The whole idea using everyday analogies | 🟢 Layman |
| 2 | [`02-big-picture-architecture.md`](02-big-picture-architecture.md) | How the 4 files fit together (diagrams) | 🟢 Beginner |
| 3 | [`03-step-by-step-flow.md`](03-step-by-step-flow.md) | Exactly what happens on one request | 🟡 Intermediate |
| 4 | [`04-file-by-file.md`](04-file-by-file.md) | Deep dive into each file & function | 🟡 Intermediate |
| 5 | [`05-worked-example.md`](05-worked-example.md) | Follow ONE query from start to finish | 🟡 Intermediate |
| 6 | [`06-all-diagrams.md`](06-all-diagrams.md) | Every diagram in one place (cheat sheet) | 🟢 All |
| 7 | [`07-glossary.md`](07-glossary.md) | Plain-English meaning of every term | 🟢 All |
| 8 | [`08-how-to-test-locally.md`](08-how-to-test-locally.md) | What lines 350–354 do & what's needed to run | 🟡 Intermediate |
| 9 | [`09-missing-files.md`](09-missing-files.md) | Exact list of missing files & where they go | 🟢 All |
| 11 | [`11-rulebased-vs-llm.md`](11-rulebased-vs-llm.md) | Which labels are rule-based vs sent to the LLM | 🟡 Intermediate |
| 12 | [`12-bug-217995-zytel-casestudy.md`](12-bug-217995-zytel-casestudy.md) | Full case study: Zytel/Celanyl out-of-scope bug + session log | 🟡 Intermediate |
| 13 | [`13-how-ner-prediction-works.md`](13-how-ner-prediction-works.md) | How prediction works (rules+LLM), data/DBs, fine-tuning, ambiguity gaps & failure modes | 🟡 Intermediate |
| 15 | [`15-retrieval-based-ner-approach.md`](15-retrieval-based-ner-approach.md) | **Proposal** — a retrieval-grounded design with no fine-tuning | 🔵 Design |
| 16 | [`16-entity-by-entity-resolution.md`](16-entity-by-entity-resolution.md) | **Every entity**: rule or LLM, which rule, which file, 10 examples each | 🔴 Deep |
| 17 | [`17-dependencies-files-explained.md`](17-dependencies-files-explained.md) | **Every dependency file**: schema, who reads it, what breaks without it | 🔴 Deep |
| 🔀 | [`nerflow.md`](nerflow.md) | **20 worked queries** traced end to end — the fastest way to see the whole machine | 🟡 Intermediate |
| 🖼️ | [`images/README-images.md`](images/README-images.md) | **Diagram gallery** — 11 SVG diagrams (architecture, UML, domain) | 🟢 All |

### Tools in this folder

| Tool | What it does |
|---|---|
| [`trace_query.py`](trace_query.py) | `python trace_query.py "your query"` — shows which route a query takes and why. No endpoint or API key needed |
| [`make_dependencies_sample.py`](make_dependencies_sample.py) | Rebuilds [`dependencies-sample/`](dependencies-sample/) — every data file in miniature (44 KB instead of 12 MB) |

> ### 📌 Current version — 11-Aug-2026
> `API_VERSION v5.9.2` · `MODEL_VERSION GPT-4-1-mini-15_07_26` · **19 entities**
> (the original 17 plus **`MEDICAL_CERT`** and **`CHEMICAL_RESISTANCE`**).
>
> Documents 1–13 were written against the 17-entity version and still describe the core pipeline
> accurately. For the two new entities and the rules that came with them, read
> [`16-…`](16-entity-by-entity-resolution.md) §18.

---

## 🗺️ The 30-second mental model

```
   "messy human words"                          "clean computer facts"
   ───────────────────                          ─────────────────────
   "30% glass filled        ┌──────────────┐    GRADE:    nylon 66
    UV resistant     ─────► │  NER SERVICE │ ─► FILLER:   glass fiber 30%
    nylon 66 UL94V0"        └──────────────┘    FEATURE:  UV stabilized
                                                 PROPERTY: flammability V-0
```

The service is built like a **3-station assembly line**:

```
  STATION 1            STATION 2              STATION 3
  CLEAN  ───────────►  UNDERSTAND  ─────────► FIX & CHECK
  (pre_processing)     (GPT AI model)         (post_processing + rules)
```

---

## 💡 How to view the diagrams

The diagrams use two formats:
- **Mermaid** (```` ```mermaid ````) — renders automatically in **GitHub**, **VS Code** (with the
  *Markdown Preview Mermaid* extension), Obsidian, and many markdown viewers.
- **ASCII art** — works *everywhere*, even Notepad.

If a Mermaid diagram shows as plain text, install a Mermaid-enabled previewer — or just read the ASCII version right beside it.

---

## 📂 What code this documents

```
flat-repo-ner/
└── onlinescoring/
    ├── score.py            ← the entry point (Azure ML calls this)
    ├── pre_processing.py   ← STATION 1: clean the text
    ├── ner_helper.py       ← the orchestrator (calls AI + rules)
    └── post_processing.py  ← STATION 3: validate & convert
```

➡️ **Start with [`01-explain-like-im-5.md`](01-explain-like-im-5.md).**

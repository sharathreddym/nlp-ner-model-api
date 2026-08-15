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

| # | Page | What you'll learn | Level |
|---|------|-------------------|-------|
| 1 | [`01-Explain-Like-Im-5`](./NER-Knowledge-Transfer/01-Explain-Like-Im-5.md) | The whole idea using everyday analogies | 🟢 Layman |
| 2 | [`02-Big-Picture-Architecture`](./NER-Knowledge-Transfer/02-Big-Picture-Architecture.md) | How the 4 files fit together (diagrams) | 🟢 Beginner |
| 3 | [`03-Step-By-Step-Flow`](./NER-Knowledge-Transfer/03-Step-By-Step-Flow.md) | Exactly what happens on one request | 🟡 Intermediate |
| 4 | [`04-File-By-File`](./NER-Knowledge-Transfer/04-File-By-File.md) | Deep dive into each file & function | 🟡 Intermediate |
| 5 | [`05-Worked-Example`](./NER-Knowledge-Transfer/05-Worked-Example.md) | Follow ONE query from start to finish | 🟡 Intermediate |
| 6 | [`06-All-Diagrams`](./NER-Knowledge-Transfer/06-All-Diagrams.md) | Every diagram in one place (cheat sheet) | 🟢 All |
| 7 | [`07-Glossary`](./NER-Knowledge-Transfer/07-Glossary.md) | Plain-English meaning of every term | 🟢 All |
| 8 | [`08-How-To-Test-Locally`](./NER-Knowledge-Transfer/08-How-To-Test-Locally.md) | What lines 350–354 do & what's needed to run | 🟡 Intermediate |
| 9 | [`09-Missing-Files`](./NER-Knowledge-Transfer/09-Missing-Files.md) | Exact list of missing files & where they go | 🟢 All |
| 11 | [`11-Rule-Based-vs-LLM`](./NER-Knowledge-Transfer/11-Rule-Based-vs-LLM.md) | Which labels are rule-based vs sent to the LLM | 🟡 Intermediate |
| 12 | [`12-Bug-217995-Zytel-Case-Study`](./NER-Knowledge-Transfer/12-Bug-217995-Zytel-Case-Study.md) | Full case study: Zytel/Celanyl out-of-scope bug + session log | 🟡 Intermediate |
| 13 | [`13-How-NER-Prediction-Works`](./NER-Knowledge-Transfer/13-How-NER-Prediction-Works.md) | How prediction works (rules+LLM), data/DBs, fine-tuning, ambiguity gaps & failure modes | 🟡 Intermediate |
| 🖼️ | [`Diagram-Gallery`](./NER-Knowledge-Transfer/Diagram-Gallery.md) | **Diagram gallery** — all 12 image diagrams (architecture, UML, domain) | 🟢 All |

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

The diagrams come in three formats, all of which work inside this wiki:
- **Mermaid** (`::: mermaid` blocks) — rendered natively by Azure DevOps Wiki.
- **PNG images** — the hand-drawn architecture/UML/domain diagrams, stored as wiki
  attachments. See [`Diagram-Gallery`](./NER-Knowledge-Transfer/Diagram-Gallery.md).
- **ASCII art** — works *everywhere*, even in a plain-text editor.

If a Mermaid block ever shows as plain text (older Azure DevOps Server versions), just read the
ASCII version right beside it — every Mermaid diagram in this KT has an ASCII twin.

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

➡️ **Start with [`01-Explain-Like-Im-5`](./NER-Knowledge-Transfer/01-Explain-Like-Im-5.md).**

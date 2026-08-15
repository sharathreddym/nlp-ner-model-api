# 1. Explain Like I'm 5 🍼

> No code here. Just the *idea*, using everyday things you already understand.

---

## The problem we are solving

Imagine you run a **giant plastics shop** with thousands of products.
Customers come in and say things in their *own* words:

- "I need that bendy nylon with glass in it that doesn't catch fire"
- "30% GF PA66 UV stable"
- "pa6-gf60-01"

All three customers might want a **similar product** — but they said it in completely different ways.
A computer can't search a product catalog with messy sentences. It needs **clean labels**.

So we need a smart helper that listens to the customer and fills out a **standard form**:

```
   ┌─────────────────────────────────────┐
   │           PRODUCT REQUEST FORM       │
   ├─────────────────────────────────────┤
   │ Material (GRADE):   nylon 66         │
   │ Filler:             glass fiber, 30% │
   │ Special feature:    UV resistant     │
   │ Fire rating:        V-0              │
   └─────────────────────────────────────┘
```

**This whole project is that smart helper.** It's called an **NER service**.

---

## The "smart receptionist" analogy 🧑‍💼

Think of the service as a **receptionist** at the plastics shop who is *very good at understanding customers*.

```
        Customer says something messy
                    │
                    ▼
        ┌───────────────────────┐
        │     RECEPTIONIST       │
        │  (our NER service)     │
        └───────────────────────┘
                    │
                    ▼
        Hands a neat, filled-out form
        to the warehouse computer
```

But the receptionist doesn't work alone. They have a **3-person team** behind the desk:

### 👨‍🔧 Person 1 — "The Cleaner" (`pre_processing.py`)

Customers write sloppily: extra symbols, weird spacing, `™`, `®`, `≥`, ALL CAPS, etc.

The Cleaner tidies the sentence first — like ironing a wrinkled shirt — so the next
person can read it easily.

```
  "PA66™  30%GF  ≥UV-stable"   ──Cleaner──►   "pa66 30 gf uv stable"
```

### 🧠 Person 2 — "The Genius" (the AI / GPT model)

This is a **very smart AI** (a fine-tuned version of GPT) that has studied *tons* of
Celanese product queries. You give it the cleaned sentence, and it says:

> "Ah, this person wants: a GRADE of pa66, a FILLER of glass fiber at 30%, and a FEATURE of UV stability."

The Genius is brilliant but occasionally makes small mistakes or uses the wrong wording.

### 📋 Person 3 — "The Inspector" (`post_processing.py` + rules)

The Inspector double-checks the Genius's work against the **company rulebook**:

- "We don't measure pressure in GPa here, convert it to MPa." ✅
- "This customer is *external*, so hide the products they're not allowed to see." ✅
- "The Genius wrote 'aramide' — the correct spelling is 'aramid'." ✅
- "A fire rating of '600 volts' should be written as category 'PLC 0'." ✅

The Inspector produces the **final, correct form**.

---

## The assembly line (the most important picture)

```
   CUSTOMER                                                    WAREHOUSE
   "PA66 30%GF        ┌─────────┐   ┌─────────┐   ┌──────────┐  COMPUTER
    UV stable"  ────► │ CLEANER │──►│ GENIUS  │──►│ INSPECTOR │ ───► clean
                      │ (clean  │   │  (AI    │   │ (rules &  │      form
                      │  text)  │   │ extract)│   │  checks)  │
                      └─────────┘   └─────────┘   └──────────┘
                       pre_         GPT model      post_
                       processing                  processing
```

That's the entire system. Everything else is detail.

---

## One clever shortcut ⚡

Sometimes the customer says something the receptionist **instantly recognizes** — like an
exact product code (`pa6-gf60-01`) or a barcode-like number.

In that case, the receptionist **skips the Genius entirely** (the AI is slow and costs money)
and fills the form immediately. This is called a **"fast-path."**

```
   Is the query an exact known product code or barcode?
                    │
         ┌──────────┴──────────┐
        YES                    NO
         │                      │
         ▼                      ▼
   Fill form NOW          Send to the AI Genius
   (skip the AI)          (normal path)
```

---

## Why not just use the AI for everything?

Good question! Two reasons:

1. **The AI isn't perfect.** It's great at *understanding language* but bad at *strict rules*
   (like unit conversions or company-specific spelling). Rules handle those perfectly.
2. **Fixing rules is cheap; retraining the AI is expensive.** If the AI makes a mistake,
   we just add a rule in the Inspector step instead of re-teaching the whole AI.

> 📌 The project README literally says: *"Avoid frequent finetuning if a NER issue can be fixed by a rule-based approach."*

That's why this is a **hybrid** system: **AI for understanding + rules for correctness.**

---

## What "internal" vs "external" means 🔐

Each request says whether the customer is an **internal** employee or an **external** customer.

- **Internal** people can see the *full* catalog.
- **External** people see a *restricted* catalog (some grades/brands are hidden = "out of scope").

The Inspector uses this to decide what to hide.

```
   Same query, different viewer:

   Internal user  ─► sees grades A, B, C, D
   External user  ─► sees grades A, B        (C and D are "out of scope")
```

---

✅ **You now understand the whole system at a high level.**
Next: [`02-big-picture-architecture.md`](02-big-picture-architecture.md) — the same idea, but mapped to the actual files.

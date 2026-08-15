# 16. Entity-by-Entity Resolution — how each entity is *actually* decided 🔬

> The concept-level answer to: **"for this entity, who decides — a rule or the model? which rule?
> which file? what domain knowledge is baked in?"**
>
> Everything below is traced from the code in `flat-repo-ner/onlinescoring/`. File and line
> references are given so you can open the exact rule.

---

## Version — updated after the 11-Aug-2026 commit

| | Value |
|---|---|
| `MODEL_VERSION` | `GPT-4-1-mini-15_07_26` |
| `API_VERSION` | `v5.9.2` |
| Entities | **19** — the 17 documented below, plus `MEDICAL_CERT` and `CHEMICAL_RESISTANCE` |

The 11-Aug commit brought the repo in line with the deployed service. **Both new entities are now
implemented in `onlinescoring/`**, backed by a new dependency file (`chemical_resistance.json`),
three new keys in `normalized_unique_values_for_grade_mapping.json`, and five new functions in
`post_processing.py` — see **§18**, which has been rewritten from traced code rather than
observed behaviour.

---

# PART A — the five things you need to understand first

Most of the confusion around this project comes from not knowing **which of five mechanisms** is
acting at any moment. Every entity value is produced by one or more of these:

| # | Mechanism | Where | What it does |
|---|---|---|---|
| **M1** | **Regex short-circuit** | `ner_helper.py` | Pattern matches the *whole query* → return immediately, LLM never called |
| **M2** | **Gazetteer exact / substring match** | `ner_helper.py` | Normalised query looked up in a list of known values → return immediately |
| **M3** | **The LLM** | `get_entities()` `ner_helper.py:499` | Fine-tuned GPT-4.1-mini reads the cleaned query and emits the whole 17-key dict |
| **M4** | **Post-LLM correction rules** | `ner_helper.py:1293-1885` | Reclassify, convert, rename, split and enrich whatever the LLM said |
| **M5** | **Scope / validation filters** | `post_processing.py` | Enforce the schema, then hide anything the user is not allowed to see |

**The mental model:** *M1 and M2 are the fast lanes. M3 is the default. M4 is where the business
knowledge lives. M5 is the gate at the exit.*

```
                    ┌──────────── M1/M2 hit? ──── yes ──► RETURN (no LLM)
 query ─► clean ────┤
                    └──── no ──► M3 (LLM) ──► M4 (rules) ──► M5 (scope) ──► RETURN
```

## A.1 The two vocabularies — and why there are two

This trips everyone up. There are **two different reference files** and they are not
interchangeable:

| File | Loaded as | Shape | Used for |
|---|---|---|---|
| `dependencies/unique_values_22_02_24.json` | `UNIQUE_VALUES` | human-readable values (`"celanex 2002-2"`, `"glass fiber"`) | the **fuzzy** matching in M4, and building the units list |
| `dependencies/normalized_unique_values_for_grade_mapping.json` | `NORMALIZED_UNIQUE_VALUES` | punctuation-stripped, lowercase (`"celanex20022"`) | the **exact** matching in M2 |

Loaded at `score.py:78-89`.

`NORMALIZED_UNIQUE_VALUES` holds 7 lists:

| Key | Size | Meaning |
|---|---|---|
| `GRADE` | 21,029 | every Celanese grade, normalised |
| `COMPETITOR_GRADE` | 56,871 | every competitor grade, normalised |
| `COMPETITOR_BRAND` | 875 | competitor brand names |
| `BRAND` | 64 | Celanese brands |
| `AUTO_CERT` | 998 | `[normalised_cert, oem]` pairs |
| `columnstoIgnore` | 1,022 | strings that look like grades but are not (`mf74`, `gf28`) |
| `columnsforSubstringCheck` | 4,142 | strings that must **only** match exactly, never as a substring |

## A.2 Normalisation — the single most important trick

`pre_processing.normalize_query()` (`pre_processing.py:208`) does two things:

1. drops **`GRADE_OFFSET_TERMS`** (`pre_processing.py:6`) — the 30-odd words users wrap around a
   grade name: *imds, tds, sds, alternative, offset, replacement, similar, instead, looking, want,
   show me, grade, material, competitor, spec…*
2. strips every non-alphanumeric character and lowercases

```
"looking for alternative to Celanex 2002-2"
        │  drop offset terms  →  "celanex 2002-2"
        │  strip punctuation  →  "celanex20022"
        └─────────────────────────► compared against NORMALIZED_UNIQUE_VALUES['GRADE']
```

**Why:** users type `PA6-GF30-01`, `pa6 gf30 01`, `PA6GF3001`. All three normalise to
`pa6gf3001`, so one list entry covers every spelling. This is what makes the fast paths work at
all.

## A.3 The guard conditions — why the fast path often does *not* fire

Before any grade lookup, `ner_helper.py:941-945` requires **all** of:

```python
not any(query in s for s in columnstoIgnore + columnsforSubstringCheck)   # or query == "ultra"
and not re.fullmatch(r'(\d+(?:gf|mf|gb|af)|(?:gf|mf|gb|af)\d+|gf|mf|gb|af)', query)
and not any(re.match(p, query) for p in non_grade_patterns)
and not re.match(r'^(pbt|pet){2}$', query)
and len(query) > 2
```

`non_grade_patterns` (`ner_helper.py:873-888`) is 12 regexes built from three vocabularies
declared just above:

- `polymers` — 30 polymer codes (`pps|pa66|pom|pbt|lcp|…`)
- `filler_abbreviations` — 15 codes (`cf|gf|gb|mf|lgf|lcf|…`)
- `flame_values` — 9 UL ratings (`5va|v0|v1|v2|hb|…`)

They encode a piece of **domain knowledge that is easy to miss**: a string like `pa66gf30` is *not*
a grade name, it is *a polymer plus a filler load*. Without these patterns, `pa66gf30` would
substring-match some real grade and the query would short-circuit to the wrong answer. The comment
at line 874 records a real incident: `v1810` must not be split into `v1` + `810`, because it is
part of the competitor grade `kynar hsv1810`.

## A.4 The order of operations (with line numbers)

| Step | Line | What happens |
|---|---|---|
| 1 | `run_ner` `ner_helper.py:720` | entry |
| 2 | `:779-818` | **MATERIAL_ID** short-circuit |
| 3 | `:823` | `data_preprocessing()` → cleaned query + normalised query |
| 4 | `:828-863` | empty after cleaning → return `unidentified` |
| 5 | `:891-936` | **single-FEATURE** short-circuit (pfas-free) |
| 6 | `:938-1086` | **GRADE** short-circuit |
| 7 | `:1089-1137` | **COMPETITOR_GRADE** short-circuit |
| 8 | `:1140-1193` | **AUTO_CERT** short-circuit |
| 9 | `:1262-1267` | **LLM call** (primary deployment, PROD falls back to secondary) |
| 10 | `:1270` | `eval()` the model's text into a dict; on failure → all-empty dict |
| 11 | `:1293` | `validate_result_dict()` — schema enforcement |
| 12 | `:1295-1885` | **all the correction rules** (the rest of this document) |
| 13 | `:1886` | `identify_out_of_scope_items()` |
| 14 | `:1901-1905` | de-duplicate every list |

## A.5 The design rationale

From the repo README, quoted in the KT: *"Avoid frequent finetuning if a NER issue can be fixed by
a rule-based approach."*

That single sentence explains the shape of the whole codebase. **A rule ships today; a fine-tune
takes days and costs money.** So every business decision that can be expressed deterministically
has been pushed out of the model and into `ner_helper.py` lines 1295-1885. When you read those 600
lines you are reading a **changelog of business decisions**, not a designed system.

---

# PART B — the entities, one at a time

Legend for the examples: **✓** = observed in the real 500-query model run;
**⟶** = traced from the code path.

---

## 1. MATERIAL_ID

**Definition.** The 8-digit **SAP material number** that identifies a specific sellable material in
Celanese's ERP. Not a product name — an internal system key.

**Resolver: 🔧 100% rule. The LLM never produces this and is not even called.**

**Path:** `ner_helper.py:779-818`

```python
search_query = search_query.strip()
if search_query.isdigit():
    search_query = str(int(search_query))          # strips leading zeros
    if len(search_query) == 8 and search_query.startswith(('2', '5')):
        return output_sap_material_id              # LLM never called
```

**Three rules, all domain knowledge:**

1. the query must be **digits only** — a SAP id never appears alongside other words
2. after stripping leading zeros it must be **exactly 8 digits**
3. it must **start with 2 or 5** — Celanese's SAP number ranges for sellable materials

The `int()` conversion is deliberate: SAP exports pad ids to 18 characters, so users paste
`000000000021234567`. Converting to int and back drops the padding.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `21234567` | whole query | `MATERIAL_ID: ["21234567"]` | 8 digits, starts `2` ⟶ |
| 2 | `51234567` | whole query | `MATERIAL_ID: ["51234567"]` | starts `5` ⟶ |
| 3 | `00021234567` | whole query | `MATERIAL_ID: ["21234567"]` | `int()` strips zeros → 8 digits ⟶ |
| 4 | `  21234567  ` | whole query | `MATERIAL_ID: ["21234567"]` | `.strip()` first ⟶ |
| 5 | `31234567` | — | **not** MATERIAL_ID → goes to LLM | starts `3`, fails rule 3 ⟶ |
| 6 | `2123456` | — | goes to LLM | 7 digits ⟶ |
| 7 | `212345678` | — | goes to LLM | 9 digits ⟶ |
| 8 | `21234567 pa66` | — | goes to LLM | not `isdigit()` ⟶ |
| 9 | `celanex 21234567` | — | goes to LLM | not `isdigit()` ⟶ |
| 10 | `2002-2` | — | goes to LLM (likely GRADE) | not `isdigit()` ⟶ |

**Gap worth knowing:** rule 3 means a valid SAP id in another number range is silently missed, and
a SAP id embedded in a longer query is never detected at all.

---

## 2. GRADE

**Definition.** A specific **Celanese commercial product**, at the level you can actually order —
usually `brand + code + optional colour code`, e.g. `celanex 2002-2`, `hostaform c 9021`,
`celstran pa6-gf60-01`.

**Resolver: 🔧 fast-path rule (M2) **or** 🤖 LLM + heavy rules (M3+M4).**

### 2a. The fast path — `ner_helper.py:938-1086`

Four ways to match, tried in order:

| Order | Line | Test |
|---|---|---|
| skip | `:951` | if the query is a **competitor brand**, abandon the grade path entirely |
| 1 | `:953` | cleaned query, punctuation stripped, is **exactly** a known grade → also sets `no_offsets=True` |
| 2 | `:956` | normalised query (offset terms removed) is **exactly** a known grade |
| 3 | `:958` | normalised query is a **substring** of some grade — but only if it is not itself in `columnsforSubstringCheck` |
| 4 | `:962-1011` | the **`a` / `i` token dance** (below) |

**The `a`/`i` dance** exists because `a` and `i` are both *English words* and *parts of grade
names* (`vectra a130`, `celanex 2002-2 i`). `GRADE_OFFSET_TERMS2` (`:948`) is the offset list with
`a` and `i` removed; the code then tries dropping each occurrence in turn to see whether any
variant matches a real grade. This is pure hard-won domain patching.

**Name reconstruction** (`:1013-1028`): the returned grade is the *cleaned* query minus offset
terms, then `" - "→"-"` and `". "→"."` are restored — because `celanex 2002-2` must not come back
as `celanex 2002 - 2`. If pre-processing altered the query at all (`:1027`), the **raw lowercased
query** is returned instead, to avoid handing search a mangled grade name.

### 2b. Post-LLM correction — `ner_helper.py:1390-1421`

For each GRADE the model returned:

1. `:1392` normalised value is a substring of a known grade → **keep**
2. `:1394` it is a substring of a **competitor** grade → **move to COMPETITOR_GRADE**
3. `:1397` it matches an **auto certification** → **move to AUTO_CERT** via `update_auto_cert()`
4. `:1409` it **starts with a known Celanese brand** → keep (added to stop brand-prefixed grades being reclassified)
5. `:1416` `thefuzz.token_sort_ratio > 80` against `GRADE_NAMES` **and** the value does not contain an out-of-scope brand → **move to COMPETITOR_GRADE**

### 2c. Grade decorations — `ner_helper.py:1471-1509`

The grade string carries suffixes that are really *features*, and they must be split out:

| Suffix | Becomes | Line | Domain meaning |
|---|---|---|---|
| `uv` | `FEATURE: u.v. stabilized or stable to weather` | `:1356-1359, 1477` | UV-stabilised variant |
| `eco-r` | `FEATURE: recycled content` | `:1480-1487` | mechanically recycled |
| `eco-b` | `FEATURE: bio-content` | `:1489-1496` | bio-based feedstock |
| `eco-c` | `FEATURE: carbon capture` | `:1498-1505` | carbon-capture feedstock |
| value is a brand | move to `BRAND` | `:1507-1509` | user typed only the brand |

The UV regex (`:1356`) is `(?:(?<=\W)|(?<=^)|(?<=\d))(uv)(?=\W|$|\d)` — `uv` only counts as a
suffix when it stands alone or follows a digit, so `uvex` inside a name is untouched.

> **`eco-c` is handled entirely in rules** because it was never in the training data — see the
> `run_ner` docstring at `:770`. And `eco` alone was ambiguous in the synonym table (it meant both
> *sustainable* and *ecomid*), so `:1750-1752` forces it to `sustainable`.

**Domain knowledge required:** Celanese brand→grade naming conventions; that `GF60` in a grade name
is part of the name, not a filler spec; that colour codes (`BK009`, `NC010`) are appended to grade
names and must sometimes be stripped (`post_processing.py:601-602`).

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `vectra a130 Phenolic chemicals resistance` | `vectra a130` | `GRADE: ["vectra a130"]` | ✓ LLM, kept by `:1392` |
| 2 | `celanex 2002-2 - any data on Styrene exposure?` | `celanex 2002-2` | `GRADE: ["celanex 2002-2"]` | ✓ LLM + punctuation restore |
| 3 | `does fortron 0214 hold up in Industrial oxidants` | `fortron 0214` | `GRADE: ["fortron 0214"]` | ✓ LLM |
| 4 | `can I use hostaform c 9021 where there is Silicone grease contact` | `hostaform c 9021` | `GRADE: ["hostaform c 9021"]` | ✓ LLM |
| 5 | `celanex 2002-2` | whole query | `GRADE`, **no LLM call** | fast path `:953` ⟶ |
| 6 | `looking for alternative to celanex 2002-2` | after offset strip | `GRADE`, no LLM | offsets dropped by `normalize_query` ⟶ |
| 7 | `hostaform c 9021 uv` | `hostaform c 9021` + `uv` | `GRADE` + `FEATURE: u.v. stabilized…` | `check_if_uv_in_grade` `:1345` ⟶ |
| 8 | `celcon m90 eco-r` | `celcon m90` + `eco-r` | `GRADE: ["celcon m90"]` + `FEATURE: recycled content` | `:1480` ⟶ |
| 9 | `ultramid a3wg6` | whole query | **COMPETITOR_GRADE**, not GRADE | competitor list wins `:1089` ⟶ |
| 10 | `pa66gf30` | — | **not** a grade → LLM | blocked by `non_grade_patterns` `:943` ⟶ |

---

## 3. COMPETITOR_GRADE

**Definition.** A specific product **from another manufacturer** — BASF Ultramid, DuPont Zytel,
EMS Grivory, DSM Stanyl. Present so the search can answer *"what do you have that replaces X?"*.

**Resolver: 🔧 fast path **or** 🤖 LLM + rules.**

**Fast path** `ner_helper.py:1089-1137` — three tests: exact match in `COMPETITOR_GRADE`
(`:1089`), exact match in `COMPETITOR_BRAND` (`:1091`), or substring of a competitor grade
(`:1093`), with `"nsf"` explicitly excluded (`:1095`) because it collides with the NSF
certification.

**Post-LLM reclassification** `:1366-1388` is the mirror of the GRADE logic, plus one important
extra: `:1373-1375` — if the query contains **`tds`, `sds`, `alternative`, `offset`, `replacement`,
`similar`, `instead`, `competitor`**, the value is left alone. Those words *signal competitor
intent*, so the model's label is trusted rather than second-guessed.

**Competitor brand stripping** `:1455-1469`: words are popped from the **start and end** of the
value while they appear in `NORMALIZED_COMPETITOR_NAMES`. `"ultramid a3wg6"` → `"a3wg6"`. The
business reason is that the downstream search indexes competitor grades **without** the maker's
name.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `replacement for radilon a cf200 333 bk in Phenol derivatives service` | `radilon a cf200 333 bk` | `COMPETITOR_GRADE` | ✓ LLM, protected by `:1373` |
| 2 | `alternative to durethan akv15 000000 that handles Aryl alcohol derivatives` | `durethan akv15 000000` | `COMPETITOR_GRADE` | ✓ |
| 3 | `we currently use ultramid a3eg6, need better Motor gasoline resistance` | `ultramid a3eg6` | `COMPETITOR_GRADE` | ✓ |
| 4 | `cross reference for ultramid a3eg6 - must survive VALEO SERVICE G13` | `ultramid a3eg6` | `COMPETITOR_GRADE` | ✓ |
| 5 | `akulon care k1g6` | whole query | fast path, no LLM | `:1089` ⟶ |
| 6 | `zytel` | whole query | `COMPETITOR_GRADE` (brand match) | `:1091` ⟶ |
| 7 | `ultramid a3wg6` (after strip) | — | value becomes `a3wg6` | `:1459-1464` ⟶ |
| 8 | LLM says `COMPETITOR_GRADE: celanex 2002-2` | — | moved to `GRADE` | `:1370-1372` ⟶ |
| 9 | LLM says `COMPETITOR_GRADE: ms50017` | — | moved to `AUTO_CERT` | `:1376-1383` ⟶ |
| 10 | `nsf` | — | **not** competitor grade | excluded at `:1095` ⟶ |

---

## 4. BRAND

**Definition.** A Celanese **product family / trade name** — `celanex` (PBT), `hostaform` /
`celcon` (POM), `fortron` (PPS), `vectra` / `zenite` (LCP), `celstran` (long-fibre), `santoprene`
(TPV). 64 brands.

**Resolver: 🤖 LLM, then hard-filtered by rules.**

**The validation** `ner_helper.py:1334-1339`:

```python
for brand in result['BRAND']:
    if brand.lower() in NORMALIZED_UNIQUE_VALUES['BRAND']: pass
    else: result['BRAND'].remove(brand)
```

> ⚠️ **Live bug.** This mutates the list while iterating over it. With two invalid brands, the
> second is skipped. Worth raising.

**Brand-specific rules — every one of these is a recorded incident:**

| Line | Rule | Domain reason |
|---|---|---|
| `:1443-1445` | `blueridge` in GRADE → BRAND | model kept mislabelling it |
| `:1446-1448` | `litepol` in GRADE → BRAND | same |
| `:1449-1450` | drop `hostaform` if it is **not in the query** but `at` is | model hallucinated `hostaform` from the token `at` |
| `:1507-1509` | grade value that is actually a brand → BRAND | user typed only the family name |
| `:1747-1752` | `ecomid` + any eco term → drop brand; `eco` alone → `FEATURE: sustainable` | the synonym-table collision |
| `post_processing.py:545-546` | `bexloy` → `hytrel` | brand renamed commercially |

**Scope filtering** `post_processing.py:548-568` — this is where `user_type` bites:

| List | internal user | external user |
|---|---|---|
| `brands_internal` (0) | visible | — |
| `brands_commerical` (7) | visible | **hidden** |
| `brands_not_in_scope` (50) | **hidden** | **hidden** |

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `is hostaform ok with isopropyl alcohol (IPA)` | `hostaform` | `BRAND: ["hostaform"]` | ✓ LLM + `:1336` |
| 2 | `is celcon ok with toluene` | `celcon` | `BRAND: ["celcon"]` | ✓ |
| 3 | `is celanyl ok with silicone oils` | `celanyl` | `BRAND: ["celanyl"]` | ✓ |
| 4 | `Highly alkaline media resistant grade frianyl` | `frianyl` | `BRAND: ["frianyl"]` | ✓ |
| 5 | `Styrene resistant grade vectra` | `vectra` | `BRAND: ["vectra"]` | ✓ |
| 6 | `coolpoly DMF 8356` | `coolpoly` | `BRAND: ["coolpoly"]` | ✓ |
| 7 | LLM returns `BRAND: ["ultramid"]` | — | **removed** | not in the 64-brand list `:1338` ⟶ |
| 8 | `... at ...` (no hostaform in query) | — | `hostaform` dropped | `:1449` ⟶ |
| 9 | `bexloy` | `bexloy` | `BRAND: ["hytrel"]` | `post_processing.py:545` ⟶ |
| 10 | `pipelon` (external user) | `pipelon` | moved to `outOfScope.BRAND` | commercial brand, external `:563` ⟶ |

---

## 5. POLYMER

**Definition.** The **base chemistry** independent of brand — `pa66`, `pom`, `pbt`, `pps`, `lcp`.
229 values including long forms (`polyamide 66`, `acetal copolymer`) and the **wildcard `pa*`** for
"some nylon, unspecified".

**Resolver: 🤖 LLM, with two rules after.**

**Rule 1 — PBT vs polyester** `ner_helper.py:1511-1514`:

```python
if "pbt" in POLYMER and "polyester" in query and "pbt" not in query:
    POLYMER: pbt → polyester
```

*Domain knowledge:* PBT **is** a polyester, so the model learned to answer `pbt` whenever it saw
"polyester". But a user who typed the generic word wants the whole polyester family, not just PBT.
The rule only fires when the user did **not** write `pbt`.

**Rule 2 — out-of-scope polymers** `post_processing.py:521-536`: 23 polymers Celanese does not
sell (`ps`, `ptt`, `pa12`…) are moved to `outOfScope`. Two extras:

- `:528-531` — a **bonding** word (`bondable`, `adhesion`, `cohesive`) alongside any polymer adds
  `OTHERS: bondable`. Celanese cannot answer bonding questions from this data.
- `:532-536` — `polyether` is hardcoded out of scope, "not in OOS list, currently hardcoded".

**The `pa*` wildcard** is genuine domain modelling: *"nylon"* alone cannot be resolved to PA6 or
PA66, so the schema carries an explicit "unspecified polyamide" value rather than guessing.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `POM resistant to isopropyl alcohol (IPA)` | `POM` | `POLYMER: ["pom"]` | ✓ LLM |
| 2 | `nylon 66 resistant to toluene` | `nylon 66` | `POLYMER: ["pa66"]` | ✓ LLM canonicalises |
| 3 | `PPS resistant to xylene` | `PPS` | `POLYMER: ["pps"]` | ✓ |
| 4 | `acid resistant polyamide` | `polyamide` | `POLYMER: ["pa*"]` | ✓ wildcard |
| 5 | `alcohol resistant PPA` | `PPA` | `POLYMER: ["ppa"]` | ✓ |
| 6 | `acetal copolymer for ...` | `acetal copolymer` | `POLYMER: ["acetal copolymer"]` | ✓ |
| 7 | `polyester housing` | `polyester` | `pbt` → **`polyester`** | `:1512` ⟶ |
| 8 | `pbt polyester housing` | `pbt` | stays `pbt` | user wrote pbt, rule skipped ⟶ |
| 9 | `ps enclosure` | `ps` | → `outOfScope.POLYMER` | `:522` ⟶ |
| 10 | `bondable pa66` | `pa66` + `bondable` | `POLYMER` kept, `OTHERS: bondable` | `:528` ⟶ |

---

## 6. FILLER

**Definition.** The **reinforcement or additive** and how much of it. Two separate things in one
entity: **what** (`glass fiber`, `carbon fiber`, `mineral`) and **how much** (`total_load`, a
percentage with a tolerance band).

**Output shape** — a list of up to two dicts:

```python
FILLER: [{'filler_name': ['glass fiber']},
         {'total_load': {'value': '30', 'min': '25', 'max': '35'}}]
```

**Resolver: 🤖 LLM, with three rules.**

**Rule 1 — collapse a fake range** `ner_helper.py:1295-1303`: if `value == min` or `value == max`,
set `value = None`. The model sometimes emits `{value: 30, min: 30, max: 35}` for *"30-35%"*; that
is a range, not a point, so the point value is cleared.

**Rule 2 — Celstran long fibre** `:1305-1323`. This is the most domain-specific rule in the file.
**Celstran is Celanese's long-fibre-reinforced line**, so when the brand is Celstran the filler
must be upgraded:

| normal | Celstran |
|---|---|
| `glass fiber` | `long glass fiber` |
| `carbon fiber` | `long carbon fiber` |
| `aramid fiber` | `long aramid fiber` |

with a guard: only upgrade if the plain form actually appears in the raw query (`:1318`) — the user
may already have typed "long glass fiber".

**Rule 3 — spelling** `:1873-1881`: `aramide fiber` → `aramid fiber`.

**Validation** `post_processing.py:253-275`: each dict must carry `filler_name` (a list) **or**
`total_load` (a dict with `value`/`min`/`max`).

**Out of scope** `post_processing.py:572-581`: only one entry — `natural organic fiber`. If
removing it empties the list, the whole FILLER entity is cleared.

**Reading the tolerance band:** `gf30` → `{value: 30, min: 25, max: 35}`. The ±5 is a **search
tolerance**, not a spec — a 27% glass grade should still be found by a "30% glass" search.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `Middle-distillate fuel resistant PET gf20` | `gf20` | `glass fiber` + `20 (15-25)` | ✓ |
| 2 | `polyamide 66 gf50 ...` | `gf50` | `glass fiber` + `50 (45-55)` | ✓ |
| 3 | `Corrosive bases resistant polyamide 66 gf33` | `gf33` | `glass fiber` + `33 (28-38)` | ✓ |
| 4 | `LCP gf60 Designer lubricants resistant` | `gf60` | `glass fiber` + `60 (55-65)` | ✓ |
| 5 | `Petroleum-derived oil resistant acetal gf30` | `gf30` | `glass fiber` + `30 (25-35)` | ✓ |
| 6 | `30% glass filled nylon` | `30% glass filled` | same shape | ✓ |
| 7 | `celstran glass fiber 40%` | `glass fiber` | **`long glass fiber`** | `:1306` ⟶ |
| 8 | `aramide fiber reinforced` | `aramide fiber` | `aramid fiber` | `:1876` ⟶ |
| 9 | `25-35% glass` | range | `{value: None, min: 25, max: 35}` | `:1302` ⟶ |
| 10 | `natural organic fiber filled` | — | → `outOfScope.FILLER` | `:575` ⟶ |

---

## 7. PROPERTY — the hardest entity

**Definition.** A **measurable characteristic with a value**: tensile strength, melt flow, service
temperature, flame rating. Three parts: *what* (property_name), *how much* (modifier), and *which
regime* (property_type).

**Output shape:**

```python
PROPERTY: [{'property_name': 'continuous service temperature iec 60216-1 (°c)',
            'modifier': {'value': '150.0', 'min': '135.0', 'max': '165.0', 'unit': 'c'},
            'property_type': 'property'}]
```

**`property_type` is the key concept — there are three:**

| Type | Meaning | Where set |
|---|---|---|
| `property` | ordinary datasheet value | LLM |
| `ul_property` | a **UL yellow-card** headline property | forced at `:1797-1802` |
| `ul_sub_property` | a UL property that hangs off a thickness | forced at `:1787-1795` |

The distinction matters because UL properties are **certified test results at a stated thickness**,
not free-floating numbers. `dependencies/ul_list_name_value.json` holds **28** of them, 9 flagged
`has_thickness: true`.

**Resolver: 🤖 LLM, then the heaviest rule stack in the codebase.**

### 7a. Unit conversion — `post_processing.py:122-226`

Users type GPa, the database stores MPa. The conversion runs against two CSV tables:

- `final_unit_conversion_table.csv` — the general case
- `final_unit_conversion_table_for_exeptions.csv` — six properties where the conversion is
  reversed or different: **bulk density, flexural modulus tape, tensile modulus tape, specific
  resistivity, average particle size, inclined-plane tracking** (`:182-193`)

Matching is **fuzzy** (`token_sort_ratio > 85`, `:109`). Units already correct are skipped by an
exclusion list (`:181`): `"", %, v, volt, volts, °c, c, d`.

The converted unit is recorded as **`old<->new`** (`:206`), e.g. `gpa<->mpa` — so downstream can
see a conversion happened.

### 7b. UL value → PLC conversion — `ner_helper.py:359-497`

**This is pure electrical-safety domain knowledge and the single biggest piece of SME content in
the project.** UL does not compare raw numbers; it bands them into **Performance Level Categories**
where **PLC 0 is best**.

| Property | Function | Bands |
|---|---|---|
| CTI (V) | `cti_value_convertion:359` | ≥600→0, ≥400→1, ≥250→2, ≥175→3, ≥100→4, else 5 |
| HAI (arcs) | `hai_value_convertion:383` | ≥120→0, ≥60→1, ≥30→2, ≥15→3, else 4 |
| HWI (s) | `hwi_value_convertion:405` | ≥120→0, ≥60→1, ≥30→2, ≥15→3, ≥7→4, else 5 |
| HVAR (arcs) | `hvar_value_convertion:429` | ≥300→0, ≥120→1, ≥30→2, else 3 |
| HVTR (mm/min) | `hvtr_value_convertion:449` | >150→4, ≥80.1→3, ≥25.5→2, ≥10.1→1, else 0 |
| Arc resistance (s) | `arc_value_convertion:471` | ≥420→0 … <60→7 |

Note **HVTR is inverted** — a *lower* tracking rate is better, so the bands run the other way. Get
that backwards and every HVTR search is wrong.

Each function is reached through a **synonym list** at `:1806-1811` — `cti`, `comparative
tracking`, `comparative tracking index rating`… all route to the CTI converter.

The fallback at `:1775-1778` is candid: if the value will not parse, `"high"` becomes `plc 0` and
everything else is left alone, with the comment *"rules not yet defined by the business team"*.

### 7c. Property-specific fixes — `:1826-1866`

| Line | Rule | Domain reason |
|---|---|---|
| `:1826-1849` | `dimensional change`: decide whether a value or a range was meant, using a **10% heuristic** — if max is ~10% above value it was a default expansion, otherwise a real range was given | the model pads a ±10% band by default |
| `:1851-1852` | property with no value at all → `value = 'good'` | "good flow" is a real query shape |
| `:1854-1860` | `hardness` + unit `a` → `shore a hardness iso 48-4 / iso 868 15s`; unit `d` → `shore d…` | Shore A and Shore D are different scales |
| `:1861-1864` | `bulk density` → `density iso 1183` when the query says **specific gravity** and not **bulk** | different measurements; users conflate them |
| `:1865-1866` | any `water absorption` → `absorption` | the database column is generic |

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `... CTI plc 1 ...` | `CTI plc 1` | `comparative tracking index (cti)`, `plc 1`, `ul_property` | ✓ |
| 2 | `... continuous service temperature of 120C` | `120C` | `…iec 60216-1 (°c)`, `120.0 (108-132)`, `property` | ✓ |
| 3 | `RTI 120.0C` | `RTI 120.0C` | `relative thermal index`, `ul_sub_property` | ✓ forced at `:1794` |
| 4 | `UL94 v-0` | `v-0` | `flame rating`, `v-0`, `ul_sub_property` | ✓ |
| 5 | `600 V CTI` | `600 V` | → **`plc 0`** | `cti_value_convertion` ⟶ |
| 6 | `CTI 350` | `350` | → `plc 2` | 250 ≤ 350 < 400 ⟶ |
| 7 | `hvtr 200` | `200` | → `plc 4` (worst) | inverted band ⟶ |
| 8 | `tensile modulus 3 GPa` | `3 GPa` | `3000`, unit `gpa<->mpa` | `:206` ⟶ |
| 9 | `shore 50 a` | `50` + unit `a` | `shore a hardness iso 48-4 / iso 868 15s` | `:1855` ⟶ |
| 10 | `good flow` | `good` | `value: 'good'` | `:1851` ⟶ |

---

## 8. FEATURE

**Definition.** A **qualitative characteristic** with no number: flame retardant, UV stabilised,
food contact, recycled content. 862 values — the messiest vocabulary in the system.

**Resolver: 🔧 fast path for a single feature, otherwise 🤖 LLM + many rules.**

**Fast path** `ner_helper.py:891-936`: if the whole query equals a known feature **and that feature
is `pfas-free`**, return immediately. Only `pfas-free` short-circuits (`:895`) — a regulatory
topic where a single-word query is unambiguous.

**Canonical renaming** `:1532-1546` — the model emits the short form, search needs the long form:

| Model says | Rewritten to |
|---|---|
| `heat stabilized` | `heat stabilized or stable to heat` |
| `impact modified` | `high impact or impact modified` |
| `bio-based` | `bio-content` |
| `contains recycle` | `recycled content` |

Then `:1546` deletes **every feature containing `auto`** — those belong in `AUTO_CERT`.

**Carbon capture** `:1548-1551`: `carbon footprint`, `iso 14067`, `ccu`, `carbon capture` in the
query → `FEATURE: carbon capture`, regardless of what the model said.

**Eco terms** `:1723-1745` via `check_for_terms()` (`:698`), which spaces out `-` and `/` first so
`eco-c`, `eco c`, `eco / c` and `ecoc` all match:

| Term | Feature | Extra |
|---|---|---|
| eco-c | `carbon capture` | also **removes** a `carbon capture` PROPERTY if the model made one (`:1731-1739`) |
| eco-b | `bio-content` | |
| eco-r | `recycled content` | |

**Medical** `:1631-1635`: any APPLICATION containing `medical` is **deleted** and becomes
`FEATURE: medical/healthcare`. Medical is treated as a property of the material, not a use case.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `oil resistant POM` | `oil resistant` | `FEATURE: ["oil resistant"]` | ✓ |
| 2 | `alkali resistant grade` | `alkali resistant` | `FEATURE: ["alkali resistant"]` | ✓ |
| 3 | `coolant resistant PA66` | `coolant resistant` | `FEATURE: ["coolant resistant"]` | ✓ |
| 4 | `grades that handle silicone oils` | (inferred) | `FEATURE: ["low wear / low friction"]` | ✓ model inference |
| 5 | `pfas-free` | whole query | `FEATURE`, **no LLM** | `:895` ⟶ |
| 6 | `heat stabilized pbt` | `heat stabilized` | `heat stabilized or stable to heat` | `:1533` ⟶ |
| 7 | `iso 14067 grade` | `iso 14067` | `carbon capture` | `:1548` ⟶ |
| 8 | `celcon m90 eco-b` | `eco-b` | `bio-content` | `:1741` ⟶ |
| 9 | `medical device housing` | `medical` | APPLICATION deleted → `medical/healthcare` | `:1631` ⟶ |
| 10 | model returns `auto approved` | — | **deleted** | `:1546` ⟶ |

---

## 9. APPLICATION

**Definition.** What the part **is** or what it **does** — `fuel tank`, `coolant valve`, `catheter
device`. 22,475 values, by far the largest vocabulary.

**Resolver: 🤖 LLM + cleanup rules.**

**Generic-word stripping** `:1572-1628` + `:1642-1643`: `part`, `parts`, `material`, `materials`
are popped from **both ends**, plus `possibly/a/an/the/in` anywhere and `for`/`with` at the start.
`"dishwasher parts"` → `"dishwasher"`. `"material handling"` is explicitly exempt (`:1643`) —
there it is the actual application.

**`li auto`** `:1638-1640`: moved out of APPLICATION into `AUTO_CERT` with `oem: li auto`. Li Auto
is a Chinese EV maker, not an application. The comment calls it an "old issue".

**E&E abbreviations** `:1693` + `pre_processing.py:341-356`: a list of two- and three-letter codes
(`pv, hv, tb, sim, lv, vcm, rf, hsd, ic, ff, ac, wtb`) that are applications in the
electrical/electronics domain. Some are expanded during pre-processing (`hsd` → `high speed data`,
`labs` → `lead acid battery separator`, `ff` → `full frame`).

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `isopropyl alcohol (IPA) resistance for catheter device` | `catheter device` | `APPLICATION` | ✓ |
| 2 | `toluene resistance for cooling line` | `cooling line` | `APPLICATION` | ✓ |
| 3 | `silicone oils resistance for fuel cap` | `fuel cap` | `APPLICATION` | ✓ |
| 4 | `nylon 6 for radiator fluids contact` | `radiator fluids contact` | `APPLICATION` | ✓ |
| 5 | `dishwasher parts` | `dishwasher parts` | `dishwasher` | `:1642` ⟶ |
| 6 | `material handling` | whole | unchanged | exempt `:1643` ⟶ |
| 7 | `li auto approval` | `li auto` | → `AUTO_CERT` | `:1638` ⟶ |
| 8 | `hsd connector` | `hsd` | → `high speed data connector` | `pre_processing.py:351` ⟶ |
| 9 | `medical tubing` | `medical` | → `FEATURE: medical/healthcare` | `:1631` ⟶ |
| 10 | `nylon grade for Chlorine gas` | `chlorine gas` | `APPLICATION: ["chlorine gas"]` ⚠️ | ✓ **wrong** — a chemical read as an application |

---

## 10. INDUSTRY

**Definition.** The market sector. **Five documented values**: Medical & Pharma, Industrial,
Automotive & Transportation, Consumer Goods, Electrical & Electronics.

**Resolver: 🤖 LLM + a dedicated E&E rule block.**

**E&E detection** `:1648-1686` — six patterns in priority order: `electrical and electronics`,
`electronics and electrical`, `e & e`, `e and e`, `electrical`, `electronics`. Any hit appends
`electrical & electronics`. E&E gets its own block because it is written so many ways.

**`get_industry()`** `:652-696` maps application keywords to industries, but note the docstring at
`:664`: **"is not used currently"** — the model was trained to emit INDUSTRY directly. It still
runs at `:1689` and can append a second industry.

The `>= 0.8` length ratio at `:692` prevents `"pvc"` matching the `pv` keyword.

**Exception lists** `:1691-1706`: when INDUSTRY is set from a keyword, redundant FEATURE /
APPLICATION / PROCESSING values are blanked — e.g. APPLICATION `["retail"]` is cleared and the
industry popped, because "retail" alone is not an application.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `toluene resistance for cooling line` | (inferred) | `automotive & transportation` | ✓ |
| 2 | `isopropyl alcohol resistance for catheter device` | (inferred) | `medical & pharma` | ✓ |
| 3 | `ABS grade for saline solutions` | (inferred) | `medical & pharma` | ✓ |
| 4 | `vectra a230 Industrial light alcohols resistance` | `Industrial` | `industrial` | ✓ |
| 5 | `nylon 6 for radiator fluids contact` | (inferred) | `automotive & transportation` | ✓ |
| 6 | `electrical & electronics connector` | `electrical & electronics` | `electrical & electronics` | `:1650` ⟶ |
| 7 | `e & e housing` | `e & e` | same | `:1659` ⟶ |
| 8 | `electronics enclosure` | `electronics` | same | `:1671` ⟶ |
| 9 | `retail packaging` | `retail` | APPLICATION cleared, industry popped | `:1702` ⟶ |
| 10 | `nylon grade for Chlorine gas` | — | `INDUSTRY: ["chemical"]` ⚠️ | ✓ **outside the five documented values** |

---

## 11. PROCESSING

**Definition.** The **manufacturing method** — injection moulding, extrusion, blow moulding, fibre
spinning.

**Resolver: 🤖 LLM + two rules.**

- `:1523-1526` — `fibre spinning / gel extrusion` → `fiber spinning / gel spinning`. British
  spelling plus a wrong second term; the database uses the American form.
- `:1528-1529` — if the query contains `moulding` and no PROCESSING value contains `molding`, append
  `molding`. Also fires when `molding` and `grade` appear together in either order. This is a pure
  **en-GB → en-US** safety net.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `Injection moulding project: ABS with 40% GF …` | `Injection moulding` | `injection molding` | ✓ |
| 2 | `injection molding grade pom` | `injection molding` | `injection molding` | ✓ |
| 3 | `blow moulding pe` | `blow moulding` | `molding` appended | `:1528` ⟶ |
| 4 | `moulding grade` | `moulding grade` | `molding` appended | `:1528` ⟶ |
| 5 | `extrusion grade pbt` | `extrusion` | `extrusion` | LLM ⟶ |
| 6 | model says `fibre spinning / gel extrusion` | — | `fiber spinning / gel spinning` | `:1524` ⟶ |
| 7 | `overmolding tpe` | `overmolding` | LLM value | ⟶ |
| 8 | `thermoforming sheet` | `thermoforming` | LLM value | ⟶ |
| 9 | `3d printing filament` | `3d printing` | LLM value | ⟶ |
| 10 | `manufacturing` + industry match | — | PROCESSING **cleared** | `:1705` ⟶ |

---

## 12. DELIVERY_FORM

**Definition.** The **physical form supplied** — pellets, granules, powder, sheet, rod, film.

**Resolver: 🤖 LLM only. No business rules anywhere.**

The only handling is `validate_result_dict` (`post_processing.py:392-432`) checking it is a list.
There is no gazetteer, no canonical list, no correction rule. It never appeared in our 500-query
run.

*Ten examples are not meaningful for this entity — whatever the model emits is what you get. If you
need it to behave predictably, it needs either training data or a rule; today it has neither.*

---

## 13. AUTO_CERT

**Definition.** An **automotive OEM material specification** — the approval that lets a material be
used on a car programme. Two parts: **which carmaker** (`oem`) and **which spec** (`certs`).

**Output shape:** `[{'oem': 'stellantis', 'certs': ['ms50017']}]`, with `'all'` as a wildcard on
either side.

**Resolver: 🔧 fast path **or** 🤖 LLM + the most elaborate validation in the codebase.**

**Fast path** `:1140-1193`, and note what it excludes first (`:1140-1141`): if the query mentions
`tds`, `sds`, `alternative`, `replacement`, `competitor`… it is **not** a cert lookup — the user is
comparing products. Then `ignore_common_words` (`:889`) strips `approval`, `approved`, `cert`,
`certified`, `by`, `need`, `auto`, `automotive`, `imds`, and the remainder is matched against the
998 `[normalised_cert, oem]` pairs.

**`update_auto_cert()`** `:537-577` — used when the model misfiled a cert as a grade. Manages the
`'all'` wildcard: adding a specific cert removes `'all'`; the OEM is created if new.

**`validate_auto_cert()`** `:579-650` — the important one. **It re-maps a cert to the correct OEM.**
If the model said `{oem: 'ford', certs: ['ms50017']}` but the gazetteer says `ms50017` belongs to
Stellantis, `:633-638` reassigns it. The SME knowledge here is that **spec numbers are unique to a
carmaker** — the number itself tells you the OEM.

`:605-607` — if the query says "auto certification"/"auto approval" but the model found nothing,
inject `{oem: 'all', certs: ['all']}`, i.e. *"any automotive approval"*.

**Out of scope** `post_processing.py:637-644`: **Toyota is always removed** and flagged. Whatever
the commercial reason, Toyota specs cannot be surfaced.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `grade for Total ALTIS series` | `altis series` | `{oem: total, certs: [altis series]}` | ✓ |
| 2 | `ms50017` | whole query | fast path, no LLM | `:1150` ⟶ |
| 3 | `ms50017 approval` | `ms50017` | same (`approval` stripped) | `:889` ⟶ |
| 4 | `auto certification pa66` | — | `{oem: all, certs: [all]}` | `:605` ⟶ |
| 5 | model says `{oem: ford, certs: [ms50017]}` | — | OEM corrected to `stellantis` | `:633` ⟶ |
| 6 | model says `GRADE: ms50017` | — | moved to AUTO_CERT | `:1397` ⟶ |
| 7 | model says `COMPETITOR_GRADE: n28bn05ox036` | — | moved to AUTO_CERT (bosch) | `:1376` ⟶ |
| 8 | `li auto` | `li auto` | `{oem: li auto, certs: [all]}` | `:1638` ⟶ |
| 9 | `toyota ts m0500g` | — | → `outOfScope.OTHERS: toyota` | `:638` ⟶ |
| 10 | `alternative to ms50017` | — | **not** a cert lookup | `:1141` ⟶ |

---

## 14. RAILWAY_CERT

**Definition.** Rail fire-safety certification, essentially **EN 45545-2** — the European standard
for fire behaviour of rail materials.

**Output shape:** `[{'standard': 'en45545', 'hazard_level': ['hl2'], 'req_set': ['r22']}]`

**Domain knowledge you need:**
- **hazard level** HL1–HL3 — how dangerous the operating environment is (HL3 = underground/tunnel)
- **requirement set** R1–R26 — which test set applies to that part type

**Resolver: 🤖 LLM + one normalisation rule.**

`:1519-1521`: both lists are lowercased and stripped of non-alphanumerics, so `HL 2`, `hl-2` and
`HL2` all become `hl2`. Note it only processes `result["RAILWAY_CERT"][0]` — **a second railway
cert would be left unnormalised.**

Validation at `post_processing.py:305-320` requires all three keys.

*Not observed in the 500-query run; examples below are traced from the rules.*

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `en45545 hl2 r22` | all three | `{standard: en45545, hazard_level: [hl2], req_set: [r22]}` | ⟶ |
| 2 | `EN 45545-2 HL 2` | `HL 2` | `hl2` | `:1520` ⟶ |
| 3 | `hl-3 requirement` | `hl-3` | `hl3` | `:1520` ⟶ |
| 4 | `R 22 rail` | `R 22` | `r22` | `:1521` ⟶ |
| 5 | `railway approval pa66` | `railway approval` | LLM decides | ⟶ |
| 6 | `en45545 hl1 hl2` | both | `hazard_level: [hl1, hl2]` | ⟶ |
| 7 | model returns a string not a dict | — | entity cleared | `post_processing.py:314` ⟶ |
| 8 | model omits `req_set` | — | entity cleared | `:316` ⟶ |
| 9 | two railway certs | — | only the first normalised ⚠️ | `:1519` ⟶ |
| 10 | `rail interior panel` | — | usually APPLICATION, not cert | ⟶ |

---

## 15. WATER_CERT

**Definition.** **Drinking-water contact approval** — KTW (Germany), WRAS (UK), ACS (France), NSF
61 (US). The `temp` field matters because approvals are granted per temperature class.

**Output shape:** `[{'standard': 'ktw', 'temp': ['cold']}]`

**Resolver: 🤖 LLM only.** Validation at `post_processing.py:322-337` requires `standard` and a
list `temp`. **No canonicalisation, no gazetteer.**

**Observed problem.** In our run the model emitted `{standard: 'all', temp: ['all']}` for queries
that merely mentioned water — *"any data on Utility water exposure?"*, *"where there is Cooling
water contact"*. Industrial cooling water has nothing to do with drinking-water approval. With no
validation rule, these pass straight through. This is a genuine precision problem.

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `vectra a230 - any data on Utility water exposure?` | `water` | `{standard: all, temp: [all]}` ⚠️ | ✓ **false positive** |
| 2 | `where there is Cooling water contact` | `water` | `{standard: all, temp: [all]}` ⚠️ | ✓ false positive |
| 3 | `... surgical instrument ... cold ...` | — | `{standard: all, temp: [cold]}` | ✓ |
| 4 | `ktw approval pom` | `ktw` | `{standard: ktw, …}` | ⟶ |
| 5 | `wras cold water` | `wras` + `cold` | `{standard: wras, temp: [cold]}` | ⟶ |
| 6 | `acs france potable` | `acs` | `{standard: acs, …}` | ⟶ |
| 7 | `nsf 61 hot water` | `nsf 61` + `hot` | `{standard: nsf 61, temp: [hot]}` | ⟶ |
| 8 | `drinking water approval` | phrase | `{standard: all, temp: [all]}` | ⟶ |
| 9 | model returns a string | — | entity cleared | `:331` ⟶ |
| 10 | `temp` not a list | — | entity cleared | `:335` ⟶ |

---

## 16. NSF_CERT

**Definition.** **NSF International** certification — mainly NSF/ANSI 51 (food equipment) and 61
(drinking water components).

**Resolver: 🤖 LLM only.** The weakest validation of all — `post_processing.py:339-348` only checks
it is a list. It is a **flat list of strings**, unlike every other certification entity.

One rule elsewhere matters: `ner_helper.py:1095` excludes the token `nsf` from the competitor-grade
substring match, otherwise `nsf` would match some competitor grade and short-circuit the query.

*Not observed in the run.*

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `nsf 51` | `nsf 51` | `NSF_CERT: ["nsf 51"]` | ⟶ |
| 2 | `nsf 61 approval` | `nsf 61` | `["nsf 61"]` | ⟶ |
| 3 | `nsf certified pom` | `nsf` | LLM decides | ⟶ |
| 4 | `nsf` | `nsf` | **not** competitor grade | `:1095` ⟶ |
| 5 | `nsf/ansi 51` | phrase | `["nsf/ansi 51"]` | ⟶ |
| 6 | `nsf 51 and 61` | both | two-item list | ⟶ |
| 7 | model returns a dict | — | cleared (must be list) | `:346` ⟶ |
| 8 | `food equipment approval` | phrase | may or may not map | ⟶ |
| 9 | `nsf 61 hot` | — | may split across NSF_CERT / WATER_CERT ⚠️ | overlap ⟶ |
| 10 | `national sanitation foundation` | full name | probably missed | no synonym list ⟶ |

---

## 17. REGION

**Definition.** The **commercial region** where the material must be available — Celanese sells
different portfolios in different regions.

**Resolver: 🤖 LLM + one rule.**

`:1451-1453`: `africa middle east` → `europe middle east africa`. The model learned a partial
region name; the business region is EMEA.

Note `:1885` — a commented-out line that used to blank REGION entirely *"to be used only till model
is updated with region"*. REGION is a recent addition.

*Not observed in the run.*

| # | Query | Chunk | Resolved | How |
|---|---|---|---|---|
| 1 | `pa66 for europe` | `europe` | `REGION: ["europe"]` | ⟶ |
| 2 | `africa middle east availability` | `africa middle east` | `europe middle east africa` | `:1451` ⟶ |
| 3 | `emea grades` | `emea` | LLM decides | ⟶ |
| 4 | `north america pom` | `north america` | `["north america"]` | ⟶ |
| 5 | `asia pacific supply` | `asia pacific` | `["asia pacific"]` | ⟶ |
| 6 | `china availability` | `china` | country, may or may not map | ⟶ |
| 7 | `us market grade` | `us` | ambiguous with other tokens | ⟶ |
| 8 | `apac` | `apac` | abbreviation, no synonym rule | ⟶ |
| 9 | `latin america` | `latin america` | `["latin america"]` | ⟶ |
| 10 | `global availability` | `global` | probably no region | ⟶ |

---

## 18. The two new entities — MEDICAL_CERT and CHEMICAL_RESISTANCE

Implemented in the **11-Aug-2026** commit. Everything below is traced from code and **verified by
running the functions** against the real data files.

New machinery:

| Piece | Where |
|---|---|
| `chemical_resistance.json` | new dependency file — 11 categories, 25 sub-categories |
| `FEATURE` / `MEDICAL_CERT` / `CHEMICAL_RESISTANCE` keys | added to `normalized_unique_values_for_grade_mapping.json` |
| 5 new functions | `post_processing.py:399-557` |
| 4 new call sites | `ner_helper.py:1306, 1311, 1316, 1320` |

---

### 18a. CHEMICAL_RESISTANCE

**Definition.** Which chemical family the part must survive, plus the verdict.

```python
{'chemical_category':     'acids',
 'chemical_sub_category': 'sulfuric acid',
 'temperature':           '23',
 'resistance_level':      'resistant, long-term exposure'}
```

**Resolver: 🤖 LLM proposes the chemical · 🔧 rules supply the verdict.**

`chemical_resistance.json` holds, per category, a list of
`{sub_category, resistance_level, synonyms, temperature}`. At import (`post_processing.py:18-45`)
it is flattened into four lookups — the one that matters is **`chem_term_to_entry`**, mapping
**583 searchable chemical terms** (category names, sub-category names and every synonym) to a
`(category, sub_category)` pair.

**`validate_chemical_resistance_values()`** (`:399`) — the important design change. It does **not**
trust the model's verdict:

| Field | Treatment |
|---|---|
| `chemical_category` | validated against the 11 keys; invalid → `'None'` |
| `chemical_sub_category` | validated within that category; invalid → `'None'` |
| `resistance_level` | **backfilled** from the `(category, sub_category)` lookup — the model's value is discarded |
| `temperature` | **forced to `'23'`** |

✅ **Verified by running it:**

```
in : {"chemical_category":"Acids","chemical_sub_category":"Formic Acid",
      "resistance_level":"TOTALLY WRONG","temperature":"80"}
out: {"chemical_category":"acids","chemical_sub_category":"formic acid",
      "temperature":"23","resistance_level":"limited resistance, short-term exposure"}
```

This directly answers the concern raised earlier in this document: `resistance_level` and
`temperature` are **not extractable from a query** — they describe how a material behaves, not what
the user asked. They are now a deterministic lookup rather than a model guess. The model's only job
is naming the chemical.

**`reclassify_feature_to_chem_res()`** (`:460`, called at `ner_helper.py:1311`) — the migration
Mohan described. For each FEATURE value:

1. if it is the generic tag `chemical resistant` → **delete it** and set a flag
2. else if it matches a known chemical term → **move it** to CHEMICAL_RESISTANCE
3. else → keep it in FEATURE

If the generic tag was present and the query contains `resistant`, the **tail of the query after
the first `resistant`** is scanned for chemical terms (`:487-492`).

> ### ⚠️ Word order matters — and most English puts it the wrong way round
>
> `:490` uses `query.partition('resistant')[2]`, i.e. only text **after** the word. ✅ Verified:
>
> | query | result |
> |---|---|
> | `resistant to toluene` | `solvents / non-halogenated solvent` ✅ |
> | `resistant to sulfuric acid` | `acids / sulfuric acid` ✅ |
> | `pom resistant to methanol` | `alcohols / short-chain alcohols (c1-c4)` ✅ |
> | **`toluene resistant`** | **nothing — chemical lost** ❌ |
> | **`sulfuric acid resistant`** | **nothing — chemical lost** ❌ |
> | **`methanol resistant pom`** | **nothing — chemical lost** ❌ |
>
> In the failing cases FEATURE is emptied (the generic tag is always removed) and nothing is added,
> so the chemical **disappears from the output entirely**.
>
> **The fix already exists but is not wired in.** `chem_res_from_query()` (`:500`) scans the
> *whole* query and handles all six cases correctly — ✅ verified — but it is called **0 times** in
> `ner_helper.py`.

Note also that legacy FEATURE values such as `oil resistant` and `fuel resistant` are **not** moved
— they are not chemical terms in the lookup, so step 2 misses them and they stay in FEATURE. Only
the generic `chemical resistant` tag is guaranteed to go.

---

### 18b. MEDICAL_CERT

**Definition.** Biocompatibility testing and regulatory filings — two very different kinds:

| Kind | Count | Source | Examples |
|---|---|---|---|
| ISO 10993 biocompatibility tests | 8 | `NORMALIZED_UNIQUE_VALUES['MEDICAL_CERT']` as `[canonical, [synonyms]]` | `cytotoxicity`, `genetoxicity`, `hemolysis`, `pyrogenicity`, `systemic_toxicity`, `dermal_irritation`, `muscle_implantation`, `physicochemical_compliance` |
| DMF / MAF filings | 24 | hardcoded list, `post_processing.py:520` | `dmf8356`, `maf302` |

**Resolver: 🤖 LLM + validation.**

**`_is_med_cert()`** (`:528`) accepts a value if it is a **canonical key** (underscored) or a
DMF/MAF id. ✅ Verified:

```
'cytotoxicity'        -> True      'dermal irritation'    -> False
'dermal_irritation'   -> True      'muscle implantation'  -> False
'muscle_implantation' -> True      'cell toxicity'        -> False
'dmf8356' / 'DMF 8356'-> True      'gene toxicity'        -> False
```

So the contract is: **the model emits the underscored canonical form**, validation accepts it, and
`:537` converts `_` to a space on output — which is why the live run showed
`MEDICAL_CERT: ["dermal irritation"]`.

**`validate_feature_for_med_cert()`** (`:547`, called at `ner_helper.py:1320`) moves med-cert
values that landed in FEATURE across to MEDICAL_CERT. ✅ Verified:

```
FEATURE=['genetoxicity']     -> FEATURE=[]                MEDICAL_CERT=['genetoxicity']
FEATURE=['dermal_irritation']-> FEATURE=[]                MEDICAL_CERT=['dermal irritation']
FEATURE=['gene toxicity']    -> FEATURE=['gene toxicity'] MEDICAL_CERT=[]      ← still missed
```

This is the fix for *"genetoxicity is tagged MEDICAL_CERT but gene toxicity goes to FEATURE"* —
but only for the **canonical** form. The spaced variants are still absent from the synonym lists,
so `gene toxicity`, `cyto toxicity`, `hemo lysis`, `pyro genicity` remain unhandled.

> ### ⚠️ One invalid value discards the whole extraction
>
> `validate_medical_cert_values()` (`:532-545`):
>
> ```python
> if invalid and not cleaned:
>     val = copy.deepcopy(default_output)   # GRADE, POLYMER, BRAND … all wiped
>     val['MEDICAL_CERT'] = [None]
> ```
>
> If the model returns a single unrecognised MEDICAL_CERT value and no recognised one, **every
> other entity extracted for that query is thrown away**. A very large blast radius for one bad
> value.

> ### ⚠️ DMF / MAF now contradict themselves
>
> `valid_medical_certifications` (`:520`) treats `dmf8356`, `maf302` … as legitimate entity values,
> while `identify_out_of_scope_items` (`:896-905`) still flags `dmf`, `maf` and `iso 10993` as
> out-of-scope. A *"DMF 8356"* query now produces a valid `MEDICAL_CERT` **and** an out-of-scope
> flag. One of the two has to give.

---

# PART C — the cross-cutting machinery

## 19. Out-of-scope filtering — `post_processing.py:474-696`

Runs last, on every path including the fast paths. Two different jobs:

**Job 1 — hide entities the user may not see.** POLYMER, BRAND, FILLER and GRADE are checked
against `outOfScopeData.json` and moved into `outOfScope.entities`.

**GRADE is the subtle one** (`:583-631`), and it is **in-scope-first**:

```
if grade IS in the in-scope list        → keep, done
else if grade IS in the out-of-scope list → flag, done
else → strip the colour code and try again
```

The colour-code strip (`:601-602`) uses `oos_color_code_pattern.txt` (a 900 KB regex) plus a
trailing `-bk`/`black` rule. **This is exactly what caused bug 217995**: `Zytel 101F BK009` sat in
the OOS list, and the in-scope master only held the variant `BKB009`, so the de-confliction never
removed it. A data problem that presented as a model bug.

The lists differ by `user_type` (`:584-589`) — external users get a smaller in-scope list, and
crucially `gradesExternal + gradesInScope` is the external OOS list.

**Job 2 — flag topics the system cannot answer**, by pattern on the raw query (`:646-693`):

| Trigger | Flag |
|---|---|
| `fda`, `food contact`, `food grade` | `fda` |
| `amorphous` | `amorphous` |
| `fmvss` | `fmvss` |
| `cfr 21` | `cfr 21` |
| `cross-link` (any spacing) | `crosslinked` |
| `dmf`, `drug master file` | `drug master file` |
| `maf`, `device master file` | `device master file` |
| `iso 10993` | `iso 10993` |
| `ltha`, `long term heat aging` | `long term heat aging` |
| `usp`, `usp 23`, `usp 88` | `usp` |
| `addictive(s)` | `addictives` |
| `toyota` | `toyota` |

**These are all statements about missing data**, not about language. If you have wondered "why does
the system say it cannot answer FDA questions" — this is why, and it is one list in one file.

## 20. Schema validation — `post_processing.py:350-472`

Runs immediately after the LLM (`ner_helper.py:1293`). It:

1. **deletes** any key the model invented (`:414-419`)
2. **creates** any of the 17 keys the model omitted, as `[]` (`:423-425`)
3. coerces a dict to a single-item list, otherwise empties it (`:426-432`)
4. runs the five structural validators; **any failure empties that entity** (`:434-469`)

That last point matters: a single malformed PROPERTY object silently discards **all** properties
for that query.

## 21. De-duplication — `ner_helper.py:1901-1905`

Order-preserving dedup on every entity list, last thing before returning. Necessary because the
correction rules append liberally — `FEATURE` in particular can receive the same value from a
grade suffix, an eco term and the model itself.

---

# PART D — the business rules you are most likely missing

If you read only one section, read this one. These are the rules that are **pure business
decision** and cannot be inferred from the code's structure:

| # | Rule | Where | Why it exists |
|---|---|---|---|
| 1 | SAP ids start with **2 or 5** and are 8 digits | `ner_helper.py:783` | Celanese ERP number ranges |
| 2 | `PLC 0 is best`, and **HVTR is inverted** | `:359-497` | UL classification convention |
| 3 | **Celstran ⇒ long fibre** | `:1306` | Celstran *is* the long-fibre product line |
| 4 | `eco-r / eco-b / eco-c` are **features hidden inside grade names** | `:1480-1505` | sustainability variants share a base grade |
| 5 | `eco` alone means **sustainable**, not `ecomid` | `:1750` | a genuine error in the synonym table |
| 6 | **Toyota is always out of scope** | `post_processing.py:638` | commercial restriction |
| 7 | FDA / food contact is **out of scope** | `:646` | the data does not exist |
| 8 | **Medical is a feature, not an application** | `:1631` | it describes the material |
| 9 | An auto spec number **implies its OEM** | `:633` | spec numbers are OEM-unique |
| 10 | Competitor **maker names are stripped** from grades | `:1455` | search indexes them without |
| 11 | `pa66gf30` is a **polymer + filler**, never a grade | `:873-888` | naming-collision defence |
| 12 | Filler `±5` and property `±10%` are **search tolerances** | model-side | so near-misses still match |
| 13 | Colour codes are **stripped and retried** against scope | `:601` | one grade, many colours |
| 14 | `user_type` changes **which grades and brands exist** | `:554-568, 584-589` | internal vs public catalogue |
| 15 | PBT→polyester only when the user **did not** type `pbt` | `:1512` | generic beats specific |

---

## 22. Where to look when an entity is wrong

| Symptom | Look here |
|---|---|
| Right value, wrong entity | the reclassify block `ner_helper.py:1365-1441` |
| Entity missing entirely | fast-path guards `:941-945`, then the LLM |
| Value present but renamed oddly | the canonicalisation rules for that entity in `:1443-1885` |
| Number converted unexpectedly | `modifier_unit_conversion` `post_processing.py:122` |
| UL value became `plc N` | `:1806-1824` + the six converters |
| Entity vanished into `outOfScope` | `identify_out_of_scope_items` `post_processing.py:474` |
| Whole entity empty despite a good query | a structural validator emptied it, `post_processing.py:434-469` |
| Query short-circuited to one entity | one of the four fast paths, `:779 / :891 / :938 / :1089 / :1140` |

---

# PART E — whole-query vs partial matching

Everything above answers *"who decides this entity?"*. This part answers the follow-up:
**"was the whole query matched, or only part of it — and against which file?"**

## 23. The five match types

| Code | Name | Meaning | Direction |
|---|---|---|---|
| **W** | whole-query exact | the entire normalised query **equals** a catalog entry | query **=** entry |
| **P⊂** | query inside entry | the query is a **substring of** a catalog entry (user typed a fragment of a longer name) | query **⊂** entry |
| **P⊃** | entry inside query | a known term is **found within** the query | entry **⊂** query |
| **F** | fuzzy | similarity score above a threshold (`thefuzz.token_sort_ratio`) | approximate |
| **R** | regex | structural pattern, no vocabulary | pattern |

**P⊂ and P⊃ are opposite directions and it matters.** `P⊂` is *"is `celanex2002` part of some grade?"*
— it makes short queries resolve. `P⊃` is *"does this query mention `toyota`?"* — it makes long
queries trigger a flag. Confusing the two is the fastest way to misread this codebase.

---

## 24. Whole-query matching (W) — the fast paths

These are the only places where a match ends the request. All operate on the **normalised** query
(punctuation stripped, offset terms removed — see A.2).

| Entity | Line | Test | Data file → key |
|---|---|---|---|
| **MATERIAL_ID** | `:779-783` | `isdigit()` + len 8 + starts `2`/`5` | **none** — pure regex |
| **FEATURE** | `:894` | `search_query == f[0]` (only `pfas-free` returns) | `normalized_unique_values…json` → `FEATURE` ⚠️ |
| **GRADE** | `:953` | `search_query_normalized in [...]` | `normalized_unique_values…json` → `GRADE` |
| **GRADE** | `:956` | `query_for_grade_match in [...]` | same → `GRADE` |
| **COMPETITOR_GRADE** | `:1089` | `query_for_grade_match in [...]` | same → `COMPETITOR_GRADE` |
| **COMPETITOR_GRADE** | `:1091` | `query_for_grade_match in [...]` | same → `COMPETITOR_BRAND` |

Two more whole-value **W** checks run later, on individual entity values rather than the query:

| Where | Line | Test | File → key |
|---|---|---|---|
| BRAND validation | `:1336` | `brand.lower() in [...]` | `normalized_unique_values…json` → `BRAND` |
| Grade out-of-scope | `post_processing.py:610` | `grade_name_normalized in [...]` | `outOfScopeData.json` → `grades` / `gradesExternal` |

---

## 25. Partial matching

### 25a. P⊂ — the query is part of a catalog entry

This is what makes *"celanex 2002"* find *"celanex 2002-2 bk009"*.

| Entity | Line | Test | File → key |
|---|---|---|---|
| GRADE (fast path) | `:958-960` | `any(query in s for s in GRADE)` | `normalized_unique_values…json` → `GRADE` |
| GRADE (token dance) | `:978, :993, :1006` | `temp_norm in nuv_grade` | same → `GRADE` |
| COMPETITOR_GRADE | `:1093-1096` | `any(query in s for s in COMPETITOR_GRADE)` | same → `COMPETITOR_GRADE` |
| AUTO_CERT | `:1151` | `query_cert_norm in auto_cert[0]` | same → `AUTO_CERT` |
| COMPETITOR→GRADE | `:1370` | `any(value in s for s in GRADE)` | same → `GRADE` |
| COMPETITOR→AUTO_CERT | `:1376` | `any(value in auto_cert[0] …)` | same → `AUTO_CERT` |
| GRADE keep | `:1392` | `any(value in s for s in GRADE)` | same → `GRADE` |
| GRADE→COMPETITOR | `:1394` | `any(value in s for s in COMPETITOR_GRADE)` | same → `COMPETITOR_GRADE` |
| GRADE→AUTO_CERT | `:1397` | `any(value in auto_cert[0] …)` | same → `AUTO_CERT` |
| AUTO_CERT validation | `:1428` | `any(cert_norm in auto_cert[0] …)` | same → `AUTO_CERT` |
| Grade scope check | `post_processing.py:595, 596, 612, 618` | `any(grade in s for s in inScope/OOS)` | `outOfScopeData.json` → 4 grade lists |

### 25b. P⊃ — a known term is found inside the query

The query is long; we are looking for a trigger word in it. Almost all of these use **hardcoded
lists in the source**, not dependency files.

| Purpose | Line | Terms | Source of terms |
|---|---|---|---|
| Block the cert path | `:1140-1141` | `tds`, `sds`, `alternative`, `replacement`, `competitor`… | hardcoded |
| Protect competitor labels | `:1373-1374` | same list | hardcoded |
| Carbon capture | `:1549` | `carbon footprint`, `iso 14067`, `ccu` | hardcoded |
| Eco terms | `:1723-1726` via `check_for_terms:698` | `ecoc/ecob/ecor/ecomid` variants | hardcoded |
| E&E industry | `:1650-1673` | 6 patterns for electrical/electronics | hardcoded |
| Bondable | `post_processing.py:529` | `bond*`, `adhesi*`, `cohesi*` | hardcoded |
| OOS brand inside a grade | `post_processing.py:614` | brands longer than 3 chars | `outOfScopeData.json` → `brands` |
| OOS topic flags | `post_processing.py:642-693` | `toyota`, `fda`, `amorphous`, `fmvss`, `cfr 21`, `crosslink`, `dmf`, `maf`, `iso 10993`, `ltha`, `usp`, `addictive` | hardcoded |

### 25c. F — fuzzy matching

Only four places in the whole service use similarity scoring:

| Purpose | Line | Threshold | Compared against |
|---|---|---|---|
| COMPETITOR_GRADE → GRADE | `:1384` | `token_sort_ratio > 80` | `unique_values_22_02_24.json` → `GRADE` |
| GRADE → COMPETITOR_GRADE | `:1416` | `token_sort_ratio > 80` | same |
| Unit lookup | `post_processing.py:107-109` | `> 85` | both unit-conversion CSVs → `Incoming Unit` |
| Exception property | `post_processing.py:182-193` | `> 90` (or `> 80` with "tape") | hardcoded list of 6 properties |

Note the fuzzy pair uses the **readable** vocabulary (`unique_values`), while every exact/substring
test uses the **normalised** one. That is the practical reason both files must ship.

### 25d. Prefix / suffix matching

| Purpose | Line | Behaviour |
|---|---|---|
| Grade starts with a known brand → keep as GRADE | `:1409-1412` | `grade_normalized.startswith(brand)` over `BRAND` |
| Strip maker name off a competitor grade | `:1459-1464` | pop tokens from **both ends** while in `normalized_competitor_names.json` |
| Strip colour code from a grade | `post_processing.py:601` | anchored-to-end regex, `oos_color_code_pattern.txt` |
| Strip `-bk` / `black` suffix | `post_processing.py:602` | hardcoded regex |
| Strip generic words off an APPLICATION | `:1613-1623` | pop `part(s)`, `material(s)` from both ends |

### 25e. R — pure regex, no vocabulary

| Purpose | Line | Pattern |
|---|---|---|
| SAP id | `:779-783` | digits, length 8, leading `2`/`5` |
| Not-a-grade shapes | `:873-888` | 12 patterns over polymer / filler / flame-value codes |
| Filler-only query | `:942`, `:1146` | `\d+(gf\|mf\|gb\|af)` and inverse |
| `pbtpbt` / `petpet` | `:944` | `^(pbt\|pet){2}$` |
| UV suffix in a grade | `:1356` | `(?<=\W\|^\|\d)(uv)(?=\W\|$\|\d)` |
| eco-r/b/c | `:866-868` | `eco\s*[-/\s]?\s*[rbc]$` |
| Moulding | `:1528` | `\bmolding\b.*\bgrade\b` and inverse |

---

## 26. The guards that *stop* a match

Three mechanisms exist purely to prevent false matches. They are the reason the fast paths are
trustworthy at all.

| Guard | Line | Type | Effect |
|---|---|---|---|
| `columnstoIgnore` (1,022) | `:941` | P⊂ | query that is a substring of these is never treated as a grade — filler-like codes `mf74`, `gf28` |
| `columnsforSubstringCheck` (4,142) | `:941`, `:958`, `:1093` | P⊂ / W | these may match **only exactly**, never as a substring — mostly German property names |
| `non_grade_patterns` (12) | `:943`, `:1147` | R | polymer+filler+flame-value shapes are never grades |
| `COMPETITOR_BRAND` | `:951` | W | a competitor brand abandons the grade path entirely |
| length | `:945`, `:1148` | — | query must exceed 2 (grade) or 3 (cert) characters |
| `nsf` | `:1095` | W | explicitly excluded from the competitor substring test |

---

## 27. Consolidated map — entity × match type × file

| Entity | W | P⊂ | P⊃ | F | R | Dependency file(s) used |
|---|:--:|:--:|:--:|:--:|:--:|---|
| MATERIAL_ID | ✔ | | | | ✔ | *none* |
| GRADE | ✔ | ✔ | ✔ | ✔ | ✔ | normalized_unique_values, unique_values, outOfScopeData, oos_color_code_pattern |
| COMPETITOR_GRADE | ✔ | ✔ | ✔ | ✔ | | normalized_unique_values, unique_values, normalized_competitor_names |
| AUTO_CERT | | ✔ | ✔ | | | normalized_unique_values → `AUTO_CERT` |
| BRAND | ✔ | | ✔ | | | normalized_unique_values → `BRAND`, outOfScopeData → `brands_*` |
| FEATURE | ✔ | | ✔ | | ✔ | normalized_unique_values → `FEATURE` (41 entries) |
| POLYMER | | | ✔ | | | outOfScopeData → `polymers` |
| FILLER | | | | | | outOfScopeData → `fillers` (P⊃ on the value, not the query) |
| PROPERTY | | | | ✔ | ✔ | unit-conversion CSVs, ul_list_name_value |
| **MEDICAL_CERT** | ✔ | | ✔ | | | normalized_unique_values → `MEDICAL_CERT` (8) + hardcoded DMF/MAF list |
| **CHEMICAL_RESISTANCE** | ✔ | | ✔ | | | **chemical_resistance.json** (583 searchable terms) |
| APPLICATION | | | ✔ | | | *none* (hardcoded word lists) |
| INDUSTRY | | | ✔ | | ✔ | *none* (hardcoded map) |
| PROCESSING | | | ✔ | | ✔ | *none* |
| REGION, DELIVERY_FORM, RAILWAY/WATER/NSF_CERT | | | | | | *none* — LLM only |

Read the empty rows carefully: **six of the nineteen entities are matched against no reference
data at all.** They are whatever the model says, plus a hardcoded rename or two.

The two new entities arrived with reference data from day one — `CHEMICAL_RESISTANCE` is the only
entity whose *value* is looked up rather than trusted (`resistance_level` is backfilled, §18a).

---

## 28. ✅ Resolved — the `FEATURE` key (and what replaced the finding)

**Earlier state.** `ner_helper.py:893` reads `NORMALIZED_UNIQUE_VALUES['FEATURE']`, but that key
did not exist in the repo's data file — which would raise `KeyError` on **every** query, before any
fast path.

**Now fixed.** The 11-Aug commit added it, in exactly the shape the code expects:

```json
"FEATURE": [["anti-static",  ["anti-static", "static resistant", "static", ...]],
            ["bio-content",  ["bio-content", "bio-based", "bio", "biobased", "eco-b"]], ... ]
```

`f[0]` is the canonical value, `f[1]` the synonym list — the same pair shape as `AUTO_CERT`.
41 entries.

✅ **Verified end to end** — `pfas-free` now takes the fast path:

```
pfas-free   ->   FAST-PATH FEATURE     (was: fell through to the LLM)
```

All ten keys the code reads are now present:

| Key | Entries |
|---|---|
| `columnstoIgnore` | 1,022 |
| `GRADE` | 21,225 |
| `COMPETITOR_GRADE` | 56,885 |
| `columnsforSubstringCheck` | 4,143 |
| `BRAND` | 71 |
| **`FEATURE`** | **41** ← new |
| **`MEDICAL_CERT`** | **8** ← new |
| **`CHEMICAL_RESISTANCE`** | **11** ← new |
| `AUTO_CERT` | 1,171 |
| `COMPETITOR_BRAND` | 875 |

### The lesson that outlives the bug

This file is now loaded **twice** — once in `score.py:init()` and again at **module import** in
`post_processing.py:521-524`, to build `med_cert_lookup`. The import-time load means a malformed
copy no longer fails at startup, it fails at **`import post_processing`** — i.e. before `init()` is
ever reached, with a bare `JSONDecodeError` and no context.

That is exactly what happened on 11-Aug: the file arrived truncated, then spliced, and the service
could not start. Two independent repairs were needed before it parsed. **These files are large,
not in git, and hand-copied — verify them before trusting anything downstream:**

```bash
python -c "import json; d=json.load(open('dependencies/normalized_unique_values_for_grade_mapping.json',encoding='utf-8')); print(len(d),'keys'); [print(' ',k,len(v)) for k,v in d.items()]"
```

Ten keys with plausible counts = good. Anything else = stop and regenerate from
`Development files/2. Create normalized Grade and Competitor Grade names.ipynb` rather than
re-copying.

---

⬅️ Back to [`00-README-START-HERE.md`](00-README-START-HERE.md) · related:
[`11-rulebased-vs-llm.md`](11-rulebased-vs-llm.md) ·
[`13-how-ner-prediction-works.md`](13-how-ner-prediction-works.md) ·
[`17-dependencies-files-explained.md`](17-dependencies-files-explained.md) ·
[`04-file-by-file.md`](04-file-by-file.md)

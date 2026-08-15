# 17. The `dependencies/` folder — every file explained 📦

> The NER service has **no database at serving time**. Everything it knows that is not in the
> model's weights lives in this one folder, loaded once at container start.
>
> ~12 MB — **10 files are live, 4 are dead weight, 1 is config.**
>
> *Updated for the 11-Aug-2026 commit: `chemical_resistance.json` added (§5a), three new keys in
> the normalized index (§3), and the bug-217995 scope fix merged in (§4).*

A miniature copy of every file, same schema and real rows, is in
[`dependencies-sample/`](dependencies-sample/) — 44 KB instead of 12 MB. Regenerate it with
`python make_dependencies_sample.py`.

---

## 1. The load map

Everything is read in `score.py:init()` (lines 72-136) and packed into the `DEPENDENCIES` dict at
`score.py:144-163`, which is then handed to `run_ner()` on every request.

| # | File | Size | Loaded at | Becomes | Read by |
|---|---|---|---|---|---|
| 1 | `unique_values_22_02_24.json` | 2.3 MB | `score.py:78` | `UNIQUE_VALUES`, `GRADE_NAMES` | fuzzy reclassification, units list |
| 2 | `normalized_unique_values_for_grade_mapping.json` | 1.6 MB | `score.py:83` | `NORMALIZED_UNIQUE_VALUES` | **all four fast paths** |
| 3 | `outOfScopeData.json` | 725 KB | `score.py:91` | `OUT_OF_SCOPE_DATA` | scope filtering |
| 4 | `oos_color_code_pattern.txt` | 898 KB | `score.py:95` | `OOS_COLOR_CODE_PATTERN` | colour-code stripping |
| 5 | `ul_list_name_value.json` | 13 KB | `score.py:99` | `UL_LIST_NAME_VALUE`, `UL_TERMS` | UL property recognition |
| 6 | `final_unit_conversion_table.csv` | 46 KB | `score.py:72` | `UNIT_CONVERSION_TABLE_GENERAL` | unit conversion |
| 7 | `final_unit_conversion_table_for_exeptions.csv` | 8 KB | `score.py:75` | `..._FOR_EXEPTIONS` | unit conversion (6 special properties) |
| 8 | `normalized_competitor_names.json` | 20 KB | `score.py:87` | `NORMALIZED_COMPETITOR_NAMES` | stripping maker names off competitor grades |
| 9 | `abbreviations.xlsx` | 23 KB | `score.py:104-111` | `ABBREVIATIONS` | **loaded but effectively unused** (see §9) |
| **10** | **`chemical_resistance.json`** | **23 KB** | **`post_processing.py:18`** | `valid_format` | **CHEMICAL_RESISTANCE — see §5a** |
| — | `outOfScopeData_new.json` | 733 KB | never | — | superseded — its fix is now *in* `outOfScopeData.json` |
| — | `unique_values_22_02_24_index.json` | 2.2 MB | never | — | dead |
| — | `unique_values_22_02_24_preprocessed.json` | 3.1 MB | never | — | dead |
| — | `model-best/` | empty | never | — | dead (retired spaCy model) |
| — | `.amlignore` | 322 B | n/a | — | Azure ML upload config |
| — | `3. OOS Color codes.ipynb` | 15 KB | never | — | ⚠️ a **notebook** copied into `dependencies/` by mistake — belongs in `Development files/` |

> **Two loaders, not one.** Since the 11-Aug commit, `post_processing.py` reads two files at
> **module import** (`:18` and `:521`) rather than through `score.py:init()`. A malformed copy of
> either now fails at `import post_processing` — before `init()` runs — so the traceback shows a
> bare `JSONDecodeError` with no clue which file it was. Worth knowing when a container refuses to
> start.

**Origin.** Almost all of it is generated offline from **Snowflake** `ANALYTICS_DEV.GST_CURATED`
(tables `SPT`, `competitor_data`, `SYNONYM`, `CTQ`, `OUT_OF_SCOPE_*`) plus an **Azure APIM**
UI-properties call, by the notebooks in `Development files/`. See §14 for which notebook builds
what.

---

## 2. `unique_values_22_02_24.json` — the master vocabulary

**Purpose.** The human-readable list of every value the system knows, per entity type. This is the
**fuzzy-match** side of the house.

**Shape:** a flat dict of 16 lists of strings.

```json
{
  "BRAND":            ["ateva", "celanex", "celanyl", "celcon", "celstran", ...],
  "POLYMER":          ["abs", "acetal", "acetal copolymer", "pa66", "pom", ...],
  "GRADE":            ["celanex 1401a", "hostaform c 9021", ...],
  "COMPETITOR_GRADE": ["2200j", "ultramid a3wg6", ...],
  "...": []
}
```

| Key | Count | What it holds |
|---|---|---|
| `BRAND` | 64 | Celanese trade names |
| `POLYMER` | 229 | base chemistries incl. long forms and the `pa*` wildcard |
| `PROPERTY` | 3,585 | every property name incl. the ISO/ASTM-suffixed forms |
| `FEATURE` | 862 | qualitative characteristics |
| `FILLER` | 782 | filler names **and** coded loads (`10gf`, `30glass`) |
| `GRADE` | 1,997 | Celanese grades (readable form) |
| `CERTIFICATION` | 3,116 | certificate identifiers |
| `COMPETITOR_GRADE` | 8,822 | competitor products |
| `APPLICATION` | 22,475 | the largest list — end uses |
| `MODIFIER` | 1,715 | value+unit strings seen in queries |
| `UNIT` | 265 | measurement units |
| `FILLER_PERCENTAGE` | 14 | canonical load percentages |
| `GRADE_WITHOUT_BRAND` | 1,865 | grade codes with the brand removed |
| `COMPETITOR_GRADE_TRANSFORMED` | 18,064 | competitor grades, normalised variants |
| `COMP_GRADE_WITHOUT_BRAND` | 9,142 | competitor codes minus maker |
| `COMP_GRADE_TRANSFORMED_WITHOUT_BRAND` | 14,300 | both transforms combined |

**Who reads it**

- `score.py:81` → `GRADE_NAMES = UNIQUE_VALUES['GRADE']`, used by the two fuzzy reclassification
  rules at `ner_helper.py:1384` and `:1416` (`thefuzz.token_sort_ratio > 80`)
- `score.py:127` → `get_filtered_values()` walks **every** list to collect words containing
  `.`, `-`, `/` plus all units; the result drives `add_spaces()` in `pre_processing.py:8`, which
  decides where punctuation may be split. This is why the file must be loaded even though only two
  rules query it directly.
- `ner_helper.py:1336` → BRAND validation uses the *normalized* file, not this one — easy to
  confuse.

**If it were missing:** `init()` crashes on the first `pd.read_csv`/`json.load`. Nothing starts.

**Gotchas**
- The last four keys are **derived transforms**, not new knowledge — they exist so a competitor
  grade can be matched with or without the maker's name.
- `FILLER` mixes two different things: names (`glass fiber`) and coded loads (`30gf`).
- The date in the filename (`22_02_24`) is the extract date and is now stale; nothing enforces it.

---

## 3. `normalized_unique_values_for_grade_mapping.json` — the fast-path index

**Purpose.** The **exact-match** side. Same knowledge as file 2 but punctuation-stripped and
lowercased, so `PA6-GF30-01`, `pa6 gf30 01` and `PA6GF3001` all collapse to one key.

**Shape:** dict of **10** lists (was 7 before the 11-Aug commit). Some are lists of strings; four
are lists of **pairs**.

```json
{
  "GRADE":                    ["celanex20022", "hostaformc9021", ...],
  "COMPETITOR_GRADE":         ["ultramida3wg6", ...],
  "COMPETITOR_BRAND":         ["platamid", "isoglasslft", ...],
  "BRAND":                    ["ateva", "celanex", ...],
  "AUTO_CERT":                [["ms50017cpn5448", "stellantis-chrysler"], ...],
  "FEATURE":                  [["bio-content", ["bio-content","bio-based","bio","eco-b"]], ...],
  "MEDICAL_CERT":             [["cytotoxicity", ["cytotoxicity","cell toxicity","cyto",...]], ...],
  "CHEMICAL_RESISTANCE":      [["acids", [["formic acid", "limited resistance, short-term exposure",
                                           ["methanoic acid","hcooh", ...]], ...]], ...],
  "columnstoIgnore":          ["mf74", "gf28", "glass26", ...],
  "columnsforSubstringCheck": ["dielektrischerverlustfaktor", "trüb", ...]
}
```

| Key | Count | Role |
|---|---|---|
| `GRADE` | 21,225 | fast-path grade lookup |
| `COMPETITOR_GRADE` | 56,885 | fast-path competitor lookup |
| `COMPETITOR_BRAND` | 875 | maker names; also **blocks** the grade path at `ner_helper.py:951` |
| `BRAND` | 71 | BRAND validation `ner_helper.py:1336` |
| `AUTO_CERT` | 1,171 | `[normalised_cert, oem]` — this is how a spec number implies its carmaker |
| **`FEATURE`** | **41** | `[canonical, [synonyms]]` — drives the pfas-free fast path at `:893` |
| **`MEDICAL_CERT`** | **8** | `[canonical, [synonyms]]` — builds `med_cert_lookup` at `post_processing.py:524` |
| **`CHEMICAL_RESISTANCE`** | **11** | category → sub-category → synonyms (mirrors `chemical_resistance.json`) |
| `columnstoIgnore` | 1,022 | strings that *look* like grades but are not |
| `columnsforSubstringCheck` | 4,143 | must match **exactly**, never as a substring |

**The two guard lists are the interesting part.** They encode a hard-won lesson: substring
matching against 21k grade names produces false positives. `columnstoIgnore` holds filler-like
codes (`mf74`, `gf28`); `columnsforSubstringCheck` holds mostly **German property names** and other
long words that would otherwise be swallowed by a substring test.

**Who reads it:** every fast path — `ner_helper.py:941` (guards), `:951-960` (grade), `:1089-1096`
(competitor), `:1150` (auto cert) — plus BRAND validation `:1336` and the reclassification rules
`:1368-1437`.

**If it were missing:** no fast path ever fires; every query goes to the LLM; grade lookups get
much worse. The service still runs.

**Gotcha:** it has **10× more grades** (21,029) than file 2 (1,997), because it includes every
colour and packaging variant. The two files are **not** two views of the same list.

---

## 4. `outOfScopeData.json` — the visibility rules

**Purpose.** What a given user is **not allowed to see**. This is commercial policy expressed as
data.

**Shape:** dict of 10 lists of normalised strings.

```json
{
  "grades":                ["ateva9020", "zenitefg77340bk011", ...],   // 11,947
  "gradesExternal":        [...],                                       // 11,960
  "gradesInScope":         ["stp6sd001a30nat", ...],                    //  6,607
  "gradesInScopeExternal": ["kepm25ecob", ...],                         //  4,590
  "brands":                ["omnilon", "ecomid", "forflex", ...],       //     36
  "brands_internal":       [],                                          //      0
  "brands_commerical":     ["pipelon", "ecomid", "vitaldose", ...],     //      7
  "brands_not_in_scope":   ["im", "omnilon", "forflex", ...],           //     50
  "polymers":              ["ps", "ptt", "pa12", ...],                  //     23
  "fillers":               ["natural organic fiber"]                    //      1
}
```

**The logic is in-scope-first** (`post_processing.py:583-631`):

```
if grade IS in the in-scope list          → keep it
else if grade IS in the out-of-scope list → flag it
else → strip the colour code, try both lists again
```

**Which pair of lists is used depends on `user_type`** (`post_processing.py:584-589`):

| user_type | in-scope list | out-of-scope list |
|---|---|---|
| `internal` | `gradesInScope` | `grades` |
| anything else | `gradesInScopeExternal` | `gradesExternal` **+ `gradesInScope`** |

That last cell is the subtle one: for external users, everything that is *internal-only in scope*
is added to the out-of-scope list. Internal-visible ≠ public.

**Brands** are scoped separately (`:548-568`) using the three `brands_*` lists.
`brands_internal` is **empty**, so the internal branch only ever protects `brands_commerical`.

**This file caused bug 217995.** `Zytel 101F BK009` sat in `grades` and was missing from
`gradesInScope`, so the de-confliction (`OOS − in-scope`) never removed it.

> ### ✅ Resolved by the 11-Aug-2026 commit
>
> The corrected data is now **in the file the code actually loads**. Verified against the two bug
> grades:
>
> | grade | in `grades` | in `gradesInScope` | verdict |
> |---|---|---|---|
> | `zytel101fbk009` | False | True | **in scope ✅** |
> | `zytel103hslbk080` | False | True | **in scope ✅** |
>
> List sizes moved accordingly: `grades` 11,947 → 11,410 · `gradesInScope` 6,607 → **7,303** ·
> `gradesInScopeExternal` 4,590 → **5,401** · `brands` 36 → 28 · `polymers` 23 → 18.
>
> `outOfScopeData_new.json` is now **redundant** — it was the staging copy of this fix. It is still
> sitting in `dependencies/` and should be deleted to avoid confusion about which file is live.

---

## 5a. `chemical_resistance.json` — the chemical taxonomy *and* the verdicts

**New in the 11-Aug-2026 commit.** 23 KB. Loaded at **`post_processing.py:18`**, at module import,
into the global `valid_format`.

**Purpose.** Two jobs at once: recognise which chemical a user named, and supply the answer for
that chemical. It is the only dependency file that carries a **verdict**, not just vocabulary.

**Shape:** dict keyed by chemical category; each value a list of sub-category objects.

```json
{
  "acids": [
    { "sub_category":     "formic acid",
      "resistance_level": "limited resistance, short-term exposure",
      "temperature":      "23",
      "synonyms": ["methanoic acid", "hcooh", "concentrated formic acid >85%",
                   "formate acid", "ant sting acid", ...] },
    ...
  ],
  "alcohols": [...], "alkalies/bases": [...], "coolants": [...], "fuels": [...],
  "hydrocarbons": [...], "oils & greases": [...], "oxidizers": [...],
  "phenolic compounds": [...], "solvents": [...], "water & aqueous solutions": [...]
}
```

**11 categories · 25 sub-categories.** At import (`post_processing.py:24-45`) it is flattened into
four lookups:

| Global | Contents |
|---|---|
| `valid_categories` | the 11 category names |
| `valid_sub_categories` | category → set of its sub-categories |
| `valid_resistance_levels` | **`(category, sub_category)` → the canonical verdict** |
| `chem_term_to_entry` | **583 searchable terms** (categories + sub-categories + every synonym) → `(category, sub_category)` |

That last one is the workhorse: 583 surface forms collapse onto 25 canonical pairs.

**Who reads it**

- `validate_chemical_resistance_values()` (`:399`) — validates the model's category/sub-category
  and **overwrites** `resistance_level` from `valid_resistance_levels`, forcing `temperature` to
  `'23'`. The model's verdict is discarded.
- `reclassify_feature_to_chem_res()` (`:460`) — moves chemical signals out of `FEATURE`.
- `chem_res_from_query()` (`:500`) — builds entries straight from the query text. **Currently never
  called** (see [`16-…`](16-entity-by-entity-resolution.md) §18a).

**The design point worth understanding.** `resistance_level` is not something a query can tell you
— *"is PA66 OK in methanol?"* contains no answer. Putting the verdict in the reference data and
having the code overwrite whatever the model guessed is the right split: **the model names the
chemical, the data supplies the outcome.**

**Gotcha:** three synonyms legitimately contain commas — `"cetyl alcohol, c16"`,
`"stearyl alcohol, c18"`, `"motor oil os206 304 ref.eng.oil, isp"`. Any script that splits this
file on commas rather than parsing it as JSON will corrupt them.

---

## 5. `ul_list_name_value.json` — the UL yellow-card dictionary

**Purpose.** Recognise UL electrical-safety properties, their many spellings, and their legal
values. The densest piece of domain knowledge in the folder.

**Shape:** dict keyed by the canonical property name; 28 entries.

```json
{
  "comparative tracking index (cti)": {
    "synonyms":       ["comparative tracking", "cti", "comp tracking", ...],
    "values":         ["plc 0", "plc 1", ..., "plc-5"],
    "has_thickness":  false,
    "value_priority": true
  }
}
```

| Field | Meaning |
|---|---|
| `synonyms` | every way a user might write the property |
| `values` | the legal result values (PLC bands, flame ratings, `f1`/`f2`, `compliant`, `yes`) |
| `has_thickness` | whether the result is only meaningful **at a stated thickness** — true for 9 of 28 |
| `value_priority` | whether the value matters more than the property name when disambiguating |

**The 28 properties** include CTI, HAI, HWI, HVTR, arc resistance, flame rating, flammability
classification, glow-wire (3 variants), RTI (4 variants), dielectric strength, dimensional change,
outdoor suitability, detergent resistance, RoHS, non-halogenated, mechanically recycled content,
ball pressure test, surface resistivity, tensile/Charpy impact.

**Who reads it:** `score.py:129-136` flattens names + synonyms + values into `UL_TERMS`, which
feeds pre-processing. The **values** are what let `plc 0` survive as a value rather than being
parsed as a number.

**`has_thickness` is real domain knowledge:** a UL flame rating is certified *at a thickness*
(V-0 @ 0.4 mm ≠ V-0 @ 1.5 mm). That is why the model emits `minimum thickness (mm)` alongside a
flame rating — it is a companion field, not noise.

---

## 6 & 7. The two unit-conversion tables

**Purpose.** Users type GPa; the database stores MPa. These tables carry the arithmetic.

**Shape:** identical 3-column CSV.

```csv
Incoming Unit,ceed_unit,formula
gpa,MPa,(x)*1000
psi,MPa,(x)*0.00689476
ºf,°C,((x) - 32)*(5/9)
g/cm3,kg/m³,(x)*1000
ft-lb/in2,kJ/m²,(x)*2.10152
in/in,%,(x)*100
```

| Column | Meaning |
|---|---|
| `Incoming Unit` | what the user might type (1,442 distinct spellings) |
| `ceed_unit` | the canonical unit Chemille/CEED stores (32 distinct) |
| `formula` | a Python-evaluable expression where `x` is the incoming value |

| File | Rows | Used when |
|---|---|---|
| `final_unit_conversion_table.csv` | 1,496 | the general case |
| `final_unit_conversion_table_for_exeptions.csv` | 286 | six properties where the conversion differs |

**The six exceptions** (`post_processing.py:182-193`): bulk density, flexural modulus tape, tensile
modulus tape, specific resistivity, average particle size, inclined-plane tracking. For these the
same unit string converts a different way — e.g. `mohm*cm` means *milli*ohm (`x/1000`) in one row
and *mega*ohm (`x*1000000`) in another, resolved by which property is being measured.

**How it runs** (`post_processing.py:122-226`):

1. skip if the unit is already canonical — `"", %, v, volt, volts, °c, c, d` (`:181`)
2. decide general vs exception table by fuzzy-matching the **property name** (`:189-193`)
3. fuzzy-match the **unit** with `token_sort_ratio > 85` (`:109`)
4. rewrite the unit as **`old<->new`** (`:206`) — e.g. `gpa<->mpa`, so downstream can see it happened
5. apply the formula to `value`, `min` and `max` independently (`:207-223`)

**Gotcha:** the formula is executed by string substitution into an eval-style helper
(`string_to_number`, `:54`). A malformed formula fails silently — each conversion is wrapped in a
bare `try/except: pass`.

---

## 8. `oos_color_code_pattern.txt` — the colour-code stripper

**Purpose.** One enormous regex that recognises **colour codes** appended to grade names, so
`Zytel 101F BK009` can be reduced to `Zytel 101F` and re-checked against the scope lists.

**Shape:** a single line, 897,930 characters, **43,667 alternations**.

```
([\s\(-]|^)(  ^30[-./\s()]*5436[-./\s()]*light[-./\s()]*grey$
            | ^247c$
            | (?:20[-./\s()]*4030)
            | p904a
            | ...
           )[-./\s()]*$
```

Three alternation styles:

| Style | Count | Share | Behaviour |
|---|---|---|---|
| `^code$` anchored | 19,202 | 44% | matches only when the code is the whole remaining string |
| `(?:code)` group | 16,804 | 38% | matches anywhere before the trailing separator |
| `code` bare | 7,660 | 18% | same as a group, no wrapper |

`[-./\s()]*` appears between the tokens of a multi-word code (52% of alternations contain it), so
`BK 009`, `BK-009` and `BK009` all match. 7,818 codes are single tokens with no separator at all.

### ⚠️ Three defects in the generated pattern

1. **4 alternations match the empty string** — e.g.
   `(?:[-./\s()]*[-./\s()]*[-./\s()]*...)`, 124 characters of nothing but repeated separator
   classes. They come from source rows whose colour code was blank or punctuation-only. Effect is
   mild (they strip trailing separators) but they are junk in a 900 KB regex.

2. **Collisions with filler codes and plain numbers.** The list is not restricted to colour-like
   tokens:

   | Kind | Count | Examples |
   |---|---|---|
   | pure numbers | 1,883 | `00`, `000`, `0001`, `1070`, `30` |
   | filler-shaped | 38 | `af3001`, `cf2001`, and `gf30` |
   | 1-2 characters | 159 | `00`, `01`, `10`, `0c`, `0m` |

   Verified consequences:

   ```
   'pom gf30'    →  'pom'      (gf30 is registered as a colour code)
   'ateva 1070'  →  'ateva'    (1070 likewise)
   ```

3. **The truncated name is written back.** `post_processing.py:607` appends the stripped name to
   `updated_grade_names`, and `:631` assigns that list to `result["GRADE"]`. So the shortened grade
   is what the caller receives, even when nothing is flagged out of scope.

**Blast radius is bounded** — the strip only runs inside the *"grade was not found in the in-scope
list"* branch (`:595`). A recognised grade is never touched. But an unrecognised one can be
truncated, and the truncation is what gets searched.

**Who reads it:** `post_processing.py:601`, immediately followed by a hand-written rule for the
commonest case (`:602`):

```python
grade_name_updated = re.sub(OOS_COLOR_CODE_PATTERN, '', grade_name).rstrip()
grade_name_updated = re.sub(r"([-,/ ])(bk|black)$", '', grade_name_updated)
```

**Verified behaviour** against the real pattern:

| Input | Output |
|---|---|
| `zytel 101f bk009` | `zytel 101f` |
| `celanex 2002-2 nc010` | `celanex 2002-2` |
| `hostaform c 9021 247c` | `hostaform c 9021` |
| `vectra a130 bk` | `vectra a130` |
| `celanex 2002-2` | `celanex 2002-2` (unchanged) |
| `celanyl xs3 gf60 bg 1019/c ef` | `celanyl xs3 gf60` |

> That last row is the grade in the open investigation noted in `CLAUDE.md`
> (*"Celanyl XS3 GF60 BG 1019/C EF — 0 results despite in-scope"*). The stripper removes
> `bg 1019/c ef`, so the search runs on a shortened name. Worth checking whether that is the cause.

**Gotcha:** a 900 KB regex is compiled on **every** grade check. It is not pre-compiled anywhere —
Python's internal regex cache carries it, but any change to the string forces a recompile.

---

## 9. `normalized_competitor_names.json` — maker names to strip

**Purpose.** The list of competitor **company/brand** words that must be removed from the front and
back of a competitor grade, because the downstream search indexes competitor grades without them.

**Shape:** a flat list of 1,165 lowercase strings.

```json
["nico", "lh-plastics", "matrix polymers ltd", "corp.", "international",
 "molded fiber glass", "usi", "poliblend", "vamp", ...]
```

Note it holds both real makers (`poliblend`) and **legal-form fragments** (`corp.`,
`international`, `ltd`) — because those trail company names in the source data.

**Who reads it:** `ner_helper.py:1455-1469` — words are popped from the start while they appear in
this list, then from the end.

```
"ultramid a3wg6"  →  "a3wg6"
```

**Gotcha:** it only strips from the **ends**. A maker name in the middle survives.

---

## 10. `abbreviations.xlsx` — loaded, but effectively unused

**Purpose (original).** Expand short forms into full property / filler / feature names.

**Shape:** four sheets.

| Sheet | Rows | Columns | Example row |
|---|---|---|---|
| `PROPERTY` | 367 | `PROPERTY`, `Abbreviations` | `abrasion resistance` ← `abrres` |
| `FILLER` | 62 | `FILLER`, `Abbreviations` | `aramide fiber` ← `af` |
| `FEATURE` | 63 | `FEATURE`, `Abbreviations` | `chlorine resistant` ← `cl` |
| `common_abb` | 39 | `WORDS` | `al`, `bayshore`, `ca`, `cs`, `dc` |

Loaded at `score.py:104-125`, lowercased, and **sorted by abbreviation length descending** so the
longest abbreviation wins.

**The catch.** The only consumer is `replace_abbreviation()` (`ner_helper.py:136-358`), and its own
docstring says (`:150`):

> *"It was used in previous version of the NER Model but the latest version of the model does not
> need this."*

`replace_abbreviation` is **never called** anywhere in `run_ner()`. The fine-tuned model learned
the abbreviations directly. So the file is parsed on every container start and then ignored.

`common_abb` deserves a mention: it is a **stop-list of dangerous abbreviations** — `al`, `ca`,
`cs`, `dc` are all real words or brand fragments, so the expansion logic refuses to touch a name
containing them.

---

## 11. `.amlignore`

Azure ML upload config, auto-generated. Excludes `.ipynb_aml_checkpoints/`, `*.amltmp`,
`*.amltemp` from the snapshot uploaded at deploy time. Not read by the service.

---

## 12. The dead files

| File | Size | Why it is dead |
|---|---|---|
| `outOfScopeData_new.json` | 733 KB | **Now redundant** — its fix was merged into `outOfScopeData.json` on 11-Aug. Safe to delete |
| `unique_values_22_02_24_index.json` | 2.2 MB | 8 keys of indexed/expanded property names, e.g. `arc resistance internal (s)`. Built for the retired spaCy matcher |
| `unique_values_22_02_24_preprocessed.json` | 3.1 MB | 8 keys of the same values after preprocessing. Same era |
| `model-best/` | empty | Contains only a `.amlignore`. The retired spaCy model directory |

Together that is **6 MB of the 12 MB** shipped in the model artifact for no runtime benefit. They
also mislead: someone reading the folder reasonably assumes `_new` is the file in use.

---

## 13. What breaks if a file goes missing

| File | Effect |
|---|---|
| any of the 9 live files | `init()` raises → **container never starts** (`User container has crashed`) |
| `normalized_unique_values...` | *(hypothetically)* all fast paths dead, every query hits the LLM |
| `outOfScopeData.json` | no scope filtering — external users could see internal grades |
| `ul_list_name_value.json` | UL properties parsed as ordinary numbers; PLC conversion never fires |
| unit tables | GPa stays GPa; search compares against MPa and returns nothing |
| colour pattern | `Zytel 101F BK009` never simplified to `Zytel 101F` — more false out-of-scope |

Note the first row: `init()` has **no error handling**. A missing or corrupt file is a hard start
failure, which is why `CLAUDE.md` flags that these files are not in git and must be restored on a
fresh checkout.

---

## 14. Where each file comes from

Verified by grepping every generator notebook for its Snowflake tables and HTTP calls.

| File | Built by | Upstream source |
|---|---|---|
| `outOfScopeData.json` | `Development files/1. Clean out of scope Data.ipynb`, and now `automation/refresh_oos.py` | Snowflake `GST_CURATED.OUT_OF_SCOPE_BRANDS` / `_POLYMERS` / `_GRADES` / `_FILLERS`, plus `SPT` and `SYNONYM` for de-confliction |
| `normalized_unique_values_for_grade_mapping.json` | `2. Create normalized Grade and Competitor Grade names.ipynb` | Snowflake `GST_CURATED.AUSP_SAP_MATERIAL_COLOR_CODE` + `comp_offset_json_property_mapping`, **plus** the UI-Properties API, **plus** an Elasticsearch call |
| `normalized_competitor_names.json` | same notebook | same |
| `oos_color_code_pattern.txt` | `3. OOS Color codes.ipynb` | Snowflake `GST_CURATED.AUSP_SAP_MATERIAL_COLOR_CODE` |
| `unique_values_22_02_24.json` | `Create unique values/1 - Create Unique Values File.ipynb`, `Clean unique values.ipynb`, `NER_Training/1 Data for NER.ipynb` | **UI-Properties API** `apim-gst-dev.azure-api.net/func-uiproperties-d-ussc-01`, plus curated files in `uv files/` (`SPT.csv`, `Celanese website cleaned.xlsx`, `property_name 6 cleaned.xlsx`) |
| `final_unit_conversion_table.csv` (+ exceptions) | `Generate Unit Conversion table/Unit conversion tables.ipynb` | hand-built `Unit_conversions.xlsx` + `conversion_table{,2,3}.csv` — **no database** |
| `abbreviations.xlsx` | `Create unique values/1 - …ipynb` | `uv files/Abbreviations-Synonyms List.xlsx` v1/v2 — **SME-curated, no database** |
| `ul_list_name_value.json` | **nothing in the repo writes it** | UL 746 domain knowledge; most likely saved by hand from the UI-Properties API `results['UL']` |
| `chemical_resistance.json` | **nothing in the repo writes it** | hand-maintained; arrived with the Aug-2026 commit |

### Only two upstream systems, plus hand-curation

1. **Snowflake** — account `celanese-celanytics.privatelink`, database `ANALYTICS_DEV`,
   schema **`GST_CURATED`**, warehouse `reporting_wh`. SSO over VPN in the notebooks;
   `automation/refresh_oos.py` uses key-pair auth with secrets from Key Vault.
   Tables used: `SPT`, `COMPETITOR_DATA`, `SYNONYM`, `AUSP_SAP_MATERIAL_COLOR_CODE`,
   `comp_offset_json_property_mapping`, `OUT_OF_SCOPE_{BRANDS,POLYMERS,GRADES,FILLERS}`.
2. **UI-Properties API** — `POST https://apim-gst-dev.azure-api.net/func-uiproperties-d-ussc-01/func-ui-properties`
   with an `Ocp-Apim-Subscription-Key`. An Azure Function fronting the product's own
   vocabulary. This is why FEATURE has 41 values and DELIVERY_FORM 5 — **the product owns
   those lists, not NER.**
3. **Hand-curated spreadsheets** — unit conversions, abbreviations, UL values, chemical
   resistance taxonomy. No pipeline; someone edits a file.

### Nothing is fetched at request time

Every file above is a **static artefact baked into the registered model
`gst-gpt-ner-model`** and read once in `score.py:init()`. At inference the service makes
exactly one network call — to Azure OpenAI. **No Snowflake, no API, no database on the
request path.** Refreshing reference data therefore means bumping the model version and
redeploying, which is precisely why the Zytel fix (bug 217995) needed a deployment even
though it was a pure data change.

**The dependency chain that matters:** a data problem in Snowflake becomes a NER bug three steps
later, and looks like a model failure. Bug 217995 was exactly this. Before blaming the model,
check the file.

---

## 15. Reviewing the sample folder

```
KT learning/dependencies-sample/          44 KB, same schema, real rows
├── unique_values_22_02_24.json            5 values × 16 keys
├── normalized_unique_values_...json       5 values × 7 keys
├── outOfScopeData.json                    5 values × 10 keys
├── outOfScopeData_new.json                5 values × 10 keys  (dead file, for comparison)
├── ul_list_name_value.json                3 of 28 UL properties, complete
├── oos_color_code_pattern.txt             6 of 43,667 alternations — still compiles
├── final_unit_conversion_table.csv        8 of 1,496 rows
├── final_unit_conversion_table_for_...csv 8 of 286 rows
├── abbreviations.xlsx                     8 rows × 4 sheets
├── unique_values_..._index.json           dead file, 3×3
├── unique_values_..._preprocessed.json    dead file, 3×3
├── model-best/                            placeholder note
├── .amlignore                             verbatim
└── README.md
```

**Do not point the service at it** — it is for reading. `python make_dependencies_sample.py`
rebuilds it from the live files.

---

## 16. In-scope vs out-of-scope — worked through three queries

`identify_out_of_scope_items()` (`post_processing.py:474-696`) is the last thing that runs before
the response is returned. It answers one question per entity value:

> **"Is this user allowed to see this?"**

### 16.1 The mental model

Most people assume it is a blacklist. It is not — it is a **whitelist that wins over a blacklist**:

```
        ┌─ is the grade in the IN-SCOPE list?  ──── yes ──►  KEEP IT. done.
value ──┤
        └─ no ─┬─ is it in the OUT-OF-SCOPE list? ── yes ──►  FLAG IT. done.
               │
               └─ in neither ──► strip the colour code, try both lists again
```

Why that order? The out-of-scope list is **huge and generated by subtraction**
(`grades` = 11,947 entries), while the in-scope list is the authoritative *"we actually sell
this"* master (`gradesInScope` = 6,607). If the two ever disagree, the in-scope list is trusted.
That is a deliberate safety choice: wrongly hiding a product you sell is worse than showing one
you do not.

### 16.2 Which lists are consulted depends on `user_type`

`post_processing.py:584-589`:

| `user_type` | in-scope list used | out-of-scope list used |
|---|---|---|
| `internal` | `gradesInScope` (6,607) | `grades` (11,947) |
| anything else → external | `gradesInScopeExternal` (4,590) | `gradesExternal` (11,960) **+ `gradesInScope`** |

**That bold clause is the whole external model.** Everything an internal user may see is *added to
the external blocklist*. Internal-visible is not a subset of public — it is explicitly excluded
from public. 2,017 grades sit in `gradesInScope` but not in `gradesInScopeExternal`; those are the
internal-only products.

Brands work the same way but with three separate lists (`post_processing.py:548-568`):

| List | Size | internal | external |
|---|---|---|---|
| `brands_internal` | 0 | visible | — |
| `brands_commerical` | 7 | visible | **hidden** |
| `brands_not_in_scope` | 50 | **hidden** | **hidden** |

### 16.3 Three worked examples

All outputs below were produced by **calling the real function against the real data files**, not
by hand-tracing.

---

#### Example 1 — `hostaform c 9021` · a grade we sell

The model returns `GRADE: ["hostaform c 9021"]`. Normalised → `hostaformc9021`.

| Step | Line | Result |
|---|---|---|
| in-scope check | `:595` | **found** in `gradesInScope` |
| everything else | — | skipped |

```
internal   kept={'GRADE': ['hostaform c 9021']}   active=False   flagged={}
external   kept={'GRADE': ['hostaform c 9021']}   active=False   flagged={}
```

Identical for both users, because it is in both in-scope lists. The colour-code stripper never
runs — step 1 ended it.

---

#### Example 2 — `zytel 101f bk009` · the bug-217995 grade

Zytel is a **DuPont** product. Normalised → `zytel101fbk009`.

| Step | Line | Result |
|---|---|---|
| in-scope check | `:595` | **not found** in `gradesInScope` |
| out-of-scope check | `:596` | **found** in `grades` → flag and `continue` |
| colour-code strip | `:601` | **never reached** — the `continue` at `:599` exits first |

```
internal   kept={}   active=True   flagged={'GRADE': ['zytel 101f bk009']}
external   kept={}   active=True   flagged={'GRADE': ['zytel 101f bk009']}
```

The grade is removed from `entities.GRADE` and moved to `outOfScope.entities.GRADE`, and the whole
response is marked `active: True` so the UI can explain why there are no results.

**This is correct behaviour on incorrect data.** Celanese *does* sell an equivalent; the grade was
sitting in the blocklist because the in-scope master held the colour variant `BKB009` rather than
`BK009`, so the notebook's `OOS − in-scope` subtraction never removed it. Note the ordering trap:
because the out-of-scope test fires at step 2 and `continue`s, the colour-code stripper that would
have rescued it **never gets a chance to run**.

> Re-running this with `outOfScopeData_new.json` returns `active=False` and keeps the grade — see
> §4. The corrected file is still not the one the code loads.

---

#### Example 3 — `ateva 1231mt` · visible internally, hidden publicly

Ateva is a Celanese EVA brand. This grade is in `gradesInScope` but **not** in
`gradesInScopeExternal`.

| user | Step 1 (`:595`) | Step 2 (`:596`) | Outcome |
|---|---|---|---|
| internal | found in `gradesInScope` | — | kept |
| external | not found in `gradesInScopeExternal` | found in `gradesExternal + gradesInScope` | flagged |

```
internal   kept={'GRADE': ['ateva 1231mt']}   active=False   flagged={}
external   kept={}                            active=True    flagged={'GRADE': ['ateva 1231mt']}
```

**Same query, same model output, opposite answers.** This is the `+ gradesInScope` clause doing
its job: the grade is internal-in-scope, and that alone puts it on the external blocklist.

The same asymmetry for brands and polymers:

```
'pipelon grade'  internal  kept={'BRAND': ['pipelon']}   active=False   (commercial brand)
                 external  kept={}                       active=True    flagged={'BRAND': ['pipelon']}

'ps enclosure'   internal  kept={}                       active=True    flagged={'POLYMER': ['ps']}
                 (polystyrene is out of scope for everyone - not a Celanese chemistry)
```

### 16.4 What the caller receives

```jsonc
"modelOutput": {
  "entities":  { "GRADE": [] },                       // stripped
  "outOfScope": {
     "active":   true,                                 // show the banner
     "entities": { "GRADE": ["zytel 101f bk009"],
                   "BRAND": [], "POLYMER": [], "FILLER": [], "OTHERS": [] }
  }
}
```

`active` is the flag the UI uses to say *"we recognised this, but we can't help with it"* rather
than showing a bare empty result.

### 16.5 ⚠️ Bug — a valid BRAND switches the flag back off

Every branch sets the flag with `= True`. One does not (`post_processing.py:567`):

```python
out_of_scope_output["active"] = bool(out_of_scope_brands_identified)   # assignment, not OR
```

The BRAND block runs **after** POLYMER, so if a polymer was flagged and the brands are all fine,
`active` is reset to `False` — while the flagged polymer stays in the payload. Reproduced against
the real data:

| Input | Flagged entities | `active` |
|---|---|---|
| `POLYMER: ['ps']` alone | `{'POLYMER': ['ps']}` | `True` ✅ |
| `POLYMER: ['ps']` **+ `BRAND: ['celanex']`** | `{'POLYMER': ['ps']}` | **`False`** ❌ |

Consequence: for a query like *"ps celanex enclosure"*, the out-of-scope polymer is silently
stripped and the user is never told. The fix is one character — `|=` instead of `=`, or
`active = active or bool(...)`. Anything ordered after BRAND (FILLER, GRADE, AUTO_CERT, the topic
flags) sets `active = True` again, so the window is narrow but real: it needs an out-of-scope
POLYMER, a clean BRAND, and nothing else flagged.

### 16.6 Reproducing this yourself

`identify_out_of_scope_items()` needs only two dependency files and no model call, so it can be
driven directly:

```python
import json, sys, types
# the function does not use thefuzz - stub it so the import succeeds
m = types.ModuleType('thefuzz'); m.fuzz = m.process = types.SimpleNamespace()
sys.modules['thefuzz'] = m
sys.path.insert(0, 'onlinescoring')
from post_processing import identify_out_of_scope_items

DEP = {'OUT_OF_SCOPE_DATA': json.load(open('dependencies/outOfScopeData.json')),
       'OOS_COLOR_CODE_PATTERN': open('dependencies/oos_color_code_pattern.txt',
                                      encoding='latin-1').read()}
result = {k: [] for k in ['GRADE','APPLICATION','BRAND','POLYMER','PROPERTY','FILLER','FEATURE',
                          'PROCESSING','DELIVERY_FORM','COMPETITOR_GRADE','AUTO_CERT',
                          'RAILWAY_CERT','WATER_CERT','NSF_CERT','INDUSTRY','REGION','MATERIAL_ID']}
result['GRADE'] = ['zytel 101f bk009']

oos = identify_out_of_scope_items(DEP, 'zytel 101f bk009', result, 'internal')
print(result['GRADE'], oos['active'], oos['entities']['GRADE'])
```

This is the fastest way to test a scope question — no endpoint, no Azure OpenAI key, no container.

---

## 17. Summary — state after the 11-Aug-2026 commit

### Closed

1. **The bug-217995 fix is now in the file the code loads.** Both Zytel grades verify as in scope.
2. **`normalized_unique_values_for_grade_mapping.json` carries all ten keys**, including the three
   new ones. `FEATURE` was missing before, which would have raised `KeyError` on every query.
3. **`CHEMICAL_RESISTANCE` has proper reference data** — `chemical_resistance.json`, with the
   verdict supplied by lookup rather than trusted from the model.

### Still worth acting on

1. **6 MB of ~12 MB is dead weight** — two stale `unique_values_*` variants, the now-redundant
   `outOfScopeData_new.json`, and an empty `model-best/`. Deleting them shrinks the artifact and
   removes real ambiguity about which file is live.
2. **`abbreviations.xlsx` is parsed on every start and never used.** Either delete it together with
   `replace_abbreviation()`, or write down why it is kept.
3. **Validate these files after every hand-copy.** Two separate corruptions of the same file were
   caught on 11-Aug — first a truncated head, then a duplicated splice. Because
   `post_processing.py` loads it at *import*, a bad copy stops the container before `init()` with
   an unhelpful `JSONDecodeError`. One command tells you:

   ```bash
   python -c "import json;d=json.load(open('dependencies/normalized_unique_values_for_grade_mapping.json',encoding='utf-8'));print(len(d),'keys');[print(' ',k,len(v)) for k,v in d.items()]"
   ```

4. **Prefer regenerating over re-copying.** These files come from
   `Development files/1-3*.ipynb`; a rerun is safer than a clipboard round-trip.

---

⬅️ Back to [`00-README-START-HERE.md`](00-README-START-HERE.md) · related:
[`16-entity-by-entity-resolution.md`](16-entity-by-entity-resolution.md) ·
[`09-missing-files.md`](09-missing-files.md) ·
[`13-how-ner-prediction-works.md`](13-how-ner-prediction-works.md)

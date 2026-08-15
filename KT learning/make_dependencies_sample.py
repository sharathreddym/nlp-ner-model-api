# -*- coding: utf-8 -*-
"""
Builds `dependencies-sample/` - a miniature, readable copy of every file in
flat-repo-ner/dependencies/.

Same file names, same schema, same value shapes - just a handful of real rows each,
so the whole reference-data layer can be reviewed in a few minutes instead of
opening 11 MB of JSON.

Run:  python make_dependencies_sample.py
"""
import json
import os
import shutil

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "dependencies")
OUT = os.path.join(HERE, "dependencies-sample")

N = 5          # values kept per list
os.makedirs(OUT, exist_ok=True)


def load_json(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def save_json(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print("  wrote", name)


# ---------------------------------------------------------------- 1. unique_values
u = load_json("unique_values_22_02_24.json")
save_json("unique_values_22_02_24.json", {k: v[:N] for k, v in u.items()})

# ------------------------------------------------- 2. normalized_unique_values
n = load_json("normalized_unique_values_for_grade_mapping.json")
save_json("normalized_unique_values_for_grade_mapping.json",
          {k: v[:N] for k, v in n.items()})

# ------------------------------------------------- 3. normalized_competitor_names
c = load_json("normalized_competitor_names.json")
save_json("normalized_competitor_names.json", c[:12])

# ------------------------------------------------------------ 4. outOfScopeData
o = load_json("outOfScopeData.json")
save_json("outOfScopeData.json", {k: v[:N] for k, v in o.items()})

on = load_json("outOfScopeData_new.json")
save_json("outOfScopeData_new.json", {k: v[:N] for k, v in on.items()})

# ------------------------------------------- 4b. chemical_resistance (new 11-Aug)
cr = load_json("chemical_resistance.json")
sample_cr = {}
for cat in list(cr)[:3]:                      # 3 of 11 categories
    items = []
    for item in cr[cat][:2]:                  # 2 sub-categories each
        trimmed = dict(item)
        if isinstance(trimmed.get("synonyms"), list):
            trimmed["synonyms"] = trimmed["synonyms"][:5]
        items.append(trimmed)
    sample_cr[cat] = items
save_json("chemical_resistance.json", sample_cr)

# ---------------------------------------------------------- 5. ul_list_name_value
ul = load_json("ul_list_name_value.json")
keep = ["comparative tracking index (cti)", "flame rating", "outdoor suitability"]
save_json("ul_list_name_value.json",
          {k: ul[k] for k in keep if k in ul})

# --------------------------------------------------------- 6. colour-code regex
with open(os.path.join(SRC, "oos_color_code_pattern.txt"), encoding="latin-1") as f:
    pat = f.read()
PREFIX = r"([\s\(-]|^)("
SUFFIX = r")[-./\s()]*$"
body = pat[len(PREFIX):-len(SUFFIX)]
alts = body.split("|")[:6]
with open(os.path.join(OUT, "oos_color_code_pattern.txt"), "w", encoding="latin-1") as f:
    f.write(PREFIX + "|".join(alts) + SUFFIX)
print("  wrote oos_color_code_pattern.txt  (%d of %d alternations)"
      % (len(alts), len(body.split("|"))))

# --------------------------------------------------------- 7. unit conversion CSVs
g = pd.read_csv(os.path.join(SRC, "final_unit_conversion_table.csv"))
picks = ["gpa", "psi", "ºf", "g/cm3", "ft-lb/in2", "in/in"]
rows = pd.concat([g[g["Incoming Unit"] == p].head(1) for p in picks
                  if (g["Incoming Unit"] == p).any()])
if len(rows) < 8:
    rows = pd.concat([rows, g.head(8 - len(rows))])
rows.to_csv(os.path.join(OUT, "final_unit_conversion_table.csv"), index=False)
print("  wrote final_unit_conversion_table.csv  (%d of %d rows)" % (len(rows), len(g)))

e = pd.read_csv(os.path.join(SRC, "final_unit_conversion_table_for_exeptions.csv"))
e.head(8).to_csv(os.path.join(OUT, "final_unit_conversion_table_for_exeptions.csv"),
                 index=False)
print("  wrote final_unit_conversion_table_for_exeptions.csv  (8 of %d rows)" % len(e))

# ------------------------------------------------------------- 8. abbreviations
xl = os.path.join(SRC, "abbreviations.xlsx")
with pd.ExcelWriter(os.path.join(OUT, "abbreviations.xlsx"), engine="openpyxl") as w:
    for sheet in ["PROPERTY", "FILLER", "FEATURE", "common_abb"]:
        df = pd.read_excel(xl, sheet_name=sheet)
        df.head(8).to_excel(w, sheet_name=sheet, index=False)
        print("  wrote abbreviations.xlsx[%s]  (8 of %d rows)" % (sheet, len(df)))

# ------------------------------------------------------------- 9. dead files
i = load_json("unique_values_22_02_24_index.json")
save_json("unique_values_22_02_24_index.json",
          {k: (v[:3] if isinstance(v, list) else v) for k, v in list(i.items())[:3]})
p = load_json("unique_values_22_02_24_preprocessed.json")
save_json("unique_values_22_02_24_preprocessed.json",
          {k: v[:3] for k, v in list(p.items())[:3]})

# ------------------------------------------------------------ 10. .amlignore
shutil.copyfile(os.path.join(SRC, ".amlignore"), os.path.join(OUT, ".amlignore"))
os.makedirs(os.path.join(OUT, "model-best"), exist_ok=True)
with open(os.path.join(OUT, "model-best", "EMPTY-IN-THE-REAL-REPO.txt"), "w") as f:
    f.write("The real dependencies/model-best/ contains only a .amlignore file.\n"
            "It is a leftover from the retired spaCy model and is never read by the code.\n")
print("  wrote .amlignore + model-best/ placeholder")

# ------------------------------------------------------------------ README
with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
    f.write("""# dependencies-sample

Miniature copies of every file in `flat-repo-ner/dependencies/`, with the **same schema**
and a handful of **real** rows each, so the structure can be reviewed quickly.

**Do not point the service at this folder** - it is for reading, not running.
Regenerate with `python ../make_dependencies_sample.py`.

Full explanation: [`17-dependencies-files-explained.md`](../17-dependencies-files-explained.md)

| File | Live? | Sample holds |
|---|---|---|
| `unique_values_22_02_24.json` | yes | 5 values per key (16 keys) |
| `chemical_resistance.json` | yes | 3 of 11 categories, 2 sub-categories each |
| `normalized_unique_values_for_grade_mapping.json` | yes | 5 values per key (10 keys) |
| `normalized_competitor_names.json` | yes | 12 of 1,165 names |
| `outOfScopeData.json` | yes | 5 values per key (10 keys) |
| `ul_list_name_value.json` | yes | 3 of 28 UL properties, complete |
| `oos_color_code_pattern.txt` | yes | 6 of 43,667 alternations |
| `final_unit_conversion_table.csv` | yes | 8 of 1,496 rows |
| `final_unit_conversion_table_for_exeptions.csv` | yes | 8 of 286 rows |
| `abbreviations.xlsx` | yes | 8 rows per sheet (4 sheets) |
| `outOfScopeData_new.json` | **no** | 5 per key - the corrected data, not loaded |
| `unique_values_22_02_24_index.json` | **no** | 3 keys x 3 values |
| `unique_values_22_02_24_preprocessed.json` | **no** | 3 keys x 3 values |
| `model-best/` | **no** | empty in the real repo too |
| `.amlignore` | n/a | copied verbatim |
""")
print("  wrote README.md")
print("\nDone ->", OUT)

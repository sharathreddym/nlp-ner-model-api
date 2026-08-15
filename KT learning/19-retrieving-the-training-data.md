# 18 · Retrieving the NER training data

**Question this answers:** the fine-tuning corpus is not in the repo. Where is it,
how do I get it back, and how do I turn it into something reviewable?

Companion tool: **`extract_training_data.py`** → `training-data-review/`

---

## 0. The notebooks — names and paths

Everywhere below, "notebook 3" means the file whose name starts with `3 `. All
nine live in one folder:

```
D:\sarath_interview_study_material_v2\celanese-knowledge-base\
    flat-repo-ner\Development files\NER_Training\
```

| # | Exact filename | Size | Cells | What it does |
|---|---|---:|---:|---|
| **1** | `1 Data for NER.ipynb` | 153 KB | 48 | Pulls the **vocabulary**. UI-Properties API → `unique_values_*.json`; Snowflake `SPT` / `COMPETITOR_DATA` / `SYNONYM` → `all_grades_*.json`, `all_cgrades_*.json`, `all_brands_*.json`, `all_certifications_*.json` |
| **2** | `2 Out of scope Data.ipynb` | 35 KB | 34 | Pulls the four `GST_CURATED.OUT_OF_SCOPE_*` tables → `outOfScopeData_*.json`. Also instantiates an Elasticsearch client for validation |
| **3** | `3 Generate Training Data.ipynb` | **3.4 MB** | **296** | **The generator.** `templates × vocabulary` under per-entity quotas → ~44k synthetic rows across 7 xlsx files. Biggest and most important notebook |
| **4** | `4 Merge Training data and Entities Insights.ipynb` | 87 KB | 25 | Merges **15 files** (9 human-labelled + 6 generated) → `without_formatting/Training_Data_27_01_25.xlsx`. Also produces entity-combination counts |
| **5** | `5 Format Training Data.ipynb` | 192 KB | 22 | Normalises property names via `prop_syn_mapping`, runs the schema validators, renumbers `Sl. No.` → `Training_Data_27_01_25.xlsx` (**61,532 rows**) |
| **6** | `6 Get Labelled Values.ipynb` | 81 KB | 12 | Side-analysis, **not** in the training path. Walks every `Output` dict and extracts the distinct values actually used per entity → `all_labelled_unique_values_27_01_25.json` |
| **7** | `7 GPT Finetuning for NER-usnc.ipynb` | 21 KB | 24 | Excel → chat JSONL, token/format checks, 80/20 split (`random_state=42`), upload to Azure OpenAI, launch the fine-tune |
| **8** | `8 GPT NER Test Queries.ipynb` | 65 KB | 250 | Evaluation of the **raw model** — calls the fine-tuned deployment directly (`seed=12`, `temperature=0.01`). The commented-out deployment list is the full model history |
| **9** | `9 DEV model testing (NER API with pre or post processing).ipynb` | 17 KB | 13 | Evaluation of the **whole service** — POSTs to `gst-ner-endpoint-{dev,qa,prod}`, so pre- and post-processing are included |

**Training path: 1 → 2 → 3 → 4 → 5 → 7.**
Notebook 6 is analysis. Notebooks 8 and 9 are evaluation — 8 tests the model,
9 tests the deployed service.

### Where to stop, depending on what you want

| Goal | Run | You end up with |
|---|---|---|
| **The training data, readable** | **1 → 2 → 3 → 4 → 5** | `Training_Data_27_01_25.xlsx` — 61,532 rows, columns `Sl. No.` / `Query` / `Output` / `Ref No.` |
| The same data in fine-tuning format | + **7, cells 0–18** | `Training_Data_*.jsonl`, then `train_*.jsonl` (49,225) and `validation_*.jsonl` (12,307) on local disk |
| Uploaded to Azure OpenAI | + **7, cells 21–23** | two `file-…` IDs |
| Actually fine-tuned | — | **not in any notebook** (see below) |

**Stop after notebook 5 if the goal is the data.** Notebook 5 is the last one
that produces a dataset; everything in 7 is packaging and transport.

Inside notebook 7 the boundary is **cell 18**. Cells 4–6 build the JSONL, 7–14
validate and price it, 15–18 shuffle and split 80/20 and write both files. Cell
20 is the markdown header *"Upload the file"* — nothing before it leaves your
machine, so you can run 0–18 with no Azure OpenAI credentials at all.

> **Notebook 7 has only 24 cells and ends at cell 23, the file upload.** There is
> no `FineTuningJob.create` anywhere in it. The training run itself was launched
> outside these notebooks — almost certainly from the Azure OpenAI Studio UI —
> which is why the notebook records the two file IDs but no job ID. Budget for
> that step separately; it is not code you can just re-run.

Also note: notebooks 2 and 3 are **not** independent. Notebook 2 writes
`outOfScopeData_{version}.json`, which notebook 3 reads at cell 4 (`OOS_Data`)
and uses to extend `all_gradenames`. Run 2 before 3.

---

## 1. What exists, and what does not

Everything below is verified against the notebooks in
`Development files/NER_Training/` and against the filesystem.

| Artefact | Version | Rows | On disk here? |
|---|---|---:|---|
| `Training_Data_27_01_25.xlsx` (source of truth) | 27_01_25 | 61,532 | ❌ **no** |
| `Training_Data_27_01_25.jsonl` (chat-formatted) | 27_01_25 | 61,532 | ❌ no |
| `train_27_01_25.jsonl` (80%) | 27_01_25 | **49,225** | ❌ no |
| `validation_27_01_25.jsonl` (20%) | 27_01_25 | **12,307** | ❌ no |
| `validation_27_11_24.jsonl` | **27_11_24** (previous) | **12,190** | ✅ **yes** — 9.46 MB |

> `Data/temp/validation_27_11_24.jsonl` is the **only** surviving corpus file.
> It is the validation slice of the *previous* build. It has **16 entity keys** —
> no `MATERIAL_ID`, no `MEDICAL_CERT`, no `CHEMICAL_RESISTANCE`. Accurate for
> **format**, stale for **label set**.

### Numbers straight from notebook 7's saved output

```
len(dataset)                        -> 61532
train_test_split(test_size=0.20,
                 random_state=42)   -> (49225, 12307)
tokens per example  min/max          155 / 506      (mean 188, median 175)
assistant tokens    min/max           88 / 369      (mean 112, median  99)
examples over the 4096-token cap    -> 0
billing tokens                      -> 11,594,698
epochs (auto)                       -> 1     # 61532 x 3 > 25000 -> clamped
cost estimate                       -> $92.72
```

---

## 2. Where the data comes from — the origin, not the download

**The training data is not stored anywhere as a thing. It is *manufactured* by
notebooks 1→3→4→5 from five upstream systems.** If you need training data, this
is the section that matters — you re-run the chain, you do not find a file.

```
                        ┌──────────────────────────────────────────────┐
 A. UI-Properties API ──┤ the master vocabulary (what words exist)      │
 B. Snowflake          ─┤ grades, competitor grades, synonyms, OOS      │──┐
 C. Curated .xlsx      ─┤ application→industry, region, UL name/value   │  │
                        └──────────────────────────────────────────────┘  │
                                                                          ▼
                                                          (1) Data for NER.ipynb
                                                          (3) Generate Training Data
                                                              templates × vocabulary
                                                              = ~44k SYNTHETIC rows
                                                                          │
 D. Prod search logs ───► human labelling ───► data/reviewed/prod/*.xlsx ─┤
 E. Prodigy / survey ───► human labelling ───► data/reviewed/*.xlsx ──────┤
                                                                          ▼
                                                          (4) Merge -> 61,532 rows
                                                          (5) Format/validate
                                                          (7) 80/20 -> Azure OpenAI
```

### A · The UI-Properties API — the vocabulary master

`1 Data for NER.ipynb` cell 3. **This is the single source of the entity
vocabulary**, and the origin of `unique_values_*.json`:

```python
url = "https://apim-gst-dev.azure-api.net/func-uiproperties-d-ussc-01/func-ui-properties"
headers = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": "<key>"}
unique_values = requests.post(url, headers=headers).json()["results"]
```

It returns the keys the product UI itself uses — `Brand`, `Property`, `UL`,
`Feature` (which carries Processing / Product Categories / Delivery Form as a
`Feature Type` sub-field), `Filler`, `Polymer`, `Application`, `Region`,
`Auto_Approval`, `Certification`. That is why FEATURE has only 62 distinct
values and DELIVERY_FORM only 5 — **these are closed lists owned by the product,
not by NER.** When the business adds a feature in the UI, this API is where it
appears first.

### B · Snowflake — `ANALYTICS_DEV` . `GST_CURATED`

Connected via `connection_string` in `.env`, warehouse `reporting_wh`, SSO over VPN.

| Table | Column pulled | Becomes |
|---|---|---|
| `SPT` | `PRODUCT_CD` | every Celanese **GRADE** (`all_grades_*.json`) |
| `COMPETITOR_DATA` | `COMPETITOR_GRADE` | every **COMPETITOR_GRADE** (`all_cgrades_*.json`) |
| `SYNONYM` | `DEFINED_NAME`, `SYNONYMS`, `TYPE` | the alternate surface forms — how one concept is said many ways |
| `OUT_OF_SCOPE_GRADES` / `_BRANDS` / `_POLYMERS` / `_FILLERS` | — | `outOfScopeData.json` (notebook 2) |

`SYNONYM` is the interesting one. It is a business-maintained table of
`concept -> "syn1; syn2; syn3"`, and notebook 1 uses it to **multiply grades by
brand synonyms** — if `hostaform` has synonym `celcon`, then every
`hostaform xyz` grade also generates `celcon xyz`. That is domain knowledge
entering the corpus from a database table rather than from a person.

### C · Curated spreadsheets — business-reviewed mappings

Read directly by notebook 3, not generated by any code:

- `applications_industry_mapping_gd_reviewed.xlsx` — application → industry.
  The comment in the notebook says it plainly: *"Application and its respective
  Industry are reviewed by the Business Team."* This is why `"part in a beer
  machine"` yields `INDUSTRY: consumer goods` when the query never said it.
- `applications_industry_mapping_sq_21_11_24.xlsx` — same, from survey data.
- `Region_data_04_09_24.xlsx` — sheets `americas` / `europe` / `asia`.
- `ul_list_name_value.json` — legal UL property/sub-property value pairs.

### D · Production search logs — the real queries

`4 Merge...ipynb` cell 3 lists them under `data/reviewed/prod/`:

```
Prod_queries_from_02_19_to_03_2_reviewed.xlsx
Prod_Query_1-16_to_2-18_part1_reviewed.xlsx   (+ part2, part3)
labelled_prod_queries.xlsx
```

These are **askchemille.com search queries, exported by date range and then
hand-labelled**. The `Ref No.` column in the final corpus preserves the
provenance of every row — e.g. `Prod_queries_from_02_19_to_03_2_reviewed_1`.

**This is the only part of the pipeline that cannot be regenerated by code.**
It requires (a) an export of prod search traffic for a date window, and
(b) a human labelling pass. Getting new training data means doing this again.

### E · Earlier hand-labelled sets

`data/reviewed/` — `labeled_data_for_grade_comp_grade_brand_intial_review`,
`labeled_data_survey_queries 2_filtered`, `Sample labels 1 Reviewed`,
`enhancement_queries`. The Prodigy-era artefacts still in the repo
(`Development files/Prodigy/`) are the ancestor of these.

### The generator — notebook 3, `templates × vocabulary`

Roughly 44,000 of the 61,532 rows are **synthetic**: notebook 3 loops, drawing
random values from the vocabularies above and slotting them into query
templates, until a per-entity quota is hit (cell 252):

```
feat_th   6500   poly_th  6500   brand_th 6000   process_th 3500
app_th    3000   region_th 3000  auto_th  2500   fill_th    2500
prop_th   2000   del_th   2000   ignore_terms_th 2000
ul_prop_th 1500  rail_th  1500   ul_sub_prop_th 1400
water_th  1000   nsf_th   1000   prop_rm_th 1000  prop_abb_th 1000
```

Because generation is per-entity, each generated row usually carries **one**
entity — hence the 69% single-entity figure in `corpus_profile.md` §5, and hence
the model's weakness on long multi-entity queries. **The quota block above is the
lever**: to make the model better at combinations, that generator needs
multi-entity templates, not more rows.

The output lands in seven files (`prod_generated_data_27_01_25.xlsx`,
`auto_certifications_data_*`, `multi_ul_sub_props_*`, `grade_cgrade_data_*`,
`prod_generated_data_auto_num_*`, `prod_generated_data_prop_grade_*`,
`prod_generated_data_poly_brand_tl_*`), which notebook 4 merges with the nine
human-labelled files.

> **Elasticsearch** appears in notebooks 2 and 3 (`elast-gst-{nprd,tst,prd}-ussc-01
> …:9243`). Notebook 2 instantiates a client for validation; notebook 3 imports it
> but never queries it. **The corpus does not come from Elasticsearch** — worth
> knowing given the retrieval proposal in `15-retrieval-based-ner-approach.md`.

### ⚠ Before sharing these notebooks

Notebooks 1, 2, 3 and 7 contain **live plaintext credentials** — the APIM
subscription key, the Elasticsearch **prod** password, prod/QA/dev NER and sbert
API keys, and an Azure OpenAI key. Strip them before publishing to the ADO wiki
or any shared location, and rotate them. This is the Key Vault item already open
in `CLAUDE.md`.

---

## 3. Four ways to get it back — best first

### Route A · Azure OpenAI Files API (the uploaded copies)

Notebook 7 cell 23 printed the file IDs. These are the exact bytes that trained
the model:

```
resource      https://oai-gst-d-usnc-01.openai.azure.com/
train          file-a3b0d8eea34c469391fe9a6d3bc3c84a   train_27_01_25.jsonl
validation     file-4866d639a96d492ab99e606dcb80c101   validation_27_01_25.jsonl
```

```bash
# az login first; needs Cognitive Services OpenAI Contributor on the resource
az cognitiveservices account keys list \
  -n oai-gst-d-usnc-01 -g <rg> --query key1 -o tsv
```

```python
# pip install openai>=1.0
from openai import AzureOpenAI
c = AzureOpenAI(azure_endpoint="https://oai-gst-d-usnc-01.openai.azure.com/",
                api_key=KEY, api_version="2024-10-21")

for f in c.files.list():                       # confirm they still exist
    print(f.id, f.filename, f.bytes, f.status)

open("train_27_01_25.jsonl", "wb").write(
    c.files.content("file-a3b0d8eea34c469391fe9a6d3bc3c84a").read())
open("validation_27_01_25.jsonl", "wb").write(
    c.files.content("file-4866d639a96d492ab99e606dcb80c101").read())
```

Or plain REST:

```bash
curl -s "https://oai-gst-d-usnc-01.openai.azure.com/openai/files/file-a3b0d8eea34c469391fe9a6d3bc3c84a/content?api-version=2024-10-21" \
     -H "api-key: $KEY" -o train_27_01_25.jsonl
```

**Caveat:** the upload was Jan 2025 on a **dev** resource. Files can be purged,
and the resource may have been rotated. Check `files.list()` before assuming.
If the IDs are gone, the fine-tune job record may still name them —
`c.fine_tuning.jobs.list()` shows `training_file` / `validation_file` per job.

### Route B · The author's working directory

All notebook paths are **relative** (`data/Training_Data_27_01_25/...`), so the
whole `data/` tree lived beside the notebooks on the developer's machine and was
never committed — `Data/temp/` survived only because one file was left behind.
Ask whoever ran notebook 7 (the fine-tuning owner) for the folder
`data/Training_Data_27_01_25/`. **This is the fastest route if the person is
reachable** — one zip gets you the Excel *and* both JSONL splits.

### Route C · Azure ML workspace

Worth 10 minutes before rebuilding:

```bash
az ml data list -w ml-gst-dev-usscc-01 -g rg-gst-dev-ussc-01 -o table
az ml job list  -w ml-gst-dev-usscc-01 -g rg-gst-dev-ussc-01 -o table
```

Also check the default datastore blob container (`sagmlstoredev01`) under
`UI/`, `azureml/`, and any `Users/<alias>/` notebook file-share paths — Compute
Instance home directories persist and are the most likely place a `data/` folder
was left.

### Route D · Regenerate from source — the real answer for *new* training data

Routes A–C recover the **old** corpus. If the goal is to train again, this is the
route, and it is §2's chain run forward. Notebooks **1 → 2 → 3 → 4 → 5 → 7**.

What you need in hand before starting:

| Need | Where from | Blocker if missing |
|---|---|---|
| `.env` with `connection_string` | Snowflake SSO, VPN | notebooks 1, 2, 3 |
| APIM subscription key | `func-ui-properties` owner | notebook 1 cell 3 |
| `data/reviewed/prod/*.xlsx` | **prod search-log export + human labelling** | notebook 4 — no substitute |
| `data/reviewed/*.xlsx` (5 older sets) | the previous corpus owner | notebook 4 |
| `applications_industry_mapping_*.xlsx`, `Region_data_*.xlsx` | business team | notebook 3 |
| Azure OpenAI key + fine-tune quota | `oai-gst-d-usnc-01` | notebook 7 |

Two honest caveats:

1. **The nine human-labelled files are not reproducible by code.** Notebooks 1–3
   regenerate the ~44k synthetic rows from live sources; the ~17k human rows have
   to be recovered from the previous owner or re-labelled from a fresh prod export.
2. Output will not be byte-identical — the gazetteers have moved since Jan 2025.
   That is the point: a regenerated corpus carries **today's** grades and today's
   19-key label set, including `MEDICAL_CERT` and `CHEMICAL_RESISTANCE`, which the
   27_01_25 corpus never had.

**If the objective is specifically to teach the model the three newer entities**,
you do not need the whole chain. Add labelled rows for those entities to the
merge in notebook 4 and re-run 5 and 7. The vocabulary for them already exists —
`chemical_resistance.json` (11 categories) and the `MEDICAL_CERT` list in
`normalized_unique_values_for_grade_mapping.json` — so the generator in notebook 3
can be pointed at them the same way it is pointed at FEATURE today.

---

## 4. Formatting it for review

Once you have any `.jsonl` (or the source `.xlsx`):

```bash
cd "flat-repo-ner/KT learning"

python extract_training_data.py                              # local 27_11_24 file
python extract_training_data.py path/to/train_27_01_25.jsonl
python extract_training_data.py train.jsonl validation.jsonl -o full-corpus/   # merged
python extract_training_data.py path/to/Training_Data_27_01_25.xlsx
```

Output in `training-data-review/`:

| File | What it is |
|---|---|
| **`corpus_profile.md`** | **Read this one.** ~19 KB, the whole corpus in one page: schema, fill rate per entity, top values per entity, PROPERTY/FILLER shapes, arity + query-length histograms, duplicates, 14 verbatim examples. |
| `training_data_flat.xlsx` | One row per example, one column per entity, plus `prop1_name/value/min/max/unit`. Sort and filter. |
| `training_data_flat.csv` | Same, diff-friendly. |
| `property_rows.csv` | One row per PROPERTY object — the entity that carries all the schema complexity. |
| `filler_rows.csv` | One row per FILLER, names + total_load. |
| `entity_values.csv` | Every distinct value per entity with its frequency. Diff this against `dependencies/unique_values_22_02_24.json` to find label/gazetteer drift. |
| `sample_200.jsonl` | Stratified — every entity and every arity represented, verbatim chat format. |
| `schema_report.txt` | Notebook 5's validators re-run over every row. |

**To show the data as a whole**, `corpus_profile.md` + `sample_200.jsonl` is the
pair to hand over: ~180 KB together and they characterise all 61k rows. The raw
JSONL is 9–47 MB and cannot be read end to end by anyone, human or model.

---

## 5. One thing to check on arrival

The corpus predates three entities. Before trusting any retrieved file, run:

```bash
head -1 train_27_01_25.jsonl | python -c "import json,sys,ast; \
print(sorted(ast.literal_eval(json.load(sys.stdin)['messages'][2]['content'])))"
```

- **16 keys** → the 27_11_24-era label set. No `MATERIAL_ID`, `MEDICAL_CERT`,
  `CHEMICAL_RESISTANCE`.
- **19 keys** → current. Cross-check `MEDICAL_CERT` and `CHEMICAL_RESISTANCE`
  fill rates in `corpus_profile.md` §4 — if they are ~0%, the model never learned
  them and they are being carried entirely by the post-processing rules in
  `post_processing.py` (`validate_medical_cert_values()` :532,
  `reclassify_feature_to_chem_res()` :460).

That distinction decides whether a gap gets fixed with **more training data** or
with **a rule change** — see `16-entity-by-entity-resolution.md`.

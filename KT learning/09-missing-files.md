# 9. Missing Files — What to Add & Where 📁

> The code logic is complete, but this repo copy is missing the **data files** and the
> **credentials file** needed to actually run it. This page lists every missing file, its exact
> name, and the folder it belongs in.
>
> All data-file loads happen in `score.py` → `init()` (lines 72–111). The helper modules read
> no data files; they only read Azure credentials from `.env`.

---

## 1️⃣ Data files — go in the `dependencies/` folder

📂 **Target folder:**
`D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\`

*(The folder exists but is empty except an unused `model-best/` subfolder.)*

| # | Missing file | Loaded at | Type / note |
|---|--------------|-----------|-------------|
| 1 | `final_unit_conversion_table.csv` | score.py:72 | CSV |
| 2 | `final_unit_conversion_table_for_exeptions.csv` | score.py:75 | CSV — note the misspelling **"exeptions"**; filename must match exactly |
| 3 | `unique_values_22_02_24.json` | score.py:78 | JSON |
| 4 | `normalized_unique_values_for_grade_mapping.json` | score.py:83 | JSON |
| 5 | `normalized_competitor_names.json` | score.py:87 | JSON |
| 6 | `outOfScopeData.json` | score.py:91 | JSON |
| 7 | `oos_color_code_pattern.txt` | score.py:95 | Text (read with `latin-1` encoding) |
| 8 | `ul_list_name_value.json` | score.py:99 | JSON |
| 9 | `abbreviations.xlsx` | score.py:104–111 | Excel — **must contain 4 sheets**: `PROPERTY`, `FILLER`, `FEATURE`, `common_abb` |

### Full paths (copy-paste)
```
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\final_unit_conversion_table.csv
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\final_unit_conversion_table_for_exeptions.csv
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\unique_values_22_02_24.json
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\normalized_unique_values_for_grade_mapping.json
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\normalized_competitor_names.json
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\outOfScopeData.json
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\oos_color_code_pattern.txt
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\ul_list_name_value.json
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\dependencies\abbreviations.xlsx
```

> ⚠️ `init()` crashes on the **first** missing file — `final_unit_conversion_table.csv`
> (line 73) — so you won't see errors for the rest until each earlier one is in place.

---

## 2️⃣ Credentials file — goes in the `onlinescoring/` folder

📂 **Target folder:**
`D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\onlinescoring\`

| Missing file | Needed by | Must contain these keys |
|--------------|-----------|--------------------------|
| `.env` | ner_helper.py:14–18 | `azure_openai_key_aif`<br>`azure_openai_endpoint_aif`<br>`api_version_aif` |

### Full path
```
D:\sarath_interview_study_material_v2\celanese-repos\flat-repo-ner\onlinescoring\.env
```

### `.env` template
```env
azure_openai_key_aif=<your-azure-openai-api-key>
azure_openai_endpoint_aif=<your-azure-openai-endpoint-url>
api_version_aif=<your-azure-openai-api-version>
```

---

## ℹ️ `model-best/` — present but NOT required

```
dependencies\model-best\   ← legacy spaCy NER model
```
The current pipeline uses **GPT**, not spaCy. Nothing in `onlinescoring/` loads `model-best`,
so it is **not needed** to run. You can ignore it.

---

## 📍 Where to obtain these files

They are part of the **Azure ML registered "dependencies" model** (README lines 58–65 & 94).
The owner of the Azure ML workspace / original repository can export them. They are deliberately
kept out of git (data + secret credentials are not committed to source control).

---

## ✅ Target folder layout once complete

```
flat-repo-ner/
├── dependencies/
│   ├── final_unit_conversion_table.csv                    ← add
│   ├── final_unit_conversion_table_for_exeptions.csv      ← add
│   ├── unique_values_22_02_24.json                        ← add
│   ├── normalized_unique_values_for_grade_mapping.json    ← add
│   ├── normalized_competitor_names.json                   ← add
│   ├── outOfScopeData.json                                ← add
│   ├── oos_color_code_pattern.txt                         ← add
│   ├── ul_list_name_value.json                            ← add
│   ├── abbreviations.xlsx                                 ← add (4 sheets)
│   └── model-best/                                        ← already here (unused, ignore)
└── onlinescoring/
    ├── .env                                               ← add (Azure creds)
    └── score.py, ner_helper.py, ...                       ← already here
```

---

## 🔌 External services, databases & APIs

> Question asked: *does the code use Elasticsearch, Snowflake, Postgres, or call any APIs/routes?*
> Short answer: **the deployed runtime uses only Azure OpenAI. Elasticsearch and Snowflake
> appear ONLY in development notebooks, not in the live service.**

### A) Runtime code (`onlinescoring/` — the deployed service)

| Service / DB / API | Used? | Where | Notes |
|--------------------|-------|-------|-------|
| **Azure OpenAI** (GPT-4.1-mini) | ✅ YES | `ner_helper.py:12–22`, `:525` | The ONLY external call. Chat-completions API. |
| **Elasticsearch** | ❌ No | — | Not imported or called anywhere in runtime. |
| **Snowflake** | ❌ No | — | Not imported or called anywhere in runtime. |
| **Postgres / any SQL DB** | ❌ No | — | No `psycopg`, `sqlalchemy`, `pyodbc`, no SQL at all. |
| **Any REST API via `requests`/`http`** | ❌ No | — | No `requests`, `httpx`, or raw HTTP calls. |
| **Web routes (Flask/FastAPI)** | ❌ No | — | No `@app.route`, no web framework. See "routes" note below. |

**The only external integration — Azure OpenAI (`ner_helper.py`):**
```python
from openai import AzureOpenAI                          # line 12
azure_openai_key      = os.getenv('azure_openai_key_aif')       # line 16
azure_openai_endpoint = os.getenv('azure_openai_endpoint_aif')  # line 17
api_version           = os.getenv('api_version_aif')            # line 18
client = AzureOpenAI(api_key=..., api_version=..., azure_endpoint=...)  # lines 19–22

# the actual call (line 525):
completion = client.chat.completions.create(
    seed=12, temperature=0.01, model=deployment_name,
    messages=[{"role":"system","content":ner_prompt},
              {"role":"user","content":query}])
```

### B) "Routes" — there are none in the usual sense

This service has **no HTTP routes / URL paths** of its own. It is an **Azure ML online
endpoint**, which uses a fixed convention instead of routes:

```
   Azure ML endpoint  ──►  init()   (once at startup)
                      ──►  run()    (per scoring request)
```

- There is **one logical entry point**: a `POST` to the Azure ML scoring URI, which Azure
  internally dispatches to `run(raw_data)` in `score.py`.
- `API_VERSION` (`score.py:142` = `"v5.8.4"`) is just a **version string stamped on responses**,
  not a routed API path.
- The endpoint's public scoring URL lives in the Azure ML workspace, not in this code.

### C) Two GPT "deployments" (the closest thing to multiple endpoints)

`score.py` `init()` defines two Azure OpenAI **deployment names** (primary + fallback):

| Variable | Value (in code) | Line |
|----------|-----------------|------|
| `GPT_DEPLOYMENT_NPROD` | `aif-gpt-4-1-mini-NER-2026-04-17-aif-gst-ussc-01` | score.py:66 |
| `GPT_DEPLOYMENT_PROD`  | `aif-gpt-4-1-mini-NER-2026-05-11-aif-gst-ussc-01-prod` | score.py:68 |

`run_ner()` picks one based on `ENVIRONMENT` and falls back to the other if the call fails.

### D) Development notebooks (`Development files/` — NOT deployed)

These are **offline data-prep tools** used to *build* the dependency files. They DO touch
external data stores, but they never run in production:

| Service | Where (notebook) | Purpose |
|---------|------------------|---------|
| **Snowflake** | `Development files/Get Data from Snowflake.ipynb` | Pull raw grade/material data to generate the dependency files. |
| **Elasticsearch** | `Development files/NER_Training/2 Out of scope Data.ipynb`, `3 Generate Training Data.ipynb`, `9 DEV model testing...ipynb`, and a few others | Source out-of-scope data / training data. Connects via `from elasticsearch import Elasticsearch`. |

> 🔐 **Security note:** the Elasticsearch notebook (`2 Out of scope Data.ipynb`, lines ~67–84)
> contains **hard-coded Elasticsearch URLs and plaintext passwords** for nprod/test/prod
> clusters. These are committed in the repo and should be treated as **leaked credentials** —
> rotate them and move to a secrets store. They are not used by the runtime service, but they
> are a real exposure in the repository.

### Summary diagram

```
   ┌─────────────────────── DEPLOYED RUNTIME (onlinescoring/) ───────────────────────┐
   │   request ─► score.run() ─► ner_helper.run_ner() ─► Azure OpenAI (GPT-4.1-mini)  │
   │   (NO Elasticsearch · NO Snowflake · NO Postgres · NO REST calls · NO routes)    │
   └─────────────────────────────────────────────────────────────────────────────────┘

   ┌─────────────── DEV-TIME ONLY (Development files/*.ipynb) — not deployed ──────────┐
   │   Snowflake  ─►  pull source data                                                 │
   │   Elasticsearch ─► pull out-of-scope / training data   ──►  build dependency files │
   └───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Data sources — exact tables, columns & indexes queried

> All of this is **dev-time only** (inside `Development files/*.ipynb`). The deployed runtime
> reads none of it directly — these queries build the static dependency files.
>
> ⚠️ **There is NO Postgres.** The relational database used is **Azure SQL / Microsoft SQL
> Server** (connected via `pymssql` + SQLAlchemy: `mssql+pymssql://...mssqldb-gst-dev-ussc-01`).
> The two real data stores are **Snowflake** (primary) and **Azure SQL Server** (certifications).

### 🟦 A) Snowflake

**Connection:** database `ANALYTICS_DEV`, schema `GST_CURATED` / `snowpark`,
warehouse `reporting_wh`, role `data_analyst_gst`, account `celanese-celanytics`.
Source notebooks: `Get Data from Snowflake.ipynb`, `2. Create normalized Grade and Competitor Grade names.ipynb`.

| Table | Columns selected | Used to build |
|-------|------------------|----------------|
| `GST_Curated.SPT` | `PRODUCT_LINE`, `POLYMER`, `PRODUCT_CD`, `PROPERTY_NAME`, `NON_STD_TEST_COND_DESC`, `VALUE_ASSMNT_SI`, `UNIT_OF_MEAS_SI`, `TEMP_C2` | PROPERTY & FILLER values (split on `TEMP_C2`) |
| `GST_Curated.FEATURE` | `PRODUCT_CD`, `VALUE_ASSMNT_SI` (→ FEATURE); filtered by `PROPERTY_NAME` ∉ (Approval, Delivery Form, Regulatory) | FEATURE values |
| `GST_Curated.APPLICATION_MAP_SFDC` | `PRODUCT_NAME`, `INDUSTRY_GROUP`, `MARKET`, `MARKET_SEGMENT`, `SUB_SEGMENT`, `APPLICATION` | APPLICATION / INDUSTRY mapping |
| `GST_Curated.COMPETITOR_DATA` | `SELECT *` → `PRODUCT_LINE`, `CELANESE_GRADE_NAME`, `CELANESE_POLYMER_TYPE`, `COMPETITOR`, `COMPETITOR_GRADE`, `COMPETITOR_POLYMER_TYPE` | COMPETITOR_GRADE mapping |
| `GST_Curated.CTQ` | `SELECT *` | reference data |
| `GST_Curated.TDS_MAPPING` | `SELECT *` | reference data |
| `GST_Curated.RAILWAY` | `SELECT *` (17 columns) | RAILWAY_CERT values |
| `GST_Curated.WATER_APPROVALS` | `SELECT *` (15 columns) | WATER_CERT values |
| `GST_Curated.NSF` | `SELECT *` (5 columns) | NSF_CERT values |
| `GST_CURATED.OUT_OF_SCOPE_BRANDS` | `BRAND` | out-of-scope brands |
| `GST_CURATED.OUT_OF_SCOPE_POLYMERS` | `POLYMER` | out-of-scope polymers |
| `GST_CURATED.OUT_OF_SCOPE_GRADES` | `GRADE` | out-of-scope grades |
| `GST_CURATED.OUT_OF_SCOPE_FILLERS` | `FILLER` | out-of-scope fillers |
| `SYNONYM` (gst_curated) | `DEFINED_NAME`, `SYNONYMS`, `TYPE` | brand/grade synonym expansion |

### 🟥 B) Azure SQL / SQL Server (NOT Postgres)

**Connection:** `mssql+pymssql://...@mssql-gst-dev-ussc-01.database.windows.net/mssqldb-gst-dev-ussc-01`.
Source notebook: `Get Data from Snowflake.ipynb` (the certification section).

| Table | Columns referenced | Used to build |
|-------|--------------------|----------------|
| `SFTRaw.Nsf` | `standard`, `primary_trade_name`, `nsf61_23c`, `nsf61_82c` (+ `doc_type`) | NSF_CERT (nsf 42 / 51 / 61) |
| `SFTRaw.Railway` | `material_name`, `railway_certification` (+ `norm`, `specification`, `classification`) | RAILWAY_CERT |
| `SFTRaw.WaterApprovals` | `wras_23c/60c/85c`, `ktw_bwgl_en16421_p2_23c/60c/85c`, `ktw_bwgl_en16421_p2_en16422`, `acs_23c/60c/85c`, `grade` | WATER_CERT (date-validity filtered) |
| `SFTRaw.Feature` | `PRODUCT_CD`, `VALUE_ASSMNT_SI`, `TEMP_C2`, `property_name` (filter `='Approval'`) | AUTO_CERT (OEM approvals) |
| `SftTransform.df_cert_remapped_pipeline` | *(written, not read)* `grade`, `certifications` | output table of remapped certs |

### 🟩 C) Elasticsearch

**Connection:** Elastic Cloud v8.16.2, `https://elast-gst-*-ussc-01.es...:9243`, user `elastic`.
Source notebooks: `2. Create normalized Grade and Competitor Grade names.ipynb`,
`Sample user queries from templates for training and testing - 650K.ipynb`.

Queries are `match_all` (fetch all docs) and read the **entire `_source`** (no column
projection), so the "columns" are whole documents from these indexes:

| Index | Query | Pulled into |
|-------|-------|-------------|
| `filter_polymer` | `match_all`, size 100, full `_source` | polymer filter values |
| `filter_ul` | `match_all`, size 100, full `_source` | UL category values |
| `filter_property` | `match_all`, size 1000, full `_source` | property filter values |

### ⬜ D) Postgres

| Engine | Used? |
|--------|-------|
| **PostgreSQL** | ❌ Not used anywhere in the repo (runtime or dev). The relational DB is SQL Server, see section B. |

### Where each source ends up (dev pipeline → dependency files)

```
   Snowflake  ─┐
               ├─►  *.ipynb processing  ─►  dependencies/*.json + *.csv  ─►  used by score.py init()
   Azure SQL  ─┤      (clean / normalize / merge)
   Elastic    ─┘
```

> 🔐 **Security:** the same notebooks contain **hard-coded credentials** — Elasticsearch
> passwords, the SQL Server connection string (`sqldbadmin:rYxz&5m~...`), and Azure ML endpoint
> API keys (sbert/ner). Treat all of these as **leaked**; rotate them and move to a secrets store.

---

## 🔎 How this list was verified

Searched the entire `onlinescoring/` folder for every file-loading call
(`open`, `read_csv`, `read_excel`, `json.load`, `load_dotenv`, `getenv`). Results:
- **All 9 data-file loads** are in `score.py` `init()`.
- **The only credential reads** are in `ner_helper.py` (`.env` via `load_dotenv`).
- No other module loads any data file.

⬅️ Back to [`00-README-START-HERE.md`](00-README-START-HERE.md) · Related: [`08-how-to-test-locally.md`](08-how-to-test-locally.md)

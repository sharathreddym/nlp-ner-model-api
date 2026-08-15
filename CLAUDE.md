# CLAUDE.md

Project context and working notes for the **Celanese NER service** (`NLP-NER-Model-API`).
Keep this file updated so future sessions have the key facts without re-deriving them.

---

## What this project is

A **Named Entity Recognition (NER)** service that turns a free-text material search
(e.g. `"30% glass filled UV nylon 66 UL94V0"`) into a structured dictionary of **17 entity
types** (GRADE, POLYMER, BRAND, FILLER, PROPERTY, FEATURE, certifications, INDUSTRY, etc.).
It powers product search on **askchemille.com**.

- **Entry point:** `onlinescoring/score.py` → Azure ML calls `init()` once, `run()` per request.
- **Orchestrator:** `onlinescoring/ner_helper.py` → `run_ner()`.
- **Pipeline:** `pre_processing.py` (clean text) → **Azure OpenAI GPT-4.1-mini** (extract) →
  `post_processing.py` + rules (unit conversion, out-of-scope, dedup).
- **Hybrid design:** LLM for language understanding + deterministic rules for business logic.
  Fast-paths (exact GRADE / SAP id / FEATURE) skip the LLM.
- **Deployed as:** Azure ML managed online endpoint `gst-ner-endpoint-dev` (workspace
  `ml-gst-dev-usscc-01`, RG `rg-gst-dev-ussc-01`).

Detailed KT docs: **`KT learning/`** (start at `00-README-START-HERE.md`; bug case study in
`12-bug-217995-zytel-casestudy.md`).

---

## Bugs resolved this effort

| Bug | Grade | Root cause | Status |
|-----|-------|-----------|--------|
| **217995** | `Zytel 101F BK009` | grade was in the out-of-scope lists and missing from the in-scope lists in `dependencies/outOfScopeData.json` | ✅ Fixed |
| **217962** | `Zytel 103HSL BK080` | same root cause (newly-added grade not yet in in-scope master) | ✅ Fixed by same data regen |
| (discussion) | `Celanyl XS3 GF60 BG 1019/C EF` | full grade already in-scope but returns 0 results — likely color-code strip / downstream search | ⏳ Separate investigation |

### Root cause (data, not code)
`post_processing.identify_out_of_scope_items()` only acts on `result["GRADE"]`. A grade is
flagged out-of-scope when it appears in the OOS `grades`/`gradesExternal` lists and is absent
from `gradesInScope`/`gradesInScopeExternal`. The Zytel grades sat in the OOS lists because the
Snowflake in-scope master (`GST_CURATED.SPT`) only held a **color-code variant** (`BKB009` vs the
searched `BK009`), so the notebook's de-confliction (`OOS grades − in-scope grades`) never removed
them.

### Fix
1. Corrected the **Snowflake source** so the grades are in-scope in `SPT`.
2. Regenerated `dependencies/outOfScopeData.json` via
   `Development files/1. Clean out of scope Data.ipynb` (writes **only** this one file).
3. Validated: `zytel101fbk009` / `zytel103hslbk080` moved out of the OOS lists into the in-scope
   lists; end-to-end simulation shows **not flagged** for internal & external.

**The data fix is code-independent** and ships on the existing image — a rebuild is not required
for it.

---

## Environment / deployment notes (Python 3.8 → 3.10 upgrade)

The deploy also carried a **Python 3.8 → 3.10** upgrade (3.8 is EOL). Container Python = **3.10.20**.

### `environment/conda.yaml` — the working set
```yaml
channels: [conda-forge]
dependencies:
  - python=3.10
  - numpy=1.24.4
  - pip
  - pip:
    - azureml-defaults==1.62.0
    - inference-schema[numpy-support]~=1.8      # NOT ==1.5 (conflicts with azureml-defaults 1.62)
    - openai==1.61.1
    - pandas==2.0.3
    - thefuzz==0.22.1
    - rapidfuzz
    - openpyxl==3.1.5
    - python-dotenv==1.0.1
    # DO NOT pin pydantic / pydantic-core — let azureml-defaults choose (needs ~=2.11/2.12)
```
**Principle:** only pin the app libraries; never pin things `azureml-defaults` controls
(`pydantic`, `azureml-inference-server-http`, etc.). Unused libs removed: `spello`, `nltk`,
`sympy`, `contractions`, `regex`, `joblib`, `python-Levenshtein` (code doesn't import them;
`thefuzz` uses `rapidfuzz`).

### Deploy pieces
- **Code** = `./onlinescoring` (uploaded per deploy). Must include **`onlinescoring/.env`**.
- **Data** = registered model `gst-gpt-ner-model` (version bumped to include the updated
  `dependencies/` folder). Reference the **new** model version in the deployment.
- **Env** = `gst-ner-env`. To skip a rebuild, reference a previously-succeeded version instead of
  rebuilding from `conda.yaml`.

### `.env` (required, not in git)
`onlinescoring/.env` must contain the Azure OpenAI creds read by `ner_helper.py`:
```
azure_openai_key_aif=<key>
azure_openai_endpoint_aif=<endpoint>
api_version_aif=<version>
```
It is `.gitignore`d (correct) but **not** `.amlignore`d, so it deploys. Missing `.env` →
`AzureOpenAI(api_key=None)` raises at import → **container crashes at startup**
(`User container has crashed or terminated`).

---

## Gotchas hit this effort (so we don't repeat them)

- **Image build timeouts / failures** on this Private-Link workspace: `imageBuildCompute` is
  `null` → builds run on **serverless** compute that can't reach the private storage
  `sagmlstoredev01` → hang/timeout. Durable fix: set a dedicated in-VNet **image-build compute
  cluster** (or reuse a good env version to skip building).
- **`ResolutionImpossible` in the build**: caused by stale pins (`inference-schema==1.5`,
  `pydantic==2.10.6`) vs `azureml-defaults==1.62.0`. **Validate the full `conda.yaml` locally**
  (`pip install --dry-run azureml-defaults==1.62.0 "inference-schema[numpy-support]~=1.8" ...`)
  **before** the ~20-min cloud build. Note: validating only `requirements.txt` misses these
  because it omits `azureml-defaults`.
- **Auth:** notebooks use `AzureCliCredential` (not `DefaultAzureCredential`); token expires ~8h →
  `az login --use-device-code` to refresh.
- **Snowflake data notebooks** need Python 3.10/3.11 with the `[pandas]` extra (pyarrow); they use
  `authenticator=externalbrowser` (SSO, needs VPN). `1. Clean out of scope Data.ipynb` regenerates
  only `outOfScopeData.json`.
- **Dependency data files & `.env` are not in git** — a fresh checkout must restore them before the
  service can start. Watch for 32 KB clipboard truncation and the 4-sheet `abbreviations.xlsx`
  (`PROPERTY/FILLER/FEATURE/common_abb`).

---

## Verify a grade end-to-end (dev)
```python
import json
def check_grade(query, user_type=None):
    payload = {"data": query}
    if user_type: payload["user_type"] = user_type
    with open("req.json","w") as f: json.dump(payload, f)
    r = json.loads(ml_client.online_endpoints.invoke(
        endpoint_name=endpoint_name, deployment_name="blue", request_file="req.json"))
    ent, oos = r["modelOutput"]["entities"], r["modelOutput"]["outOfScope"]
    print(query, "| GRADE:", ent["GRADE"], "| COMP:", ent["COMPETITOR_GRADE"],
          "| oos.active:", oos["active"], "| oos.GRADE:", oos["entities"]["GRADE"])

check_grade("Zytel 101F BK009")          # PASS = not in oos.GRADE, appears in GRADE/COMPETITOR_GRADE
check_grade("Zytel 103HSL BK080")
```

---

## Outstanding / next steps
- [ ] Confirm dev verification for the Zytel grades, then **promote to prod** (same
      `outOfScopeData.json` + redeploy prod endpoint).
- [ ] Investigate **Celanyl XS3 GF60 BG 1019/C EF** (0 results despite in-scope) — capture the NER
      `entities.GRADE` to see if the color code is being dropped.
- [ ] Add the missing `gradesExternal` de-confliction line in `1. Clean out of scope Data.ipynb`.
- [ ] Pin the base image away from `:latest`; set `imageBuildCompute` to a dedicated cluster.
- [ ] **Move secrets to Key Vault** (Snowflake, DevOps PAT, Azure OpenAI key; remove hard-coded
      creds in dev notebooks) and **standardize the repo structure** (runtime vs notebooks vs
      config vs data; drop committed temp files).

---

## Handy references
- Workspace: `ml-gst-dev-usscc-01` · RG `rg-gst-dev-ussc-01` · sub `710c48d7-...` · tenant `7a3c88ff-...`
- ACR: `crgstmlnpussc01.azurecr.io` · Storage: `sagmlstoredev01`
- Snowflake: account `celanese-celanytics.privatelink`, db `analytics_dev`, schema `GST_CURATED`,
  warehouse `reporting_wh` (SSO / VPN required)
- Model: `gst-gpt-ner-model` · Env: `gst-ner-env` · Endpoint: `gst-ner-endpoint-dev` (deployment `blue`)

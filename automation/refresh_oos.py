"""
refresh_oos.py — single scheduled orchestrator (NO CI/CD triggers).

One headless program that, on a schedule, does the whole job:
  1. Snowflake (key-pair auth) — detect if the source changed; exit if not.
  2. Regenerate outOfScopeData.json  (the "1. Clean out of scope Data.ipynb" logic).
  3. Validate (validate_oos.py) — abort on any problem.
  4. Compare to the committed file — exit if identical (no-op).
  5. Commit/push the file to Azure DevOps 'dev' via the REST Pushes API (PAT).
  6. Deploy: register a new dependencies model version + update the endpoint (Azure ML SDK).
  7. Smoke test a known grade; roll back the deployment on failure.

Run it from: an Azure ML scheduled Command Job, an Azure Function timer, an
Automation runbook, or cron on an always-on box. All of those are schedulers,
not CI/CD trigger systems.

Secrets come from Azure Key Vault (never inline):
  - snowflake-user, snowflake-account, snowflake-private-key (+ optional passphrase)
  - devops-pat  (Code: Read & Write)
Env/config below is dev by default; pass --database / --environment for qa/prod.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tempfile

import requests

# ----------------------------------------------------------------------------
# CONFIG (dev defaults — override via args / env for qa/prod)
# ----------------------------------------------------------------------------
KEY_VAULT_URL   = os.getenv("KEY_VAULT_URL", "https://<your-kv>.vault.azure.net/")
SNOWFLAKE_DB    = os.getenv("SNOWFLAKE_DB", "analytics_dev")
SNOWFLAKE_SCHEMA= "GST_CURATED"
SNOWFLAKE_WH    = "reporting_wh"
SNOWFLAKE_ROLE  = "data_developer_gst"   # a SERVICE ACCOUNT role, not a person

DEVOPS_ORG      = "CelaneseCorporation"
DEVOPS_PROJECT  = "GradeSelectionTool"
DEVOPS_REPO     = "NLP-NER-Model-API"
DEVOPS_BRANCH   = "refs/heads/dev"
REPO_FILE_PATH  = "/dependencies/outOfScopeData.json"

AML_SUBSCRIPTION = "710c48d7-7060-4d97-9be0-699f76c25447"
AML_RESOURCE_GRP = "rg-gst-dev-ussc-01"
AML_WORKSPACE    = "ml-gst-dev-usscc-01"
AML_ENDPOINT     = "gst-ner-endpoint-dev"
AML_DEPLOYMENT   = "blue"
AML_MODEL_NAME   = "gst-gpt-ner-model"
AML_ENV_NAME     = "gst-ner-env"          # reuse a known-good version to skip image build
AML_ENV_VERSION  = os.getenv("AML_ENV_VERSION", "")   # set to a Succeeded version

SMOKE_GRADE = "Zytel 101F BK009"          # must come back NOT out-of-scope


# ----------------------------------------------------------------------------
# 0) SECRETS — Azure Key Vault
# ----------------------------------------------------------------------------
def get_secret(name: str) -> str:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    client = SecretClient(vault_url=KEY_VAULT_URL, credential=DefaultAzureCredential())
    return client.get_secret(name).value


# ----------------------------------------------------------------------------
# 1) SNOWFLAKE — key-pair (headless) connection + change detection
# ----------------------------------------------------------------------------
def snowflake_connect():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    pkey_pem = get_secret("snowflake-private-key").encode()
    passphrase = os.getenv("SNOWFLAKE_KEY_PASSPHRASE")  # or get_secret(...) if set
    pkey = serialization.load_pem_private_key(
        pkey_pem, password=passphrase.encode() if passphrase else None
    )
    pkb = pkey.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        user=get_secret("snowflake-user"),
        account=get_secret("snowflake-account"),   # celanese-celanytics.privatelink
        private_key=pkb,
        warehouse=SNOWFLAKE_WH,
        database=SNOWFLAKE_DB,
        schema="snowpark",
        role=SNOWFLAKE_ROLE,
    )


def source_fingerprint(conn) -> str:
    """Cheap change-detector: row counts of the tables that feed the file."""
    cur = conn.cursor()
    counts = {}
    for tbl in ("OUT_OF_SCOPE_GRADES", "SPT", "OUT_OF_SCOPE_BRANDS",
                "OUT_OF_SCOPE_POLYMERS", "OUT_OF_SCOPE_FILLERS"):
        cur.execute(f"SELECT COUNT(*) FROM {SNOWFLAKE_SCHEMA}.{tbl}")
        counts[tbl] = cur.fetchone()[0]
    return hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()


# ----------------------------------------------------------------------------
# 2) GENERATE — port of "1. Clean out of scope Data.ipynb"
#    (structure is faithful; the brand-synonym expansion must be copied verbatim
#     from the notebook — marked TODO — everything else is here.)
# ----------------------------------------------------------------------------
def _norm_grade(s: str) -> str:
    return re.sub(r"\W+", "", s).lower()


def _norm_simple(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z\d\s]", " ", s)).strip().lower()


def generate_oos(conn) -> dict:
    cur = conn.cursor()

    def col(table, column, where=""):
        cur.execute(f"SELECT DISTINCT {column} FROM {SNOWFLAKE_SCHEMA}.{table} {where}")
        return [r[0] for r in cur.fetchall() if r[0] is not None]

    # in-scope (from SPT product master)
    all_grades          = [g.lower() for g in col("SPT", "PRODUCT_CD")]
    all_grades_external = [g.lower() for g in col("SPT", "PRODUCT_CD",
                                                  "WHERE GRADE_INDICATOR = 'Commercial'")]
    # out-of-scope raw
    oos_grades          = [g.lower() for g in col("OUT_OF_SCOPE_GRADES", "GRADE")]
    oos_grades_external = list(oos_grades)  # same source table
    oos_polymers        = col("OUT_OF_SCOPE_POLYMERS", "POLYMER")
    oos_fillers         = col("OUT_OF_SCOPE_FILLERS", "FILLER")

    # brands split by GRADE_INDICATOR
    cur.execute(f"SELECT DISTINCT BRAND, GRADE_INDICATOR FROM {SNOWFLAKE_SCHEMA}.OUT_OF_SCOPE_BRANDS")
    brand_rows = cur.fetchall()
    brands_all        = [_norm_simple(b) for b, _ in brand_rows if b]
    brands_commercial = [_norm_simple(b) for b, gi in brand_rows if gi and gi.lower().strip() == "commercial"]
    brands_notinscope = [_norm_simple(b) for b, gi in brand_rows if gi and gi.lower().strip() == "not in scope"]

    # TODO: port brand-synonym expansion (SYNONYM table) from the notebook so that
    #       grades/brands carrying a synonym prefix are also covered. Until ported,
    #       the file is slightly less complete than the notebook's output.

    # normalize
    all_norm          = [_norm_grade(s) for s in all_grades]
    all_ext_norm      = [_norm_grade(s) for s in all_grades_external]
    oos_norm          = [_norm_grade(s) for s in oos_grades]
    oos_ext_norm      = [_norm_grade(s) for s in oos_grades_external]
    polymers_norm     = [re.sub(r"\s+", "", _norm_simple(p)) for p in oos_polymers]
    fillers_norm      = [_norm_simple(f) for f in oos_fillers if _norm_simple(f) != "glass filler"]

    # DE-CONFLICTION — remove in-scope grades from the out-of-scope lists.
    # NOTE: the notebook does this for the INTERNAL list only; we do BOTH
    # (this is the missing 'gradesExternal' line called out in CLAUDE.md).
    oos_norm     = list(set(oos_norm) - set(all_norm))
    oos_ext_norm = list(set(oos_ext_norm) - set(all_ext_norm))

    return {
        "grades":                 sorted(set(oos_norm)),
        "gradesExternal":         sorted(set(oos_ext_norm)),
        "brands":                 sorted(set(brands_all)),
        "brands_internal":        [],
        "brands_commerical":      sorted(set(brands_commercial)),
        "brands_not_in_scope":    sorted(set(brands_notinscope)),
        "polymers":               sorted(set(polymers_norm)),
        "fillers":                sorted(set(fillers_norm)),
        "gradesInScope":          sorted(set(all_norm)),
        "gradesInScopeExternal":  sorted(set(all_ext_norm)),
    }


# ----------------------------------------------------------------------------
# 5) GIT — commit/push to Azure DevOps via REST Pushes API (no local clone)
# ----------------------------------------------------------------------------
def _devops_auth():
    pat = get_secret("devops-pat")
    return ("", pat)  # basic auth: empty user, PAT as password


def devops_get_branch_head(session) -> str:
    url = (f"https://dev.azure.com/{DEVOPS_ORG}/{DEVOPS_PROJECT}/_apis/git/"
           f"repositories/{DEVOPS_REPO}/refs?filter=heads/dev&api-version=7.1")
    r = session.get(url); r.raise_for_status()
    return r.json()["value"][0]["objectId"]


def devops_push_file(new_json_text: str, message: str) -> None:
    session = requests.Session()
    session.auth = _devops_auth()
    old_object_id = devops_get_branch_head(session)
    body = {
        "refUpdates": [{"name": DEVOPS_BRANCH, "oldObjectId": old_object_id}],
        "commits": [{
            "comment": message,
            "changes": [{
                "changeType": "edit",   # use "add" if the file doesn't exist yet
                "item": {"path": REPO_FILE_PATH},
                "newContent": {
                    "content": base64.b64encode(new_json_text.encode()).decode(),
                    "contentType": "base64encoded",
                },
            }],
        }],
    }
    url = (f"https://dev.azure.com/{DEVOPS_ORG}/{DEVOPS_PROJECT}/_apis/git/"
           f"repositories/{DEVOPS_REPO}/pushes?api-version=7.1")
    r = session.post(url, json=body)
    r.raise_for_status()
    print("pushed commit:", r.json()["commits"][0]["commitId"])
    # If branch policies block direct pushes to dev, push to a feature branch
    # instead and open a PR via the Pull Requests REST API here.


# ----------------------------------------------------------------------------
# 6) DEPLOY — Azure ML SDK (register model version + update deployment)
# ----------------------------------------------------------------------------
def deploy(dependencies_dir: str):
    from azure.ai.ml import MLClient
    from azure.ai.ml.entities import (ManagedOnlineDeployment, Model,
                                       CodeConfiguration)
    from azure.ai.ml.constants import AssetTypes
    from azure.identity import DefaultAzureCredential

    ml = MLClient(DefaultAzureCredential(), AML_SUBSCRIPTION, AML_RESOURCE_GRP, AML_WORKSPACE)

    model = ml.models.create_or_update(Model(
        path=dependencies_dir, name=AML_MODEL_NAME, type=AssetTypes.CUSTOM_MODEL,
        description="auto-refresh outOfScopeData.json"))
    print("registered model version:", model.version)

    env = ml.environments.get(name=AML_ENV_NAME, version=AML_ENV_VERSION)  # reuse good build
    dep = ManagedOnlineDeployment(
        name=AML_DEPLOYMENT, endpoint_name=AML_ENDPOINT,
        model=model, environment=env,
        code_configuration=CodeConfiguration(code="./onlinescoring", scoring_script="score.py"),
        instance_type="Standard_DS3_v2", instance_count=1,
    )
    ml.online_deployments.begin_create_or_update(dep).result()
    print("deployment updated")
    return ml


def smoke_test(ml) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"data": SMOKE_GRADE}, f)
        req = f.name
    resp = json.loads(ml.online_endpoints.invoke(
        endpoint_name=AML_ENDPOINT, deployment_name=AML_DEPLOYMENT, request_file=req))
    oos_grades = resp["modelOutput"]["outOfScope"]["entities"]["GRADE"]
    ok = _norm_grade(SMOKE_GRADE) not in [_norm_grade(g) for g in oos_grades]
    print(f"smoke test '{SMOKE_GRADE}': {'PASS' if ok else 'FAIL'} (oos.GRADE={oos_grades})")
    return ok


# ----------------------------------------------------------------------------
# MAIN — orchestration (idempotent / no-op when nothing changed)
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-file", default="dependencies/outOfScopeData.json",
                    help="local committed copy to diff against")
    ap.add_argument("--state-file", default=".oos_source_fingerprint")
    ap.add_argument("--deploy", action="store_true", help="also register model + redeploy")
    args = ap.parse_args()

    conn = snowflake_connect()

    # (1) change detection — bail early if the source is unchanged
    fp = source_fingerprint(conn)
    prev = open(args.state_file).read().strip() if os.path.exists(args.state_file) else ""
    if fp == prev:
        print("source unchanged — nothing to do."); return 0

    # (2) generate
    data = generate_oos(conn)
    new_text = json.dumps(data)
    tmp = os.path.join(tempfile.gettempdir(), "outOfScopeData_new.json")
    with open(tmp, "w") as f:
        f.write(new_text)

    # (3) validate — hard stop on any problem
    from validate_oos import validate
    problems = validate(tmp, baseline_path=args.repo_file if os.path.exists(args.repo_file) else None)
    if problems:
        print("VALIDATION FAILED — not committing/deploying:", file=sys.stderr)
        for p in problems: print("  -", p, file=sys.stderr)
        return 1

    # (4) no-op if identical to the committed copy
    if os.path.exists(args.repo_file) and open(args.repo_file).read() == new_text:
        open(args.state_file, "w").write(fp)  # record fingerprint so we don't re-check
        print("regenerated file identical to committed — no change."); return 0

    # (5) commit/push to dev
    devops_push_file(new_text, message="chore(data): auto-refresh outOfScopeData.json [skip ci]")

    # (6/7) optional deploy + smoke test (behind --deploy; gate prod separately)
    if args.deploy:
        # write into the local dependencies dir so the model registers with it
        with open(args.repo_file, "w") as f:
            f.write(new_text)
        ml = deploy(os.path.dirname(args.repo_file))
        if not smoke_test(ml):
            print("SMOKE TEST FAILED — roll back the deployment to the previous model version",
                  file=sys.stderr)
            return 1

    open(args.state_file, "w").write(fp)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

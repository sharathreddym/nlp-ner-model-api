# -*- coding: utf-8 -*-
"""
Follow-up to knn_feasibility.py.

Experiment 1 showed retrieval-over-examples routes well (72.5% key-set) but
copies badly (17.1% exact). This asks WHY, by testing where entity *values*
actually live:

  A. are gold values findable in the TRAINING EXAMPLES?   (example index)
  B. are gold values findable in the GAZETTEER?           (dependencies/)
  C. does majority-vote over top-k beat NN-1 for routing?

If B >> A, the design is settled: two indexes, not one.
"""
import ast
import json
import os
import random
import sys
from collections import Counter, defaultdict

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DEP = os.path.join(ROOT, "dependencies")
SEED, TEST_FRAC, K = 42, 0.10, 16

J = lambda n: json.load(open(os.path.join(DEP, n), encoding="utf-8"))
UV, NUV = J("unique_values_22_02_24.json"), J("normalized_unique_values_for_grade_mapping.json")
CR = J("chemical_resistance.json")

flat = lambda seq: {str(x).lower().strip() for x in seq if isinstance(x, (str, int, float))}
nflat = lambda seq: {str(e[0]).lower().strip() for e in seq if isinstance(e, list) and e} | \
                    {str(e).lower().strip() for e in seq if isinstance(e, str)}

chem_vals = set()
for cat, items in CR.items():
    chem_vals.add(str(cat).lower())
    for it in items:
        if isinstance(it, dict):
            for k in ("chemical_sub_category", "sub_category", "name"):
                if it.get(k):
                    chem_vals.add(str(it[k]).lower())
            for s in (it.get("synonyms") or []):
                chem_vals.add(str(s).lower())

GAZ = {
    "GRADE": flat(UV["GRADE"]) | flat(UV["GRADE_WITHOUT_BRAND"]) | nflat(NUV["GRADE"]),
    "COMPETITOR_GRADE": flat(UV["COMPETITOR_GRADE"]) | flat(UV["COMPETITOR_GRADE_TRANSFORMED"])
                        | flat(UV["COMP_GRADE_WITHOUT_BRAND"]) | nflat(NUV["COMPETITOR_GRADE"]),
    "BRAND": flat(UV["BRAND"]) | nflat(NUV["BRAND"]) | nflat(NUV["COMPETITOR_BRAND"]),
    "POLYMER": flat(UV["POLYMER"]),
    "PROPERTY": flat(UV["PROPERTY"]),
    "FILLER": flat(UV["FILLER"]),
    "FEATURE": flat(UV["FEATURE"]) | nflat(NUV["FEATURE"]),
    "APPLICATION": flat(UV["APPLICATION"]),
    "AUTO_CERT": flat(UV["CERTIFICATION"]) | nflat(NUV["AUTO_CERT"]),
    "RAILWAY_CERT": flat(UV["CERTIFICATION"]),
    "WATER_CERT": flat(UV["CERTIFICATION"]),
    "NSF_CERT": flat(UV["CERTIFICATION"]),
    "MEDICAL_CERT": nflat(NUV["MEDICAL_CERT"]),
    "CHEMICAL_RESISTANCE": chem_vals | nflat(NUV["CHEMICAL_RESISTANCE"]),
}
print("gazetteer loaded:")
for k in sorted(GAZ):
    print("   %-22s %s" % (k, f"{len(GAZ[k]):,}"))


def atoms(o):
    """(entity, value) pairs we could hope to resolve."""
    out = set()
    for k, v in o.items():
        if not v or k in ("INDUSTRY", "REGION", "PROCESSING", "DELIVERY_FORM"):
            continue
        for item in (v if isinstance(v, list) else [v]):
            if isinstance(item, str):
                out.add((k, item.lower().strip()))
            elif isinstance(item, dict):
                if item.get("property_name"):
                    out.add((k, str(item["property_name"]).lower().strip()))
                for x in (item.get("filler_name") or []):
                    out.add((k, str(x).lower().strip()))
                for key in ("chemical_sub_category", "chemical_category"):
                    if item.get(key):
                        out.add((k, str(item[key]).lower().strip()))
                for c in (item.get("CERTS") or item.get("certs") or []):
                    out.add((k, str(c).lower().strip()))
                if item.get("OEM") or item.get("oem"):
                    out.add((k, str(item.get("OEM") or item.get("oem")).lower().strip()))
    return out


df = pd.read_excel(os.path.join(ROOT, "Development files", "Training_Data_14_07_2026.xlsx"))
df = df[df["Query"].notna()].reset_index(drop=True)
rows = []
for q, o in zip(df["Query"].astype(str), df["Output"]):
    try:
        rows.append((q.strip().lower(), ast.literal_eval(o) if isinstance(o, str) else o))
    except Exception:
        pass

rnd = random.Random(SEED)
idx = list(range(len(rows)))
rnd.shuffle(idx)
n_test = int(len(idx) * TEST_FRAC)
test_i, index_i = idx[:n_test], idx[n_test:]
index_q = [rows[i][0] for i in index_i]
qset = set(index_q)
kept = [i for i in test_i if rows[i][0] not in qset]

EX_ATOMS = set()
for i in index_i:
    EX_ATOMS |= atoms(rows[i][1])

print("\n%s held-out rows, example-index atoms: %s\n" % (f"{len(kept):,}", f"{len(EX_ATOMS):,}"))

# ---------------------------------------------- A/B: where do values live?
# The gazetteer stores STRIPPED forms ('celanex20022'); training stores readable
# ones ('celanex 2002-2'). Compare on both, or GRADE coverage reads far too low.
import re as _re
_k = lambda s: _re.sub(r"[^a-z0-9]", "", str(s).lower())
GAZ_N = {e: {_k(v) for v in vals} for e, vals in GAZ.items()}
EX_N = {(e, _k(v)) for (e, v) in EX_ATOMS}

per = defaultdict(lambda: Counter())
for i in kept:
    for (e, v) in atoms(rows[i][1]):
        per[e]["n"] += 1
        if (e, v) in EX_ATOMS or (e, _k(v)) in EX_N:
            per[e]["ex_exact"] += 1
        if v in GAZ.get(e, set()) or _k(v) in GAZ_N.get(e, set()):
            per[e]["gaz"] += 1
        if (e, v) in EX_ATOMS or (e, _k(v)) in EX_N or \
           v in GAZ.get(e, set()) or _k(v) in GAZ_N.get(e, set()):
            per[e]["either"] += 1

print("=" * 74)
print("WHERE DO ENTITY VALUES LIVE?   (held-out gold values, % findable)")
print("=" * 74)
print("%-22s %8s %13s %13s %10s" % ("entity", "values", "in EXAMPLES", "in GAZETTEER", "EITHER"))
tot_n = tot_ex = tot_gz = tot_ei = 0
for e in sorted(per, key=lambda x: -per[x]["n"]):
    c = per[e]
    tot_n += c["n"]; tot_ex += c["ex_exact"]; tot_gz += c["gaz"]; tot_ei += c["either"]
    print("%-22s %8s %12.1f%% %12.1f%% %9.1f%%"
          % (e, f"{c['n']:,}", 100.0 * c["ex_exact"] / c["n"],
             100.0 * c["gaz"] / c["n"], 100.0 * c["either"] / c["n"]))
print("-" * 74)
print("%-22s %8s %12.1f%% %12.1f%% %9.1f%%" % ("ALL", f"{tot_n:,}",
      100.0 * tot_ex / tot_n, 100.0 * tot_gz / tot_n, 100.0 * tot_ei / tot_n))

# ---------------------------------------------- C: vote vs NN-1 for routing
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
X = vec.fit_transform(index_q)
Q = vec.transform([rows[i][0] for i in kept])
nn = NearestNeighbors(n_neighbors=K, metric="cosine", algorithm="brute").fit(X)
dist, nbr = nn.kneighbors(Q)
ikeys = [frozenset(k for k, v in rows[i][1].items() if v) for i in index_i]

print("\n" + "=" * 74)
print("ROUTING: predicting WHICH ENTITY KEYS are present")
print("=" * 74)
for k in (1, 4, 8, 16):
    exact = partial = 0
    for r, ns in enumerate(nbr):
        gold = frozenset(x for x, v in rows[kept[r]][1].items() if v)
        if k == 1:
            pred = ikeys[ns[0]]
        else:                                   # per-key majority vote
            cnt = Counter()
            for j in ns[:k]:
                cnt.update(ikeys[j])
            pred = frozenset(x for x, c in cnt.items() if c > k / 2)
        if pred == gold:
            exact += 1
        if gold and gold <= pred:
            partial += 1
    tag = "NN-1" if k == 1 else "vote@%d" % k
    print("  %-9s exact key-set %5.1f%%    gold keys all recalled %5.1f%%"
          % (tag, 100.0 * exact / len(kept), 100.0 * partial / len(kept)))

print("\n" + "=" * 74)
print("PER-ENTITY routing recall / precision  (NN-1)")
print("=" * 74)
tp = Counter(); fp = Counter(); fn = Counter()
for r, ns in enumerate(nbr):
    gold = frozenset(x for x, v in rows[kept[r]][1].items() if v)
    pred = ikeys[ns[0]]
    for e in gold | pred:
        if e in gold and e in pred: tp[e] += 1
        elif e in pred: fp[e] += 1
        else: fn[e] += 1
print("%-22s %8s %10s %10s" % ("entity", "support", "recall", "precision"))
for e in sorted(tp | fn, key=lambda x: -(tp[x] + fn[x])):
    sup = tp[e] + fn[e]
    rec = 100.0 * tp[e] / sup if sup else 0
    pre = 100.0 * tp[e] / (tp[e] + fp[e]) if (tp[e] + fp[e]) else 0
    print("%-22s %8s %9.1f%% %9.1f%%" % (e, f"{sup:,}", rec, pre))

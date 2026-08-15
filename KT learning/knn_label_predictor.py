# -*- coding: utf-8 -*-
"""
Can the 68k predict entity labels at RUN TIME, well enough to correct an LLM?

Experiments 1 and 2 (knn_feasibility*.py) showed retrieval cannot ANSWER.
This asks a different question: can retrieval act as a second opinion that
repairs the LLM's output?

Three predictors, all built from the training corpus only, no LLM:

  A. KEY predictor    - which entity types are present
                        similarity-weighted soft vote, threshold swept per entity
  B. VALUE predictor  - which exact values, for closed-vocabulary entities
  C. PHRASE memory    - query n-gram -> entity value, mined by co-occurrence
                        (a gazetteer learned from the corpus)

What matters is not F1. It is the shape of the precision/recall curve:
  - a HIGH-PRECISION operating point lets us ADD what the LLM missed
  - a HIGH-RECALL operating point lets us FLAG what the LLM invented

    python knn_label_predictor.py
"""
import ast
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SEED, TEST_FRAC, K = 42, 0.10, 25

CLOSED = ["FEATURE", "POLYMER", "FILLER", "PROCESSING", "DELIVERY_FORM",
          "INDUSTRY", "REGION", "BRAND", "CHEMICAL_RESISTANCE", "MEDICAL_CERT"]

# ------------------------------------------------------------------ load
df = pd.read_excel(os.path.join(ROOT, "Development files",
                                "Training_Data_14_07_2026.xlsx"))
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
print("index %s / held-out %s" % (f"{len(index_i):,}", f"{len(kept):,}"))


def keys_of(o):
    return {k for k, v in o.items() if v}


def vals_of(o, e):
    """Comparable string values for entity e."""
    out = set()
    for item in (o.get(e) or []):
        if isinstance(item, str):
            out.add(item.lower().strip())
        elif isinstance(item, dict):
            for k in ("filler_name",):
                for x in (item.get(k) or []):
                    out.add(str(x).lower().strip())
            for k in ("chemical_sub_category", "chemical_category"):
                if item.get(k):
                    out.add(str(item[k]).lower().strip())
    return out


# ------------------------------------------------------------- retrieve
print("vectorising + searching top-%d..." % K)
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
X = vec.fit_transform(index_q)
Q = vec.transform([rows[i][0] for i in kept])
nn = NearestNeighbors(n_neighbors=K, metric="cosine", algorithm="brute").fit(X)
dist, nbr = nn.kneighbors(Q)
sim = 1.0 - dist

ikeys = [keys_of(rows[i][1]) for i in index_i]
ivals = {e: [vals_of(rows[i][1], e) for i in index_i] for e in CLOSED}

# ---------------------------------------------------- A. KEY predictor
print("\n" + "=" * 78)
print("A. KEY PREDICTOR - similarity-weighted soft vote over top-%d" % K)
print("=" * 78)

scores = defaultdict(list)     # entity -> [(score, is_gold)]
for r in range(len(kept)):
    w = sim[r]
    tot = w.sum() or 1e-9
    acc = Counter()
    for j, wj in zip(nbr[r], w):
        for e in ikeys[j]:
            acc[e] += wj
    gold = keys_of(rows[kept[r]][1])
    for e in set(acc) | gold:
        scores[e].append((acc.get(e, 0.0) / tot, e in gold))


def pr_at(pairs, t):
    tp = sum(1 for s, g in pairs if s >= t and g)
    fp = sum(1 for s, g in pairs if s >= t and not g)
    fn = sum(1 for s, g in pairs if s < t and g)
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * rc / (p + rc) if p + rc else 0.0
    return p, rc, f


GRID = [round(x, 2) for x in np.arange(0.05, 1.0, 0.05)]
print("%-20s %7s | %-22s | %-22s | %s" %
      ("entity", "support", "best F1 (t)", "t for precision>=0.95", "t for recall>=0.95"))
print("-" * 110)
oper = {}
for e in sorted(scores, key=lambda x: -sum(1 for _, g in scores[x] if g)):
    pairs = scores[e]
    sup = sum(1 for _, g in pairs if g)
    if sup < 20:
        continue
    best = max(((pr_at(pairs, t), t) for t in GRID), key=lambda z: z[0][2])
    (bp, br, bf), bt = best
    hi = next(((t, pr_at(pairs, t)) for t in GRID if pr_at(pairs, t)[0] >= .95
               and pr_at(pairs, t)[1] > 0), None)
    lo = next(((t, pr_at(pairs, t)) for t in reversed(GRID) if pr_at(pairs, t)[1] >= .95), None)
    oper[e] = (bt, hi[0] if hi else None, lo[0] if lo else None)
    print("%-20s %7s | F1 %.2f  P %.2f R %.2f @%.2f | %-22s | %s"
          % (e, f"{sup:,}", bf, bp, br, bt,
             ("t=%.2f -> R %.2f" % (hi[0], hi[1][1])) if hi else "unreachable",
             ("t=%.2f -> P %.2f" % (lo[0], lo[1][0])) if lo else "unreachable"))

# -------------------------------------------------- B. VALUE predictor
print("\n" + "=" * 78)
print("B. VALUE PREDICTOR - exact values for closed-vocabulary entities")
print("=" * 78)
print("%-22s %8s %8s %8s %8s   %s" % ("entity", "support", "P@best", "R@best", "F1", "t"))
print("-" * 78)
for e in CLOSED:
    pairs = []
    for r in range(len(kept)):
        w = sim[r]
        tot = w.sum() or 1e-9
        acc = Counter()
        for j, wj in zip(nbr[r], w):
            for v in ivals[e][j]:
                acc[v] += wj
        gold = vals_of(rows[kept[r]][1], e)
        for v in set(acc) | gold:
            pairs.append((acc.get(v, 0.0) / tot, v in gold))
    sup = sum(1 for _, g in pairs if g)
    if sup < 20:
        continue
    (p, rc, f), t = max(((pr_at(pairs, t), t) for t in GRID), key=lambda z: z[0][2])
    print("%-22s %8s %7.1f%% %7.1f%% %7.1f%%   %.2f"
          % (e, f"{sup:,}", 100 * p, 100 * rc, 100 * f, t))

# --------------------------------------------------- C. PHRASE memory
print("\n" + "=" * 78)
print("C. PHRASE MEMORY - query n-gram -> entity value, mined from the corpus")
print("=" * 78)

GRAM = defaultdict(Counter)
QCNT = Counter()


def grams(q):
    w = re.findall(r"[a-z0-9][a-z0-9\-/\.]*", q)
    out = set()
    for n in (1, 2, 3):
        for i in range(len(w) - n + 1):
            out.add(" ".join(w[i:i + n]))
    return out


for i in index_i:
    q, o = rows[i]
    gs = grams(q)
    for g in gs:
        QCNT[g] += 1
    for e in CLOSED:
        for v in vals_of(o, e):
            for g in gs:
                GRAM[g][(e, v)] += 1

RULES = {}
for g, c in GRAM.items():
    if QCNT[g] < 4:
        continue
    (ev, n) = c.most_common(1)[0]
    conf = n / QCNT[g]
    if conf >= 0.85 and n >= 4:
        RULES[g] = (ev, conf, n)
print("mined %s high-confidence phrase rules (support>=4, confidence>=0.85)"
      % f"{len(RULES):,}")

# how do those rules do on held-out?
tp = fp = fn = 0
fired = Counter()
for i in kept:
    q, o = rows[i]
    pred = set()
    for g in grams(q):
        if g in RULES:
            pred.add(RULES[g][0])
            fired[RULES[g][0][0]] += 1
    gold = {(e, v) for e in CLOSED for v in vals_of(o, e)}
    tp += len(pred & gold); fp += len(pred - gold); fn += len(gold - pred)
P = tp / (tp + fp) if tp + fp else 0
R = tp / (tp + fn) if tp + fn else 0
print("held-out:  precision %.1f%%   recall %.1f%%   (tp %s / fp %s / fn %s)"
      % (100 * P, 100 * R, f"{tp:,}", f"{fp:,}", f"{fn:,}"))

print("\nexample mined rules (surface form -> canonical label):")
shown = 0
for g, (ev, conf, n) in sorted(RULES.items(), key=lambda kv: -kv[1][2]):
    if " " in g and ev[1] not in g:          # the interesting ones: not literal copies
        print("   %-32s -> %-20s %-28s conf %.2f  n=%d"
              % ("'" + g + "'", ev[0], ev[1][:28], conf, n))
        shown += 1
        if shown >= 18:
            break

out = {g: {"entity": ev[0], "value": ev[1], "confidence": round(c, 3), "support": n}
       for g, (ev, c, n) in RULES.items()}
with open(os.path.join(HERE, "mined_phrase_rules.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print("\nwrote mined_phrase_rules.json (%s rules)" % f"{len(out):,}")

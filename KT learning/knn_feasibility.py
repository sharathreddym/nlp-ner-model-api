# -*- coding: utf-8 -*-
"""
Does retrieval-instead-of-fine-tuning actually work on OUR data?

Held-out experiment over Training_Data_14_07_2026.xlsx. No LLM, no API key -
this measures the *ceiling* that a retrieval+ICL system could reach, and the
*floor* that pure copying already reaches.

  python knn_feasibility.py

Reports, on a 10% held-out slice with exact-duplicate leakage removed:
  1. COPY floor  - nearest neighbour's answer used verbatim
  2. ROUTE       - does NN-1 at least get the right entity *keys*
  3. ORACLE@k    - is the true answer present anywhere in the top-k neighbours
                   (= the ceiling for a k-shot prompt, since the LLM can only
                    pick from what retrieval showed it)
  4. VALUE cover - do the gold entity values exist anywhere in the index at all
"""
import ast
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "Development files", "Training_Data_14_07_2026.xlsx")
K = 16
TEST_FRAC = 0.10
SEED = 42


def norm(o):
    """Canonical comparable form of one Output dict."""
    return json.dumps({k: v for k, v in sorted(o.items()) if v},
                      sort_keys=True, default=str)


def keyset(o):
    return frozenset(k for k, v in o.items() if v)


def values_of(o):
    """Flatten to comparable atoms so we can ask 'does this value exist in the index'."""
    out = set()
    for k, v in o.items():
        if not v:
            continue
        for item in (v if isinstance(v, list) else [v]):
            if isinstance(item, str):
                out.add((k, item))
            elif isinstance(item, dict):
                if "property_name" in item:
                    out.add((k, item["property_name"]))
                for sub in ("filler_name",):
                    if sub in item:
                        for x in (item[sub] or []):
                            out.add((k, x))
    return out


print("loading", os.path.basename(SRC))
df = pd.read_excel(SRC)
df = df[df["Query"].notna()].reset_index(drop=True)
rows = []
for q, o in zip(df["Query"].astype(str), df["Output"]):
    try:
        rows.append((q.strip().lower(), ast.literal_eval(o) if isinstance(o, str) else o))
    except Exception:
        pass
print("  %s usable rows" % f"{len(rows):,}")

rnd = random.Random(SEED)
idx = list(range(len(rows)))
rnd.shuffle(idx)
n_test = int(len(idx) * TEST_FRAC)
test_i, index_i = idx[:n_test], idx[n_test:]

index_q = [rows[i][0] for i in index_i]
index_o = [rows[i][1] for i in index_i]
index_qset = set(index_q)

# Honesty: drop held-out queries that appear verbatim in the index. Those would
# score 100% by memorisation and tell us nothing about generalisation.
kept = [i for i in test_i if rows[i][0] not in index_qset]
print("  index %s / held-out %s (%s dropped as exact duplicates of an index row)"
      % (f"{len(index_i):,}", f"{len(kept):,}", f"{n_test - len(kept):,}"))

print("\nvectorising (char 2-5 grams - built for grade codes like 'pa66gf30')...")
t0 = time.time()
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2,
                      sublinear_tf=True)
X = vec.fit_transform(index_q)
Q = vec.transform([rows[i][0] for i in kept])
print("  %d features, %.1fs" % (X.shape[1], time.time() - t0))

print("searching top-%d..." % K)
t0 = time.time()
nn = NearestNeighbors(n_neighbors=K, metric="cosine", algorithm="brute")
nn.fit(X)
dist, nbr = nn.kneighbors(Q)
print("  %.1fs  (%.1f ms/query)" % (time.time() - t0, 1000 * (time.time() - t0) / len(kept)))

# --------------------------------------------------------------- scoring
index_norm = [norm(o) for o in index_o]
index_keys = [keyset(o) for o in index_o]
index_values = set()
for o in index_o:
    index_values |= values_of(o)

copy_hit = route_hit = 0
oracle = Counter()
val_full = val_part = val_none = 0
per_arity = defaultdict(lambda: [0, 0])
by_dist = defaultdict(lambda: [0, 0])

for row, (ns, ds) in enumerate(zip(nbr, dist)):
    gold = rows[kept[row]][1]
    gnorm, gkeys, gvals = norm(gold), keyset(gold), values_of(gold)
    arity = len(gkeys)

    if index_norm[ns[0]] == gnorm:
        copy_hit += 1
        per_arity[arity][0] += 1
    per_arity[arity][1] += 1

    if index_keys[ns[0]] == gkeys:
        route_hit += 1

    for k in (1, 2, 4, 8, 16):
        if any(index_norm[j] == gnorm for j in ns[:k]):
            oracle[k] += 1

    if gvals:
        have = sum(1 for v in gvals if v in index_values)
        if have == len(gvals):
            val_full += 1
        elif have:
            val_part += 1
        else:
            val_none += 1

    bucket = "0.0-0.2" if ds[0] < .2 else "0.2-0.4" if ds[0] < .4 else \
             "0.4-0.6" if ds[0] < .6 else "0.6+"
    by_dist[bucket][1] += 1
    if index_norm[ns[0]] == gnorm:
        by_dist[bucket][0] += 1

n = len(kept)
P = lambda x: "%5.1f%%" % (100.0 * x / n)

print("\n" + "=" * 66)
print("RESULTS  -  %s held-out queries, index of %s" % (f"{n:,}", f"{len(index_i):,}"))
print("=" * 66)
print("\n1. COPY floor      nearest neighbour's answer used verbatim")
print("   exact match          %s" % P(copy_hit))
print("\n2. ROUTE           NN-1 gets the right entity KEYS (values may differ)")
print("   key-set match        %s" % P(route_hit))
print("\n3. ORACLE@k        gold answer present somewhere in top-k")
print("                   = the CEILING for a k-shot prompt")
for k in (1, 2, 4, 8, 16):
    print("   k=%-3d                %s" % (k, P(oracle[k])))
print("\n4. VALUE coverage  do the gold entity values exist in the index at all?")
d = val_full + val_part + val_none
if d:
    print("   all values present  %5.1f%%" % (100.0 * val_full / d))
    print("   some present        %5.1f%%" % (100.0 * val_part / d))
    print("   none present        %5.1f%%   <- unreachable by any retrieval" % (100.0 * val_none / d))

print("\n5. COPY accuracy by number of gold entities")
for a in sorted(per_arity):
    hit, tot = per_arity[a]
    print("   %d entit%-3s %6s rows   %5.1f%%" % (a, "y" if a == 1 else "ies",
                                                  f"{tot:,}", 100.0 * hit / tot))

print("\n6. COPY accuracy by retrieval distance  (the confidence signal)")
for b in ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6+"]:
    hit, tot = by_dist[b]
    if tot:
        print("   dist %-8s %6s rows (%4.1f%%)   %5.1f%% correct"
              % (b, f"{tot:,}", 100.0 * tot / n, 100.0 * hit / tot))
print()

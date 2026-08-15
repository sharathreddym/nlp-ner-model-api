# -*- coding: utf-8 -*-
"""
Show, step by step, what kNN does to one query.

    python knn_demo.py "30% glass filled heat stabilized pa66"
    python knn_demo.py            # runs the built-in examples

Prints: the character n-grams -> the nearest labelled examples and why they are
near -> the soft vote -> what the reconciler would do. No LLM involved.
"""
import ast
import json
import os
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
K = 8

# precision>=0.95 add-thresholds, measured in knn_label_predictor.py
ADD = {"COMPETITOR_GRADE": .15, "RAILWAY_CERT": .20, "PROCESSING": .25,
       "AUTO_CERT": .30, "PROPERTY": .35, "APPLICATION": .35, "GRADE": .45,
       "DELIVERY_FORM": .30, "FEATURE": .50, "WATER_CERT": .65, "REGION": .40,
       "FILLER": .60, "INDUSTRY": .60, "POLYMER": .70}

print("building index (once, ~20s)...")
df = pd.read_excel(os.path.join(ROOT, "Development files", "Training_Data_14_07_2026.xlsx"))
df = df[df["Query"].notna()].reset_index(drop=True)
Q, O = [], []
for q, o in zip(df["Query"].astype(str), df["Output"]):
    try:
        O.append(ast.literal_eval(o) if isinstance(o, str) else o)
        Q.append(q.strip().lower())
    except Exception:
        pass
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
X = vec.fit_transform(Q)
nn = NearestNeighbors(n_neighbors=K, metric="cosine", algorithm="brute").fit(X)
PH = {}
p = os.path.join(HERE, "mined_phrase_rules.json")
if os.path.exists(p):
    PH = json.load(open(p, encoding="utf-8"))
print("  %s examples, %s char n-gram features, %s phrase rules\n"
      % (f"{len(Q):,}", f"{X.shape[1]:,}", f"{len(PH):,}"))


def grams(q):
    w = re.findall(r"[a-z0-9][a-z0-9\-/\.]*", q)
    return {" ".join(w[i:i + n]) for n in (1, 2, 3) for i in range(len(w) - n + 1)}


def brief(o, width=88):
    s = ", ".join("%s=%s" % (k, v) for k, v in o.items() if v)
    return s[:width] + ("…" if len(s) > width else "")


def demo(query):
    q = query.strip().lower()
    print("=" * 100)
    print("QUERY:  %r" % query)
    print("=" * 100)

    # --- 1. the query becomes a vector of character n-grams
    v = vec.transform([q])
    nz = v.nonzero()[1]
    names = vec.get_feature_names_out()
    top = sorted(((v[0, j], names[j]) for j in nz), reverse=True)[:12]
    print("\n1) QUERY -> CHARACTER N-GRAMS  (%d active of %s features)"
          % (len(nz), f"{X.shape[1]:,}"))
    print("   heaviest: " + "  ".join("%r(%.2f)" % (n, w) for w, n in top))
    print("   -> no dictionary needed; 'pa66gf30' still overlaps 'pa66 gf30'")

    # --- 2. nearest neighbours
    dist, nbr = nn.kneighbors(v)
    sims = 1 - dist[0]
    print("\n2) %d NEAREST LABELLED EXAMPLES  (cosine similarity)" % K)
    for rank, (j, s) in enumerate(zip(nbr[0], sims), 1):
        print("   %d. sim=%.3f  %r" % (rank, s, Q[j][:60]))
        print("        %s" % brief(O[j]))

    # --- 3. soft vote
    tot = sims.sum() or 1e-9
    acc = Counter()
    who = defaultdict(list)
    for j, s in zip(nbr[0], sims):
        for k_, val in O[j].items():
            if val:
                acc[k_] += s
                who[k_].append(rank_of(j, nbr[0]))
    print("\n3) SIMILARITY-WEIGHTED VOTE   score = sum(sim of neighbours having it) / sum(sim)")
    print("   %-22s %7s  %-18s %s" % ("entity", "score", "threshold", "verdict"))
    for k_, sc in sorted(acc.items(), key=lambda kv: -kv[1]):
        s = sc / tot
        t = ADD.get(k_)
        verdict = ("no add-rule (LLM only)" if t is None else
                   "ADD if LLM misses it" if s >= t else "below threshold - stay quiet")
        print("   %-22s %7.2f  %-18s %s"
              % (k_, s, ("%.2f" % t) if t else "-", verdict))

    # --- 4. phrase memory
    if PH:
        hits = [(g, PH[g]) for g in sorted(grams(q), key=len, reverse=True) if g in PH]
        print("\n4) PHRASE MEMORY  (deterministic, 95.5%% precision on held-out)")
        if not hits:
            print("   no rule fired")
        for g, r in hits[:8]:
            print("   %-26s -> %-20s %-30s conf %.2f  n=%d"
                  % ("'" + g + "'", r["entity"], r["value"][:30], r["confidence"], r["support"]))
    print()


def rank_of(j, arr):
    return list(arr).index(j) + 1


EXAMPLES = [
    "30% glass filled heat stabilized pa66",
    "micro powder for medical tubing",
    "iso 1817 resistance for fuel line",
]

if __name__ == "__main__":
    for qq in ([" ".join(sys.argv[1:])] if len(sys.argv) > 1 else EXAMPLES):
        demo(qq)

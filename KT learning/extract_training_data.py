# -*- coding: utf-8 -*-
"""
Turn NER fine-tuning JSONL (or the source Training_Data_*.xlsx) into a reviewable
set of artefacts, so the corpus can be inspected as a whole instead of scrolled.

    python extract_training_data.py                       # auto-finds the local jsonl
    python extract_training_data.py path/to/train.jsonl
    python extract_training_data.py path/to/Training_Data_27_01_25.xlsx
    python extract_training_data.py a.jsonl b.jsonl -o out/   # merge several

Emits into <out>/ (default: training-data-review/):

  corpus_profile.md      <- THE ONE TO READ. Whole-corpus digest: schema, fill
                            rates, top values per entity, PROPERTY/FILLER shapes,
                            arity + length distributions, duplicates, examples.
  training_data_flat.xlsx one row per example, one column per entity + flattened
                          PROPERTY/FILLER columns. Sortable, filterable.
  training_data_flat.csv  same, diff-friendly.
  property_rows.csv       one row per PROPERTY object (name/value/min/max/unit).
  filler_rows.csv         one row per FILLER object.
  entity_values.csv       every distinct value per entity + its frequency.
  sample_200.jsonl        stratified sample: every entity, every arity, verbatim.
  schema_report.txt       notebook-5 validators re-run over the whole file.

Companion: 13-*.md (fine-tuning), 16-entity-by-entity-resolution.md
"""
import argparse
import ast
import collections
import hashlib
import json
import os
import random
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

# Entity order as it appears in the training corpus (16-key era) plus the
# post-27_01_25 additions, so newer files profile correctly too.
KNOWN_ENTITIES = [
    "GRADE", "APPLICATION", "BRAND", "POLYMER", "PROPERTY", "FILLER", "FEATURE",
    "PROCESSING", "DELIVERY_FORM", "COMPETITOR_GRADE", "COMPETITOR_BRAND",
    "MATERIAL_ID", "AUTO_CERT", "RAILWAY_CERT", "WATER_CERT", "NSF_CERT",
    "MEDICAL_CERT", "CHEMICAL_RESISTANCE", "INDUSTRY", "REGION",
]
DICT_ENTITIES = {"PROPERTY", "FILLER"}      # list-of-dict, not list-of-str
TOP_N = 25                                  # values shown per entity in the profile


# ----------------------------------------------------------------- loading
def parse_output(raw):
    """Assistant content is a *Python* dict literal, not JSON - single quotes,
    None instead of null. That is why the service uses eval() and not
    json.loads() (ner_helper.py:1270). literal_eval is the safe equivalent."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return ast.literal_eval(raw)


def load_jsonl(path):
    """chat-format JSONL -> [(query, output_dict, system_prompt)]"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
                msgs = {m["role"]: m["content"] for m in ex["messages"]}
                rows.append((msgs.get("user", ""),
                             parse_output(msgs.get("assistant", "{}")),
                             msgs.get("system", "")))
            except Exception as e:
                print("  !! line %d unparseable: %s" % (lineno, e))
    return rows


def load_excel(path):
    """The pre-JSONL source: columns Query / Output (/ Ref No.)."""
    df = pd.read_excel(path)
    qcol = next(c for c in df.columns if c.strip().lower() == "query")
    ocol = next(c for c in df.columns if c.strip().lower() == "output")
    rows = []
    for q, o in zip(df[qcol], df[ocol]):
        try:
            rows.append((str(q), parse_output(o), ""))
        except Exception as e:
            print("  !! unparseable Output for %r: %s" % (q, e))
    return rows


def load_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".jsonl":
        return load_jsonl(path)
    if ext in (".xlsx", ".xls"):
        return load_excel(path)
    raise SystemExit("don't know how to read %s" % path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------- flatten
def clean(s):
    """Excel rejects control characters."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(s))


def entity_cell(val):
    if not val:
        return ""
    if isinstance(val, list) and val and isinstance(val[0], dict):
        return json.dumps(val, ensure_ascii=False, default=str)
    if isinstance(val, list):
        return " | ".join(str(v) for v in val)
    return str(val)


def flatten(rows, entities):
    flat, prop_rows, fill_rows = [], [], []
    for i, (q, out, _) in enumerate(rows, 1):
        populated = [k for k in out if out[k]]
        rec = {"idx": i, "query": clean(q),
               "n_chars": len(q), "n_words": len(q.split()),
               "n_entities_populated": len(populated),
               "entities_populated": ",".join(populated)}
        for e in entities:
            rec[e] = clean(entity_cell(out.get(e)))

        # PROPERTY is where nearly all the schema complexity lives - give it
        # first-class columns so it can be filtered without reading JSON.
        props = out.get("PROPERTY") or []
        rec["prop_count"] = len(props)
        if props and isinstance(props[0], dict):
            p0, m0 = props[0], (props[0].get("modifier") or {})
            rec["prop1_name"] = p0.get("property_name", "")
            rec["prop1_type"] = p0.get("property_type", "")
            rec["prop1_value"] = m0.get("value", "")
            rec["prop1_min"] = m0.get("min", "")
            rec["prop1_max"] = m0.get("max", "")
            rec["prop1_unit"] = m0.get("unit", "")
        for p in props:
            if not isinstance(p, dict):
                continue
            m = p.get("modifier") or {}
            prop_rows.append({
                "idx": i, "query": clean(q),
                "property_name": p.get("property_name", ""),
                "property_type": p.get("property_type", ""),
                "value": m.get("value"), "min": m.get("min"),
                "max": m.get("max"), "unit": m.get("unit"),
                "shape": modifier_shape(m),
            })

        fillers = out.get("FILLER") or []
        names, load = [], {}
        for f in fillers:
            if not isinstance(f, dict):
                continue
            if "filler_name" in f:
                names += f["filler_name"] or []
            if "total_load" in f:
                load = f["total_load"] or {}
        rec["filler_names"] = " | ".join(names)
        rec["filler_total_load"] = load.get("value") if load else ""
        if names or load:
            fill_rows.append({"idx": i, "query": clean(q),
                              "filler_names": " | ".join(names),
                              "load_value": load.get("value"),
                              "load_min": load.get("min"),
                              "load_max": load.get("max")})
        flat.append(rec)
    return pd.DataFrame(flat), pd.DataFrame(prop_rows), pd.DataFrame(fill_rows)


def modifier_shape(m):
    """How the numeric constraint was expressed - the thing fine-tuning teaches."""
    v, lo, hi = m.get("value"), m.get("min"), m.get("max")
    if v and lo and hi:
        return "banded (value +/- band)"
    if lo and not hi:
        return "open lower (>= min)"
    if hi and not lo:
        return "open upper (<= max)"
    if lo and hi and not v:
        return "explicit range"
    if v:
        return "exact value only"
    return "categorical / no number"


# ----------------------------------------------------------------- profile
def bar(n, total, width=28):
    filled = int(round(width * n / total)) if total else 0
    return "#" * filled + "." * (width - filled)


def dist_table(counter, title, total, limit=None):
    lines = ["| %s | count | %% | |" % title, "|---|---:|---:|---|"]
    items = counter.most_common(limit) if limit else sorted(counter.items())
    for k, n in items:
        lines.append("| `%s` | %s | %.1f%% | `%s` |"
                     % (str(k).replace("|", "\\|"), f"{n:,}", 100.0 * n / total,
                        bar(n, total)))
    return "\n".join(lines)


def build_profile(rows, entities, sources, out_dir, flat, props, fills):
    total = len(rows)
    L = []
    w = L.append

    w("# NER fine-tuning corpus profile\n")
    w("Generated by `extract_training_data.py`. This file is the whole-corpus")
    w("view - read it instead of the JSONL.\n")

    w("## 1. Source\n")
    w("| file | bytes | sha256 (first 16) | examples |")
    w("|---|---:|---|---:|")
    for p, n in sources:
        w("| `%s` | %s | `%s` | %s |"
          % (os.path.basename(p), f"{os.path.getsize(p):,}", sha256(p)[:16], f"{n:,}"))
    w("\n**Total examples: %s**\n" % f"{total:,}")

    sysmsgs = collections.Counter(s for _, _, s in rows if s)
    if sysmsgs:
        w("## 2. System prompt\n")
        w("%d distinct system message(s) across %s examples.\n"
          % (len(sysmsgs), f"{total:,}"))
        for s, n in sysmsgs.most_common(3):
            w("`%s x` :\n" % f"{n:,}")
            w("```\n%s\n```\n" % s)

    # ---- schema
    keycount = collections.Counter(len(o) for _, o, _ in rows)
    allkeys = collections.Counter()
    for _, o, _ in rows:
        allkeys.update(o.keys())
    w("## 3. Schema\n")
    w("Keys per example: %s\n"
      % ", ".join("%d keys -> %s examples" % (k, f"{v:,}")
                  for k, v in sorted(keycount.items())))
    w("Every key is emitted on every example, empty or not - that is how the")
    w("model learns the output shape.\n")
    w("Keys present: %s\n" % ", ".join("`%s`" % k for k in allkeys))

    # ---- fill rate
    w("## 4. Fill rate per entity\n")
    w("How often each entity is *populated* (non-empty).\n")
    fill = collections.Counter()
    for _, o, _ in rows:
        for k, v in o.items():
            if v:
                fill[k] += 1
    w("| entity | populated | % of corpus | |")
    w("|---|---:|---:|---|")
    for e in entities:
        n = fill.get(e, 0)
        w("| **%s** | %s | %.1f%% | `%s` |" % (e, f"{n:,}", 100.0 * n / total, bar(n, total)))
    w("")

    # ---- arity
    arity = collections.Counter(sum(1 for v in o.values() if v) for _, o, _ in rows)
    w("## 5. Entities populated per example\n")
    w(dist_table(arity, "entities", total))
    w("")

    # ---- query shape
    wl = collections.Counter(min(len(q.split()), 15) for q, _, _ in rows)
    w("## 6. Query length (words, 15+ bucketed)\n")
    w(dist_table(wl, "words", total))
    w("")

    dups = collections.Counter(q.strip().lower() for q, _, _ in rows)
    ndup = sum(n - 1 for n in dups.values() if n > 1)
    w("Distinct queries: %s of %s (%s duplicate lines).\n"
      % (f"{len(dups):,}", f"{total:,}", f"{ndup:,}"))
    if ndup:
        w("Most repeated:\n")
        for q, n in dups.most_common(5):
            w("- `%s` x %d" % (q[:80], n))
        w("")

    # ---- values per entity
    w("## 7. Values per entity\n")
    w("Top %d by frequency. Full list in `entity_values.csv`.\n" % TOP_N)
    valcsv = []
    for e in entities:
        if e in DICT_ENTITIES:
            continue
        c = collections.Counter()
        for _, o, _ in rows:
            for v in (o.get(e) or []):
                if isinstance(v, str):
                    c[v] += 1
        if not c:
            continue
        for v, n in c.items():
            valcsv.append({"entity": e, "value": v, "count": n})
        w("### %s - %s distinct values, %s mentions\n"
          % (e, f"{len(c):,}", f"{sum(c.values()):,}"))
        w("| value | count |")
        w("|---|---:|")
        for v, n in c.most_common(TOP_N):
            w("| `%s` | %s |" % (str(v).replace("|", "\\|")[:70], f"{n:,}"))
        w("")

    # ---- PROPERTY deep dive
    if len(props):
        w("## 8. PROPERTY - the complex entity\n")
        w("%s PROPERTY objects across %s examples.\n"
          % (f"{len(props):,}", f"{props['idx'].nunique():,}"))
        w("### 8.1 property_type\n")
        w(dist_table(collections.Counter(props["property_type"]), "property_type", len(props)))
        w("\n### 8.2 modifier shape - how the number was expressed\n")
        w(dist_table(collections.Counter(props["shape"]), "shape", len(props)))
        w("\n### 8.3 Top %d property_name\n" % TOP_N)
        w(dist_table(collections.Counter(props["property_name"]), "property_name",
                     len(props), TOP_N))
        w("\n### 8.4 Top %d units\n" % TOP_N)
        w(dist_table(collections.Counter(str(u) for u in props["unit"]), "unit",
                     len(props), TOP_N))
        w("")

    if len(fills):
        w("## 9. FILLER\n")
        c = collections.Counter()
        for s in fills["filler_names"]:
            for n in str(s).split(" | "):
                if n.strip():
                    c[n.strip()] += 1
        w("%s examples carry a FILLER; %s carry a total_load.\n"
          % (f"{len(fills):,}", f"{fills['load_value'].notna().sum():,}"))
        w(dist_table(c, "filler_name", sum(c.values()), TOP_N))
        w("")

    # ---- worked examples
    w("## 10. Full examples, verbatim\n")
    rnd = random.Random(42)
    picks = []
    by_arity = collections.defaultdict(list)
    for i, (q, o, _) in enumerate(rows):
        by_arity[sum(1 for v in o.values() if v)].append(i)
    for a in sorted(by_arity):
        picks += rnd.sample(by_arity[a], min(2, len(by_arity[a])))
    for i in picks[:14]:
        q, o, _ = rows[i]
        w("**%d entit%s** - `%s`\n" % (sum(1 for v in o.values() if v),
                                       "y" if sum(1 for v in o.values() if v) == 1 else "ies",
                                       q))
        w("```python")
        w(json.dumps({k: v for k, v in o.items() if v}, indent=1,
                     ensure_ascii=False, default=str) if any(o.values())
          else "{ all %d keys empty }" % len(o))
        w("```\n")

    with open(os.path.join(out_dir, "corpus_profile.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    pd.DataFrame(valcsv).sort_values(["entity", "count"], ascending=[True, False]) \
        .to_csv(os.path.join(out_dir, "entity_values.csv"), index=False,
                encoding="utf-8-sig")


# ----------------------------------------------------------------- validate
def validate(rows, out_dir, entities):
    """Notebook 5's validators, re-run over the whole corpus."""
    errs = collections.Counter()
    detail = []
    for i, (q, o, _) in enumerate(rows, 1):
        for e in o:
            if e not in entities:
                errs["unknown_key:%s" % e] += 1
        for p in (o.get("PROPERTY") or []):
            if not isinstance(p, dict):
                errs["PROPERTY not dict"] += 1; detail.append((i, q, "PROPERTY not dict")); continue
            for k in ("property_name", "modifier", "property_type"):
                if k not in p:
                    errs["PROPERTY missing %s" % k] += 1; detail.append((i, q, "missing " + k))
            m = p.get("modifier")
            if not isinstance(m, dict):
                errs["modifier not dict"] += 1
            else:
                for k in ("value", "min", "max", "unit"):
                    if k not in m:
                        errs["modifier missing %s" % k] += 1
        for fl in (o.get("FILLER") or []):
            if not isinstance(fl, dict):
                errs["FILLER not dict"] += 1; continue
            if "filler_name" in fl and not isinstance(fl["filler_name"], list):
                errs["filler_name not list"] += 1
            if "total_load" in fl:
                tl = fl["total_load"]
                if not isinstance(tl, dict):
                    errs["total_load not dict"] += 1
                else:
                    for k in ("value", "min", "max"):
                        if k not in tl:
                            errs["total_load missing %s" % k] += 1
        for e in entities:
            v = o.get(e)
            if isinstance(v, list) and e not in DICT_ENTITIES:
                if any(x == "" for x in v):
                    errs["empty string in %s" % e] += 1
                    detail.append((i, q, "empty string in " + e))

    with open(os.path.join(out_dir, "schema_report.txt"), "w", encoding="utf-8") as f:
        f.write("Examples checked: %s\n\n" % f"{len(rows):,}")
        if not errs:
            f.write("No schema errors found.\n")
        else:
            for k, n in errs.most_common():
                f.write("%-40s %s\n" % (k, f"{n:,}"))
            f.write("\nFirst 50 offending rows:\n")
            for i, q, msg in detail[:50]:
                f.write("  #%-7d %-60s %s\n" % (i, q[:60], msg))
    return errs


def stratified_sample(rows, entities, out_dir, target=200):
    """Every entity represented, every arity represented, verbatim JSONL."""
    rnd = random.Random(42)
    chosen, by_ent, by_arity = [], collections.defaultdict(list), collections.defaultdict(list)
    for i, (_, o, _) in enumerate(rows):
        by_arity[sum(1 for v in o.values() if v)].append(i)
        for e in entities:
            if o.get(e):
                by_ent[e].append(i)
    per = max(1, target // max(1, len(by_ent) + len(by_arity)))
    for pool in list(by_ent.values()) + list(by_arity.values()):
        chosen += rnd.sample(pool, min(per, len(pool)))
    chosen = sorted(set(chosen))[:target]
    with open(os.path.join(out_dir, "sample_%d.jsonl" % target), "w", encoding="utf-8") as f:
        for i in chosen:
            q, o, s = rows[i]
            f.write(json.dumps({"messages": [
                {"role": "system", "content": s},
                {"role": "user", "content": q},
                {"role": "assistant", "content": str(o)}]}, ensure_ascii=False) + "\n")
    return len(chosen)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", help=".jsonl or .xlsx (several = merged)")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "training-data-review"))
    args = ap.parse_args()

    inputs = args.inputs or [os.path.join(
        HERE, "..", "Development files", "NER_Training", "Data", "temp",
        "validation_27_11_24.jsonl")]
    inputs = [p for p in inputs if os.path.exists(p) or print("  !! missing:", p)]
    if not inputs:
        raise SystemExit("no readable input")

    os.makedirs(args.out, exist_ok=True)
    rows, sources = [], []
    for p in inputs:
        print("reading", p)
        r = load_any(p)
        print("  %s examples" % f"{len(r):,}")
        sources.append((p, len(r)))
        rows += r

    seen = set()
    entities = [e for e in KNOWN_ENTITIES] + \
               [k for _, o, _ in rows for k in o
                if k not in KNOWN_ENTITIES and not (k in seen or seen.add(k))]
    entities = [e for e in entities if any(e in o for _, o, _ in rows)]

    print("flattening...")
    flat, props, fills = flatten(rows, entities)
    flat.to_csv(os.path.join(args.out, "training_data_flat.csv"),
                index=False, encoding="utf-8-sig")
    try:
        flat.to_excel(os.path.join(args.out, "training_data_flat.xlsx"), index=False)
    except Exception as e:
        print("  !! xlsx skipped:", e)
    if len(props):
        props.to_csv(os.path.join(args.out, "property_rows.csv"),
                     index=False, encoding="utf-8-sig")
    if len(fills):
        fills.to_csv(os.path.join(args.out, "filler_rows.csv"),
                     index=False, encoding="utf-8-sig")

    print("profiling...")
    build_profile(rows, entities, sources, args.out, flat, props, fills)
    print("validating...")
    errs = validate(rows, args.out, entities)
    n = stratified_sample(rows, entities, args.out)

    print("\nDone ->", args.out)
    print("  %s examples, %s entities, %s PROPERTY objects, %s schema issues"
          % (f"{len(rows):,}", len(entities), f"{len(props):,}", f"{sum(errs.values()):,}"))
    print("  sample_200.jsonl holds %d stratified examples" % n)
    print("\n  Read corpus_profile.md first.")


if __name__ == "__main__":
    main()

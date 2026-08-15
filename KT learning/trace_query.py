# -*- coding: utf-8 -*-
"""
Trace a search query through the NER routing logic - no endpoint, no API key, no container.

Runs the REAL pre_processing.data_preprocessing() and the fast-path predicates copied verbatim
from ner_helper.py:938-1193, and reports which route the query takes and why.

    python trace_query.py "looking for alternative to celanex 2002-2"
    python trace_query.py            # runs the 20 examples from nerflow.md

Companion: nerflow.md
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "onlinescoring"))

from pre_processing import data_preprocessing, GRADE_OFFSET_TERMS   # noqa: E402

DEP = os.path.join(ROOT, "dependencies")
UV = json.load(open(os.path.join(DEP, "unique_values_22_02_24.json"), encoding="utf-8"))
NUV = json.load(open(os.path.join(DEP, "normalized_unique_values_for_grade_mapping.json"),
                    encoding="utf-8"))

# ---- replicate score.py:get_filtered_values() (score.py:167-205) ----
_fv, _units = [], []
for _k in UV:
    for _v in UV[_k]:
        for _w in _v.split():
            if (re.search(r"\.", _w) or re.search("-", _w) or re.search("/", _w)) \
                    and _w not in ["-", "/", "."]:
                _fv.append(_w)
                if _k == "UNIT":
                    _units.append(_w)
_units += ["g/ml", "w/m.k", "kg/m^3", "g/cm^3", "kj/m^2", "grams/cm^2", "g/cc", "ohm/m",
           "kj/m^3", "kg/m3", "kn/m", "kv/mm", "g/cm3", "j/m^2", "kg/cc"]
FILTERED_VALUES = list(set(_fv + _units))
UNITS_LIST = _units

# ---- constants copied verbatim from ner_helper.py:870-889 ----
FILLER_ABB = "(cf|cd|gf|gb|gd|gx|gm|mf|md|mx|nf|af|mh|lgf|laf|lcf)"
POLYMERS = ("(pps|pehmw|pa610|pa66|tpv|pa666|tpe|tpc|pa1010|pa6t6i|pa666t|pet|ppa|pehd|lcp|abs"
            "|pa6|pom|pa612|pa6t66|pa|tpu|peuhmw|pc|pct|pbt|pa6txt)")
FLAME = "(5va|5vb|vo|v0|v1|v2|hb|hb40|hb75)"
NON_GRADE_PATTERNS = [
    f"^({POLYMERS})({FLAME})$",
    f"^({FLAME})({POLYMERS})$",
    f"^({FLAME})({FILLER_ABB}?|{FILLER_ABB}(\\d*))$",
    f"^({POLYMERS})((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))$",
    f"^((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))({POLYMERS})$",
    f"^((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))({FLAME})$",
    f"^({FLAME})({FILLER_ABB}?|{FILLER_ABB}(\\d*))({POLYMERS})$",
    f"^({POLYMERS})({FLAME})({FILLER_ABB}?|{FILLER_ABB}(\\d*))$",
    f"^({FLAME})({POLYMERS})((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))$",
    f"^({POLYMERS})((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))({FLAME})$",
    f"^((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))({FLAME})({POLYMERS})$",
    f"^((\\d+){FILLER_ABB}?|{FILLER_ABB}(\\d*))({POLYMERS})({FLAME})$",
]
IGNORE_COMMON = GRADE_OFFSET_TERMS + [
    "of", "for", "to", "looking", "i", "want", "show", "me", "an", "a", "grades", "grade",
    "search", "material", "materials", "approval", "approved", "cert", "certified",
    "certification", "certifications", "by", "need", "require", "auto", "automotive", "imds"]
BLOCK_CERT = ["alternatives", "alternative", "alternate", "similar", "offset", "replacement",
              "replace", "replacing", "in place", "inplace", "instead", "competitor",
              "competitors"]


def trace(raw):
    steps = []
    sq = raw.strip()

    # ① MATERIAL_ID - ner_helper.py:779-783
    if sq.isdigit():
        n = str(int(sq))
        steps.append(("① MATERIAL_ID :779", f"isdigit=True, int()->{n}, len={len(n)}"))
        if len(n) == 8 and n.startswith(("2", "5")):
            return "FAST-PATH MATERIAL_ID", f"8 digits starting {n[0]}", sq, n, steps
        steps.append(("", "  not 8 digits starting 2/5 -> continue"))

    # ② pre-processing - :823
    cleaned, qgm = data_preprocessing(sq, FILTERED_VALUES, UNITS_LIST, None)
    steps.append(("② data_preprocessing :823", f"cleaned={cleaned!r}"))
    steps.append(("   normalize_query", f"normalised={qgm!r}"))
    if not cleaned:
        return "EMPTY -> unidentified", "nothing survived cleaning", cleaned, qgm, steps

    # ③ FEATURE - :893
    if "FEATURE" in NUV:
        for f in NUV["FEATURE"]:
            if sq == f[0] or sq in f[1]:
                if f[0] == "pfas-free":
                    return "FAST-PATH FEATURE", "pfas-free", cleaned, qgm, steps
    else:
        steps.append(("③ FEATURE :893", "SKIPPED - NUV['FEATURE'] missing in this data copy"))

    # guards - :941-945
    g = {
        "columnstoIgnore/SubstringCheck":
            not any(qgm in s for s in NUV["columnstoIgnore"] + NUV["columnsforSubstringCheck"])
            or qgm == "ultra",
        "filler-code regex":
            not re.fullmatch(r"(\d+(?:gf|mf|gb|af)|(?:gf|mf|gb|af)\d+|gf|mf|gb|af)", qgm),
        "non_grade_patterns": not any(re.match(p, qgm) for p in NON_GRADE_PATTERNS),
        "pbt/pet doubling": not bool(re.match(r"^(pbt|pet){2}$", qgm)),
        "len > 2": len(qgm) > 2,
    }
    failed = [k for k, ok in g.items() if not ok]
    steps.append(("   guards :941-945", "all pass" if not failed else "FAILED: " + ", ".join(failed)))
    if failed:
        return "LLM (fast paths blocked)", "guard: " + ", ".join(failed), cleaned, qgm, steps

    # ④ GRADE - :951-960
    sqn = re.sub(r"\W+", "", cleaned)
    if qgm in NUV["COMPETITOR_BRAND"]:
        steps.append(("④ GRADE :951", "query is a COMPETITOR_BRAND -> grade path abandoned"))
    elif sqn in NUV["GRADE"]:
        return "FAST-PATH GRADE", "exact, cleaned+stripped (:953)", cleaned, qgm, steps
    elif qgm in NUV["GRADE"]:
        return "FAST-PATH GRADE", "exact, offset-stripped (:956)", cleaned, qgm, steps
    elif not any(s == qgm for s in NUV["columnsforSubstringCheck"]) \
            and any(qgm in s for s in NUV["GRADE"]):
        return "FAST-PATH GRADE", "partial: query is substring of a grade (:958)", cleaned, qgm, steps
    steps.append(("④ GRADE :938-1086", "no match"))

    # ⑤ COMPETITOR_GRADE - :1089-1096
    if qgm in NUV["COMPETITOR_GRADE"]:
        return "FAST-PATH COMPETITOR_GRADE", "exact (:1089)", cleaned, qgm, steps
    if qgm in NUV["COMPETITOR_BRAND"]:
        return "FAST-PATH COMPETITOR_GRADE", "competitor brand (:1091)", cleaned, qgm, steps
    if not any(s == qgm for s in NUV["columnsforSubstringCheck"]) \
            and any(qgm in s for s in NUV["COMPETITOR_GRADE"]) and qgm not in ["nsf"]:
        return "FAST-PATH COMPETITOR_GRADE", "partial (:1093)", cleaned, qgm, steps
    steps.append(("⑤ COMPETITOR_GRADE :1089", "no match"))

    # ⑥ AUTO_CERT - :1140-1154
    blocked = any(re.compile(r"\b({0})\b".format(i), re.I).search(cleaned) for i in ["tds", "sds"]) \
        or any(i in cleaned for i in BLOCK_CERT)
    if blocked:
        steps.append(("⑥ AUTO_CERT :1140", "blocked - query signals comparison, not a cert lookup"))
    else:
        qc = " ".join(x for x in cleaned.split() if x not in IGNORE_COMMON)
        qc = qc.replace(" - ", "-").replace(" + ", "+").replace(". ", ".")
        qcn = re.sub(r"\W+", "", qc)
        ok = (not any(qcn in s for s in NUV["columnstoIgnore"] + NUV["columnsforSubstringCheck"])
              and not re.fullmatch(r"(\d+gf|gf\d+|\d+mf|mf\d+|gf|mf)", qcn)
              and not any(re.match(p, qcn) for p in NON_GRADE_PATTERNS) and len(qcn) > 3)
        if ok:
            for ac in NUV["AUTO_CERT"]:
                if qcn in ac[0]:
                    return ("FAST-PATH AUTO_CERT", f"'{qcn}' in cert, oem={ac[1]} (:1151)",
                            cleaned, qgm, steps)
        steps.append(("⑥ AUTO_CERT :1140-1154", f"cert-form={qcn!r}, no match"))

    return "LLM", "no fast path matched -> get_entities() at :1263", cleaned, qgm, steps


EXAMPLES = [
    "21234567", "000000000021234567", "pfas-free", "celanex 2002-2",
    "looking for alternative to celanex 2002-2", "ultramid a3eg6", "ms50017cpn5448",
    "pa66gf30", "gf30", "zytel 101f bk009",
    "30% glass filled UV resistant nylon 66 with UL94V0", "celcon m90 eco-r",
    "600 V CTI flame retardant PBT", "tensile modulus 3 GPa pa66",
    "celstran glass fiber 40%", "polyester housing", "medical device housing pom",
    "injection moulding grade", "alternative to ultramid a3wg6 with better fuel resistance",
    "nylon grade for Chlorine gas",
]

if __name__ == "__main__":
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        route, why, cleaned, qgm, steps = trace(q)
        print("\nQUERY      : %r" % q)
        print("ROUTE      : %s" % route)
        print("REASON     : %s\n" % why)
        print("trace")
        for where, what in steps:
            print("   %-32s %s" % (where, what))
        print()
    else:
        print("%-3s %-52s %-28s %s" % ("#", "QUERY", "ROUTE", "REASON"))
        print("-" * 150)
        for i, q in enumerate(EXAMPLES, 1):
            route, why, cleaned, qgm, _ = trace(q)
            print("%-3d %-52s %-28s %s" % (i, q[:52], route, why))
        print("\n(pass a query as an argument for the full step-by-step trace)")

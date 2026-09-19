"""Runs eval/questions.yaml against the running agent and reports routing accuracy,
source hit rate, answer checks, invalid citations, and latency (RICA_PLAN.md §13).

    docker exec rica python eval/run_eval.py [--only SUBSTRING] [--delay SECONDS]
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import yaml

URL = os.environ.get("RICA_URL", "http://localhost:8000/v1/chat/completions")
NOT_FOUND = re.compile(
    r"(couldn.t|could not|can.t|cannot|didn.t|did not|don.t|do not) (find|see|locate)|no (note|record|information|mention)|not (in|found in) your notes",
    re.I,
)
TARGETS = {"routing": 0.90, "source_hit": 0.80}
LATENCY_TARGETS = {"chat": 4, "docs": 8, "web": 15}


def ask(question: str) -> dict:
    body = json.dumps({"debug": True, "messages": [{"role": "user", "content": question}]}).encode()
    req = urllib.request.Request(URL, body, {
        "Authorization": "Bearer " + os.environ["RICA_INTERNAL_KEY"], "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(Path(__file__).with_name("questions.yaml")))
    ap.add_argument("--only", help="run questions containing this text")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between questions (free-tier RPM)")
    args = ap.parse_args()

    cases = yaml.safe_load(Path(args.file).read_text())["questions"]
    if args.only:
        cases = [c for c in cases if args.only.lower() in c["question"].lower()]

    rows = []
    for case in cases:
        resp = ask(case["question"])
        answer = resp["choices"][0]["message"]["content"]
        dbg = resp["rica"]
        routes = set(dbg["routes"] or []) - {"chat"}
        expected = set(case.get("expected_routes") or []) - {"chat"}
        seen = " ".join([e["locator"] for e in dbg["evidence"]])
        sources = case.get("expected_sources")
        checks = [
            bool(NOT_FOUND.search(answer)) if pat == "NOT_FOUND" else bool(re.search(pat, answer, re.I))
            for pat in case.get("expect") or []
        ]
        rows.append({
            "q": case["question"],
            "route_ok": routes == expected,
            "routes": sorted(routes) or ["chat"],
            "expected": sorted(expected) or ["chat"],
            "source_hit": None if not sources else any(s in seen for s in sources),
            "checks_ok": all(checks) if checks else None,
            "invalid": dbg["invalid_citations"] or [],
            "tier": dbg["answer_tier"],
            "latency": dbg["latency_s"],
            "answer": answer,
        })
        r = rows[-1]
        flag = "ok " if r["route_ok"] and r["source_hit"] is not False and r["checks_ok"] is not False and not r["invalid"] else "BAD"
        print(f"{flag} {r['latency']:5.1f}s {r['tier'] or '-':12s} {'+'.join(r['routes']):9s} {r['q'][:70]}")
        if flag == "BAD":
            print(f"      expected routes {r['expected']}, source hit {r['source_hit']}, checks {r['checks_ok']}, "
                  f"invalid citations {r['invalid']}\n      answer: {answer[:200]!r}")
        time.sleep(args.delay)

    def rate(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    print("\nSummary")
    ok = True
    for key, label in [("route_ok", "routing"), ("source_hit", "source_hit"), ("checks_ok", "answer checks")]:
        value, n = rate(key)
        if value is None:
            print(f"  {label:14s} n/a")
            continue
        target = TARGETS.get(label)
        met = target is None or value >= target
        ok &= met
        print(f"  {label:14s} {value:6.1%}  (n={n}{f', target {target:.0%}' if target else ''}){'' if met else '  BELOW TARGET'}")
    invalid = sum(len(r["invalid"]) for r in rows)
    print(f"  invalid citations: {invalid}")
    ok &= invalid == 0
    for route, target in LATENCY_TARGETS.items():
        lat = [r["latency"] for r in rows if route in r["routes"] or (route == "chat" and r["routes"] == ["chat"])]
        if lat:
            p50 = statistics.median(lat)
            print(f"  p50 latency {route:5s} {p50:5.1f}s  (n={len(lat)}, target < {target}s){'' if p50 < target else '  ABOVE TARGET'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Quantitative audit of a trade list: is the edge real, or a few lucky trades?

Standard library only (Python 3.9+). Input: a CSV with one row per trade/position.

    python audit_trades.py trades.csv --pnl pnl_usd --size size_usd \
        --asset mint --entity wallet --time entry_time [--json out.json]

Columns (names configurable):
  --pnl     net PnL per trade, in quote currency (required)
  --size    capital deployed per trade (optional; enables return-per-$ and % medians)
  --asset   token/mint/symbol (optional; enables asset concentration + asset bootstrap)
  --entity  wallet/leader/strategy the trade was copied from (optional; enables the
            selection test: pick entities on the first half, trade them on the second)
  --time    entry time: ISO-8601, unix seconds, or any sortable number such as a slot
            (optional; enables the A/B time split)

Optional extras:
  --period N            length of one "day" in --time units (86400 for unix seconds or ISO
                        dates, the default; e.g. 216000 for Solana slots). Enables per-day stats.
  --daily-loss-limit X  simulate a risk rule: stop taking trades for the rest of the day once
                        the day's PnL is <= -X. Needs --time.

Prints a markdown report and a list of flags. Every number is computed from the CSV;
nothing is estimated. Exit code is 0 even when flags fire: flags are findings, not errors.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any


# --------------------------------------------------------------------------- loading


def _parse_time(v: str) -> float:
    v = v.strip()
    try:
        return float(v)
    except ValueError:
        pass
    s = v.replace("Z", "+00:00")
    return datetime.fromisoformat(s).timestamp()


def load(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        for name in (args.pnl, args.size, args.asset, args.entity, args.time):
            if name and name not in cols:
                sys.exit(f"column '{name}' not in CSV header: {cols}")
        for r in reader:
            raw = (r.get(args.pnl) or "").strip()
            if raw == "" or raw.lower() in ("null", "none", "nan"):
                skipped += 1
                continue
            t: dict[str, Any] = {"pnl": float(raw)}
            if args.size:
                s = (r.get(args.size) or "").strip()
                t["size"] = float(s) if s else None
            if args.asset:
                t["asset"] = r[args.asset]
            if args.entity:
                t["entity"] = r[args.entity]
            if args.time:
                t["time"] = _parse_time(r[args.time])
            rows.append(t)
    if skipped:
        print(f"_note: skipped {skipped} rows with empty PnL (unfilled/unknown trades)._\n")
    return rows


# --------------------------------------------------------------------------- metrics


def basic(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [t["pnl"] for t in trades]
    n = len(pnl)
    if n == 0:
        return {"n": 0}
    gains = sum(p for p in pnl if p > 0)
    losses = -sum(p for p in pnl if p < 0)
    out: dict[str, Any] = {
        "n": n,
        "total": sum(pnl),
        "mean": sum(pnl) / n,
        "median": statistics.median(pnl),
        "win_rate": sum(p > 0 for p in pnl) / n,
        "profit_factor": gains / losses if losses else math.inf,
    }
    sized = [t for t in trades if t.get("size")]
    if sized:
        deployed = sum(t["size"] for t in sized)
        out["deployed"] = deployed
        out["return_per_dollar"] = sum(t["pnl"] for t in sized) / deployed
        out["median_pct"] = statistics.median(t["pnl"] / t["size"] for t in sized)
    return out


def tail(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = sorted((t["pnl"] for t in trades), reverse=True)
    n = len(pnl)
    k1 = max(1, math.ceil(n * 0.01))
    total = sum(pnl)
    return {
        "best_trade": pnl[0] if pnl else 0.0,
        "best_trade_share": pnl[0] / total if total > 0 and pnl else None,
        "top1pct_k": k1,
        "ex_top1pct": sum(pnl[k1:]),
        "ex_top10": sum(pnl[10:]),
        "ex_best": sum(pnl[1:]),
    }


def by_asset(trades: list[dict[str, Any]]) -> dict[str, float]:
    agg: dict[str, float] = defaultdict(float)
    for t in trades:
        agg[t["asset"]] += t["pnl"]
    return dict(agg)


def asset_concentration(trades: list[dict[str, Any]]) -> dict[str, Any]:
    agg = sorted(by_asset(trades).values(), reverse=True)
    return {
        "assets": len(agg),
        "pct_assets_profitable": sum(v > 0 for v in agg) / len(agg) if agg else None,
        "ex_best_asset": sum(agg[1:]),
        "ex_best_5_assets": sum(agg[5:]),
        "ex_best_10_assets": sum(agg[10:]),
    }


def bootstrap(groups: list[float], n_boot: int, seed: int) -> dict[str, Any]:
    """Resample whole groups (assets) with replacement; returns P(total > 0) and quantiles.
    Resampling groups, not trades, keeps correlated trades (many copies of one runner)
    together, which is what makes trade-level bootstraps too optimistic."""
    rng = random.Random(seed)
    k = len(groups)
    sums = sorted(sum(rng.choices(groups, k=k)) for _ in range(n_boot))
    return {
        "n_boot": n_boot,
        "p_total_positive": sum(s > 0 for s in sums) / n_boot,
        "p5": sums[int(n_boot * 0.05)],
        "p50": sums[n_boot // 2],
        "p95": sums[int(n_boot * 0.95) - 1],
    }


def split_halves(trades: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    times = sorted(t["time"] for t in trades)
    mid = times[len(times) // 2]
    a = [t for t in trades if t["time"] < mid]
    b = [t for t in trades if t["time"] >= mid]
    return a, b, mid


def _ex_best(pnls: list[float]) -> float:
    return sum(pnls) - max(pnls) if pnls else 0.0


def _rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (vx * vy) if vx and vy else None


def selection_test(
    a: list[dict[str, Any]], b: list[dict[str, Any]], min_trades: int
) -> dict[str, Any]:
    """Pick entities on A only (>= min_trades, PnL excluding their best trade > 0), then
    compare their B results with everyone else's. This is the honest version of
    'we found profitable wallets and copying them works'."""
    pa: dict[str, list[float]] = defaultdict(list)
    pb: dict[str, list[float]] = defaultdict(list)
    for t in a:
        pa[t["entity"]].append(t["pnl"])
    for t in b:
        pb[t["entity"]].append(t)
    picked = {e for e, p in pa.items() if len(p) >= min_trades and _ex_best(p) > 0}

    def summarize(ents: set[str]) -> dict[str, Any]:
        tr = [t for e in ents for t in pb.get(e, [])]
        return {"entities": len([e for e in ents if e in pb]), **basic(tr)} if tr else {
            "entities": 0, "n": 0}

    both = [e for e in pa if e in pb and len(pa[e]) >= min_trades]
    rho = spearman(
        [_ex_best(pa[e]) for e in both], [_ex_best([t["pnl"] for t in pb[e]]) for e in both]
    )
    return {
        "min_trades_in_a": min_trades,
        "picked": summarize(picked),
        "not_picked": summarize({e for e in pb if e not in picked}),
        "spearman_a_vs_b_ex_best": rho,
        "entities_compared": len(both),
    }


def top_trades(trades: list[dict[str, Any]], k: int = 5) -> list[dict[str, Any]]:
    out = []
    for t in sorted(trades, key=lambda x: x["pnl"], reverse=True)[:k]:
        ret = t["pnl"] / t["size"] if t.get("size") else None
        out.append({"pnl": t["pnl"], "return": ret, "asset": t.get("asset"),
                    "entity": t.get("entity"), "time": t.get("time")})
    return out


def sanity(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Cheap data checks: exact duplicate rows, impossible losses, extreme winners."""
    seen: dict[tuple[Any, ...], int] = defaultdict(int)
    # Only meaningful when rows can be told apart: need at least two identifying columns.
    if trades and sum(k in trades[0] for k in ("entity", "asset", "time")) >= 2:
        for t in trades:
            seen[(t.get("entity"), t.get("asset"), t.get("time"), t["pnl"])] += 1
    sized = [t for t in trades if t.get("size")]
    return {
        "duplicate_rows": sum(c - 1 for c in seen.values() if c > 1),
        "loss_over_105pct": sum(1 for t in sized if t["pnl"] < -1.05 * t["size"]),
        "return_over_10000pct": sum(1 for t in sized if t["pnl"] > 100 * t["size"]),
    }


def entity_luck(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """How many entities are profitable at all, and without their single best trade."""
    per: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        per[t["entity"]].append(t["pnl"])
    totals = sorted((sum(v) for v in per.values()), reverse=True)
    return {
        "entities": len(per),
        "positive": sum(sum(v) > 0 for v in per.values()),
        "positive_ex_best": sum(_ex_best(v) > 0 for v in per.values()),
        "total_ex_top5_entities": sum(totals[5:]),
    }


def clones(trades: list[dict[str, Any]], min_entries: int = 10, share: float = 0.7) -> list[Any]:
    """Entity pairs that enter the same asset at the same time on >= `share` of the smaller
    one's trades: probably one operator, so their trades are one bet counted twice."""
    sets: dict[str, set[tuple[Any, Any]]] = defaultdict(set)
    for t in trades:
        sets[t["entity"]].add((t["asset"], t["time"]))
    ents = [e for e, s in sets.items() if len(s) >= min_entries]
    out = []
    for i, a in enumerate(ents):
        for b in ents[i + 1:]:
            inter = len(sets[a] & sets[b])
            frac = inter / min(len(sets[a]), len(sets[b]))
            if frac >= share:
                out.append({"a": a, "b": b, "shared_entries": inter, "share": frac})
    return sorted(out, key=lambda x: -x["share"])


def cost_sensitivity(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Total PnL if every round trip cost an extra x% of size; and the break-even x."""
    sized = [t for t in trades if t.get("size")]
    deployed = sum(t["size"] for t in sized)
    total = sum(t["pnl"] for t in sized)
    return {
        "break_even_extra_cost": total / deployed if deployed else None,
        "extra": {str(x): total - deployed * x / 100 for x in (1, 3, 5)},
    }


def sequence(trades: list[dict[str, Any]], period: float, loss_limit: float | None) -> dict[str, Any]:
    """Path statistics in entry order. PnL is booked at entry time (exit times are usually not
    in a trade log), so drawdown and the loss-limit simulation are approximations."""
    tr = sorted(trades, key=lambda x: x["time"])
    t0 = tr[0]["time"]  # days are counted from the first trade
    eq = peak = dd = 0.0
    streak = longest = 0
    days: dict[int, float] = defaultdict(float)
    for t in tr:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        streak = streak + 1 if t["pnl"] <= 0 else 0
        longest = max(longest, streak)
        days[int((t["time"] - t0) // period)] += t["pnl"]
    out: dict[str, Any] = {
        "max_drawdown": dd,
        "longest_losing_streak": longest,
        "days": len(days),
        "days_positive": sum(v > 0 for v in days.values()),
        "median_day": statistics.median(days.values()),
    }
    if loss_limit is not None:
        day_pnl: dict[int, float] = defaultdict(float)
        halted: set[int] = set()
        taken, total = 0, 0.0
        top = {id(t) for t in sorted(tr, key=lambda x: x["pnl"], reverse=True)[
            : max(1, math.ceil(len(tr) * 0.01))]}
        top_caught = 0
        for t in tr:
            d = int((t["time"] - t0) // period)
            if d in halted:
                continue
            taken += 1
            total += t["pnl"]
            top_caught += id(t) in top
            day_pnl[d] += t["pnl"]
            if day_pnl[d] <= -loss_limit:
                halted.add(d)
        out["loss_limit"] = {
            "limit": loss_limit, "trades_taken": taken, "total": total,
            "days_halted": len(halted), "top1pct_caught": top_caught, "top1pct_n": len(top),
        }
    return out


def first_entry_per_asset(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Total if only the first entry into each asset is taken (one position per token)."""
    first: dict[str, dict[str, Any]] = {}
    for t in sorted(trades, key=lambda x: x.get("time", 0)):
        first.setdefault(t["asset"], t)
    return {"trades": len(first), "total": sum(t["pnl"] for t in first.values()),
            "rows_in_multi_entry_assets": len(trades) - len(first)}



# --------------------------------------------------------------------------- report


def fmt(v: Any, spec: str = ",.2f") -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    return format(v, spec)


def pct(v: Any) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def build(trades: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    res: dict[str, Any] = {"overall": basic(trades), "tail": tail(trades)}
    res["sanity"] = sanity(trades)
    res["top_trades"] = top_trades(trades)
    if any(t.get("size") for t in trades):
        res["costs"] = cost_sensitivity(trades)
    if args.entity:
        res["entity_luck"] = entity_luck(trades)
    if args.asset:
        res["first_entry"] = first_entry_per_asset(trades)
    if args.entity and args.asset and args.time:
        res["clones"] = clones(trades)
    if args.time:
        res["sequence"] = sequence(trades, args.period, args.daily_loss_limit)
    if args.asset:
        res["assets"] = asset_concentration(trades)
        res["bootstrap"] = bootstrap(list(by_asset(trades).values()), args.boot, args.seed)
        res["bootstrap"]["unit"] = "asset"
    elif args.entity:
        agg: dict[str, float] = defaultdict(float)
        for t in trades:
            agg[t["entity"]] += t["pnl"]
        res["bootstrap"] = bootstrap(list(agg.values()), args.boot, args.seed)
        res["bootstrap"]["unit"] = "entity"
    if args.time:
        a, b, mid = split_halves(trades)
        res["split"] = {
            "mid": mid,
            "A": {**basic(a), **{"ex_top1pct": tail(a)["ex_top1pct"]}},
            "B": {**basic(b), **{"ex_top1pct": tail(b)["ex_top1pct"]}},
        }
        if args.entity:
            res["selection"] = selection_test(a, b, args.min_entity_trades)
    res["flags"] = flags(res)
    return res


def flags(res: dict[str, Any]) -> list[str]:
    out = []
    o, t = res["overall"], res["tail"]
    if o.get("n", 0) < 100:
        out.append(f"SMALL SAMPLE: n={o.get('n')}; below ~100 trades almost any result is noise.")
    if o.get("total", 0) > 0 and t["ex_top1pct"] <= 0:
        out.append(
            f"TAIL-DEPENDENT: total {fmt(o['total'])} turns {fmt(t['ex_top1pct'])} without the"
            f" top 1% of trades ({t['top1pct_k']} trades)."
        )
    if t.get("best_trade_share") and t["best_trade_share"] > 0.5:
        out.append(f"ONE TRADE: the best trade is {pct(t['best_trade_share'])} of total PnL.")
    a = res.get("assets")
    if a and o.get("total", 0) > 0 and a["ex_best_5_assets"] <= 0:
        out.append(
            f"FEW-ASSET DEPENDENT: without the best 5 of {a['assets']} assets the total is"
            f" {fmt(a['ex_best_5_assets'])}."
        )
    bs = res.get("bootstrap")
    if bs and bs["p_total_positive"] < 0.95:
        out.append(
            f"NOT ROBUST: {bs['unit']}-level bootstrap P(total > 0) = {bs['p_total_positive']:.3f}"
            f" (p5 {fmt(bs['p5'])}, p95 {fmt(bs['p95'])})."
        )
    if o.get("median_pct") is not None and o["median_pct"] < 0 and o.get("total", 0) > 0:
        out.append(
            f"LOTTERY PROFILE: median trade {pct(o['median_pct'])} while the total is positive;"
            " check drawdown and whether risk limits would halt trading before winners arrive."
        )
    sn = res.get("sanity", {})
    if sn.get("return_over_10000pct"):
        out.append(
            f"SUSPECT TRADES: {sn['return_over_10000pct']} trade(s) above +10,000%. Treat as a"
            " data error (wrong pool, decimals) until checked on a block explorer."
        )
    if sn.get("duplicate_rows"):
        out.append(f"DUPLICATES: {sn['duplicate_rows']} exact duplicate rows.")
    if sn.get("loss_over_105pct"):
        out.append(f"IMPOSSIBLE LOSSES: {sn['loss_over_105pct']} trade(s) lose more than 105% of their size.")
    el = res.get("entity_luck")
    if el and el["positive_ex_best"] < el["entities"] / 2 and o.get("total", 0) > 0:
        out.append(
            f"ENTITY LUCK: {el['positive']} of {el['entities']} entities are positive, only"
            f" {el['positive_ex_best']} without their single best trade."
        )
    if res.get("clones"):
        out.append(
            f"CLONED ENTITIES: {len(res['clones'])} entity pair(s) share >= 70% of their entries;"
            " they are probably one operator, so the sample is smaller than it looks."
        )
    fe = res.get("first_entry")
    if fe and o.get("total", 0) > 0 and fe["total"] <= 0:
        out.append(
            f"STACKED ENTRIES: taking only the first entry per asset gives {fmt(fe['total'])}"
            f" ({fe['trades']} trades); the profit comes from repeat entries into the same assets."
        )
    cs = res.get("costs")
    if cs and cs["break_even_extra_cost"] is not None and 0 < cs["break_even_extra_cost"] < 0.03:
        out.append(
            f"THIN MARGIN: an extra {pct(cs['break_even_extra_cost'])} of round-trip cost"
            " (latency slip, failed sends, worse fills) erases the profit."
        )
    sq = res.get("sequence", {})
    ll = sq.get("loss_limit")
    if ll and o.get("total", 0) > 0 and ll["total"] < o["total"] * 0.5:
        out.append(
            f"RISK LIMIT KILLS IT: with a {fmt(ll['limit'])} daily loss limit the total is"
            f" {fmt(ll['total'])} ({ll['days_halted']} of {sq['days']} days halted,"
            f" {ll['top1pct_caught']} of {ll['top1pct_n']} top trades caught)."
        )
    s = res.get("split")
    if s:
        ta, tb = s["A"].get("total", 0), s["B"].get("total", 0)
        if (ta > 0) != (tb > 0):
            out.append(f"UNSTABLE: first half {fmt(ta)} vs second half {fmt(tb)}.")
        if s["A"].get("ex_top1pct", 0) <= 0 and s["B"].get("ex_top1pct", 0) <= 0 and o.get(
            "total", 0) > 0:
            out.append("TAIL-DEPENDENT IN BOTH HALVES: each half is negative without its top 1%.")
    sel = res.get("selection")
    if sel:
        p, q = sel["picked"], sel["not_picked"]
        if p.get("n", 0) == 0:
            out.append("SELECTION: no entity qualifies on the first half; nothing to test.")
        else:
            if p.get("n", 0) < 100 or p.get("entities", 0) < 5:
                out.append(
                    f"SELECTION TOO SMALL TO JUDGE: {p.get('entities')} entities picked on the first"
                    f" half, {p.get('n')} trades on the second; a positive result here is weak"
                    " evidence either way."
                )
            if p.get("total", 0) <= 0:
                out.append(
                    f"SELECTION FAILS OUT OF SAMPLE: entities picked on the first half made"
                    f" {fmt(p['total'])} on the second (n={p['n']})."
                )
            if q.get("n", 0) and p.get("mean", 0) < q.get("mean", 0):
                out.append(
                    "SELECTION NO BETTER THAN RANDOM: picked entities averaged"
                    f" {fmt(p['mean'])}/trade vs {fmt(q['mean'])} for the rest on the second half."
                )
        rho = sel.get("spearman_a_vs_b_ex_best")
        if rho is not None and rho < 0.3:
            out.append(
                f"NO PERSISTENCE: rank correlation of entity results between halves = {rho:.2f}"
                f" ({sel['entities_compared']} entities)."
            )
    return out


def markdown(res: dict[str, Any]) -> str:
    o, t = res["overall"], res["tail"]
    L = ["# Trade audit", "", "## Overall", ""]
    L.append(f"- trades: {o.get('n')}")
    L.append(f"- total PnL: {fmt(o.get('total'))}; mean {fmt(o.get('mean'))}; median"
             f" {fmt(o.get('median'))}")
    if "deployed" in o:
        L.append(f"- deployed: {fmt(o['deployed'])}; return per $ deployed:"
                 f" {pct(o['return_per_dollar'])}; median trade {pct(o['median_pct'])}")
    L.append(f"- win rate {pct(o.get('win_rate'))}; profit factor {fmt(o.get('profit_factor'))}")
    L += ["", "## Tail dependence", ""]
    L.append(f"- best trade {fmt(t['best_trade'])} ({pct(t['best_trade_share'])} of total)")
    L.append(f"- without best trade: {fmt(t['ex_best'])}; without top 10: {fmt(t['ex_top10'])};"
             f" without top 1% ({t['top1pct_k']} trades): {fmt(t['ex_top1pct'])}")
    if res.get("top_trades"):
        L += ["", "| top trades | PnL | return | asset | entity |", "|---|---|---|---|---|"]
        for i, x in enumerate(res["top_trades"], 1):
            L.append(f"| {i} | {fmt(x['pnl'])} | {pct(x['return'])} | {x.get('asset') or ''} |"
                     f" {x.get('entity') or ''} |")
    sn = res["sanity"]
    L += ["", "## Data sanity", "",
          f"- duplicate rows: {sn['duplicate_rows']}; losses over 105% of size: {sn['loss_over_105pct']};"
          f" trades above +10,000%: {sn['return_over_10000pct']}"]
    a = res.get("assets")
    if a:
        L += ["", "## Asset concentration", ""]
        L.append(f"- assets: {a['assets']}; profitable: {pct(a['pct_assets_profitable'])}")
        L.append(f"- without best asset: {fmt(a['ex_best_asset'])}; best 5:"
                 f" {fmt(a['ex_best_5_assets'])}; best 10: {fmt(a['ex_best_10_assets'])}")
    fe = res.get("first_entry")
    if fe:
        L.append(f"- first entry per asset only: {fmt(fe['total'])} on {fe['trades']} trades"
                 f" ({fe['rows_in_multi_entry_assets']} rows are repeat entries)")
    el = res.get("entity_luck")
    if el:
        L += ["", "## Entities", "",
              f"- {el['positive']} of {el['entities']} positive; {el['positive_ex_best']} positive"
              f" without their best trade; total without the top 5 entities:"
              f" {fmt(el['total_ex_top5_entities'])}"]
        for c in (res.get("clones") or [])[:10]:
            L.append(f"- possible same operator: {c['a']} / {c['b']} share {pct(c['share'])} of"
                     f" entries ({c['shared_entries']})")
    cs = res.get("costs")
    if cs:
        L += ["", "## Cost sensitivity (extra cost per round trip, % of size)", "",
              f"- break-even extra cost: {pct(cs['break_even_extra_cost'])}",
              "- total at +1% / +3% / +5%: " + " / ".join(fmt(cs["extra"][k]) for k in ("1", "3", "5"))]
    sq = res.get("sequence")
    if sq:
        L += ["", "## Path (entry order; PnL booked at entry, so approximate)", "",
              f"- max drawdown {fmt(sq['max_drawdown'])}; longest losing streak"
              f" {sq['longest_losing_streak']} trades",
              f"- days: {sq['days_positive']} of {sq['days']} positive; median day"
              f" {fmt(sq['median_day'])}"]
        ll = sq.get("loss_limit")
        if ll:
            L.append(f"- with a {fmt(ll['limit'])} daily loss limit: {ll['trades_taken']} trades,"
                     f" total {fmt(ll['total'])}, {ll['days_halted']} days halted,"
                     f" {ll['top1pct_caught']} of {ll['top1pct_n']} top-1% trades caught")
    bs = res.get("bootstrap")
    if bs:
        L += ["", f"## Bootstrap ({bs['unit']}-level, {bs['n_boot']} resamples)", ""]
        L.append(f"- P(total > 0) = {bs['p_total_positive']:.3f}; p5 {fmt(bs['p5'])}, median"
                 f" {fmt(bs['p50'])}, p95 {fmt(bs['p95'])}")
    s = res.get("split")
    if s:
        L += ["", "## Time split at the median entry (A = first half, B = second)", "",
              "| half | n | total | return/$ | median trade | win rate | total ex top 1% |",
              "|---|---|---|---|---|---|---|"]
        for h in ("A", "B"):
            x = s[h]
            L.append(f"| {h} | {x.get('n')} | {fmt(x.get('total'))} |"
                     f" {pct(x.get('return_per_dollar'))} | {pct(x.get('median_pct'))} |"
                     f" {pct(x.get('win_rate'))} | {fmt(x.get('ex_top1pct'))} |")
    sel = res.get("selection")
    if sel:
        L += ["", "## Selection test (pick entities on A, trade them on B)", "",
              f"Picked = >= {sel['min_trades_in_a']} trades in A and PnL excluding their best"
              " trade > 0 in A.", "",
              "| group | entities | trades in B | total B | mean/trade B | return/$ B |",
              "|---|---|---|---|---|---|"]
        for name in ("picked", "not_picked"):
            x = sel[name]
            L.append(f"| {name.replace('_', ' ')} | {x.get('entities')} | {x.get('n')} |"
                     f" {fmt(x.get('total'))} | {fmt(x.get('mean'))} |"
                     f" {pct(x.get('return_per_dollar'))} |")
        rho = sel["spearman_a_vs_b_ex_best"]
        L.append("")
        L.append(f"Rank correlation (A vs B, PnL ex-best per entity, {sel['entities_compared']}"
                 f" entities): {fmt(rho, '.2f')}")
    L += ["", "## Flags", ""]
    L += [f"- {f}" for f in res["flags"]] or ["- none fired"]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--pnl", required=True)
    ap.add_argument("--size")
    ap.add_argument("--asset")
    ap.add_argument("--entity")
    ap.add_argument("--time")
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--min-entity-trades", type=int, default=10)
    ap.add_argument("--period", type=float, default=86400.0,
                    help="length of one day in --time units (default 86400; Solana slots: 216000)")
    ap.add_argument("--daily-loss-limit", type=float,
                    help="simulate halting for the rest of the day at this loss")
    ap.add_argument("--json", help="also write the full result as JSON")
    args = ap.parse_args()
    trades = load(args)
    if not trades:
        sys.exit("no trades with a PnL value")
    res = build(trades, args)
    print(markdown(res))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, default=str)


if __name__ == "__main__":
    main()

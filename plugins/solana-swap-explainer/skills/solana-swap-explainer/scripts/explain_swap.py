"""Explain a Solana swap from its transaction JSON: what was really paid, to whom, and why.

Standard library only (Python 3.9+). Works offline on a saved transaction:

    python explain_swap.py tx.json [--wallet ADDRESS] [--json out.json]

Input: the JSON of one transaction as returned by the RPC method getTransaction with
encoding "jsonParsed" (the bare transaction object, or the whole RPC reply with "result").
Use fetch_tx.py next to this file to download one, or save it from any RPC or explorer.

Fully modeled venues:
  - pump.fun bonding curve: decoded from the TradeEvent the program logs on every trade
    (post-trade virtual reserves and the fee rates this token actually charges).
  - PumpSwap (pump.fun AMM): from the pool's two vault balances before and after.
Any other venue still gets the wallet's net SOL and token changes and the cost breakdown;
the pool math is skipped and the report says so.

All amounts are computed from integers in the transaction. Nothing is estimated except where
the report says "assumed" (token supply) or "likely" (rent for new accounts).
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
from datetime import datetime, timezone
from typing import Any

PUMPFUN = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
OTHER_VENUES = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "Raydium LaunchLab",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora DAMM v1",
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "Meteora DAMM v2",
    "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "Meteora DBC",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6 (router)",
}

LAMPORTS = 1_000_000_000
BASE_FEE_PER_SIGNATURE = 5000
PUMP_STANDARD_SUPPLY = 1_000_000_000  # tokens; pump.fun mints 1B with 6 decimals

# pump.fun TradeEvent: 8-byte discriminator, then this layout (little-endian). Verified on
# mainnet transactions; newer program versions append fields after these, which are ignored.
TRADE_EVENT_DISC = bytes.fromhex("bddb7fd34ee661ee")
TRADE_EVENT = struct.Struct("<32sQQ?32sqQQQQ32sQQ32sQQ")
LOG_PREFIX = "Program data: "

# PumpSwap logs one event per swap. Only its fee fields are used: they sit at the same offsets in
# both event kinds and matched the measured fills on mainnet transactions. The amount fields
# differ between event versions, so amounts always come from the vault balances instead.
POOL_EVENT_DISCS = (bytes.fromhex("67f4521f2cf57777"), bytes.fromhex("3e2f370aa503dc2a"))
POOL_EVENT_HEAD = struct.Struct("<14Q")  # ..., [8] lp bps, [9] lp fee, [10] protocol bps, [11] fee
POOL_EVENT_PUBKEYS = 7  # then creator fee bps and creator fee, when present
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


# --------------------------------------------------------------------------- reading the tx


def load_tx(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
    if not isinstance(data, dict) or "meta" not in data or "transaction" not in data:
        sys.exit("not a getTransaction result: expected an object with 'transaction' and 'meta'")
    if data["meta"] is None:
        sys.exit("transaction has no meta (too old for this RPC, or not found)")
    return data


def account_keys(tx: dict[str, Any]) -> list[str]:
    keys = tx["transaction"]["message"]["accountKeys"]
    out = [k["pubkey"] if isinstance(k, dict) else k for k in keys]
    if keys and not isinstance(keys[0], dict):  # "json" encoding: lookup-table keys come apart
        loaded = tx["meta"].get("loadedAddresses") or {}
        out += list(loaded.get("writable") or []) + list(loaded.get("readonly") or [])
    return out


def signer_keys(tx: dict[str, Any]) -> list[str]:
    msg = tx["transaction"]["message"]
    keys = msg["accountKeys"]
    if keys and isinstance(keys[0], dict):
        return [k["pubkey"] for k in keys if k.get("signer")]
    n = (msg.get("header") or {}).get("numRequiredSignatures", 1)
    return list(keys[:n])


def token_balances(tx: dict[str, Any], when: str) -> dict[int, dict[str, Any]]:
    out = {}
    for b in tx["meta"].get(f"{when}TokenBalances") or []:
        out[b["accountIndex"]] = {
            "mint": b["mint"],
            "owner": b.get("owner"),
            "amount": int(b["uiTokenAmount"]["amount"]),
            "decimals": int(b["uiTokenAmount"]["decimals"]),
        }
    return out


def wallet_changes(tx: dict[str, Any], wallet: str) -> dict[str, Any]:
    """Net change for the wallet: native SOL, wrapped SOL it owns, and each other token."""
    keys = account_keys(tx)
    meta = tx["meta"]
    idx = keys.index(wallet) if wallet in keys else None
    lamports = (meta["postBalances"][idx] - meta["preBalances"][idx]) if idx is not None else 0
    pre, post = token_balances(tx, "pre"), token_balances(tx, "post")
    wsol = 0
    tokens: dict[str, int] = {}
    decimals: dict[str, int] = {}
    new_accounts = 0
    for i in sorted(pre.keys() | post.keys()):
        b = post.get(i) or pre[i]
        if b["owner"] != wallet:
            continue
        delta = (post[i]["amount"] if i in post else 0) - (pre[i]["amount"] if i in pre else 0)
        if b["mint"] == WSOL:
            wsol += delta
            continue
        tokens[b["mint"]] = tokens.get(b["mint"], 0) + delta
        decimals[b["mint"]] = b["decimals"]
        if i not in pre and i in post:
            new_accounts += 1
    return {
        "lamports": lamports,
        "wsol": wsol,
        "sol_total": lamports + wsol,
        "tokens": {m: d for m, d in tokens.items() if d != 0},
        "decimals": decimals,
        "new_token_accounts": new_accounts,
    }


def trade_events(tx: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for line in tx["meta"].get("logMessages") or []:
        if not line.startswith(LOG_PREFIX):
            continue
        try:
            raw = base64.b64decode(line[len(LOG_PREFIX):])
        except ValueError:
            continue
        if not raw.startswith(TRADE_EVENT_DISC) or len(raw) < 8 + TRADE_EVENT.size:
            continue
        (mint, sol, tok, is_buy, user, ts, vsol, vtok, rsol, rtok, recipient, fee_bps, fee,
         _creator, creator_bps, creator_fee) = TRADE_EVENT.unpack_from(raw, 8)
        out.append({
            "mint": b58encode(mint), "user": b58encode(user), "is_buy": bool(is_buy),
            "sol_amount": sol, "token_amount": tok, "timestamp": ts,
            "virtual_sol_after": vsol, "virtual_token_after": vtok,
            "real_sol_after": rsol, "real_token_after": rtok,
            "fee_bps": fee_bps, "fee": fee, "creator_fee_bps": creator_bps,
            "creator_fee": creator_fee, "fee_recipient": b58encode(recipient),
        })
    return out


def pool_event_fees(tx: dict[str, Any]) -> list[dict[str, int]]:
    """Fee rates each PumpSwap swap in this transaction declared in its event."""
    out = []
    for line in tx["meta"].get("logMessages") or []:
        if not line.startswith(LOG_PREFIX):
            continue
        try:
            raw = base64.b64decode(line[len(LOG_PREFIX):])
        except ValueError:
            continue
        if raw[:8] not in POOL_EVENT_DISCS or len(raw) < 8 + POOL_EVENT_HEAD.size:
            continue
        head = POOL_EVENT_HEAD.unpack_from(raw, 8)
        fees = {"lp_bps": head[8], "protocol_bps": head[10], "creator_bps": 0}
        tail = 8 + POOL_EVENT_HEAD.size + 32 * POOL_EVENT_PUBKEYS
        if len(raw) >= tail + 16:
            fees["creator_bps"] = struct.unpack_from("<Q", raw, tail)[0]
        if all(v <= 10_000 for v in fees.values()):  # ignore anything that is not a rate
            fees["total_bps"] = sum(fees.values())
            out.append(fees)
    return out


def money_flows(tx: dict[str, Any], wallet: str, mint: str, pool: str | None,
                events: list[dict[str, Any]]) -> dict[str, Any]:
    """Who gained SOL and who gained the token in this transaction, apart from the wallet.
    This itemises the cost lines: the pool or curve, fee accounts, tips, rent."""
    keys = account_keys(tx)
    meta = tx["meta"]
    pre, post = token_balances(tx, "pre"), token_balances(tx, "post")
    recipients = {e["fee_recipient"]: "pump.fun protocol fee" for e in events}
    curve_amounts = {e["sol_amount"]: "pump.fun bonding curve" for e in events}
    creator_amounts = {e["creator_fee"]: "pump.fun creator fee" for e in events if e["creator_fee"]}
    sol_rows, rent = [], 0
    for i, key in enumerate(keys):
        gain = meta["postBalances"][i] - meta["preBalances"][i]
        if gain <= 0 or key == wallet:
            continue
        tb = post.get(i) or pre.get(i)
        if tb and tb["owner"] == wallet:
            if i not in pre:  # a token account opened for the wallet: its balance is the rent
                rent += meta["postBalances"][i]
                sol_rows.append({"to": key, "lamports": gain,
                                 "what": "rent for the wallet's new token account (refundable)"})
            continue
        if tb and tb["mint"] == WSOL:
            what = "PumpSwap pool" if tb["owner"] == pool else (
                f"wrapped-SOL account owned by {tb['owner']} (fee or route)")
        elif key in recipients:
            what = recipients[key]
        elif gain in curve_amounts:
            what = curve_amounts[gain]
        elif gain in creator_amounts:
            what = creator_amounts[gain]
        else:
            what = "other account (tip, bot or router fee, or rent)"
        sol_rows.append({"to": key, "lamports": gain, "what": what})
    token_rows = []
    by_owner: dict[str, int] = {}
    for i in pre.keys() | post.keys():
        b = post.get(i) or pre[i]
        if b["mint"] != mint or b["owner"] in (wallet, None):
            continue
        delta = (post[i]["amount"] if i in post else 0) - (pre[i]["amount"] if i in pre else 0)
        by_owner[b["owner"]] = by_owner.get(b["owner"], 0) + delta
    for owner, delta in by_owner.items():
        if delta > 0:
            token_rows.append({"to": owner, "raw": delta,
                               "what": "PumpSwap pool" if owner == pool else "other account (pool, fee or router)"})
    return {
        "sol": sorted(sol_rows, key=lambda r: -r["lamports"])[:12],
        "token": sorted(token_rows, key=lambda r: -r["raw"])[:8],
        "rent_lamports": rent,
    }


def pumpswap_pools(tx: dict[str, Any], mint: str) -> list[dict[str, Any]]:
    """Every PumpSwap pool for `mint` touched here: a non-signer owner of both a `mint` and a
    wrapped-SOL token account. A mint can have several pools; they are listed deepest first."""
    signers = signer_keys(tx)
    pre, post = token_balances(tx, "pre"), token_balances(tx, "post")
    owners: dict[str, dict[str, dict[str, int]]] = {}
    for when, bal in (("pre", pre), ("post", post)):
        for b in bal.values():
            if b["owner"] is None or b["owner"] in signers or b["mint"] not in (mint, WSOL):
                continue
            side = "token" if b["mint"] == mint else "sol"
            owners.setdefault(b["owner"], {}).setdefault(when, {})[side] = b["amount"]
    pools = []
    for owner, v in owners.items():
        p, q = v.get("pre", {}), v.get("post", {})
        if all(k in p and k in q for k in ("token", "sol")) and p["token"] > 0 and p["sol"] > 0:
            pools.append({"pool": owner, "sol_before": p["sol"], "token_before": p["token"],
                          "sol_after": q["sol"], "token_after": q["token"]})
    return sorted(pools, key=lambda x: -x["sol_before"])


# --------------------------------------------------------------------------- analysis


def explain_curve(ev: dict[str, Any], decimals: int) -> dict[str, Any]:
    unit = 10 ** decimals
    sol, tok = ev["sol_amount"], ev["token_amount"]
    if ev["is_buy"]:
        vsol_b, vtok_b = ev["virtual_sol_after"] - sol, ev["virtual_token_after"] + tok
    else:
        vsol_b, vtok_b = ev["virtual_sol_after"] + sol, ev["virtual_token_after"] - tok
    spot_b = (vsol_b / LAMPORTS) / (vtok_b / unit)
    spot_a = (ev["virtual_sol_after"] / LAMPORTS) / (ev["virtual_token_after"] / unit)
    curve_price = (sol / LAMPORTS) / (tok / unit) if tok else 0.0
    fees = ev["fee"] + ev["creator_fee"]
    paid = sol + fees if ev["is_buy"] else sol - fees
    return {
        "venue": "pump.fun bonding curve",
        "side": "buy" if ev["is_buy"] else "sell",
        "trader": ev["user"],
        "token_amount_raw": tok,
        "curve_sol_lamports": sol,
        "protocol_fee_lamports": ev["fee"], "protocol_fee_bps": ev["fee_bps"],
        "creator_fee_lamports": ev["creator_fee"], "creator_fee_bps": ev["creator_fee_bps"],
        "sol_with_fees_lamports": paid,
        "reserves_before": {"virtual_sol": vsol_b, "virtual_token": vtok_b},
        "reserves_after": {"virtual_sol": ev["virtual_sol_after"],
                           "virtual_token": ev["virtual_token_after"]},
        "real_sol_in_curve_after": ev["real_sol_after"],
        "real_token_left_after": ev["real_token_after"],
        "spot_before": spot_b, "spot_after": spot_a,
        "fill_price_ex_fees": curve_price,
        "fill_price_with_fees": (paid / LAMPORTS) / (tok / unit) if tok else 0.0,
        "price_impact": (curve_price / spot_b - 1) if ev["is_buy"] else (1 - curve_price / spot_b),
        "spot_move": spot_a / spot_b - 1,
        "mcap_sol_after_assumed_1b_supply": spot_a * PUMP_STANDARD_SUPPLY,
        "curve_k": vsol_b * vtok_b,
    }


def explain_pool(pool: dict[str, Any], token_delta_wallet: int, decimals: int) -> dict[str, Any]:
    unit = 10 ** decimals
    sb, tb, sa, ta = (pool[k] for k in ("sol_before", "token_before", "sol_after", "token_after"))
    spot_b = (sb / LAMPORTS) / (tb / unit)
    spot_a = (sa / LAMPORTS) / (ta / unit)
    buy = token_delta_wallet > 0
    if buy:
        sol_in = sa - sb
        ideal = tb * sol_in // (sb + sol_in) if sol_in > 0 else 0
        got = token_delta_wallet
        eff_fee = 1 - got / ideal if ideal else None
        impact = sol_in / (sb + sol_in) if sol_in > 0 else 0.0
        fill = (sol_in / LAMPORTS) / (got / unit) if got else 0.0
        sol_side = sol_in
    else:
        tok_in = -token_delta_wallet
        ideal = sb * tok_in // (tb + tok_in) if tok_in > 0 else 0
        got = sb - sa
        eff_fee = 1 - got / ideal if ideal else None
        impact = tok_in / (tb + tok_in) if tok_in > 0 else 0.0
        fill = (got / LAMPORTS) / (tok_in / unit) if tok_in else 0.0
        sol_side = got
    return {
        "venue": "PumpSwap pool",
        "side": "buy" if buy else "sell",
        "pool": pool["pool"],
        "token_amount_raw": abs(token_delta_wallet),
        "pool_sol_lamports": sol_side,
        "reserves_before": {"sol": sb, "token": tb},
        "reserves_after": {"sol": sa, "token": ta},
        "spot_before": spot_b, "spot_after": spot_a,
        "fill_price": fill,
        "price_impact": impact,
        "effective_fee": eff_fee,
        "spot_move": spot_a / spot_b - 1,
    }


def costs(tx: dict[str, Any], ch: dict[str, Any], swap_sol: int | None, side: str,
          rent: int) -> dict[str, Any]:
    fee = tx["meta"]["fee"]
    base = BASE_FEE_PER_SIGNATURE * len(tx["transaction"]["signatures"])
    out: dict[str, Any] = {
        "network_fee_lamports": fee,
        "base_fee_lamports": min(base, fee),
        "priority_fee_lamports": max(fee - base, 0),
        "wallet_sol_change_lamports": ch["sol_total"],
        "new_token_accounts": ch["new_token_accounts"],
        "rent_lamports": rent,
    }
    if swap_sol is not None:
        # Whatever the wallet paid or failed to receive beyond the swap itself and the network
        # fee: tips, trading-bot or aggregator fees, rent for new accounts.
        if side == "buy":
            other = -ch["sol_total"] - fee - swap_sol
        else:
            other = swap_sol - fee - ch["sol_total"]
        out["other_costs_lamports"] = other
        out["other_costs_ex_rent_lamports"] = other - rent
    return out


def analyse(tx: dict[str, Any], wallet: str | None) -> dict[str, Any]:
    signers = signer_keys(tx)
    wallet = wallet or signers[0]
    keys = account_keys(tx)
    ch = wallet_changes(tx, wallet)
    events = trade_events(tx)
    venues = [name for pid, name in OTHER_VENUES.items() if pid in keys]
    if PUMPFUN in keys:
        venues.insert(0, "pump.fun")
    if PUMPSWAP in keys:
        venues.insert(0, "PumpSwap")
    res: dict[str, Any] = {
        "signature": tx["transaction"]["signatures"][0],
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "succeeded": tx["meta"].get("err") is None,
        "wallet": wallet,
        "signers": signers,
        "programs_seen": venues,
        "wallet_changes": ch,
        "swaps": [],
        "notes": [],
    }
    if wallet not in keys:
        res["notes"].append("The wallet given is not an account in this transaction.")
    for mint, delta in ch["tokens"].items():
        dec = ch["decimals"][mint]
        side = "buy" if delta > 0 else "sell"
        swap: dict[str, Any] = {"mint": mint, "decimals": dec, "side": side,
                                "wallet_token_change_raw": delta}
        mine = [e for e in events if e["mint"] == mint]
        own = [e for e in mine if e["user"] == wallet] or mine
        pools = pumpswap_pools(tx, mint) if PUMPSWAP in keys else []
        swap_sol: int | None = None
        if own:
            swap["curve_trades"] = [explain_curve(e, dec) for e in own]
            swap_sol = sum(c["sol_with_fees_lamports"] * (1 if c["side"] == side else -1)
                           for c in swap["curve_trades"])
            if len(mine) > len(own):
                res["notes"].append(f"{len(mine) - len(own)} other curve trade(s) on {mint} in "
                                    "this transaction belong to a different trader.")
        if pools:
            swap["pool_trade"] = explain_pool(pools[0], delta, dec)
            swap_sol = (swap_sol or 0) + swap["pool_trade"]["pool_sol_lamports"]
            if len(pools) > 1:
                swap["other_pools"] = pools[1:]
                res["notes"].append(f"{len(pools)} PumpSwap pools for {mint} appear here; the "
                                    "deepest one by SOL is explained.")
        if not own and not pools:
            res["notes"].append(f"{mint}: venue not modeled; only the wallet's net amounts and "
                                "costs are reported.")
        pool_addr = pools[0]["pool"] if pools else None
        flows = money_flows(tx, wallet, mint, pool_addr, own)
        swap["flows"] = flows
        if pools:
            declared = pool_event_fees(tx)
            if declared:
                swap["pool_trade"]["declared_fees"] = declared
                pt = swap["pool_trade"]
                cut = sum(x["raw"] for x in flows["token"] if x["to"] != pool_addr) / abs(delta)
                known = declared[0]["total_bps"] / 10_000 + (cut if side == "buy" else 0.0)
                if pt["effective_fee"] is not None and pt["effective_fee"] > known + 0.001:
                    res["notes"].append(
                        "Part of the shortfall is not explained by the declared pool fees and the "
                        "token-side transfers. Some PumpSwap pools price with virtual SOL reserves "
                        "on top of the vault balance, which makes the true pool price higher than "
                        "the vault ratio shown here.")
        swap["costs"] = costs(tx, ch, swap_sol if len(ch["tokens"]) == 1 else None, side,
                              flows["rent_lamports"])
        spot = None
        if own:
            spot = swap["curve_trades"][0]["spot_before"]
        elif pools:
            spot = swap["pool_trade"]["spot_before"]
        if spot and len(ch["tokens"]) == 1 and delta:
            per_token = (abs(ch["sol_total"]) / LAMPORTS) / (abs(delta) / 10 ** dec)
            swap["all_in_price"] = per_token
            swap["all_in_vs_spot_before"] = (per_token / spot - 1) if side == "buy" else (
                1 - per_token / spot)
        res["swaps"].append(swap)
    if not ch["tokens"]:
        res["notes"].append("The wallet's token balances did not change: not a swap for this "
                            "wallet (try --wallet with another signer or account).")
    if len(ch["tokens"]) > 1:
        res["notes"].append("Several tokens changed for this wallet, so SOL costs cannot be "
                            "assigned to one of them; per-token cost lines are omitted.")
    return res


# --------------------------------------------------------------------------- report


def sol(lamports: int | float | None) -> str:
    return "n/a" if lamports is None else f"{lamports / LAMPORTS:,.9f} SOL"


def pct(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f}%"


def price(v: float) -> str:
    return f"{v:.12f} SOL per token"


def tokens(raw: int, decimals: int) -> str:
    return f"{raw / 10 ** decimals:,.{min(decimals, 6)}f}"


def markdown(r: dict[str, Any]) -> str:
    when = (datetime.fromtimestamp(r["block_time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if r.get("block_time") else "unknown time")
    L = [f"# Swap explained: {r['signature']}", "",
         f"- slot {r['slot']}, {when}, {'succeeded' if r['succeeded'] else 'FAILED'}",
         f"- wallet: {r['wallet']}",
         f"- programs referenced: {', '.join(r['programs_seen']) or 'none recognised'}"]
    ch = r["wallet_changes"]
    L.append(f"- wallet SOL change: {sol(ch['sol_total'])} (native {sol(ch['lamports'])},"
             f" wrapped {sol(ch['wsol'])})")
    for s in r["swaps"]:
        dec = s["decimals"]
        L += ["", f"## {s['side'].upper()} {tokens(abs(s['wallet_token_change_raw']), dec)} of"
                  f" {s['mint']}"]
        for c in s.get("curve_trades", []):
            L += ["", "### pump.fun bonding curve", "",
                  f"- curve amount: {sol(c['curve_sol_lamports'])} for"
                  f" {tokens(c['token_amount_raw'], dec)} tokens ({c['side']} by {c['trader']})",
                  f"- protocol fee: {sol(c['protocol_fee_lamports'])} ({c['protocol_fee_bps']} bps);"
                  f" creator fee: {sol(c['creator_fee_lamports'])} ({c['creator_fee_bps']} bps)",
                  f"- {'paid' if c['side'] == 'buy' else 'received'} including fees:"
                  f" {sol(c['sol_with_fees_lamports'])}",
                  f"- spot before: {price(c['spot_before'])}; after: {price(c['spot_after'])}"
                  f" ({pct(c['spot_move'])})",
                  f"- fill price: {price(c['fill_price_ex_fees'])} before fees,"
                  f" {price(c['fill_price_with_fees'])} with fees",
                  f"- price impact of this trade: {pct(c['price_impact'])}",
                  f"- virtual reserves before: {sol(c['reserves_before']['virtual_sol'])} /"
                  f" {tokens(c['reserves_before']['virtual_token'], dec)} tokens",
                  f"- real SOL in the curve after: {sol(c['real_sol_in_curve_after'])}; tokens left"
                  f" to sell on the curve: {tokens(c['real_token_left_after'], dec)}",
                  f"- market cap after, assumed 1B supply:"
                  f" {c['mcap_sol_after_assumed_1b_supply']:,.2f} SOL"]
        p = s.get("pool_trade")
        if p:
            L += ["", "### PumpSwap pool", "",
                  f"- pool: {p['pool']}",
                  f"- SOL {'into' if p['side'] == 'buy' else 'out of'} the pool:"
                  f" {sol(p['pool_sol_lamports'])}",
                  f"- reserves before: {sol(p['reserves_before']['sol'])} /"
                  f" {tokens(p['reserves_before']['token'], dec)} tokens",
                  f"- spot before: {price(p['spot_before'])}; after: {price(p['spot_after'])}"
                  f" ({pct(p['spot_move'], 4)})",
                  f"- fill price: {price(p['fill_price'])}",
                  f"- price impact of this trade: {pct(p['price_impact'], 4)}",
                  f"- shortfall vs a no-fee constant-product fill: {pct(p['effective_fee'], 3)}"
                  " (pool fees, plus any router or referral cut taken on the token side)"]
            for d in p.get("declared_fees", []):
                L.append(f"- fee rates declared by the pool's event: LP {d['lp_bps']} bps, protocol"
                         f" {d['protocol_bps']} bps, creator {d['creator_bps']} bps"
                         f" (total {d['total_bps'] / 100:.2f}%)")
            for o in s.get("other_pools", []):
                L.append(f"- another pool in this transaction: {o['pool']} with"
                         f" {sol(o['sol_before'])}")
        c2 = s["costs"]
        L += ["", "### Costs", "",
              f"- network fee: {sol(c2['network_fee_lamports'])} (base"
              f" {sol(c2['base_fee_lamports'])}, priority {sol(c2['priority_fee_lamports'])})"]
        if c2["rent_lamports"]:
            L.append(f"- rent for {c2['new_token_accounts']} new token account(s):"
                     f" {sol(c2['rent_lamports'])} (comes back when the account is closed)")
        if "other_costs_lamports" in c2:
            L.append(f"- other costs beyond the swap, network fee and rent (tips, bot or router"
                     f" fees): {sol(c2['other_costs_ex_rent_lamports'])}")
        if "all_in_price" in s:
            word = "above" if s["side"] == "buy" else "below"
            L.append(f"- all-in: {price(s['all_in_price'])}, {pct(s['all_in_vs_spot_before'])}"
                     f" {word} the spot price before the trade")
        fl = s.get("flows") or {}
        if fl.get("sol"):
            L += ["", "### Who received SOL in this transaction", ""]
            L += [f"- {sol(x['lamports'])} to {x['to']}: {x['what']}" for x in fl["sol"]]
        if fl.get("token"):
            L += ["", "### Who received the token, apart from the wallet", ""]
            base = abs(s["wallet_token_change_raw"]) or 1
            L += [f"- {tokens(x['raw'], dec)} to {x['to']}: {x['what']}"
                  f" ({x['raw'] / base * 100:.3f}% of the wallet's amount)" for x in fl["token"]]
    if r["notes"]:
        L += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Explain a Solana swap from its transaction JSON.")
    ap.add_argument("tx_json", help="file with a getTransaction (jsonParsed) result")
    ap.add_argument("--wallet", help="whose point of view to report (default: the fee payer)")
    ap.add_argument("--json", help="also write the full result as JSON to this path")
    args = ap.parse_args()
    result = analyse(load_tx(args.tx_json), args.wallet)
    sys.stdout.reconfigure(encoding="utf-8")
    print(markdown(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()

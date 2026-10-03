---
name: crypto-backtest-audit
description: Audits crypto trading backtests, copy-trading results and "this wallet is printing" claims for the statistical traps that make losing strategies look profitable — look-ahead wallet selection, survivorship in hit rates, PnL that depends on a handful of trades or tokens, fills priced at the leader's price instead of after latency, missing fees/priority fees/price impact, and bad pool/price data. Runs a bundled script on a trade CSV (tail exclusion, asset-level bootstrap, first-half/second-half split, pick-on-A-trade-on-B selection test) and returns a verdict with evidence. Use this whenever someone shares a crypto or memecoin backtest, strategy results, a trade log, a PnL screenshot or leaderboard, a smart-money / copy-trading / sniper / KOL wallet list, or asks "is this edge real", "should I copy this wallet", "why does my bot lose live when the backtest was great", or wants a strategy reviewed before going live — even if they don't say "audit".
---

# Crypto backtest audit

Most crypto backtests that look profitable are not. The failure is rarely the strategy code; it's the evidence. A handful of 100× tokens, a wallet list chosen with hindsight, or fills at prices nobody could have gotten will turn a losing system into a beautiful equity curve. This skill finds those problems and says plainly whether an edge survives them.

The traps here come from a real project: copy-trading Solana memecoin wallets. A full-window backtest showed +10% per dollar deployed. After the checks below, nothing survived out of sample. `references/case-study.md` walks through it with numbers. It's the best way to see what each check catches.

## Workflow

### 1. Get the evidence, not the summary

An audit of a summary ("68% win rate, +340% in 30 days") can only list what's missing. Ask for or locate:
- **Trade-level data**: one row per trade or position with net PnL. Size, asset (token/mint/symbol), entity (the wallet or leader copied) and entry time each unlock more checks.
- **How the trades were generated**: backtest code, the selection rule for wallets/tokens, the fill model, the cost model, and the dates the strategy was designed on vs. evaluated on.

If only a summary or screenshot exists, do step 3 qualitatively and make the missing evidence the main finding. Missing evidence is not a neutral result. Say what can't be verified and why it matters.

### 2. Run the quantitative checks (when there's a trade list)

```bash
python <skill-dir>/scripts/audit_trades.py trades.csv --pnl <col> \
    [--size <col>] [--asset <col>] [--entity <col>] [--time <col>] \
    [--period <day length in time units>] [--daily-loss-limit <amount>] [--json out.json]
```

Standard library only; no install needed. Pass every optional column that exists, since each one enables checks:

| option | enables |
|---|---|
| `--size` | return per dollar deployed, median trade %, cost sensitivity (extra round-trip cost that erases the profit), trades above +10,000% |
| `--asset` | asset concentration, asset-level bootstrap, "first entry per asset only" total |
| `--entity` | per-entity luck check (how many stay positive without their best trade) |
| `--time` | first/second-half split, max drawdown, losing streak, per-day stats. Accepts ISO dates, unix seconds, or block/slot numbers |
| `--entity` + `--time` | selection test: pick wallets on the first half, trade them on the second |
| `--entity` + `--asset` + `--time` | cloned-entity detection (wallets making the same entries are one operator) |
| `--period` | length of a "day" in `--time` units. Default 86400 (seconds). Use 216000 for Solana slots |
| `--daily-loss-limit` | simulates halting for the rest of the day at that loss. Ask the user for their real limit; if they have none, try 3× the position size as an illustration and say so |

The script covers the standard checks, so don't re-implement them. Write extra code only for something specific to this data (e.g. per-hour effects, a position cap that needs exit times).

Read the output's flags, but interpret them; don't just paste them. A flag is a prompt to look, e.g. "SUSPECT TRADES" means open that trade on a block explorer or ask the user to. If the data needs reshaping first (per-fill rows into positions, PnL from entry/exit prices), do that in a small script and say what you did. If PnL is gross, note that costs are missing and estimate them (step 3, costs).

### 3. Check the traps

Go through each category. For the details, detection queries and fixes, read `references/traps.md`. Each has a short "how to detect" you can apply to code or data.

1. **Selection and look-ahead.** Were wallets, tokens or parameters chosen with data from the evaluation period? A leaderboard of last month's top wallets "backtested" on last month is circular. The fix is to select on window A and evaluate on window B.
2. **Survivorship.** Do hit rates count only tokens that still exist or only waves that happened? The denominator must be every attempt, including duds and rugs.
3. **Tail dependence.** Does the result survive removing the top 1% of trades, the best 5 assets, and the single best trade? Memecoin returns are extremely fat-tailed, so a positive total is often just one runner.
4. **Robustness.** Bootstrap by asset or entity, not by trade, because copies of one runner are correlated. Check P(total > 0) and p5. Check that both halves agree.
5. **Fill realism.** Entries at the leader's fill price, or at a candle close, can't be had. Copying takes 1–3 s or more, and at 5k–50k USD market cap the price can move 20–50% in that time. Fills should come from pool reserves at signal + latency.
6. **Costs.** Venue/LP fees (pump.fun curve ~0.95–1.25% per side, varying per token; PumpSwap ~0.25%; aggregator fees), priority fees, tips, our own price impact, and failed transactions. Many "profitable" scalps are pure fee donations.
7. **Data errors.** Several pools per token (dust pools priced 1000× off), wrong decimals or supply, wicks in thin candles, stablecoin swaps counted as trades, duplicate rows. A single impossible trade (+50,000%) is a data bug until proven otherwise.
8. **Practical tradability.** Would the risk rules (max open positions, daily loss limit) have halted trading before the runners arrived? Could the size actually be absorbed, and sold?

### 4. Verdict

Write the report in this shape. Keep it numerical; the reader should be able to check every claim against the data.

```markdown
# Backtest audit: <strategy / claim>

**Verdict:** <one of: No evidence of edge | Edge not robust | Plausible edge, needs out-of-sample test | Edge survives the checks run>
<two or three sentences: the decisive numbers and what they mean>

## What was checked
<data used: n trades, assets, entities, date range; what was missing>

## Findings
<one subsection per trap that matters, most damaging first: the number, why it matters, how to fix>

## What would change the verdict
<the specific test or data that would upgrade or overturn it, e.g. "a forward paper run of ≥ 100 trades over 2 weeks with leaders frozen today">
```

Pick the verdict from the evidence, using these rules:
- **No evidence of edge**: negative after costs, or the out-of-sample half/selection test fails.
- **Edge not robust**: positive, but it disappears without the top 1% of trades or the best few assets, or the bootstrap P(total > 0) is below ~0.95, or the halves disagree.
- **Plausible edge, needs out-of-sample test**: survives the tail and bootstrap checks, but selection or fills used in-sample information.
- **Edge survives the checks run**: survives all of the above, with realistic fills and costs. Even then, say a live paper test is the next step, not live money.

Be direct. Someone may be about to put money behind this. Saying "this doesn't hold up, and here's the number" is the useful answer. Don't hedge it into mush. Equally, don't invent problems; if a check passes, say so.

## Scope and tone

This is an analysis tool, not investment advice; say so briefly in the report if the person seems to be deciding whether to trade. Don't recommend specific tokens or wallets to buy. Auditing someone's claimed wallet performance is fine. Helping them fake or inflate a track record (wash trades, selective screenshots, sybil wallets) is not; decline that part.

## Files

- `scripts/audit_trades.py`: quantitative checks on a trade CSV.
- `references/traps.md`: each trap in detail, with detection and fixes. Read it during step 3.
- `references/case-study.md`: a worked example from a real copy-trading project, from a +10% backtest to "no edge". Read it when the user is unsure why these checks matter, or as a model for the report.

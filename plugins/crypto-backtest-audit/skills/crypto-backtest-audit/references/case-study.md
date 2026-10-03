# Case study: a Solana copy-trading backtest, from +10% to "no edge"

A real research project (September–October 2026) tried to copy profitable pump.fun / PumpSwap memecoin traders. Every number below comes from that project's data. Wallet addresses are omitted. Use this as a model of how the checks interact.

## Setup

- **Leaders:** 36 non-bot wallets with ≥ 20 closed positions over ~38 days, still profitable after removing each one's best trade (the "luck check").
- **Trades:** 5,650 leader positions entered on the pump.fun curve or PumpSwap; 4,990 could be filled at 2 s latency.
- **Fill model:** constant-product math on the pool reserves at the leader's buy + latency (1/2/3 s). Positions were 20 USD, capped so price impact stays ≤ 2%. Each trade's own pump.fun event supplied the per-token fees (95 + 30 bps or 95 + 0 bps). PumpSwap fees were measured at 25 bps. Priority fee and tip were charged per side.
- **Model validation:** predicted fills matched recorded transactions within 0.05% (PumpSwap) and 1e-7 (curve). Five fills were spot-checked against a block explorer.

## Step by step

**1. The headline (full window, exit when the leader sells).**
- 1 s latency: +12,889 USD, +12.8% per dollar deployed.
- 2 s: +10,097 USD. 3 s: +4,093 USD.

Win rate was 24–25%. This is the number that would go on a landing page.

**2. A data bug inflated it first.** The first run showed +17,144 USD at 1 s, with single trades of +53,114% and +78,853%.
- One was real: a token that went from ~23k USD to ~7.8M USD market cap while the leader held for 24 h.
- The other was a dust pool. The entry was priced from a second PumpSwap pool holding 3.4 SOL, at ~1,000× below the main pool, while the exit was priced in the main pool.

Pinning fills to the pool the leader actually traded fixed it. Lesson: check the extreme trades on a block explorer before believing them (traps §7).

**3. Tail dependence.** At 2 s:

| | PnL |
|---|---|
| total | +10,097 USD |
| without top 10 trades | −2,076 USD |
| without top 50 (1%) | −8,745 USD |
| median trade | −15.9% |

Without the best 5 of 3,051 tokens, every exit variant was negative. Only 21–26% of tokens were profitable.

**4. The leader ranking didn't persist.** Leaders were ranked by copy PnL on the first 26.9 days, then traded on the next 11.6 days:
- Correlation between the two halves: 0.01–0.12 across latencies and exit rules.
- Leaders picked in the first half did worse in the second half than those not picked, in 5 of 6 combinations. At 2 s: −4.9% vs +0.6% per trade.

**5. Letting winners run (exit-rule variants on the real price path).**

| exit rule | total | without top 1% | bootstrap P(total > 0) |
|---|---|---|---|
| leader's sell, no cap | +10,097 USD | −8,745 USD | 0.95 |
| leader's sell, 4 h cap | +5,603 USD | −7,568 USD | 0.93 |
| + 30% stop | +3,908 USD | −7,192 USD | 0.88 |
| trail 40% + 30% stop | +7,053 USD | −9,636 USD | 0.82 |
| sell half at 2×, trail rest | +1,600 USD | −7,906 USD | 0.61 |
| trail 25% + 30% stop | −839 USD | −7,007 USD | 0.33 |

The bootstrap resampled whole tokens. The leader-sell exit looked borderline (P = 0.95). But the leaders had been chosen using full-window PnL, including these very trades (look-ahead), so the full-window numbers are an upper bound.

**6. The decisive test: select on the first half only, trade the second half.**

| exit | picked leaders: return per dollar in B | others: return per dollar in B |
|---|---|---|
| leader's sell, 4 h cap | −1.9% | +17.0% |
| trail 40% | +22.2% | −2.0% |

The trail-40% result came from one token. Without it, the picked leaders' second half was −562 USD.

**7. Tradability.** With a −14% median trade at 20 USD, a 60 USD daily loss limit halts after a handful of losers. Live trading would usually be stopped before a runner arrived.

## Verdict

**No evidence of edge.** Copy-trading this leader group, at any latency or exit rule tested, earns only by catching ~0.2% of tokens that run 100×+. Neither leader selection nor exit choice predicted which ones, out of sample.

## What generalises

- A 25% win rate with a positive total is a lottery profile. Look at the median trade and at what happens without the top 1%.
- "Profitable wallets" chosen from the same window are not evidence. Select on A, trade on B.
- Fill realism moves results more than strategy tweaks: going from 1 s to 3 s cut the total by ~70%.
- Extreme trades are data bugs until a block explorer says otherwise.

# Traps in crypto backtests: detection and fixes

Contents
1. Selection and look-ahead
2. Survivorship and the wrong denominator
3. Tail dependence
4. Robustness: bootstrap and halves
5. Fill realism and latency
6. Costs
7. Data errors
8. Practical tradability
9. Quick code-review checklist

---

## 1. Selection and look-ahead

**What it is:** something used to build the strategy (the wallet list, token list, parameters, filters) was chosen with knowledge of the period it's evaluated on.

**Typical forms**
- "Top 50 wallets by 30-day PnL", backtested on those same 30 days. Their PnL is the selection criterion, so the backtest is guaranteed to look good.
- Wallets found as "early buyers of tokens that later did 100×". The future outcome picked them.
- Parameters (TP/SL, thresholds, K-of-N) tuned on the full history, then reported on the full history.
- Excluding tokens that "were obviously rugs", judged with hindsight.

**How to detect**
- Ask: on what date range was each choice made, and on what range is the result reported? Any overlap is look-ahead.
- In code: look for a selection query or filter that reads PnL, peak price or outcome columns over the same window as the evaluation.
- With data: run the selection test (`audit_trades.py --entity --time`). Pick entities on the first half only and compare their second-half results with everyone else's. Also check the rank correlation between halves. Values near 0 mean past performance didn't predict future performance.

**Fix:** walk-forward. Select on window A, evaluate on window B with no overlap, roll forward (e.g. weekly), and report only the B results. Better still, freeze the selection today and paper-trade forward.

## 2. Survivorship and the wrong denominator

**What it is:** counting only the attempts that survived or succeeded.

**Typical forms**
- A hit rate of "waves ridden / waves", instead of "waves ridden / all early entries, including duds and rugs".
- Token universes built from what's listed today (dead tokens are gone from the APIs), or from tokens that reached a market-cap milestone.
- Wallets that went to zero or stopped trading are missing from the leaderboard you sampled.

**How to detect**
- For every rate, ask "out of what?" The denominator must be decided before the outcome is known.
- Check whether the universe query has a condition on a future value: current liquidity, peak market cap, still listed.

**Fix:** define the universe at decision time (every token launched / every buy the wallet made in the window). Report the denominator next to every rate. Use a Wilson lower bound for small counts.

## 3. Tail dependence

**What it is:** a positive total produced by very few trades. Memecoin returns are extremely skewed. A strategy can lose on 75% of trades and on the median trade, and still show a profit because one token went 300×.

**How to detect**
- Total excluding the single best trade, the top 10, and the top 1%.
- By asset: total excluding the best 1, 5 and 10 assets; the share of assets that are profitable at all.
- Best trade as a share of total PnL. Above ~50% means the result is one event.

**Interpretation:** tail dependence isn't automatically fatal. Venture-style strategies are meant to work this way. But then the claim is "we will reliably catch runners", and that needs evidence that the runner rate is stable (both halves, bootstrap) and that nothing about selection used the runners themselves. Without that, a tail-driven backtest is a lottery ticket that happened to win.

## 4. Robustness: bootstrap and halves

**Bootstrap by group, not by trade.** When ten wallets bought the same runner, those ten trades are one bet. A trade-level bootstrap treats them as independent and overstates confidence. Resample whole assets (or entities) with replacement, recompute the total, and report P(total > 0) and the 5th percentile. Below ~0.95, or a negative p5, means the sign of the result isn't established.

**Halves.** Split at the median entry time. If one half is positive and the other negative, or each half is only positive because of its own top 1%, the edge isn't stable. Regimes change fast in crypto (weeks), so a result from one month is weak evidence for the next.

## 5. Fill realism and latency

**What it is:** the backtest fills at a price the strategy could not have gotten.

**Typical forms**
- A copy trade filled at the leader's own fill price. A copier is always later.
- Fills at candle open/close, or at "the price at signal time" from an aggregator, instead of the pool state when the transaction lands.
- No price impact for your size in a thin pool, which matters most exactly where memecoins move fastest (5k–50k USD market cap).
- A sell priced at the last trade even though the pool was drained (rug), so nobody could actually sell.

**How to detect**
- Compare backtest fills with what the source actually paid. Our entries landed within a few % of the leader in calm periods, but one fill was 40 vs 61.7 lamports per token in a 1 s burst.
- Look for the latency assumption. If there isn't one, it's zero.

**Fix:** price fills from pool reserves at signal time + latency, with constant-product math at your size (or the venue's real curve). Test several latencies (e.g. 1 s, 2 s, 3 s) and report the sensitivity. Model exits the same way: the trigger is seen, then the fill lands later.

## 6. Costs

Include every cost, per side:
- **Venue fees.** pump.fun bonding curve: protocol + creator fee, which varies per token (we measured 95 + 30 bps and 95 + 0 bps; read each trade's event). PumpSwap: ~25 bps effective. Raydium/Meteora: per pool. Aggregator and trading-bot fees (often ~1%).
- **Network costs.** Base fee, priority fee, tips (Jito/Sender), and rent for new token accounts.
- **Your own price impact**, entering and exiting.
- **Failed and reverted transactions**: fees paid, no fill.
- **Copy-trading services' cut**, if one is used.

Round-trip costs of 2–4% are normal for small memecoin trades. With a +20% take-profit and a −30% stop, break-even win rate ≈ (30 + cost) / (20 + 30) ≈ 66%. Show this arithmetic for TP/SL systems; it usually ends the discussion.

## 7. Data errors

Before believing an extreme trade, check:
- **Several pools per token.** Anyone can create a pool. Dust pools can be priced 100–1000× away from the main pool. In our data, a fill from a 3.4 SOL dust pool against an exit in the main pool produced a fake +78,853% trade. Pin fills to the pool the source actually traded.
- **Decimals and supply.** Market cap = price × supply. Supply varies (pump.fun uses a fixed 1B, but verify per token).
- **Candles.** Thin markets print single-trade wicks. Use closes or volume-weighted prices, and require minimum volume.
- **Quote currency.** SOL vs USD vs USDC mixed. Stablecoin swaps counted as trades.
- **Duplicates.** The same swap ingested twice from overlapping pages. Multi-hop routes counted per leg instead of net per wallet.

Rule of thumb: a single trade above ~+10,000% is a data error until shown otherwise on a block explorer.

## 8. Practical tradability

- **Risk limits vs. the payoff profile.** A strategy with a −14% median trade and a 60 USD daily loss limit at 20 USD per position halts after a handful of losers. In live trading it would rarely be running when the runner arrives, so the backtest's best trades are exactly the ones you'd miss.
- **Concurrency.** The backtest may assume 100 simultaneous positions while the account allows 15.
- **Capacity.** Does the edge survive at 5× the size? In thin pools it usually doesn't.
- **Crowding.** Public wallets are copy-botted within seconds, and some sell into their copiers. Measure the price move in the 30–60 s after the leader's buy. If it's large, the copiers are your competition.

## 9. Quick code-review checklist

When the backtest is code, grep for:
- selection/ranking queries over the same date range as the evaluation;
- `close`, `open` or `price` used as the fill without a latency offset;
- missing fee or slippage parameters, or a slippage constant of 0;
- `dropna` / filters on outcome columns (survivorship);
- `shift(-1)` or forward-looking indexes;
- a train/test split that is random instead of by time (it leaks regime information);
- parameters chosen by `max(sharpe)` over the full sample.

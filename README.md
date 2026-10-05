# crypto-skills

Claude skills for crypto research that's honest about the numbers.

## crypto-backtest-audit

Hand Claude a crypto or memecoin backtest, a trade log, a copy-trading result or a "this wallet is printing" claim. It checks for the traps that make losing strategies look profitable:

- **Look-ahead selection:** wallets or parameters chosen with data from the test period.
- **Survivorship:** hit rates that leave out the duds.
- **Tail dependence:** results that vanish without the top 1% of trades or the best few tokens.
- **Robustness:** a bootstrap by asset, not by trade, plus a first-half / second-half split.
- **Fill realism:** latency, pool reserves, price impact.
- **Costs:** venue fees, priority fees and tips.
- **Data errors:** dust pools, decimals, wicks.

You get back a verdict with the numbers behind it.

It ships a standard-library Python script that runs the quantitative checks on any trade CSV:

```bash
python scripts/audit_trades.py trades.csv --pnl pnl_usd --size size_usd \
    --asset mint --entity wallet --time entry_time --daily-loss-limit 60
```

It reports what's left without the top 1% of trades and the best few tokens, a bootstrap that resamples whole tokens, first-half vs second-half results, a pick-on-A / trade-on-B test for wallets, cost sensitivity, drawdown, a daily-loss-limit simulation, and wallets that look like the same operator.

The checks come from a real Solana copy-trading project in which a +10% backtest turned out to have no out-of-sample edge. The worked example is in `references/case-study.md`.

## solana-swap-explainer

Give Claude a Solana transaction signature or its JSON and it accounts for every lamport of a swap:

- **pump.fun bonding curve:** SOL into the curve, protocol and creator fees (the rates differ per token), reserves, price before and after, price impact.
- **PumpSwap:** pool reserves, fill price, price impact, the fee rates the pool declared, and how far the fill fell short of a no-fee fill.
- **Any venue:** network fee split into base and priority, exact rent, a list of who received SOL and tokens (pool, fee accounts, tips, a router taking a cut), and an all-in price against the pool price before the trade.

The decoder works offline on a transaction file. A separate helper downloads a transaction from the RPC address you give it; there is no built-in endpoint.

```bash
python scripts/explain_swap.py examples/pumpfun_buy.json
```

Checked against recorded mainnet transactions: pump.fun fills reproduce to within 1 part in 10 million, PumpSwap fills to within 0.01%.

## Install (Claude Code)

```
/plugin marketplace add chrisamz/crypto-skills
/plugin install crypto-backtest-audit@crypto-skills
/plugin install solana-swap-explainer@crypto-skills
```

Then just ask, for example: "here's my bot's trade log, is the edge real?"

To use a skill in claude.ai, download its `.skill` file from the [releases page](https://github.com/chrisamz/crypto-skills/releases) and upload it under Settings, Skills.

## Privacy and support

Neither plugin sends anything to the author. `crypto-backtest-audit` works fully offline; `solana-swap-explainer` only contacts the RPC you choose. See each plugin's `PRIVACY.md`. For help or to report a problem, open an [issue](https://github.com/chrisamz/crypto-skills/issues).

## Disclaimer

These are analysis tools, not investment advice. A skill that says a backtest "survives the checks" is telling you the evidence is consistent with an edge, not that you will make money. Paper-trade forward before risking capital.

## License

MIT

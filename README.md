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

## Install (Claude Code)

```
/plugin marketplace add chrisamz/crypto-skills
/plugin install crypto-backtest-audit@crypto-skills
```

Then just ask, for example: "here's my bot's trade log, is the edge real?"

To use it in claude.ai, upload the `plugins/crypto-backtest-audit/skills/crypto-backtest-audit` folder as a skill (zip it first).

## Disclaimer

These are analysis tools, not investment advice. A skill that says a backtest "survives the checks" is telling you the evidence is consistent with an edge, not that you will make money. Paper-trade forward before risking capital.

## License

MIT

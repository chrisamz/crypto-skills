# crypto-backtest-audit

A Claude skill that audits crypto and memecoin backtests, copy-trading results and wallet-performance claims for the traps that make losing strategies look profitable.

## What it checks

- **Look-ahead selection:** wallets, tokens or parameters chosen with data from the test period.
- **Survivorship:** hit rates and token lists that leave out the failures.
- **Tail dependence:** totals that vanish without the top 1% of trades or the best few tokens.
- **Robustness:** a bootstrap that resamples whole tokens, and first-half vs second-half results.
- **Selection test:** pick wallets on the first half, trade them on the second.
- **Fill realism and costs:** latency, pool reserves, price impact, venue and priority fees.
- **Data errors:** dust pools, decimals, duplicate rows, trades above +10,000%.
- **Tradability:** drawdown, losing streaks, and whether a daily loss limit would stop the bot before the winners arrive.

## Use it

Ask Claude things like:

- "Here's my bot's trade log, is the edge real enough to go live?"
- "This wallet shows 82% win rate on GMGN. Should I copy it?"
- "Review my backtest script before I trade it."

With a trade CSV, Claude runs the bundled script (standard-library Python, no install):

```bash
python skills/crypto-backtest-audit/scripts/audit_trades.py trades.csv --pnl pnl_usd \
    --size size_usd --asset mint --entity wallet --time entry_time --daily-loss-limit 60
```

The answer is a verdict (no evidence of edge / edge not robust / plausible, needs out-of-sample test / survives the checks), the numbers behind it, and what test would change it.

## What it runs

- One Python script, `skills/crypto-backtest-audit/scripts/audit_trades.py`, which Claude runs on your machine when you give it a trade CSV.
- The script uses only the Python standard library. It reads the CSV you point it at and prints a report; with `--json` it also writes one result file where you tell it to.
- It works fully offline. The only file it opens is the CSV you give it.
- The plugin has no hooks, no MCP servers and no background processes.

## Not investment advice

This is an analysis tool. A passing audit means the evidence is consistent with an edge, not that you will make money.

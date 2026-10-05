# solana-swap-explainer

A Claude skill that takes one Solana swap transaction and accounts for every lamport: what the wallet really paid or received, the fill price against the pool price before the trade, price impact, launchpad and pool fees, priority fee, tips and bot fees.

## What it explains

- **pump.fun bonding curve trades**, decoded from the event the program logs on every trade: the SOL that went into the curve, the protocol fee and creator fee (the rates differ between tokens), reserves, spot price before and after, price impact, and how full the curve is.
- **PumpSwap (pump.fun AMM) trades**, from the pool's vault balances: reserves, fill price, price impact, and how far the fill fell short of a no-fee fill.
- **Any other venue** (Raydium, Meteora, routes through Jupiter): the wallet's exact net amounts and the cost breakdown. The pool math for these is not modeled, and the report says so.
- **Costs for every swap**: network fee split into base and priority, other costs such as tips and bot fees, account rent, and an all-in price compared with the pool price before the trade.

## Use it

Ask Claude things like:

1. "Explain this transaction: <signature>. What did I actually pay?"
2. "I bought 0.01 SOL of a pump.fun coin and got far fewer tokens than the price suggested. Here is the transaction JSON. Why?"
3. "Break down the fees and price impact in examples/pumpswap_sell.json."

Two real mainnet transactions are included in `examples/` to try it with: `pumpfun_buy.json` and `pumpswap_sell.json`.

You can also run the decoder yourself:

```bash
python skills/solana-swap-explainer/scripts/explain_swap.py examples/pumpfun_buy.json
```

## What it runs

- `scripts/explain_swap.py` reads one transaction JSON file and prints a report. It works fully offline and uses only the Python standard library.
- `scripts/fetch_tx.py` downloads one transaction when you give Claude a signature. It is the only part that uses the network. It sends a single `getTransaction` request, containing the signature, to the RPC address you provide with `--rpc-url`. There is no built-in endpoint, and the helper reads no saved configuration.
- The plugin has no hooks, no MCP servers and no background processes. It never signs or sends transactions.

## Privacy and support

- Privacy policy: [PRIVACY.md](PRIVACY.md). Nothing is sent to the author. The only network request goes to the RPC you choose.
- Support and security reports: open an issue at https://github.com/chrisamz/crypto-skills/issues

## Accuracy

The decoding was checked against recorded mainnet transactions: pump.fun fills reproduce to within 1 part in 10 million, PumpSwap fills to within 0.01%. Details and known limits are in `skills/solana-swap-explainer/references/venues.md`. pump.fun can change its program; if a report looks wrong, compare it with a block explorer and open an issue.

## Not investment advice

This is an analysis tool. It reports what a trade cost, not whether it was a good idea.

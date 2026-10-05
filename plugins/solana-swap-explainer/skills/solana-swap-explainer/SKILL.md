---
name: solana-swap-explainer
description: Explains exactly what happened in a Solana swap transaction - what the wallet really paid or received, the fill price against the pool price before the trade, price impact, pump.fun protocol and creator fees, PumpSwap pool fees, priority fee, tips and bot fees, and the pool reserves it traded against. Decodes pump.fun bonding-curve trades and PumpSwap (pump.fun AMM) pools exactly with a bundled script, and gives net amounts and costs for any other venue. Use this whenever someone shares a Solana transaction signature, a Solscan or other explorer link, or transaction JSON and asks things like "what did I actually pay", "why did I get fewer tokens than quoted", "how much were the fees / slippage / price impact", "what did this wallet buy and at what price", "did my bot overpay", or wants a memecoin trade on pump.fun, PumpSwap, Raydium, Meteora or Jupiter broken down - even if they just paste a signature and say "explain this".
---

# Solana swap explainer

A swap's headline price hides most of what the trader paid. On a small memecoin trade the pool fee, the launchpad's protocol and creator fees, the priority fee, tips, a trading bot's cut and the trade's own price impact routinely add up to several percent, and on tiny trades to much more. This skill reads one transaction and accounts for every lamport.

The bundled script does the arithmetic from the integers in the transaction, so use it instead of working the numbers out by hand. Your job is to get the transaction, run the script, and explain the result in plain language.

## Workflow

### 1. Get the transaction JSON

The script needs the transaction as JSON: the result of the RPC method `getTransaction` with encoding `jsonParsed`.

- **The user gave a file or pasted JSON:** save it to a file and go to step 2.
- **The user gave a signature or an explorer link:** the signature is the long base58 string (in a Solscan link it follows `/tx/`). Download it with the helper:

  ```bash
  python <skill-dir>/scripts/fetch_tx.py <SIGNATURE> --rpc-url <RPC URL> --out tx.json
  ```

  The helper has no built-in endpoint, on purpose: ask the user which RPC to use. If they have none, offer Solana's public endpoint, `https://api.mainnet-beta.solana.com`, which is free but rate-limited and keeps only recent history. If their RPC URL contains an API key, don't repeat the URL back in your reply.
- **If the download fails** ("not found", HTTP 429), say why and ask for another RPC or for the JSON itself. Don't guess what the transaction contained.

### 2. Run the decoder

```bash
python <skill-dir>/scripts/explain_swap.py tx.json [--wallet <ADDRESS>] [--json out.json]
```

Standard library only; it works offline. By default it reports from the fee payer's point of view. Pass `--wallet` when the user asks about a different account (for example the trader behind a bot or relayer that paid the fee). If the report says the wallet's tokens did not change, try the other signers.

What it gives you:

| section | meaning |
|---|---|
| pump.fun bonding curve | Decoded from the event the program logs on each trade: SOL into the curve, protocol and creator fee (the rates vary per token), reserves, spot price before and after, price impact, SOL in the curve, market cap at an assumed 1B supply |
| PumpSwap pool | From the pool's vault balances: reserves, spot before and after, fill price, price impact, and how far the fill fell short of a no-fee fill |
| PumpSwap declared fees | The LP, protocol and creator rates the pool's own event reports for this swap |
| Costs | Network fee split into base and priority; exact rent for any new token account; "other costs" is what the wallet paid beyond the swap, network fee and rent (tips, bot or router fees) |
| Who received SOL / the token | Every other account whose balance went up, labelled where known. Use it to name where the money went: the pool, fee accounts, a router taking a cut in tokens |
| all-in | The wallet's total SOL change per token, compared with the pool price just before the trade |

For any other venue (Raydium, Meteora, a route through Jupiter into them) the report gives the wallet's net amounts and the cost lines, and says the pool math was skipped. Say that plainly; don't fill the gap with guesses.

### 3. Explain it

Lead with the answer to what the user asked, then show the breakdown. A good explanation:

- States what happened in one sentence: who bought or sold how much of which token, on which venue, for how much SOL in total.
- Separates the price the pool gave from everything charged on top. The all-in line against the spot price before the trade is the single most useful number: it is the true cost of getting in or out.
- Names what drove that cost, largest first. Common patterns:
  - **Fixed costs on a small trade.** A priority fee or bot fee of a few thousandths of a SOL is negligible on a 5 SOL trade and can be 10-30% of a 0.01 SOL trade.
  - **Price impact.** The trade itself moved the price; large relative to the pool or curve.
  - **Launchpad fees.** pump.fun charges a protocol fee plus a creator fee that differs between tokens; the report shows the rates this token charged.
  - **A cut taken in tokens.** When the PumpSwap "shortfall vs a no-fee fill" is well above the usual 0.3%, a router, referral or bot took part of the output.
  - **Rent.** A first buy of a token opens a token account (0.0015 to 0.002 SOL), which comes back when the account is closed. On a tiny trade it is often the largest line, so say that it is a deposit, not a loss.
- Converts to the units the user thinks in. The report is in SOL; if they ask in dollars and gave a SOL price, convert, otherwise say the amounts are in SOL.
- Flags anything the transaction can't show: the price they were quoted, whether they were sandwiched (that needs the neighbouring transactions in the block), and what happened in other transactions.

Use this shape unless the user wants something else:

```markdown
**What happened:** <one sentence>

| | amount | share of trade |
|---|---|---|
| Into / out of the pool or curve | ... | |
| Protocol + creator fees or pool fee | ... | ...% |
| Price impact | | ...% |
| Network fee (base + priority) | ... | ...% |
| Other costs (tips, bot fee, rent) | ... | ...% |
| **All-in vs price before the trade** | | **...%** |

<two or three sentences: what drove the cost, and what would have reduced it>
```

If the transaction failed, say so first: a failed swap still pays the network fee and gets nothing.

## When the numbers look wrong

- **Several pools for one token** can appear in one transaction. The script explains the deepest pool by SOL and lists the others; check that the one explained is the one the wallet's tokens came from.
- **Market cap** assumes pump.fun's standard supply of 1 billion tokens. For a token with a different supply, say the figure doesn't apply.
- **A trade far from the pool price** (tens of percent) on a normal-sized trade usually means a thin or secondary pool, not a decoding error. Report it; it is the finding.

Read `references/venues.md` when you need the details: the event layout, how each line is computed, what was verified against real transactions, and the known limits.

## Scope

This explains transactions that already happened. It does not sign, send or simulate transactions, and it is not investment advice: it reports costs, not whether a trade was a good idea.

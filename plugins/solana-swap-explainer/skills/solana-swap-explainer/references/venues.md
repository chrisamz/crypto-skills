# How the swap explainer computes each number

Contents
1. Wallet changes and costs
2. pump.fun bonding curve
3. PumpSwap pools
4. Other venues
5. What was verified
6. Known limits

---

## 1. Wallet changes and costs

All of these come from the transaction's own balance records, so they are exact for any venue.

- **Wallet SOL change** = change in the wallet's native balance, plus the change in any wrapped-SOL token account the wallet owns. Wrapped SOL is counted because many swaps wrap and unwrap inside the transaction.
- **Token change** = change across every token account the wallet owns, per mint.
- **Network fee** = `meta.fee`. Base fee is 5,000 lamports per signature; the rest is the priority fee.
- **Other costs** = what the wallet paid beyond the swap itself and the network fee. For a buy: SOL out of the wallet, minus the network fee, minus the SOL that went into the curve or pool. For a sell: SOL out of the curve or pool, minus the network fee, minus what the wallet actually received. This is where tips (for example Jito), trading-bot or terminal fees, aggregator fees and account rent show up.
- **Rent**: a first buy opens a token account. The report reads the exact rent from the new account's balance in the transaction (about 0.00204 SOL for a classic token account, about 0.00151 SOL for the Token-2022 accounts seen in testing). It is refunded when the account is closed.
- **Who received SOL / who received the token**: every account other than the wallet whose SOL or token balance went up, largest first, labelled where the role is known (pool, bonding curve, pump.fun protocol fee, rent). Unlabelled rows are tips, bot or router fees. This list is what turns "other costs" into named amounts.
- **All-in price** = total wallet SOL change divided by tokens bought or sold. Compared with the spot price before the trade, it is the full cost of the trade as a percentage.

When several tokens change for the wallet in one transaction, SOL can't be assigned to one of them, so the per-token cost lines are left out.

## 2. pump.fun bonding curve

Program: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.

Every buy and sell logs an event as a `Program data:` line (base64). The decoded bytes start with the discriminator `bddb7fd34ee661ee`, followed by these fields, little-endian:

| field | type |
|---|---|
| mint | 32 bytes |
| sol_amount | u64, lamports. On a buy this excludes fees; on a sell it is before fees |
| token_amount | u64, raw units |
| is_buy | u8 |
| user | 32 bytes |
| timestamp | i64 |
| virtual_sol_reserves | u64, after the trade |
| virtual_token_reserves | u64, after the trade |
| real_sol_reserves | u64, after the trade |
| real_token_reserves | u64, after the trade |
| fee_recipient | 32 bytes |
| fee_basis_points | u64 |
| fee | u64, lamports |
| creator | 32 bytes |
| creator_fee_basis_points | u64 |
| creator_fee | u64, lamports |

Newer program versions add more fields after these. The decoder reads the fields above and ignores the rest.

How the report uses them:

- **Reserves before** are the reserves after with the trade undone: for a buy, virtual SOL minus `sol_amount` and virtual tokens plus `token_amount`.
- **Spot price** = virtual SOL / virtual tokens. The curve is constant-product on the virtual reserves.
- **Fees** are charged on top of a buy (the buyer pays `sol_amount + fee + creator_fee`) and taken out of a sell. Each is rounded up: `ceil(sol_amount x bps / 10,000)`.
- **Price impact** = the curve fill price (`sol_amount / token_amount`) against the spot price before.
- **Market cap** = spot after x 1,000,000,000 tokens, in SOL. This assumes the pump.fun standard supply.

Two things vary per token, which is why the decoder reads the event instead of using constants:

- **Fee rates.** Observed: 95 bps protocol + 30 bps creator, and 95 + 0.
- **Curve parameters.** The commonly documented starting point (30 virtual SOL x 1.073 billion virtual tokens) held for one verified token and not for another, whose constant product was about six times smaller.

## 3. PumpSwap pools

Program: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`.

A pool is an account that owns both a token account for the mint and a wrapped-SOL token account. The decoder finds it in the transaction's token balances, skipping accounts that signed the transaction (a trader can hold both kinds of account too).

- **Reserves** = the two vault balances before and after.
- **Spot price** = SOL vault / token vault.
- **Price impact** = SOL in / (SOL reserve + SOL in) for a buy, tokens in / (token reserve + tokens in) for a sell.
- **Shortfall vs a no-fee fill** = 1 - what the wallet got / what a constant-product pool with no fee would have given. On direct PumpSwap trades this was 0.30% in the verified transactions: about 0.25% stays in or is taken at the pool, and about 0.05% is paid out on the token side. A much larger shortfall means something else took a cut of the output (a router, a referral fee, a bot).

- **Declared fee rates** come from the event PumpSwap logs for each swap (discriminators `67f4521f2cf57777` and `3e2f370aa503dc2a`). Only the fee fields are read: LP, protocol and creator rates. In testing they were 25 + 5 + 0 bps on two pools and 20 + 5 + 20 bps on a third, and they matched the measured fills. The event's amount fields are laid out differently between versions, so amounts always come from vault balances.
- **Token-side cuts.** When a router or trading terminal takes its fee in tokens, the pool sends out more tokens than the wallet keeps. The "who received the token" list shows it; in one tested Jupiter route it was 1.5% of the output.
- **Virtual reserves.** Some pools price with extra virtual SOL on top of the vault balance (17.58 SOL on a 2,705 SOL pool in one tested transaction). The true pool price is then slightly higher than the vault ratio the report shows, and the difference lands in the shortfall figure. The report adds a note when the shortfall is larger than the declared fees and token-side transfers explain.

**Several pools per token.** Anyone can create a pool, and small secondary pools can be priced far from the main one. When more than one pool for the mint appears, the decoder explains the deepest by SOL and lists the rest.

## 4. Other venues

Raydium (AMM v4, CPMM, CLMM, LaunchLab), Meteora (DLMM, DAMM, DBC) and routes through Jupiter are recognised by program id and named in "programs referenced". Their pool math is not modeled. For these the report still gives the exact wallet changes and the network fee split, but nothing about the pool. Say so in the explanation.

"Programs referenced" lists programs in the transaction's account list. A program can be referenced without being the venue that filled the trade.

## 5. What was verified

Against recorded mainnet transactions (September 2026):

- pump.fun buys: decoded `sol_amount`, `token_amount` and both fees match the wallet's actual token and SOL changes; a constant-product prediction from the reserves before reproduces the tokens received to within 1 part in 10 million.
- PumpSwap buy and sell: a constant-product prediction with a 0.30% total fee reproduces the fills to within 0.01%.
- The fetch helper and decoder were run end to end against Solana's public RPC.

Two of those transactions are in `examples/` at the plugin root: `pumpfun_buy.json` and `pumpswap_sell.json`.

## 6. Known limits

- One transaction at a time. Sandwich detection needs the neighbouring transactions in the same block; this doesn't fetch them.
- The quoted price the user saw before sending is not on chain, so "slippage vs quote" can't be computed. The report compares against the pool price just before the trade, which is the on-chain equivalent.
- Token-2022 transfer fees are not broken out; they would appear inside the shortfall or all-in figure.
- The order's slippage limit (minimum out or maximum in) is in the instruction data and is not decoded, so the report can't say how loose the trader's limit was.
- PumpSwap virtual reserves are detected only indirectly (see section 3).
- pump.fun can change its event layout. If the discriminator stops matching, the curve section disappears and the report falls back to net amounts; say so and point the user to the transaction's logs.

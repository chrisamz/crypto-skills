"""Download one Solana transaction as JSON, ready for explain_swap.py.

Standard library only. This is the only part of the plugin that uses the network, and it
talks to exactly one address: the RPC URL you pass on the command line. There is no built-in
endpoint and nothing is read from saved configuration.

    python fetch_tx.py SIGNATURE --rpc-url https://your-rpc.example --out tx.json

What is sent: a single JSON-RPC getTransaction request containing the signature.
What comes back: the public transaction, saved to the file given with --out.

Any Solana RPC works. Solana's public endpoint (https://api.mainnet-beta.solana.com) is free
but rate-limited and only keeps recent history; a provider URL of your own reaches further back.
If your URL contains an API key, treat the URL as a secret: it is used for this one request and
is never printed or saved.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def fetch(signature: str, rpc_url: str, timeout: float) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                               "commitment": "finalized"}],
    }).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            reply = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"RPC returned HTTP {e.code}. A 429 means rate-limited: wait and retry.")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach the RPC: {e.reason}")
    if reply.get("error"):
        sys.exit(f"RPC error: {reply['error'].get('message', reply['error'])}")
    if reply.get("result") is None:
        sys.exit("transaction not found: wrong signature, not finalized yet, or older than this "
                 "RPC keeps. Try an archival RPC.")
    return reply["result"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Download a Solana transaction for explain_swap.py.")
    ap.add_argument("signature")
    ap.add_argument("--rpc-url", required=True, help="the RPC to ask; no default")
    ap.add_argument("--out", required=True, help="where to save the transaction JSON")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    if not args.rpc_url.startswith("https://"):
        sys.exit("--rpc-url must start with https://")
    tx = fetch(args.signature, args.rpc_url, args.timeout)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(tx, f)
    print(f"saved {args.signature} (slot {tx.get('slot')}) to {args.out}")


if __name__ == "__main__":
    main()

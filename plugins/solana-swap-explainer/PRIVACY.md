# Privacy policy: solana-swap-explainer

Last updated: 2026-10-05

## Summary

This plugin sends nothing to its author. It has no server of its own, no account, no analytics and no telemetry.

## What the plugin handles

- **A transaction you ask about.** Solana transactions are public records. The decoder reads one transaction JSON file and prints a report about it.
- **An RPC address, if you ask it to download a transaction.** When you give Claude a signature, the fetch helper sends one request to the RPC address you provide. The request contains the signature and nothing else. If your RPC address includes an API key, the key is used for that request only; the helper does not print it or save it.

## What leaves your computer

- **To the author:** nothing.
- **To the RPC you chose:** one `getTransaction` request per download. That RPC provider sees the request under its own privacy policy. The plugin has no built-in endpoint, so no request is made unless you supply an address.
- The decoder itself works offline.

Your conversation with Claude is handled by Anthropic under Anthropic's own privacy policy. This plugin does not change that.

## Storage and retention

The plugin stores nothing by itself. It writes only the files you ask for: the downloaded transaction (the path given with `--out`) and, optionally, a result file (`--json`). Both stay on your computer.

Because the author receives no data, there is nothing for the author to retain, share or delete.

## Children

The plugin is a tool for analysing trading transactions and is not intended for anyone under 18.

## Changes

If the plugin ever handles data differently, this file will be updated in the same release and the change described in the release notes.

## Contact

Questions or concerns: open an issue at https://github.com/chrisamz/crypto-skills/issues

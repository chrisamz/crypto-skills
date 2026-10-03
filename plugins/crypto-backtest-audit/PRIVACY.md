# Privacy policy: crypto-backtest-audit

Last updated: 2026-10-03

## Summary

This plugin collects nothing. It has no server, no account, no analytics and no telemetry. Everything it does happens on your own computer, inside your Claude session.

## What the plugin handles

- **Files you choose to give it.** When you ask for an audit and point Claude at a trade file (a CSV), the bundled script reads that one file and prints a report. The file can contain trade results, sizes, token names and wallet identifiers.
- **Nothing else.** The plugin does not read Claude's memory, your chat history, or any file you did not point it at.

## What leaves your computer

Nothing is sent to the plugin's author or to any third party. The script works fully offline and contains no network code. The plugin has no hooks, no MCP servers and no connectors.

Your conversation with Claude, including anything you paste or upload, is handled by Anthropic under Anthropic's own privacy policy. This plugin does not change that.

## Storage and retention

The plugin stores nothing. The only file it can write is a result file, and only when you ask for one by passing the `--json` option with a path you choose. That file stays on your computer.

Because the author receives no data, there is nothing for the author to retain, share or delete.

## Children

The plugin is a tool for analysing trading results and is not intended for anyone under 18.

## Changes

If the plugin ever starts handling data differently, this file will be updated in the same release, and the change will be described in the release notes.

## Contact

Questions or concerns: open an issue at https://github.com/chrisamz/crypto-skills/issues

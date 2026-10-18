---
title: "Photo upload, annotation, MCP servers and second opinions — Roomsmith"
description: "The local web app for uploading and annotating room photos, the MCP servers Claude can use alongside it (Roomsmith, Artlist, OpenRouter), and consulting other models."
---

# Services

## `design serve` — photos, annotations, revisions, catalog

```bash
design serve                 # or: nix run .#serve
```

Prints a one-time login link for `http://127.0.0.1:8765`. Pick a room in the sidebar.

**Photos.** Drop photos in, or tap to choose on a phone. JPEG, PNG and WebP; HEIC is refused with
the setting that fixes it. Every upload has its **location and camera metadata removed** (EXIF GPS,
serial numbers, XMP, PNG text), keeping only orientation. Pixel data is never re-encoded.

**Annotate.** Click a photo:

| Tool | Use it for | Saved as |
|---|---|---|
| Measure | drag along something you've put a tape on, type the length | `line` + `length_m` |
| Tag | click a door, window or radiator, give it the room-model tag | `point` + `tag` (`D1`, `W1`, `RAD`) |
| Area | outline damp, a beam, a socket run | `rect` + note |
| Arrow | point at anything | `arrow` + note |

Annotations go to `refs/<photo>.annotations.json`, in fractions of the image size. The surveyor
agent reads them: **a tape measurement beats anything it would estimate by proportion.**

**Revisions.** Make any revision HEAD, branch a new one, and flip between two revisions' renders
or drawings in place (space bar).

**Catalog.** Every item with footprint, clearances, sources and verification state. *I checked
these numbers* verifies an item, exactly like `design catalog verify`.

The server is for your own machine. See [SECURITY](SECURITY.md#the-local-server) for how it is
locked down. `--host 0.0.0.0` is possible (the container uses it) and prints a warning.

## MCP servers

`.mcp.json` registers three. Claude Code asks before enabling each project server the first time.

| Server | What it adds | Auth |
|---|---|---|
| `roomsmith` (stdio, this repo) | `rooms_list`, `room_status`, `catalog_list`, `catalog_get`, `annotations_get` — read-only — and `consult` | none; local |
| `artlist` (`https://mcp.artlist.io/mcp`) | Artlist's stock footage, music and AI image/video generation, for mood boards and walk-through clips | your Artlist account, OAuth. Generations use your Artlist AI credits |
| `openrouter` (`https://mcp.openrouter.ai/mcp`) | OpenRouter's official server: model lists, prices, credits, and billable `send-message` / `generate-image` | OAuth; it mints a key that expires in 7 days with a $10 cap you can change at approval |

```bash
claude mcp list                  # see them
/mcp                             # inside Claude Code: authenticate artlist / openrouter
```

**Claude remains the driver.** The other servers are tools it calls, and their output is
material it weighs. The `roomsmith` server deliberately has no tool that approves a gate,
verifies a catalog item or edits a spec — those stay with you on the command line.

The same `.mcp.json` works for any MCP client. For Codex: `codex mcp add roomsmith -- design mcp`.

## `design consult` — a second opinion

For when another model's view is worth paying for — a critic's verdict on a render, a dimension
two sources disagree on:

```bash
design consult "Is there a door in the left wall of this image?" --image renders/01-rack-hero.png
design consult "Rogue says 24 in inside depth, a review says 30. Which fits a 60 cm bench?" --model anthropic/claude-sonnet-4.5
```

Uses `OPENROUTER_API_KEY` from `.env` — the same key as the paid render backend.

| Variable | Default | |
|---|---|---|
| `ROOMSMITH_CONSULT_MODEL` | `openrouter/auto` | the model asked when `--model` is not given |
| `ROOMSMITH_CONSULT_MODELS` | *(any)* | comma-separated allowlist; set it and nothing else can be called |
| `ROOMSMITH_CONSULT_MAX_USD` | `5` | hard ceiling on total consult spend, kept in `.consult.jsonl` |

Agents use it through the `consult` MCP tool, under the same ceiling. Set
`ROOMSMITH_MCP_CONSULT=off` to remove that ability.

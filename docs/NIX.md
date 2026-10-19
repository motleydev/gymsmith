---
title: "Running anywhere with Nix — Roomsmith"
description: "Install Roomsmith with Nix: a pinned Python, Chromium and fonts on Linux and macOS, a dev shell with Claude Code, a container image, and a CVE scan of the whole closure."
---

# Running anywhere with Nix

The flake pins **everything Roomsmith shells out to** to one nixpkgs release: Python and PyYAML,
Chromium, the fonts the drawings are laid out in, and the CVE scanner. Two machines with the same
`flake.lock` draw the same plan, pixel for pixel.

| | |
|---|---|
| `nix run github:motleydev/gymsmith -- rooms` | run it without installing anything |
| `nix profile install github:motleydev/gymsmith` | install `design` on your PATH |
| `nix develop` | a shell in a checkout: Python, Chromium, fonts, vulnix |
| `nix develop .#agents` | the same, plus Claude Code and the Codex CLI, pinned |
| `nix run .#serve` | the photo upload, annotation and revision viewer |
| `nix run .#cve-scan` | every package in the runtime closure checked against the NVD |
| `nix flake check` | the test suite, in the Nix sandbox |
| `nix build .#docker` | a container image, for machines without Nix (Linux) |

Requires Nix with flakes (`experimental-features = nix-command flakes`). With
[direnv](https://direnv.net), `direnv allow` enters the dev shell automatically (`.envrc` is
committed).

## Every command is an app

Each `design` subcommand is also a flake app. Arguments go after `--`:

| | |
|---|---|
| `nix run .#demo` | a ready-made garage gym in two revisions |
| `nix run .#init -- house/garage` | scaffold a room |
| `nix run .#rooms` · `nix run .#use -- house/garage` | list everything · set the default |
| `nix run .#status` · `nix run .#gates` | where the job is · the approval gates |
| `nix run .#check` | geometry, layouts and catalog clearances |
| `nix run .#approve -- room-model --note "measured"` | record an approval |
| `nix run .#rev -- new --note "rack in the corner"` | branch a revision (`list`, `switch r1`, `diff r1..r2`) |
| `nix run .#catalog -- list` | the catalog (`show`, `check`, `verify`, `new` + an id) |
| `nix run .#drawings -- 01` · `nix run .#pack -- 01` | measured drawings · one direction end to end |
| `nix run .#render -- --dry` · `nix run .#report` | photoreal views · the PDF |
| `nix run .#serve` · `nix run .#consult -- "question"` · `nix run .#mcp` | services |
| `nix run .#test` · `nix run .#cve-scan` | the test suite · the CVE scan |

`nix flake show` lists them with descriptions. Run inside a checkout, they use the checkout as
the data home, exactly like `./bin/design`; run anywhere else (`nix run github:motleydev/gymsmith#rooms`),
they use `~/.local/share/roomsmith`.

Inside `nix develop`, `design` itself is on your PATH and runs the checkout's own code — so
`design check` instead of `./bin/design check`.

## Where your data goes

Code and data are separate. Installed from Nix, the code is read-only in `/nix/store`, so projects,
the catalog and `.env` live in a data home:

1. `$ROOMSMITH_HOME`, if set
2. the checkout itself, when you run from a writable git clone — exactly as `./bin/design` always
   worked
3. `$XDG_DATA_HOME/roomsmith`, else `~/.local/share/roomsmith`

`design rooms` prints which one is in use. Point several machines at one synced folder with
`ROOMSMITH_HOME` and they share projects and the catalog.

## Platforms

| | Linux x86-64 / ARM | macOS (Apple silicon / Intel) |
|---|---|---|
| CLI, catalog, server, MCP | ✓ | ✓ |
| Chromium for drawings and the PDF | pinned by the flake | nixpkgs does not build Chromium for macOS: install Google Chrome, which is found in `/Applications`, or set `ROOMSMITH_CHROME` |
| Container image | ✓ | build it on a Linux builder |
| `.#agents` shell | ✓ | ✓ |

Windows: use WSL2 and follow the Linux column.

## The container

```bash
docker load < $(nix build .#docker --print-out-paths)
docker run --rm -p 127.0.0.1:8765:8765 -v roomsmith:/data roomsmith      # serve
docker run --rm -v roomsmith:/data roomsmith rooms                      # any command
```

No shell, no package manager, runs as uid 1000, data on the `/data` volume. Publish the port on
`127.0.0.1` only; set `ROOMSMITH_SERVE_TOKEN` if you want a stable login link.

## Keeping it patched

```bash
nix flake update          # move nixpkgs to the newest nixos-26.05 commit
nix run .#cve-scan        # what is still open
nix flake check           # nothing broke
git commit flake.lock -m "chore: bump nixpkgs"
```

Do this monthly, and the day a Chromium or OpenSSL advisory lands. When 26.11 is released, change
the branch in `flake.nix` and repeat. See [SECURITY](SECURITY.md) for how the scan's results are
triaged.

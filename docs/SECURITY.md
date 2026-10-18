---
title: "Security and prompt injection — Roomsmith"
description: "Roomsmith's threat model: where untrusted text enters, how prompt injection is contained, how the local server is locked down, and how CVEs in the dependency closure are tracked."
---

# Security

Roomsmith is an agent system that reads photographs, web pages and other models' output, and can
spend money and run tools. The design rule: **untrusted text may inform a decision, but it can
never make one.** Every irreversible or costly step is gated on a person, and every place where
outside text meets something that can act has a control that does not depend on a model behaving.

## Where untrusted text enters

| Source | Reaches | Control |
|---|---|---|
| Web pages (catalog research) | `catalog-researcher`, then the catalog, prompts, report | The researcher has **no shell** (Read, Write, Glob, Grep, WebSearch, WebFetch only). `catalog check` rejects invisible/bidi characters, implausible units and non-https sources, and flags instruction-shaped text. An item is unusable in a render until a person runs `catalog verify`, which is **hash-bound**: any later edit un-verifies it |
| Text in photographs, annotation labels | surveyor and author agents | Agent instructions treat it as data. Labels are length-limited and stripped of control characters on save |
| Other models (`consult`, OpenRouter, Artlist) | Claude | Returned labelled as untrusted advice. `consult` has a model allowlist and a spend ceiling |
| Spec, catalog and annotation text | image prompts | Free text is normalised, stripped of invisible characters and code fences, and bounded (`catalog.clean`) |
| All of the above | the **codex** render backend | See below — this was the most serious issue |

### The codex backend (fixed)

Previously codex ran with `--dangerously-bypass-approvals-and-sandbox` and write access to the
whole repository, while its prompt carried spec text — and, with the catalog, text derived from web
pages. An injected sentence in that prompt was therefore one step from arbitrary command execution
on your machine.

Now codex runs with `--sandbox workspace-write` in an empty scratch directory containing only
copies of the reference images. The prompt is fenced and declared to be data. The escape hatch
`ROOMSMITH_CODEX_SANDBOX=off` exists for old codex builds, and the Claude Code permissions deny
Claude from setting it.

### What Claude may not do

`.claude/settings.json` denies, whatever an injected instruction says:

- `design approve …` — gates are the client's
- `design catalog verify|unverify …` — so is trusting a product's numbers
- editing `STATE.json` or `catalog/.verified.json` directly
- reading `.env`
- disabling the codex sandbox

The allow list covers the read-only commands (`status`, `check`, `catalog check`, `render --dry` …)
so they run without prompts. The `roomsmith` MCP server has **no tool that writes**, apart from
spend-capped `consult`, and confines every path to the data home.

## The local server

`design serve` assumes a browser on the same machine is also open on the internet.

- Binds `127.0.0.1` by default; anything else prints a warning
- A random token per run, exchanged at `/login` for an `HttpOnly; SameSite=Strict` cookie
- **Host header allowlist**, which defeats DNS rebinding
- Changing requests need an `X-Roomsmith` header (forces a CORS preflight the server never
  answers) and a same-origin `Origin`, which defeats CSRF
- CSP `default-src 'none'; script-src 'self' …`; no third-party code; the UI sets text with
  `textContent` only, so a label or catalog field cannot become script
- Every name in a URL is validated against a pattern and resolved paths are confined to their
  directory
- Uploads are identified by magic bytes (JPEG/PNG/WebP only, no SVG), size- and pixel-limited,
  and **stripped of EXIF GPS, serials, XMP and PNG text** before they are written
- Errors never return tracebacks

## Headless Chrome

Drawings and the report are HTML built from spec text. Every page Chrome opens carries
`default-src 'none'` (no script, no network — tested: a script that turns the page red does not
run). Each run gets a throwaway profile, extensions, sync and background networking are off, and
Chrome's own sandbox stays on except as root or in the container.

## Python

- Standard library only, plus PyYAML through `yaml.safe_load` (never `load`, the source of
  CVE-2017-18342 and CVE-2020-14343). The built-in fallback parser evaluates nothing.
- The Nix wrapper runs Python with `-P`, so a planted `engine/` or `yaml.py` in your working
  directory cannot shadow the real modules.

## CVEs

Every runtime dependency — Python, PyYAML, Chromium, fonts, glibc, OpenSSL — comes from one pinned
nixpkgs commit in `flake.lock`. Nothing is fetched at runtime and there is no npm or pip install.

```bash
nix run .#cve-scan        # vulnix over the whole runtime closure; non-zero exit if anything open
nix flake update          # take the newest security fixes on nixos-26.05
```

Triage: an unwhitelisted finding is fixed by updating the lock. If nixpkgs has not shipped the fix
yet and the CVE cannot be reached the way Roomsmith uses the package, add it to
`security/vulnix-whitelist.toml` **with a reason and an `until` date**. Chromium is the package to
watch: it is the largest attack surface in the closure, and it only ever opens local, script-free
pages here.

### Status at the current pin (2026-10-18, nixpkgs `26f4107`, the head of nixos-26.05)

`nix run .#cve-scan` reports **57 CVE matches in 16 packages, 5 rated CVSS ≥ 9.0**, and exits
non-zero. Nothing is whitelisted yet; each needs reading before it is accepted or fixed:

| Packages | Why they are in the closure | Reachability here |
|---|---|---|
| avahi, cups, gstreamer, orc, libsoup, libusb, libsndfile, giflib, nghttp2, cjson | Chromium's runtime dependencies (printing, mDNS, media, WebUSB, HTTP/2) | Low: Chromium opens only local, script-free, network-free pages, headless. Still the first thing to bump |
| zlib, sqlite, glibc, perl, gcc (runtime libs), jq | shared by Python, Chromium and the dev shell | Roomsmith itself never decompresses image data, but Chromium and Python do — read each advisory |

vulnix matches on package name and version, so some of these will already be patched in nixpkgs
without a version change (false positives). The ones that are not get fixed by `nix flake update`
as nixos-26.05 picks up the fixes — or sooner by following `nixos-26.05-small`, which receives
security updates days earlier. Re-run the scan after every update; whitelist only with a reason.

Remote MCP servers (Artlist, OpenRouter) are run by those companies and are not in the closure.
They authenticate with OAuth; the OpenRouter token expires after 7 days with a spend cap. Revoke
either from the provider's dashboard.

## Reporting

Open a private security advisory on the repository rather than a public issue.

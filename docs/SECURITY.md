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

`nix run .#cve-scan` first reported **57 matches in 16 packages, 5 rated CVSS ≥ 9.0**. All five
critical findings were triaged and are **false positives**, whitelisted against their exact
versions in `security/vulnix-whitelist.toml`:

| Package | CVE | Why it does not apply |
|---|---|---|
| glibc 2.42-100 | CVE-2026-5450 | Fixed by nixpkgs' `2.42-master.patch` (upstream backport naming this CVE) |
| zlib 1.3.2 | CVE-2026-27820 | A different product: the Ruby `zlib` gem |
| orc 0.4.41 | CVE-2025-47436 | A different product: Apache ORC, not GStreamer's orc |
| perl 5.42.3 | CVE-2026-8376, CVE-2026-13221 | Fixed in 5.42.3-RC1; 5.42.3 includes the fix |

**52 lower-severity matches remain untriaged** (none critical; the highest is 8.8), so the scan
still exits non-zero. Most are in Chromium's dependencies — gstreamer, libsoup, avahi, cups,
libsndfile — which this setup barely exercises: Chromium opens only local, script-free,
network-free pages. The rest are glibc, sqlite, cjson, perl and nghttp2. Expect a share of
version-only false positives like the ones above.

vulnix matches on package name and version, so it cannot see nixpkgs backports or tell two
products with the same name apart. Genuine findings are fixed by `nix flake update` as nixos-26.05
picks up fixes — or sooner by following `nixos-26.05-small`. Re-run the scan after every update.

Remote MCP servers (Artlist, OpenRouter) are run by those companies and are not in the closure.
They authenticate with OAuth; the OpenRouter token expires after 7 days with a spend cap. Revoke
either from the provider's dashboard.

## Reporting

Open a private security advisory on the repository rather than a public issue.

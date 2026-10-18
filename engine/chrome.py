"""Headless Chrome, used for two things only: SVG → PNG and HTML → PDF.

The pages it opens are built from spec text, catalog entries and annotations, which agents and
web pages helped write. So every page carries a CSP that forbids script and network access, the
browser gets a throwaway profile, and Chrome's own sandbox stays on unless we are root (where
Chrome refuses to start with it).

Which binary, highest first: $ROOMSMITH_CHROME (the Nix package sets this), then the usual
names on PATH, then the standard macOS application path.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

NAMES = ("google-chrome", "chromium", "chromium-browser", "chrome", "google-chrome-stable")
MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
       "img-src data:; style-src 'unsafe-inline'; font-src data:\">")


def find():
    env = os.environ.get("ROOMSMITH_CHROME", "").strip()
    if env and os.access(env, os.X_OK):
        return env
    for n in NAMES:
        p = shutil.which(n)
        if p:
            return p
    return MAC if os.access(MAC, os.X_OK) else None


def run(args, timeout=180, check=False):
    """Run Chrome headless with hardening flags. Returns the CompletedProcess, or None."""
    exe = find()
    if not exe:
        return None
    with tempfile.TemporaryDirectory(prefix="roomsmith-chrome-") as profile:
        flags = ["--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                 "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                 "--disable-background-networking", "--disable-component-update",
                 f"--user-data-dir={profile}"]
        # Script is forbidden by the CSP every page carries (see with_csp), not by a flag:
        # --blink-settings=scriptEnabled=false also stops headless screenshots being taken.
        if hasattr(os, "geteuid") and os.geteuid() == 0 or os.environ.get("ROOMSMITH_CHROME_NO_SANDBOX"):
            flags.append("--no-sandbox")
        return subprocess.run([exe, *flags, *args], capture_output=True, timeout=timeout,
                              check=check)


def with_csp(html):
    """Insert the no-script, no-network policy as the first thing in <head>."""
    if "<head>" in html:
        return html.replace("<head>", "<head>" + CSP, 1)
    return f"<html><head>{CSP}</head>" + html.replace("<html>", "", 1)


def page_uri(path):
    return pathlib.Path(path).resolve().as_uri()

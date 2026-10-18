"""Projects, rooms and revisions.

A PROJECT is a site — a house, a flat, a client. It holds ROOMS. Each room holds REVISIONS, and
exactly one revision is HEAD. A revision is an ordinary job directory (project.yml, STATE.json,
brief/, directions/ …), so every existing command works on it unchanged; this module only decides
which directory that is.

    projects/<project>/
      workspace.yml                     name, notes
      rooms/<room>/
        HEAD                            the active revision id, e.g. "r2"
        refs/                           photographs, shared by every revision of the room
        revisions/
          r1/  REVISION.json  project.yml  STATE.json  brief/  directions/  drawings/  renders/ …
          r2/  …

Photographs live at room level because they are of the physical room, which does not change when
the design does. Everything a revision *decides* lives inside it, so flipping HEAD is instant and
lossless: nothing is deleted, nothing is merged.

The older flat layout — projects/<slug>/project.yml — is still a valid single-room project.

Addresses:
    garage-gym                 a flat project, or a nested project with exactly one room
    house/garage               HEAD revision of that room
    house/garage@r1            a specific revision
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import time

from .paths import CONFIG, PROJECTS

CFG_NAMES = ("project.yml", "project.yaml", "project.json")
# Sources are copied into a new revision. Outputs are regenerated from them, so are not.
SOURCES = ("project.yml", "project.yaml", "project.json", "brief", "directions")
OUTPUTS = ("drawings", "renders", "report", "prompts")
# Lenient enough for every slug the flat layout ever accepted; strict enough that no address can
# climb out of projects/ ("..", "/", absolute paths).
SLUG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}$")
REV = re.compile(r"^r[0-9]{1,4}$")


def check_slug(s, what="slug"):
    if not SLUG.match(s or "") or ".." in s:
        raise SystemExit(f"bad {what} {s!r}: use letters, digits and hyphens")
    return s


def parse(address):
    """'house/garage@r2' -> ('house', 'garage', 'r2'). Missing parts are None."""
    rev = None
    if "@" in address:
        address, rev = address.split("@", 1)
        if not REV.match(rev):
            raise SystemExit(f"bad revision {rev!r}: revisions are r1, r2, …")
    parts = address.strip("/").split("/")
    if len(parts) > 2:
        raise SystemExit(f"bad address {address!r}: expected project[/room][@rev]")
    proj = check_slug(parts[0], "project")
    room = check_slug(parts[1], "room") if len(parts) == 2 else None
    return proj, room, rev


def is_flat(proj_dir):
    return any((proj_dir / n).exists() for n in CFG_NAMES)


def rooms(proj_dir):
    d = proj_dir / "rooms"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def revisions(room_dir):
    d = room_dir / "revisions"
    if not d.exists():
        return []
    return sorted((p.name for p in d.iterdir() if p.is_dir() and REV.match(p.name)),
                  key=lambda r: int(r[1:]))


def head(room_dir):
    f = room_dir / "HEAD"
    if f.exists():
        rev = f.read_text().strip()
        if (room_dir / "revisions" / rev).is_dir():
            return rev
    revs = revisions(room_dir)
    return revs[-1] if revs else None


def locate(address):
    """Resolve an address to (job_dir, canonical_address). Exits with a clear reason if it can't."""
    proj, room, rev = parse(address)
    pd = PROJECTS / proj
    if not pd.exists():
        raise SystemExit(f"no project {proj!r} in {PROJECTS}")
    if is_flat(pd):
        if room or rev:
            raise SystemExit(f"{proj!r} is a single-room project with no rooms or revisions. "
                             f"Address it as just '{proj}'")
        return pd, proj
    if room is None:
        rs = rooms(pd)
        if len(rs) != 1:
            raise SystemExit(f"project {proj!r} has {len(rs)} rooms; say which: "
                             + ", ".join(f"{proj}/{r}" for r in rs))
        room = rs[0]
    rd = pd / "rooms" / room
    if not rd.exists():
        raise SystemExit(f"no room {room!r} in project {proj!r}. Rooms: {', '.join(rooms(pd)) or 'none'}")
    rev = rev or head(rd)
    if not rev or not (rd / "revisions" / rev).is_dir():
        raise SystemExit(f"room {proj}/{room} has no revision {rev or ''}. "
                         f"Revisions: {', '.join(revisions(rd)) or 'none'}")
    return rd / "revisions" / rev, f"{proj}/{room}@{rev}"


def room_dir_of(job_dir):
    """The room directory a revision belongs to, or None for a flat project."""
    return job_dir.parent.parent if job_dir.parent.name == "revisions" else None


def address_of(job_dir):
    rd = room_dir_of(job_dir)
    if rd is None:
        return job_dir.name
    return f"{rd.parent.parent.name}/{rd.name}@{job_dir.name}"


def current():
    f = CONFIG / "current"
    return f.read_text().strip() if f.exists() else ""


def use(address):
    locate(address)
    CONFIG.mkdir(parents=True, exist_ok=True)
    # Store the room, not the revision, so `current` follows HEAD when it moves.
    (CONFIG / "current").write_text(address.split("@")[0] + "\n")


# ---------------------------------------------------------------- creation

def new_project(proj, name=""):
    check_slug(proj, "project")
    pd = PROJECTS / proj
    if is_flat(pd):
        raise SystemExit(f"{proj!r} is already a single-room project")
    (pd / "rooms").mkdir(parents=True, exist_ok=True)
    meta = pd / "workspace.yml"
    if not meta.exists():
        meta.write_text(f'name: "{name or proj}"\ncreated: "{time.strftime("%Y-%m-%d")}"\n')
    return pd


def new_room(proj, room, template_file):
    pd = new_project(proj)
    check_slug(room, "room")
    rd = pd / "rooms" / room
    if rd.exists():
        raise SystemExit(f"room {proj}/{room} already exists")
    (rd / "refs").mkdir(parents=True)
    job = rd / "revisions" / "r1"
    _scaffold(job)
    shutil.copy(template_file, job / "project.yml")
    _write_meta(job, "r1", None, "initial revision")
    (rd / "HEAD").write_text("r1\n")
    return job


def new_revision(room_dir, base=None, note="", keep_approvals=False):
    base = base or head(room_dir)
    src = room_dir / "revisions" / base
    if not src.is_dir():
        raise SystemExit(f"no revision {base!r} to branch from")
    revs = revisions(room_dir)
    rid = f"r{max(int(r[1:]) for r in revs) + 1}"
    dst = room_dir / "revisions" / rid
    _scaffold(dst)
    for name in SOURCES:
        s = src / name
        if s.is_dir():
            shutil.copytree(s, dst / name, dirs_exist_ok=True)
        elif s.exists():
            shutil.copy(s, dst / name)
    state = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "approvals": {}, "log": []}
    old = json.loads((src / "STATE.json").read_text()) if (src / "STATE.json").exists() else {}
    # A revision exists because something is changing, so the decisions that rested on the old
    # version are not carried over by default. The brief is about the client, not the design,
    # and is the one exception.
    keep = old.get("approvals", {}) if keep_approvals else {
        k: v for k, v in old.get("approvals", {}).items() if k == "brief"}
    state["approvals"] = {k: dict(v, note=f"inherited from {base}: {v.get('note', '')}")
                          for k, v in keep.items()}
    state["log"].append({"at": state["created"], "msg": f"branched from {base}"
                         + (f": {note}" if note else "")})
    (dst / "STATE.json").write_text(json.dumps(state, indent=2) + "\n")
    _write_meta(dst, rid, base, note)
    return rid


def switch(room_dir, rev):
    if not (room_dir / "revisions" / rev).is_dir():
        raise SystemExit(f"no revision {rev!r}. Revisions: {', '.join(revisions(room_dir))}")
    (room_dir / "HEAD").write_text(rev + "\n")


def meta(job_dir):
    f = job_dir / "REVISION.json"
    return json.loads(f.read_text()) if f.exists() else {}


def diff(room_dir, a, b):
    """Unified diff of the SOURCES of two revisions. Outputs are derived, so not compared."""
    ra, rb = room_dir / "revisions" / a, room_dir / "revisions" / b
    for r in (ra, rb):
        if not r.is_dir():
            raise SystemExit(f"no revision {r.name!r}")

    def files(root):
        out = {}
        for name in SOURCES:
            p = root / name
            if p.is_file():
                out[name] = p
            elif p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        out[str(f.relative_to(root))] = f
        return out

    fa, fb = files(ra), files(rb)
    out = []
    for rel in sorted(set(fa) | set(fb)):
        ta = fa[rel].read_text(errors="replace").splitlines() if rel in fa else []
        tb = fb[rel].read_text(errors="replace").splitlines() if rel in fb else []
        out += difflib.unified_diff(ta, tb, f"{a}/{rel}", f"{b}/{rel}", lineterm="")
    return "\n".join(out)


def tree():
    """Every project, room and revision, for listings and the web UI."""
    out = []
    if not PROJECTS.exists():
        return out
    for pd in sorted(p for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if is_flat(pd):
            out.append({"project": pd.name, "flat": True, "rooms": []})
            continue
        rs = []
        for r in rooms(pd):
            rd = pd / "rooms" / r
            rs.append({"room": r, "head": head(rd),
                       "revisions": [dict(meta(rd / "revisions" / v), id=v)
                                     for v in revisions(rd)]})
        out.append({"project": pd.name, "flat": False, "rooms": rs})
    return out


def _scaffold(job):
    for d in ("brief", "directions") + OUTPUTS:
        (job / d).mkdir(parents=True, exist_ok=True)


def _write_meta(job, rid, parent, note):
    (job / "REVISION.json").write_text(json.dumps(
        {"id": rid, "parent": parent, "note": note,
         "created": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2) + "\n")

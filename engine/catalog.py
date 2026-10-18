"""The equipment and furniture catalog: things being considered, bought or owned.

A catalog item is not a picture of a product. It is what the room model needs to know to put the
product in a real room and prove it can be USED there:

    footprint      w × d × h assembled, in metres, with the source's own words kept beside it
    use            the clearance needed on each side to use it, and overhead reach
    implements     things that stick out in use — a 2.2 m barbell across a 1.2 m rack
    assembly       whether it is built lying down and tilted up (needs more height than it stands)
    sources        where every number came from, so a person can check it

One YAML file per item in catalog/<id>.yml, usually written by the catalog-researcher agent from
manufacturer pages. Web pages are untrusted, so an item is only usable in a render once a person
has run `design catalog verify <id>`. Verification records a hash of the file: edit the file, by
hand or by an agent, and it is unverified again. Nothing can change a verified item silently.

Directions place an item by id, and its dimensions are filled in from here:

    layout:
      plan:
        - {label: "Power rack", catalog: rogue-rml-390f, x: 0.4, y: 2.1, rotation: 0}

`rotation` is which way the item's FRONT faces in plan: 0 = towards +y (away from wall w1 in a
rectangle), 90 = -x, 180 = -y, 270 = +x. Width and depth swap at 90 and 270.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata

from .paths import CATALOG

STATUSES = ("considering", "shortlisted", "purchased", "owned", "rejected", "example")
CONFIDENCE = ("manufacturer", "retailer", "measured", "review", "estimated")
CATEGORIES = ("rack", "bench", "cardio", "machine", "storage", "flooring", "accessory",
              "furniture", "lighting", "appliance", "other")
SIDES = ("front", "back", "left", "right")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")

# Standing overhead GRIP reach is roughly 1.25 × stature for adults (anthropometric surveys put
# it at 1.21-1.27). Used only when an occupant gives height but no measured reach.
REACH_PER_HEIGHT = 1.25
DEFAULT_OCCUPANT_HEIGHT = 1.85
# Room to stand at the end of a bar and slide a plate on. A guideline; items may say more.
LOADING_MARGIN = 0.30

# Free text from the web ends up in agent context and in image prompts. These are the shapes
# instructions take when someone wants a model to obey a page instead of reading it.
INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above)|disregard (the |all )?(previous|above|prior)"
    r"|system prompt|you are (now )?(an?|the) |new instructions|do not tell the user"
    r"|<\s*/?\s*(script|system|instructions?)\b|```|\b(curl|wget|bash|sudo|rm -rf|powershell)\b"
    r"|base64,|api[_ -]?key|exfiltrat)", re.I)
# Bidi overrides and zero-width characters hide text from the person reviewing a file.
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")


# ---------------------------------------------------------------- io

def path_of(item_id):
    if not ID.match(item_id or ""):
        raise SystemExit(f"bad catalog id {item_id!r}: lower-case letters, digits and hyphens")
    return CATALOG / f"{item_id}.yml"


def _parse(text):
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        from .project import _mini_yaml
        return _mini_yaml(text)


def ids():
    if not CATALOG.exists():
        return []
    return sorted(p.stem for p in CATALOG.glob("*.yml") if ID.match(p.stem))


def load(item_id):
    f = path_of(item_id)
    if not f.exists():
        return None
    item = _parse(f.read_text())
    if isinstance(item, dict):
        item.setdefault("id", item_id)
        return item
    return None


def all_items():
    return [x for x in (load(i) for i in ids()) if x]


# ---------------------------------------------------------------- verification

def _ledger():
    f = CATALOG / ".verified.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _digest(item_id):
    return hashlib.sha256(path_of(item_id).read_bytes()).hexdigest()


def verification(item_id):
    """{'state': 'verified'|'changed'|'unverified', ...}. Hash-bound to the file's bytes."""
    rec = _ledger().get(item_id)
    if not rec:
        return {"state": "unverified"}
    if not path_of(item_id).exists() or rec.get("sha256") != _digest(item_id):
        return dict(rec, state="changed")
    return dict(rec, state="verified")


def verify(item_id, note="", by="client"):
    item = load(item_id)
    if not item:
        raise SystemExit(f"no catalog item {item_id!r}")
    errors, warnings = validate(item)
    if errors:
        raise SystemExit("refusing to verify an item that fails its checks:\n  ✗ "
                         + "\n  ✗ ".join(errors))
    led = _ledger()
    led[item_id] = {"sha256": _digest(item_id), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "by": by, "note": note}
    (CATALOG / ".verified.json").write_text(json.dumps(led, indent=2, sort_keys=True) + "\n")
    return warnings


def unverify(item_id):
    led = _ledger()
    led.pop(item_id, None)
    (CATALOG / ".verified.json").write_text(json.dumps(led, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------- validation

def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _walk_text(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_text(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_text(v, f"{path}[{i}]")


def validate(item):
    """(errors, warnings). Errors make an item unusable; warnings need a person to look."""
    E, W = [], []
    iid = item.get("id", "?")
    if not ID.match(str(iid)):
        E.append(f"id {iid!r} is not a slug")
    if not str(item.get("name", "")).strip():
        E.append("no name")
    if item.get("status", "considering") not in STATUSES:
        E.append(f"status must be one of {', '.join(STATUSES)}")
    if item.get("category") and item["category"] not in CATEGORIES:
        W.append(f"unusual category {item['category']!r} (known: {', '.join(CATEGORIES)})")

    fp = item.get("footprint") or {}
    for k in ("w", "d", "h"):
        v = fp.get(k)
        if not _num(v):
            E.append(f"footprint.{k} missing or not a number (metres)")
        elif not 0.01 <= v <= 8:
            E.append(f"footprint.{k} = {v} m is implausible — is it in inches or millimetres?")
    if fp and not fp.get("source_text"):
        W.append("footprint.source_text is empty — keep the manufacturer's own wording so the "
                 "unit conversion can be checked")

    use = item.get("use") or {}
    cl = use.get("clearance") or {}
    if not cl:
        W.append("use.clearance is empty — the item will be checked for fit but not for use")
    for k, v in cl.items():
        if k not in SIDES:
            E.append(f"use.clearance.{k}: sides are {', '.join(SIDES)}")
        elif not _num(v) or not 0 <= v <= 6:
            E.append(f"use.clearance.{k} must be 0-6 m")
    oh = use.get("overhead") or {}
    for k in oh:
        if k not in ("min_ceiling", "above_reach", "reason"):
            E.append(f"use.overhead.{k}: use min_ceiling or above_reach")
    if "min_ceiling" in oh and not (_num(oh["min_ceiling"]) and 1.5 <= oh["min_ceiling"] <= 6):
        E.append("use.overhead.min_ceiling must be 1.5-6 m")
    if "above_reach" in oh and not (_num(oh["above_reach"]) and -1 <= oh["above_reach"] <= 2):
        E.append("use.overhead.above_reach must be -1 to 2 m")
    for imp in use.get("implements") or []:
        if not (_num(imp.get("length")) and 0.1 <= imp["length"] <= 5):
            E.append(f"implement {imp.get('name', '?')!r} needs a length in metres")
        if imp.get("axis", "width") not in ("width", "depth"):
            E.append(f"implement {imp.get('name', '?')!r}: axis is width or depth")
    if _num(fp.get("w")):
        for side, need in implied_clearance(item).items():
            if (cl.get(side) or 0) + 0.01 < need:
                W.append(f"use.clearance.{side} is {cl.get(side) or 0:.2f} m but the implements "
                         f"need about {need:.2f} m (overhang + {LOADING_MARGIN} m to load)")

    srcs = item.get("sources") or []
    if not srcs:
        E.append("no sources — every dimension must say where it came from")
    for i, s in enumerate(srcs):
        url = str(s.get("url", ""))
        if not url.startswith("https://"):
            E.append(f"sources[{i}].url must be an https:// URL")
        if s.get("confidence") and s["confidence"] not in CONFIDENCE:
            E.append(f"sources[{i}].confidence must be one of {', '.join(CONFIDENCE)}")
        if not s.get("accessed"):
            W.append(f"sources[{i}] has no accessed date")
    if srcs and not any(s.get("confidence") in ("manufacturer", "measured") for s in srcs):
        W.append("no manufacturer or measured source — dimensions are second-hand")
    if item.get("url") and not str(item["url"]).startswith("https://"):
        E.append("url must be https://")

    for where, text in _walk_text(item):
        if INVISIBLE.search(text):
            E.append(f"{where} contains invisible or direction-override characters")
        if len(text) > 4000:
            E.append(f"{where} is {len(text)} characters — too long to be a spec")
        if not where.endswith("url") and INJECTION.search(text):
            W.append(f"{where} reads like an instruction, not a fact — check it was not "
                     f"copied from a page trying to steer an AI: {text[:80]!r}")
    return E, W


def implied_clearance(item):
    """Side clearance that the item's implements force, whatever the file claims."""
    fp = item.get("footprint") or {}
    need = {}
    for imp in (item.get("use") or {}).get("implements") or []:
        if not _num(imp.get("length")):
            continue
        if imp.get("axis", "width") == "width" and _num(fp.get("w")):
            over = max(0.0, (imp["length"] - fp["w"]) / 2) + LOADING_MARGIN
            for s in ("left", "right"):
                need[s] = max(need.get(s, 0), over)
        elif _num(fp.get("d")):
            over = max(0.0, (imp["length"] - fp["d"]) / 2) + LOADING_MARGIN
            for s in ("front", "back"):
                need[s] = max(need.get(s, 0), over)
    return need


# ---------------------------------------------------------------- placement

# Unit vector the item's FRONT points along, per rotation.
_FRONT = {0: (0, 1), 90: (-1, 0), 180: (0, -1), 270: (1, 0)}


def _side_vectors(rotation):
    fx, fy = _FRONT[rotation]
    # Standing in front of the item looking at it, your right hand points along R.
    rx, ry = -fy, fx
    return {"front": (fx, fy), "back": (-fx, -fy), "right": (rx, ry), "left": (-rx, -ry)}


def zones(item_placed, cat):
    """The clearance zones of a placed item, as plan rectangles {side, x, y, w, d}."""
    rot = int(item_placed.get("rotation", 0)) % 360
    cl = dict((cat.get("use") or {}).get("clearance") or {})
    for s, need in implied_clearance(cat).items():
        cl[s] = max(cl.get(s, 0), need)
    x, y, w, d = item_placed["x"], item_placed["y"], item_placed["w"], item_placed["d"]
    out = []
    for side, (vx, vy) in _side_vectors(rot).items():
        c = float(cl.get(side) or 0)
        if c <= 0:
            continue
        if vx > 0:
            out.append({"side": side, "depth": c, "x": x + w, "y": y, "w": c, "d": d})
        elif vx < 0:
            out.append({"side": side, "depth": c, "x": x - c, "y": y, "w": c, "d": d})
        elif vy > 0:
            out.append({"side": side, "depth": c, "x": x, "y": y + d, "w": w, "d": c})
        else:
            out.append({"side": side, "depth": c, "x": x, "y": y - c, "w": w, "d": c})
    return out


def resolve_spec(spec):
    """Fill catalog-placed layout items with real dimensions. Never raises: problems are
    recorded on the item under `_catalog_error` for `design check` to report."""
    plan = ((spec.get("layout") or {}).get("plan")) or []
    for it in plan:
        cid = it.get("catalog")
        if not cid:
            continue
        try:
            cat = load(cid)
        except SystemExit as e:
            it["_catalog_error"] = str(e)
            continue
        if not cat:
            it["_catalog_error"] = f"catalog item {cid!r} not found in {CATALOG}"
            it.setdefault("w", 0.5), it.setdefault("d", 0.5)
            continue
        rot = int(it.get("rotation", 0)) % 360
        if rot not in _FRONT:
            it["_catalog_error"] = f"rotation {it.get('rotation')} must be 0, 90, 180 or 270"
            rot = 0
        fp = cat.get("footprint") or {}
        w, d = (fp.get("d"), fp.get("w")) if rot in (90, 270) else (fp.get("w"), fp.get("d"))
        if not (_num(w) and _num(d)):
            it["_catalog_error"] = f"catalog item {cid!r} has no usable footprint"
            continue
        for k, v in (("w", w), ("d", d)):
            if k in it and abs(float(it[k]) - v) > 0.02:
                it["_catalog_error"] = (f"'{it.get('label', cid)}' says {k}={it[k]} but catalog "
                                        f"{cid!r} is {v:.3f} m — remove w/d and let the catalog "
                                        f"decide")
            it[k] = v
        it.setdefault("h", fp.get("h", 0.45))
        it.setdefault("label", cat.get("name", cid))
        it["_zones"] = zones(it, cat)
        it["_catalog"] = {"id": cid, "name": cat.get("name", cid),
                          "status": cat.get("status", "considering"),
                          "verification": verification(cid)["state"],
                          "overhead": (cat.get("use") or {}).get("overhead") or {},
                          "tilt_up": bool((cat.get("assembly") or {}).get("tilt_up")),
                          "footprint": fp}
    return spec


# ---------------------------------------------------------------- checks

def _overlap(a, b, tol=0.02):
    return (min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]) > tol and
            min(a["y"] + a["d"], b["y"] + b["d"]) - max(a["y"], b["y"]) > tol)


def _inside(room, pt):
    """Point-in-polygon (ray cast) against the room outline."""
    x, y = pt
    poly = room.outline()
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def rect_in_room(room, r, tol=0.01):
    xs = (r["x"] + tol, r["x"] + r["w"] - tol)
    ys = (r["y"] + tol, r["y"] + r["d"] - tol)
    if not all(_inside(room, (x, y)) for x in xs for y in ys):
        return False
    # A rectilinear outline can still poke into the rectangle (a chimney breast between two
    # corners that are both in the room), so no outline vertex may lie strictly inside it.
    return not any(xs[0] < px < xs[1] and ys[0] < py < ys[1] for px, py in room.outline())


def door_swings(room):
    """Plan rectangles swept by each door leaf, inward."""
    out = []
    for o in room.openings:
        if o.type != "door":
            continue
        a, b = room.opening_plan_segment(o)
        nx, ny = room.wall(o.wall).inward
        pts = [a, b, (a[0] + nx * o.width, a[1] + ny * o.width), (b[0] + nx * o.width, b[1] + ny * o.width)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out.append((o.tag, {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "d": max(ys) - min(ys)}))
    return out


def occupant_reach(project):
    occ = project.get("brief.occupants") or []
    reaches = []
    for o in occ:
        if _num(o.get("reach_m")):
            reaches.append(o["reach_m"])
        elif _num(o.get("height_m")):
            reaches.append(o["height_m"] * REACH_PER_HEIGHT)
    if reaches:
        return max(reaches), "brief.occupants"
    return DEFAULT_OCCUPANT_HEIGHT * REACH_PER_HEIGHT, \
        f"no brief.occupants, assuming a {DEFAULT_OCCUPANT_HEIGHT} m user"


def check_layout(project, room, spec):
    """(errors, warnings) for every catalog-placed item in one direction."""
    E, W = [], []
    sid = spec.get("id", "?")
    plan = ((spec.get("layout") or {}).get("plan")) or []
    swings = door_swings(room)
    reach, reach_why = occupant_reach(project)
    for it in plan:
        lbl = it.get("label", it.get("catalog", "?"))
        if it.get("_catalog_error"):
            E.append(f"{sid}: {it['_catalog_error']}")
        meta = it.get("_catalog")
        if not meta:
            continue
        if meta["verification"] != "verified":
            W.append(f"{sid}: '{lbl}' uses catalog item {meta['id']!r}, which is "
                     f"{meta['verification']} — renders are refused until: "
                     f"design catalog verify {meta['id']}")
        if meta["status"] == "rejected":
            W.append(f"{sid}: '{lbl}' is placed but {meta['id']!r} is marked rejected")
        if not rect_in_room(room, it):
            E.append(f"{sid}: '{lbl}' footprint does not fit inside the room outline")
        for z in it.get("_zones", []):
            if not rect_in_room(room, z):
                E.append(f"{sid}: '{lbl}' needs {z['depth']:.2f} m clear at its {z['side']} "
                         f"and that runs into a wall — it cannot be used where it stands")
        for tag, sw in swings:
            if _overlap(it, sw):
                E.append(f"{sid}: '{lbl}' stands in the swing of door {tag}")
            elif any(_overlap(z, sw) for z in it.get("_zones", [])):
                W.append(f"{sid}: door {tag} opens into the clearance of '{lbl}' — someone "
                         f"walking in meets a person mid-lift")
        for j, other in enumerate(plan):
            if other is it or other.get("z") or other.get("inside"):
                continue
            for z in it.get("_zones", []):
                if _overlap(z, other):
                    E.append(f"{sid}: '{other.get('label', '?')}' sits in the {z['side']} "
                             f"clearance of '{lbl}'")
            if other.get("_catalog") and j > plan.index(it):
                shared = [z["side"] for z in it.get("_zones", [])
                          if any(_overlap(z, oz) for oz in other.get("_zones", []))]
                if shared:
                    W.append(f"{sid}: '{lbl}' and '{other.get('label', '?')}' share clearance "
                             f"({', '.join(shared)}) — fine only if never used at the same time")
        h = meta["footprint"].get("h")
        if _num(h) and h > room.ceiling_height - 0.01:
            E.append(f"{sid}: '{lbl}' is {h:.2f} m tall; the ceiling is {room.ceiling_height:.2f} m")
        oh = meta["overhead"]
        if _num(oh.get("min_ceiling")) and oh["min_ceiling"] > room.ceiling_height:
            E.append(f"{sid}: '{lbl}' needs a {oh['min_ceiling']:.2f} m ceiling to use; the room "
                     f"has {room.ceiling_height:.2f} m")
        if _num(oh.get("above_reach")):
            need = reach + oh["above_reach"]
            if need > room.ceiling_height:
                E.append(f"{sid}: '{lbl}' needs {need:.2f} m overhead in use "
                         f"(reach {reach:.2f} m + {oh['above_reach']:.2f} m; {reach_why}); the "
                         f"ceiling is {room.ceiling_height:.2f} m")
        fp = meta["footprint"]
        if meta["tilt_up"] and _num(fp.get("h")) and _num(fp.get("d")):
            diag = math.hypot(fp["h"], min(fp["d"], fp.get("w") or fp["d"]))
            if diag > room.ceiling_height:
                W.append(f"{sid}: '{lbl}' is assembled lying down and needs {diag:.2f} m to tilt "
                         f"up; the ceiling is {room.ceiling_height:.2f} m — assemble it upright")
    return E, W


# ---------------------------------------------------------------- prompts

def clean(text, limit=600):
    """Untrusted free text, made safe to quote inside a prompt: no control or invisible
    characters, no fences, bounded length."""
    s = unicodedata.normalize("NFKC", str(text))
    s = INVISIBLE.sub("", s)
    s = "".join(ch if ch.isprintable() or ch == " " else " " for ch in s)
    s = s.replace("```", "'''")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def prompt_block(spec):
    items = [it for it in ((spec.get("layout") or {}).get("plan")) or [] if it.get("_catalog")]
    if not items:
        return ""
    out = ["EQUIPMENT AT TRUE SCALE — each item below is a real product at its real size. Draw it "
           "exactly that big relative to the room and the people in it; never shrink it to fit:"]
    for it in items:
        m = it["_catalog"]
        fp = m["footprint"]
        out.append(f"  · {clean(m['name'], 120)}: {fp.get('w', 0)*1000:.0f} mm wide × "
                   f"{fp.get('d', 0)*1000:.0f} mm deep × {fp.get('h', 0)*1000:.0f} mm tall, at the "
                   f"position shown on the measured plan.")
        zs = it.get("_zones") or []
        if zs:
            out.append("    The floor in front of and beside it is kept clear for use ("
                       + ", ".join(f"{z['side']} {z['depth']:.2f} m" for z in zs)
                       + "); nothing stands there.")
    return "\n".join(out)

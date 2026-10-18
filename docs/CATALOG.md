---
title: "The equipment and furniture catalog — Roomsmith"
description: "Track the equipment you are considering, with researched dimensions and the clearance needed to use it, and prove a squat rack, treadmill or sofa fits AND works in a real room."
---

# The equipment and furniture catalog

A catalog item is what the room model needs to know to put a real product in a real room **and
prove it can be used there**. A spec sheet gives you the box. Using a squat rack needs the box plus
a walk-out, a 2.2 m bar sticking out of both sides, and enough ceiling to press overhead.

```bash
design catalog list                    # ✓ verified   ! changed since verified   · not verified
design catalog show rogue-rml-390f
design catalog check rogue-rml-390f    # schema, units, sources, injected text
design catalog verify rogue-rml-390f   # you confirm the numbers — renders refuse until then
design catalog new my-bench            # start one by hand from the template
```

## Ingesting something

Tell Claude what you're looking at — *"we're thinking about the Rogue RML-390F"*, or paste a
link. The `catalog-researcher` agent finds the manufacturer's figures plus an independent source,
converts units while keeping the original wording, and researches the **use envelope**. Then:

1. `design catalog check <id>` — must pass
2. read the sources and the numbers (or open the Catalog tab in `design serve`)
3. `design catalog verify <id>`

Verification records a hash of the file. Edit the file afterwards — by hand or by an agent — and
it reads `changed` and is refused by `render` until verified again. Nothing can alter a verified
item silently.

## What an item records

`config/catalog-item.yml` is the annotated template; `catalog/rogue-rml-390f.yml` is a worked
example. All lengths in metres.

| Field | Purpose |
|---|---|
| `footprint: {w, d, h, source_text}` | Assembled size. `w` is side to side as you face the front. `source_text` keeps the manufacturer's words so the conversion can be checked |
| `use.clearance: {front, back, left, right}` | Floor that must stay clear to USE it — a rack's walk-out, a treadmill's belt run-off, a rower's handle travel |
| `use.implements` | Things longer than the item: `{name: Olympic barbell, length: 2.20, axis: width}`. Side clearance is derived from these whatever `clearance` says: overhang + 0.30 m to load plates |
| `use.overhead` | `above_reach` (margin above the tallest occupant's overhead reach) or `min_ceiling` |
| `assembly.tilt_up` | Built lying down and stood up — needs √(h² + d²) of headroom |
| `mounting`, `power`, `floor`, `weight_kg` | Bolting, circuits, point loads |
| `sources` | Every number's origin, with `confidence`: manufacturer · retailer · measured · review · estimated |
| `status` | considering · shortlisted · purchased · owned · rejected |

## Using one in a design

A direction places a catalog item by id. Its size comes from the catalog, never from the spec:

```json
{"label": "Power rack", "catalog": "rogue-rml-390f", "x": 0.9, "y": 1.0, "rotation": 270}
```

`rotation` is the way its front faces in plan: `0` = +y, `90` = −x, `180` = −y, `270` = +x.
The plan draws each clearance zone as a dashed, labelled area.

`design check` then reports:

| Error | Warning |
|---|---|
| footprint outside the room outline | item not verified (render refuses) |
| a clearance zone runs into a wall | a door opens into a clearance zone |
| something else stands in a clearance zone | two items share clearance |
| the item stands in a door's swing | needs more height to tilt up than the ceiling allows |
| taller than the ceiling | item marked `rejected` |
| overhead use needs more than the ceiling | |
| the spec gives a `w`/`d` that contradicts the catalog | |

## Who is using it

Overhead checks need the people. In `project.yml`:

```yaml
brief:
  occupants:
    - {name: "Martin", height_m: 1.83}
    - {name: "Sam", height_m: 1.68, reach_m: 2.10}   # measured reach beats the estimate
```

Reach is estimated as 1.25 × height when not measured. With no occupants a 1.85 m user is assumed
and the check says so.

## Renders

Each catalog item is described to the image model at its true size, with its clearance stated as
kept clear, in a block generated from the catalog. The critic fails a render that shrinks a rack
or puts something in its walk-out.

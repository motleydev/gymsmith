---
title: "Projects, rooms and revisions — Roomsmith"
description: "Organise design work as projects that hold rooms, and rooms that hold revisions you can flip between without losing anything."
---

# Projects, rooms and revisions

```
project   a site — a house, a flat, a client              house
  room    one space in it                                 house/garage
    rev   one version of the design for that room         house/garage@r2   ← HEAD
```

```
projects/house/
  workspace.yml
  rooms/garage/
    HEAD                    r2
    refs/                   photos + annotations, shared by every revision
    revisions/
      r1/  REVISION.json  project.yml  STATE.json  brief/  directions/  drawings/  renders/  report/
      r2/  …
```

A revision is an ordinary job directory, so every command works on it unchanged. Photos live at
**room** level because they are of the physical room, which does not change when the design does.

## Commands

```bash
design init house/garage            # a project, a room, revision r1 — and make it the default
design init house/office --from room
design rooms                        # everything; * marks the default, [r2] marks HEAD
design use house/office             # make another room the default
design status --project house/garage@r1     # any command, any revision
```

```bash
design rev new --note "rack on the far wall"     # copy sources from HEAD into r2, make it HEAD
design rev new r1 --note "back to the original"  # branch from a specific revision
design rev switch r1                             # flip HEAD back. Nothing is lost
design rev diff                                  # HEAD against its parent
design rev diff r1..r3
design rev list
```

`design serve` shows each revision's renders and lets you **flip between two in place**
(the space bar toggles) — the quickest way to compare a rack against the wall with the same rack
in the corner.

## What a new revision copies

| Copied | Not copied | Why |
|---|---|---|
| `project.yml`, `brief/`, `directions/` | `drawings/`, `renders/`, `report/` | outputs regenerate from the sources |
| the `brief` approval | every other approval | a revision exists because something is changing, so decisions that rested on the old one are taken again. `--keep-approvals` overrides |

## Single-room projects

The older flat layout — `projects/<slug>/project.yml` — still works, addressed as just `<slug>`.
It has no revisions. `design init <slug>` (no slash) still creates one.

## Addresses

`--project` accepts `house`, `house/garage` or `house/garage@r2`. A project with exactly one room
can be named alone. Addresses are validated before they touch the filesystem; nothing can climb
out of `projects/`.

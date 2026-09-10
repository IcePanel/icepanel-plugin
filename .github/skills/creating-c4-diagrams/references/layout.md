# Diagram layout

IcePanel has no auto-layout. Every object needs an explicit `x`/`y`, and the result is only as readable as the placement you choose. Sizes and line routing are handled for you; **placement is the whole job**. This file covers the grid, boundaries, line routing, and the spec format the helper script consumes.

## Contents

- [Grid and sizing](#grid-and-sizing)
- [Reading order](#reading-order)
- [Boundary areas](#boundary-areas)
- [Line routing](#line-routing)
- [Diagram spec format](#diagram-spec-format)

## Grid and sizing

**`width` and `height` are optional — don't send them.** IcePanel applies its default box size, **256 × 128**. Send a size only when a box genuinely needs to be off-default; the numbers below assume the default, so an odd-sized box means doing the pitch maths yourself around it.

Lay boxes out on a fixed pitch — the step from one box's top-left corner to the next, not the gap between them. Positions are then multiples of one number, so rows stay aligned:

- horizontal pitch **384** = 256 box + 128 gutter → x = 0, 384, 768, …
- vertical pitch **320** = 128 box + 192 gutter → y = 0, 320, 640, …

The vertical gutter is larger because it holds the connection labels, which IcePanel draws on the line. Short names (see the naming rule in `SKILL.md`) fit this pitch comfortably. Too little room and a label collides with the box below or with a parallel connection's label, which is the most common way these diagrams turn unreadable. The API won't catch it: the request validates and the picture is still a mess.

If a name has to run long, increase the vertical pitch rather than shortening the gutter's job. Wider columns buy no label room; taller rows do.

Coordinates increase right and down. Keep the top-left of the diagram at or near `(0, 0)`; there's no need for negative coordinates, and starting at the origin makes rows easier to reason about.

Centre a row under the one above by matching centres, not left edges. A row of `n` boxes starting at `x0` spans `n * 384 - 128`, so its centre is `x0 + (n * 384 - 128) / 2`.

## Reading order

C4 diagrams read top-down: who initiates at the top, the thing being described in the middle, what it depends on at the bottom.

- **L1** — actors across the top, the system in the middle, external systems along the bottom.
- **L2** — actors above the boundary, containers inside it arranged along the request path, external systems below.
- **L3** — the entry-point component at the top, the components it delegates to below, external objects below that.

Arrange each row so connections run roughly straight down. Crossed lines almost always mean two boxes in a row are in the wrong order. Reorder the row before reaching for a different line shape.

## Boundary areas

`shape: "area"` draws a bounding box around children. The system boundary on an L2, the container boundary on an L3, or a group. Everything else is `shape: "box"`.

**Areas carry no size at all** — omit `width` and `height`. IcePanel grows the boundary itself to fit whichever children are on the diagram, plus room for its own title. Hand-computed extents only go stale the moment you move a box. The helper script drops `w`/`h` on an area, so give it `x` and `y` only.

Set `x`/`y` to the top-left corner of the children it wraps: for children spanning `x0..x1` and `y0..y1`, that's `x0, y0`.

An area uses the same `modelId` as the object it represents — the L2 boundary of a system carries that system's ID, while that same system may appear as a plain box on the L1.

Keep objects that live outside the boundary (actors, external systems) clear of it, with a full gutter of space.

## Line routing

**Send only `originId` and `targetId`.** IcePanel picks which edge and anchor each line attaches to, its shape, and where the label sits, all from the geometry — so `originConnector`, `targetConnector`, `lineShape` and `labelPosition` are optional and normally omitted. There is no anchor-spreading work to do.

That puts the whole burden on placement. The routing is only as good as the positions it is given, so the way to fix ugly lines is to move boxes, not to reach for an override.

First check you are fixing the right problem: if reordering only moves the crossings elsewhere, the diagram is overloaded rather than misplaced — cut connections or split it (*A diagram tells one story* in `SKILL.md`). Once the content is right:

- **Crossed lines mean two boxes in a row are in the wrong order.** Reorder the row so each line runs roughly straight down to its target.
- **A line cutting through an unrelated box** means the corridor between rows is blocked. Shift the box out of the way, or move the target to a column with a clear run.
- **Many lines converging on one box** read best when its callers sit in the row directly above it, spread across the columns either side of it rather than stacked in one column.

If a specific line still needs a different attachment point, the override fields are still accepted — anchors are the 12 points listed in `references/api.md`. Treat that as a last resort on a diagram you've already placed well.

## Diagram spec format

The helper script takes a spec and handles ID resolution, validation and posting. Write placement; let it do the mechanical part.

`ref` fields accept your import IDs (resolved via `idmap.json`), raw IcePanel IDs, or `@root` for the domain root.

```json
{
  "name": "Enterprise Agent Platform - Apps",
  "type": "app-diagram",
  "modelId": "s-aip",
  "index": 1,
  "description": "The applications and data store inside the platform.",
  "objects": [
    { "ref": "s-aip", "shape": "area", "x": 192, "y": 400 },
    { "ref": "a-finance", "x": 128, "y": 0 },
    { "ref": "app-api-gateway", "x": 192, "y": 400 },
    { "ref": "store-governance", "x": 576, "y": 1040 }
  ],
  "connections": [
    { "ref": "conn-finance-gateway", "from": "a-finance", "to": "app-api-gateway" },
    { "ref": "conn-gateway-runtime", "from": "app-api-gateway", "to": "app-agent-runtime" }
  ]
}
```

Note how little each entry carries: a `ref` and a position. `type` is looked up from the model, and sizes are left to IcePanel — pass `w`/`h` only for a deliberately off-default box, and never on an area. Connections need only `ref`, `from` and `to`; `lineShape`, `labelPosition`, `originConnector` and `targetConnector` are accepted as overrides but are otherwise left out so IcePanel routes the line.

Every object referenced by a connection must also appear in `objects`, since a diagram can only draw what it shows.

---
name: translating-context-maps
description: Turn an image or sketch of a DDD context map into IcePanel model objects and connections. Bounded contexts as groups, upstream/downstream relationships as connections, and the context map patterns (OHS, ACL, CF, SK, PL, C/S, Partnership) as tags. Use whenever the user supplies a photo, screenshot, whiteboard shot, Miro or draw.io export of a context map, or otherwise describes bounded contexts and their relationships, and wants it in IcePanel.
---

# Translating context maps into IcePanel

A DDD context map records **bounded contexts and how their teams and models relate**. IcePanel holds a C4 model. The two describe the same landscape at different angles, so a step by step translation is required to get the map into IcePanel.

This skill covers that translation only: from an image or sketch to a validated import file. **Importing it and drawing the diagrams belong to** `creating-c4-diagrams`. Hand off once the file is written and don't reimplement any of it.

Two rules from that skill are deliberately overridden here. Both are explained where they come up:

- Connections are authored **upstream → downstream** (model influence), not from the initiator.
- Bounded contexts become a `group` **plus a** `system`, not a bare `system`.



## Order of work

1. Read the map and extract every context, line and marker (*Step 1*).
2. Confirm the reading with the user before writing anything (*Step 2*).
3. Build objects (*Step 3*), connections (*Step 4*) and tags (*Step 5*).
4. Hand the file to `creating-c4-diagrams` (*Step 6*).



## Step 1: Read the image/sketch

Read `references/notation.md` first. It has the ddd-crew symbol set including line styles, `U`/`D` letters, the pattern markers, and the specific ways a sketch misleads you.

Work through the image in a fixed order rather than describing what jumps out:

1. **Every context.** Circles and boxes with names. A cloud is a big ball of mud, which is also a bounded context.
2. **Every line**, one at a time. For each: the two contexts it joins, its style (thick, thin, dotted), any `U`/`D` letters and which end each sits at, and any label on the line itself.
3. **Every marker.** The small rectangular boxes — `OHS`, `PL`, `CF`, `ACL`, `SK`, `SW`. For each, record **which end of the line it sits at**. That is the whole meaning of the marker and the easiest thing to lose.
4. **Anything you couldn't read.** Blurred text, an ambiguous line end, a marker you can't place. Keep the list; it goes to the user in Step 2.

Build a table as you go, one row per line. This is what you confirm and what you translate from:


| From   | To       | Style      | U/D                  | Markers (which end)          | Line label |
| ------ | -------- | ---------- | -------------------- | ---------------------------- | ---------- |
| Orders | Shipping | thin solid | Orders=U, Shipping=D | OHS @ Orders, ACL @ Shipping | —          |


**Don't infer relationships that aren't drawn.** A context map is deliberately sparse. Two contexts with no line between them are making a statement. Adding the arrow you'd expect from experience quietly replaces the user's map with your own.

## Step 2: Confirm with the user

An image read is a hypothesis. Show the user the context list and the relationship table from Step 1, name anything you couldn't make out, and get a correction pass before building the file.

Ask for one more thing in the same message: **a one-line purpose for each context.** A sketch gives you names and nothing else, and every IcePanel object wants a `caption` and a `description`. Inventing them from a context called "Fulfilment" produces confident fiction, which is worse than a gap. Ask, and use what you're given.

## Step 3: Build the JSON

A bounded context is a boundary around a model, not a deployable, so it doesn't map cleanly onto any single C4 abstraction. Model it as **a** `group` with a single `system` inside:

```json
{ "id": "g-orders", "name": "Orders BC", "type": "group", "parentId": "d-commerce",
  "caption": "Bounded context",
  "description": "The Orders bounded context, from the context map." },

{ "id": "s-orders", "name": "Orders", "type": "system", "parentId": "d-commerce",
  "groupIds": ["g-orders"],
  "caption": "Order capture and lifecycle",
  "description": "Captures orders and owns their lifecycle through to fulfilment." }
```

**The group and the system cannot share a name.** Both are children of the same domain, and IcePanel rejects duplicate names among siblings. Suffix the group with `BC` and leave the system holding the map's own name, so the name a reader sees on the box is the name that was on the sketch.

**Groups sit outside the C4 hierarchy.** The system's `parentId` is the *domain*, and it joins the group through `groupIds`. A group is never a `parentId`. Membership is many-to-many, so a context that grows to several systems later is one more entry in `groupIds`, never a re-parent.

That is the point of the extra object. The group is the flexible boundary, the system inside it is a sensible default that the user can split into several as the real architecture surfaces.

Set `external: true` on the system where the context is somebody else's like a SaaS provider, a partner's platform. The group still represents the boundary.

### Big Ball of Mud

A cloud on a context map is a Big Ball of Mud: a region of the landscape that is *not* a well-defined bounded context. Model it exactly like one anyway, a `group` named `<Name> BC` with the `system` inside carrying the plain name.

Two things differ:

- Per the mapping below, `BBoM` **gets no tag.** Say what it is in the `description` instead.
- **Expect it to have no connections.** Drawing a Big Ball of Mud is a statement that its model must not propagate, so a well-drawn map usually leaves it unattached. Model the boundary and author nothing. Where the map *does* draw a relationship to it, which is common and normally has an `ACL` on the other end shielding a real context, author that connection like any other.



## Step 4: Relationships become connections

**Author every connection from upstream to downstream.** On a context map the relationship being drawn is *model influence*: the upstream context's model shapes the downstream one's. The name reads across the arrow as `Orders · Upstream of · Shipping`.

This inverts the rule in `creating-c4-diagrams`, which authors from whoever initiates the call. It has to, because the two usually disagree, the downstream context is normally the one calling the upstream's API, so the runtime arrow points *back* up the influence arrow. Here, influence wins. Say so when handing the model over, because a reader who knows the sibling skill will expect the other convention.


| On the map                       | Connection                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------------- |
| Thin solid, `U`/`D` at the ends  | `outgoing`, origin = `U`, target = `D`, name **"Upstream of"**                        |
| Thick solid (mutually dependent) | `bidirectional`, name **"Mutually dependent"**                                        |
| Labelled `Partnership`           | `bidirectional`, name **"Partnership"**                                               |
| `CUS --> SUP`                    | `outgoing`, origin = **supplier**, target = **customer**, name "Supplier upstream of" |
| Dotted, or labelled `Free`       | nothing — author no connection                                                        |
| Dotted with `SW` (Separate Ways) | nothing — author no connection                                                        |


Two of those rows are where this goes wrong:

**Customer/Supplier runs against its own arrowhead.** The map draws `CUS --> SUP` pointing from customer to supplier, because that arrow is about whose priorities influence whose planning. The `U`/`D` letters underneath tell the other story: the supplier is upstream. Model influence flows supplier → customer, so the connection is authored **supplier → customer**, opposite to the drawn arrowhead. Transcribe arrowheads and every C/S pair in the model ends up backwards.

**Separate Ways and Free mean silence.** They are assertions that no relationship exists. A connection here, even one named "Separate ways", states the opposite of the map.

**Connect the Groups, not the Systems.** `originId` and `targetId` take the `g-` ids. A context map relationship holds between two *bounded contexts*, and the group is what represents a bounded context here. The system inside it is only a placeholder for whatever containers turn up later. Author it on the group and the relationship survives that context being split into three systems.

```json
{ "id": "conn-orders-shipping", "name": "Upstream of", "direction": "outgoing",
  "originId": "g-orders", "targetId": "g-shipping",
  "tagIds": ["tag-ohs", "tag-acl"],
  "description": "Orders publishes an open host service; Shipping consumes it behind an anticorruption layer." }
```

IcePanel accepts connections between `group` objects. Groups are model objects like any other, even though they sit outside the C4 hierarchy. Every `originId`/`targetId` in the file should be a `g-` id; an `s-` id in a connection is the mistake this note exists to prevent.

## Step 5: Patterns become tags

Every pattern marker becomes a **tag on the connection**, never on an object. Create the tag group and its tags in the same import file:

```json
"tagGroups": [
  { "id": "tg-context-map-patterns", "name": "Context Map Patterns", "icon": "star" }
],
"tags": [
  { "id": "tag-ohs",         "name": "OHS",         "color": "blue",   "groupId": "tg-context-map-patterns" },
  { "id": "tag-pl",          "name": "PL",          "color": "green",  "groupId": "tg-context-map-patterns" },
  { "id": "tag-acl",         "name": "ACL",         "color": "orange", "groupId": "tg-context-map-patterns" },
  { "id": "tag-cf",          "name": "CF",          "color": "red",    "groupId": "tg-context-map-patterns" },
  { "id": "tag-sk",          "name": "SK",          "color": "purple", "groupId": "tg-context-map-patterns" },
  { "id": "tag-cs",          "name": "C/S",         "color": "beaver", "groupId": "tg-context-map-patterns" },
  { "id": "tag-partnership", "name": "Partnership", "color": "pink",   "groupId": "tg-context-map-patterns" }
]
```

`icon` is required on a tag group, and it takes a **named icon string**. Send `star` and leave it alone. A tag group carries no meaning in its icon.

**One colour per pattern, all seven different**, so a connection carrying two or three tags stays readable at a glance. The colours mean nothing beyond telling the patterns apart. Use these values as they stand rather than reassigning them per landscape, so a tag looks the same in every model. The full set IcePanel accepts is in `creating-c4-diagrams` `references/api.md`; `white` is not a sensible choice on a light canvas.

**Combinations are separate tags.** An `OHS + PL` marker is `tag-ohs` and `tag-pl` on the same connection, not a combined label.

### Why moving markers onto the line loses nothing

A marker on the map belongs to *one end* of it, and tagging the connection appears to throw that away. It doesn't, because ownership is fixed by the pattern:

- `OHS` and `PL` are always **upstream** — the origin.
- `ACL` and `CF` are always **downstream** — the target.
- `SK`, `C/S` and `Partnership` describe the relationship itself.

Since connections run upstream → downstream, a connection tagged `OHS` and `ACL` unambiguously reads: the origin publishes a host service, the target wraps it in an anticorruption layer. The end is always recoverable.

### Two consequences to expect

**One marker can become several tags.** A context publishing one `OHS` to three downstream contexts has one box on the map and three connections in the model, each tagged `OHS`. That's correct, each of those relationships really does run through that host service, but the count won't match the sketch, so say so rather than letting it look like a bug.

**A marker with no line attached is dropped.** A context drawn with an `OHS` and no relationship going anywhere has nothing to tag. Tell the user which markers fell out this way, don't manufacture a connection to hold one.

## Step 6: Hand off

Write the file, then stop and pass it to `creating-c4-diagrams`, which owns import, ID mapping, diagrams and verification. Don't duplicate that work here.

Set `"namespace": "context-map"` so a later re-read of the same map upserts rather than duplicates, and use stable slugs, `g-orders`, `s-orders`, `conn-orders-shipping` since they are the join key on every future run.

Tell the user, in the handoff:

- What you dropped and why — Separate Ways and Free relationships, unattached markers, anything unreadable.
- That connections run **upstream → downstream** by model influence, not by who calls whom.
- That every connection is named "Upstream of", and you can refine the names now that it's visible.

On the diagrams that follow, each bounded-context group is drawn with `shape: "area"` wrapping its system, so the L1 context diagram shows the map's own boundaries. Since the connections are authored on the groups, the L1's `from`/`to` are those same groups each relationship runs area to area.

## Reference

- `references/notation.md` — the ddd-crew symbol set, and how sketches mislead
- `references/example.md` — a worked translation: map, confirmation table, import file
- `creating-c4-diagrams` — the sibling skill that imports the file and draws the diagrams


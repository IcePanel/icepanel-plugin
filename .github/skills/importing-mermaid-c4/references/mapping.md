# Mermaid C4 to IcePanel mapping

Every rule the parser applies, and why. Read this before interpreting `report.md`
or hand-editing `model.json`.

## Contents

- [Elements](#elements)
- [Boundaries](#boundaries)
- [Hierarchy and the gaps Mermaid leaves](#hierarchy-and-the-gaps-mermaid-leaves)
- [Relationships](#relationships)
- [Text fields](#text-fields)
- [Diagrams](#diagrams)
- [Six ways a literal reading goes wrong](#six-ways-a-literal-reading-goes-wrong)

## Elements

| Mermaid | IcePanel `type` | Notes |
| --- | --- | --- |
| `Person`, `Person_Ext` | `actor` | Parent is the domain |
| `System`, `System_Ext` | `system` | Parent is the domain |
| `SystemDb`, `SystemQueue` (+`_Ext`) | `system` | The shape has no equivalent and is treated as a system |
| `Container`, `Container_Ext` | `app` | A runtime boundary: individually runnable and deployable |
| `ContainerDb` (+`_Ext`) | `store` | |
| `ContainerQueue` (+`_Ext`) | `store` | A broker is deployable, but it is on the diagram for holding data |
| `Component`, `ComponentDb`, `ComponentQueue` (+`_Ext`) | `component` | All three flatten; parent is an `app` or `store` |
| `Deployment_Node`, `Node`, `Node_L`, `Node_R` | `group` | Nests through `parentId`; members join via `groupIds` |

Any keyword ending `_Ext` sets `external: true`. `Node_L` and `Node_R` differ from
`Node` only in alignment, which is layout, so all three are the same object.

## Boundaries

**A boundary's type comes from what it contains, not from which keyword was used.**
The same keyword means different things at different levels, `Container_Boundary`
wraps containers in a `C4Container` block, making it a *system*, and wraps
components in a `C4Component` block, making it an *app*. Mermaid's own reference
docs do exactly this with the same object.

| Contents | IcePanel `type` |
| --- | --- |
| Containers (`Container`, `ContainerDb`, `ContainerQueue`) | `system` |
| Components | `app`, or `store` if that alias is declared `ContainerDb`/`ContainerQueue` elsewhere |
| Systems, actors, or other boundaries | `group` |
| Nothing | `group` |

Two keywords override the contents rule:

- **`Deployment_Node` and its aliases are always a `group`**, whatever they hold.
- **The outermost `Enterprise_Boundary` is the `domain`.** A nested one is a `group`,
  because domains cannot nest in IcePanel.

Being a boundary is also **per diagram, not per object**. An app is the boundary on
the component diagram that opens it up and an ordinary box on the container diagram
above, which shows none of its components. The parser decides this per block, by
whether any of the object's children appear in that block.

## Hierarchy and the gaps Mermaid leaves

IcePanel needs a full chain: `domain` → `actor` | `system` | `group`, then
`system` → `app` | `store`, then `app` | `store` → `component`. A `group` parents only
another `group`.

Four things in that chain are never stated in Mermaid, and each has a rule:

**The domain.** Taken from the outermost `Enterprise_Boundary`. Failing that, from the
subject of the first `title`, "Container diagram for Internet Banking System" gives
"Internet Banking System", since the diagram-type wrapper is not a domain name.
Failing that, `--domain` is required. A domain object must exist in the import file
regardless, because `parentId` resolves against that file alone.

**A parent system for containers.** Common in `C4Component` blocks and universal in
`C4Deployment`, which never names a system at all. The parser invents one, named from
the **outermost enclosing deployment node** so related containers share it. A node
called "Big Bank plc" yields a system "Big Bank plc System". With no node to derive
from, everything unparented lands in one placeholder called "Unassigned Containers".
Every placeholder is reported; rename them before they reach the model.

**Group membership.** A group's own `parentId` is a domain or another group. Its
members — apps, stores, systems and actors alike — keep their real `parentId` and join
through **`groupIds`**, which lists *every* enclosing group, inner and outer both. A
group's area on a diagram is sized around the members it can see there, so an object
naming only the inner group would leave the outer boundary empty.

**Unique names.** IcePanel requires names to be unique **across the whole domain**, not
just among siblings, and Mermaid enforces nothing, its deployment example has two
containers both plainly named "Database". A clash is suffixed with the boundary a
reader would use to tell them apart, preferring the innermost enclosing group:
"Database (Oracle - Primary)" and "Database (Oracle - Secondary)".

## Relationships

| Mermaid | IcePanel |
| --- | --- |
| `Rel(from, to, label, ?techn, ?descr)` | `direction: outgoing`, origin `from`, target `to` |
| `BiRel` | `direction: bidirectional` |
| `Rel_U`/`Rel_D`/`Rel_L`/`Rel_R` (and `_Up`/`_Down`/`_Left`/`_Right`) | Ordinary `outgoing`. The suffix is a layout hint, kept for placement and dropped from the model |
| `Rel_Back(a, b, label)` | **Origin `b`, target `a`** — it renders `a <-- b`, so the relationship runs `b → a` |
| `RelIndex(index, ...)` | Ordinary `outgoing`; the step number is dropped, since flows are out of scope |
| `?techn` | `technologyIds` on the connection, after a catalog lookup |
| `?descr` | `description` |

Mermaid's usual direction is initiator to receiver, which is also IcePanel's
convention, so no inversion is needed. `Rel_Back` is the exception, and it is the
single most dangerous statement in the syntax. See below.

### One relationship stated at two levels

Merged blocks often state the same relationship at different altitudes:
`Rel(customerA, SystemAA, "Uses")` in the context block and
`Rel(customer, web_app, "Uses", "HTTPS")` in the container block, where `web_app` is a
child of `SystemAA`.

If the labels match and one pair is the other opened up (`web_app` inside
`SystemAA`), that is **one relationship seen from two heights**, so it becomes
one model connection. That only holds when there is a single such pair. Three
`Uses` from the same customer to three containers are three relationships that
happen to share a word; they stay three.

It is authored at the **shallowest** pair, because a label in that register
belongs to the level it was written for. "Uses" is a business phrase and belongs
on the L1. Each block's diagram still draws it against the objects visible there:
`originId`/`targetId` are the objects on that diagram, `modelId` is the one shared
connection. That is exactly how IcePanel's connection inheritance is meant to work.

Where the labels genuinely differ, they stay two connections, one per level. The
right wording for a business audience and for an engineer are not the same sentence.

## Text fields

- **`descr` → `description`**, verbatim.
- **`caption` mirrors the description**, trimmed to label shape: the first clause, at
  most eight words, no trailing full stop. It renders under the object's name on every
  diagram, so it reads as a label and not a sentence.
- **`techn` → `technologyIds` and `icon` only.** Never the caption, never the
  description. One string is often several technologies: split `"Java, Spring MVC"` and
  `"async, JSON/HTTPS"` before looking them up.
- **`$link` → `links`.**
- **`$tags`** parses but Mermaid does not implement it. Where an input carries tags
  they can become IcePanel tags and tag groups; the parser leaves them alone.
- **Boundaries have no description field in Mermaid at all**, so every boundary-derived
  object needs one written.

`<br/>` is flattened to a space, and a label may be unquoted — `Person(customer,
Customer, "…")` is legal.

## Diagrams

| Mermaid block | IcePanel diagram `type` | `modelId` |
| --- | --- | --- |
| `C4Context` | `context-diagram` | the domain root (`@root`) |
| `C4Container` | `app-diagram` | the boundary that resolved to a `system` |
| `C4Component` | `component-diagram` | the boundary that resolved to an `app` or `store` |
| `C4Dynamic` | whichever of the two above fits its contents | as above |
| `C4Deployment` | `context-diagram` | `@root`, with the nodes as group areas |

One diagram per block, `index` in input order, so several blocks at the same level
become several diagrams rather than one crowded one. `title` becomes the diagram name.

**Mermaid carries no geometry**, so all placement is generated: ranks come from the
relationship graph, actors are pinned to the first row, and anything outside the
subject boundary is pushed clear of it. Above if it calls in, below if it is called
because an area is auto-sized around its children and would otherwise swallow a
non-member sitting between two members. `$c4ShapeInRow` from `UpdateLayoutConfig` sets
boxes per row, and the `Rel_U` family nudges rank. The grid is the 384 × 320 pitch from
`creating-c4-diagrams/references/layout.md`.

## Six ways a literal reading goes wrong

1. **`Rel_Back` reverses the arrow.** `Rel_Back(database, backend_api, "Reads from and
   writes to")` means the *API* reads from the database. Transcribe the argument order
   and every one of these lands backwards. Authors also reach for it purely to move a
   box, which silently reverses a correct relationship — so the parser reports every
   one for a direction check, and some of them will need flipping back.
2. **The boundary keyword lies about the level.** `Container_Boundary` is a system in
   one block and an app in the next. Classify by contents.
3. **Aliases are not stable across blocks.** Mermaid's own docs rename `backend_api` to
   `api` between diagrams. Merging by alias silently produces two objects; the report
   catches it by name, but only across blocks — two same-named objects in one block are
   two objects.
4. **Names collide domain-wide.** Not just among siblings. A `group` and a `system` can
   clash, which is why bounded contexts get a "BC" suffix in the sibling skill.
5. **A label is not always a name.** `Rel(c3, c4, "select * from users where username =
   ?", "JDBC")` is from the reference docs. Long or code-shaped labels belong in the
   description.
6. **A container with no boundary has no system.** It is not an error in Mermaid and it
   is very common. Something has to be invented, and it should be renamed before it
   reaches the model.

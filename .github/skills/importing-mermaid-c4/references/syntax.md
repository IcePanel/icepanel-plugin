# The Mermaid C4 syntax

What the parser accepts, and what Mermaid itself does not implement. Mermaid's C4
support is a subset of [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML)
and is marked experimental upstream, so an input may contain PlantUML statements that
Mermaid ignores.

## Contents

- [Block structure](#block-structure)
- [Statements](#statements)
- [Argument forms](#argument-forms)
- [Not implemented upstream](#not-implemented-upstream)

## Block structure

A block opens with one of five headers and runs to the end of the fence or file:

```
C4Context | C4Container | C4Component | C4Dynamic | C4Deployment
```

Everything else is optional, including `title`. Boundaries nest with `{ }` to any
depth, and **relationships may be written inside a boundary block**. The reference
`C4Component` example does exactly that, which means a parser cannot assume all
`Rel` statements come after all elements.

```
C4Container
title Container diagram for Ledger
Container_Boundary(ledger, "Ledger") {
  Container(web, "Web UI", "React", "Where accountants work.")
  ContainerDb(pg, "Ledger Store", "PostgreSQL", "The double-entry record.")
  Rel(web, pg, "Writes to")
}
System_Ext(bank, "Bank API", "Settles payments.")
Rel(pg, bank, "Settles through", "REST")
```

An optional YAML frontmatter block may precede the header, carrying render config
only. Wrapping has defaulted to on since v11.17.1 and is disabled with `c4.wrap`:

```yaml
---
config:
  c4:
    wrap: false
---
```

`%%` starts a comment to end of line. A `%%` inside a quoted string is not a comment.

## Statements

### Elements

| Keyword | Positional arguments |
| --- | --- |
| `Person`, `Person_Ext` | `alias, label, ?descr, ?sprite, ?tags, $link` |
| `System`, `SystemDb`, `SystemQueue` (+ `_Ext` of each) | `alias, label, ?descr, ?sprite, ?tags, $link` |
| `Container`, `ContainerDb`, `ContainerQueue` (+ `_Ext`) | `alias, label, ?techn, ?descr, ?sprite, ?tags, $link` |
| `Component`, `ComponentDb`, `ComponentQueue` (+ `_Ext`) | `alias, label, ?techn, ?descr, ?sprite, ?tags, $link` |
| `Deployment_Node`, `Node`, `Node_L`, `Node_R` | `alias, label, ?type, ?descr, ?sprite, ?tags, $link` |

Note the shift: the `Container` and `Component` families take `techn` in third
position, so their `descr` is the **fourth** argument, where the `Person` and `System`
families have it third. Binding those by position without switching on the family
puts the description into the technology slot.

### Boundaries

| Keyword | Positional arguments |
| --- | --- |
| `Boundary` | `alias, label, ?type, ?tags, $link` |
| `Enterprise_Boundary`, `System_Boundary`, `Container_Boundary` | `alias, label, ?tags, $link` |

`Boundary` takes a free-text `type` the others do not, so it too has a different
positional shape. Its value carries no meaning, the docs pass the literal
`"boundary"`.

### Relationships

| Keyword | Positional arguments |
| --- | --- |
| `Rel`, `BiRel`, `Rel_U`/`Rel_Up`, `Rel_D`/`Rel_Down`, `Rel_L`/`Rel_Left`, `Rel_R`/`Rel_Right`, `Rel_Back` | `from, to, label, ?techn, ?descr, ?sprite, ?tags, $link` |
| `RelIndex` | `index, from, to, label, ?tags, $link` |

`RelIndex` is accepted for PlantUML compatibility but **Mermaid ignores the index**;
sequence follows statement order.

### Directives

| Keyword | Arguments | Effect here |
| --- | --- | --- |
| `title` | free text | The diagram name, and a fallback source for the domain name |
| `UpdateLayoutConfig` | `?c4ShapeInRow` (default 4), `?c4BoundaryInRow` (default 2) | `c4ShapeInRow` sets boxes per row in the generated layout |
| `UpdateElementStyle` | `elementName, ?bgColor, ?fontColor, ?borderColor, ?shadowing, ?shape, ?sprite, ?techn, ?legendText, ?legendSprite` | Dropped |
| `UpdateRelStyle` | `from, to, ?textColor, ?lineColor, ?offsetX, ?offsetY` | Dropped |

The two style directives are implemented in Mermaid and parse fine. They are dropped
on the way into IcePanel because IcePanel styles objects by type and tag, so a colour
or a label offset has nothing to land on.

## Argument forms

Three things make naive splitting fail:

**Labels need not be quoted.** `Person(customer, Customer, "A customer…")` is legal and
appears in the reference docs.

**`$named` arguments may follow the positionals in any order**, and win their slot:

```
System_Ext(email_system, "E-Mail System", "The internal Exchange system", $tags="v1.0")
UpdateRelStyle(customerA, bankA, $offsetY="60", $lineColor="blue")
```

Both assignment styles are equivalent. The docs give
`UpdateRelStyle(customerA, bankA, "red", "blue", "-40", "60")` and the `$named` form
of the same call.

**`<br/>` appears inside strings** as a manual line break, in any of `<br>`, `<br/>`
and `<br />`. It flattens to a space.

## Not implemented upstream

Mermaid parses some of these and does nothing with them; others are absent entirely.
Either way there is nothing to import.

- **`sprite`, `tags`, `link`, and the legend** — listed as unfinished features. A
  `$tags=` argument parses without error and appears in Mermaid's own examples, so an
  input may carry tags even though nothing renders them.
- **`AddElementTag`, `AddRelTag`** — custom stereotypes.
- **`RoundedBoxShape()`, `EightSidedShape()`, `DashedLine()`, `DottedLine()`,
  `BoldLine()`** — the shape and line-style helpers those tag calls would use.
- **`Lay_U`, `Lay_D`, `Lay_L`, `Lay_R`** — pure layout statements. The docs state there
  is *no plan* to support them, because Mermaid positions shapes by statement order.

That last point is worth keeping in mind for the `Rel_U`/`Rel_D`/`Rel_L`/`Rel_R`
family too. They parse, and they record which way the author wanted the target placed,
but since Mermaid's own layout comes from statement order they may have little effect
in its output. They are treated here as a hint about intent, never as a change to the
relationship.

There is also no code-level (C4 level 4) diagram in either Mermaid or IcePanel, so
nothing is lost at that end.

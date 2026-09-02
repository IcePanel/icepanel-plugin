# Context map notation

The ddd-crew notation, which most context maps follow: [https://github.com/ddd-crew/context-mapping](https://github.com/ddd-crew/context-mapping).

Sketches are rarely faithful to it. Read this for what the symbols mean, then read *Reading a real sketch* at the bottom for what actually goes wrong.

## Contents

- [Boundaries](#boundaries)
- [Team relationships](#team-relationships)
- [Context map patterns](#context-map-patterns)
- [Reading a real sketch](#reading-a-real-sketch)

## Boundaries


| Symbol                                   | Means                            | Becomes                                                            |
| ---------------------------------------- | -------------------------------- | ------------------------------------------------------------------ |
| Named circle or box                      | A bounded context                | `group` named `<Name> BC` + `system` named `<Name>`                |
| Named circle with people icons beside it | The team of that bounded context | `group` for the bounded context, `actors` for the people inside    |
| Cloud with a yellow `BBoM` tag           | Big Ball of Mud                  | same pair, **no tag**, usually unconnected                         |


The `BC` suffix isn't decoration: the group and the system are siblings under the domain, and IcePanel refuses two siblings with the same name. See *Step 3* in `SKILL.md`.


People icons are decoration for this translation. The user assigns IcePanel teams to the groups or systems afterwards.

## Team relationships

The **line style** carries the team relationship. This is the layer people most often skip when reading a map, and it decides the connection's direction.


| Line                                            | Relationship              | Meaning                                                                                  |
| ----------------------------------------------- | ------------------------- | ---------------------------------------------------------------------------------------- |
| Thin solid, `U` at one end and `D` at the other | **Upstream / Downstream** | Asymmetric. The upstream context's decisions affect the downstream one, not the reverse. |
| Thick solid                                     | **Mutually dependent**    | Neither succeeds without the other. Both models are entangled.                           |
| Dotted, sometimes labelled `Free`               | **Free**                  | No organisational or technical link at all.                                              |


`U` and `D` are plain letters sitting next to the context at each end of the line, not on the line, not inside the circle. They are small and easy to miss on a photo, and they are the single most load-bearing mark on the map. They set which way the connection is authored.

## Context map patterns

Patterns are the small teal boxes attached to a line, plus two text labels.


| Marker        | Pattern                                                                         | Owned by     | Tag                           |
| ------------- | ------------------------------------------------------------------------------- | ------------ | ----------------------------- |
| `OHS`         | Open Host Service: a defined set of services other contexts integrate against   | upstream     | `OHS`                         |
| `PL`          | Published Language: a documented shared language for the exchange               | upstream     | `PL`                          |
| `OHS + PL`    | Both together, the common combination                                           | upstream     | `OHS` **and** `PL`            |
| `CF`          | Conformist: the downstream adopts the upstream model wholesale, no translation  | downstream   | `CF`                          |
| `ACL`         | Anticorruption Layer: the downstream translates the upstream model into its own | downstream   | `ACL`                         |
| `SK`          | Shared Kernel: a jointly-owned subset of the model, drawn straddling the line   | both         | `SK`                          |
| `CUS --> SUP` | Customer / Supplier: the downstream's priorities factor into upstream planning  | relationship | `C/S`                         |
| `Partnership` | Partnership: coordinated planning and joint interface evolution                 | relationship | `Partnership`                 |
| `SW`          | Separate Ways: integration deliberately not attempted                           | relationship | none, drop the relationship   |
| `BBoM`        | Big Ball of Mud: a mess whose model must not propagate                          | boundary     | none, usually unconnected too |


**Which end a marker sits on is its meaning.** `OHS` hangs off the upstream context; `ACL` and `CF` off the downstream one. In ddd-crew's own example, context A carries a single `OHS`, and the three contexts downstream of it each carry their own `ACL` or `CF` on their side of the line. A marker read as a property of the *line* rather than of an *end* has lost the point.

For the model this is recoverable, ownership is fixed by the pattern, so the tag on the connection is enough (see *Step 5* in `SKILL.md`). It still matters while reading, because a marker on the wrong end usually means the whole line has been read backwards.

`SK` is the exception: it straddles the line on a thick mutually-dependent connection, belonging to both ends.

## Reading a real sketch



### `U`/`D` beats the arrowhead, always

The lines on a context map are mostly plain, no arrowheads at all. Where an arrowhead does appear it is usually `CUS --> SUP`, and **it points from the customer to the supplier**, while the supplier is the upstream one. The arrow is about influence over planning; the `U`/`D` letters are about influence over the model, which is what gets authored.

Read direction from `U`/`D`. Where the letters are missing, infer it from the markers. `OHS`/`PL` sit upstream, `ACL`/`CF` downstream, and say that you inferred it.

### A hand-drawn map won't use the notation properly

Expect all of these, and don't quietly repair them:

- **Rectangles for contexts.** Fine — the shape carries no meaning beyond circle-vs-cloud.
- **Arrowheads on ordinary lines**, drawn to mean a call rather than influence. Check them against `U`/`D` and the markers before believing them.
- **Line weight that isn't deliberate.** Thick-versus-thin is only a signal when the map is drawn carefully. If every line looks the same weight, treat them all as upstream/downstream and confirm.
- **Markers written out**. "Anticorruption Layer", "anti-corruption", "ACL?", or floating near a line rather than attached to an end.
- **Patterns that aren't in the notation.** "Legacy", "TBD", "?", a question mark over a line. Report these; don't map them onto the nearest official pattern.
- **Contexts with no relationships at all.** Legitimate. model the context, author no connection.



### What to carry into Step 2

Anything ambiguous goes to the user rather than into the file. Specifically:

- A line whose direction you inferred rather than read.
- A marker you couldn't attribute to an end.
- Any text you couldn't make out.
- Anything that isn't part of the notation.

An unreadable map is worth saying so about. "I can make out six contexts but not the markers on three of the lines" gets you a better photo. A confident wrong reading gets imported and lives in the landscape.
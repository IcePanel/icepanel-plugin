---
name: importing-mermaid-c4
description: Turn Mermaid C4 diagrams (C4Context, C4Container, C4Component, C4Dynamic, C4Deployment) into IcePanel model objects, connections and diagrams. Use whenever the user supplies Mermaid C4 syntax, pasted, in a Markdown fence, or in a .mmd file — or asks to import, convert or migrate C4 diagrams, PlantUML-style C4, or docs-as-code architecture diagrams into IcePanel.
---

# Importing Mermaid C4 into IcePanel

Mermaid C4 is a set of **diagrams**. IcePanel holds a **model** that diagrams are views onto. So this is not a transcription: the model has to be reconstructed from the diagrams, and the diagrams then redrawn from the model.

Most of the work is reconciling Mermaid C4 with IcePanel's data structure. Mermaid has no domain, no coordinates, no captions, and no way to say which system a container belongs to unless the author happened to wrap it in a boundary. Those gaps get filled by inference, and **every inference is confirmed with the user before anything is written** (*Step 3*).

This skill owns the translation: input to a validated import file and diagram specs. **Importing and drawing belong to** `creating-c4-diagrams`. Hand off at *Step 5* and don't reimplement any of it.

## Order of work

1. Get the diagram code (DSL) and get an API key and landscape (*Step 1*).
2. Parse, which merges the blocks and writes a report (*Step 2*).
3. Confirm the report with the user. Stop until they answer (*Step 3*).
4. Fill the gaps the report names. Descriptions, technologies, labels (*Step 4*).
5. Hand off to `creating-c4-diagrams` to import, draw and verify (*Step 5*).

## Step 1: collect the input

Three input shapes, all handled by the parser:

- Markdown files with ` ```mermaid ` fences. Every C4 block in the file is picked up and non-C4 fences are skipped
- standalone `.mmd` / `.mermaid` files
- a block pasted into the conversation. Write it to a file, or pipe it in as `-`

**Take every block the user has, not just one.** A single block is dramatically lossier, because merging is how the hierarchy is recovered: a `C4Container` block says which system a container belongs to, and the `C4Component` block for that same container says which components it holds. Neither alone gives you the chain. If the user offers one block and mentions others exist, ask for them.

Don't scan a repository for blocks unless asked. And confirm the landscape and API key as `creating-c4-diagrams` describes. A key is required.

## Step 2: parse

```bash
python scripts/mermaid_c4.py parse docs/architecture.md --out mermaid-c4
```

It writes `model.json`, one `diagram-NN-*.json` per block, `groups-NN.json` passes when groups nest, and `report.md`. It does no HTTP and invents no prose.

`--domain NAME` names the domain when the input gives nothing to name it from. `--namespace` defaults to `mermaid-c4`; set it when the landscape is fed from more than one source. `--alias OLD=NEW` merges two aliases into one object, which is what the report asks for when it finds a probable duplicate.

**Read `references/mapping.md` before interpreting the output.** It has the element and relationship tables, the boundary rule, and the six places a literal reading produces a wrong model.

### Aliases are the merge key, and authors are inconsistent

An alias declared in several blocks is one object. That is the whole mechanism, and it fails whenever the author renamed things between diagrams. Mermaid's own reference docs call one app `backend_api` in the container diagram and `api` in the component diagram.

The parser detects this by name and reports it as a probable duplicate with the exact `--alias` flags to fix it. **Those are proposals, not findings.** Two containers legitimately named "Database" on a deployment diagram are two databases; a primary and a replica must not be merged. Put the list to the user in *Step 3* and re-run with the flags they confirm.

## Step 3: confirm with the user

`report.md` is the confirmation gate, and it exists because a Mermaid import is a stack of guesses. Read it, then put it to the user before importing. Lead with the sections that change the model:

| Section | Why it needs an answer |
|---|---|
| Problems | Something didn't translate. Fix these first |
| Probable duplicates | Which alias pairs are really one object |
| Conflicting declarations | One alias declared two ways across blocks |
| Invented objects | Systems and apps that exist only because Mermaid named none |
| Renamed for uniqueness | IcePanel names must be unique across the domain |
| Inferences | Domain naming, boundary classification, deployment fallbacks |
| Merged across levels | One relationship stated at two altitudes |
| Reversed by `Rel_Back` | Directions that may be backwards in the source |

Ask about the model, not the mechanics. "These two both say 'Database', are they one store or a primary and a replica?" is answerable in a sentence. "Should I merge alias `db2` into `db`?" is not.

Say plainly that **layout is generated** and needs their eye once it's drawn. There is no Mermaid geometry to preserve, so placement comes from the relationship graph and the reading order in `creating-c4-diagrams/references/layout.md`. It is a starting point.

## Step 4: fill the gaps

Three things the parser deliberately leaves for you, all listed in the report.

**Descriptions.** Mermaid's `descr` is optional and often missing, and boundaries have no description field at all, so those objects arrive with `description` and `caption` empty. Write a short one that explains what the object does, and keep the caption to a few words in label shape with no trailing full stop, matching the description. Show what you generated at the confirmation gate rather than writing it silently; a name like `c1` gives you very little to go on, and the user will spot fiction instantly.

**Technologies.** Every Mermaid `techn` string is listed unresolved. Look them up in the catalog and set `technologyIds` and `icon` as `creating-c4-diagrams` describes. A `techn` is often several technologies in one string — `"Java, Spring MVC"` is two, `"async, JSON/HTTPS"` is a protocol and a format. Split it, look up each part, and skip anything with no genuine match. `techn` never becomes the caption or the description; it is technology data and nothing else.

**Labels.** A verbose or code-shaped relationship label has been moved into the connection's `description` and given a provisional name. Mermaid's own docs use a raw SQL statement as a label. Rewrite those to a short verb phrase that reads across the arrow. Leave the plain ones (`"Uses"`, `"Sends e-mails to"`) exactly as the author wrote them.

Edit `model.json` in place. Everything else about it is already in import shape.

## Step 5: hand off

Import the group passes first when they exist, then the model, then draw:

```bash
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> mermaid-c4/groups-01.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> mermaid-c4/groups-02.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> mermaid-c4/model.json
python ../creating-c4-diagrams/scripts/icepanel.py idmap   <landscapeId>
python ../creating-c4-diagrams/scripts/icepanel.py diagram <landscapeId> mermaid-c4/diagram-01-*.json
python ../creating-c4-diagrams/scripts/icepanel.py verify  <landscapeId>
```

The `groups-NN.json` files exist only when the input nests groups, which a `C4Deployment` block sometimes does. They must go in **in order and before the model**: a group parented to another group fails with `Parent not found` when both are created in one request, and that failure cascades to every object listing the nested group in `groupIds`.

Then tell the user what you chose, what you invented, and that the layout is a first pass. Give them the landscape link.

## Importing into a landscape that already has a model

The common case is a fresh landscape. When the landscape already holds objects, a straight import creates a second near-duplicate set, which is far more work to undo than to avoid.

So read the model first and match by name:

```bash
python ../creating-c4-diagrams/scripts/icepanel.py idmap <landscapeId>
```

**Names are unique within a domain**, so a name match is unambiguous. No need to walk the hierarchy looking for the right sibling. For every match, replace the import ID in `model.json` and in the diagram specs with the IcePanel ID, so the import updates that object instead of creating a new one.

Three rules on a match:

- **A type mismatch stops and asks.** Mermaid saying `Container` where IcePanel holds a `system` is not something to resolve quietly; it means one of the two models is wrong about what that thing is.
- **Fill blanks, never overwrite.** A blank `description`, `caption` or `technologyIds` on the existing object can take the Mermaid value. Text that is already there stays, and the user confirms the fills before they go in.
- **Re-sending an object clears its `icon`** while leaving `caption`, `description` and `technologyIds` alone. Re-send the icon for every existing object you touch.

Where the model is already complete and only the diagrams are wanted, skip the import entirely: point the diagram specs' `ref` fields at the IcePanel IDs and go straight to `icepanel.py diagram`.

## What doesn't come across

Say these out loud rather than letting the user find them later.

- **Ordering in a `C4Dynamic` block.** An ordered walkthrough is an IcePanel flow, which is out of scope here. The relationships are imported; the step numbers are not.
- **`C4Deployment` as a diagram type.** IcePanel has no deployment diagram. The nodes become nested groups in the model, correctly, and the block is drawn as a app (Level 2) diagram with those groups as areas.
- **All styling.** `UpdateElementStyle`, `UpdateRelStyle` and their colours and label offsets have nothing to land on; IcePanel styles objects by type and tag. `UpdateLayoutConfig`'s `$c4ShapeInRow` is the exception and does feed the layout.
- **`Db` and `Queue` shapes on systems and components.** No IcePanel equivalent, so `SystemDb` is a `system` and `ComponentQueue` is a `component`. `ContainerDb` and `ContainerQueue` both survive as stores.
- **Sprites, and C4 level 4.** Neither exists in IcePanel, and Mermaid doesn't implement sprites either.

## Reference

- `references/mapping.md` — element, boundary and relationship mapping, and the traps in each
- `references/syntax.md` — the Mermaid C4 syntax the parser accepts, and what is unimplemented upstream
- `references/example.md` — a worked import: two blocks, the report, the fixes, the commands
- `creating-c4-diagrams` — the sibling skill that owns the API, the import, layout and verification

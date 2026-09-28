---
name: importing-structurizr-dsl
description: Turn a Structurizr DSL workspace (workspace.dsl, a pasted block, or a directory of DSL files) into IcePanel model objects, connections and diagrams. Use whenever the user supplies Structurizr DSL, points at a workspace.dsl, or asks to import, convert or migrate a Structurizr workspace, a models-as-code C4 landscape, or `softwareSystem`/`container`/`component` definitions into IcePanel.
---

# Importing Structurizr DSL into IcePanel

Structurizr is already model-first: a `model` block and a `views` block, the same split IcePanel makes. This is a translation, not a reconstruction.

Four gaps are left to fill. Structurizr has one container type where IcePanel has two, no external flag, no software system above an `infrastructureNode`, and no layout to preserve. Each is filled by inference, and **every inference is confirmed with the user before anything is written** (*Step 3*).

This skill owns the translation: DSL in, a validated import file and diagram specs out. **Importing and drawing belong to** `creating-c4-diagrams`. Hand off at *Step 5* and do not reimplement it.

## Order of work

1. Get the DSL, an API key and a landscape (*Step 1*).
2. Parse. This writes the import file, the diagram specs and a report (*Step 2*).
3. Confirm the report with the user. Stop until they answer (*Step 3*).
4. Fill the gaps the report names: descriptions, technologies, captions (*Step 4*).
5. Hand off to `creating-c4-diagrams` to import, draw and verify (*Step 5*).

## Step 1: collect the input

Four input shapes, all handled by the parser:

- a `workspace.dsl` file, by path
- a directory, which is how real repositories are laid out. Every `.dsl` in it is read and `!include` resolves against it
- an `https://` URL to a DSL file
- a block pasted into the conversation. Write it to a file, or pipe it in as `-`

**Prefer the directory or the file path over a paste.** `!include` is very common once a workspace outgrows one file, and a pasted fragment cannot resolve it. The parser reports each unresolved include, but the model is genuinely incomplete at that point. If the user pastes something containing `!include`, ask for the path.

Confirm the landscape and API key as `creating-c4-diagrams` describes. A key is required.

### A workspace.json is not the input

`workspace.json` is the *compiled* workspace and a different job: its element IDs are sequential integers reassigned on every parse, and its relationships include Structurizr's automatically generated implied ones, which IcePanel does not want. Ask for the `.dsl` it was built from. The one thing the JSON adds is saved diagram layout, and this skill generates layout anyway.

## Step 2: parse

```bash
python scripts/structurizr_dsl.py parse workspace.dsl --out structurizr
```

It writes `model.json`, a `diagram-NN-*.json` for each view it can draw, `groups-NN.json` passes when groups nest, and `report.md`. It does no HTTP beyond fetching an `https://` input, and invents no prose.

`--domain NAME` names the domain when the workspace is unnamed. `--namespace` defaults to `structurizr`. `--environment NAME` picks the deployment environment, and is **required when the workspace defines more than one**; the parser stops and lists them rather than guessing. `--split-instances` turns a container deployed onto several nodes into one object per node.

**Read** `references/mapping.md` **before interpreting the output.** It has the element, group and view tables, and the six places a literal reading produces a wrong model.

### Two things the parser will not do

**It never runs** `!script` **or** `!plugin`**.** Both execute arbitrary JVM code from the user's workspace. They are reported and skipped, so anything they would have added to the model is missing. Say so rather than letting the user find a hole later.

**It does not evaluate view expressions.** A Structurizr view never lists what it shows, it *computes* it. There are three ways an author can say what belongs on one:

| In the DSL                            | What it means                                                 | Handled |
| ------------------------------------- | ------------------------------------------------------------- | ------- |
| `include *`                           | everything at this view's level, plus whatever connects to it | yes     |
| `include webapp database`             | exactly these elements, named by identifier                   | yes     |
| `include "element.tag==Microservice"` | a query run over the model                                    | **no**  |

The first two are the idiom, and Structurizr's own examples use nothing else. The third is a small query language matching on tags, parent, technology, properties and couplings, combined with `&&` and `||`. The parser does not implement it.

When it meets one, it falls back to `include *` for that view and names the expression in the report. An expression almost always *narrows* the wildcard down, so the practical result is that **the diagram shows more than the author asked for**. An unevaluated `exclude` expression does the same from the other direction: something the author deliberately took off the diagram comes back onto it.

None of this touches the model, only what one diagram draws. So when the report's **Views** section names an expression, open that diagram's spec and either delete the objects that do not belong or ask the user which elements they meant.

## Step 3: confirm with the user

`report.md` is the confirmation gate. Read it, then put it to the user before importing. Lead with the sections that change the model:

| Section                            | Why it needs an answer                                             |
| ---------------------------------- | ------------------------------------------------------------------ |
| Problems                           | Something did not translate. Fix these first                       |
| Refused for safety                 | `!script` or `!plugin` was skipped, so the model may be short      |
| Containers read as data stores     | The one inference that silently corrupts the model                 |
| Systems marked external            | Structurizr has no external flag, so this is all inference         |
| Deployed more than once            | One container on several nodes. One object or several?             |
| Renamed for domain-wide uniqueness | IcePanel names are unique across the domain                        |
| Inferences                         | Domain naming, the system each infrastructureNode landed in, deployment views |
| Views                              | Which views were skipped, and which used an unevaluated expression |
| Tags                               | Which tags were kept as meaning and which were dropped as styling  |

A skipped block is the loudest problem there is. An unrecognised statement that opens braces takes its whole body with it, so a single unknown keyword can cost most of the model. The report says so under **Problems**, and every relationship pointing into that body fails underneath it.

Ask about the model, not the mechanics. "Structurizr shows one Database deployed on both an Oracle primary and a secondary. Is that one store or two?" is answerable in a sentence. "Should I pass `--split-instances`?" is not.

Say plainly that **layout is generated**. The DSL holds no geometry. `autoLayout` is an instruction to Structurizr's renderer, not a set of coordinates, so placement comes from the relationship graph and the reading order in `creating-c4-diagrams/references/layout.md`.

## Step 4: fill the gaps

Three things the parser deliberately leaves for you, all listed in the report.

**Descriptions and captions.** Structurizr's `description` is a positional argument on nearly every element, so it is usually there, and where it is the parser writes both `description` and a `caption` trimmed from it. Boundaries are the gap: `group` and `deploymentNode` have no description field at all, so every group arrives empty. Write a short one, and keep the caption to a few words in label shape with no trailing full stop. Show what you generated at the confirmation gate rather than writing it silently.

**Technologies.** Every `technology` string is listed unresolved. Look them up in the catalog and set `technologyIds` and `icon` as `creating-c4-diagrams` describes. One string is often several technologies: `"Java and Spring MVC"` is two, `"JSON/HTTPS"` is a format and a protocol. Split it, look up each part, and skip anything with no genuine match. A `technology` never becomes the caption or the description.

**Tags.** The parser keeps tags that carry meaning and drops the ones whose meaning has already been absorbed. A tag styled `shape Cylinder` became the `store` type, a tag saying somebody else owns the thing (`Third Party`, `SaaS`) became the external flag, and a tag whose style sets nothing but a shape was only ever notation. Both lists are in the report. Prune what is left before importing; a landscape with forty single-use tags is worse than one with none.

`Existing System` is **not** in that second group. It means brownfield, not third-party. A team's own old system is still its own, so it sets no flag and survives as an ordinary tag.

Edit `model.json` in place. Everything else about it is already in import shape.

## Step 5: hand off

Import the group passes first where they exist, then the model, then draw. These paths assume the two skills sit side by side; adjust them to wherever `creating-c4-diagrams` is installed.

```bash
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/groups-01.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/groups-02.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/model.json
python ../creating-c4-diagrams/scripts/icepanel.py idmap   <landscapeId>
python ../creating-c4-diagrams/scripts/icepanel.py diagram <landscapeId> structurizr/diagram-01-*.json
python ../creating-c4-diagrams/scripts/icepanel.py verify  <landscapeId>
```

The `groups-NN.json` files exist whenever groups nest, which any `deploymentEnvironment` with nested nodes produces. They must go in **in order and before the model**. A group parented to another group fails with `Parent not found` when both are created in one request, and that failure cascades to every object listing the nested group in `groupIds`.

Then tell the user what you chose, what you inferred, and that the layout is a first pass. Give them the landscape link.

## Importing into a landscape that already has a model

The common case is a fresh landscape. When the landscape already holds objects, a straight import creates a second near-duplicate set, which is far more work to undo than to avoid.

So read the model first and match by name:

```bash
python ../creating-c4-diagrams/scripts/icepanel.py idmap <landscapeId>
```

**Names are unique within a domain**, so a name match is unambiguous. For every match, replace the import ID in `model.json` and in the diagram specs with the IcePanel ID, so the import updates that object instead of creating a new one.

Three rules on a match:

- **A type mismatch stops and asks.** Structurizr saying `container` where IcePanel holds a `system` means one of the two models is wrong about what that thing is.
- **Fill blanks, never overwrite.** A blank `description`, `caption` or `technologyIds` can take the Structurizr value. Text already there stays, and the user confirms the fills before they go in.
- **Re-sending an object clears its** `icon` while leaving `caption`, `description` and `technologyIds` alone. Re-send the icon for every existing object you touch.

Where the model is already complete and only the diagrams are wanted, skip the import: point the diagram specs' `ref` fields at the IcePanel IDs and go straight to `icepanel.py diagram`.

## What doesn't come across

Say these out loud rather than letting the user find them later.

- `dynamic` **views.** An ordered walkthrough is an IcePanel flow, which is out of scope here. The relationships are already in the model from the static definitions; the ordering and any view-level description overrides are not.
- `deployment` **as a diagram type.** IcePanel has no deployment diagram. The nodes become nested groups in the model, correctly, and the view is drawn as an app diagram on the scoped system with those nodes as areas.
- `filtered`**,** `custom` **and** `image` **views.** A tag filter over another view, custom elements outside the C4 model, and an embedded picture. None has anything to land on. Flag them to the user rather than ignoring them.
- `infrastructureNode` **keeps its system by inference.** Load balancers, firewalls and DNS become `app`s, sitting in the node groups they were deployed on. Structurizr puts no software system above one, so the parser infers it from the environment and reports every call. Check those calls, because shared infrastructure fronting several systems has no right answer.
- **All styling, themes and terminology.** IcePanel styles objects by type and tag. The styles block is still *read*, because a store-shaped tag is one of the things that says a container is a data store, but nothing in it is written to IcePanel.
- `properties`**,** `perspectives`**,** `healthCheck`**,** `instances` **counts and** `deploymentGroup`**.** No IcePanel equivalent.
- `!docs` **and** `!adrs`**.** Documentation and decision records have nowhere to go through this API surface.
- `enterprise { ... }`**.** The deprecated enterprise boundary is not parsed, and its entire body is skipped. Reported as a problem. If a workspace uses it, unwrap the block so its contents sit at model level and re-parse; the boundary becomes the domain either way.
- **C4 level 4.** Neither tool has it.

## Reference

- `references/mapping.md` for element, group, relationship and view mapping, and the traps in each
- `references/syntax.md` for the DSL the parser accepts and what it deliberately does not
- `references/example.md` for a worked import of the Big Bank plc workspace: the report, the fixes, the commands
- `creating-c4-diagrams` for the sibling skill that owns the API, the import, layout and verification

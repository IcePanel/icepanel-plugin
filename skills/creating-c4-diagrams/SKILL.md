---
name: creating-c4-diagrams
description: Build and maintain C4 architecture models in IcePanel via its REST API. Model objects (actors, systems, apps, stores, components), connections, and Level 1/2/3 diagrams with hand-authored layout. Use this whenever the user wants architecture put into IcePanel, wants to import or sync a landscape, wants existing diagrams/descriptions/codebases turned into a C4 model, or asks for context/app/component diagrams.
---

# C4 modelling in IcePanel

IcePanel separates the **model** (the real graph of objects and connections) from **diagrams** (views onto it). Build the model first and get it right; diagrams are then just placement. Getting this backwards produces diagrams that look fine and a model that is wrong. The model is what everything else in IcePanel is derived from.

There is no auto-layout, and connections do not appear on a diagram unless you explicitly draw them there.

## Order of work

1. Get an API key and the target landscape.
2. **Decide whether the model already exists.** If it does, skip straight to *Step 4: create diagrams*.
3. Derive the model (*Step 1*) and its connections (*Step 2*), confirming the object list with the user first if the source is ambiguous.
4. Import (*Step 3*), then fetch the ID map — import IDs are yours, IcePanel assigns its own.
5. Create diagrams with explicit layout (*Step 4*).
6. Verify, then hand the user a link to the landscape (*Step 5*).

## Setup

Auth is `X-API-Key` **alone**. Sending `Authorization: Bearer` as well returns 401, despite the API reference marking both as required.

**If the user hasn't given you a key, ask for one and stop until they do** — there is nothing useful to do without it, and don't go looking for one in their environment or files. They generate it themselves in IcePanel, under the organization's settings, on the API keys page. It looks like `<key-id>:<secret>` — both halves, colon-separated.

```bash
export ICEPANEL_TOKEN='<key-id>:<secret>'
curl -s -H "X-API-Key: $ICEPANEL_TOKEN" https://api.icepanel.io/v1/organizations
```

Everything is scoped to a landscape and a version: `/v1/landscapes/{landscapeId}/versions/{versionId}/...`. Use `latest` as the version unless the user names a snapshot.

To create a landscape: `POST /v1/organizations/{orgId}/landscapes` with `{"name": "..."}`. The response includes the landscape and its initial version.

**Domains** are business or product areas, and every object belongs to exactly one. One domain is usually right.

A new landscape ships with a "Default domain", but you cannot import into it. `parentId` inside an import file resolves **only against `id`s in that same file** — an IcePanel object ID or a domain name both fail with `Parent <x> not found`. So include a `domain` object in the import and parent your top-level objects to it:

```json
{ "id": "d-deadball", "name": "Dead Ball", "type": "domain",
  "description": "The office foosball league product area." },
{ "id": "s-deadball", "name": "Dead Ball", "type": "system", "parentId": "d-deadball" }
```

That leaves the shipped default domain behind, empty. Delete it once the import completes. `GET /domains` returns no child list, so identify the leftover by name (`Default domain`) or by diffing against `GET /model/objects` — the empty one is the `domainId` no object other than its own `root` belongs to. Then `DELETE /landscapes/{id}/versions/latest/domains/{domainId}`.

## Diagramming a model that already exists

Plenty of landscapes already have their objects and connections. Then importing is not just unnecessary, it's harmful — a second set of near-duplicate objects is far more work to undo than to avoid. Steps 1 to 3 are for building a model; skip them and go to *Step 4: create diagrams*.

Read what's there first, and use it as the object list:

```bash
python scripts/icepanel.py idmap <landscapeId>
```

Every IcePanel ID maps to itself, so a diagram spec's `ref` fields take those IDs directly — no import IDs needed, and `@root` still resolves the domain root. `GET /model/objects` and `GET /model/connections` give you the full picture including the hierarchy, and `GET /diagrams` shows what's already drawn so you extend rather than duplicate.

The one thing to check before placing anything: **a diagram can only draw connections the model already has.** If the story needs an arrow that isn't in the model, author that connection — and only that one — rather than reaching for a null `modelId`.

**When you can't tell whether the model covers what you need, ask.** "Are these existing objects the ones you want on the diagram, or should I add anything?" is a cheap question. Guessing wrong means either a duplicate model or a diagram missing half its subject, and the user can answer in a sentence.

## Step 1: derive the model

C4's abstractions nest: a software system is made of containers (applications and data stores), each containing components, implemented by code.

| C4 | IcePanel `type` | Parent | Test to apply |
|---|---|---|---|
| Person | `actor` | domain root | A human or role that uses the system |
| Software system | `system` | domain root | Delivers value to users; typically what one team owns and deploys together |
| Container (application) | `app` | `system` | A **runtime** boundary. Individually runnable and deployable. Web/mobile/desktop apps, services, serverless functions, batch jobs, shell scripts |
| Container (data store) | `store` | `system` | Databases, caches, blob/content stores, file systems |
| Component | `component` | `app` or `store` | Grouped functionality behind an interface, running **in the same process** as its container |
| — | `group` | `domain` or another `group` | Purely visual clustering. Often used for deployment regions, nodes or layers. Apps and stores **join** a group through `groupIds`, never `parentId` — see [Groups](#groups) |

A JAR, DLL, assembly, package, namespace or folder is **not** a container and usually not a component. Those are organisational, not runtime, boundaries. Containers have nothing to do with Docker.

### Groups

A group is visual clustering: a deployment region, a node, a layer. It is the one type whose containment does **not** run through `parentId`, and assuming it does costs a failed import.

- **A group's own `parentId` is a `domain` or another `group`** — never a `system`. Parenting a group to a system fails with `System is not allowed as a parent of group (allowed: domain, group)`.
- **Apps and stores never parent to a group.** Their `parentId` stays the `system`; parenting one to a group fails with `Group is not allowed as a parent of store (allowed: system)`. They join a group through **`groupIds`**, a list that sits alongside the C4 hierarchy rather than inside it.

So a group sits beside the system in the tree, while its members stay inside the system:

```json
{ "id": "g-region-primary", "name": "Primary Region", "type": "group", "parentId": "d-aws",
  "caption": "Write and read region",
  "description": "The primary region, and the only one that accepts writes." },

{ "id": "g-data", "name": "Data Layer", "type": "group", "parentId": "g-region-primary",
  "caption": "Authoritative projections",
  "description": "The authoritative read and write models in the primary region." },

{ "id": "store-single-view", "name": "Single View", "type": "store", "parentId": "s-platform",
  "groupIds": ["g-data", "g-region-primary"],
  "caption": "Consolidated read model",
  "description": "One consolidated view of each business entity, served at low latency." }
```

`groupIds` accepts several groups, so **name every group whose boundary should enclose the object** rather than relying on the nesting to imply the outer one — that is why `store-single-view` above lists `g-data` and `g-region-primary` both. A group's area on a diagram is sized around the members it can see there, so an object that names only the inner group risks leaving the outer boundary empty on any diagram that draws it.

Two import mechanics follow from groups being parented rather than referenced:

- **A nested group cannot be created in the same request as its parent group.** The child fails with `Parent <x> not found` even when the parent sits earlier in the same file. Import groups in two passes: parent groups first, then the nested ones.
- Because `parentId` resolves against the file alone, that second pass must **re-declare the parent group** next to the nested one. See [Step 3: import](#step-3-import).

On a diagram a group is an `area`, exactly like a system boundary, and IcePanel insets each nesting level itself — see `references/layout.md`.

Set `external: true` on third-party systems the user doesn't own (SaaS, identity providers, managed model endpoints). Externally-hosted services the system *does* own and control (its own S3 bucket, its own RDS instance) are its containers, not external systems.

Give every object **both** text fields. They are not duplicates and they show up in different places:

- `caption` — the *display description*. A few words summarising the object, shown under its name on diagrams and in the model tree. Write it as a label, not a sentence: no trailing full stop. "Browser client", "Managed Postgres", "Quarterly ratings and standings".
- `description` — the detailed one. One or two sentences on what it does and why it exists, read when someone opens the object.

A model without descriptions is much less useful than it looks; one without captions reads as a wall of bare names on every diagram.

```json
{ "id": "store-league", "name": "League Database", "type": "store", "parentId": "s-deadball",
  "caption": "Managed Postgres",
  "description": "Holds players, games, goals and the rating history. Reached through the connection pooler." }
```

Connections take no caption — their name is already the label.

### Technologies and icons

Optional, and worth doing: the catalog has a technology for most languages, frameworks, protocols and managed services. Attaching them puts a logo on the object in every diagram and makes the model searchable by stack. If nothing in the catalog genuinely matches an object, skip it.

`fields` is required and shapes the response. Ask for the few that decide the choice. `name`, `description` and `websiteUrl` are what tell you whether a row is the technology you mean; add `restrictions` and `iconUrlLight`/`iconUrlDark` because the mechanics below depend on them. `id` always comes back. The rows come back under `catalogTechnologies`, not `technologies`.

```bash
curl -sS -H "X-API-Key: $ICEPANEL_TOKEN" -G "https://api.icepanel.io/v1/catalog/technologies/select" \
  --data-urlencode 'search=postgres' --data-urlencode 'limit=5' \
  --data-urlencode 'fields[]=name' --data-urlencode 'fields[]=description' \
  --data-urlencode 'fields[]=websiteUrl' --data-urlencode 'fields[]=restrictions' \
  --data-urlencode 'fields[]=iconUrlLight' --data-urlencode 'fields[]=iconUrlDark'
```

Once you know the exact name, `filter[name][]=PostgreSQL` beats a search. Then set one technology as `icon` and list them all in `technologyIds` — the icon is **not** implied, so repeat it if it should also count as a technology:

```json
{ "id": "store-db", "name": "Workspace Database", "type": "store", "parentId": "s-tld",
  "icon": { "technologyId": "6MZFjMqn4mLaL59WGjTW" },
  "technologyIds": ["6MZFjMqn4mLaL59WGjTW", "AtAwOo48GPChCWOkPkkj"] }
```

On import `icon` is `{"technologyId": ...}`, not the `{catalogTechnologyId, name, urlLight, urlDark}` object that reads back.

Four things to keep in mind:

- **Only a technology that has an icon can be one.** Request `iconUrlLight`/`iconUrlDark` and check they aren't null. WebSocket and JSON-RPC have none — the import accepts the icon and silently drops it.
- **`restrictions` is the list of object types a technology belongs on.** Golang is `app, component, group`; PostgreSQL is `group, store`; GitHub is `group, system`. Nothing enforces it, but aim to follow the restrictions unless the user overrides it.
- **A name match is not an identity match.** Searching `bun` returns the JavaScript runtime, not the Go ORM of the same name. Read the `description` to verify.
- **Near-duplicates and junk rows exist** — two identically-named `approved` "Vite" entries, names like `tech-b811ae65` with placeholder descriptions. `websiteUrl` is the tiebreak: prefer the row pointing at the real project over the one with none.

Tag what differentiates. Putting the one language everything is written in on all 40 objects says nothing; put it on the containers where it is the point and leave the rest clean.

## Step 2: create connections

**A connection is drawn per diagram.** Model connections inherit up and down the hierarchy, so a connection authored between two components is *available* on the app and context diagrams via the containing objects. But it only appears on a diagram if you explicitly put it there.

**Always author a connection from the initiator to the receiver**, and name it so it reads as a sentence across the arrow: *origin → name → target*. "API Gateway" + "Sends requests to" + "Agent Runtime". Prefer `outgoing` and model whoever really starts the exchange; reach for `bidirectional` only when both sides genuinely initiate.

**Keep names to a few words.** A connection name is a label on a line, not a summary of the integration. Level 2 and 3 names are mostly a small set of verb phrases:

> Sends requests to · Fetches data from · Reads from · Writes to · Publishes events to · Subscribes to · Authenticates with · Uploads files to

Level 1 is read by a business audience, so the verb is about outcome rather than mechanism — "Signs in users with", "Tracks match results in" — but it stays just as short. Put the detail in the connection's `description` if it matters; that is what it is for.

A model connection holds one name, so when the right wording genuinely differs by level, author a **separate connection at each level** (e.g. `system → external system` for L1 and `app → external system` for L2) rather than stretching one label across all three. Reuse a single connection across levels only when one phrasing honestly serves every audience.

Required fields: `id`, `name`, `direction` (`outgoing` or `bidirectional`), `originId`, `targetId`. Optional `description`, `status`, `viaId` for a connection that passes through an intermediary.

## Step 3: import

`POST /landscapes/{id}/versions/latest/import` with `modelObjects`, `modelConnections`, and optionally `tags`, `tagGroups`, `namespace`.

The `id` on each entry is **your own key**, not IcePanel's. Import is an idempotent upsert on that key, so re-running the same file updates rather than duplicates. Use stable, readable slugs (`app-api-gateway`, `conn-gateway-idp`) because they are the join key on every future run. Set `namespace` when the landscape is fed by more than one source.

`prune=true` **permanently deletes** everything absent from the file (limited to the namespace if set). Never pass it unless the user explicitly asks for a destructive sync.

Import is asynchronous — poll `GET /import/{importId}` until `status` is `completed` or `error`, and read the `errors` array, which is where failures surface rather than in the initial response. A failed import can still leave part of the file applied, so check `GET /model/objects` rather than assuming a clean slate.

Re-importing a subset is fine but has two traps. `parentId` still resolves only within the file, so include the whole parent chain up to the `domain` — and when you rebuild that file from `GET /model/objects`, the domain's `import-original-id` sits on its `root` object, which you must write back as `type: "domain"`. Second, an omitted `icon` is **cleared**, while an omitted `caption`, `description` or `technologyIds` is preserved. Re-send the icon for every object you touch.

**Nested groups need their own pass.** A group parented to another group fails with `Parent <x> not found` when both are created in the same request, even with the parent earlier in the array — and because that failure cascades to every object listing the nested group in `groupIds`, and to their components, it takes a large part of the file down with it. So when the model has groups inside groups, import in three passes:

```bash
python scripts/icepanel.py import <landscapeId> groups-top.json    # domain + top-level groups
python scripts/icepanel.py import <landscapeId> groups-nested.json # nested groups, parents re-declared
python scripts/icepanel.py import <landscapeId> model.json         # everything, groups included
```

Each pass re-declares the parents it hangs from, since `parentId` resolves against the file alone. Flat groups need none of this — one pass does it.

```bash
python scripts/icepanel.py import <landscapeId> model.json
```

## Step 4: create diagrams

Fetch the ID map first. Diagram content references IcePanel's IDs, not yours:

```bash
python scripts/icepanel.py idmap <landscapeId>
```

| Diagram `type` | C4 | `modelId` points at |
|---|---|---|
| `context-diagram` | L1 | the **domain root** |
| `app-diagram` | L2 | the `system` being opened up |
| `component-diagram` | L3 | the `app` or `store` being opened up |

Diagram connections take **model object IDs** for `originId`/`targetId` (the objects visible at that level) and the **model connection ID** for `modelId`. A connection with a null `modelId` is drawn on the diagram but backed by nothing in the model. Don't create them.

### A diagram tells one story

The model is the complete graph; a diagram is an argument made from it. Omitting a connection loses nothing. It stays in the model and on other diagrams, so draw only the ones relevant to the story. 

It's tempting to create a bloated diagram, instead of a succinct one. `index` allows several per level, so split a crowded level by what each part explains: the authoring path, the analysis pipeline, the sync path, reusing the same model objects and connections across them.

Past roughly a 15-20 connections, or a box fanning out across the canvas, stop placing and reconsider the cut. Crossed lines usually mean too much on the diagram rather than bad placement.

Set `description` in the create call rather than patching afterwards. If you can't state the story in one sentence, the diagram is carrying more than one.

Write a layout spec and let the script handle ID resolution, validation and posting:

```bash
python scripts/icepanel.py diagram <landscapeId> l2.json
```

Sizes and line routing are IcePanel's job, not yours: omit `width`/`height` on boxes and areas, and omit `originConnector`, `targetConnector`, `lineShape` and `labelPosition` on connections. All of them are computed from the geometry. **Placement is the entire lever you have** — if lines look wrong, move boxes.

Read `references/layout.md` before placing anything. It has the grid, the boundary maths, the spec format, and how to place rows so the routing comes out readable.

## Step 5: verify

```bash
python scripts/icepanel.py verify <landscapeId>
```

This checks for overlapping boxes, objects that escape their boundary area, and diagram connections with no model connection behind them. Layout still needs a human eye, so tell the user what you chose and where you were guessing.

**Don't open the app in a browser to inspect the diagram.** `verify` is the whole check. There is no server-side render, viewing needs a logged-in session, and judging the layout is the user's job, not yours. Once `verify` passes you are done.

Give them the landscape link: `https://app.icepanel.io/landscapes/{landscapeId}`.

## Reference

- `references/example.md` — a complete three-level build: import file, diagram spec, command sequence
- `references/layout.md` — grid, boundaries, line routing, diagram spec format
- `references/api.md` — endpoints, full schemas, enum values, and the places the published docs are wrong

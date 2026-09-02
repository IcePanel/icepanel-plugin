# IcePanel API reference

Base URL `https://api.icepanel.io/v1`. Official docs: [https://developer.icepanel.io](https://developer.icepanel.io)

## Contents

- [Important notes](#important-notes)
- [Auth and scoping](#auth-and-scoping)
- [Landscapes and domains](#landscapes-and-domains)
- [Import](#import)
- [Model objects and connections](#model-objects-and-connections)
- [Diagrams](#diagrams)
- [Enum values](#enum-values)

## Important notes

1. **Auth is** `X-API-Key` **alone.** The reference lists both `X-API-Key` and `Authorization` as required. Sending both returns `401 auth/invalid-access-token`.
2. **"Required, nullable" means the key must be present.** `modelId`, `originId` and `targetId` on a diagram connection are all marked this way: you must send the key, but `null` is an accepted value. That's how a connection with no model behind it becomes possible.
3. **Import errors don't surface in the initial response.** It returns `in-progress`; per-entity failures appear in the `errors` array once the poll returns `completed` or `error`.
4. `parentId` **in an import file is resolved against that file only.** It matches the `id` of another entry in the same `modelObjects` array — nothing else. Passing a real IcePanel object ID, a domain ID, or a domain name all fail with `Parent <x> not found`. This means top-level objects can only be parented to a `domain` object you include in the import.
5. **Responses are wrapped in a resource-keyed envelope, and the key is not always the path's plural.** `/catalog/technologies/select` returns `catalogTechnologies`, not `technologies`; `/import` returns `landscapeImport`; `/diagrams/{id}/content` returns `diagramContent`. Read the key from the response rather than assuming it.



## Auth and scoping

```
X-API-Key: <key-id>:<secret>
```

Most routes are scoped to a landscape and version:

```
/v1/landscapes/{landscapeId}/versions/{versionId}/{resource}
```

`versionId` accepts `latest` (live, editable) or a numbered snapshot ID (immutable).

The hierarchy is Organization → Landscape → Version → {Domains, Model objects, Connections, Diagrams, Flows}.

## Landscapes and domains

- `GET /organizations` — find `organizationId`
- `POST /organizations/{orgId}/landscapes` — `{"name": "..."}`; returns landscape + initial version
- `GET /landscapes/{id}/versions/latest/domains`
- `PATCH /landscapes/{id}/versions/latest/domains/{domainId}` — rename a domain
- `DELETE /landscapes/{id}/versions/latest/domains/{domainId}` — remove the empty default domain after importing your own

`GET /domains` lists each domain's own fields and **no child list**, so you cannot spot the empty one from that response alone. Identify it by name (`Default domain`) or diff against `GET /model/objects`: the leftover is the `domainId` that owns nothing but its own `root`.

Every domain has exactly one `root` object, and that root's ID is a context diagram's `modelId`. **The root ID is not always the domain ID.** For a domain created by import they happen to match; for the "Default domain" a new landscape ships with, they differ — its root is a separate ID with an empty `name`. Don't derive one from the other. Read the root from `GET /model/objects` (`type: "root"`, matching `domainId`), or let the helper script's `@root` resolve it, which picks the root that actually has children.

## Import

`POST /landscapes/{landscapeId}/versions/{versionId}/import`

Query: `prune` (boolean) — **permanently deletes** anything absent from the file, limited to `namespace` when set.

Body: `modelObjects`, `modelConnections`, `tags`, `tagGroups`, `namespace`.

IDs in the file are **your own**. Import upserts on them, so re-running is idempotent. IcePanel stores them as labels on each entity:

```json
"labels": {
  "imported": "true",
  "import-namespace": "claude-import",
  "import-original-id": "app-api-gateway"
}
```

That label is how you map your slugs back to IcePanel IDs afterwards.

Poll `GET /landscapes/{landscapeId}/versions/{versionId}/import/{importId}` until `status` is `completed` or `error`. Errors carry `message`, `entityOriginalId` and `entityType`.

`status: "error"` is not all or nothing, entities that validate are still applied, so a failed import can leave partial state behind. Check `GET /model/objects` after an error.

Entity errors carry `entityId` (your import ID) — not `entityOriginalId`, which the published docs suggest.

On a partial re-import, an omitted `icon` is cleared while an omitted `caption`, `description`, `tagIds` or `technologyIds` is preserved.

### modelObjects

Required `id`, `name`, `type`. Optional: `parentId`, `description`, `caption`, `external`, `groupIds`, `teamIds`, `tagIds`, `technologyIds`, `status`, `labels`, `icon`, `links`.

`icon` is `{"technologyId": "<catalog technology id>"}` — the import shape only. It reads back as `{catalogTechnologyId, name, urlLight, urlDark, url}`, and `url` is deprecated. Setting a technology that has no icon asset succeeds and silently leaves the object without one. `technologyIds` is independent: the icon's technology is not added to it.

`caption` is the **display description**: a few words rendered under the object's name on every diagram and in the model tree. `description` is the **detailed description**, one or two sentences, read when someone opens the object. They serve different readers — set both on every object. Connections have a `description` but no `caption`.

Hierarchy (`parentId`): `domain` → `actor` | `system` | `group`; `group` → `group`; `system` → `app` | `store`; `app` | `store` → `component`.

A `system` **cannot** parent a `group`, and a `group` cannot parent anything but another `group`. Group membership for apps and stores is `groupIds` — a list of group IDs on the member object, resolved against the same file like any other reference — while the member's `parentId` stays its `system`. List every group whose boundary should enclose an object, inner and outer both, rather than relying on nesting to imply the outer one. A nested group also cannot be created in the same request as its parent group (`Parent <x> not found`), so import parent groups in one pass and nested groups in a second that re-declares the parent. See **Groups** in `SKILL.md`.

Top-level objects take the `id` of a `domain` entry in the same file as their `parentId` (see note 4 above). The import creates that domain and its `root` object together.

### modelConnections

Required `id`, `name`, `direction`, `originId`, `targetId`. Optional: `description`, `status`, `viaId`, `tagIds`, `technologyIds`, `labels`, `links`.

### tags / tagGroups

Tags require `id`, `name`, `color`, `groupId`. Tag groups require `id`, `name`, `icon`.

`icon` on a tag group is a **named icon string**, not an emoji — `star` is the safe default. Tag `color` is one of the values in [Enum values](#enum-values).

## Catalog technologies

`GET /catalog/technologies/select` — the shared technology catalog, used to fill `technologyIds` and `icon`. Rows come back under `catalogTechnologies` (see note 5 above), each carrying `id` plus whichever `fields` you asked for.


| Query                                                                                | Notes                                                                                                                                                                              |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fields`                                                                             | **Required**, repeat as `fields[]=`. Controls the response shape — request only what you need, since the full set is mostly provider plumbing. `id` is always returned regardless. |
| `search`                                                                             | Fuzzy match on name.                                                                                                                                                               |
| `filter[name][]`                                                                     | Exact name match, up to 30. Cheaper and safer than `search` when you know the name.                                                                                                |
| `filter[type][]`, `filter[provider][]`, `filter[restrictions][]`, `filter[status][]` | Up to 30 each.                                                                                                                                                                     |
| `limit`                                                                              | Defaults to 1000, max 10000.                                                                                                                                                       |
| `cursor`                                                                             | Paginate via `nextCursor` in the response.                                                                                                                                         |


Useful `fields` values: `name`, `description` and `websiteUrl` to judge whether a row is the right technology; `restrictions` and `iconUrlLight`/`iconUrlDark` for where it can go and whether it can be an icon; then `nameShort`, `type`, `provider`, `docsUrl`, `status` as needed. The rest (`awsXmlSelector`, `updatesXmlUrl`, `createdBy`, `rejectionReason`, …) are noise for this job.

- `type` — `data-storage`, `deployment`, `framework-library`, `gateway`, `language`, `message-broker`, `network`, `other`, `protocol`, `runtime`, `service-tool`, or `null`. Often null, so don't filter on it expecting completeness.
- `restrictions` — the object types the technology belongs on: `actor`, `app`, `component`, `connection`, `group`, `store`, `system`. Advisory; the import does not enforce it.
- `iconUrlLight` / `iconUrlDark` — null for plenty of entries. A technology with both null cannot serve as an object's `icon`.

Connections take `technologyIds` too, and `connection` appears in `restrictions` for the protocol-ish entries.

## Model objects and connections

- `GET /landscapes/{id}/versions/latest/model/objects`
- `GET /landscapes/{id}/versions/latest/model/connections`
- `POST`/`PATCH`/`PUT` equivalents exist for single-entity work, but import is better for anything bulk because it's idempotent.



## Diagrams

`POST /landscapes/{landscapeId}/versions/{versionId}/diagrams`

Required: `name`, `type`, `modelId`, `index`. Optional: `description`, `status`, `objects`, `connections`, `groupId`, `parentId`, `handleId`, `labels`, `zoomOverrides`, `pinned`.

`index` orders diagrams within a level; several diagrams per level are allowed.

`modelId`: domain root for `context-diagram`, the `system` for `app-diagram`, the `app`/`store` for `component-diagram`.

`objects` and `connections` are **maps**, not arrays. Keying each entry by its own `id` is simplest, and using the model object / model connection ID as that key keeps everything traceable.

### Diagram object

```json
{
  "id": "<key>",
  "modelId": "<model object id>",
  "type": "actor|app|component|group|store|system",
  "shape": "box|area",
  "x": 192, "y": 400
}
```

`id`, `modelId`, `type`, `shape`, `x` and `y` are required. `width` **and** `height` **are optional on both shapes — leave them out.** A box then gets IcePanel's default size (256 × 128), and an area is grown around whichever children are on the diagram, with room for its title. Send a size only for a deliberately off-default box; a hand-sized area just goes stale the moment a child moves.

### Diagram connection

```json
{
  "id": "<key>",
  "modelId": "<model connection id>",
  "originId": "<model OBJECT id>",
  "targetId": "<model OBJECT id>"
}
```

That is the whole thing. `originId`/`targetId` are model **object** IDs (the objects visible at that level), while `modelId` is the model **connection**. All three are "required, nullable": send the key, `null` is accepted. A null `modelId` means a line with nothing behind it in the model, which is drift.

**Routing is computed server-side**, so `originConnector`, `targetConnector`, `lineShape` and `labelPosition` are all optional — omit them and IcePanel chooses the attachment points, line shape and label position from the geometry. They remain accepted as per-line overrides: `labelPosition` is the percentage along the line where the label sits (`0`–`100`, `50` centres it), and the anchors are listed under [Enum values](#enum-values). There is also a deprecated `points` field: leave it alone.

### Other diagram routes

- `GET /diagrams/{id}/content` — read back objects/connections
- `PUT /diagrams/{id}/content` — replace content
- `PATCH /diagrams/{id}` — update metadata such as `description`
- `GET /diagrams/{id}/thumbnail` — returns a signed URL, but thumbnails render lazily in the app, so it 404s (`NoSuchKey`) for a diagram nobody has opened. There is no server-side render to verify layout with; check geometry numerically and have a human look.



## Enum values


| Field                           | Values                                                                                                                                                                       |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| model object `type`             | `domain`, `root`, `actor`, `system`, `app`, `store`, `component`, `group`                                                                                                    |
| object / connection `status`    | `live`, `future`, `deprecated`, `removed`                                                                                                                                    |
| connection `direction`          | `outgoing`, `bidirectional`                                                                                                                                                  |
| diagram `type`                  | `context-diagram`, `app-diagram`, `component-diagram`                                                                                                                        |
| diagram `status`                | `current`                                                                                                                                                                    |
| diagram object `shape`          | `box`, `area`                                                                                                                                                                |
| `lineShape` (optional override) | `curved`, `straight`, `square`                                                                                                                                               |
| connectors (optional override)  | `top-left`, `top-center`, `top-right`, `right-top`, `right-middle`, `right-bottom`, `bottom-right`, `bottom-center`, `bottom-left`, `left-bottom`, `left-middle`, `left-top` |
| tag `color`                     | `blue`, `green`, `yellow`, `orange`, `red`, `beaver`, `dark-blue`, `purple`, `pink`, `white`, `grey`, `black`                                                                |


There is no code-level (C4 level 4) diagram type.
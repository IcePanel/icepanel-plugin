# Structurizr DSL to IcePanel mapping

Every rule the parser applies, and why. Read this before interpreting `report.md` or hand-editing `model.json`.

## Contents

- [Elements](#elements)
- [The container problem](#the-container-problem)
- [External systems](#external-systems)
- [Groups and the enterprise boundary](#groups-and-the-enterprise-boundary)
- [Deployment](#deployment)
- [Relationships](#relationships)
- [Text fields and tags](#text-fields-and-tags)
- [Views](#views)
- [Six ways a literal reading goes wrong](#six-ways-a-literal-reading-goes-wrong)

## Elements


| Structurizr              | IcePanel `type`      | Notes                                                 |
| ------------------------ | -------------------- | ----------------------------------------------------- |
| `person`                 | `actor`              | Parent is the domain                                  |
| `softwareSystem`         | `system`             | Parent is the domain                                  |
| `container`              | `app` **or** `store` | See below. This is the one real ambiguity             |
| `component`              | `component`          | Parent is an `app` or `store`                         |
| `group`                  | `group`              | Nests through `parentId`; members join via `groupIds` |
| `deploymentNode`         | `group`              | Nests the same way                                    |
| `infrastructureNode`     | `app`                | Parent system is inferred; joins its node's `groupIds` |
| `softwareSystemInstance` | none                 | Not an object. The system joins the node's groups     |
| `containerInstance`      | none                 | Not an object. The container joins the node's groups  |
| `element` (custom)       | none                 | Sits outside C4 by design; dropped and reported       |
| workspace                | `domain`             | Named from the workspace, or `--domain`               |


Archetypes are resolved before any of this. `application = container` means an `application` **is** a container, and its default technology and tags are applied to every element declared with it. Archetypes extend each other, so scalars come from the nearest one in the chain and tags accumulate along it.

## The container problem

**Structurizr has no data-store element type.** IcePanel has `app` and `store`, and something has to decide which. Four signals, in order, and the first two are worth far more than the last two because the author stated them deliberately:

1. **A tag the styles block gives a store shape.** The author saying outright that this thing is drawn as a cylinder:
  ```
   database = container "Database" "…" "Oracle Database Schema" "Database"
   …
   element "Database" { shape Cylinder }
  ```
   The parser collects every tag whose element style sets `shape` to `Cylinder`, `Bucket` or `Pipe`, and any container carrying one becomes a `store`.
2. **An archetype named after a data store.** An archetype is a user-defined type, so naming one `datastore` is the author building the distinction Structurizr lacks:
  ```
   archetypes {
       service   = container
       datastore = container
       queue     = container
   }
   ledger = datastore "Ledger"
  ```
   `Ledger` is a `store`, and it would be one even with no name, no technology and no styles in the whole workspace. The archetype name is split on camelCase and underscores first, so `dataStore`, `message_queue` and `blobStore` all match, and matching is on whole words, `storefront` is not a store.
3. **The name or technology**, when neither of the above says anything: `database`, `db`, `store`, `cache`, `queue`, `topic`, `bucket`, `schema`, `blob`, `s3`, `redis`, `kafka`.
4. Otherwise it is an `app`.

Every call is listed in the report with the signal that fired, so a `store` from a styled shape or an archetype can be told apart from one that came from a guess at its name. **Confirm all of them.** A message broker is the usual argument. Structurizr authors often shape one as a Pipe or type it with a `queue` archetype, which makes it a store here, and that is normally right: it is on the diagram for holding data.

Signal 3 is a guess and it misfires on names that merely contain a store word. "Store SPA" is a React front end, not a data store. Read every call in that section rather than skimming it.

## External systems

**Structurizr has no external flag.** IcePanel's `external: true` has to come from somewhere, and the only thing in the DSL carrying that intent is a tag. A system or actor tagged `external`, `third party`, `saas` or `vendor` is marked external.

`Existing System` **is not one of them, and neither is** `Legacy`**.** Those mean brownfield: a system that already exists and has to be lived with. A team's own old system is still its own. Big Bank plc tags its mainframe, e-mail system and ATM `Existing System` while building and running all three, and none of them is external. The tag survives as an ordinary IcePanel tag, so the distinction is not lost.

Every call is listed in the report, and so is the case where nothing matched. A workspace that tags no third parties produces a landscape with no external systems, which is worth saying out loud rather than leaving the user to notice.

## Groups and the enterprise boundary

Structurizr groups only ever hold elements of one level: people and systems at the model, containers inside a system, components inside a container. They nest.

IcePanel groups work differently in one way that costs a failed import if you assume otherwise:

- **A group's own** `parentId` **is a domain or another group**, never a system. So a group of containers sits *beside* the system in the tree while its members stay parented to that system. Counterintuitive, correct.
- **Members join through** `groupIds`, listing *every* enclosing group, inner and outer both. A group's area on a diagram is sized around the members it can see there, so an object naming only the inner group would leave the outer boundary empty.

**A model-level group with the workspace's own name is the enterprise boundary, and becomes the domain rather than a group.** `workspace "Big Bank plc"` containing `group "Big Bank plc"` means one thing, not two, and IcePanel already has a name for it. Its members reparent to the domain. This is reported.

## Deployment

A `deploymentEnvironment` is a parallel description of the same containers, not new ones. So:

- Every `deploymentNode` becomes a nested `group`.
- Every `infrastructureNode` becomes an `app`. Load balancers, DNS, firewalls and message brokers are running things, not boundaries, so they are modelled like any other container: the node chain they sit in becomes their `groupIds`, and they are drawn as boxes inside those node boundaries.
- `containerInstance x` and `softwareSystemInstance x` create **nothing**. They add the node's group chain to the `groupIds` of the element being deployed.
- An identifier bound to an instance resolves to that element, so `elb -> webApplicationInstance` lands on the real container.

**An infrastructureNode's system is inferred.** Structurizr puts nothing above one but deployment nodes, and an IcePanel `app` must parent to a `system`. The parser takes the system whose containers are deployed in that environment, and where several are, the one with the most of them. That is the same rule a landscape-wide deployment view uses to pick its subject. Every call is reported. When the environment deploys nothing there is no system to infer, and the node is skipped rather than guessed at.

Shared infrastructure is where this gets argued with. A Route 53 zone or an ELB fronting three systems is not owned by whichever one happens to deploy the most containers. The report names the system chosen for each node, so re-parent them at the confirmation gate when the landscape has a better home.

**One environment per import.** Two environments describe the same containers deployed twice, and merging them puts one object in two unrelated group trees. When a workspace defines more than one, the parser stops and lists them; pass `--environment NAME`.

**A deployment view is always an app diagram.** It is full of containers, and containers belong at Level 2; a context diagram would be the wrong altitude. A view scoped to a software system takes that system as its subject and draws only that system's containers, leaving other systems' instances off and reporting each one. A landscape-wide `deployment * <env>` has no scope to take a subject from, so the system owning most of what is drawn becomes it, and the other systems' containers sit outside its boundary. Both cases are reported.

**A view names its environment by name or by identifier.** `deployment s live` and `deployment s "Live"` are the same view, because `live = deploymentEnvironment "Live"` binds one to the other. A view for an environment other than the one being imported is skipped and reported.

**A container deployed onto several nodes in one environment** is the awkward case, and Big Bank plc has it: one `database` on both `Oracle - Primary` and `Oracle - Secondary`. IcePanel has one model, so it is one object, and one box cannot sit inside two boundaries. The default keeps a single object in every one of those groups and draws it inside the first. `--split-instances` makes one object per node instead (`Database (Oracle - Primary)`, `Database (Oracle - Secondary)`), where the first keeps every connection authored against the original. Put the choice to the user: a primary and a replica are arguably two stores, three instances behind a load balancer are one.

## Relationships


| Structurizr                   | IcePanel                                                    |
| ----------------------------- | ----------------------------------------------------------- |
| `a -> b "desc" "tech" "tags"` | `direction: outgoing`, origin `a`, target `b`               |
| `-> b` inside an element      | Origin is the element in scope                              |
| `this -> b`, `a -> this`      | Same, on either side of the arrow                           |
| `a --https-> b`               | Relationship archetype; its technology and tags are applied |
| `a -/-> b`                    | Relationship removal. Not supported, reported               |
| `?technology`                 | `technologyIds` on the connection, after a catalog lookup   |


Structurizr is strictly unidirectional and explicitly refuses bidirectional arrows, so every connection is `outgoing` and nothing needs reversing.

**Implied relationships are never created.** Structurizr generates them by default, so `u -> webapp` also creates `u -> softwareSystem`, but they exist only in a compiled workspace and IcePanel does not want them. Model connections inherit up the hierarchy natively, so a component-level connection is already available on the app and context diagrams above. The parser reads only what the author wrote, and the diagram builder lifts each endpoint to whatever is visible at that level. Expect fewer connections than a JSON import would have produced. That is correct, not missing.

Where several relationships lift onto the same pair at one level, say six calls from the single-page application to three controllers all becoming `Single-Page Application` to `API Application`, the diagram draws one line and the report says how many were folded. The model keeps them all.

## Text fields and tags

- `description` **→** `description`, verbatim, on elements and connections both.
- `caption` **is trimmed from the description**: the first clause, at most eight words, no trailing full stop. It renders under the object's name on every diagram, so it reads as a label and not a sentence.
- `technology` **→** `technologyIds` **and** `icon` **only.** Never the caption, never the description. One string is often several: split `"Java and Spring MVC"` before looking each part up.
- `url` **→** `links`**.**
- Groups have no description field in Structurizr at all, so every group and deployment node arrives with none and needs one written. An `infrastructureNode` does take a description, but authors rarely write one.

Tags are kept when they carry meaning and dropped when their meaning has already been absorbed:


| Tag                                                                   | What happens                         |
| --------------------------------------------------------------------- | ------------------------------------ |
| Styled with a store shape (`Database`)                                | Dropped. It became the `store` type  |
| Matching the external hints (`Third Party`, `SaaS`)                   | Dropped. It became `external`        |
| Styled with nothing but a shape or icon (`Web Browser`, `Mobile App`) | Dropped. Pure notation               |
| Structurizr's own (`Element`, `Container`, ...)                       | Dropped. The type already says it    |
| Anything else (`Customer`, `Bank Staff`, `Failover`)                  | Kept, in a `Structurizr` tag group   |


Both lists are in the report. Prune the kept ones before importing.

## Views


| Structurizr view                         | IcePanel diagram `type` | `modelId`                         |
| ---------------------------------------- | ----------------------- | --------------------------------- |
| `systemLandscape`                        | `context-diagram`       | the domain root (`@root`)         |
| `systemContext <ss>`                     | `context-diagram`       | `@root`                           |
| `container <ss>`                         | `app-diagram`           | that system                       |
| `component <container>`                  | `component-diagram`     | that app or store                 |
| `deployment <ss> <env>`                  | `app-diagram`           | that system; only its containers  |
| `deployment * <env>`                     | `app-diagram`           | the system owning most of it      |
| `dynamic`, `filtered`, `custom`, `image` | none                    | skipped, each reported            |


A landscape view and one or more system context views all land on the same domain root; `index` orders them, so they coexist as separate Level 1 diagrams telling different stories.

**Contents come from** `include` *, whose meaning differs per view type. The scoped system plus everything directly connected, all containers plus connected people and systems, all components plus connected people, systems and containers. Naming elements explicitly (`include webapp database`) works too, as does `exclude` on named elements.

What does not work is an expression, `include "element.tag==Microservice"` and its relatives, which query the model rather than list it. Those are reported and that view falls back to `include *`. Because an expression is nearly always a filter narrowing the wildcard, the diagram ends up showing more than the author asked for; an unevaluated `exclude` expression puts back something they deliberately removed. The model is unaffected, so this is a per-diagram cleanup, not a modelling problem.

**Deployment diagrams rank by node, not by request path.** Everything on one node shares a row, so its area wraps a contiguous span. Every other diagram ranks by the request path through the subject, with initiators at the top.

**Structurizr carries no geometry.** `autoLayout` is an instruction to its renderer, not a set of coordinates, and coordinates only ever live in a compiled `workspace.json`. All placement here is generated on the 384 × 320 pitch from `creating-c4-diagrams/references/layout.md`.

## Six ways a literal reading goes wrong

1. **A container is not always an app.** Structurizr has one container type and IcePanel has two. Read the styles block, not the keyword.
2. `Existing System` **does not mean external.** It means existing. Big Bank plc builds and runs its own mainframe. Only a tag saying somebody else owns the thing (`External`, `Third Party`, `SaaS`, `Vendor`) sets IcePanel's external flag.
3. **Names collide domain-wide.** Structurizr scopes uniqueness per parent (container names within a system, component names within a container), and `!identifiers hierarchical` exists so `ss1.api` and `ss2.api` can coexist. IcePanel requires uniqueness across the whole domain, so those get suffixed with the parent that tells them apart.
4. **An instance is not an object.** `containerInstance database` does not make a second database. Creating one doubles the model.
5. **Positional arguments shift.** `deploymentNode "bigbank-web***" "" "Ubuntu 16.04 LTS" "" 4` is name, empty description, technology, empty tags, instance count. Miscount and the technology lands in the tags slot.
6. **A group of containers cannot be parented to its system.** IcePanel rejects it. The group sits beside the system; the members stay inside it and join through `groupIds`.


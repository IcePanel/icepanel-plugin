# Worked example

A context map of a commerce landscape, taken from a whiteboard photo. Seven bounded contexts, one Big Ball of Mud, and one relationship that gets deliberately dropped.

## What the map showed

Contexts drawn as circles: **Orders**, **Shipping**, **Billing**, **Payments Gateway**, **Catalogue**, **Search**, **Marketing**. One cloud labelled **Legacy CRM**, tagged `BBoM`.

The relationship table built in Step 1, and confirmed with the user in Step 2:


| From             | To        | Style       | U/D                   | Markers (which end)              | Line label                                |
| ---------------- | --------- | ----------- | --------------------- | -------------------------------- | ----------------------------------------- |
| Orders           | Shipping  | thin solid  | Orders=U, Shipping=D  | `OHS` @ Orders, `ACL` @ Shipping | —                                         |
| Orders           | Billing   | thin solid  | Orders=U, Billing=D   | `OHS` @ Orders, `CF` @ Billing   | —                                         |
| Payments Gateway | Billing   | thin solid  | Payments=U, Billing=D | `OHS + PL` @ Payments            | `CUS --> SUP` pointing Billing → Payments |
| Catalogue        | Search    | thick solid | —                     | `SK` straddling the line         | —                                         |
| Legacy CRM       | Orders    | thin solid  | CRM=U, Orders=D       | `ACL` @ Orders                   | —                                         |
| Orders           | Marketing | dotted      | —                     | `SW`                             | —                                         |


The user was asked for a one-line purpose per context in the same message, which is where the captions and descriptions below come from. None of them were inferred from the names.

## The import file

```json
{
  "namespace": "context-map",
  "modelObjects": [
    { "id": "d-commerce", "name": "Commerce", "type": "domain",
      "caption": "Commerce landscape",
      "description": "The commerce product area, as drawn on the team's context map." },

    { "id": "g-orders", "name": "Orders BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Orders bounded context, from the context map." },
    { "id": "s-orders", "name": "Orders", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-orders"],
      "caption": "Order capture and lifecycle",
      "description": "Captures orders and owns their lifecycle through to fulfilment. Publishes an open host service that the rest of the landscape integrates against." },

    { "id": "g-shipping", "name": "Shipping BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Shipping bounded context, from the context map." },
    { "id": "s-shipping", "name": "Shipping", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-shipping"],
      "caption": "Dispatch and carrier booking",
      "description": "Books carriers and tracks dispatch. Translates the Orders model into its own through an anticorruption layer." },

    { "id": "g-billing", "name": "Billing BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Billing bounded context, from the context map." },
    { "id": "s-billing", "name": "Billing", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-billing"],
      "caption": "Invoicing and settlement",
      "description": "Raises invoices and settles payments. Conforms to the Orders model rather than translating it." },

    { "id": "g-payments", "name": "Payments Gateway BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Payments Gateway bounded context, from the context map. Owned by a third party." },
    { "id": "s-payments", "name": "Payments Gateway", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-payments"],
      "external": true,
      "caption": "Third-party payment processing",
      "description": "External payment processor. Exposes a documented API and message format that Billing integrates against." },

    { "id": "g-catalogue", "name": "Catalogue BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Catalogue bounded context, from the context map." },
    { "id": "s-catalogue", "name": "Catalogue", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-catalogue"],
      "caption": "Product data and merchandising",
      "description": "Owns product data and merchandising rules. Shares a product model with Search." },

    { "id": "g-search", "name": "Search BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Search bounded context, from the context map." },
    { "id": "s-search", "name": "Search", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-search"],
      "caption": "Product discovery and indexing",
      "description": "Indexes the catalogue and serves discovery. Shares a product model with Catalogue." },

    { "id": "g-marketing", "name": "Marketing BC", "type": "group", "parentId": "d-commerce",
      "caption": "Bounded context",
      "description": "The Marketing bounded context, from the context map. Drawn with no integration to the rest of the landscape." },
    { "id": "s-marketing", "name": "Marketing", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-marketing"],
      "caption": "Campaigns and promotions",
      "description": "Runs campaigns and promotions on its own data. The team went separate ways from Orders rather than integrating." },

    { "id": "g-legacy-crm", "name": "Legacy CRM BC", "type": "group", "parentId": "d-commerce",
      "caption": "Big Ball of Mud",
      "description": "Drawn as a Big Ball of Mud on the context map: mixed models and inconsistent boundaries, not a well-defined bounded context." },
    { "id": "s-legacy-crm", "name": "Legacy CRM", "type": "system", "parentId": "d-commerce",
      "groupIds": ["g-legacy-crm"],
      "caption": "Legacy customer system",
      "description": "The customer data and account handling inside the legacy CRM. Orders shields itself from this model with an anticorruption layer." }
  ],

  "modelConnections": [
    { "id": "conn-orders-shipping", "name": "Upstream of", "direction": "outgoing",
      "originId": "g-orders", "targetId": "g-shipping",
      "tagIds": ["tag-ohs", "tag-acl"],
      "description": "Orders publishes an open host service; Shipping consumes it behind an anticorruption layer." },

    { "id": "conn-orders-billing", "name": "Upstream of", "direction": "outgoing",
      "originId": "g-orders", "targetId": "g-billing",
      "tagIds": ["tag-ohs", "tag-cf"],
      "description": "Orders publishes an open host service; Billing conforms to its model rather than translating." },

    { "id": "conn-payments-billing", "name": "Upstream of", "direction": "outgoing",
      "originId": "g-payments", "targetId": "g-billing",
      "tagIds": ["tag-ohs", "tag-pl", "tag-cs"],
      "description": "Payments Gateway publishes an open host service with a published language. Billing is the customer in a customer/supplier relationship, so its priorities factor into the gateway's planning." },

    { "id": "conn-catalogue-search", "name": "Mutually dependent", "direction": "bidirectional",
      "originId": "g-catalogue", "targetId": "g-search",
      "tagIds": ["tag-sk"],
      "description": "Catalogue and Search jointly own a shared product model and must be released together." },

    { "id": "conn-legacycrm-orders", "name": "Upstream of", "direction": "outgoing",
      "originId": "g-legacy-crm", "targetId": "g-orders",
      "tagIds": ["tag-acl"],
      "description": "Orders isolates itself from the legacy CRM's model with an anticorruption layer." }
  ],

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
}
```



## The decisions visible in that file

**Six lines on the map, five connections in the model.** `Orders — SW — Marketing` produced nothing. Marketing is still modelled as a context, because it exists; the relationship isn't, because the map says there isn't one.

`conn-payments-billing` **runs against the drawn arrowhead.** The map's `CUS --> SUP` points Billing → Payments, but Payments is `U`. Model influence flows supplier → customer, so the connection is authored Payments → Billing and tagged `C/S`. Following the arrowhead would have inverted it.

`OHS` **appears on three connections** and was one marker on the map — one on Orders, one on Payments Gateway. Orders' single host service serves both Shipping and Billing, so it tags both of those connections.

`OHS + PL` **became two tags**, `tag-ohs` and `tag-pl`, on `conn-payments-billing`.

**Legacy CRM gets a group like every other boundary**, even though it's a Big Ball of Mud rather than a real bounded context. Every named boundary on the map takes the same shape, so there's no special case; what marks it out is the `caption` and `description`, since `BBoM` carries no tag.

**It is also the one connected Big Ball of Mud here**, which is the common case rather than the ideal one. A well-drawn map leaves a BBoM unattached — that's the whole point of naming it — but this one has Orders downstream of it behind an `ACL`, so `conn-legacycrm-orders` is authored like any other relationship. Model what the map draws.

**Catalogue and Search are** `bidirectional` **and named "Mutually dependent"** — a thick line with no `U`/`D` has no direction to author, so the name states the relationship rather than pretending to a verb.

`tag-partnership` **is declared but unused.** The whole tag group is created every run so the vocabulary is complete in the landscape and later maps upsert into it rather than adding to it piecemeal.

**Every system is parented to** `d-commerce`, never to its group. Group membership is `groupIds` only.

**Every connection joins two** `g-` **ids, never two** `s-` **ids.** A context map relationship holds between bounded contexts, and the group is the bounded context; the system inside is a placeholder for containers that haven't been modelled yet. `conn-orders-shipping` runs `g-orders → g-shipping`, so it stays true if Orders is later split into three systems.

**Each group carries a** `BC` **suffix its system doesn't.** `Orders BC` wraps `Orders`. The group and the system are both children of `d-commerce`, and IcePanel rejects two siblings sharing a name — an import with both named `Orders` fails outright, and since import is all-or-nothing, nothing lands at all. The system keeps the map's own name because that is what a reader sees on the box.

## Handing off

The file goes to `creating-c4-diagrams` unchanged:

```bash
python scripts/icepanel.py import <landscapeId> model.json
```

And the handoff message says what the file can't:

> Seven bounded contexts and one Big Ball of Mud, with five relationships. The `Orders — Marketing` separate-ways relationship was dropped deliberately: a connection there would assert an integration the map denies. Connections run upstream → downstream by model influence, so they point the opposite way to the runtime calls — Billing calls the Payments Gateway, but the gateway is upstream of Billing. Every connection is named "Upstream of"; happy to refine those into real verb phrases now the model is visible.


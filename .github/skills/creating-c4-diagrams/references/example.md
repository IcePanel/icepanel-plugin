# Worked example

A trimmed version of a real three-level build: an agent platform used by three teams, with one system opened up into containers, and one container opened up into components.

## The import file

Objects first, ordered parents before children for readability (the API doesn't require it). Every object gets a short `caption` and a fuller `description`. The `domain` entry comes first because `parentId` only resolves against IDs in this same file — top-level objects have nothing else to hang from.

```json
{
  "namespace": "agent-platform",
  "modelObjects": [
    { "id": "d-enterprise", "name": "Enterprise", "type": "domain",
      "caption": "Enterprise AI",
      "description": "The enterprise AI product area." },

    { "id": "a-finance", "name": "Finance Team", "type": "actor", "parentId": "d-enterprise",
      "caption": "Cost analysts",
      "description": "Reviews supplier spend and cost analysis surfaced by the platform." },

    { "id": "s-aip", "name": "Enterprise Agent Platform", "type": "system", "parentId": "d-enterprise",
      "caption": "Governed AI agents",
      "description": "Runs governed enterprise AI agents over enterprise data and tools.",
      "icon": { "technologyId": "Rzc4wgxOTB4iATjc3Cly" },
      "technologyIds": ["Rzc4wgxOTB4iATjc3Cly"] },
    { "id": "s-idp", "name": "Okta / Entra ID", "type": "system", "parentId": "d-enterprise",
      "external": true,
      "caption": "Identity provider",
      "description": "Enterprise identity provider used for authentication and RBAC." },

    { "id": "app-api-gateway", "name": "API Gateway", "type": "app", "parentId": "s-aip",
      "caption": "HTTPS entry point",
      "description": "Single entry point. Authenticates callers and routes requests to agents.",
      "icon": { "technologyId": "FqQvEKtNfW2Q9ue6XQwn" },
      "technologyIds": ["FqQvEKtNfW2Q9ue6XQwn", "20VtuIRnZRytNwM9vvxn"] },
    { "id": "app-agent-runtime", "name": "Agent Runtime", "type": "app", "parentId": "s-aip",
      "caption": "Agent execution service",
      "description": "Executes agents: plans work, calls models and tools, enforces guardrails.",
      "icon": { "technologyId": "fK3P9HZzJS9tIt7J4tlb" },
      "technologyIds": ["fK3P9HZzJS9tIt7J4tlb", "4lzhdnvtb77ySYTU43fX", "nWuWnZHGbVvf4T40CTEM"] },
    { "id": "store-governance", "name": "Governance Store", "type": "store", "parentId": "s-aip",
      "caption": "Audit store",
      "description": "Audit store for agent invocations, decisions and policy violations.",
      "icon": { "technologyId": "AtAwOo48GPChCWOkPkkj" },
      "technologyIds": ["AtAwOo48GPChCWOkPkkj"] },

    { "id": "c-agent-orchestrator", "name": "Agent Orchestrator", "type": "component",
      "parentId": "app-agent-runtime",
      "caption": "Plans and delegates",
      "description": "Builds and drives the agent plan, delegating to the other components." },
    { "id": "c-workflow-engine", "name": "Workflow Engine", "type": "component",
      "parentId": "app-agent-runtime",
      "caption": "Multi-step task runner",
      "description": "Runs multi-step tasks and human approval flows." }
  ],
  "modelConnections": [
    { "id": "conn-l1-finance-aip", "name": "Reviews supplier spend in",
      "direction": "outgoing", "originId": "a-finance", "targetId": "s-aip" },
    { "id": "conn-l1-aip-idp", "name": "Signs in users with",
      "direction": "outgoing", "originId": "s-aip", "targetId": "s-idp" },

    { "id": "conn-finance-gateway", "name": "Sends requests to",
      "direction": "outgoing", "originId": "a-finance", "targetId": "app-api-gateway" },
    { "id": "conn-gateway-idp", "name": "Validates tokens with",
      "direction": "outgoing", "originId": "app-api-gateway", "targetId": "s-idp" },
    { "id": "conn-gateway-runtime", "name": "Routes requests to",
      "direction": "outgoing", "originId": "app-api-gateway", "targetId": "app-agent-runtime" },

    { "id": "conn-orch-workflow", "name": "Delegates tasks to",
      "direction": "outgoing", "originId": "c-agent-orchestrator", "targetId": "c-workflow-engine" },
    { "id": "conn-workflow-governance", "name": "Writes audit records to",
      "direction": "outgoing", "originId": "c-workflow-engine", "targetId": "store-governance" }
  ]
}
```

Every name reads as a sentence across the arrow — "Finance Team · Sends requests to · API Gateway" — and none of them runs past a few words. Anything longer belongs in the connection's `description`.

### What the technologies show

Those IDs came from `GET /catalog/technologies/select`. **Look yours up rather than copying these**. Resolve every ID against the catalog in the environment you're writing to.

Four decisions are visible in the block above:

- **The icon is repeated in `technologyIds`.** Setting `icon` alone does not make that technology part of the object's stack.
- **A technology with no icon can still be a technology.** HTTPS (`20VtuIRnZRytNwM9vvxn`) has no icon asset, so it sits in API Gateway's `technologyIds` while the API Gateway entry carries the logo. Had HTTPS been used as the `icon`, the import would have succeeded and quietly left the object bare.
- **`s-idp` gets nothing, because of `restrictions`.** Okta is restricted to `app, group, store`, and `s-idp` is a `system`. Nothing would have stopped the assignment, but the model would then hold something IcePanel's own picker refuses. Note this varies per entry rather than per category. Check the restriction on the row you actually picked.
- **Neither component is tagged.** Both are Python, which the containing app already says, so tagging them repeats the parent and distinguishes nothing. Components are also the most restricted level in the catalog: Temporal is `app, group`, so it belongs on Agent Runtime rather than on Workflow Engine.

Note the deliberate pairs. `conn-l1-finance-aip` and `conn-finance-gateway` describe the same real interaction, and `conn-l1-aip-idp` and `conn-gateway-idp` because the Level 1 reader wants the business outcome ("Reviews supplier spend in", "Signs in users with") while the Level 2 reader wants the mechanism ("Sends requests to", "Validates tokens with"). One connection cannot serve both audiences.

`conn-workflow-governance` is authored once at component level and drawn twice: on the L3 as `Workflow Engine → Governance Store`, and on the L2 as `Agent Runtime → Governance Store`, since Agent Runtime is what's visible there. Inheritance makes that legal; only draw it that way when the single label reads correctly at both levels.

## The Level 2 diagram spec

Actors above the boundary, containers inside along the request path, external systems below.

```json
{
  "name": "Enterprise Agent Platform - Apps",
  "type": "app-diagram",
  "modelId": "s-aip",
  "index": 1,
  "description": "The applications and data store inside the platform: requests are authenticated at the gateway, executed by the runtime, and audited in the governance store.",
  "objects": [
    { "ref": "s-aip", "shape": "area", "x": 192, "y": 400 },
    { "ref": "a-finance",        "x": 128,  "y": 0 },
    { "ref": "app-api-gateway",  "x": 192,  "y": 400 },
    { "ref": "app-agent-runtime","x": 960,  "y": 400 },
    { "ref": "store-governance", "x": 576,  "y": 1040 },
    { "ref": "s-idp",            "x": 128,  "y": 1360 }
  ],
  "connections": [
    { "ref": "conn-finance-gateway",    "from": "a-finance",       "to": "app-api-gateway" },
    { "ref": "conn-gateway-runtime",    "from": "app-api-gateway", "to": "app-agent-runtime" },
    { "ref": "conn-gateway-idp",        "from": "app-api-gateway", "to": "s-idp" },
    { "ref": "conn-workflow-governance","from": "app-agent-runtime","to": "store-governance" }
  ]
}
```

The boundary carries only `x`/`y`, set to the top-left of the containers it holds. No size is sent — IcePanel grows it around them — so there is nothing to compute and nothing to keep in sync when a box moves. The connections carry only `ref`, `from` and `to`, because IcePanel routes each line and places its label itself.

## Full sequence

```bash
export ICEPANEL_TOKEN='<key-id>:<secret>'

curl -s -H "X-API-Key: $ICEPANEL_TOKEN" https://api.icepanel.io/v1/organizations
curl -s -X POST -H "X-API-Key: $ICEPANEL_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Agent Platform"}' \
  https://api.icepanel.io/v1/organizations/<orgId>/landscapes

# Resolve technology IDs before writing model.json. Ask only for the fields that
# decide the choice: name/description/websiteUrl to identify the row,
# restrictions for where it may go, iconUrl* for whether it can be the icon.
# The rows arrive under `catalogTechnologies`, not `technologies`.
curl -s -H "X-API-Key: $ICEPANEL_TOKEN" -G \
  https://api.icepanel.io/v1/catalog/technologies/select \
  --data-urlencode 'search=postgres' --data-urlencode 'limit=5' \
  --data-urlencode 'fields[]=name' --data-urlencode 'fields[]=description' \
  --data-urlencode 'fields[]=websiteUrl' --data-urlencode 'fields[]=restrictions' \
  --data-urlencode 'fields[]=iconUrlLight' --data-urlencode 'fields[]=iconUrlDark'

python scripts/icepanel.py import  <landscapeId> model.json

# The import created its own domain; the shipped "Default domain" is now an
# empty leftover. This response carries no child list, so pick the leftover out
# by name, or diff against /model/objects for the domainId nothing belongs to.
curl -s -H "X-API-Key: $ICEPANEL_TOKEN" \
  https://api.icepanel.io/v1/landscapes/<landscapeId>/versions/latest/domains
curl -s -X DELETE -H "X-API-Key: $ICEPANEL_TOKEN" \
  https://api.icepanel.io/v1/landscapes/<landscapeId>/versions/latest/domains/<emptyDomainId>

python scripts/icepanel.py idmap   <landscapeId>
python scripts/icepanel.py diagram <landscapeId> l1.json
python scripts/icepanel.py diagram <landscapeId> l2.json
python scripts/icepanel.py diagram <landscapeId> l3.json
python scripts/icepanel.py verify  <landscapeId>
```

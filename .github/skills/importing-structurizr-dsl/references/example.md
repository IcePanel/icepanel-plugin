# A worked import

Structurizr's own Big Bank plc workspace, through to a drawn landscape. Everything below is real parser output, not a sketch.

## The input

`workspace.dsl`, the canonical example, abridged to the parts that decide something:

```
workspace "Big Bank plc" "This is an example workspace to illustrate the key features of Structurizr…" {

    model {
        customer = person "Personal Banking Customer" "A customer of the bank…" "Customer"

        group "Big Bank plc" {
            supportStaff = person "Customer Service Staff" "…" "Bank Staff"
            mainframe = softwaresystem "Mainframe Banking System" "…" "Existing System"
            email     = softwaresystem "E-mail System" "…" "Existing System"

            internetBankingSystem = softwaresystem "Internet Banking System" "…" {
                singlePageApplication = container "Single-Page Application" "…" "JavaScript and Angular" "Web Browser"
                apiApplication = container "API Application" "…" "Java and Spring MVC" {
                    signinController  = component "Sign In Controller" "…" "Spring MVC Rest Controller"
                    securityComponent = component "Security Component" "…" "Spring Bean"
                }
                database = container "Database" "Stores user registration information…" "Oracle Database Schema" "Database"
            }
        }

        customer -> internetBankingSystem "Views account balances, and makes payments using"
        customer -> singlePageApplication "Views account balances, and makes payments using"
        securityComponent -> database "Reads from and writes to" "JDBC"

        deploymentEnvironment "Development" { … }

        deploymentEnvironment "Live" {
            deploymentNode "Big Bank plc" "" "Big Bank plc data center" {
                deploymentNode "bigbank-web***" "" "Ubuntu 16.04 LTS" "" 4 {
                    deploymentNode "Apache Tomcat" "" "Apache Tomcat 8.x" {
                        liveWebApplicationInstance = containerInstance webApplication
                    }
                }
                deploymentNode "bigbank-db01" "" "Ubuntu 16.04 LTS" {
                    primaryDatabaseServer = deploymentNode "Oracle - Primary" "" "Oracle 12c" {
                        containerInstance database
                    }
                }
                deploymentNode "bigbank-db02" "" "Ubuntu 16.04 LTS" "Failover" {
                    secondaryDatabaseServer = deploymentNode "Oracle - Secondary" "" "Oracle 12c" "Failover" {
                        containerInstance database "Failover"
                    }
                }
            }
        }
    }

    views {
        systemlandscape "SystemLandscape" { include *  autoLayout }
        systemcontext internetBankingSystem "SystemContext" { include *  autoLayout }
        container internetBankingSystem "Containers" { include *  autoLayout }
        component apiApplication "Components" { include *  autoLayout }
        dynamic apiApplication "SignIn" "…" { … }
        deployment internetBankingSystem "Live" "LiveDeployment" { include *  autoLayout }

        styles {
            element "Database"    { shape Cylinder }
            element "Web Browser" { shape WebBrowser }
            element "Customer"    { background #08427b }
        }
    }
}
```

## Parse

Two deployment environments, so the parser refuses to guess:

```
$ python scripts/structurizr_dsl.py parse workspace.dsl --out structurizr
error: this workspace has more than one deployment environment (Development, Live); pick one with --environment NAME
```

```
$ python scripts/structurizr_dsl.py parse workspace.dsl --out structurizr --environment Live
wrote structurizr/groups-01.json — 4 objects (nested groups need their own pass; import these first, in order)
wrote structurizr/groups-02.json — 10 objects (nested groups need their own pass; import these first, in order)
wrote structurizr/groups-03.json — 14 objects (nested groups need their own pass; import these first, in order)
wrote structurizr/model.json — 32 objects, 27 connections
wrote structurizr/diagram-01-*.json — context-diagram 'SystemLandscape' (7 objects)
wrote structurizr/diagram-02-*.json — context-diagram 'SystemContext' (4 objects)
wrote structurizr/diagram-03-*.json — app-diagram 'Containers' (9 objects)
wrote structurizr/diagram-04-*.json — component-diagram 'Components' (12 objects)
wrote structurizr/diagram-05-*.json — app-diagram 'LiveDeployment' (17 objects)
wrote structurizr/report.md

report: dropped 1, inferred 2, stores 1, external 1, instances 1, renames 3,
technologies 33, tags 7, descriptions 13, views 2, merged 5
read report.md and confirm it with the user before importing
```

### What the mapping did

- `group "Big Bank plc"` has the workspace's own name, so it became the **domain**, not a group. Its members parent straight to the domain.
- `database` became a **store**, because its `Database` tag is styled `shape Cylinder`.
- Three deployment node trees became **nested groups**, three levels deep, which is why there are three `groups-NN.json` passes.
- `containerInstance` created **nothing**. The containers joined the node groups.
- The `Development` environment was left out entirely.

## The report

```markdown
# Structurizr DSL import — Big Bank plc

32 objects, 27 connections, 5 diagrams.
Deployment environment: **Live**.

Layout is generated — there is no geometry in the DSL to preserve, so placement
comes from the relationship graph. It is a starting point and needs your eye once
it is drawn.

## Inferences

- group **Big Bank plc** has the workspace's own name, so it is read as the
  enterprise boundary and becomes the domain rather than a group
- deployment view `LiveDeployment` drawn as an app diagram on **Internet Banking
  System**, with the deployment nodes as group areas. IcePanel has no deployment
  diagram

## Containers read as data stores — confirm each

- **Database** → store, because tag `Database` is styled `shape Cylinder`

## Systems marked external — confirm each

- No system was marked external — Structurizr has no external flag, and no tag in
  this workspace says a system belongs to somebody else. Name any third parties and
  they can be set before importing

## Deployed more than once

- **Database** is deployed on 2 nodes (Oracle - Primary, Oracle - Secondary) — kept
  as one object in every one of those groups. The diagram draws it inside
  **Oracle - Primary** only, because one box cannot sit in two boundaries — re-run
  with --split-instances to make them separate objects

## Renamed for domain-wide uniqueness

- **Big Bank plc** (group) renamed to **Big Bank plc (Live)**
- **Apache Tomcat** (group) renamed to **Apache Tomcat (bigbank-web***)**
- **Apache Tomcat** (group) renamed to **Apache Tomcat (bigbank-api***)**

## Views

- `dynamic` view `SignIn` skipped. An ordered walkthrough is an IcePanel flow,
  which is out of scope
- deployment view `DevelopmentDeployment` is for environment **Development**, not
  **Live**. Skipped

## Relationships merged on a diagram

- more than one relationship between **Personal Banking Customer** and
  **Internet Banking System** at this level — one line drawn (x6)
- more than one relationship between **Single-Page Application** and
  **API Application** at this level — one line drawn (x4)

## Tags

- tag `Bank Staff` kept, on 2 object(s)
- tag `Customer` kept, on 1 object(s)
- tag `Failover` kept, on 2 object(s)
- tag `Database` dropped — its meaning is already in the object's type, its
  external flag, or its shape
- tag `Existing System` kept, on 3 object(s)
- tag `Web Browser` dropped — …
```

## What to ask

Three questions, all answerable in a sentence:

> Nothing came through as an external system. Structurizr has no external flag, and `Existing System` only means the bank already runs it, which it does. Are any of the mainframe, e-mail system or ATM actually run by somebody else?

> `Database` is deployed on both an Oracle primary and a secondary. I've made it one store sitting in both node groups, drawn inside the primary. Is that one database with a replica, or two you want modelled separately?

> The `SignIn` dynamic view won't come across. It's an ordered walkthrough, which is an IcePanel flow. The relationships behind it are all in the model. Fine to leave it?

## Fill the gaps

Thirteen objects have no description, and every one of them is a group. Structurizr gives `deploymentNode` no description field:

```markdown
- `customer-s-mobile-device` (**Customer's mobile device**, group) — the DSL gave no description
- `big-bank-plc-bigbank-db01` (**bigbank-db01**, group) — the DSL gave no description
- `primaryDatabaseServer` (**Oracle - Primary**, group) — the DSL gave no description
```

Write both fields, caption in label shape:

```json
{ "id": "primaryDatabaseServer", "name": "Oracle - Primary", "type": "group",
  "parentId": "big-bank-plc-bigbank-db01",
  "caption": "Write and read database server",
  "description": "The primary Oracle instance, and the only one that accepts writes." }
```

Then the technologies. Thirty-three strings, and several are more than one technology:

```markdown
- `webApplication` (**Web Application**) — technology "Java and Spring MVC", not yet looked up
- `conn-singlePageApplication-signinController-…` — technology "JSON/HTTPS", not yet looked up
```

`"Java and Spring MVC"` is two catalog entries; `"JSON/HTTPS"` is a format and a protocol. Look each part up, set `technologyIds`, and set `icon` to the one that should carry the logo:

```json
{ "id": "webApplication", "name": "Web Application", "type": "app",
  "parentId": "internetBankingSystem",
  "icon": { "technologyId": "<Java>" },
  "technologyIds": ["<Java>", "<Spring>"] }
```

## Import and draw

Three group passes, in order, before the model:

```bash
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/groups-01.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/groups-02.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/groups-03.json
python ../creating-c4-diagrams/scripts/icepanel.py import <landscapeId> structurizr/model.json
python ../creating-c4-diagrams/scripts/icepanel.py idmap   <landscapeId>
for d in structurizr/diagram-*.json; do
  python ../creating-c4-diagrams/scripts/icepanel.py diagram <landscapeId> "$d"
done
python ../creating-c4-diagrams/scripts/icepanel.py verify  <landscapeId>
```

## The generated layout

The container diagram, on the 384 x 320 pitch. Customer above the boundary, the containers along the request path inside it, the external systems clear of it below:

```
area internetBankingSystem   0  320
box  customer              192    0
box  mobileApp               0  320
box  webApplication        384  320
box  singlePageApplication 192  640
box  apiApplication        192  960
box  database              192 1280
box  email                   0 1600
box  mainframe             384 1600
```

The deployment diagram ranks by node instead, so each node's area wraps a contiguous row rather than straddling several:

```
area big-bank-plc-2 (data center)   0    0
box  apiApplication                 0    0
box  database                     384    0
box  mainframe                    768    0
box  webApplication              1152    0
area customer-s-computer          576  320
box  singlePageApplication        576  320
area customer-s-mobile-device     576  640
box  mobileApp                    576  640
```

## What to tell the user

> Imported 32 objects and 27 connections into Big Bank plc, with five diagrams: two Level 1 (the landscape and the Internet Banking System context), the container diagram, the API Application components, and the Live deployment drawn as an app diagram with the nodes as group areas.
>
> Nothing is marked external. `Existing System` means the bank already runs it, not that a third party does, so tell me if any of those should be. `Database` is one store, in both the primary and secondary Oracle groups. The `SignIn` dynamic view didn't come across; its relationships are all in the model. The `Development` environment isn't imported.
>
> Layout is generated, because there's no geometry in the DSL, so it's a first pass. Worth your eye: https://app.icepanel.io/landscapes/<landscapeId>

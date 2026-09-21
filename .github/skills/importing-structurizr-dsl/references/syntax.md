# The Structurizr DSL the parser accepts

Structurizr's DSL is a real language, not a flat line grammar. This file says which of it the parser implements, which of it is deliberately refused, and where a workspace will come through incomplete.

Official reference: [docs.structurizr.com/dsl/language](https://docs.structurizr.com/dsl/language).

## Contents

- [Lexical rules](#lexical-rules)
- [Structure](#structure)
- [Elements](#elements)
- [Relationships](#relationships)
- [Archetypes](#archetypes)
- [Views](#views)
- [Styles](#styles)
- [Directives](#directives)
- [What is not implemented](#what-is-not-implemented)



## Lexical rules

All of these are handled, and each one appears in Structurizr's own examples:

- **Keywords are case-insensitive.** The Big Bank plc example writes `softwaresystem` and `systemlandscape` in lower case.
- **Four comment forms**: `/* … */`, `# …`, `// …`, and multi-line block comments.
- **Line continuation** with a trailing `\`.
- **Quotes are optional** when a value contains no whitespace.
- `""` **is a placeholder** for an optional positional argument being skipped.
- `{` **is the last token on its line;** `}` **sits on a line of its own.**
- `"""…"""` **text blocks** are read as one value.
- `${NAME}` **substitution** from `!const`, `!var`, or the environment. A name with no value is left as written and reported.



## Structure

```
workspace [name] [description] {
    model   { … }
    views   { … }
    configuration { … }      # read and skipped
}
```

The workspace name becomes the IcePanel domain. An unnamed workspace needs `--domain`.

Any statement the parser does not know is skipped. When it opens braces, the whole block goes with it and the report says so under **Problems**, because one unknown keyword can cost most of a model.

## Elements

Positional arguments, in order. Getting this table wrong is the classic way to land a technology string in the tags slot.


| Keyword                                                       | Positionals                                    |
| ------------------------------------------------------------- | ---------------------------------------------- |
| `person`                                                      | name, description, tags                        |
| `softwareSystem`                                              | name, description, tags                        |
| `container`                                                   | name, description, technology, tags            |
| `component`                                                   | name, description, technology, tags            |
| `deploymentNode`                                              | name, description, technology, tags, instances |
| `infrastructureNode`                                          | name, description, technology, tags            |
| `containerInstance` / `softwareSystemInstance` / `instanceOf` | identifier, deploymentGroups, tags             |
| `element` (custom)                                            | name, metadata, description, tags              |
| `group`                                                       | name                                           |


Inside an element block these also set fields: `description`, `technology`, `tags`, `tag`, `url`. A bare `group "Name"` with no braces sets the enclosing element's group.

`deploymentEnvironment "Name" { … }` wraps a deployment tree. Nodes nest through `deploymentNode`, and `infrastructureNode` sits inside them.

### Identifiers

`x = softwareSystem "X"` binds an identifier, which is separate from the element's name and is what the rest of the DSL refers to it by. It also becomes the IcePanel import ID, so it is the join key that makes a re-run an update rather than a duplicate; anonymous elements fall back to a slug of their path through the model.

`!identifiers hierarchical` additionally registers the dotted path, so `softwareSystem1.api` and `softwareSystem2.api` both resolve. A **bare** identifier used twice resolves to whichever was declared last, where Structurizr resolves it by scope. In practice they agree, because inner declarations come after outer ones, but they are not the same rule. Per Structurizr's own docs, `!identifiers hierarchical` does not apply to groups.

A duplicate identifier under the default flat scope is reported, and the later declaration wins. **Structurizr does not do this, it refuses to parse**, with an error saying the identifier is already in use. The parser deliberately carries on instead, because killing an entire import over one ambiguous reference is worse than importing everything and flagging it. Both elements still reach IcePanel as separate objects; it is only the reference that is ambiguous, and the report names it.

Hierarchical identifiers are also a warning sign worth reading. They exist because Structurizr scopes *names* per parent (container names within a system, component names within a container) while **IcePanel requires names unique across the whole domain**. So a workspace using them is exactly the workspace most likely to hold two containers both called `API`, which IcePanel rejects. Those get suffixed with the parent that tells them apart, and every rename is in the report.

An identifier bound to an instance resolves to the element being deployed: `webApplicationInstance = containerInstance webapp` makes `elb -> webApplicationInstance` land on `webapp`.

## Relationships

```
a -> b "Description" "Technology" "Tags"
-> b "Description"                       # source is the element in scope
this -> b                                # the same, written out
a -> this                                # `this` works on either side
a --https-> b "Makes API calls using"    # a relationship archetype
rel = a -> b "Uses"                      # identifiers are allowed
a -/-> b                                 # removal, reported but not applied
```

Every relationship is `direction: outgoing`. Structurizr does not support bidirectional arrows, so nothing is ever reversed.

## Archetypes

```
archetypes {
    application = container { tag "Application" }
    datastore   = container { tag "Datastore" }
    microservice = group
    springBootApplication = application {
        technology "Spring Boot"
        tags "Spring Boot"
    }
    https = -> { technology "HTTPS" }
}
```

Element archetypes alias any element keyword, `group` included, and extend each other. Scalars: `description`, `technology` come from the nearest archetype in the chain; tags accumulate along it. Relationship archetypes supply a technology and tags to `--name->`.

## Views

A `deployment` view names its environment either way: `deployment s live` and `deployment s "Live"` both resolve, because `live = deploymentEnvironment "Live"` binds the identifier to the name.

```
systemLandscape [key] [description] { … }
systemContext <softwareSystem> [key] [description] { … }
container <softwareSystem> [key] [description] { … }
component <container> [key] [description] { … }
deployment <*|softwareSystem> <environment> [key] [description] { … }
dynamic <scope> [key] [description] { … }       # consumed, then skipped
filtered / custom / image                        # consumed, then skipped
```

Inside a view: `include`, `exclude`, `title`, `description` are read. `autoLayout`, `animation`, `default` and `properties` are consumed and ignored. `autoLayout` is an instruction to Structurizr's renderer, and there is nothing in it to translate.

`include *` is implemented per view type, matching Structurizr's documented wildcard semantics, and so is naming elements explicitly (`include webapp database`). `exclude` works the same way on named elements. Expressions are not evaluated, see below.

## Styles

```
styles {
    element "Database" { shape Cylinder }
    element "Person"   { shape Person }
    light { … }  dark { … }
    relationship "Async" { style dashed }
}
```

The styles block is **read but never written to IcePanel**, which styles objects by type and tag. It matters for one thing: an element style whose `shape` is `Cylinder`, `Bucket` or `Pipe` marks its tag as a data store. That is the strongest signal turning a `container` into an IcePanel `store`, alongside an archetype named after a store, which is the other one the author states deliberately. See `mapping.md`. Tags styled with nothing but a shape or icon are treated as notation and dropped.

## Directives


| Directive                                                                     | Handling                                                     |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `!identifiers hierarchical                                                    | flat`                                                        |
| `!const`, `!var`, `${NAME}`                                                   | Implemented, with environment fallback                       |
| `!include <file                                                               | directory>`                                                  |
| `!include <url>`                                                              | Fetched                                                      |
| `!impliedRelationships`                                                       | Ignored and reported. IcePanel inherits connections natively |
| `!docs`, `!adrs`, `!decisions`, `!components`                                 | Skipped and reported                                         |
| `!script`, `!plugin`                                                          | **Refused.** Never executed, always reported                 |
| `!element`, `!elements`, `!relationship`, `!relationships`, `!extend`, `!ref` | Skipped and reported                                         |




## What is not implemented

Each of these is reported rather than silently skipped, so the report tells you how complete the model really is.

- `enterprise { ... }`**.** The deprecated enterprise boundary, replaced by `group` in current Structurizr but still common in older workspaces. It is not a statement the parser knows, so **its entire body is skipped**: every person, system, container and component inside it is missing from the model, and every relationship referring to one of them fails. Tell the user it's deprecated syntax and ask them to re-import.
- `!script` **and** `!plugin`**.** These run arbitrary Groovy, Kotlin, Ruby, JavaScript or Java from the workspace. Executing code out of a file someone pasted is not something this skill does, at any convenience.
- `workspace extends <file|url>`**.** The base workspace is not pulled in, so its elements are missing.
- **View expressions**: `element.tag==X`, `element.parent==Y`, `->identifier->`, `relationship.source==`, and the `&&` / `||` combinators. The view falls back to `include `*, which normally draws more than the expression would have, and an unevaluated `exclude` expression puts back whatever it was meant to remove.
- `!element` **/** `!relationship` **back-references**, including lookups by canonical name against a JSON workspace. Any tags, properties or children they add are missing.
- `!elements` **/** `!relationships` **bulk operations.**
- `-/->` **relationship removal.**
- `properties`**,** `perspectives`**,** `healthCheck`**,** `deploymentGroup`**,** `instances` **counts,** `terminology`**,** `theme`**,** `themes`**,** `branding`**,** `animation`**.** No IcePanel equivalent.
- **Custom** `element` **declarations and** `custom` **views.** They sit outside the C4 model by design.


# IcePanel plugin

Claude Code and GitHub Copilot skills for working with IcePanel architecture landscapes.

The repository keeps the canonical Claude skill source under `skills/` and includes
the harness-specific manifests and skill copies required by GitHub Copilot discovery.

## Install

```
/plugin marketplace add IcePanel/icepanel-plugin
/plugin install icepanel@icepanel-plugins
```

To try it from a local clone instead, point the marketplace at the checkout:

```
/plugin marketplace add ./icepanel-plugin
/plugin install icepanel@icepanel-plugins
```

If the install summary says `Run /reload-plugins to activate.`, run that too.

## GitHub Copilot

The repository includes a GitHub Copilot CLI plugin manifest at `plugin.json` and a
marketplace catalog at `.github/plugin/marketplace.json`. The Copilot app and other
project-integrated surfaces discover skills from `.github/skills/`:

```
.github/skills/creating-c4-diagrams/
.github/skills/translating-context-maps/
```

The canonical skill source remains under `skills/` for the Claude plugin and CLI plugin.
The `.github/skills/` copies are required because GitHub Copilot uses that documented
project-skill location.

## Skills

### creating-c4-diagrams

Builds and maintains C4 models in IcePanel through its REST API — model objects (actors, systems, apps, stores, components), connections, catalog technologies and icons, and Level 1/2/3 diagrams with hand-authored layout.

It covers the parts that are easy to get wrong: that the model matters more than the diagrams, that a diagram is a story rather than a dump of every edge, that IcePanel has no auto-layout so placement is the whole job, and the places the published API docs disagree with the API.

Includes a helper script for the mechanical work:

```bash
python scripts/icepanel.py import  <landscapeId> model.json   # upsert objects and connections
python scripts/icepanel.py idmap   <landscapeId>              # map import IDs to IcePanel IDs
python scripts/icepanel.py diagram <landscapeId> l2.json      # create a diagram from a layout spec
python scripts/icepanel.py verify  <landscapeId>              # check every diagram for layout problems
```

### translating-context-maps

Turns an image or sketch of a DDD [context map](https://github.com/ddd-crew/context-mapping) into IcePanel model objects and connections. Bounded contexts become a group with a system inside it, upstream/downstream relationships become connections, and the context map patterns — `OHS`, `PL`, `CF`, `ACL`, `SK`, `C/S`, `Partnership` become tags on those connections.

It stops at the import file and hands off to `creating-c4-diagrams`, which does the importing and diagramming.

## Requirements

- An IcePanel API key, generated in the organization's settings on the API keys page. Format is `<key-id>:<secret>`.

  ```bash
  export ICEPANEL_TOKEN='<key-id>:<secret>'
  ```

- Python 3 and `curl`. The script shells out to `curl` on purpose: Python installs on macOS often lack a configured CA bundle, which fails with `CERTIFICATE_VERIFY_FAILED` against the API.

## Layout

```
.claude-plugin/marketplace.json          the marketplace catalog
.claude-plugin/plugin.json               the plugin manifest
.github/plugin/marketplace.json          the GitHub Copilot marketplace catalog
plugin.json                              the GitHub Copilot CLI plugin manifest
skills/
  creating-c4-diagrams/
    SKILL.md
    references/api.md                    endpoints, schemas, enums, doc corrections
    references/layout.md                 grid, boundaries, line routing, spec format
    references/example.md                a worked three-level build
    scripts/icepanel.py
  translating-context-maps/
    SKILL.md
    references/notation.md               the ddd-crew symbol set, and how sketches mislead
    references/example.md                a worked translation, map to import file
.github/skills/                            GitHub Copilot app/project skills
```

## License

Licensed under the [MIT License](./LICENSE).

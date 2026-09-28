#!/usr/bin/env python3
"""Translate a Structurizr DSL workspace into an IcePanel import file and diagram specs.

Usage:
    structurizr_dsl.py parse <input...> [--out DIR] [--namespace NS]
                             [--domain NAME] [--environment NAME] [--split-instances]

Inputs may be a .dsl file, a directory of .dsl files, an https:// URL, or '-' to
read a pasted workspace from stdin. `!include` is resolved when the input gives a
directory to resolve against, and reported when it cannot be.

Writes into DIR (default 'structurizr/'):
    model.json          the import file for `icepanel.py import`
    groups-NN.json      one pass per nesting level, when groups nest
    diagram-NN-*.json   one layout spec per view, for `icepanel.py diagram`
    report.md           every inference made, for the confirmation step

The script does no HTTP except to fetch an https:// input, never executes
`!script` or `!plugin`, and never invents prose. Technology strings are listed
unresolved for a catalog lookup.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict

# ----------------------------------------------------------------- vocabulary

# Structurizr keyword -> IcePanel model object type. `container` is deliberately
# absent: it is an app or a store, decided from the styles block (see store_tags()).
ELEMENT_TYPES = {
    "person": "actor",
    "softwaresystem": "system",
    "container": None,
    "component": "component",
    "deploymentnode": "group",
    "infrastructurenode": "app",
    "element": None,
}

# Positional argument names per keyword. Getting this table wrong is the classic
# way to land a technology string in the tags slot.
ARITY = {
    "person": ["name", "description", "tags"],
    "softwaresystem": ["name", "description", "tags"],
    "container": ["name", "description", "technology", "tags"],
    "component": ["name", "description", "technology", "tags"],
    "deploymentnode": ["name", "description", "technology", "tags", "instances"],
    "infrastructurenode": ["name", "description", "technology", "tags"],
    "element": ["name", "metadata", "description", "tags"],
    "containerinstance": ["ref", "deploymentGroups", "tags"],
    "softwaresysteminstance": ["ref", "deploymentGroups", "tags"],
    "instanceof": ["ref", "deploymentGroups", "tags"],
}

INSTANCE_KEYWORDS = {"containerinstance", "softwaresysteminstance", "instanceof"}

# Every view keyword, and whether it becomes an IcePanel diagram.
VIEW_KEYWORDS = {"systemlandscape", "systemcontext", "container", "component",
                 "dynamic", "deployment", "filtered", "custom", "image"}
DRAWN_VIEWS = {"systemlandscape", "systemcontext", "container", "component", "deployment"}

# Shapes that mean "this container is a data store". The styles block is the
# author's own declaration of what they consider one, which beats guessing names.
STORE_SHAPES = {"cylinder", "bucket", "pipe"}

# An archetype named after a data store is the author saying so outright, which is
# worth more than any guess at a name. camelCase and snake_case are split first, so
# `dataStore`, `message_queue` and `blobStore` all match.
STORE_ARCHETYPE = re.compile(
    r"\b(database|datastore|store|storage|db|cache|queue|topic|broker|bucket|"
    r"blob|schema|table|index|log|stream)\b", re.I)


def words(name):
    """Split an identifier into space-separated words: dataStore -> data Store."""
    return re.sub(r"[_\-]+", " ", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name or ""))

# Tags Structurizr adds itself. They describe the type, which IcePanel already has.
AUTO_TAGS = {"element", "person", "software system", "container", "component",
             "deployment node", "infrastructure node", "relationship",
             "container instance", "software system instance", "group", "boundary"}

# A tag whose element style sets only these is a notation hint, not a category.
NOTATION_ONLY = {"shape", "icon"}

# Tags that mean "someone else owns this". `Existing System` and `Legacy` are
# deliberately absent: they mean brownfield, and a team's own old system is
# still its own. They stay as ordinary tags instead.
EXTERNAL_HINTS = re.compile(r"\b(external|third[- ]party|3rd party|saas|vendor)\b", re.I)

# Layout grid from creating-c4-diagrams/references/layout.md.
PITCH_X, PITCH_Y = 384, 320
BOX_W = 256
SHAPES_IN_ROW = 4

TAG_COLORS = ["blue", "green", "yellow", "orange", "purple", "pink",
              "dark-blue", "beaver", "red", "grey"]


class DslError(Exception):
    pass


def slug(text, fallback="x"):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or fallback


def norm(text):
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


# --------------------------------------------------------------------- lexing

def _http_slashes(text, i):
    """True when // at i is the separator in http:// or https://, not a comment."""
    head = text[max(0, i - 6):i].lower()
    if head.endswith("https:"):
        return True
    if head.endswith("http:"):
        start = i - 5
        return start <= 0 or not text[start - 1].isalnum()
    return False


def strip_comments(text):
    """Drop /* */, #, and // comments, leaving quoted strings and \"\"\" blocks alone."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith('"""', i):
            j = text.find('"""', i + 3)
            j = n if j == -1 else j + 3
            out.append(text[i:j])
            i = j
        elif text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(text[i:j])
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif text.startswith("//", i) and not _http_slashes(text, i):
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif text[i] == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def join_continuations(text):
    return re.sub(r"\\[ \t]*\n[ \t]*", " ", text)


TOKEN = re.compile(r'"""(.*?)"""|"((?:[^"\\]|\\.)*)"|(\S+)', re.S)


def split_tokens(line):
    """Split a statement into tokens, honouring quotes. A trailing { is its own token."""
    toks = []
    for m in TOKEN.finditer(line):
        if m.group(1) is not None:
            toks.append(re.sub(r"\s+", " ", m.group(1)).strip())
        elif m.group(2) is not None:
            toks.append(m.group(2).replace('\\"', '"'))
        else:
            raw = m.group(3)
            # `container "X"{` is legal enough in the wild to be worth handling.
            while raw.endswith("{") and len(raw) > 1:
                toks.append(raw[:-1])
                raw = "{"
            toks.append(raw)
    return toks


def substitute(text, consts, report):
    """Expand ${NAME} from !const/!var, falling back to the environment."""
    def repl(m):
        name = m.group(1)
        if name in consts:
            return consts[name]
        if name in os.environ:
            return os.environ[name]
        report.tally("dropped", f"`${{{name}}}` has no constant, variable or "
                                f"environment value — left as written")
        return m.group(0)
    return re.sub(r"\$\{([a-zA-Z0-9_.-]+)\}", repl, text)


# ------------------------------------------------------------------ the model

class Elem:
    """One Structurizr element, before it is mapped onto an IcePanel type."""

    def __init__(self, keyword, identifier=None):
        self.keyword = keyword          # person, softwaresystem, container, ...
        self.archetype = None           # the archetype it was declared with, if any
        self.identifier = identifier    # the DSL identifier, when one was given
        self.name = None
        self.description = None
        self.technology = None
        self.tags = []
        self.url = None
        self.parent = None              # enclosing Elem (system, container, node)
        self.children = []
        self.groups = []                # enclosing group Elems, outermost first
        self.chains = []                # one group chain per node it is deployed on
        self.type = None                # IcePanel type, decided in build()
        self.external = False
        self.eid = None                 # import id
        self.final_name = None
        self.env = None                 # deployment environment, for nodes
        self.deploy_system = None       # for an infrastructureNode: its owning system

    def __repr__(self):
        return f"<{self.keyword} {self.name!r}>"


class Rel:
    def __init__(self, source, target, description, technology, tags, identifier=None):
        self.source = source
        self.target = target
        self.description = description
        self.technology = technology
        self.tags = tags or []
        self.identifier = identifier
        self.eid = None


class View:
    def __init__(self, kind, scope, key, description):
        self.kind = kind
        self.scope = scope              # identifier token, '*' or None
        self.key = key
        self.description = description
        self.title = None
        self.environment = None         # deployment views only
        self.includes = []
        self.excludes = []


class Workspace:
    def __init__(self):
        self.name = None
        self.description = None
        self.elements = []
        self.rels = []
        self.views = []
        self.styles = {}                # tag -> {property: value}
        self.by_identifier = {}
        self.hierarchical = False
        self.archetypes = {}            # name -> (base keyword, defaults dict)
        self.environments = []
        self.env_aliases = {}           # identifier -> environment name


class Report:
    def __init__(self):
        self.sections = defaultdict(list)
        self.tallies = defaultdict(int)

    def add(self, section, line):
        if line not in self.sections[section]:
            self.sections[section].append(line)

    def tally(self, section, line):
        self.tallies[(section, line)] += 1

    def finalise(self):
        for (section, line), n in sorted(self.tallies.items()):
            self.sections[section].append(line + (f" (x{n})" if n > 1 else ""))
        self.tallies.clear()


# --------------------------------------------------------------------- parsing

REL_OP = re.compile(r"^(?:--(\w+))?->$")
REMOVE_OP = re.compile(r"^(?:--(\w+))?-/->$")


class Parser:
    """A line-oriented recursive parser. Structurizr puts { last and } alone."""

    def __init__(self, report, source):
        self.ws = Workspace()
        self.report = report
        self.source = source
        self.consts = {}
        self.instances = []             # (identifier, node Elem, environment)

    # -- helpers ----------------------------------------------------------

    def register(self, identifier, elem, scope_path):
        if not identifier:
            return
        elem.identifier = identifier
        keys = [identifier]
        if self.ws.hierarchical and scope_path:
            keys.append(".".join(scope_path + [identifier]))
        for k in keys:
            if k in self.ws.by_identifier and self.ws.by_identifier[k] is not elem:
                if not self.ws.hierarchical:
                    self.report.add("problems",
                                    f"identifier `{k}` is declared twice — the second "
                                    f"declaration wins, which may not be what you want")
            self.ws.by_identifier[k] = elem

    def archetype(self, keyword):
        """Resolve an archetype name down to a base keyword plus its defaults."""
        seen, defaults, tags = set(), {}, []
        while keyword in self.ws.archetypes and keyword not in seen:
            seen.add(keyword)
            base, d = self.ws.archetypes[keyword]
            for k, v in d.items():
                if k == "tags":
                    tags += [t for t in v if t not in tags]
                elif k not in defaults:     # the nearest archetype wins
                    defaults[k] = v
            keyword = base
        if tags:
            defaults["tags"] = tags
        return keyword, defaults

    # -- the loop ---------------------------------------------------------

    def parse(self, text):
        text = join_continuations(strip_comments(text))
        lines = text.split("\n")
        self.lines = lines
        self.i = 0
        # A leading !const/!var has to be read before substitution.
        self.prescan(lines)
        self.block(context={"kind": "root"})
        return self.ws

    def prescan(self, lines):
        for raw in lines:
            toks = split_tokens(raw.strip())
            if len(toks) >= 3 and toks[0].lower() in ("!const", "!var"):
                self.consts[toks[1]] = toks[2]

    def block(self, context):
        """Consume lines until the matching } (or EOF at the root)."""
        while self.i < len(self.lines):
            raw = self.lines[self.i].strip()
            self.i += 1
            if not raw:
                continue
            raw = substitute(raw, self.consts, self.report)
            toks = split_tokens(raw)
            if not toks:
                continue
            if toks[0] == "}":
                return
            opens = toks[-1] == "{"
            if opens:
                toks = toks[:-1]
            if not toks:
                continue
            self.statement(toks, opens, context)

    def skip_block(self, opens):
        if not opens:
            return
        depth = 1
        while self.i < len(self.lines) and depth:
            toks = split_tokens(self.lines[self.i].strip())
            self.i += 1
            if not toks:
                continue
            if toks[-1] == "{":
                depth += 1
            if toks[0] == "}":
                depth -= 1

    # -- statements -------------------------------------------------------

    def statement(self, toks, opens, ctx):
        kw = toks[0].lower()

        # `x = ...` — an identifier binding.
        identifier = None
        if len(toks) >= 2 and toks[1] == "=":
            identifier = toks[0]
            toks = toks[2:]
            if not toks:
                return
            kw = toks[0].lower()

        if kw.startswith("!"):
            return self.directive(kw, toks, opens, ctx)

        if ctx["kind"] == "view":
            return self.view_body(kw, toks, opens, ctx)

        if ctx["kind"] == "archetypes":
            return self.archetype_statement(kw, toks, opens, identifier)

        # A relationship anywhere: `a -> b`, `-> b`, `a --https-> b`.
        if any(REL_OP.match(t) or REMOVE_OP.match(t) for t in toks):
            return self.relationship(toks, opens, ctx, identifier)

        kind = ctx["kind"]
        if kind == "root" and kw == "workspace":
            # `extends` is a keyword here, not the workspace name.
            if len(toks) > 1 and toks[1].lower() == "extends":
                target = toks[2] if len(toks) > 2 else ""
                self.report.add("problems",
                                f"`workspace extends{(' ' + target) if target else ''}` "
                                f"— the base workspace is not pulled in, so its "
                                f"elements are missing")
            else:
                self.ws.name = toks[1] if len(toks) > 1 else None
                self.ws.description = toks[2] if len(toks) > 2 else None
            return self.block({"kind": "workspace"})
        if kind == "workspace":
            if kw == "model":
                return self.block({"kind": "model", "groups": [], "scope": []})
            if kw == "views":
                return self.block({"kind": "views"})
            if kw == "configuration":
                return self.skip_block(opens)
            if kw in ("name", "description", "properties"):
                return self.skip_block(opens)
            return self.skip_block(opens)

        if kind in ("model", "element", "group", "deployment", "node"):
            return self.model_statement(kw, toks, opens, ctx, identifier)
        if kind == "views":
            return self.views_statement(kw, toks, opens, ctx)
        if kind == "styles":
            return self.styles_statement(kw, toks, opens, ctx)
        return self.skip_block(opens)

    def directive(self, kw, toks, opens, ctx):
        if kw in ("!script", "!plugin"):
            self.report.add("refused", f"`{kw}` runs arbitrary code and was not "
                                       f"executed — anything it would have added is missing")
            return self.skip_block(opens)
        if kw == "!identifiers":
            self.ws.hierarchical = len(toks) > 1 and toks[1].lower() == "hierarchical"
            return
        if kw in ("!const", "!var"):
            if len(toks) >= 3:
                self.consts[toks[1]] = toks[2]
            return
        if kw == "!include":
            self.report.add("problems", f"`!include {toks[1] if len(toks) > 1 else ''}` "
                                        f"was not resolved — the model is incomplete")
            return
        if kw == "!impliedrelationships":
            self.report.add("inferred", "`!impliedRelationships` ignored — IcePanel "
                                        "inherits connections up the hierarchy natively, "
                                        "so implied relationships are never created")
            return
        if kw in ("!docs", "!adrs", "!decisions", "!components"):
            self.report.tally("dropped", f"`{kw}` — IcePanel has nowhere to put it")
            return self.skip_block(opens)
        if kw in ("!element", "!elements", "!relationship", "!relationships", "!extend", "!ref"):
            self.report.add("problems", f"`{kw}` is not supported — any tags, properties "
                                        f"or children it adds are missing")
            return self.skip_block(opens)
        return self.skip_block(opens)

    # -- model ------------------------------------------------------------

    def model_statement(self, kw, toks, opens, ctx, identifier):
        parent = ctx.get("elem")
        groups = list(ctx.get("groups", []))
        scope = list(ctx.get("scope", []))

        if kw == "archetypes":
            return self.block({"kind": "archetypes"})

        base, defaults = self.archetype(kw)

        if base == "group":
            name = toks[1] if len(toks) > 1 else "Group"
            # `group "X"` with no brace inside an element sets that element's group.
            if not opens and parent is not None:
                parent.groups = groups + [self.make_group(name, groups, ctx)]
                return
            g = self.make_group(name, groups, ctx)
            return self.block({**ctx, "kind": "group", "groups": groups + [g],
                               "elem": parent, "scope": scope})

        if base == "deploymentenvironment":
            name = toks[1] if len(toks) > 1 else "Deployment"
            if name not in self.ws.environments:
                self.ws.environments.append(name)
            if identifier:
                self.ws.env_aliases[identifier] = name
            return self.block({"kind": "deployment", "groups": [], "scope": [],
                               "env": name, "elem": None})

        if base == "deploymentgroup":
            self.report.tally("dropped", "`deploymentGroup` — it only scopes relationship "
                                         "replication, which this import does not do")
            return

        if kw == "healthcheck":
            return self.skip_block(opens)

        if base in INSTANCE_KEYWORDS:
            return self.instance(toks, opens, ctx, identifier)

        # Element properties inside an element block.
        if parent is not None and kw in ("description", "technology", "tags", "tag", "url"):
            value = " ".join(toks[1:]) if kw in ("tags", "tag") else (toks[1] if len(toks) > 1 else "")
            if kw == "description":
                parent.description = toks[1] if len(toks) > 1 else None
            elif kw == "technology":
                parent.technology = toks[1] if len(toks) > 1 else None
            elif kw in ("tags", "tag"):
                for t in toks[1:]:
                    parent.tags += [x.strip() for x in t.split(",") if x.strip()]
            elif kw == "url":
                parent.url = toks[1] if len(toks) > 1 else None
            return
        if parent is not None and kw in ("properties", "perspectives"):
            self.report.tally("dropped", f"`{kw}` on model elements — IcePanel has no "
                                         f"matching field")
            return self.skip_block(opens)

        if base not in ELEMENT_TYPES:
            if opens:
                # A skipped block takes its whole body with it, which is data loss,
                # not a footnote. `enterprise { ... }` is the common one.
                self.report.add("problems", f"`{toks[0]}` is not a statement the parser knows, "
                                            f"and everything inside its braces was skipped. "
                                            f"Whatever it declared is missing from the model, "
                                            f"and relationships referring to it will fail below")
            else:
                self.report.tally("dropped", f"unrecognised statement `{toks[0]}`")
            return self.skip_block(opens)

        elem = self.make_element(base, defaults, toks, identifier, parent, groups, ctx)
        if base != kw:
            elem.archetype = toks[0]    # the author's own name for this kind of thing
        if opens:
            child_scope = scope + [identifier] if identifier else scope
            self.block({"kind": "node" if base == "deploymentnode" else "element",
                        "elem": elem, "groups": list(elem.groups), "scope": child_scope,
                        "env": ctx.get("env")})

    def make_group(self, name, groups, ctx):
        g = Elem("group")
        g.name = name
        g.groups = list(groups)
        g.parent = groups[-1] if groups else None
        g.env = ctx.get("env")
        if g.parent:
            g.parent.children.append(g)
        self.ws.elements.append(g)
        return g

    def make_element(self, base, defaults, toks, identifier, parent, groups, ctx):
        elem = Elem(base, identifier)
        names = ARITY.get(base, ["name"])
        for i, field in enumerate(names):
            if i + 1 >= len(toks):
                break
            value = toks[i + 1]
            if value == "":
                continue
            if field == "tags":
                elem.tags += [t.strip() for t in value.split(",") if t.strip()]
            elif field in ("name", "description", "technology"):
                setattr(elem, field, value)
        for field, value in defaults.items():
            if field == "tags":
                elem.tags += [t for t in value if t not in elem.tags]
            elif not getattr(elem, field, None):
                setattr(elem, field, value)
        elem.parent = parent
        elem.groups = list(groups)
        elem.env = ctx.get("env")
        if parent is not None:
            parent.children.append(elem)
        self.ws.elements.append(elem)
        self.register(identifier, elem, ctx.get("scope", []))
        return elem

    def instance(self, toks, opens, ctx, identifier=None):
        """`containerInstance x` deploys an existing element onto the enclosing node.

        An instance is not a new object. When it is given an identifier, that
        identifier resolves to the element being deployed, so a relationship
        authored against the instance lands on the real container.
        """
        ref = toks[1] if len(toks) > 1 else None
        node = ctx.get("elem")
        if ref and node is not None:
            self.instances.append((ref, node, ctx.get("env")))
        target = self.ws.by_identifier.get(ref) if ref else None
        if identifier and target is not None:
            self.ws.by_identifier[identifier] = target
        elif identifier:
            self.report.add("problems", f"`{identifier}` is an instance of `{ref}`, which is "
                                        f"not declared — relationships to it are skipped")
        if opens:
            self.skip_block(True)

    def endpoint(self, token, ctx):
        """Resolve an arrow's end: a bare identifier, or the element in scope."""
        if token not in (None, "this"):
            return token
        elem = ctx.get("elem")
        if elem is None:
            return None
        return elem.identifier or elem      # an anonymous element in scope

    def relationship(self, toks, opens, ctx, identifier):
        idx = next(i for i, t in enumerate(toks) if REL_OP.match(t) or REMOVE_OP.match(t))
        op = toks[idx]
        if REMOVE_OP.match(op):
            self.report.tally("dropped", "`-/>` relationship removal is not supported")
            return self.skip_block(opens)

        source = self.endpoint(toks[idx - 1] if idx > 0 else None, ctx)
        target = self.endpoint(toks[idx + 1] if idx + 1 < len(toks) else None, ctx)
        rest = toks[idx + 2:]
        description = rest[0] if len(rest) > 0 and rest[0] else None
        technology = rest[1] if len(rest) > 1 and rest[1] else None
        tags = []
        if len(rest) > 2 and rest[2]:
            tags = [t.strip() for t in rest[2].split(",") if t.strip()]

        m = REL_OP.match(op)
        if m and m.group(1):
            base, defaults = self.archetype(m.group(1).lower())
            technology = technology or defaults.get("technology")
            tags += [t for t in defaults.get("tags", []) if t not in tags]

        rel = Rel(source, target, description, technology, tags, identifier)
        self.ws.rels.append(rel)
        if opens:
            self.skip_block(True)

    # -- archetypes -------------------------------------------------------

    def archetype_statement(self, kw, toks, opens, identifier):
        if not identifier:
            return self.skip_block(opens)
        base = toks[0]
        m = REL_OP.match(base)
        if m:
            base = (m.group(1) or "->").lower()
        else:
            base = base.lower()
        defaults = {}
        if opens:
            depth = 1
            while self.i < len(self.lines) and depth:
                line = self.lines[self.i].strip()
                self.i += 1
                t = split_tokens(line)
                if not t:
                    continue
                if t[-1] == "{":
                    depth += 1
                    continue
                if t[0] == "}":
                    depth -= 1
                    continue
                k = t[0].lower()
                if k in ("technology", "description") and len(t) > 1:
                    defaults[k] = t[1]
                elif k in ("tag", "tags"):
                    vals = []
                    for tok in t[1:]:
                        vals += [x.strip() for x in tok.split(",") if x.strip()]
                    defaults.setdefault("tags", []).extend(vals)
        self.ws.archetypes[identifier.lower()] = (base, defaults)

    # -- views ------------------------------------------------------------

    def views_statement(self, kw, toks, opens, ctx):
        if kw == "styles":
            return self.block({"kind": "styles"})
        if kw in ("theme", "themes", "terminology", "branding", "properties"):
            self.report.tally("dropped", f"`{kw}` — IcePanel styles objects by type and tag")
            return self.skip_block(opens)
        if kw not in VIEW_KEYWORDS:
            return self.skip_block(opens)

        args = toks[1:]
        scope = key = description = environment = None
        if kw == "systemlandscape":
            key = args[0] if len(args) > 0 else None
            description = args[1] if len(args) > 1 else None
        elif kw in ("systemcontext", "container", "component", "dynamic"):
            scope = args[0] if len(args) > 0 else None
            key = args[1] if len(args) > 1 else None
            description = args[2] if len(args) > 2 else None
        elif kw == "deployment":
            scope = args[0] if len(args) > 0 else None
            environment = args[1] if len(args) > 1 else None
            key = args[2] if len(args) > 2 else None
            description = args[3] if len(args) > 3 else None
        elif kw == "image":
            scope = args[0] if len(args) > 0 else None
            key = args[1] if len(args) > 1 else None
        else:                                   # filtered, custom
            key = args[0] if len(args) > 0 else None

        view = View(kw, scope, key, description)
        view.environment = environment
        self.ws.views.append(view)
        if opens:
            self.block({"kind": "view", "view": view})

    def view_body(self, kw, toks, opens, ctx):
        """Inside a view: what it shows. A dynamic view's body is relationships,
        and dynamic views are skipped, so those lines are simply consumed."""
        view = ctx["view"]
        if any(REL_OP.match(t) for t in toks):
            return self.skip_block(opens)
        if kw == "include":
            view.includes += toks[1:]
        elif kw == "exclude":
            view.excludes += toks[1:]
        elif kw == "title":
            view.title = toks[1] if len(toks) > 1 else view.title
        elif kw == "description":
            view.description = toks[1] if len(toks) > 1 else view.description
        else:
            self.skip_block(opens)

    # -- styles -----------------------------------------------------------

    def styles_statement(self, kw, toks, opens, ctx):
        if kw in ("light", "dark"):
            return self.block({"kind": "styles"})
        if kw not in ("element", "relationship"):
            return self.skip_block(opens)
        tag = toks[1] if len(toks) > 1 else None
        props = {}
        if opens:
            depth = 1
            while self.i < len(self.lines) and depth:
                line = self.lines[self.i].strip()
                self.i += 1
                t = split_tokens(line)
                if not t:
                    continue
                if t[-1] == "{":
                    depth += 1
                    continue
                if t[0] == "}":
                    depth -= 1
                    continue
                props[t[0].lower()] = t[1] if len(t) > 1 else ""
        if kw == "element" and tag:
            merged = self.ws.styles.setdefault(tag, {})
            merged.update(props)


# ------------------------------------------------------------------- loading

def load_inputs(paths, report):
    """Return (text, base directory or None). Several inputs are concatenated."""
    chunks, base = [], None
    for path in paths:
        if path == "-":
            chunks.append(sys.stdin.read())
        elif path.startswith("http://") or path.startswith("https://"):
            with urllib.request.urlopen(path, timeout=30) as r:
                chunks.append(r.read().decode("utf-8"))
        elif os.path.isdir(path):
            base = base or path
            found = sorted(f for f in os.listdir(path) if f.endswith(".dsl"))
            if not found:
                raise DslError(f"no .dsl files in {path}")
            for f in found:
                with open(os.path.join(path, f)) as fh:
                    chunks.append(fh.read())
        else:
            base = base or os.path.dirname(os.path.abspath(path))
            with open(path) as fh:
                chunks.append(fh.read())
    return "\n".join(chunks), base


# A trailing #, //, or /* comment is valid and must not block inlining.
# // inside http:// or https:// stays part of the path.
INCLUDE = re.compile(
    r"^[ \t]*!include[ \t]+"
    r"(\"(?:[^\"\\]|\\.)*\"|[^\s#]+)"
    r"[ \t]*(?:#.*|//.*|/\*.*)?$",
    re.M | re.I,
)


def _include_target(raw):
    """Path from an !include line, quotes and a glued comment removed."""
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    i = 0
    while i < len(raw):
        if raw.startswith("/*", i):
            return raw[:i].strip('"')
        # :// is a URL scheme, not a comment. Any other // ends the path.
        if raw.startswith("//", i) and (i == 0 or raw[i - 1] != ":"):
            return raw[:i].strip('"')
        i += 1
    return raw.strip('"')


def resolve_includes(text, base, report, depth=0):
    """Inline !include targets that can be reached from the input's directory."""
    if depth > 8:
        report.add("problems", "!include nesting is deeper than 8 levels — stopped")
        return text

    def repl(m):
        target = _include_target(m.group(1))
        if target.startswith("http://") or target.startswith("https://"):
            try:
                with urllib.request.urlopen(target, timeout=30) as r:
                    return resolve_includes(r.read().decode("utf-8"), base, report, depth + 1)
            except Exception as e:
                report.add("problems", f"`!include {target}` could not be fetched ({e})")
                return ""
        if not base:
            return m.group(0)               # left for the parser to report
        full = os.path.join(base, target)
        if os.path.isdir(full):
            parts = []
            for f in sorted(os.listdir(full)):
                if f.endswith(".dsl"):
                    with open(os.path.join(full, f)) as fh:
                        parts.append(resolve_includes(fh.read(), os.path.dirname(
                            os.path.join(full, f)), report, depth + 1))
            return "\n".join(parts)
        if os.path.isfile(full):
            with open(full) as fh:
                return resolve_includes(fh.read(), os.path.dirname(full), report, depth + 1)
        report.add("problems", f"`!include {target}` not found relative to {base}")
        return ""
    return INCLUDE.sub(repl, text)


# ------------------------------------------------------------- building model

def store_tags(ws):
    """Normalized tag -> shape, for tags the styles block marks as a data store.

    Keys are folded with norm() because an element's tag and the styles key
    often differ in case or internal whitespace. The shape is kept here so the
    report does not look the element's original tag up in ws.styles.
    """
    found = {}
    for tag, props in ws.styles.items():
        shape = props.get("shape")
        if norm(shape) in STORE_SHAPES:
            found.setdefault(norm(tag), shape)
    return found


def notation_tags(ws):
    """Tags whose style says nothing but which glyph to draw."""
    return {norm(tag) for tag, props in ws.styles.items()
            if props and set(props) <= NOTATION_ONLY}


def resolve(ws, token):
    if isinstance(token, Elem):
        return token
    if token is None:
        return None
    return ws.by_identifier.get(token)


def canonical(elem):
    parts, cur = [], elem
    while cur is not None:
        parts.append(cur.name or "anon")
        cur = cur.parent
    return "/".join(reversed(parts))


def assign_ids(ws, report):
    used = {}
    for e in ws.elements:
        base = e.identifier or slug(canonical(e))
        base = re.sub(r"[^A-Za-z0-9_.-]", "-", base)
        if base in used and used[base] is not e:
            n = 2
            while f"{base}-{n}" in used:
                n += 1
            base = f"{base}-{n}"
        used[base] = e
        e.eid = base


def classify(ws, report):
    """Decide each element's IcePanel type, and which containers are stores."""
    stores = store_tags(ws)
    for e in ws.elements:
        if e.keyword == "group":
            e.type = "group"
        elif e.keyword == "deploymentnode":
            e.type = "group"
        elif e.keyword == "infrastructurenode":
            e.type = "app"
        elif e.keyword == "element":
            e.type = None
            report.add("dropped", f"custom element **{e.name}** sits outside the C4 model "
                                  f"and has no IcePanel type")
        elif e.keyword == "container":
            hit = next((t for t in e.tags if norm(t) in stores), None)
            if hit:
                e.type = "store"
                report.add("stores", f"**{e.name}** → store, because tag `{hit}` is styled "
                                     f"`shape {stores[norm(hit)]}`")
            elif e.archetype and STORE_ARCHETYPE.search(words(e.archetype)):
                e.type = "store"
                report.add("stores", f"**{e.name}** → store, because it is declared with the "
                                     f"`{e.archetype}` archetype")
            elif re.search(r"\b(database|db|store|cache|queue|topic|bucket|schema|"
                           r"blob|s3|redis|kafka)\b", f"{e.name} {e.technology or ''}", re.I):
                e.type = "store"
                report.add("stores", f"**{e.name}** → store, from its name or technology "
                                     f"(\"{e.technology or e.name}\") — no styled shape to go on")
            else:
                e.type = "app"
        else:
            e.type = ELEMENT_TYPES.get(e.keyword)

    for e in ws.elements:
        if e.type not in ("system", "actor"):
            continue
        hit = next((t for t in e.tags if EXTERNAL_HINTS.search(t)), None)
        if not hit:
            continue
        e.external = True
        report.add("external", f"**{e.name}** marked external, from tag `{hit}`")

    if not any(e.external for e in ws.elements):
        report.add("external", "No system was marked external — Structurizr has no external "
                               "flag, and no tag in this workspace says a system belongs to "
                               "somebody else. Name any third parties and they can be set "
                               "before importing")


def enterprise_group(ws, report):
    """A model-level group named after the workspace is the enterprise boundary."""
    if not ws.name:
        return None
    for e in ws.elements:
        if e.keyword == "group" and not e.parent and norm(e.name) == norm(ws.name):
            report.add("inferred", f"group **{e.name}** has the workspace's own name, so it "
                                   f"is read as the enterprise boundary and becomes the "
                                   f"domain rather than a group")
            return e
    return None


def apply_instances(ws, pending, environment, split, report):
    """Join deployed elements to their node groups, or split them when asked."""
    by_target = defaultdict(list)
    for ref, node, env in pending:
        if environment and env != environment:
            continue
        target = resolve(ws, ref)
        if target is None:
            report.add("problems", f"`{ref}` is deployed onto **{node.name}** but no such "
                                   f"element is declared")
            continue
        by_target[target].append(node)

    extra = []
    for target, nodes in by_target.items():
        chain = []
        for n in nodes:
            chain += [g for g in group_chain(n) if g not in chain]
        target.chains = [group_chain(n) for n in nodes]
        if len(nodes) == 1 or not split:
            target.groups = [g for g in (target.groups + chain)]
            if len(nodes) > 1:
                report.add("instances",
                           f"**{target.name}** is deployed on {len(nodes)} nodes "
                           f"({', '.join(n.name for n in nodes)}) — kept as one object in "
                           f"every one of those groups. The diagram draws it inside "
                           f"**{nodes[0].name}** only, because one box cannot sit in two "
                           f"boundaries — re-run with --split-instances to make them "
                           f"separate objects")
            continue
        # Splitting: the first instance keeps the original object and its connections.
        # Copies keep the same model-level groups; only the node chain differs.
        stem, first = target.name, nodes[0]
        existing = list(target.groups)
        target.groups = existing + group_chain(first)
        target.name = f"{stem} ({first.name})"
        for n in nodes[1:]:
            copy = Elem(target.keyword, None)
            copy.name = f"{stem} ({n.name})"
            copy.description = target.description
            copy.technology = target.technology
            copy.tags = list(target.tags)
            copy.type = target.type
            copy.parent = target.parent
            copy.groups = existing + group_chain(n)
            extra.append(copy)
            report.add("instances", f"**{copy.name}** split out from **{stem}** — it carries "
                                    f"no connections of its own")
        report.add("instances", f"**{target.name}** keeps every connection authored against "
                                f"**{stem}**")
    ws.elements += extra


def place_infrastructure(ws, pending, environment, report):
    """An infrastructureNode is an app, and an app has to live in a system.

    Structurizr puts nothing above it but deployment nodes, so the system is
    inferred: the one whose containers are deployed in this environment, and
    where several are, the one with the most of them — the same rule a
    landscape-wide deployment view uses to pick its subject. The node chain it
    sits in becomes its groupIds, exactly like a deployed container's.
    """
    infra = [e for e in ws.elements
             if e.keyword == "infrastructurenode"
             and (not environment or e.env == environment)]
    if not infra:
        return

    counts = defaultdict(int)
    for ref, node, env in pending:
        if environment and env != environment:
            continue
        target = resolve(ws, ref)
        while target is not None and target.type != "system":
            target = target.parent
        if target is not None:
            counts[target] += 1
    system = max(counts, key=counts.get) if counts else None

    for e in infra:
        e.groups = group_chain(e.parent)
        e.deploy_system = system
        if system is None:
            report.add("problems", f"**{e.name}** is an infrastructureNode, which is an app, "
                                   f"but nothing is deployed in this environment to say which "
                                   f"system it belongs to — skipped")
        else:
            report.add("inferred", f"**{e.name}** is an infrastructureNode — it becomes an app "
                                   f"in **{system.name}**, the system deployed in this "
                                   f"environment")


def build_hierarchy(ws, domain_eid, enterprise, report):
    """parentId for every object, and groupIds alongside it."""
    objects = []
    for e in ws.elements:
        if e.type is None or e is enterprise:
            continue
        o = {"id": e.eid, "name": e.final_name, "type": e.type}

        if e.type in ("actor", "system"):
            o["parentId"] = domain_eid
        elif e.type == "group":
            parent = e.parent
            while parent is not None and parent.type != "group":
                parent = parent.parent
            if parent is enterprise:
                parent = None
            o["parentId"] = parent.eid if parent is not None else domain_eid
        elif e.type in ("app", "store"):
            system = e.parent
            while system is not None and system.type != "system":
                system = system.parent
            if system is None and e.keyword == "infrastructurenode":
                system = e.deploy_system
            if system is None:
                report.add("problems", f"**{e.name}** is a container with no software "
                                       f"system around it — skipped")
                continue
            o["parentId"] = system.eid
        elif e.type == "component":
            host = e.parent
            while host is not None and host.type not in ("app", "store"):
                host = host.parent
            if host is None:
                report.add("problems", f"**{e.name}** is a component with no container "
                                       f"around it — skipped")
                continue
            o["parentId"] = host.eid

        groups = [g for g in e.groups if g is not enterprise and g.type == "group"]
        # An object must name every enclosing group, inner and outer both, or the
        # outer boundary comes out empty on any diagram that draws it.
        if groups and e.type != "group":
            o["groupIds"] = []
            for g in groups:
                for anc in [x for x in g.groups if x is not enterprise] + [g]:
                    if anc.eid not in o["groupIds"]:
                        o["groupIds"].append(anc.eid)
        if e.external:
            o["external"] = True
        if e.description:
            o["description"] = e.description
            o["caption"] = caption_from(e.description)
        else:
            report.add("descriptions", f"`{e.eid}` (**{e.final_name}**, {e.type}) — "
                                       f"the DSL gave no description")
        if e.technology:
            report.add("technologies", f"`{e.eid}` (**{e.final_name}**) — technology "
                                       f"\"{e.technology}\", not yet looked up")
        if e.url:
            o["links"] = {"structurizr": {"name": "Link", "url": e.url}}
        objects.append(o)
    return objects


def caption_from(descr):
    """A description trimmed to caption shape: first clause, no trailing stop."""
    text = re.split(r"(?<=[a-z0-9])[.;:]|\s+[-—]\s+|,\s+(?:and|with|which|that)\b",
                    descr.strip(), maxsplit=1)[0]
    words = text.split()[:8]
    return " ".join(words).rstrip(" .,;:")


def dedupe_names(ws, enterprise, domain_name, report):
    """IcePanel names are unique across the whole domain; Structurizr's are not."""
    for e in ws.elements:
        e.final_name = e.name
    seen = defaultdict(list)
    for e in ws.elements:
        if e.type is None or e is enterprise:
            continue
        seen[norm(e.name)].append(e)
    for key, group in seen.items():
        clash_with_domain = key == norm(domain_name)
        if len(group) == 1 and not clash_with_domain:
            continue
        for e in group:
            qualifier = None
            for cand in reversed(e.groups):
                if cand is not enterprise and cand.name:
                    qualifier = cand.name
                    break
            if qualifier is None and e.parent is not None:
                qualifier = e.parent.name
            if qualifier is None:
                qualifier = e.env or e.type
            e.final_name = f"{e.name} ({qualifier})"
            report.add("renames", f"**{e.name}** ({e.type}) renamed to "
                                  f"**{e.final_name}** — names must be unique "
                                  f"across the domain")


def build_connections(ws, report):
    conns, used = [], set()
    for r in ws.rels:
        src = resolve(ws, r.source)
        dst = resolve(ws, r.target)
        if src is None or dst is None:
            report.add("problems", f"relationship `{r.source} -> {r.target}` refers to "
                                   f"something that is not declared — skipped")
            continue
        if src.type is None or dst.type is None:
            report.add("dropped", f"relationship **{r.description or 'unnamed'}** touches a "
                                  f"custom element and has no IcePanel equivalent")
            continue
        name = r.description or "Uses"
        base = r.identifier or f"conn-{src.eid}-{dst.eid}-{slug(name)[:24]}"
        eid = base
        n = 2
        while eid in used:
            eid = f"{base}-{n}"
            n += 1
        used.add(eid)
        r.eid = eid
        conn = {"id": eid, "name": name, "direction": "outgoing",
                "originId": src.eid, "targetId": dst.eid}
        if r.technology:
            report.add("technologies", f"`{eid}` — technology \"{r.technology}\", "
                                       f"not yet looked up")
        conns.append((conn, src, dst))
    return conns


def build_tags(ws, report):
    """Semantic tags only: the ones absorbed into type or external are gone, and so
    are the ones whose style says nothing but which glyph to draw."""
    stores = store_tags(ws)
    notation = notation_tags(ws)
    keep, dropped = {}, set()
    for e in ws.elements:
        if e.type is None:
            continue
        for t in e.tags:
            n = norm(t)
            if n in AUTO_TAGS or n in stores or n in notation or EXTERNAL_HINTS.search(t):
                dropped.add(t)
                continue
            keep.setdefault(t, []).append(e)
    for t in sorted(dropped):
        report.tally("tags", f"tag `{t}` dropped — its meaning is already in the object's "
                             f"type, its external flag, or its shape")
    if not keep:
        return [], [], {}
    group = {"id": "tg-structurizr", "name": "Structurizr", "icon": "star"}
    tags, by_name = [], {}
    for i, name in enumerate(sorted(keep)):
        tid = f"tag-{slug(name)}"
        tags.append({"id": tid, "name": name, "color": TAG_COLORS[i % len(TAG_COLORS)],
                     "groupId": group["id"]})
        by_name[name] = tid
        report.add("tags", f"tag `{name}` kept, on {len(keep[name])} object(s)")
    return tags, [group], by_name


# -------------------------------------------------------------------- layout

def group_chain(node):
    """Every group enclosing a node, outermost first, including the node itself."""
    chain, cur = [], node
    while cur is not None and cur.type == "group":
        chain.append(cur)
        cur = cur.parent
    return list(reversed(chain))


def descendants(elem):
    out, stack = [], list(elem.children)
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack += cur.children
    return out


def resolve_environment(ws, ref):
    """A deployment view names its environment by name or by identifier.

    `deployment s live` and `deployment s "Live"` are the same view; Structurizr
    accepts both, and `live = deploymentEnvironment "Live"` binds the one to the
    other. Matching on the name alone silently drops every view written the
    first way.
    """
    if ref is None:
        return None
    if ref in ws.environments:
        return ref
    if ref in ws.env_aliases:
        return ws.env_aliases[ref]
    return next((n for n in ws.environments if norm(n) == norm(ref)), ref)


def is_deployment_group(g):
    return g.keyword == "deploymentnode" or g.env is not None


def enclosing(elem, enterprise, view_kind=None):
    """The groups that should box this element in on a diagram.

    Deployment nodes only box things in on a deployment view; a container view
    has no business drawing the servers its containers run on. And an element
    deployed onto several nodes is drawn inside the first of them, because one
    box cannot sit inside two boundaries.
    """
    groups = [g for g in elem.groups if g is not enterprise and g.type == "group"]
    if view_kind is None:
        return groups
    if view_kind != "deployment":
        return [g for g in groups if not is_deployment_group(g)]
    if len(elem.chains) > 1:
        chain = [g for g in elem.chains[0] if g is not enterprise]
        return [g for g in groups if g in chain or not is_deployment_group(g)]
    return groups


def layout(visible, areas, edges, inside, report, title, bands=None):
    """Place objects on the 384x320 grid, initiators at the top.

    Ported from the Mermaid importer: rank by the request path through the
    subject, then two barycentre passes to reduce crossings. Outsiders are pushed
    clear of the subject because an area is auto-sized around its children.
    """
    boxes = [e for e in visible if e not in areas]
    if not boxes:
        return [], []

    if bands is not None:
        # A deployment diagram reads by node, not by request path: everything on
        # one node shares a row, so its area wraps a contiguous span instead of
        # straddling rows that other nodes' areas also cross.
        rank = {e: bands.get(e, 0) for e in boxes}
        return place(boxes, areas, rank, {e: float(i) for i, e in enumerate(boxes)},
                     report, title)

    rank = {e: (0 if e.type == "actor" else 1) for e in boxes}
    for _ in range(len(boxes) + 1):
        changed = False
        for src, dst in edges:
            if dst not in inside or dst.type == "actor" or src not in rank or dst not in rank:
                continue
            if src in inside or src.type == "actor":
                if rank[dst] <= rank[src]:
                    rank[dst] = rank[src] + 1
                    changed = True
        if not changed:
            break

    floor = max([rank[e] for e in inside if e in rank], default=0)
    for e in boxes:
        if e in inside or e.type == "actor":
            continue
        calls_in = any(o is e and d in inside for o, d in edges)
        called_by = any(d is e and o in inside for o, d in edges)
        rank[e] = 0 if (calls_in and not called_by) else floor + 1

    order = {e: float(i) for i, e in enumerate(boxes)}
    for _ in range(2):
        for e in boxes:
            nbrs = [o for o, d in edges if d is e] + [d for o, d in edges if o is e]
            nbrs = [n for n in nbrs if n in rank and rank[n] != rank[e]]
            if nbrs:
                order[e] = sum(order[n] for n in nbrs if n in order) / len(nbrs)

    return place(boxes, areas, rank, order, report, title)


def place(boxes, areas, rank, order, report, title):
    def group_key(e):
        return "/".join(g.eid for g in e.groups if g in areas)

    counts = defaultdict(int)
    for e in boxes:
        counts[rank[e]] += 1
    per_row = min(max(counts.values(), default=1), SHAPES_IN_ROW)
    canvas = per_row * PITCH_X - (PITCH_X - BOX_W)

    placed, pos, y = [], {}, 0
    for r in sorted({rank[e] for e in boxes}):
        row = sorted([e for e in boxes if rank[e] == r], key=lambda e: (group_key(e), order[e]))
        for i in range(0, len(row), SHAPES_IN_ROW):
            chunk = row[i:i + SHAPES_IN_ROW]
            span = len(chunk) * PITCH_X - (PITCH_X - BOX_W)
            x0 = max(0, (canvas - span) // 2)
            x0 -= x0 % 8
            for j, e in enumerate(chunk):
                spec = {"ref": e.eid, "x": x0 + j * PITCH_X, "y": y}
                placed.append(spec)
                pos[e] = spec
            y += PITCH_Y

    area_specs = []
    for a in sorted(areas, key=lambda a: -len(descendants(a))):
        kids = [pos[k] for k in pos if a in enclosures(k)]
        if not kids:
            report.add("problems", f"boundary **{a.name}** has nothing inside it on "
                                   f"\"{title}\" — dropped from the diagram")
            continue
        area_specs.append({"ref": a.eid, "shape": "area",
                           "x": min(k["x"] for k in kids), "y": min(k["y"] for k in kids)})
    return placed, area_specs


def enclosures(elem):
    """Every area that could enclose `elem`: its groups and its ancestors."""
    out, cur = list(elem.groups), elem.parent
    while cur is not None:
        out.append(cur)
        cur = cur.parent
    return out


# ------------------------------------------------------------------ diagrams

def lift(elem, visible):
    """Map an endpoint up to the nearest ancestor drawn on this diagram."""
    cur = elem
    while cur is not None:
        if cur in visible:
            return cur
        cur = cur.parent
    return None


def view_contents(ws, view, enterprise, report):
    """The elements a view shows. `include *` is the idiom; expressions are not
    evaluated, and fall back to the wildcard with a note."""
    people = [e for e in ws.elements if e.type == "actor"]
    systems = [e for e in ws.elements if e.type == "system"]
    scope = resolve(ws, view.scope) if view.scope and view.scope != "*" else None

    def named(tokens):
        """Split include/exclude tokens into resolved elements and expressions."""
        elems, exprs = [], []
        for token in tokens:
            if token == "*" or token == "*?":
                continue
            if any(op in token for op in ("==", "!=", "->")):
                exprs.append(token)
                continue
            hit = resolve(ws, token)
            if hit is not None:
                elems.append(hit)
            else:
                exprs.append(token)
        return elems, exprs

    included, include_exprs = named(view.includes)
    excluded, exclude_exprs = named(view.excludes)
    for token in include_exprs:
        report.add("views", f"view `{view.key or view.kind}` selects what it shows with "
                            f"`{token}`, which is not evaluated — the view falls back to "
                            f"`include *`, so the diagram probably draws more than it should")
    for token in exclude_exprs:
        report.add("views", f"view `{view.key or view.kind}` removes things with "
                            f"`{token}`, which is not evaluated — whatever it was meant to "
                            f"take off the diagram is still on it")

    def trim(members):
        """Honour an explicit include list, then drop anything explicitly excluded."""
        wildcard = any(t in ("*", "*?") for t in view.includes) or not view.includes
        if included and not wildcard:
            members = [e for e in members if e in included] + \
                      [e for e in included if e not in members]
        elif included:
            members = members + [e for e in included if e not in members]
        if excluded:
            members = [e for e in members if e not in excluded]
        return members

    if view.kind == "systemlandscape":
        return trim(people + systems), None
    if view.kind == "systemcontext":
        if scope is None:
            return trim(people + systems), None
        near = {scope}
        for r in ws.rels:
            a, b = resolve(ws, r.source), resolve(ws, r.target)
            for x, y in ((a, b), (b, a)):
                if x is None or y is None:
                    continue
                top = x
                while top is not None and top.type not in ("system", "actor"):
                    top = top.parent
                other = y
                while other is not None and other.type not in ("system", "actor"):
                    other = other.parent
                if top is scope and other is not None:
                    near.add(other)
        return trim([e for e in people + systems if e in near]), scope
    if view.kind == "container":
        if scope is None:
            return [], None
        inside = [e for e in ws.elements if e.type in ("app", "store") and e.parent is scope]
        outside = set()
        for r in ws.rels:
            a, b = resolve(ws, r.source), resolve(ws, r.target)
            for x, y in ((a, b), (b, a)):
                if x is None or y is None:
                    continue
                if lift(x, set(inside)) is not None:
                    top = y
                    while top is not None and top.type not in ("system", "actor"):
                        top = top.parent
                    if top is not None and top is not scope:
                        outside.add(top)
        return trim(inside + sorted(outside, key=lambda e: e.name or "")), scope
    if view.kind == "component":
        if scope is None:
            return [], None
        inside = [e for e in ws.elements if e.type == "component" and e.parent is scope]
        outside = set()
        for r in ws.rels:
            a, b = resolve(ws, r.source), resolve(ws, r.target)
            for x, y in ((a, b), (b, a)):
                if x is None or y is None:
                    continue
                if lift(x, set(inside)) is not None:
                    top = y
                    while top is not None and top.type not in (
                            "system", "actor", "app", "store"):
                        top = top.parent
                    if top is not None and top is not scope and top not in inside:
                        outside.add(top)
        return trim(inside + sorted(outside, key=lambda e: e.name or "")), scope
    if view.kind == "deployment":
        members = [e for e in ws.elements if e.type in ("app", "store", "system")
                   and any(is_deployment_group(g) for g in enclosing(e, enterprise))]
        if scope is not None and scope.type == "system":
            kept = [e for e in members
                    if e.type == "system" or owning_system(e) is scope]
            for e in members:
                if e not in kept:
                    report.add("views", f"**{e.name}** is deployed in this environment but "
                                        f"belongs to another system, so it is left off "
                                        f"`{view.key or view.kind}`, which is scoped to "
                                        f"**{scope.name}**")
            members = kept
        return trim(members), scope
    return [], None


def diagram_spec(ws, view, conns, enterprise, domain_eid, counters, report):
    members, scope = view_contents(ws, view, enterprise, report)
    members = [e for e in members if e.type is not None]
    if not members:
        report.add("views", f"view `{view.key or view.kind}` has nothing to draw — skipped")
        return None

    visible = list(dict.fromkeys(members))
    vset = set(visible)

    # Boundaries on this diagram: the subject, plus every group enclosing a member.
    areas = []
    if view.kind in ("container", "component") and scope is not None:
        areas.append(scope)
        visible.append(scope)
        vset.add(scope)
    for e in members:
        for g in enclosing(e, enterprise, view.kind):
            if g not in areas:
                areas.append(g)
                visible.append(g)
                vset.add(g)

    boxes = [e for e in visible if e not in areas]
    bset = set(boxes)
    edges, drawn, seen_pairs = [], [], set()
    for conn, src, dst in conns:
        a, b = lift(src, bset), lift(dst, bset)
        if a is None or b is None or a is b:
            continue
        if (a.eid, b.eid) in seen_pairs:
            report.tally("merged", f"more than one relationship between **{a.final_name}** "
                                   f"and **{b.final_name}** at this level — one line drawn")
            continue
        seen_pairs.add((a.eid, b.eid))
        edges.append((a, b))
        drawn.append({"ref": conn["id"], "from": a.eid, "to": b.eid})

    inside = set()
    if view.kind in ("container", "component") and scope is not None:
        inside = {e for e in boxes if ancestor_of(scope, e)}
    if not inside:
        inside = {e for e in boxes if e.type != "actor" and not e.external}

    title = view.title or view.description or view.key or view.kind
    bands = None
    if view.kind == "deployment":
        roots, bands = [], {}
        for e in boxes:
            chain = e.chains[0] if e.chains else enclosing(e, enterprise, view.kind)
            root = chain[0] if chain else None
            if root not in roots:
                roots.append(root)
            bands[e] = roots.index(root)
    placed, area_specs = layout(boxes, areas, edges, inside, report, title, bands)
    if not placed:
        return None
    placed_ids = {p["ref"] for p in placed} | {a["ref"] for a in area_specs}
    drawn = [c for c in drawn if c["from"] in placed_ids and c["to"] in placed_ids]

    dtype, model_ref = diagram_target(ws, view, scope, boxes, domain_eid, report)
    if dtype is None:
        return None
    counters[dtype] = counters.get(dtype, 0) + 1
    return {
        "name": title,
        "type": dtype,
        "modelId": model_ref,
        "index": counters[dtype],
        "description": view.description or
                       f"Imported from the Structurizr {view.kind} view.",
        "objects": area_specs + placed,
        "connections": drawn,
    }


def ancestor_of(ancestor, elem):
    cur = elem
    while cur is not None:
        if cur is ancestor:
            return True
        cur = cur.parent
    return False


def diagram_target(ws, view, scope, boxes, domain_eid, report):
    if view.kind in ("systemlandscape", "systemcontext"):
        return "context-diagram", "@root"
    if view.kind == "container" and scope is not None:
        return "app-diagram", scope.eid
    if view.kind == "component" and scope is not None:
        return "component-diagram", scope.eid
    if view.kind == "deployment":
        subject = scope if scope is not None and scope.type == "system" else None
        if subject is None:
            subject = busiest_system(boxes)
            if subject is None:
                report.add("problems", f"deployment view `{view.key or view.environment}` "
                                       f"deploys nothing that belongs to a software system, "
                                       f"so there is no app diagram to draw — skipped")
                return None, None
            report.add("inferred", f"deployment view `{view.key or view.environment}` covers "
                                   f"the whole landscape, so it is drawn as an app diagram on "
                                   f"**{subject.final_name}**, the system owning most of what "
                                   f"is on it. Containers of other systems are drawn outside "
                                   f"its boundary")
        else:
            report.add("inferred", f"deployment view `{view.key or view.environment}` drawn "
                                   f"as an app diagram on **{subject.final_name}**, with the "
                                   f"deployment nodes as group areas — IcePanel has no "
                                   f"deployment diagram")
        return "app-diagram", subject.eid
    return "context-diagram", "@root"


def owning_system(elem):
    """The software system an element belongs to, or itself when it is one.

    An infrastructureNode is the exception: its parent chain runs up through
    deployment nodes and never reaches a system, so the system inferred for it in
    place_infrastructure is the answer. Walking the parents instead returns None,
    which reads as "belongs to some other system" and drops it off its own
    deployment diagram.
    """
    if elem.deploy_system is not None:
        return elem.deploy_system
    cur = elem
    while cur is not None:
        if cur.type == "system":
            return cur
        cur = cur.parent
    return None


def busiest_system(boxes):
    """The system owning the most of what is drawn — the subject of the diagram."""
    counts = defaultdict(int)
    for e in boxes:
        owner = owning_system(e)
        if owner is not None:
            counts[owner] += 1
    if not counts:
        return None
    return max(counts, key=lambda sysm: (counts[sysm], sysm.final_name or ""))


# --------------------------------------------------------------------- output

def group_passes(objects, namespace):
    """Nested groups need one import pass per level, ahead of the model.

    A group parented to another group fails with `Parent not found` when both are
    created in one request, and that failure cascades to every object listing the
    nested group in `groupIds`.
    """
    by_id = {o["id"]: o for o in objects}
    depth = {}
    for o in objects:
        if o["type"] != "group":
            continue
        d, cur, seen = 0, o.get("parentId"), set()
        while cur in by_id and by_id[cur]["type"] == "group" and cur not in seen:
            seen.add(cur)
            d += 1
            cur = by_id[cur].get("parentId")
        depth[o["id"]] = d
    if not depth or max(depth.values()) == 0:
        return []
    domain = [o for o in objects if o["type"] == "domain"]
    passes = []
    for level in range(max(depth.values()) + 1):
        objs = domain + [o for o in objects
                         if o["type"] == "group" and depth[o["id"]] <= level]
        passes.append({"namespace": namespace, "modelObjects": objs, "modelConnections": []})
    return passes


SECTION_TITLES = [
    ("problems", "Problems — read these first"),
    ("refused", "Refused for safety"),
    ("stores", "Containers read as data stores — confirm each"),
    ("external", "Systems marked external — confirm each"),
    ("instances", "Deployed more than once"),
    ("renames", "Renamed for domain-wide uniqueness"),
    ("inferred", "Inferences"),
    ("views", "Views"),
    ("merged", "Relationships merged on a diagram"),
    ("tags", "Tags"),
    ("descriptions", "Missing descriptions — generate these"),
    ("technologies", "Technology strings to look up"),
    ("dropped", "Dropped input"),
]


def write_report(path, report, model, specs, domain_name, environment):
    lines = [f"# Structurizr DSL import — {domain_name}", "",
             f"{len(model['modelObjects'])} objects, "
             f"{len(model['modelConnections'])} connections, {len(specs)} diagrams."]
    if environment:
        lines.append(f"Deployment environment: **{environment}**.")
    lines += ["", "Layout is generated — there is no geometry in the DSL to preserve, so "
                  "placement comes from the relationship graph. It is a starting point and "
                  "needs your eye once it is drawn.", ""]
    for key, title in SECTION_TITLES:
        items = report.sections.get(key)
        if not items:
            continue
        lines += [f"## {title}", ""] + [f"- {i}" for i in items] + [""]
    lines += ["## Diagrams", ""]
    for s in specs:
        lines.append(f"- **{s['name']}** — {s['type']} on `{s['modelId']}`, "
                     f"{len(s['objects'])} objects, {len(s['connections'])} connections")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))


def cmd_parse(args):
    report = Report()
    text, base = load_inputs(args.inputs, report)
    text = resolve_includes(text, base, report)

    parser = Parser(report, args.inputs[0])
    ws = parser.parse(text)
    if not ws.elements:
        raise DslError("no model elements found — is this a Structurizr DSL workspace?")

    domain_name = args.domain or ws.name
    if not domain_name:
        extends = next((line for line in report.sections.get("problems", [])
                        if line.startswith("`workspace extends")), None)
        if extends:
            raise DslError(f"{extends}. The workspace has no name to take the "
                           f"domain from; pass --domain")
        raise DslError("the workspace has no name to take the domain from; pass --domain")

    environments = ws.environments
    if len(environments) > 1 and not args.environment:
        raise DslError("this workspace has more than one deployment environment "
                       f"({', '.join(environments)}); pick one with --environment NAME")
    environment = args.environment or (environments[0] if environments else None)
    if environment and environment not in environments:
        raise DslError(f"no deployment environment named '{environment}'; "
                       f"found {', '.join(environments) or 'none'}")
    for other in environments:
        if other != environment:
            report.add("dropped", f"deployment environment **{other}** not imported — one "
                                  f"environment per import")

    # Everything outside the chosen environment leaves the model entirely.
    if environment:
        ws.elements = [e for e in ws.elements if e.env in (None, environment)]

    enterprise = enterprise_group(ws, report)
    classify(ws, report)
    if enterprise is not None:
        enterprise.type = None
        for e in ws.elements:
            e.groups = [g for g in e.groups if g is not enterprise]
            if e.parent is enterprise:
                e.parent = None

    assign_ids(ws, report)
    apply_instances(ws, parser.instances, environment, args.split_instances, report)
    place_infrastructure(ws, parser.instances, environment, report)
    assign_ids(ws, report)
    dedupe_names(ws, enterprise, domain_name, report)

    domain_eid = f"domain-{slug(domain_name)}"
    conns = build_connections(ws, report)
    tags, tag_groups, tag_ids = build_tags(ws, report)

    objects = [{"id": domain_eid, "name": domain_name, "type": "domain"}]
    if ws.description:
        objects[0]["description"] = ws.description
        objects[0]["caption"] = caption_from(ws.description)
    objects += build_hierarchy(ws, domain_eid, enterprise, report)

    if tag_ids:
        by_eid = {e.eid: e for e in ws.elements}
        for o in objects:
            e = by_eid.get(o["id"])
            if e is None:
                continue
            ids = [tag_ids[t] for t in e.tags if t in tag_ids]
            if ids:
                o["tagIds"] = ids

    order = {"domain": 0, "group": 1, "actor": 2, "system": 3,
             "app": 4, "store": 5, "component": 6}
    objects.sort(key=lambda o: (order.get(o["type"], 9), o["name"]))

    counters, specs = {}, []
    for view in ws.views:
        if view.kind not in DRAWN_VIEWS:
            report.add("views", f"`{view.kind}` view `{view.key or ''}` skipped — "
                                f"{skip_reason(view.kind)}")
            continue
        if view.kind == "deployment":
            view.environment = resolve_environment(ws, view.environment)
            if environment and view.environment not in (None, environment):
                report.add("views", f"deployment view `{view.key or view.environment}` is for "
                                    f"environment **{view.environment}**, not **{environment}** "
                                    f"— skipped")
                continue
        spec = diagram_spec(ws, view, conns, enterprise, domain_eid, counters, report)
        if spec:
            specs.append(spec)

    model = {"namespace": args.namespace,
             "modelObjects": objects,
             "modelConnections": [c for c, _, _ in conns]}
    if tags:
        model["tags"] = tags
        model["tagGroups"] = tag_groups
    report.finalise()

    os.makedirs(args.out, exist_ok=True)
    for stale in sorted(os.listdir(args.out)):
        if re.match(r"^(diagram-\d+-.*|groups-\d+)\.json$", stale):
            os.remove(os.path.join(args.out, stale))
    passes = group_passes(objects, args.namespace)
    for i, p in enumerate(passes, 1):
        with open(os.path.join(args.out, f"groups-{i:02d}.json"), "w") as f:
            json.dump(p, f, indent=2)
    with open(os.path.join(args.out, "model.json"), "w") as f:
        json.dump(model, f, indent=2)
    for i, spec in enumerate(specs, 1):
        fname = f"diagram-{i:02d}-{slug(spec['name'])[:40]}.json"
        with open(os.path.join(args.out, fname), "w") as f:
            json.dump(spec, f, indent=2)
    write_report(os.path.join(args.out, "report.md"), report, model, specs,
                 domain_name, environment)

    for i, p in enumerate(passes, 1):
        print(f"wrote {args.out}/groups-{i:02d}.json — {len(p['modelObjects'])} objects "
              f"(nested groups need their own pass; import these first, in order)")
    print(f"wrote {args.out}/model.json — {len(objects)} objects, "
          f"{len(model['modelConnections'])} connections")
    for i, spec in enumerate(specs, 1):
        print(f"wrote {args.out}/diagram-{i:02d}-*.json — {spec['type']} "
              f"'{spec['name']}' ({len(spec['objects'])} objects)")
    print(f"wrote {args.out}/report.md")
    counts = {k: len(v) for k, v in report.sections.items() if v}
    if counts:
        print("\nreport: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
        print("read report.md and confirm it with the user before importing")


def skip_reason(kind):
    return {
        "dynamic": "an ordered walkthrough is an IcePanel flow, which is out of scope",
        "filtered": "it is a tag filter over another view, which IcePanel has no equivalent for",
        "custom": "custom elements sit outside the C4 model",
        "image": "it is an embedded picture, not a model view",
    }.get(kind, "it has no IcePanel equivalent")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("parse")
    q.add_argument("inputs", nargs="+")
    q.add_argument("--out", default="structurizr")
    q.add_argument("--domain", default=None)
    q.add_argument("--namespace", default="structurizr")
    q.add_argument("--environment", default=None,
                   help="which deployment environment to import; required when the "
                        "workspace defines more than one")
    q.add_argument("--split-instances", action="store_true",
                   help="make a separate object per deployment instance of a container")
    q.set_defaults(func=cmd_parse)
    args = p.parse_args()
    try:
        args.func(args)
    except DslError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Translate Mermaid C4 diagrams into an IcePanel import file and diagram specs.

Usage:
    mermaid_c4.py parse <input...> [--out DIR] [--domain NAME] [--namespace NS]

Inputs may be Markdown files containing ```mermaid fences, standalone .mmd /
.mermaid files, or '-' to read a pasted block from stdin. Several inputs are
merged into one model: an alias declared in more than one block is one object,
which is how the C4 hierarchy is recovered from diagrams that each show a
single level of it.

Writes into DIR (default 'mermaid-c4/'):
    model.json          the import file for `icepanel.py import`
    diagram-NN-*.json   one layout spec per block, for `icepanel.py diagram`
    report.md           every inference made, for the confirmation step

The script does no HTTP and never guesses prose. Objects whose description
Mermaid did not supply are written empty and listed in the report, as are
technology strings awaiting a catalog lookup.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

# ----------------------------------------------------------------- vocabulary

# Mermaid keyword -> IcePanel model object type. The Db/Queue shape variants of
# System and Component have no IcePanel equivalent and flatten onto the base
# type; ContainerDb and ContainerQueue are both stores.
ELEMENTS = {
    "Person": "actor", "Person_Ext": "actor",
    "System": "system", "System_Ext": "system",
    "SystemDb": "system", "SystemDb_Ext": "system",
    "SystemQueue": "system", "SystemQueue_Ext": "system",
    "Container": "app", "Container_Ext": "app",
    "ContainerDb": "store", "ContainerDb_Ext": "store",
    "ContainerQueue": "store", "ContainerQueue_Ext": "store",
    "Component": "component", "Component_Ext": "component",
    "ComponentDb": "component", "ComponentDb_Ext": "component",
    "ComponentQueue": "component", "ComponentQueue_Ext": "component",
}

BOUNDARIES = {"Boundary", "Enterprise_Boundary", "System_Boundary", "Container_Boundary"}
NODES = {"Deployment_Node", "Node", "Node_L", "Node_R"}

RELS = {"Rel", "BiRel", "Rel_Back", "RelIndex",
        "Rel_U", "Rel_Up", "Rel_D", "Rel_Down",
        "Rel_L", "Rel_Left", "Rel_R", "Rel_Right"}

# Parsed and then dropped: IcePanel styles objects by type and tag, so there is
# nothing for a colour or a label offset to land on.
DROPPED = {"UpdateElementStyle", "UpdateRelStyle", "AddElementTag", "AddRelTag",
           "RoundedBoxShape", "EightSidedShape", "DashedLine", "DottedLine", "BoldLine",
           "Lay_U", "Lay_Up", "Lay_D", "Lay_Down", "Lay_L", "Lay_Left", "Lay_R", "Lay_Right"}

# Positional argument names per keyword family.
ARGS_PERSON = ["alias", "label", "descr", "sprite", "tags", "link"]
ARGS_TECHN = ["alias", "label", "techn", "descr", "sprite", "tags", "link"]
ARGS_BOUNDARY = ["alias", "label", "type", "tags", "link"]
ARGS_NAMED_BOUNDARY = ["alias", "label", "tags", "link"]
ARGS_NODE = ["alias", "label", "type", "descr", "sprite", "tags", "link"]
ARGS_REL = ["from", "to", "label", "techn", "descr", "sprite", "tags", "link"]
ARGS_RELINDEX = ["index", "from", "to", "label", "tags", "link"]

KINDS = {"C4Context": "context", "C4Container": "container", "C4Component": "component",
         "C4Dynamic": "dynamic", "C4Deployment": "deployment"}

# Layout grid from creating-c4-diagrams/references/layout.md.
PITCH_X, PITCH_Y = 384, 320
BOX_W = 256

# A relationship label longer than this, or one that looks like code, is a
# description wearing a name's clothes.
MAX_LABEL_WORDS = 5
CODE_HINTS = re.compile(r"[=;*(){}]|\bselect\b|\binsert\b|\bupdate\b|\bwhere\b", re.I)


class MermaidError(Exception):
    pass


def slug(text, fallback="x"):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or fallback


# "Container diagram for Internet Banking System" names a diagram, not a domain.
TITLE_NOISE = re.compile(
    r"^\s*(?:\w[\w\s]*?\s)?diagram\s+for\s+|^\s*(?:system\s+)?context\s+(?:diagram\s+)?(?:for\s+)?",
    re.I)


def title_subject(title):
    """The thing a Mermaid title is about, with the diagram-type wrapper removed."""
    if not title:
        return None
    s = TITLE_NOISE.sub("", title).strip()
    s = re.split(r"\s+[-–—]\s+", s)[0].strip()
    return s or title.strip()


def norm_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# --------------------------------------------------------------------- lexing

def strip_frontmatter(text):
    """Remove a leading YAML config block, which carries only render settings."""
    if not text.lstrip().startswith("---"):
        return text
    lead = text.index("---")
    end = text.find("\n---", lead + 3)
    if end == -1:
        return text
    return text[text.index("\n", end + 1) + 1:] if "\n" in text[end + 1:] else ""


def strip_comments(text):
    """Drop %% comments, but not a %% that appears inside a quoted string."""
    out, i, inq = [], 0, False
    while i < len(text):
        c = text[i]
        if c == '"':
            inq = not inq
            out.append(c)
            i += 1
        elif not inq and text.startswith("%%", i):
            j = text.find("\n", i)
            if j == -1:
                break
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_args(text, start):
    """Read a balanced (...) starting at `start`; returns (inner, index after)."""
    depth, inq, i = 0, False, start
    while i < len(text):
        c = text[i]
        if inq:
            if c == '"':
                inq = False
        elif c == '"':
            inq = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    raise MermaidError("unbalanced parentheses")


def split_args(s):
    parts, cur, inq, depth = [], "", False, 0
    for c in s:
        if inq:
            cur += c
            if c == '"':
                inq = False
        elif c == '"':
            cur += c
            inq = True
        elif c == "(":
            depth += 1
            cur += c
        elif c == ")":
            depth -= 1
            cur += c
        elif c == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


def clean(value):
    """Unquote and flatten a Mermaid argument to plain text."""
    v = value.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
    v = re.sub(r"<br\s*/?>", " ", v, flags=re.I)
    return re.sub(r"\s+", " ", v).strip()


NAMED = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", re.S)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_args(raw, names):
    """Bind arguments to names. Positionals fill in order; $named win their slot."""
    pos, out = [], {}
    for p in raw:
        m = NAMED.match(p)
        if m:
            out[m.group(1)] = clean(m.group(2))
        else:
            pos.append(clean(p))
    for i, name in enumerate(names):
        if i < len(pos) and name not in out:
            out[name] = pos[i]
    return out


def tokenize(text):
    """Yield ('call', name, [args]) | ('open',) | ('close',) | ('bare', name, rest)."""
    toks, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "{":
            toks.append(("open",))
            i += 1
            continue
        if c == "}":
            toks.append(("close",))
            i += 1
            continue
        m = IDENT.match(text, i)
        if not m:
            i += 1
            continue
        name, j = m.group(0), m.end()
        k = j
        while k < n and text[k] in " \t":
            k += 1
        if k < n and text[k] == "(":
            inner, end = read_args(text, k)
            toks.append(("call", name, split_args(inner)))
            i = end
        else:
            eol = text.find("\n", j)
            eol = n if eol == -1 else eol
            toks.append(("bare", name, text[j:eol].strip()))
            i = eol
    return toks


# ------------------------------------------------------------------ extraction

FENCE = re.compile(r"```+\s*(mermaid|mmd)[^\n]*\n(.*?)```+", re.S | re.I)
HEADER = re.compile(r"^\s*(C4Context|C4Container|C4Component|C4Dynamic|C4Deployment)\b", re.M)


def extract_blocks(text, source):
    """Pull C4 blocks out of Markdown fences, or treat the whole text as one."""
    found = [m.group(2) for m in FENCE.finditer(text)]
    if not found:
        found = [text]
    return [(source, b) for b in found if HEADER.search(b)]


# ---------------------------------------------------------------------- model

class Elem:
    """One aliased Mermaid element, merged across every block that declares it."""

    def __init__(self, alias):
        self.alias = alias
        self.label = None
        self.descr = None
        self.techn = None
        self.tags = None
        self.link = None
        self.kinds = []          # every keyword it was declared as, in order
        self.blocks = set()      # indices of the blocks that declare it
        self.children = []       # aliases declared directly inside it
        self.stack = None        # enclosing boundary aliases, outermost first
        self.depth0 = None       # nesting depth at first declaration
        self.type = None
        self.parent = None
        self.groups = []
        self.name = None         # final IcePanel name, after de-duplication

    @property
    def is_boundary(self):
        return any(k in BOUNDARIES or k in NODES for k in self.kinds)

    @property
    def is_node(self):
        return any(k in NODES for k in self.kinds)

    @property
    def external(self):
        return any(k.endswith("_Ext") for k in self.kinds)


class Rel:
    def __init__(self, kind, origin, target, label, techn, descr, block):
        self.kind = kind
        self.origin = origin
        self.target = target
        self.label = label
        self.techn = techn
        self.descr = descr
        self.block = block
        self.ref = None          # import id of the model connection behind it

    @property
    def direction(self):
        return "bidirectional" if self.kind == "BiRel" else "outgoing"

    @property
    def hint(self):
        """Layout suffix, if any: the direction the target sits from the origin."""
        for suffix, d in (("_U", "up"), ("_Up", "up"), ("_D", "down"), ("_Down", "down"),
                          ("_L", "left"), ("_Left", "left"), ("_R", "right"), ("_Right", "right")):
            if self.kind.endswith(suffix):
                return d
        return None


class Block:
    def __init__(self, kind, source, index):
        self.kind = kind
        self.source = source
        self.index = index
        self.title = None
        self.aliases = []        # declaration order, for layout
        self.rels = []
        self.shapes_in_row = 4


class Report:
    def __init__(self):
        self.sections = defaultdict(list)
        self.tallies = defaultdict(int)

    def add(self, section, line):
        self.sections[section].append(line)

    def tally(self, section, line):
        """For repeated identical findings — 12 dropped style calls are one line."""
        self.tallies[(section, line)] += 1

    def finalise(self):
        for (section, line), n in sorted(self.tallies.items()):
            self.sections[section].append(line + (f" (x{n})" if n > 1 else ""))
        self.tallies.clear()

    def __bool__(self):
        return bool(self.sections)


def parse_block(text, source, index, reg, report, alias_map=None):
    """Parse one block, registering its elements into the shared alias registry."""
    amap = alias_map or {}
    toks = tokenize(strip_comments(strip_frontmatter(text)))
    block = None
    stack = []          # open boundary aliases
    pending = None      # a boundary call awaiting its '{'

    for tok in toks:
        if tok[0] == "open":
            if pending:
                stack.append(pending)
                pending = None
            continue
        if tok[0] == "close":
            if stack:
                stack.pop()
            continue
        if tok[0] == "bare":
            name, rest = tok[1], tok[2]
            if name in KINDS:
                block = Block(KINDS[name], source, index)
            elif name == "title" and block:
                block.title = clean(rest)
            elif name == "accTitle" and block and not block.title:
                block.title = clean(rest.lstrip(": "))
            continue

        name, raw = tok[1], tok[2]
        if block is None:
            raise MermaidError("statement before the C4 diagram header")

        if name in DROPPED:
            report.tally("dropped", f"`{name}` in {source} — styling has no IcePanel equivalent")
            continue

        if name in RELS:
            if name == "RelIndex":
                a = parse_args(raw, ARGS_RELINDEX)
                report.tally("dropped", f"`RelIndex` step order in {source} — flows are out "
                                        f"of scope, the connection itself is kept")
            else:
                a = parse_args(raw, ARGS_REL)
            origin, target = a.get("from"), a.get("to")
            if not origin or not target:
                report.add("problems", f"`{name}` with missing ends in {source} block {index}")
                continue
            origin, target = amap.get(origin, origin), amap.get(target, target)
            # Rel_Back renders `from <-- to`, so the relationship runs to -> from.
            # Authors also reach for it purely to move a box, which silently
            # reverses the arrow, so every one of these gets reported.
            if name == "Rel_Back":
                origin, target = target, origin
                report.add("reversed", f"`Rel_Back` in {source} block {index} authored as "
                                       f"`{origin}` -> `{target}` (\"{a.get('label', '')}\") — "
                                       f"check the direction reads correctly")
            block.rels.append(Rel(name, origin, target, a.get("label", ""),
                                  a.get("techn"), a.get("descr"), block))
            continue

        if name == "UpdateLayoutConfig":
            a = parse_args(raw, ["c4ShapeInRow", "c4BoundaryInRow"])
            try:
                block.shapes_in_row = max(1, int(a.get("c4ShapeInRow", 4)))
            except (TypeError, ValueError):
                pass
            continue

        if name in ELEMENTS or name in BOUNDARIES or name in NODES:
            if name in NODES:
                a = parse_args(raw, ARGS_NODE)
            elif name in {"Enterprise_Boundary", "System_Boundary", "Container_Boundary"}:
                a = parse_args(raw, ARGS_NAMED_BOUNDARY)
            elif name == "Boundary":
                a = parse_args(raw, ARGS_BOUNDARY)
            elif ELEMENTS[name] in ("app", "store", "component"):
                a = parse_args(raw, ARGS_TECHN)
            else:
                a = parse_args(raw, ARGS_PERSON)

            alias = a.get("alias")
            if not alias:
                report.add("problems", f"`{name}` with no alias in {source} block {index}")
                continue
            alias = amap.get(alias, alias)

            e = reg.get(alias) or Elem(alias)
            reg[alias] = e
            if name not in e.kinds:
                e.kinds.append(name)
            # First declaration wins on text; later blocks only fill gaps.
            for field in ("label", "descr", "techn", "tags", "link"):
                if a.get(field) and not getattr(e, field):
                    setattr(e, field, a[field])
            if e.stack is None:
                e.stack = list(stack)
                e.depth0 = len(stack)
            elif stack and len(stack) > len(e.stack):
                # A deeper declaration knows more about the hierarchy than a bare one.
                e.stack = list(stack)
            if stack:
                parent = reg[stack[-1]]
                if alias not in parent.children:
                    parent.children.append(alias)
            e.blocks.add(index)
            if alias not in block.aliases:
                block.aliases.append(alias)
            if name in BOUNDARIES or name in NODES:
                pending = alias
            continue

        report.tally("dropped", f"unrecognised statement `{name}` in {source}")

    if block is None:
        raise MermaidError("no C4 diagram header found")
    return block


# ------------------------------------------------------------ type resolution

def classify(reg, blocks, report):
    """Resolve every alias to an IcePanel type.

    Plain elements come from the keyword table. A boundary's type comes from
    what it contains, because the same keyword means different things at
    different levels: Container_Boundary wraps containers in a C4Container
    (so it is a system) and components in a C4Component (so it is an app).
    """
    for e in reg.values():
        if not e.is_boundary:
            kinds = [k for k in e.kinds if k in ELEMENTS]
            e.type = ELEMENTS[kinds[0]] if kinds else "system"
            if len({ELEMENTS[k] for k in kinds}) > 1:
                report.add("conflicts", f"`{e.alias}` declared as {', '.join(e.kinds)} — "
                                        f"taking `{e.type}` from the first")
            elif len({k.endswith('_Ext') for k in kinds}) > 1:
                report.add("conflicts", f"`{e.alias}` declared both internal and external "
                                        f"({', '.join(e.kinds)}) — treating it as "
                                        f"{'external' if e.external else 'internal'}")

    # The outermost Enterprise_Boundary is the domain; anything nested is a group.
    domain_alias = None
    for b in blocks:
        for alias in b.aliases:
            e = reg[alias]
            if "Enterprise_Boundary" in e.kinds and not e.stack:
                domain_alias = domain_alias or alias

    boundaries = [e for e in reg.values() if e.is_boundary]
    for _ in range(len(boundaries) + 1):
        changed = False
        for e in boundaries:
            want = boundary_type(e, reg, domain_alias)
            if want != e.type:
                e.type = want
                changed = True
        if not changed:
            break

    for e in boundaries:
        if not e.children:
            report.add("inferred", f"boundary `{e.alias}` (\"{e.label}\") is empty — "
                                   f"modelled as a group")
    return domain_alias


def boundary_type(e, reg, domain_alias):
    if e.alias == domain_alias:
        return "domain"
    if e.is_node:
        return "group"
    child_types = {reg[c].type for c in e.children if reg[c].type}
    if child_types & {"app", "store"}:
        return "system"
    if "component" in child_types:
        # An alias declared ContainerDb elsewhere is a store holding components.
        return "store" if any(k in ("ContainerDb", "ContainerDb_Ext", "ContainerQueue",
                                    "ContainerQueue_Ext") for k in e.kinds) else "app"
    return "group"


# -------------------------------------------------------------- hierarchy

def nearest(e, reg, types):
    """Innermost enclosing boundary whose resolved type is in `types`."""
    for alias in reversed(e.stack or []):
        if reg[alias].type in types:
            return alias
    return None


def build_hierarchy(reg, domain_alias, domain_name, report):
    """Assign parentId and groupIds, inventing systems where Mermaid names none."""
    if domain_alias:
        domain = reg[domain_alias]
        domain.type = "domain"
        domain.name = domain_name or domain.label
        did = domain.alias
    else:
        domain = Elem(f"d-{slug(domain_name, 'domain')}")
        domain.kinds = ["__domain"]
        domain.type = "domain"
        domain.label = domain_name
        domain.stack = []
        reg[domain.alias] = domain
        did = domain.alias

    placeholders = {}

    for e in list(reg.values()):
        if e.type == "domain":
            e.parent = None
            continue
        if e.type in ("actor", "system"):
            e.parent = did
            e.groups = [a for a in (e.stack or []) if reg[a].type == "group"]
        elif e.type == "group":
            e.parent = nearest(e, reg, {"group"}) or did
        elif e.type in ("app", "store"):
            sys_alias = nearest(e, reg, {"system"})
            if not sys_alias:
                sys_alias = placeholder_system(e, reg, did, placeholders, report)
            e.parent = sys_alias
            e.groups = [a for a in (e.stack or []) if reg[a].type == "group"]
        elif e.type == "component":
            host = nearest(e, reg, {"app", "store"})
            if not host:
                sys_alias = nearest(e, reg, {"system"}) or \
                    placeholder_system(e, reg, did, placeholders, report)
                host = placeholder_app(e, reg, sys_alias, placeholders, report)
            e.parent = host
    return did


def placeholder_system(e, reg, did, placeholders, report):
    """Invent the system a container needs, named from its outermost node."""
    nodes = [a for a in (e.stack or []) if reg[a].type == "group"]
    if nodes:
        base = reg[nodes[0]].label or nodes[0]
        key = f"sys-{slug(base)}"
        label = base if re.search(r"\b(system|platform|service)s?$", base, re.I) \
            else f"{base} System"
    else:
        key = "sys-unassigned"
        label = "Unassigned Containers"
    if key not in placeholders:
        p = Elem(key)
        p.kinds = ["__placeholder"]
        p.type = "system"
        p.label = label
        p.stack = []
        p.parent = did
        reg[key] = p
        placeholders[key] = True
        report.add("placeholders",
                   f"system **{label}** (`{key}`) — invented to parent containers "
                   f"declared outside any system boundary. Rename it, or re-run with "
                   f"the containers inside a boundary, before this reaches the model")
    return key


def placeholder_app(e, reg, sys_alias, placeholders, report):
    key = f"app-{slug(reg[sys_alias].label or 'host')}"
    if key not in placeholders:
        p = Elem(key)
        p.kinds = ["__placeholder"]
        p.type = "app"
        p.label = f"{reg[sys_alias].label} Application"
        p.stack = []
        p.parent = sys_alias
        reg[key] = p
        placeholders[key] = True
        report.add("placeholders",
                   f"app **{p.label}** (`{key}`) — invented to host components "
                   f"declared outside any container boundary")
    return key


def detect_duplicates(reg, report):
    """Flag one object declared under two aliases in different blocks.

    Nothing forces a Mermaid author to reuse an alias between diagrams — the
    reference docs themselves call one app `backend_api` in the container
    diagram and `api` in the component one. Alias merging cannot see through
    that, so identical names are reported as probable duplicates with the
    `--alias` flags that would fix them, rather than silently becoming two
    objects.
    """
    by_name = defaultdict(list)
    for e in reg.values():
        if e.type not in ("domain", "root"):
            by_name[norm_name(e.name or e.label)].append(e)
    flags = []
    for group in by_name.values():
        if len(group) < 2:
            continue
        # A block that names two things identically means two things — replicas
        # on a deployment diagram, say. Only blocks disagreeing about an alias
        # points at one object split in two.
        if any(a.blocks & b.blocks for a in group for b in group if a is not b):
            continue
        # Keep whichever alias carries the most structure; it knows the hierarchy.
        canon = max(group, key=lambda e: (len(e.children), -(e.depth0 or 0)))
        others = [e for e in group if e is not canon]
        flags += [f"--alias {e.alias}={canon.alias}" for e in others]
        report.add("duplicates",
                   f"**{canon.label}** is declared as "
                   + " and ".join(f"`{e.alias}`" for e in group)
                   + f" — probably one object under different aliases. To merge, re-run with "
                   + " ".join(f"`--alias {e.alias}={canon.alias}`" for e in others))
    if flags:
        report.add("duplicates", "Full merge, if every pair above is really one object: "
                                 f"`--alias " + " --alias ".join(f.split(" ", 1)[1] for f in flags) + "`")


def dedupe_names(reg, report):
    """IcePanel names must be unique across the whole domain."""
    for e in reg.values():
        if not e.name:
            e.name = e.label or e.alias
    by_name = defaultdict(list)
    for e in reg.values():
        by_name[e.name].append(e)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for e in group:
            groups = [reg[a] for a in (e.stack or []) if reg[a].type == "group"]
            parent = reg.get(e.parent)
            if groups:
                qualifier = groups[-1].label or groups[-1].alias
            elif parent and parent.type != "domain":
                qualifier = parent.name
            else:
                qualifier = e.alias
            e.name = f"{name} ({qualifier})"
            report.add("renames", f"`{e.alias}` renamed to **{e.name}** — "
                                  f"\"{name}\" is not unique within the domain")
    # A qualifier can itself collide; fall back to the alias.
    seen = {}
    for e in reg.values():
        if e.name in seen:
            e.name = f"{e.name} [{e.alias}]"
            report.add("renames", f"`{e.alias}` further qualified to **{e.name}**")
        seen[e.name] = e


# ------------------------------------------------------------- connections

def depth_of(alias, reg):
    d, seen = 0, set()
    cur = reg.get(alias)
    while cur and cur.parent and cur.parent not in seen:
        seen.add(cur.parent)
        d += 1
        cur = reg.get(cur.parent)
    return d


def is_ancestor(a, b, reg):
    """Is `a` an ancestor of `b` (or the same object)?"""
    cur, seen = reg.get(b), set()
    while cur:
        if cur.alias == a:
            return True
        if cur.alias in seen:
            return False
        seen.add(cur.alias)
        cur = reg.get(cur.parent)
    return False


def related(a, b, reg):
    return is_ancestor(a, b, reg) or is_ancestor(b, a, reg)


def norm_label(label):
    return re.sub(r"[^a-z0-9 ]", "", (label or "").lower()).strip()


def build_connections(blocks, reg, report):
    """One model connection per distinct relationship, shared across levels.

    Two statements with the same label whose ends are hierarchically related
    describe one relationship seen from two altitudes, so they collapse into a
    single connection authored at the shallower pair — the level whose wording
    the label suits. Each block's diagram still draws it against the objects
    visible there.
    """
    rels = [r for b in blocks for r in b.rels]
    for r in rels:
        for end in (r.origin, r.target):
            if end not in reg:
                report.add("problems", f"relationship references undeclared alias `{end}`")

    groups = []
    for r in rels:
        if r.origin not in reg or r.target not in reg:
            continue
        for g in groups:
            h = g[0]
            if norm_label(h.label) == norm_label(r.label) and h.direction == r.direction \
                    and related(h.origin, r.origin, reg) and related(h.target, r.target, reg):
                g.append(r)
                break
        else:
            groups.append([r])

    conns = []
    for g in groups:
        # Author at the shallowest pair: a business-register label belongs to the
        # highest level it was stated at.
        lead = min(g, key=lambda r: depth_of(r.origin, reg) + depth_of(r.target, reg))
        name, descr = lead.label, lead.descr
        words = (name or "").split()
        if not name:
            name = "Connects to"
            report.add("labels", f"`{lead.origin}` -> `{lead.target}` had no label — "
                                 f"named \"Connects to\", rename it")
        elif len(words) > MAX_LABEL_WORDS or CODE_HINTS.search(name):
            descr = " ".join(x for x in (name, descr) if x)
            name = " ".join(words[:4])
            report.add("labels", f"`{lead.origin}` -> `{lead.target}` label was verbose "
                                 f"or code-shaped — moved to the description, "
                                 f"provisionally named **{name}**, rewrite it")
        ref = f"conn-{slug(lead.origin)}-{slug(lead.target)}-{slug(norm_label(lead.label), 'rel')}"
        techs = sorted({r.techn for r in g if r.techn})
        conn = {"id": ref, "name": name, "direction": lead.direction,
                "originId": lead.origin, "targetId": lead.target}
        if descr:
            conn["description"] = descr
        conns.append((conn, techs))
        for r in g:
            r.ref = ref
        if len(g) > 1:
            levels = ", ".join(sorted({f"{r.origin}->{r.target}" for r in g}))
            report.add("merged", f"**{name}** stated at several levels ({levels}) — "
                                 f"one connection authored as "
                                 f"`{lead.origin}` -> `{lead.target}`, redrawn on each diagram")
    return conns


# ----------------------------------------------------------------- layout

def subject_of(block, reg, areas):
    """The boundary the diagram opens up — the one holding the most objects."""
    ranked = [a for a in areas if reg[a].type in ("system", "app", "store")]
    if not ranked:
        return None
    return max(ranked, key=lambda a: len(descendants(a, reg)))


def layout(block, reg, report):
    """Place a block's objects on the 384x320 grid, initiators at the top.

    The diagram's subject boundary holds the middle rows, ranked by the request
    path through it. Everything outside that boundary is pushed clear of it —
    callers to the first row with the actors, dependencies to the last — because
    an area is auto-sized around its children, so a non-member left sitting
    between two members would be swallowed by the boundary it does not belong to.
    """
    aliases = [a for a in block.aliases if reg[a].type != "domain"]
    here = set(aliases)
    # Being a boundary is per diagram, not per object. An app is the boundary on
    # the component diagram that opens it up, and an ordinary box on the
    # container diagram above, which shows none of its components.
    areas = [a for a in aliases if reg[a].is_boundary
             and any(d in here for d in descendants(a, reg))]
    boxes = [a for a in aliases if a not in areas]
    if not boxes:
        return [], []

    edges = []
    for r in block.rels:
        if r.origin in boxes and r.target in boxes:
            # Rel_U asks for the target above the origin, so the edge runs upward.
            edges.append((r.target, r.origin) if r.hint == "up" else (r.origin, r.target))

    subject = subject_of(block, reg, areas)
    inside = {a for a in boxes if subject and subject in (reg[a].stack or [])}
    if not inside:
        inside = {a for a in boxes if reg[a].type != "actor" and not reg[a].external}

    rank = {}
    for a in boxes:
        rank[a] = 0 if reg[a].type == "actor" else 1
    for _ in range(len(boxes) + 1):
        changed = False
        for src, dst in edges:
            if dst not in inside or reg[dst].type == "actor":
                continue
            if src in inside or reg[src].type == "actor":
                if rank[dst] <= rank[src]:
                    rank[dst] = rank[src] + 1
                    changed = True
        if not changed:
            break

    # Outsiders go above or below the boundary, never level with it.
    floor = max([rank[a] for a in inside], default=0)
    for a in boxes:
        if a in inside or reg[a].type == "actor":
            continue
        calls_in = any(o == a and d in inside for o, d in edges)
        called_by = any(d == a and o in inside for o, d in edges)
        rank[a] = 0 if (calls_in and not called_by) else floor + 1

    # Two barycentre passes to reduce crossings, then keep members of the same
    # boundary contiguous within a row.
    order = {a: float(i) for i, a in enumerate(boxes)}
    for _ in range(2):
        for a in boxes:
            nbrs = [o for o, d in edges if d == a] + [d for o, d in edges if o == a]
            nbrs = [n for n in nbrs if rank[n] != rank[a]]
            if nbrs:
                order[a] = sum(order[n] for n in nbrs) / len(nbrs)

    def group_key(a):
        return "/".join(x for x in (reg[a].stack or []) if x in areas)

    placed, y = [], 0
    canvas = widest(boxes, rank, block)
    for r in sorted({rank[a] for a in boxes}):
        row = sorted([a for a in boxes if rank[a] == r], key=lambda a: (group_key(a), order[a]))
        for chunk in [row[i:i + block.shapes_in_row]
                      for i in range(0, len(row), block.shapes_in_row)]:
            span = len(chunk) * PITCH_X - (PITCH_X - BOX_W)
            x0 = max(0, (canvas - span) // 2)
            x0 -= x0 % 8
            for i, a in enumerate(chunk):
                placed.append({"ref": a, "x": x0 + i * PITCH_X, "y": y})
            y += PITCH_Y
    pos = {p["ref"]: p for p in placed}

    # An area's origin is the top-left of the children it wraps; IcePanel grows
    # it from there and insets each nesting level itself.
    area_specs = []
    for a in sorted(areas, key=lambda a: -len(descendants(a, reg))):
        kids = [pos[k] for k in descendants(a, reg) if k in pos]
        if not kids:
            report.add("problems", f"boundary `{a}` has nothing placed inside it on "
                                   f"\"{block.title or block.kind}\" — dropped from the diagram")
            continue
        area_specs.append({"ref": a, "shape": "area",
                           "x": min(k["x"] for k in kids), "y": min(k["y"] for k in kids)})
    return placed, area_specs


def widest(boxes, rank, block):
    counts = defaultdict(int)
    for a in boxes:
        counts[rank[a]] += 1
    n = min(max(counts.values(), default=1), block.shapes_in_row)
    return n * PITCH_X - (PITCH_X - BOX_W)


def descendants(alias, reg):
    out, stack = [], [alias]
    while stack:
        cur = stack.pop()
        for c in reg[cur].children if cur in reg else []:
            out.append(c)
            stack.append(c)
    return out


# ---------------------------------------------------------------- diagrams

def diagram_spec(block, reg, domain_alias, report, counters):
    boxes, areas = layout(block, reg, report)
    if not boxes:
        report.add("problems", f"block \"{block.title or block.kind}\" has no placeable "
                               f"objects — no diagram written")
        return None

    placed = {b["ref"] for b in boxes} | {a["ref"] for a in areas}
    dtype, model_ref = diagram_target(block, reg, placed, report)
    counters[dtype] = counters.get(dtype, 0) + 1

    connections = []
    for r in block.rels:
        if not r.ref or r.origin not in placed or r.target not in placed:
            if r.ref:
                report.add("problems", f"connection **{r.label}** skipped on "
                                       f"\"{block.title or block.kind}\": an end is not on it")
            continue
        connections.append({"ref": r.ref, "from": r.origin, "to": r.target})

    name = block.title or f"{reg[domain_alias].name} — {block.kind}"
    return {
        "name": name,
        "type": dtype,
        "modelId": model_ref,
        "index": counters[dtype],
        "description": f"Imported from the {block.kind} Mermaid diagram in {block.source}.",
        "objects": areas + boxes,
        "connections": connections,
    }


def diagram_target(block, reg, placed, report):
    """Diagram type and the model object it opens up."""
    if block.kind == "context":
        return "context-diagram", "@root"
    if block.kind == "deployment":
        report.add("inferred", f"\"{block.title or 'deployment'}\" is a C4Deployment — "
                               f"IcePanel has no deployment diagram, so it is drawn as a "
                               f"context diagram with the nodes as group areas")
        return "context-diagram", "@root"

    subjects = [a for a in placed if reg[a].is_boundary and reg[a].type in ("system", "app", "store")]
    if block.kind == "container":
        systems = [a for a in subjects if reg[a].type == "system"]
        if systems:
            best = max(systems, key=lambda a: len(descendants(a, reg)))
            return "app-diagram", best
        report.add("inferred", f"\"{block.title or 'container'}\" declares no system boundary — "
                               f"drawn as a context diagram instead of an app diagram")
        return "context-diagram", "@root"

    hosts = [a for a in subjects if reg[a].type in ("app", "store")]
    if hosts:
        best = max(hosts, key=lambda a: len(descendants(a, reg)))
        return "component-diagram", best
    systems = [a for a in subjects if reg[a].type == "system"]
    if systems:
        return "app-diagram", max(systems, key=lambda a: len(descendants(a, reg)))
    report.add("inferred", f"\"{block.title or block.kind}\" declares no container boundary — "
                           f"drawn as a context diagram")
    return "context-diagram", "@root"


# ------------------------------------------------------------------ output

def build_model(reg, conns, namespace, report):
    objects = []
    for e in reg.values():
        o = {"id": e.alias, "name": e.name, "type": e.type}
        if e.parent:
            o["parentId"] = e.parent
        # Caption mirrors the description, trimmed to label shape: a few words,
        # no trailing stop, since it renders under the name on every diagram.
        if e.descr:
            o["description"] = e.descr
            o["caption"] = caption_from(e.descr)
        else:
            # Left absent rather than empty: an omitted description is preserved on
            # re-import, while an empty string would wipe whatever is already there.
            report.add("descriptions", f"`{e.alias}` (**{e.name}**, {e.type}) — "
                                       f"Mermaid gave no description")
        if e.external:
            o["external"] = True
        if e.groups:
            o["groupIds"] = e.groups
        if e.techn:
            report.add("technologies", f"`{e.alias}` (**{e.name}**) — techn "
                                       f"\"{e.techn}\", not yet looked up")
        if e.link:
            o["links"] = {"mermaid": {"name": "Link", "url": e.link}}
        objects.append(o)

    connections = []
    for conn, techs in conns:
        connections.append(conn)
        for t in techs:
            report.add("technologies", f"`{conn['id']}` — techn \"{t}\", not yet looked up")

    order = {"domain": 0, "group": 1, "actor": 2, "system": 3, "app": 4, "store": 5, "component": 6}
    objects.sort(key=lambda o: (order.get(o["type"], 9), o["name"]))
    return {"namespace": namespace, "modelObjects": objects, "modelConnections": connections}


def group_passes(model, reg):
    """Split the import when groups nest, innermost last.

    A group parented to another group fails with `Parent not found` when both
    are created in one request, and that failure cascades to every object
    listing the nested group in `groupIds`. So nested groups go in ahead of the
    model, one pass per level, each re-declaring the ancestors it hangs from
    because `parentId` resolves against the file alone.
    """
    depth = {}
    for o in model["modelObjects"]:
        if o["type"] != "group":
            continue
        d, cur, seen = 0, o.get("parentId"), set()
        while cur and cur in reg and reg[cur].type == "group" and cur not in seen:
            seen.add(cur)
            d += 1
            cur = reg[cur].parent
        depth[o["id"]] = d
    if not depth or max(depth.values()) == 0:
        return []

    domain = [o for o in model["modelObjects"] if o["type"] == "domain"]
    passes = []
    for level in range(max(depth.values()) + 1):
        objs = domain + [o for o in model["modelObjects"]
                         if o["type"] == "group" and depth[o["id"]] <= level]
        passes.append({"namespace": model["namespace"], "modelObjects": objs,
                       "modelConnections": []})
    return passes


def caption_from(descr):
    """A description trimmed to caption shape: first clause, no trailing stop."""
    text = re.split(r"(?<=[a-z0-9])[.;:]|\s+[-—]\s+|,\s+(?:and|with|which|that)\b",
                    descr.strip(), maxsplit=1)[0]
    words = text.split()
    if len(words) > 8:
        words = words[:8]
    return " ".join(words).rstrip(" .,;:")


SECTION_TITLES = [
    ("problems", "Problems — read these first"),
    ("duplicates", "Probable duplicates from inconsistent aliases"),
    ("conflicts", "Conflicting declarations"),
    ("placeholders", "Invented objects"),
    ("renames", "Renamed for domain-wide uniqueness"),
    ("inferred", "Inferences"),
    ("merged", "Connections merged across levels"),
    ("labels", "Labels needing a rewrite"),
    ("reversed", "Reversed by Rel_Back — check each direction"),
    ("descriptions", "Missing descriptions — generate these"),
    ("technologies", "Technology strings to look up"),
    ("dropped", "Dropped input"),
]


def write_report(path, report, model, specs, domain_name):
    lines = [f"# Mermaid C4 import — {domain_name}", "",
             f"{len(model['modelObjects'])} objects, "
             f"{len(model['modelConnections'])} connections, {len(specs)} diagrams.", ""]
    for key, title in SECTION_TITLES:
        items = report.sections.get(key)
        if not items:
            continue
        lines += [f"## {title}", ""]
        lines += [f"- {i}" for i in items]
        lines.append("")
    lines += ["## Diagrams", ""]
    for s in specs:
        lines.append(f"- **{s['name']}** — {s['type']} on `{s['modelId']}`, "
                     f"{len(s['objects'])} objects, {len(s['connections'])} connections")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))


def cmd_parse(args):
    report = Report()
    sources = []
    for path in args.inputs:
        if path == "-":
            sources.append(("stdin", sys.stdin.read()))
        else:
            with open(path) as f:
                sources.append((os.path.basename(path), f.read()))

    blocks_text = []
    for name, text in sources:
        found = extract_blocks(text, name)
        if not found:
            print(f"warning: no C4 blocks found in {name}", file=sys.stderr)
        blocks_text += found
    if not blocks_text:
        raise MermaidError("no Mermaid C4 blocks found in the input")

    alias_map = {}
    for pair in args.alias:
        if "=" not in pair:
            raise MermaidError(f"--alias expects OLD=NEW, got '{pair}'")
        old, new = pair.split("=", 1)
        alias_map[old.strip()] = new.strip()

    reg, blocks = {}, []
    for i, (source, text) in enumerate(blocks_text, 1):
        blocks.append(parse_block(text, source, i, reg, report, alias_map))

    # A block can relate to an object another block declares. Merging makes that
    # resolvable, so the object belongs on this block's diagram too — otherwise
    # the relationship has nowhere to land and quietly disappears.
    for b in blocks:
        for r in b.rels:
            for end in (r.origin, r.target):
                if end in reg and end not in b.aliases:
                    b.aliases.append(end)

    domain_alias = classify(reg, blocks, report)
    domain_name = args.domain
    if not domain_name and domain_alias:
        domain_name = reg[domain_alias].label
    if not domain_name:
        title = next((b.title for b in blocks if b.title), None)
        domain_name = title_subject(title)
        if domain_name:
            report.add("inferred", f"domain named **{domain_name}**, taken from the "
                                   f"diagram title \"{title}\"")
    if not domain_name:
        raise MermaidError("no Enterprise_Boundary and no title to name the domain from; "
                           "pass --domain")

    did = build_hierarchy(reg, domain_alias, domain_name, report)
    detect_duplicates(reg, report)
    dedupe_names(reg, report)
    conns = build_connections(blocks, reg, report)

    specs, counters = [], {}
    for b in blocks:
        spec = diagram_spec(b, reg, did, report, counters)
        if spec:
            specs.append(spec)

    model = build_model(reg, conns, args.namespace, report)
    report.finalise()

    os.makedirs(args.out, exist_ok=True)
    passes = group_passes(model, reg)
    for i, p in enumerate(passes, 1):
        with open(os.path.join(args.out, f"groups-{i:02d}.json"), "w") as f:
            json.dump(p, f, indent=2)
    with open(os.path.join(args.out, "model.json"), "w") as f:
        json.dump(model, f, indent=2)
    for i, spec in enumerate(specs, 1):
        fname = f"diagram-{i:02d}-{slug(spec['name'])[:40]}.json"
        with open(os.path.join(args.out, fname), "w") as f:
            json.dump(spec, f, indent=2)
    write_report(os.path.join(args.out, "report.md"), report, model, specs, domain_name)

    for i, p in enumerate(passes, 1):
        print(f"wrote {args.out}/groups-{i:02d}.json — {len(p['modelObjects'])} objects "
              f"(nested groups need their own pass; import these first, in order)")
    print(f"wrote {args.out}/model.json — {len(model['modelObjects'])} objects, "
          f"{len(model['modelConnections'])} connections")
    for i, spec in enumerate(specs, 1):
        print(f"wrote {args.out}/diagram-{i:02d}-*.json — {spec['type']} "
              f"'{spec['name']}' ({len(spec['objects'])} objects)")
    print(f"wrote {args.out}/report.md")
    counts = {k: len(v) for k, v in report.sections.items() if v}
    if counts:
        print("\nreport: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
        print("read report.md and confirm it with the user before importing")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("parse")
    q.add_argument("inputs", nargs="+")
    q.add_argument("--out", default="mermaid-c4")
    q.add_argument("--domain", default=None)
    q.add_argument("--namespace", default="mermaid-c4")
    q.add_argument("--alias", action="append", default=[], metavar="OLD=NEW",
                   help="treat alias OLD as the same object as NEW; repeatable")
    q.set_defaults(func=cmd_parse)
    args = p.parse_args()
    try:
        args.func(args)
    except MermaidError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

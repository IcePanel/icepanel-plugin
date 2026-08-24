#!/usr/bin/env python3
"""Helper for building C4 models and diagrams in IcePanel.

Commands:
    import <landscapeId> <model.json> [--prune]   upsert model objects/connections, poll to completion
    idmap  <landscapeId> [--out idmap.json]       map your import IDs -> IcePanel IDs
    diagram <landscapeId> <spec.json>             create a diagram from a layout spec
    verify <landscapeId>                          check every diagram for layout/model problems

Auth comes from $ICEPANEL_TOKEN (the "<key-id>:<secret>" API key).

HTTP goes through curl rather than urllib on purpose: Python installs on macOS
frequently lack a configured CA bundle, which fails with CERTIFICATE_VERIFY_FAILED
against api.icepanel.io. curl uses the system trust store and just works.
"""

import argparse
import json
import os
import subprocess
import sys
import time

BASE = os.environ.get("ICEPANEL_API_BASE", "https://api.icepanel.io").rstrip("/") + "/v1"

# IcePanel's default box size. Not sent — sizes are optional and the API applies
# this itself — but the overlap check needs to know how big a box will end up.
BOX_W, BOX_H = 256, 128


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def token():
    t = os.environ.get("ICEPANEL_TOKEN")
    if not t:
        die("set ICEPANEL_TOKEN to your '<key-id>:<secret>' API key")
    return t


def api(method, path, body=None):
    cmd = ["curl", "-sS", "-X", method, f"{BASE}{path}",
           "-H", f"X-API-Key: {token()}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        die(f"curl failed: {out.stderr.strip()}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        die(f"non-JSON response from {method} {path}: {out.stdout[:400]}")


def scope(landscape, version="latest"):
    return f"/landscapes/{landscape}/versions/{version}"


def check(resp, what):
    """API errors come back as a body with 'errors'/'message' and no payload."""
    if "errors" in resp or ("message" in resp and what not in resp):
        print(json.dumps(resp, indent=2)[:2000], file=sys.stderr)
        die(f"request failed while creating {what}")
    return resp


# --------------------------------------------------------------------------- import

def cmd_import(args):
    with open(args.file) as f:
        body = json.load(f)
    path = f"{scope(args.landscape)}/import" + ("?prune=true" if args.prune else "")
    if args.prune:
        print("WARNING: prune=true permanently deletes anything absent from this file")
    imp = api("POST", path, body).get("landscapeImport")
    if not imp:
        die("import was not accepted; check the request body against references/api.md")
    print(f"import {imp['id']} submitted, polling...")

    for _ in range(60):
        cur = api("GET", f"{scope(args.landscape)}/import/{imp['id']}")["landscapeImport"]
        if cur["status"] != "in-progress":
            break
        time.sleep(2)
    else:
        die("import still in progress after 2 minutes")

    print(f"status: {cur['status']}")
    for e in cur.get("errors", []):
        print(f"  ! {e.get('entityType','?')} "
              f"{e.get('entityId') or e.get('entityOriginalId') or '?'}: {e.get('message')}")
    if cur["status"] != "completed":
        sys.exit(1)
    print(f"  {len(body.get('modelObjects', []))} objects, "
          f"{len(body.get('modelConnections', []))} connections upserted")


# --------------------------------------------------------------------------- idmap

def fetch_model(landscape):
    objs = api("GET", f"{scope(landscape)}/model/objects")["modelObjects"]
    cons = api("GET", f"{scope(landscape)}/model/connections")["modelConnections"]
    return objs, cons


def build_idmap(landscape):
    """Map import IDs and raw IDs to IcePanel IDs, plus the type of each object."""
    objs, cons = fetch_model(landscape)
    refs, types, names = {}, {}, {}
    for o in objs:
        refs[o["id"]] = o["id"]
        orig = o.get("labels", {}).get("import-original-id")
        if orig:
            refs[orig] = o["id"]
        types[o["id"]] = o["type"]
        names[o["id"]] = o.get("name") or "(unnamed)"
    for c in cons:
        refs[c["id"]] = c["id"]
        orig = c.get("labels", {}).get("import-original-id")
        if orig:
            refs[orig] = c["id"]
        names[c["id"]] = c.get("name") or "(unnamed)"

    # '@root' resolves to the domain root that actually holds the model.
    roots = [o for o in objs if o["type"] == "root"]
    populated = [r for r in roots if any(o.get("parentId") == r["id"] for o in objs)]
    if len(populated) == 1:
        refs["@root"] = populated[0]["id"]
    elif populated:
        refs["@root"] = None
        refs["@root_options"] = {names[r["id"]]: r["id"] for r in populated}
    return {"refs": refs, "types": types, "names": names}


def cmd_idmap(args):
    m = build_idmap(args.landscape)
    with open(args.out, "w") as f:
        json.dump(m, f, indent=2)
    imported = {k: v for k, v in m["refs"].items() if k != v and not k.startswith("@")}
    if imported:
        print(f"wrote {args.out}: {len(imported)} import IDs resolved")
        for k, v in sorted(imported.items()):
            print(f"  {k:28} {v:22} {m['names'].get(v,'')}")
        return
    # A model authored in the UI carries no import labels. Listing the objects is
    # what's actually useful there, since a diagram spec's refs use these IDs.
    objs = m["types"]
    print(f"wrote {args.out}: no import IDs — model not built by import; "
          f"{len(objs)} objects, use these IDs as refs")
    for oid, t in sorted(objs.items(), key=lambda kv: (kv[1], m["names"].get(kv[0], ""))):
        print(f"  {t:10} {oid:22} {m['names'].get(oid, '')}")


# --------------------------------------------------------------------------- diagram

def size_of(o):
    """Effective box size: whatever was set, else IcePanel's default."""
    return o.get("width") or BOX_W, o.get("height") or BOX_H


def validate(objects, connections, names):
    problems, notes = [], []
    boxes = [o for o in objects if o["shape"] == "box"]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            aw, ah = size_of(a)
            bw, bh = size_of(b)
            if (a["x"] < b["x"] + bw and b["x"] < a["x"] + aw and
                    a["y"] < b["y"] + bh and b["y"] < a["y"] + ah):
                problems.append(f"boxes overlap: {names.get(a['modelId'])} / {names.get(b['modelId'])}")
    for ar in [o for o in objects if o["shape"] == "area"]:
        # Areas carry no size: IcePanel grows the boundary around whichever
        # children are on the diagram, so there is no geometry to check. Only a
        # hand-sized area can fail to cover its contents.
        aw, ah = ar.get("width"), ar.get("height")
        if not aw and not ah:
            notes.append(f"area '{names.get(ar['modelId'])}' auto-sizes around its children")
            continue
        inside = [b for b in boxes
                  if b["x"] >= ar["x"] and b["y"] >= ar["y"]
                  and b["x"] + size_of(b)[0] <= ar["x"] + aw
                  and b["y"] + size_of(b)[1] <= ar["y"] + ah]
        notes.append(f"area '{names.get(ar['modelId'])}' encloses {len(inside)} object(s): "
                     + ", ".join(names.get(b["modelId"], "?") for b in inside))
    for c in connections:
        if not c.get("modelId"):
            problems.append(f"connection {c['id']} has no model connection behind it (drift)")
    return problems, notes


def cmd_diagram(args):
    with open(args.spec) as f:
        spec = json.load(f)
    m = build_idmap(args.landscape) if not os.path.exists(args.idmap) else json.load(open(args.idmap))
    refs, types, names = m["refs"], m["types"], m["names"]

    def resolve(ref, kind):
        if ref not in refs or refs[ref] is None:
            if ref == "@root" and refs.get("@root_options"):
                die(f"several populated domains; use one of {refs['@root_options']}")
            die(f"unknown {kind} reference '{ref}' — is it in the model and the idmap current?")
        return refs[ref]

    objects, seen = [], {}
    for o in spec["objects"]:
        mid = resolve(o["ref"], "object")
        shape = o.get("shape", "box")
        key = f"{mid}-area" if shape == "area" else mid
        obj = {"id": key, "modelId": mid,
               "type": o.get("type", types.get(mid, "system")),
               "shape": shape,
               "x": o["x"], "y": o["y"]}
        # Size is optional. Omit it and IcePanel applies its default box size, and
        # grows an area around whichever children are on the diagram. Only pass a
        # size when the spec deliberately asks for an off-default box.
        if shape == "box":
            if o.get("w"):
                obj["width"] = o["w"]
            if o.get("h"):
                obj["height"] = o["h"]
        objects.append(obj)
        if obj["shape"] == "box":
            seen[mid] = key

    connections = []
    for c in spec["connections"]:
        cid = resolve(c["ref"], "connection")
        origin, target = resolve(c["from"], "object"), resolve(c["to"], "object")
        for end, ref in ((origin, c["from"]), (target, c["to"])):
            if end not in seen:
                die(f"connection '{c['ref']}' references '{ref}', which is not placed on this diagram")
        # Anchors, line shape and label position are all computed by IcePanel from
        # the geometry. Only send an override the spec explicitly asked for.
        conn = {"id": cid, "modelId": cid, "originId": origin, "targetId": target}
        for field in ("lineShape", "labelPosition", "originConnector", "targetConnector"):
            if c.get(field) is not None:
                conn[field] = c[field]
        connections.append(conn)

    problems, notes = validate(objects, connections, names)
    for n in notes:
        print(f"  {n}")
    if problems:
        for p in problems:
            print(f"  ! {p}")
        if not args.force:
            die("fix the problems above, or pass --force to post anyway")

    body = {"name": spec["name"], "type": spec["type"],
            "modelId": resolve(spec["modelId"], "object"),
            "index": spec.get("index", 1), "status": "current",
            "objects": {o["id"]: o for o in objects},
            "connections": {c["id"]: c for c in connections}}
    if spec.get("description"):
        body["description"] = spec["description"]

    d = check(api("POST", f"{scope(args.landscape)}/diagrams", body), "diagram")["diagram"]
    print(f"created {d['type']} '{d['name']}' ({d['id']}) — "
          f"{len(objects)} objects, {len(connections)} connections")


# --------------------------------------------------------------------------- verify

def cmd_verify(args):
    m = build_idmap(args.landscape)
    names = m["names"]
    diagrams = api("GET", f"{scope(args.landscape)}/diagrams").get("diagrams", [])
    if not diagrams:
        print("no diagrams in this landscape")
        return
    failed = False
    for d in sorted(diagrams, key=lambda x: (x["type"], x.get("index", 0))):
        content = api("GET", f"{scope(args.landscape)}/diagrams/{d['id']}/content")
        dc = content.get("diagramContent", content)
        objs, cons = list(dc["objects"].values()), list(dc["connections"].values())
        print(f"\n{d['type']}: {d['name']} — {len(objs)} objects, {len(cons)} connections")
        if not d.get("description"):
            print("  ! no description set")
        problems, notes = validate(objs, cons, names)
        for n in notes:
            print(f"  {n}")
        for p in problems:
            print(f"  ! {p}")
            failed = True
    print()
    sys.exit(1 if failed else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("import"); i.add_argument("landscape"); i.add_argument("file")
    i.add_argument("--prune", action="store_true"); i.set_defaults(func=cmd_import)

    m = sub.add_parser("idmap"); m.add_argument("landscape")
    m.add_argument("--out", default="idmap.json"); m.set_defaults(func=cmd_idmap)

    d = sub.add_parser("diagram"); d.add_argument("landscape"); d.add_argument("spec")
    d.add_argument("--idmap", default="idmap.json"); d.add_argument("--force", action="store_true")
    d.set_defaults(func=cmd_diagram)

    v = sub.add_parser("verify"); v.add_argument("landscape"); v.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

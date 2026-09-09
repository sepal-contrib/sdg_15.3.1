"""Graph-introspection primitives shared by the engine (ee-graph) tests.

Extracted verbatim from test_integration.py (Task 10) and test_productivity.py
(Task 11), which had grown near-duplicate copies of the same walk. This code has
been debugged twice -- once for the `functionDefinitionValue.body` indirection
during Task 10's fix round, once for reading through a wrapper node without
recording it during Task 11's round 2 -- and one copy that survived both beats
three that each survived one. Task-specific walkers stay in the file that needs
them; only the primitives every engine test file wants live here.

Two indirections every reader of an ARGUMENT's value has to resolve:

* `ee.serializer.encode()` hoists a repeated CONSTANT (not just a repeated
  computed subexpression) into the `values` registry and points every use of it
  at that one entry via `{"valueReference": K}` -- e.g. the string "year" is used
  as a Filter.calendarRange field name, a `.set()` property key AND a `.rename()`
  target in the same graph, so it is stored once and referenced three times
  rather than inlined three times.
* A `.map()`/`.reduce()` callback body is a bare string key into `values` under
  `functionDefinitionValue`, NOT a `{"valueReference": ...}` wrapper, so it has
  to be followed explicitly or the whole callback subtree is invisible.

Anything that inspects a specific argument's value (rather than merely noting a
raw substring) has to resolve both, or it silently stops working the moment ee
decides to share a value it previously inlined.
"""

from __future__ import annotations

import json

import ee


def encoded(obj) -> str:
    """The serialized graph as one string, for substring assertions."""
    return json.dumps(ee.serializer.encode(obj), sort_keys=True)


def count_calls(obj, function_name: str) -> int:
    """Count DISTINCT nodes invoking `function_name`.

    The ee serializer collapses structurally identical subtrees into a single
    scope entry, so this counts distinct nodes, not textual occurrences.
    """
    graph = ee.serializer.encode(obj)
    total = 0
    stack = [graph]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            call = node.get("functionInvocationValue")
            if isinstance(call, dict) and call.get("functionName") == function_name:
                total += 1
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return total


# --- reference-resolving graph walk -----------------------------------------


def _deref_for(obj):
    """Return `(deref, graph)` for `obj`'s encoded graph."""
    graph = ee.serializer.encode(obj)
    values = graph.get("values", {})

    def deref(node):
        while isinstance(node, dict) and set(node) == {"valueReference"}:
            node = values[node["valueReference"]]
        return node

    return deref, graph


def _call(node):
    """The `functionInvocationValue` dict of `node`, or None."""
    if isinstance(node, dict):
        call = node.get("functionInvocationValue")
        if isinstance(call, dict):
            return call
    return None


def _walk(node, deref, graph):
    """Yield every resolved node reachable from `node`.

    A `.map()`/`.reduce()` callback body is a bare string key into `values`
    rather than a `{"valueReference": ...}` wrapper, so it is followed
    explicitly -- the second indirection the module docstring documents.
    """
    values = graph.get("values", {})
    stack = [node]
    seen: set[int] = set()
    while stack:
        current = deref(stack.pop())
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        if isinstance(current, dict):
            body = current.get("functionDefinitionValue")
            if isinstance(body, dict) and body.get("body") in values:
                stack.append(values[body["body"]])
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _root(obj):
    """`(deref, graph, result node)` for `obj`."""
    deref, graph = _deref_for(obj)
    return deref, graph, deref({"valueReference": graph["result"]})


# --- constants, band names and asset ids -------------------------------------


def _image_constant(node, deref):
    """The scalar behind an `ee.Image(k)` argument node, or None."""
    call = _call(node)
    if call is not None and call.get("functionName") == "Image.constant":
        inner = deref(call.get("arguments", {}).get("value", {}))
        if isinstance(inner, dict):
            return inner.get("constantValue")
    return None


def _constants_in(node, deref, graph):
    """Every `ee.Image(k)` constant under `node`."""
    values = set()
    for current in _walk(node, deref, graph):
        constant = _image_constant(current, deref)
        if constant is not None:
            values.add(constant)
    return values


def _image_constants(obj):
    """Every `ee.Image(k)` constant in the graph."""
    deref, graph, root = _root(obj)
    return _constants_in(root, deref, graph)


def _string_list_arg(arg, deref):
    """The strings behind a `names`/`bandSelectors` argument.

    It is `{"constantValue": [...]}` when inlined and `{"arrayValue":
    {"values": [...]}}` when the list -- or one of its elements -- is itself
    hoisted into `values`, so both are resolved, and each element is resolved
    individually since a shared list can mix inlined and referenced items.
    """
    if not isinstance(arg, dict):
        return []
    if isinstance(arg.get("constantValue"), list):
        items = arg["constantValue"]
    else:
        items = arg.get("arrayValue", {}).get("values", [])
    names = []
    for item in items:
        value = deref(item)
        if isinstance(value, dict):
            value = value.get("constantValue")
        if isinstance(value, str):
            names.append(value)
    return names


def _select_bands_of(node, deref):
    """The band names of an `Image.select` node, or None if it is not one."""
    call = _call(node)
    if call is None or call.get("functionName") != "Image.select":
        return None
    return _string_list_arg(deref(call.get("arguments", {}).get("bandSelectors", {})), deref)


def _selected_bands(obj):
    """Every band name passed to `.select(...)` anywhere in the graph."""
    deref, graph, root = _root(obj)
    names = set()
    for current in _walk(root, deref, graph):
        names.update(_select_bands_of(current, deref) or [])
    return names


def _renamed_bands(obj):
    """Every band name passed to `.rename(...)` anywhere in the graph."""
    deref, graph, root = _root(obj)
    names = set()
    for current in _walk(root, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") != "Image.rename":
            continue
        names.update(_string_list_arg(deref(call.get("arguments", {}).get("names", {})), deref))
    return names


def _loaded_assets_in(node, deref, graph):
    """Every asset id loaded under `node`."""
    ids = set()
    for current in _walk(node, deref, graph):
        call = _call(current)
        if call is None or call.get("functionName") not in ("Image.load", "ImageCollection.load"):
            continue
        value = deref(call.get("arguments", {}).get("id", {}))
        if isinstance(value, dict) and isinstance(value.get("constantValue"), str):
            ids.add(value["constantValue"])
    return ids


def _loaded_asset_ids(obj) -> set[str]:
    """Every asset id ee actually loaded: the `id` argument of every
    `ImageCollection.load` / `Image.load` node in the serialized graph."""
    deref, graph, root = _root(obj)
    return _loaded_assets_in(root, deref, graph)

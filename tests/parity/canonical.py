"""A scope-numbering-independent canonical form for an encoded ``ee`` graph.

``ee.serializer.encode()`` emits ``{"result": key, "values": {key: node}}``, where
the keys are handed out in traversal order and a node is either INLINED at its use
site or hoisted into ``values`` and pointed at by ``{"valueReference": key}``.
Both of those are presentation, not meaning: inserting one node near the root
shifts every later key, so two graphs that differ by a single node can differ in
every line of their serialization. That is why the port's one extra
``Image.rename`` could not be compared away by a string edit, and why the first
pass at Task 17 reached for a corpus-wide licence over the whole indicator layer
instead -- which licensed the 30-rule collapse, its rule order, the water mask and
the cast position along with it.

:func:`canonical_graph` removes both degrees of freedom:

* every ``valueReference`` is resolved, so an inlined node and a hoisted one with
  the same structure become the same node;
* every composite (dict or list) is hoisted and hash-consed, so identical
  structures land on one entry;
* ids are handed out in first-visit order of a walk that sorts dict keys, so the
  order follows the graph's shape and not the order the JSON happened to load in.

What survives is exactly the expression: function names, argument names, argument
values, literals, and the sharing structure. :func:`render` prints that as one
line per node, which compares byte-for-byte and diffs readably.

Two indirections this has to get right, both documented in
``tests/engine/graph.py`` because each has already broken a walker on this plan:

* a ``.map()``/``.reduce()`` callback body is a BARE string key into ``values``
  under ``functionDefinitionValue``, not a ``{"valueReference": ...}`` wrapper, so
  it has to be followed explicitly or the whole callback subtree is invisible;
* a repeated CONSTANT is hoisted too, not just a repeated computed subexpression,
  so an argument reader that does not resolve references sees a reference where it
  expected a value.

A ``values`` entry that nothing reachable from ``result`` points at is dropped: it
is not part of the expression. ``ee`` does not emit those, but saying so is
cheaper than wondering.

:func:`strip_indicator_band_rename` is the port's one NORMALISATION, as opposed to
a licence: it splices out the terminal ``.rename("indicator_15_3_1")`` that
``run_15_3_1.py:411`` never emitted, and nothing else. It refuses to fire unless it
finds that exact node in that exact position, so a port whose cast or water mask
moved is not normalised -- it fails.

``tests/parity/test_canonical.py`` is what keeps this file honest. A helper that
decides whether two graphs match is precisely the thing that must not be taken on
trust: an earlier probe at this same question compared ``(functionName, sorted
argument NAMES))`` multisets and reported the port and the legacy identical,
because a rename's value is inline in the arguments dict rather than a node of its
own.
"""

from __future__ import annotations

import copy
import json
from typing import Any

__all__ = [
    "INDICATOR_BAND",
    "canonical_graph",
    "function_name_counts",
    "render",
    "strip_indicator_band_rename",
]

INDICATOR_BAND = "indicator_15_3_1"

# wide enough for any graph this corpus produces, and zero-padded so a lexical
# sort of the rendered lines is also the numeric one
_ID_WIDTH = 6


def _tag(node_id: int) -> str:
    return f"{node_id:0{_ID_WIDTH}d}"


def canonical_graph(encoded: dict[str, Any]) -> dict[str, Any]:
    """The canonical form of ``encoded``.

    Returns the same ``{"result": ..., "values": ...}`` shape, with every
    composite hoisted, every reference rewritten to a canonical id and literals
    left inline. Idempotent: the canonical form of a canonical form is itself.
    """
    values: dict[str, Any] = encoded.get("values", {})
    ids: dict[Any, int] = {}
    definitions: list[Any] = []
    # id(node) -> canonical id. The structural key alone is not enough to memoise
    # on, because computing it walks the subtree: a node the graph shares 30 times
    # -- and the truth-table collapse shares its three operand images exactly that
    # often -- would be re-walked 30 times, and its own shared children 30 times
    # again, which is exponential rather than merely slow. Every node here is
    # reachable from `encoded` for the whole call, so no id can be recycled.
    seen: dict[int, int] = {}

    def resolve(node: Any) -> Any:
        """Follow a chain of ``valueReference`` wrappers to the node itself."""
        for _ in range(len(values) + 1):
            if not (isinstance(node, dict) and set(node) == {"valueReference"}):
                return node
            key = node["valueReference"]
            if key not in values:
                raise KeyError(f"valueReference {key!r} has no entry in values")
            node = values[key]
        raise ValueError("valueReference chain does not terminate")

    def named_children(node: Any) -> list[tuple[Any, Any]]:
        """``(name, resolved child)`` pairs of a composite, in canonical order.

        ``name`` is the dict key, or the index for a list. Sorting the dict keys
        here is what stops the order the JSON happened to load in from reaching
        the traversal -- and with it the ids.
        """
        if isinstance(node, dict):
            names: list[Any] = sorted(node)
        else:
            names = list(range(len(node)))
        pairs = []
        for name in names:
            child = node[name]
            if name == "body" and isinstance(child, str):
                # a function body is a bare key into `values`, not a wrapper
                child = values[child]
            pairs.append((name, resolve(child)))
        return pairs

    def slot(name: Any, child: Any) -> tuple[Any, Any]:
        """``(what the parent stores, the parent's key part)`` for one child.

        The child is already interned by the time this runs, so this is a lookup.
        """
        if isinstance(child, dict | list):
            child_id = seen[id(child)]
            if name == "body":
                return _tag(child_id), ("body", child_id)
            return {"valueReference": _tag(child_id)}, ("ref", child_id)
        return child, ("literal", json.dumps(child, sort_keys=True))

    def rewrite(node: Any) -> tuple[Any, Any]:
        """``(node with its children replaced by ids, hashable structural key)``.

        The key holds child IDS rather than child structures, so it stays small
        however deep the graph runs -- this is hash-consing, not stringification.
        """
        slots = [(name, *slot(name, child)) for name, child in named_children(node)]
        if isinstance(node, dict):
            return (
                {name: stored for name, stored, _ in slots},
                ("object", tuple((name, part) for name, _, part in slots)),
            )
        return [stored for _, stored, _ in slots], ("array", tuple(part for _, _, part in slots))

    def intern(root: Any) -> int:
        """Canonical ids for ``root`` and everything under it, children first.

        Iterative on purpose. A resolved graph is far deeper than the document it
        came from -- following references turns a shallow registry of nodes into
        one chain per year of the integration period -- and a recursive walk hits
        Python's stack limit on the wider corpus windows.
        """
        pending: list[tuple[Any, bool]] = [(root, False)]
        while pending:
            node, expanded = pending.pop()
            if id(node) in seen:
                continue
            if not expanded:
                pending.append((node, True))
                # reversed so the first child in canonical order is visited first
                for _, child in reversed(named_children(node)):
                    if isinstance(child, dict | list) and id(child) not in seen:
                        pending.append((child, False))
                continue
            rewritten, key = rewrite(node)
            node_id = ids.get(key)
            if node_id is None:
                node_id = len(definitions)
                ids[key] = node_id
                definitions.append(rewritten)
            seen[id(node)] = node_id
        return seen[id(root)]

    result = encoded["result"]
    root = values[result] if isinstance(result, str) and result in values else result
    root_id = intern(resolve(root))
    return {
        "result": _tag(root_id),
        "values": {_tag(index): node for index, node in enumerate(definitions)},
    }


def render(graph: dict[str, Any]) -> str:
    """One line per node, for byte comparison and for a readable diff."""
    canonical = canonical_graph(graph)
    lines = [f"result {canonical['result']}"]
    lines.extend(
        f"{key} {json.dumps(canonical['values'][key], sort_keys=True)}"
        for key in sorted(canonical["values"])
    )
    return "\n".join(lines)


def function_name_counts(encoded: dict[str, Any]) -> dict[str, int]:
    """How many DISTINCT nodes invoke each function name.

    Distinct rather than textual: the canonical form hash-conses, exactly as
    ``ee``'s own serializer does, so two structurally identical subtrees are one
    node in both. In the canonical form an invocation's ``{"functionName": ...,
    "arguments": ...}`` pair is a node of its own, so counting those counts calls.
    """
    counts: dict[str, int] = {}
    for node in canonical_graph(encoded)["values"].values():
        if isinstance(node, dict) and "functionName" in node:
            name = node["functionName"]
            counts[name] = counts.get(name, 0) + 1
    return counts


# --- the one normalisation, read against the RAW ee encoding -------------------
#
# The splice below walks `encoded` as `ee.serializer.encode()` emitted it, not the
# canonical form: the canonical form hoists every composite, so an invocation
# there is three nodes deep behind references and a reader of it would be checking
# its own bookkeeping rather than the graph. Here `functionInvocationValue` ->
# `arguments` -> the argument is the shape the serializer documents, which is what
# a reviewer can check the path against.


def _deref(values: dict[str, Any], node: Any) -> Any:
    """Follow ``valueReference`` wrappers to the node itself."""
    for _ in range(len(values) + 1):
        if not (isinstance(node, dict) and set(node) == {"valueReference"}):
            return node
        node = values[node["valueReference"]]
    raise ValueError("valueReference chain does not terminate")


def _invocation(node: Any, function: str) -> dict[str, Any] | None:
    """``node``'s ``functionInvocationValue`` if it invokes ``function``, else None."""
    if not isinstance(node, dict):
        return None
    call = node.get("functionInvocationValue")
    if isinstance(call, dict) and call.get("functionName") == function:
        return call
    return None


def _literal_list(values: dict[str, Any], argument: Any) -> list[Any] | None:
    """The literals behind a list-valued argument, or None if it is not one.

    ``ee`` spells such an argument ``{"constantValue": [...]}`` when the list is
    inlined and ``{"arrayValue": {"values": [...]}}`` when the list -- or one of
    its elements -- is hoisted, and a shared list can mix inlined and referenced
    items, so every hop is resolved (tests/engine/graph.py documents both). A list
    holding anything computed is not a literal list and yields None rather than a
    half-read answer.
    """
    node = _deref(values, argument)
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("constantValue"), list):
        items = node["constantValue"]
    else:
        array = node.get("arrayValue")
        items = array.get("values") if isinstance(array, dict) else None
    if not isinstance(items, list):
        return None
    literals = []
    for item in items:
        value = _deref(values, item)
        if isinstance(value, dict) and set(value) == {"constantValue"}:
            value = value["constantValue"]
        if isinstance(value, dict | list):
            return None
        literals.append(value)
    return literals


def strip_indicator_band_rename(encoded: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Splice the port's terminal ``.rename("indicator_15_3_1")`` out of ``encoded``.

    Returns ``(canonical graph, whether the splice fired)``. It fires only for the
    exact shape the port builds -- ``Image.uint8`` over ``Image.where`` over
    ``Image.rename(["indicator_15_3_1"])``, which is ``build_indicator``
    transcribing run_15_3_1.py:411 plus the one deliberate rename -- and returns
    the graph untouched otherwise.

    That narrowness is the whole point. A port whose cast, water mask or rename
    moved does not get normalised; it fails. The legacy goldens carry no such node,
    so the splice declines on them, and ``test_parity.py`` asserts that it does --
    which is what stops this from cancelling a rename on both sides and so
    comparing nothing.

    Only the ONE use is redirected. If ``ee`` had shared the rename node with
    another part of the graph, every other use would keep it and the comparison
    would still see it.
    """
    graph = copy.deepcopy(encoded)
    values = graph.get("values", {})
    decline = (canonical_graph(graph), False)

    cast = _invocation(_deref(values, {"valueReference": graph["result"]}), "Image.uint8")
    if cast is None:
        return decline
    mask = _invocation(_deref(values, cast["arguments"].get("value")), "Image.where")
    if mask is None:
        return decline
    rename = _invocation(_deref(values, mask["arguments"].get("input")), "Image.rename")
    if rename is None:
        return decline
    if _literal_list(values, rename["arguments"].get("names")) != [INDICATOR_BAND]:
        return decline
    collapse = rename["arguments"].get("input")
    if collapse is None:
        return decline

    mask["arguments"]["input"] = collapse
    # canonicalise last: it drops the spliced node rather than leaving it orphaned
    return canonical_graph(graph), True

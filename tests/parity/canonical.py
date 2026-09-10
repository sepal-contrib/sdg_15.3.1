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

THE HAZARD, and the reason :data:`_BARE_SCOPE_KEY` is a table rather than an
``if``: a scope key does not always arrive wrapped. ``ee`` spells a reference FOUR
different ways, and three of them are BARE -- they look like ordinary string
literals to a walker that is not expecting them, so the subtree behind them
silently drops out of the canonical form and any difference inside it becomes
invisible. This file shipped once knowing only two of the four, and the one it
missed (``functionReference``) is where ``ee.Image.expression`` puts the EVI and
MSVI formulas: two graphs differing only in a coefficient canonicalised
identically.

The four are exactly the call sites of ``_optimize_referred_value`` in
``ee/serializer.py``, which is the only thing there that creates a ``values`` key:

* ``:411`` -- the top-level ``result``, a bare key. Resolved in
  :func:`canonical_graph` itself, not through the table, because it has no
  enclosing node.
* ``:497`` -- ``body``, a bare key directly under ``functionDefinitionValue``: a
  ``.map()``/``.reduce()`` callback (also documented in ``tests/engine/graph.py``).
* ``:509`` -- ``functionReference``, a bare key directly inside a
  ``functionInvocationValue``, sitting where ``functionName`` normally sits, when
  the function being called is itself computed rather than named.
* ``:527`` -- ``{"valueReference": key}``, the wrapper form, handled by
  ``resolve()``.

Everything else in the ValueNode union is terminal: ``_optimize_value`` returns
``constantValue``, ``integerValue``, ``bytesValue`` and ``argumentReference``
untouched and recurses into ``arrayValue`` / ``dictionaryValue`` as ValueNodes. So
there is no FIFTH -- for earthengine-api 1.6.14, which
``test_the_recorded_ee_version_matches_this_environment`` is what pins.

The two table entries are resolved only under their own enclosing node kind, and
that anchoring NARROWS the converse hazard rather than removing it. ``body`` is a
perfectly ordinary key for an ``ee.Dictionary`` constant to carry, and resolving
one of those would splice in an unrelated node; the kind check means a bare
``{"body": "..."}`` constant is left alone. What it does not cover is a constant
shaped like the node it sits under --
``{"constantValue": {"functionInvocationValue": {"functionReference": "12"}}}`` --
because the kind consulted is only the child's immediate parent key. Nothing in this port builds such a dictionary, and if one
appeared the lookup raises ``KeyError`` unless the string also happens to name a
live scope key. Named here so the next reader knows the bound of the guarantee.

Also worth stating, because it has broken a walker on this plan: a repeated
CONSTANT is hoisted too, not just a repeated computed subexpression, so an
argument reader that does not resolve references sees a reference where it
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
    "COMPUTED_FUNCTION",
    "INDICATOR_BAND",
    "canonical_graph",
    "function_name_counts",
    "render",
    "strip_indicator_band_rename",
]

INDICATOR_BAND = "indicator_15_3_1"

# enclosing node kind -> the field inside it whose STRING value is a bare key into
# `values` rather than a literal. See the module docstring: these are two of the
# four spellings `ee` gives a reference -- the other two are the `valueReference`
# wrapper, handled by `resolve()`, and the top-level `result`, handled in
# `canonical_graph` itself. Keyed on the enclosing kind so that `body` is only
# resolved under `functionDefinitionValue`: an ee.Dictionary constant may
# legitimately carry a key called `body`, and the docstring states what that
# one-level anchoring does and does not cover.
_BARE_SCOPE_KEY: dict[str, str] = {
    "functionDefinitionValue": "body",
    "functionInvocationValue": "functionReference",
}

# the bucket `function_name_counts` reports a computed (rather than named) call
# under, since such a node carries no `functionName` at all
COMPUTED_FUNCTION = "<functionReference>"

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
    # (id(node), memo kind) -> canonical id. The structural key alone is not enough
    # to memoise on, because computing it walks the subtree: a node the graph
    # shares 30 times -- and the truth-table collapse shares its three operand
    # images exactly that often -- would be re-walked 30 times, and its own shared
    # children 30 times again, which is exponential rather than merely slow. Every
    # node here is reachable from `encoded` for the whole call, so no id can be
    # recycled.
    #
    # The kind rides along ONLY for the two enclosing kinds that change how a
    # string child is read; for every other node it is flattened to None, so an
    # image shared under `input` here and `image1` there still hits the memo once.
    seen: dict[tuple[int, Any], int] = {}

    def memo_kind(kind: Any) -> Any:
        return kind if kind in _BARE_SCOPE_KEY else None

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

    def named_children(node: Any, kind: Any) -> list[tuple[Any, Any]]:
        """``(name, resolved child)`` pairs of a composite, in canonical order.

        ``name`` is the dict key, or the index for a list. ``kind`` is the key this
        node hangs off in its parent, which is what says whether a string child is
        a bare scope key (see :data:`_BARE_SCOPE_KEY`). Sorting the dict keys here
        is what stops the order the JSON happened to load in from reaching the
        traversal -- and with it the ids.
        """
        bare = _BARE_SCOPE_KEY.get(kind)
        if isinstance(node, dict):
            names: list[Any] = sorted(node)
        else:
            names = list(range(len(node)))
        pairs = []
        for name in names:
            child = node[name]
            if name == bare and isinstance(child, str):
                if child not in values:
                    raise KeyError(f"{name} {child!r} has no entry in values")
                child = values[child]
            pairs.append((name, resolve(child)))
        return pairs

    def slot(name: Any, child: Any, kind: Any) -> tuple[Any, Any]:
        """``(what the parent stores, the parent's key part)`` for one child.

        The child is already interned by the time this runs, so this is a lookup.
        A bare scope key keeps its bare spelling and is tagged with its own field
        name, so a resolved reference can never share a key part with a literal or
        with the other reference spelling.
        """
        if isinstance(child, dict | list):
            child_id = seen[id(child), memo_kind(name)]
            if name == _BARE_SCOPE_KEY.get(kind):
                return _tag(child_id), (name, child_id)
            return {"valueReference": _tag(child_id)}, ("ref", child_id)
        return child, ("literal", json.dumps(child, sort_keys=True))

    def rewrite(node: Any, kind: Any) -> tuple[Any, Any]:
        """``(node with its children replaced by ids, hashable structural key)``.

        The key holds child IDS rather than child structures, so it stays small
        however deep the graph runs -- this is hash-consing, not stringification.
        """
        slots = [(name, *slot(name, child, kind)) for name, child in named_children(node, kind)]
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
        pending: list[tuple[Any, Any, bool]] = [(root, None, False)]
        while pending:
            node, kind, expanded = pending.pop()
            if (id(node), memo_kind(kind)) in seen:
                continue
            if not expanded:
                pending.append((node, kind, True))
                # reversed so the first child in canonical order is visited first
                for name, child in reversed(named_children(node, kind)):
                    if isinstance(child, dict | list) and (id(child), memo_kind(name)) not in seen:
                        pending.append((child, name, False))
                continue
            rewritten, key = rewrite(node, kind)
            node_id = ids.get(key)
            if node_id is None:
                node_id = len(definitions)
                ids[key] = node_id
                definitions.append(rewritten)
            seen[id(node), memo_kind(kind)] = node_id
        return seen[id(root), memo_kind(None)]

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

    A call to a COMPUTED function carries a ``functionReference`` where a named one
    carries a ``functionName``, and is counted under :data:`COMPUTED_FUNCTION`.
    Counting it is the point: comparing this against an independent walk of the raw
    document is what would have caught the canonicaliser dropping the
    ``Image.parseExpression`` subtree those references lead to.
    """
    counts: dict[str, int] = {}
    for node in canonical_graph(encoded)["values"].values():
        if not isinstance(node, dict):
            continue
        if "functionName" in node:
            name = node["functionName"]
        elif "functionReference" in node:
            name = COMPUTED_FUNCTION
        else:
            continue
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

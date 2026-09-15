"""Shared render-tree helpers for the app test suite.

Every step's tests need to answer the same two questions: what text did this
render actually show, and which real widget sits where in the tree. Walking
``.children`` by hand here, once, is what lets a test assert on the RENDER
TREE itself rather than on an extracted helper's return value or a
``content`` list's length -- see the step test modules for why that
distinction matters.
"""

from __future__ import annotations

import re

__all__ = ("find_widget", "find_widgets", "markdown_texts")

_MARKDOWN_RE = re.compile(r'<div class="solara-markdown[^"]*"[^>]*>(.*?)</div>', re.DOTALL)


def markdown_texts(node: object) -> list[str]:
    """Every rendered markdown paragraph under ``node``, in tree order.

    Reads the real render tree (each ``solara.Markdown`` becomes a
    ``VuetifyTemplate`` whose ``template`` embeds the rendered HTML), so this
    sees exactly what a user would: not just that the component "did not
    raise", but which text -- the description, a selection, a validation
    problem -- actually appears.
    """
    texts = []
    template = getattr(node, "template", None)
    if isinstance(template, str) and "solara-markdown" in template:
        match = _MARKDOWN_RE.search(template)
        if match:
            texts.append(match.group(1).strip())
    for child in getattr(node, "children", None) or ():
        texts.extend(markdown_texts(child))
    return texts


def find_widget(root: object, cls: type) -> object | None:
    """The first ``cls`` instance in the render tree, walking ``.children``."""
    if isinstance(root, cls):
        return root
    for child in getattr(root, "children", None) or []:
        found = find_widget(child, cls)
        if found is not None:
            return found
    return None


def find_widgets(root: object, cls: type) -> list[object]:
    """Every ``cls`` instance in the render tree, in tree order."""
    found = [root] if isinstance(root, cls) else []
    for child in getattr(root, "children", None) or []:
        found.extend(find_widgets(child, cls))
    return found

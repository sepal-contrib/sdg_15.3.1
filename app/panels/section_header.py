"""A flat section's own header: icon, title, and an optional description.

Reproduces the styling pysepal's ``RightPanel.vue`` applies to a section dict
(``pysepal/sepalwidgets/vue/RightPanel.vue``'s ``.section-header``/
``.section-description`` rules) -- this app no longer passes section dicts
into that component (``app/panels/outputs.py`` builds flat sections instead
of a ``RightPanel`` content list), so the two class names carry no CSS here
and the visual rules are reproduced directly: a bottom border in the
theme's own divider colour (the ``var(--v-divider-base, ...)`` CSS variable,
never a hardcoded grey -- a fixed colour would look right in one theme and
wrong in the other) plus Vuetify's own global typography classes
(``subtitle-2``, ``font-weight-medium``, ``body-2``, ``text--secondary``),
the same approach ``sbae-design``'s own port of this styling
(``component/widget/custom_widgets.py``'s ``Section``) takes, adapted to
this app's ``rv.*``-only convention for a container living inside another
``rv.*`` container (``rv.Html`` divs, not ``solara.Row``/``Column`` -- see
``app/tabs.py``'s identical convention and its own comments on why).
"""

from __future__ import annotations

import reacton.ipyvuetify as rv
import solara

__all__ = ("SectionHeader",)

_HEADER_STYLE = (
    "display: flex; align-items: center; padding: 8px 0; margin-bottom: 12px; "
    "border-bottom: 1px solid var(--v-divider-base, rgba(0, 0, 0, 0.12));"
)
_DESCRIPTION_STYLE = "padding-left: 16px; margin: 8px 0 12px;"


@solara.component
def SectionHeader(title: str, icon: str, description: str | None = None) -> None:
    with rv.Html(tag="div", style_=_HEADER_STYLE):
        rv.Icon(children=[icon], small=True, class_="mr-2")
        rv.Html(tag="span", class_="subtitle-2 font-weight-medium", children=[title])
    if description:
        rv.Html(
            tag="p",
            class_="body-2 text--secondary",
            style_=_DESCRIPTION_STYLE,
            children=[description],
        )

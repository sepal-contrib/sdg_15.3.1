"""A flat section's own header: icon, title, and an optional description.

Reproduces the styling pysepal's ``RightPanel.vue`` applies to a section dict
(``pysepal/sepalwidgets/vue/RightPanel.vue``'s ``.section-header``/
``.section-description`` rules) -- this app no longer passes section dicts
into that component (``app/panels/outputs.py`` builds flat sections instead
of a ``RightPanel`` content list), so the two class names carry no CSS here
and the visual rules are reproduced directly: a bottom border in the
theme's own divider colour plus Vuetify's own global typography classes
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
from pysepal.solara import use_theme_dark

__all__ = ("SectionHeader",)

#: NOT ``var(--v-divider-base, ...)``, which this file used until it was
#: measured. That variable is never defined anywhere in this stack: Vuetify 2
#: compiles its theme from SASS at build time, and ``--v-*`` CSS custom
#: properties are a Vuetify 3 feature -- the shipped solara-vuetify bundle
#: declares none at all. So the fallback ALWAYS won, painting a light-theme
#: divider in dark mode. It survived a browser check because a fallback that
#: always applies looks exactly like a working default: the border WAS there,
#: just permanently the wrong colour. pysepal's own ``RightPanel.vue:209`` and
#: ``sbae-design``'s ``custom_widgets.py`` carry the identical pattern, the
#: latter with a docstring claiming it adapts to the theme; both are reported
#: separately and neither is this app's to fix.
_DIVIDER_LIGHT = "rgba(0, 0, 0, 0.12)"
_DIVIDER_DARK = "rgba(255, 255, 255, 0.12)"
#: The header's own bottom margin depends on what follows it. A description
#: belongs to its title and reads as one block, so the two used to be 20px
#: apart (12 below the rule plus 8 above the text) for no reason; content
#: with no description in between still wants the full gap.
_HEADER_STYLE = (
    "display: flex; align-items: center; padding: 8px 0; margin-bottom: {gap}px; "
    "border-bottom: 1px solid {divider};"
)
_GAP_BEFORE_DESCRIPTION = 6
_GAP_BEFORE_CONTENT = 12
_DESCRIPTION_STYLE = "padding-left: 16px; margin: 0 0 12px;"


@solara.component
def SectionHeader(title: str, icon: str, description: str | None = None) -> None:
    # `use_theme_dark()`, not `solara.lab.use_dark_effective()`: the latter
    # reads a process-wide default disconnected from this app's own toggle
    # (see `app/tabs.py`'s comment on the same trap).
    divider = _DIVIDER_DARK if use_theme_dark() else _DIVIDER_LIGHT
    gap = _GAP_BEFORE_DESCRIPTION if description else _GAP_BEFORE_CONTENT
    with rv.Html(tag="div", style_=_HEADER_STYLE.format(divider=divider, gap=gap)):
        rv.Icon(children=[icon], small=True, class_="mr-2")
        rv.Html(tag="span", class_="subtitle-2 font-weight-medium", children=[title])
    if description:
        rv.Html(
            tag="p",
            class_="body-2 text--secondary",
            style_=_DESCRIPTION_STYLE,
            children=[description],
        )

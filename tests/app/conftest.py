"""Keep this suite out of an environment without pysepal 4.

``pysepal.i18n`` (and the rest of the 4.0 surface the app package needs) only
exists under ``pysepal>=4``. Without this guard, collecting this directory in an
environment built from ``sepal_environment.yml``'s ``pysepal<4`` pin would abort
the whole domain-suite run with an import error rather than simply having
nothing to run.

The skip is SILENT, which is what let CI drop all 158 of these tests unnoticed
for the whole of the app layer's development: the domain job counts its
selection and still sees ~1057, so an empty ``tests/app`` never moves the
number it checks. Any job that exists to run THIS directory must therefore set
``SDG_REQUIRE_APP_TESTS=1``, which turns the skip into a collection error
naming the cause.
"""

from __future__ import annotations

import importlib.util
import os

_HAVE_PYSEPAL_4 = importlib.util.find_spec("pysepal.i18n") is not None

if not _HAVE_PYSEPAL_4 and os.environ.get("SDG_REQUIRE_APP_TESTS") == "1":
    raise RuntimeError(
        "SDG_REQUIRE_APP_TESTS=1 but pysepal.i18n is missing: this environment has "
        "pysepal<4, so every module under app/ is unimportable and this suite would "
        "silently collect nothing. Install the 'app' extra (pip install -e '.[app,dev]')."
    )

collect_ignore_glob = [] if _HAVE_PYSEPAL_4 else ["*"]

"""Keep this suite out of ``sdg_pysepal``, which still runs pysepal 3.8.3.

``pysepal.i18n`` (and the rest of the 4.0 surface the app package needs) only
exists in ``sdg_app``'s editable install. Without this guard, collecting this
directory under ``sdg_pysepal`` would abort the whole domain-suite run with an
import error rather than simply having nothing to run.
"""

from __future__ import annotations

import importlib.util

collect_ignore_glob = ["*"] if importlib.util.find_spec("pysepal.i18n") is None else []

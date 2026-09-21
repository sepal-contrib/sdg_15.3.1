"""The container's deployment settings, held to each other.

Four files repeat two values between them, and nothing makes them agree:
``supervisord.conf`` serves the app at a ``--root-path`` on a port,
``Dockerfile`` exposes that port, ``docker-compose.yml`` health-checks it, and
``notify-catalog.yml`` tells the catalogue which app id to bump. The catalogue
in turn requires an entry's ``path`` to equal ``/api/app-launcher/<id>``.

So the id appears in two files and the port in three, and every mismatch fails
the same way: silently, in production, behind a proxy that routes on the path
the catalogue published. A disagreement is not visible from any one file, which
is why it is measured here rather than remembered.
"""

from __future__ import annotations

import re

import yaml
from conftest import REPO_ROOT

SUPERVISORD = (REPO_ROOT / "supervisord.conf").read_text(encoding="utf-8")


def _supervisord_values(flag: str) -> set[str]:
    """Every value ``flag`` is given across supervisord's program commands."""
    return set(re.findall(rf"{re.escape(flag)}=(\S+?)(?=\s|\")", SUPERVISORD))


def test_the_app_is_served_under_its_catalog_id() -> None:
    """The proxy routes on the path the catalogue published, so a ``--root-path``
    that disagrees with ``APP_ID`` serves the app at an address nothing links to."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/notify-catalog.yml").read_text(encoding="utf-8")
    )
    app_id = workflow["env"]["APP_ID"]
    expected = f"/api/app-launcher/{app_id}"

    served = _supervisord_values("--root-path")
    assert served == {expected}, (
        f"APP_ID is {app_id!r}, so --root-path must be {expected!r}: {served}"
    )


def test_every_file_agrees_on_the_port() -> None:
    ports = _supervisord_values("--port")
    assert len(ports) == 1, f"supervisord serves more than one port: {ports}"
    port = int(ports.pop())

    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    exposed = re.findall(r"^EXPOSE\s+(\d+)", dockerfile, re.MULTILINE)
    assert exposed == [str(port)], f"Dockerfile exposes {exposed}, supervisord serves {port}"

    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = next(iter(compose["services"].values()))
    assert str(port) in service["healthcheck"]["test"], (
        f"the healthcheck does not probe {port}: {service['healthcheck']['test']}"
    )

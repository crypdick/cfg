"""Pyinfra deploy entrypoint for upgrading installed system packages."""

from __future__ import annotations

from cfg.host.deploys.pkg import pkg_update, pkg_upgrade

pkg_update()
pkg_upgrade()

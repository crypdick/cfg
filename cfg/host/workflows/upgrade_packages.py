"""Pyinfra deploy entrypoint for upgrading installed system packages."""

from __future__ import annotations

from cfg.host.deploys.feature_deploys import prepare_features
from cfg.host.deploys.pkg import pkg_update, pkg_upgrade

prepare_features()
pkg_update()
pkg_upgrade()

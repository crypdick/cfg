"""Pyinfra deploy entrypoint for applying owner-contributed home files to the host."""

from __future__ import annotations

from cfg.host.deploys.home import deploy_apply_home

deploy_apply_home()

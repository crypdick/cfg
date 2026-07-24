from __future__ import annotations

from cfg.core.host_id import find_cfg_host


def current_host() -> list[str]:
    """Business logic for `cfg host current` (returns lines to print)."""
    host = find_cfg_host()
    if host:
        return [host]
    return ["(unset)", "hint: register this machine as a host with `cfg host init <host>`"]

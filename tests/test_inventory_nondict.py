from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.core.inventory import load_inventory

if TYPE_CHECKING:
    from pathlib import Path


def test_inventory_rejects_non_table_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_root = tmp_path
    (cfg_root / ".cfg-root").write_text("", encoding="utf-8")

    p = cfg_root / "hosts" / "h1" / "cfg.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('name="h1"\n', encoding="utf-8")

    import cfg.core.inventory as inv

    monkeypatch.setattr(inv.tomllib, "loads", lambda _raw: ["not-a-table"])

    with pytest.raises(CfgError, match="expected a table"):
        load_inventory(cfg_root)

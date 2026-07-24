from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from cfg.core.errors import CfgError
from cfg.deploys import host_data

if TYPE_CHECKING:
    from pathlib import Path


def test_host_data_parses_root_and_owner_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        host_data,
        "host",
        SimpleNamespace(
            data={
                host_data.CFG_ROOT: str(tmp_path),
                host_data.CFG_HOST_OWNER_IDS: [
                    "host/feature/base",
                    "host/laptop",
                ],
            }
        ),
    )

    assert host_data.cfg_root_from_host_data() == tmp_path.resolve()
    assert host_data.owner_ids_from_host_data() == [
        "host/feature/base",
        "host/laptop",
    ]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "Missing host.data"),
        ("not-a-list", r"must be a list\[str\]"),
        (["not-an-owner"], "Invalid host owner id"),
    ],
)
def test_owner_ids_from_host_data_rejects_unparsed_values(
    value: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        host_data,
        "host",
        SimpleNamespace(data={host_data.CFG_HOST_OWNER_IDS: value}),
    )

    with pytest.raises(CfgError, match=message):
        host_data.owner_ids_from_host_data()

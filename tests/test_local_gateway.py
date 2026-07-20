import argparse
import json
from pathlib import Path

import pytest

from src.service import local_gateway


def test_local_gateway_rejects_non_loopback_host(monkeypatch):
    monkeypatch.setattr(
        local_gateway,
        "parse_args",
        lambda: argparse.Namespace(
            host="0.0.0.0",
            port=8766,
            central_url="http://127.0.0.1:8765",
            no_open=True,
        ),
    )

    with pytest.raises(SystemExit, match="must bind to 127.0.0.1"):
        local_gateway.main()


def test_packaged_client_prefers_config_next_to_executable(monkeypatch, tmp_path):
    executable_dir = tmp_path / "release"
    working_dir = tmp_path / "developer-working-directory"
    executable_dir.mkdir()
    working_dir.mkdir()
    executable = executable_dir / "DrawFlowClient.exe"
    executable.write_bytes(b"")
    (executable_dir / "drawflow-client.json").write_text(
        json.dumps({"central_url": "http://central.example:8765"}),
        encoding="utf-8",
    )
    (working_dir / "drawflow-client.json").write_text(
        json.dumps({"central_url": "http://127.0.0.1:9999"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("DRAWFLOW_CENTRAL_URL", raising=False)
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(local_gateway.sys, "frozen", True, raising=False)
    monkeypatch.setattr(local_gateway.sys, "executable", str(executable))

    assert local_gateway.default_central_url() == "http://central.example:8765"
    assert local_gateway._client_config_candidates()[0] == Path(executable_dir / "drawflow-client.json")

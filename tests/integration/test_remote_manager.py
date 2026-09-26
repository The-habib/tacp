"""Integration tests for RemoteManager and remote CLI workflows."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tacp.cli.main import main
from tacp.infrastructure.config import TacpConfig
from tacp.remote.manager import RemoteManager


def test_remote_manager_lifecycle(test_config: TacpConfig) -> None:
    manager = RemoteManager(config=test_config)

    # Initial state should be inactive
    initial_status = manager.get_status()
    assert initial_status["active"] is False
    assert initial_status["device_id"]
    assert initial_status["device_name"]

    # Enable remote in direct mode (uses ephemeral local port)
    res = manager.enable_remote(
        provider="direct",
        port=19876,
        custom_domain="android-termux.local",
        auth_required=True,
    )

    assert res["status"] == "active"
    assert res["provider"] == "direct"
    assert "android-termux.local:19876/mcp" in res["endpoint"]
    assert res["device_id"]
    assert res["new_token"].startswith("tacp_sec_")

    # Status should now reflect active state
    active_status = manager.get_status()
    assert active_status["active"] is True
    assert active_status["provider"] == "direct"
    assert active_status["mcp_endpoint"] == res["endpoint"]

    # Disable remote
    disabled = manager.disable_remote()
    assert disabled is True

    # Status should now reflect disabled
    post_status = manager.get_status()
    assert post_status["active"] is False
    assert "Disabled" in post_status["status_message"]


def test_remote_manager_pairing(test_config: TacpConfig) -> None:
    manager = RemoteManager(config=test_config)

    pair_res = manager.generate_pairing(ttl_minutes=5)
    code = pair_res["pairing_code"]
    assert len(code) == 9
    assert code[4] == "-"

    paired = manager.verify_pairing(code, principal_id="remote_agent_test")
    assert paired is not None
    assert paired["paired_principal"] == "remote_agent_test"


def test_cli_remote_status_and_pair(
    temp_tacp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(temp_tacp_dir)}):
        main(["doctor"])
        capsys.readouterr()

        # tacp remote status
        code_st = main(["remote", "status"])
        assert code_st == 0
        cap_st = capsys.readouterr()
        assert "TACP Remote Integration Status" in cap_st.out
        assert "Device ID" in cap_st.out

        # tacp remote pair
        code_pair = main(["remote", "pair", "--ttl", "5"])
        assert code_pair == 0
        cap_pair = capsys.readouterr()
        assert "Pairing Code" in cap_pair.out
        assert "minutes" in cap_pair.out
        assert "TZVH-" in cap_pair.out or "-" in cap_pair.out

        # tacp remote disable
        code_dis = main(["remote", "disable"])
        assert code_dis == 0
        cap_dis = capsys.readouterr()
        assert "disabled" in cap_dis.out

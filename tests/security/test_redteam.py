"""Comprehensive Security Red Team Suite for TACP Phase 3."""

import pytest

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.control.auth import TokenService
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


@pytest.fixture
def redteam_env(tmp_path):
    db_path = tmp_path / "redteam.db"
    db = Database(db_path)
    db.connect()
    config = TacpConfig.load()
    server = create_mcp_server(config, db)
    token_svc = TokenService(db)
    token_rec, raw_token = token_svc.create_token(name="redteam_token", scopes=["tacp.read"])
    return {
        "server": server,
        "db": db,
        "token_svc": token_svc,
        "raw_token": raw_token,
        "token_rec": token_rec,
        "tmp_path": tmp_path,
    }


def test_redteam_path_traversal_jail(redteam_env):
    server = redteam_env["server"]
    traversal_attacks = [
        "../../../etc/passwd",
        r"..\..\..\windows\win.ini",
        "/data/data/com.termux/files/usr/bin/sh",
        "....//....//etc/shadow",
        "..%2f..%2f..%2fetc%2fpasswd",
        "/proc/1/environ",
    ]
    for attack in traversal_attacks:
        req = McpRequest(
            id="trav_test",
            method="tools/call",
            params={
                "name": "fs.read",
                "arguments": {"path": attack, "workspace_id": "termux-home"},
            },
        )
        resp = server.handle_request(req)
        assert resp is not None
        assert resp.result.get("isError") is True or "Error" in resp.result["content"][0]["text"]


def test_redteam_null_byte_injection(redteam_env):
    server = redteam_env["server"]
    req = McpRequest(
        id="null_byte",
        method="tools/call",
        params={
            "name": "fs.read",
            "arguments": {"path": "valid.txt" + chr(0) + "/../../etc/passwd"},
        },
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.result.get("isError") is True or "Error" in resp.result["content"][0]["text"]


def test_redteam_token_validation(redteam_env):
    token_svc = redteam_env["token_svc"]
    raw_token = redteam_env["raw_token"]
    token_rec = redteam_env["token_rec"]

    # Valid token passes
    assert token_svc.validate_token(raw_token) is not None

    # Revoked token fails
    token_svc.revoke_token(token_rec.id)
    assert token_svc.validate_token(raw_token) is None

    # Forged tokens fail
    assert token_svc.validate_token("tacp_sec_forged_random_gibberish_1234567890") is None
    assert token_svc.validate_token("") is None
    assert token_svc.validate_token("Bearer ") is None
    assert token_svc.validate_token("' OR '1'='1") is None


def test_redteam_command_injection_safeguards(redteam_env):
    server = redteam_env["server"]
    injection_payloads = [
        "; rm -rf / ;",
        chr(96) + "id" + chr(96),
        "",
        "| cat /etc/passwd",
        "&& echo pwned",
    ]
    for payload in injection_payloads:
        req = McpRequest(
            id="inj_test",
            method="tools/call",
            params={"name": "execution.request", "arguments": {"command": payload}},
        )
        resp = server.handle_request(req)
        assert resp is not None
        assert resp.result.get("isError") is True or "Error" in resp.result["content"][0]["text"]

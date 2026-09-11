"""Tests for Secret Redaction and Classification (Category H)."""

from pathlib import Path

from tacp.domain.classification import DataClassification
from tacp.infrastructure.logging import redact_dict, redact_string
from tacp.providers.filesystem import FilesystemProvider


def test_redact_bearer_token() -> None:
    text = "Authorization: Bearer ya29.a0AfH6SMB_secret_token_here_12345"
    redacted = redact_string(text)
    assert "ya29" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_github_pat() -> None:
    text = "my token is " + "gh" + "p_AbCdEf1234567890AbCdEf1234567890XyZa"
    redacted = redact_string(text)
    assert "ghp_" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_anthropic_api_key() -> None:
    text = "Key: " + "sk" + "-ant-api03-abcdef1234567890abcdef1234567890"
    redacted = redact_string(text)
    assert "sk-ant-" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_openai_api_key() -> None:
    text = "sk" + "-abcdef1234567890abcdef1234567890abcdef12"
    redacted = redact_string(text)
    assert "sk-" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_private_key_header() -> None:
    text = (
        "-----" + "BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAA\n"
        "-----" + "END OPENSSH PRIVATE KEY-----"
    )
    redacted = redact_string(text)
    assert "OPENSSH PRIVATE KEY" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_dict_preserves_non_secret_fields() -> None:
    data = {
        "user": "alice",
        "action": "read",
        "count": 42,
    }
    cleaned = redact_dict(data)
    assert cleaned["user"] == "alice"
    assert cleaned["action"] == "read"
    assert cleaned["count"] == 42


def test_redact_dict_masks_sensitive_keys() -> None:
    data = {
        "password": "super_secret_password_123",
        "token": "secret_token_abc",
        "api_key": "xyz12345",
        "public_field": "visible",
    }
    cleaned = redact_dict(data)
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["token"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["public_field"] == "visible"


def test_classify_path_ssh_keys() -> None:
    provider = FilesystemProvider()
    assert provider._classify_path(Path("id_rsa")) == DataClassification.SECRET
    assert provider._classify_path(Path("id_ed25519")) == DataClassification.SECRET
    assert provider._classify_path(Path("key.pem")) == DataClassification.SECRET


def test_classify_path_env_files() -> None:
    provider = FilesystemProvider()
    assert provider._classify_path(Path(".env")) == DataClassification.SECRET
    assert provider._classify_path(Path(".env.local")) == DataClassification.SECRET


def test_classify_path_public_files() -> None:
    provider = FilesystemProvider()
    assert provider._classify_path(Path("README.md")) == DataClassification.PUBLIC
    assert provider._classify_path(Path("main.py")) == DataClassification.PUBLIC
    assert provider._classify_path(Path("style.css")) == DataClassification.PUBLIC


def test_classify_path_git_directory() -> None:
    provider = FilesystemProvider()
    assert provider._classify_path(Path(".git/config")) == DataClassification.INTERNAL

"""Unit tests for DeviceIdentity and PairingService."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tacp.control.pairing import (
    PairingService,
    get_or_create_device_identity,
)
from tacp.infrastructure.database import Database


def test_get_or_create_device_identity(tmp_path: Path) -> None:
    data_dir = tmp_path / "tacp_data"
    identity1 = get_or_create_device_identity(data_dir)

    assert identity1.device_id.startswith("dev_")
    assert len(identity1.device_secret) >= 32
    assert identity1.device_name

    # Second call should load existing identity
    identity2 = get_or_create_device_identity(data_dir)
    assert identity1.device_id == identity2.device_id
    assert identity1.device_secret == identity2.device_secret
    assert identity1.created_at == identity2.created_at


def test_generate_pairing_code(test_db: Database) -> None:
    service = PairingService(test_db)
    res = service.generate_pairing_code(
        device_id="dev_12345",
        device_name="Test Phone",
        ttl_minutes=5,
    )

    code = res["pairing_code"]
    assert len(code) == 9
    assert code[4] == "-"
    assert res["device_id"] == "dev_12345"
    assert res["device_name"] == "Test Phone"
    assert res["ttl_seconds"] == 300


def test_verify_pairing_success(test_db: Database) -> None:
    service = PairingService(test_db)
    res = service.generate_pairing_code(
        device_id="dev_987",
        device_name="Pixel 9 Pro",
        ttl_minutes=15,
    )
    code = res["pairing_code"]

    paired = service.verify_pairing(code, principal_id="remote_agent_42")
    assert paired is not None
    assert paired["device_id"] == "dev_987"
    assert paired["device_name"] == "Pixel 9 Pro"
    assert paired["paired_principal"] == "remote_agent_42"

    # Subsequent verification must fail because code is already consumed
    re_paired = service.verify_pairing(code, principal_id="another_agent")
    assert re_paired is None


def test_verify_pairing_expired(test_db: Database) -> None:
    service = PairingService(test_db)
    res = service.generate_pairing_code(
        device_id="dev_old",
        device_name="Old Phone",
        ttl_minutes=10,
    )
    code = res["pairing_code"]

    # Artificially expire the code in database
    past = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE device_pairing SET expires_at = ? WHERE pairing_code = ?", (past, code))
    conn.commit()

    paired = service.verify_pairing(code, principal_id="remote_agent")
    assert paired is None

    # Verify status changed to EXPIRED
    cursor.execute("SELECT status FROM device_pairing WHERE pairing_code = ?", (code,))
    row = cursor.fetchone()
    assert row["status"] == "EXPIRED"


def test_verify_invalid_code(test_db: Database) -> None:
    service = PairingService(test_db)
    assert service.verify_pairing("XXXX-YYYY", principal_id="agent") is None
    assert service.verify_pairing("", principal_id="agent") is None

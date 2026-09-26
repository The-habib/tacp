"""Device Identity and Pairing Management for TACP."""

from __future__ import annotations

import json
import os
import secrets
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tacp.infrastructure.database import Database

PAIRING_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # omit 0, 1, I, O


@dataclass(frozen=True)
class DeviceIdentity:
    """Persistent cryptographic identity of the Android device."""

    device_id: str
    device_name: str
    device_secret: str
    created_at: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_secret": self.device_secret,
            "created_at": self.created_at,
        }


def get_default_device_name() -> str:
    """Determine a sensible default device name for Termux/Android."""
    model = os.environ.get("DEVICE_NAME") or os.environ.get("ANDROID_MODEL")
    if model:
        return model
    try:
        hostname = socket.gethostname()
        if hostname and hostname != "localhost":
            return f"Android-{hostname}"
    except Exception:
        pass
    return "Android-Device"


def get_or_create_device_identity(data_dir: Path) -> DeviceIdentity:
    """Retrieve or initialize the persistent device identity on disk."""
    device_file = data_dir / "device.json"
    if device_file.exists():
        try:
            with open(device_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DeviceIdentity(
                device_id=data["device_id"],
                device_name=data.get("device_name", get_default_device_name()),
                device_secret=data["device_secret"],
                created_at=data["created_at"],
            )
        except Exception:
            pass

    # Generate fresh identity
    data_dir.mkdir(parents=True, exist_ok=True)
    dev_id = f"dev_{uuid.uuid4().hex[:12]}"
    secret = secrets.token_hex(32)
    name = get_default_device_name()
    now_str = datetime.now(timezone.utc).isoformat()

    identity = DeviceIdentity(
        device_id=dev_id,
        device_name=name,
        device_secret=secret,
        created_at=now_str,
    )

    with open(device_file, "w", encoding="utf-8") as f:
        json.dump(identity.to_dict(), f, indent=2)
    try:
        os.chmod(device_file, 0o600)
    except Exception:
        pass

    return identity


class PairingService:
    """Manages secure short-lived pairing codes between device and gateway/client."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def generate_pairing_code(
        self,
        device_id: str,
        device_name: str,
        ttl_minutes: int = 10,
    ) -> Dict[str, Any]:
        """Generate a random pairing code (XXXX-XXXX) valid for ttl_minutes."""
        part1 = "".join(secrets.choice(PAIRING_CODE_CHARS) for _ in range(4))
        part2 = "".join(secrets.choice(PAIRING_CODE_CHARS) for _ in range(4))
        code = f"{part1}-{part2}"

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)
        pairing_id = f"pair_{uuid.uuid4().hex[:12]}"

        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO device_pairing (
                id, device_id, device_name, pairing_code, status,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, 'PENDING', ?, ?);
            """,
            (
                pairing_id,
                device_id,
                device_name,
                code,
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        conn.commit()

        return {
            "pairing_id": pairing_id,
            "device_id": device_id,
            "device_name": device_name,
            "pairing_code": code,
            "expires_at": expires.isoformat(),
            "ttl_seconds": ttl_minutes * 60,
        }

    def verify_pairing(self, code: str, principal_id: str) -> Optional[Dict[str, Any]]:
        """Verify and consume a pairing code."""
        clean_code = code.strip().upper()
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, device_id, device_name, status, created_at, expires_at
            FROM device_pairing
            WHERE pairing_code = ? AND status = 'PENDING';
            """,
            (clean_code,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > exp:
            cursor.execute(
                "UPDATE device_pairing SET status = 'EXPIRED' WHERE id = ?;", (row["id"],)
            )
            conn.commit()
            return None

        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE device_pairing
            SET status = 'PAIRED', paired_at = ?, paired_principal = ?
            WHERE id = ?;
            """,
            (now_str, principal_id, row["id"]),
        )
        conn.commit()

        return {
            "device_id": row["device_id"],
            "device_name": row["device_name"],
            "paired_at": now_str,
            "paired_principal": principal_id,
        }

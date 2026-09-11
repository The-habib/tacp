import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpNotFoundError,
    TacpSecurityError,
)
from tacp.infrastructure.database import Database


def compute_canonical_batch_hash(patches: List[Dict[str, Any]]) -> str:
    """Compute deterministic canonical SHA-256 hash for a batch of patches."""
    sorted_patches = sorted(
        [
            {
                "subpath": p["subpath"].replace("\\", "/").strip().lstrip("./"),
                "base_checksum": p["base_checksum"].lower().strip(),
                "patch_content": p["patch_content"].replace("\r\n", "\n"),
            }
            for p in patches
        ],
        key=lambda x: x["subpath"],
    )
    payload = json.dumps(sorted_patches, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_DENIED = "DENIED"
STATUS_CONSUMED = "CONSUMED"
STATUS_EXPIRED = "EXPIRED"
STATUS_REVOKED = "REVOKED"


@dataclass(frozen=True)
class ApprovalTicket:
    id: str
    token: str
    action_type: str
    workspace_id: str
    target_path: str
    patch_hash: str
    principal_id: str
    status: str
    created_at: str
    expires_at: str
    consumed_at: Optional[str] = None
    consumed_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ApprovalEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_ticket(
        self,
        principal_id: str,
        action_type: str,
        workspace_id: str,
        target_path: str,
        patch_hash: str,
        ttl_seconds: int = 900,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalTicket:
        ticket_id = f"appr-{uuid.uuid4().hex[:8]}"
        token = f"tacp_appr_{secrets.token_hex(16)}"
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        meta = metadata or {}

        # Normalize target_path
        clean_target = target_path.strip().lstrip("./")

        conn = self.db.connect()
        conn.execute(
            """
            INSERT INTO approvals (
                id, token, action_type, workspace_id, target_path,
                patch_hash, principal_id, status, created_at, expires_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ticket_id,
                token,
                action_type,
                workspace_id,
                clean_target,
                patch_hash,
                principal_id,
                STATUS_PENDING,
                created_at,
                expires_at,
                json.dumps(meta),
            ),
        )
        conn.commit()

        return ApprovalTicket(
            id=ticket_id,
            token=token,
            action_type=action_type,
            workspace_id=workspace_id,
            target_path=clean_target,
            patch_hash=patch_hash,
            principal_id=principal_id,
            status=STATUS_PENDING,
            created_at=created_at,
            expires_at=expires_at,
            metadata=meta,
        )

    def get_ticket(self, token: str) -> Optional[ApprovalTicket]:
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token, action_type, workspace_id, target_path,
                   patch_hash, principal_id, status, created_at, expires_at,
                   consumed_at, consumed_by, metadata_json
            FROM approvals WHERE token = ?;
            """,
            (token,),
        )
        row = cur.fetchone()
        if not row:
            return None

        return ApprovalTicket(
            id=row[0],
            token=row[1],
            action_type=row[2],
            workspace_id=row[3],
            target_path=row[4],
            patch_hash=row[5],
            principal_id=row[6],
            status=row[7],
            created_at=row[8],
            expires_at=row[9],
            consumed_at=row[10],
            consumed_by=row[11],
            metadata=json.loads(row[12]) if row[12] else {},
        )

    def approve(self, token: str, approved_by: str = "human_operator") -> ApprovalTicket:
        ticket = self.get_ticket(token)
        if not ticket:
            raise TacpNotFoundError(f"Approval ticket token '{token}' not found")

        if ticket.status != STATUS_PENDING:
            raise TacpSecurityError(
                ErrorCode.POLICY_DENIED,
                f"Cannot approve ticket in state '{ticket.status}'",
            )

        now = datetime.now(timezone.utc)
        if now > datetime.fromisoformat(ticket.expires_at):
            conn = self.db.connect()
            conn.execute(
                "UPDATE approvals SET status = ? WHERE token = ?;",
                (STATUS_EXPIRED, token),
            )
            conn.commit()
            raise TacpSecurityError(
                ErrorCode.APPROVAL_EXPIRED,
                f"Approval ticket '{token}' has expired",
            )

        meta = dict(ticket.metadata)
        meta["approved_by"] = approved_by
        meta["approved_at"] = now.isoformat()

        conn = self.db.connect()
        conn.execute(
            """
            UPDATE approvals
            SET status = ?, metadata_json = ?
            WHERE token = ?;
            """,
            (STATUS_APPROVED, json.dumps(meta), token),
        )
        conn.commit()

        updated = self.get_ticket(token)
        assert updated is not None
        return updated

    def deny(
        self, token: str, denied_by: str = "human_operator", reason: str = ""
    ) -> ApprovalTicket:
        ticket = self.get_ticket(token)
        if not ticket:
            raise TacpNotFoundError(f"Approval ticket token '{token}' not found")

        meta = dict(ticket.metadata)
        meta["denied_by"] = denied_by
        meta["denied_at"] = datetime.now(timezone.utc).isoformat()
        meta["deny_reason"] = reason

        conn = self.db.connect()
        conn.execute(
            """
            UPDATE approvals
            SET status = ?, metadata_json = ?
            WHERE token = ?;
            """,
            (STATUS_DENIED, json.dumps(meta), token),
        )
        conn.commit()

        updated = self.get_ticket(token)
        assert updated is not None
        return updated

    def revoke(
        self, token: str, revoked_by: str = "human_operator", reason: str = ""
    ) -> ApprovalTicket:
        ticket = self.get_ticket(token)
        if not ticket:
            raise TacpNotFoundError(f"Approval ticket token '{token}' not found")

        meta = dict(ticket.metadata)
        meta["revoked_by"] = revoked_by
        meta["revoked_at"] = datetime.now(timezone.utc).isoformat()
        meta["revoke_reason"] = reason

        conn = self.db.connect()
        conn.execute(
            """
            UPDATE approvals
            SET status = ?, metadata_json = ?
            WHERE token = ?;
            """,
            (STATUS_REVOKED, json.dumps(meta), token),
        )
        conn.commit()

        updated = self.get_ticket(token)
        assert updated is not None
        return updated

    def verify_and_consume(
        self,
        token: str,
        principal_id: str,
        action_type: str,
        workspace_id: str,
        target_path: str,
        patch_hash: str,
        base_checksum: Optional[str] = None,
    ) -> bool:
        ticket = self.get_ticket(token)
        if not ticket:
            raise TacpSecurityError(
                ErrorCode.APPROVAL_REQUIRED,
                f"Approval ticket '{token}' not found",
            )

        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(ticket.expires_at)
        if now > expires_at:
            conn = self.db.connect()
            conn.execute(
                "UPDATE approvals SET status = ? WHERE token = ?;",
                (STATUS_EXPIRED, token),
            )
            conn.commit()
            raise TacpSecurityError(
                ErrorCode.APPROVAL_EXPIRED,
                f"Approval ticket '{token}' expired at {ticket.expires_at}",
            )

        if ticket.status == STATUS_CONSUMED:
            raise TacpSecurityError(
                ErrorCode.APPROVAL_ALREADY_USED,
                f"Approval ticket '{token}' has already been consumed",
            )

        if ticket.status != STATUS_APPROVED:
            raise TacpApprovalRequiredError(
                f"Approval ticket '{token}' is in state '{ticket.status}', not APPROVED"
            )

        # 5-dimensional scope checks
        if ticket.action_type != action_type:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Approval action mismatch: expected '{ticket.action_type}', got '{action_type}'",
            )

        if ticket.workspace_id != workspace_id:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Approval workspace mismatch: expected '{ticket.workspace_id}', "
                f"got '{workspace_id}'",
            )

        clean_target = target_path.strip().lstrip("./")
        if ticket.target_path != clean_target and not (
            ticket.action_type == "workspace.patch_batch" and ticket.target_path == "*"
        ):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Approval target path mismatch: expected '{ticket.target_path}', "
                f"got '{clean_target}'",
            )

        if ticket.patch_hash != patch_hash:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                "Approval patch hash mismatch: diff content does not match approved hash",
            )

        if ticket.principal_id not in (principal_id, "human", "all"):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Approval principal mismatch: expected '{ticket.principal_id}', "
                f"got '{principal_id}'",
            )

        approved_base = ticket.metadata.get("base_checksum")
        if (
            approved_base
            and base_checksum
            and approved_base.lower().strip() != base_checksum.lower().strip()
        ):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Approval base checksum mismatch: expected '{approved_base}', "
                f"got '{base_checksum}'",
            )

        # Atomic single-use consumption
        consumed_at = now.isoformat()
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE approvals
            SET status = ?, consumed_at = ?, consumed_by = ?
            WHERE token = ? AND status = ?;
            """,
            (STATUS_CONSUMED, consumed_at, principal_id, token, STATUS_APPROVED),
        )
        conn.commit()
        rows_updated = cur.rowcount

        if rows_updated != 1:
            raise TacpSecurityError(
                ErrorCode.APPROVAL_ALREADY_USED,
                f"Approval ticket '{token}' was concurrently consumed or modified",
            )

        return True

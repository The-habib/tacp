import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from tacp.control.identity import Principal, PrincipalType, TrustTier
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
    token_hash: Optional[str] = None


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
        raw_token = f"tacp_appr_{secrets.token_hex(16)}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        meta = metadata or {}

        # Normalize target_path
        clean_target = target_path.strip().lstrip("./")

        # In SQLite, store token_hash in token_hash column, and masked prefix in token column
        # Raw bearer token is NEVER persisted in plaintext to the database.
        masked_token = f"tacp_appr_hash:{token_hash[:16]}"

        conn = self.db.connect()
        with conn:
            conn.execute(
                """
                INSERT INTO approvals (
                    id, token, token_hash, action_type, workspace_id, target_path,
                    patch_hash, principal_id, status, created_at, expires_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ticket_id,
                    masked_token,
                    token_hash,
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

        return ApprovalTicket(
            id=ticket_id,
            token=raw_token,
            action_type=action_type,
            workspace_id=workspace_id,
            target_path=clean_target,
            patch_hash=patch_hash,
            principal_id=principal_id,
            status=STATUS_PENDING,
            created_at=created_at,
            expires_at=expires_at,
            metadata=meta,
            token_hash=token_hash,
        )

    def get_ticket(self, token: str) -> Optional[ApprovalTicket]:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token, action_type, workspace_id, target_path,
                   patch_hash, principal_id, status, created_at, expires_at,
                   consumed_at, consumed_by, metadata_json, token_hash
            FROM approvals
            WHERE token_hash = ? OR token = ?;
            """,
            (token_hash, token),
        )
        row = cur.fetchone()
        if not row:
            return None

        return ApprovalTicket(
            id=row[0],
            token=token,
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
            token_hash=row[13] or token_hash,
        )

    def get_ticket_by_id(self, ticket_id: str) -> Optional[ApprovalTicket]:
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, token, action_type, workspace_id, target_path,
                   patch_hash, principal_id, status, created_at, expires_at,
                   consumed_at, consumed_by, metadata_json, token_hash
            FROM approvals
            WHERE id = ?;
            """,
            (ticket_id,),
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
            token_hash=row[13],
        )

    def approve(
        self,
        token: str,
        approved_by: str = "human_operator",
        approver_principal: Optional[Principal] = None,
    ) -> ApprovalTicket:
        ticket = self.get_ticket(token)
        if not ticket:
            raise TacpNotFoundError(f"Approval ticket token '{token}' not found")

        if ticket.status != STATUS_PENDING:
            raise TacpSecurityError(
                ErrorCode.POLICY_DENIED,
                f"Cannot approve ticket in state '{ticket.status}'",
            )

        # Invariant: Verify approver authority
        if approver_principal is not None:
            if (
                approver_principal.principal_type == PrincipalType.AGENT
                or approver_principal.trust_tier == TrustTier.RESTRICTED
            ):
                raise TacpSecurityError(
                    ErrorCode.NOT_AUTHORIZED,
                    f"Principal '{approver_principal.id}' cannot approve tickets: "
                    f"insufficient authority (trust tier: {approver_principal.trust_tier.value})",
                )
            approved_by = approver_principal.id

        now = datetime.now(timezone.utc)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if now > datetime.fromisoformat(ticket.expires_at):
            conn = self.db.connect()
            with conn:
                conn.execute(
                    "UPDATE approvals SET status = ? WHERE token_hash = ? OR token = ?;",
                    (STATUS_EXPIRED, token_hash, token),
                )
            raise TacpSecurityError(
                ErrorCode.APPROVAL_EXPIRED,
                f"Approval ticket '{token}' has expired",
            )

        meta = dict(ticket.metadata)
        meta["approved_by"] = approved_by
        meta["approved_at"] = now.isoformat()

        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE approvals
                SET status = ?, metadata_json = ?
                WHERE (token_hash = ? OR token = ?) AND status = ?;
                """,
                (STATUS_APPROVED, json.dumps(meta), token_hash, token, STATUS_PENDING),
            )
            if cur.rowcount != 1:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    f"Cannot approve ticket '{token}': ticket is no longer in PENDING state",
                )

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

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE approvals
                SET status = ?, metadata_json = ?
                WHERE (token_hash = ? OR token = ?) AND status IN (?, ?);
                """,
                (
                    STATUS_DENIED,
                    json.dumps(meta),
                    token_hash,
                    token,
                    STATUS_PENDING,
                    STATUS_APPROVED,
                ),
            )
            if cur.rowcount != 1:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    f"Cannot deny ticket '{token}': ticket is already {ticket.status}",
                )

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

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE approvals
                SET status = ?, metadata_json = ?
                WHERE (token_hash = ? OR token = ?) AND status IN (?, ?);
                """,
                (
                    STATUS_REVOKED,
                    json.dumps(meta),
                    token_hash,
                    token,
                    STATUS_PENDING,
                    STATUS_APPROVED,
                ),
            )
            if cur.rowcount != 1:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    f"Cannot revoke ticket '{token}': ticket is already {ticket.status}",
                )

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

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(ticket.expires_at)
        if now > expires_at:
            conn = self.db.connect()
            with conn:
                conn.execute(
                    "UPDATE approvals SET status = ? WHERE token_hash = ? OR token = ?;",
                    (STATUS_EXPIRED, token_hash, token),
                )
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
        if ticket.target_path != clean_target and ticket.target_path != "*":
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

        if ticket.principal_id != principal_id:
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

        # Atomic single-use consumption inside write transaction
        consumed_at = now.isoformat()
        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE approvals
                SET status = ?, consumed_at = ?, consumed_by = ?
                WHERE (token_hash = ? OR token = ?) AND status = ?;
                """,
                (STATUS_CONSUMED, consumed_at, principal_id, token_hash, token, STATUS_APPROVED),
            )
            rows_updated = cur.rowcount

        if rows_updated != 1:
            raise TacpSecurityError(
                ErrorCode.APPROVAL_ALREADY_USED,
                f"Approval ticket '{token}' was concurrently consumed or modified",
            )

        return True

    def create_group_ticket(
        self,
        principal_id: str,
        action_type: str,
        workspace_id: str,
        plan_hash: str,
        ttl_seconds: int = 900,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalTicket:
        """Issue a grouped approval ticket bound to an entire verified operation plan."""
        meta = dict(metadata or {})
        meta["is_group"] = True
        meta["plan_hash"] = plan_hash
        return self.create_ticket(
            principal_id=principal_id,
            action_type=action_type,
            workspace_id=workspace_id,
            target_path="*",
            patch_hash=plan_hash,
            ttl_seconds=ttl_seconds,
            metadata=meta,
        )

    def verify_and_consume_group(
        self,
        token: str,
        principal_id: str,
        action_type: str,
        workspace_id: str,
        plan_hash: str,
    ) -> bool:
        """Verify and atomically consume a grouped approval ticket."""
        return self.verify_and_consume(
            token=token,
            principal_id=principal_id,
            action_type=action_type,
            workspace_id=workspace_id,
            target_path="*",
            patch_hash=plan_hash,
        )

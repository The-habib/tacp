"""Capability Lease Engine for Risk-Adaptive Governance."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from tacp.control.risk import RiskLevel
from tacp.domain.errors import ErrorCode, TacpSecurityError, TacpValidationError
from tacp.domain.lease import CapabilityLease
from tacp.infrastructure.database import Database


class LeaseEngine:
    """Manages the issuance, validation, atomic consumption, and revocation of capability leases."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_lease(
        self,
        principal_id: str,
        workspace_id: str,
        capabilities: Sequence[str],
        resources: Optional[Sequence[str]] = None,
        risk_ceiling: str = RiskLevel.R2.value,
        budget: int = 20,
        duration_seconds: int = 1200,
        trust_profile: str = "BALANCED",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CapabilityLease:
        """Issue a new bounded capability lease."""
        if not principal_id or not principal_id.strip():
            raise TacpValidationError("principal_id cannot be empty")
        if not workspace_id or not workspace_id.strip():
            raise TacpValidationError("workspace_id cannot be empty")
        if not capabilities:
            raise TacpValidationError("capabilities sequence cannot be empty")
        if budget <= 0:
            raise TacpValidationError("budget must be greater than zero")
        if duration_seconds <= 0:
            raise TacpValidationError("duration_seconds must be positive")

        # Cap lease duration to 3600 seconds (1 hour maximum)
        clamped_duration = min(duration_seconds, 3600)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=clamped_duration)

        lease = CapabilityLease(
            id=str(uuid.uuid4()),
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            principal_id=principal_id,
            workspace_id=workspace_id,
            capabilities=tuple(capabilities),
            resources=tuple(resources or ()),
            risk_ceiling=risk_ceiling,
            budget=budget,
            budget_remaining=budget,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
            trust_profile=trust_profile,
            policy_version=1,
            session_id=session_id,
            revoked=False,
            metadata=metadata or {},
        )

        conn = self.db.connect()
        with conn:
            conn.execute(
                """
                INSERT INTO leases (
                    id, lease_id, principal_id, workspace_id,
                    capabilities_json, resources_json, risk_ceiling,
                    budget, budget_remaining, issued_at, expires_at,
                    trust_profile, policy_version, session_id,
                    revoked, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    lease.id,
                    lease.lease_id,
                    lease.principal_id,
                    lease.workspace_id,
                    json.dumps(list(lease.capabilities)),
                    json.dumps(list(lease.resources)),
                    lease.risk_ceiling,
                    lease.budget,
                    lease.budget_remaining,
                    lease.issued_at,
                    lease.expires_at,
                    lease.trust_profile,
                    lease.policy_version,
                    lease.session_id,
                    1 if lease.revoked else 0,
                    json.dumps(lease.metadata),
                ),
            )
        return lease

    def get_lease(self, lease_id: str) -> Optional[CapabilityLease]:
        """Fetch a capability lease by its lease_id token."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, lease_id, principal_id, workspace_id,
                   capabilities_json, resources_json, risk_ceiling,
                   budget, budget_remaining, issued_at, expires_at,
                   trust_profile, policy_version, session_id,
                   revoked, metadata_json
            FROM leases
            WHERE lease_id = ?;
            """,
            (lease_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return CapabilityLease(
            id=row["id"],
            lease_id=row["lease_id"],
            principal_id=row["principal_id"],
            workspace_id=row["workspace_id"],
            capabilities=tuple(json.loads(row["capabilities_json"])),
            resources=tuple(json.loads(row["resources_json"])),
            risk_ceiling=row["risk_ceiling"],
            budget=row["budget"],
            budget_remaining=row["budget_remaining"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            trust_profile=row["trust_profile"],
            policy_version=row["policy_version"],
            session_id=row["session_id"],
            revoked=bool(row["revoked"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def list_leases(
        self,
        workspace_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[CapabilityLease]:
        """List leases with optional workspace and principal filtering."""
        conn = self.db.connect()
        cursor = conn.cursor()

        query = """
            SELECT id, lease_id, principal_id, workspace_id,
                   capabilities_json, resources_json, risk_ceiling,
                   budget, budget_remaining, issued_at, expires_at,
                   trust_profile, policy_version, session_id,
                   revoked, metadata_json
            FROM leases
            WHERE 1=1
        """
        params: List[Any] = []
        if workspace_id:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        if principal_id:
            query += " AND principal_id = ?"
            params.append(principal_id)
        if active_only:
            query += " AND revoked = 0 AND budget_remaining > 0"

        query += " ORDER BY rowid DESC;"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        leases: List[CapabilityLease] = []
        for row in rows:
            lease_item = CapabilityLease(
                id=row["id"],
                lease_id=row["lease_id"],
                principal_id=row["principal_id"],
                workspace_id=row["workspace_id"],
                capabilities=tuple(json.loads(row["capabilities_json"])),
                resources=tuple(json.loads(row["resources_json"])),
                risk_ceiling=row["risk_ceiling"],
                budget=row["budget"],
                budget_remaining=row["budget_remaining"],
                issued_at=row["issued_at"],
                expires_at=row["expires_at"],
                trust_profile=row["trust_profile"],
                policy_version=row["policy_version"],
                session_id=row["session_id"],
                revoked=bool(row["revoked"]),
                metadata=json.loads(row["metadata_json"]),
            )
            if not active_only or lease_item.is_active():
                leases.append(lease_item)

        return leases

    def verify_and_consume(
        self,
        lease_id: str,
        principal_id: str,
        capability: str,
        workspace_id: str,
        risk_level: str,
        target_path: Optional[str] = None,
    ) -> bool:
        """Verify boundaries and atomically decrement budget."""
        lease = self.get_lease(lease_id)
        if not lease:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Capability lease '{lease_id}' not found",
            )

        if lease.revoked:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Capability lease '{lease_id}' has been revoked",
            )

        if not lease.is_active():
            raise TacpSecurityError(
                ErrorCode.APPROVAL_EXPIRED,
                f"Capability lease '{lease_id}' has expired or budget exhausted",
            )

        if lease.principal_id != principal_id:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Lease principal mismatch: expected '{lease.principal_id}', got '{principal_id}'",
            )

        if lease.workspace_id != workspace_id:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Lease workspace mismatch: expected '{lease.workspace_id}', got '{workspace_id}'",
            )

        if not lease.allows_capability(capability):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Capability '{capability}' is not permitted under lease '{lease_id}'",
            )

        if not lease.allows_risk(risk_level):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Risk level '{risk_level}' exceeds lease risk ceiling '{lease.risk_ceiling}'",
            )

        if not lease.allows_resource(target_path):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Target path '{target_path}' is outside lease allowed resources",
            )

        # Atomic conditional decrement
        conn = self.db.connect()
        with conn:
            cursor = conn.execute(
                """
                UPDATE leases
                SET budget_remaining = budget_remaining - 1
                WHERE lease_id = ?
                  AND principal_id = ?
                  AND workspace_id = ?
                  AND revoked = 0
                  AND budget_remaining > 0;
                """,
                (lease_id, principal_id, workspace_id),
            )
            if cursor.rowcount == 0:
                raise TacpSecurityError(
                    ErrorCode.APPROVAL_ALREADY_USED,
                    f"Lease '{lease_id}' budget exhausted or modified concurrently",
                )

        return True

    def revoke_lease(self, lease_id: str, reason: str = "") -> bool:
        """Revoke an active lease."""
        conn = self.db.connect()
        with conn:
            cursor = conn.execute(
                "UPDATE leases SET revoked = 1 WHERE lease_id = ? AND revoked = 0;",
                (lease_id,),
            )
            return cursor.rowcount > 0

    def revoke_all_leases(self, workspace_id: Optional[str] = None, reason: str = "") -> int:
        """Revoke all active leases across the system or within a workspace."""
        conn = self.db.connect()
        with conn:
            if workspace_id:
                cursor = conn.execute(
                    "UPDATE leases SET revoked = 1 WHERE workspace_id = ? AND revoked = 0;",
                    (workspace_id,),
                )
            else:
                cursor = conn.execute("UPDATE leases SET revoked = 1 WHERE revoked = 0;")
            return cursor.rowcount

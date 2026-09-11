from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.control.risk import RiskEvaluator
from tacp.core.audit_service import AuditService
from tacp.core.lock_service import LockService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.contract import ExecutionContract
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpConflictError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.patch import PatchResult, PatchStatus
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


class PatchService:
    """Governed Workspace Patch Service implementing the 16-stage pipeline."""

    def __init__(
        self,
        db: Database,
        workspace_service: WorkspaceService,
        policy_engine: PolicyEngine,
        fs_provider: FilesystemProvider,
        audit_service: AuditService,
        lock_service: LockService,
        approval_engine: ApprovalEngine,
        config: TacpConfig,
    ) -> None:
        self.db = db
        self.workspace_service = workspace_service
        self.policy_engine = policy_engine
        self.fs_provider = fs_provider
        self.audit_service = audit_service
        self.lock_service = lock_service
        self.approval_engine = approval_engine
        self.config = config

    def execute_patch(
        self,
        workspace_id: str,
        subpath: str,
        patch_content: str,
        base_checksum: str,
        dry_run: bool = False,
        approval_token: Optional[str] = None,
        principal_id: str = "agent",
        request_id: Optional[str] = None,
    ) -> PatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())
        principal = Principal(id=principal_id)
        ctx = RequestContext(
            capability="workspace.patch",
            principal=principal,
            request_id=req_id,
        )

        # Stage 5: Resource Resolution
        ws = self.workspace_service.get_workspace(workspace_id)

        # Stage 6: Validation
        if not subpath or not subpath.strip():
            raise TacpValidationError("Subpath parameter is required and cannot be empty")
        if not patch_content:
            raise TacpValidationError("Patch content is required and cannot be empty")
        if not base_checksum or not base_checksum.strip():
            raise TacpValidationError(
                "Base checksum parameter is required for optimistic concurrency control"
            )

        clean_subpath = subpath.strip()

        # Stage 7: Policy Evaluation
        decision = self.policy_engine.evaluate_request(
            ctx,
            workspace=ws,
            target_path=clean_subpath,
            dry_run=dry_run,
            has_approval=bool(approval_token),
        )

        if not decision.allowed:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability="workspace.patch",
                    action="patch_evaluate",
                    policy_decision=decision.decision_type,
                    result="DENIED",
                    duration_ms=duration_ms,
                    principal=principal_id,
                    request_id=req_id,
                    workspace_id=workspace_id,
                    parameters_redacted={
                        "subpath": clean_subpath,
                        "dry_run": dry_run,
                        "reason": decision.reason,
                    },
                )
            )

            if decision.decision_type == "REQUIRE_APPROVAL":
                patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
                ticket = self.approval_engine.create_ticket(
                    principal_id=principal_id,
                    action_type="workspace.patch",
                    workspace_id=workspace_id,
                    target_path=clean_subpath,
                    patch_hash=patch_hash,
                    metadata={"request_id": req_id, "base_checksum": base_checksum},
                )
                raise TacpApprovalRequiredError(
                    f"Execution of 'workspace.patch' requires explicit human approval. "
                    f"Ticket created: {ticket.token} (id: {ticket.id})"
                )
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Policy violation: {decision.reason}",
            )

        # Stage 8: Risk Evaluation
        risk = RiskEvaluator.evaluate("workspace.patch", is_read_only=False, dry_run=dry_run)

        # Stage 10: Lock Acquisition
        resource_id = f"{workspace_id}:{clean_subpath}"
        with self.lock_service.hold(resource_id=resource_id, owner_id=principal_id, ttl_seconds=30):
            # Stage 11: Approval Verification & Single-Use Consumption
            patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
            if not dry_run:
                if not approval_token:
                    ticket = self.approval_engine.create_ticket(
                        principal_id=principal_id,
                        action_type="workspace.patch",
                        workspace_id=workspace_id,
                        target_path=clean_subpath,
                        patch_hash=patch_hash,
                    )
                    raise TacpApprovalRequiredError(
                        f"Execution requires human approval ticket: {ticket.token}"
                    )
                self.approval_engine.verify_and_consume(
                    token=approval_token,
                    principal_id=principal_id,
                    action_type="workspace.patch",
                    workspace_id=workspace_id,
                    target_path=clean_subpath,
                    patch_hash=patch_hash,
                )

            # Stage 12: Execution Contract Issuance
            contract_id = f"contract-{uuid.uuid4().hex[:8]}"
            contract = ExecutionContract(
                contract_id=contract_id,
                principal_id=principal_id,
                capability="workspace.patch",
                target_resource=resource_id,
                risk_level=risk.value,
                approval_id=approval_token,
                status="ACTIVE",
                checksum_before=base_checksum,
            )

            # Stage 13: Provider Atomic Execution
            patch_id = f"patch-{uuid.uuid4().hex[:8]}"
            snapshot_dir = self.config.data_dir / "snapshots"
            provider_res = self.fs_provider.apply_patch(
                workspace_root=ws.root_path,
                subpath=clean_subpath,
                patch_diff=patch_content,
                base_checksum=base_checksum,
                dry_run=dry_run,
                patch_id=patch_id,
                snapshot_dir=snapshot_dir,
            )

            # Stage 14: Post-Verification Persist
            if not dry_run:
                conn = self.db.connect()
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO patches (
                        id, workspace_id, target_path, base_checksum, result_checksum,
                        diff_content, status, snapshot_path, applied_at, applied_by, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        patch_id,
                        workspace_id,
                        clean_subpath,
                        base_checksum,
                        provider_res["after_checksum"],
                        patch_content,
                        "APPLIED",
                        provider_res["snapshot_path"],
                        now_iso,
                        principal_id,
                        json.dumps(
                            {
                                "contract_id": contract.contract_id,
                                "approval_token": approval_token,
                            }
                        ),
                    ),
                )
                conn.commit()

            # Stage 15 & 16: Audit & Result
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            audit_event = AuditEvent(
                capability="workspace.patch",
                action="patch_simulate" if dry_run else "patch_apply",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=duration_ms,
                principal=principal_id,
                request_id=req_id,
                workspace_id=workspace_id,
                parameters_redacted={
                    "subpath": clean_subpath,
                    "before_checksum": base_checksum,
                    "after_checksum": provider_res["after_checksum"],
                    "lines_added": provider_res["lines_added"],
                    "lines_removed": provider_res["lines_removed"],
                    "dry_run": dry_run,
                    "patch_id": patch_id,
                },
            )
            self.audit_service.record_event(audit_event)

            return PatchResult(
                patch_id=patch_id,
                status=PatchStatus.SIMULATED if dry_run else PatchStatus.APPLIED,
                subpath=clean_subpath,
                before_checksum=base_checksum,
                after_checksum=provider_res["after_checksum"],
                lines_added=provider_res["lines_added"],
                lines_removed=provider_res["lines_removed"],
                diff_preview=provider_res["diff_preview"],
                audit_id=audit_event.id,
                message=provider_res["message"],
                details={
                    "snapshot_path": provider_res.get("snapshot_path"),
                    "contract_id": contract_id,
                    "dry_run": dry_run,
                },
            )

    def rollback_patch(
        self,
        patch_id: str,
        principal_id: str = "human_operator",
        request_id: Optional[str] = None,
    ) -> PatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())

        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, workspace_id, target_path, base_checksum, result_checksum,
                   diff_content, status, snapshot_path, applied_at, applied_by
            FROM patches WHERE id = ?;
            """,
            (patch_id,),
        )
        row = cur.fetchone()

        if not row:
            raise TacpNotFoundError(f"Patch record '{patch_id}' not found")

        ws_id = row[1]
        target_path = row[2]
        result_checksum = row[4]
        status = row[6]
        snapshot_path = row[7]

        if status == "ROLLED_BACK":
            raise TacpConflictError(f"Patch '{patch_id}' has already been rolled back")

        if not snapshot_path:
            raise TacpNotFoundError(f"No snapshot available for patch '{patch_id}'")

        ws = self.workspace_service.get_workspace(ws_id)
        resource_id = f"{ws_id}:{target_path}"

        with self.lock_service.hold(resource_id=resource_id, owner_id=principal_id, ttl_seconds=30):
            restore_res = self.fs_provider.rollback_patch(
                workspace_root=ws.root_path,
                subpath=target_path,
                snapshot_path=Path(snapshot_path),
                expected_current_checksum=result_checksum,
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            conn = self.db.connect()
            conn.execute(
                """
                UPDATE patches
                SET status = 'ROLLED_BACK', rollback_at = ?
                WHERE id = ?;
                """,
                (now_iso, patch_id),
            )
            conn.commit()

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            audit_event = AuditEvent(
                capability="workspace.patch",
                action="patch_rollback",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=duration_ms,
                principal=principal_id,
                request_id=req_id,
                workspace_id=ws_id,
                parameters_redacted={
                    "patch_id": patch_id,
                    "target_path": target_path,
                    "restored_checksum": restore_res["restored_checksum"],
                },
            )
            self.audit_service.record_event(audit_event)

            return PatchResult(
                patch_id=patch_id,
                status=PatchStatus.ROLLED_BACK,
                subpath=target_path,
                before_checksum=result_checksum,
                after_checksum=restore_res["restored_checksum"],
                audit_id=audit_event.id,
                message=f"Patch '{patch_id}' successfully rolled back",
                details={"snapshot_path": snapshot_path},
            )

    def list_patches(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cur = conn.cursor()
        if workspace_id:
            cur.execute(
                """
                SELECT id, workspace_id, target_path, base_checksum, result_checksum,
                       status, snapshot_path, applied_at, applied_by, rollback_at
                FROM patches
                WHERE workspace_id = ?
                ORDER BY applied_at DESC
                LIMIT ?;
                """,
                (workspace_id, max(1, min(limit, 100))),
            )
        else:
            cur.execute(
                """
                SELECT id, workspace_id, target_path, base_checksum, result_checksum,
                       status, snapshot_path, applied_at, applied_by, rollback_at
                FROM patches
                ORDER BY applied_at DESC
                LIMIT ?;
                """,
                (max(1, min(limit, 100)),),
            )
        rows = cur.fetchall()

        patches = []
        for r in rows:
            patches.append(
                {
                    "id": r[0],
                    "workspace_id": r[1],
                    "target_path": r[2],
                    "base_checksum": r[3],
                    "result_checksum": r[4],
                    "status": r[5],
                    "snapshot_path": r[6],
                    "applied_at": r[7],
                    "applied_by": r[8],
                    "rollback_at": r[9],
                }
            )
        return patches

    def get_patch(self, patch_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, workspace_id, target_path, base_checksum, result_checksum,
                   diff_content, status, snapshot_path, applied_at, applied_by,
                   rollback_at, metadata_json
            FROM patches WHERE id = ?;
            """,
            (patch_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "workspace_id": row[1],
            "target_path": row[2],
            "base_checksum": row[3],
            "result_checksum": row[4],
            "diff_content": row[5],
            "status": row[6],
            "snapshot_path": row[7],
            "applied_at": row[8],
            "applied_by": row[9],
            "rollback_at": row[10],
            "metadata": json.loads(row[11]) if row[11] else {},
        }

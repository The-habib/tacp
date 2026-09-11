from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.control.approval import ApprovalEngine, compute_canonical_batch_hash
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
from tacp.domain.patch import BatchPatchResult, PatchResult, PatchStatus
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
        principal: Optional[Principal] = None,
    ) -> PatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())
        caller_principal = principal or Principal.local_agent(principal_id)
        ctx = RequestContext(
            capability="workspace.patch",
            principal=caller_principal,
            request_id=req_id,
        )

        # Stage 5: Resource Resolution
        ws = self.workspace_service.get_workspace(workspace_id)

        if not subpath or not subpath.strip():
            raise TacpValidationError("Subpath parameter is required and cannot be empty")
        raw_subp = subpath.strip()
        if raw_subp.startswith("/") or raw_subp.startswith("\\") or Path(raw_subp).is_absolute():
            raise TacpSecurityError(
                ErrorCode.OUTSIDE_WORKSPACE,
                f"Absolute path '{raw_subp}' is forbidden",
            )
        if not patch_content:
            raise TacpValidationError("Patch content is required and cannot be empty")
        if not base_checksum or not base_checksum.strip():
            raise TacpValidationError(
                "Base checksum parameter is required for optimistic concurrency control"
            )

        clean_subpath = raw_subp.replace("\\", "/")
        while clean_subpath.startswith("./"):
            clean_subpath = clean_subpath[2:]
        clean_subpath = clean_subpath.strip("/")

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
                        f"Execution of 'workspace.patch' requires explicit human approval. "
                        f"Ticket created: {ticket.token} (id: {ticket.id})"
                    )

                self.approval_engine.verify_and_consume(
                    token=approval_token,
                    principal_id=principal_id,
                    action_type="workspace.patch",
                    workspace_id=workspace_id,
                    target_path=clean_subpath,
                    patch_hash=patch_hash,
                    base_checksum=base_checksum,
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
        principal: Optional[Principal] = None,
        approval_token: Optional[str] = None,
    ) -> PatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())

        is_human = (
            principal_id in ("human_operator", "operator")
            or "operator" in principal_id
            or "human" in principal_id
        )
        caller_principal = principal or (
            Principal.human_operator(principal_id)
            if is_human
            else Principal.local_agent(principal_id)
        )
        context = RequestContext(
            capability="workspace.rollback",
            principal=caller_principal,
            request_id=req_id,
        )

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

        # Policy enforcement for rollback capability
        self.policy_engine.enforce(
            context=context,
            workspace=ws,
            target_path=target_path,
            has_approval=bool(approval_token),
        )

        resource_id = f"{ws_id}:{target_path}"

        with self.lock_service.hold(
            resource_id=resource_id, owner_id=caller_principal.id, ttl_seconds=30
        ):
            restore_res = self.fs_provider.rollback_patch(
                workspace_root=ws.root_path,
                subpath=target_path,
                snapshot_path=Path(snapshot_path),
                expected_current_checksum=result_checksum,
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            conn = self.db.connect()
            with conn:
                conn.execute(
                    """
                    UPDATE patches
                    SET status = 'ROLLED_BACK', rollback_at = ?
                    WHERE id = ?;
                    """,
                    (now_iso, patch_id),
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            audit_event = AuditEvent(
                capability="workspace.rollback",
                action="patch_rollback",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=duration_ms,
                principal=caller_principal.id,
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

    def execute_patch_batch(
        self,
        workspace_id: str,
        patches: List[Dict[str, Any]],
        dry_run: bool = False,
        approval_token: Optional[str] = None,
        principal_id: str = "agent",
        request_id: Optional[str] = None,
        principal: Optional[Principal] = None,
    ) -> BatchPatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())
        caller_principal = principal or Principal.local_agent(principal_id)
        ctx = RequestContext(
            capability="workspace.patch_batch",
            principal=caller_principal,
            request_id=req_id,
        )

        # Stage 5: Resource Resolution
        ws = self.workspace_service.get_workspace(workspace_id)

        # Stage 6: Validation
        if not isinstance(patches, list) or len(patches) == 0:
            raise TacpValidationError("Patches parameter must be a non-empty list")

        if len(patches) > self.config.limits.max_batch_files:
            raise TacpValidationError(
                f"Batch item count ({len(patches)}) exceeds maximum limit of "
                f"{self.config.limits.max_batch_files}"
            )

        clean_patches: List[Dict[str, Any]] = []
        subpaths: List[str] = []
        for idx, item in enumerate(patches):
            if not isinstance(item, dict):
                raise TacpValidationError(f"Batch item at index {idx} must be an object")
            subpath = item.get("subpath")
            patch_content = item.get("patch_content")
            base_checksum = item.get("base_checksum")

            if subpath is None or not str(subpath).strip():
                raise TacpValidationError(
                    f"Batch item {idx}: subpath parameter is required and cannot be empty"
                )
            raw_subp = str(subpath).strip()
            if (
                raw_subp.startswith("/")
                or raw_subp.startswith("\\")
                or Path(raw_subp).is_absolute()
            ):
                raise TacpSecurityError(
                    ErrorCode.OUTSIDE_WORKSPACE,
                    f"Batch item {idx}: absolute path '{raw_subp}' is forbidden",
                )
            if patch_content is None or not str(patch_content):
                raise TacpValidationError(
                    f"Batch item {idx}: patch_content parameter is required and cannot be empty"
                )
            if base_checksum is None or not str(base_checksum).strip():
                raise TacpValidationError(
                    f"Batch item {idx}: base_checksum parameter is required for OCC"
                )

            clean_subp = raw_subp.replace("\\", "/")
            while clean_subp.startswith("./"):
                clean_subp = clean_subp[2:]
            clean_subp = clean_subp.strip("/")

            subpaths.append(clean_subp)
            clean_patches.append(
                {
                    "subpath": clean_subp,
                    "patch_content": str(patch_content),
                    "base_checksum": str(base_checksum).strip(),
                }
            )

        # Target Aliasing / Duplicate Target Denial
        if len(subpaths) != len(set(subpaths)):
            raise TacpValidationError(
                "Duplicate subpath in batch request: each target file must appear at most once"
            )

        # Stage 7: Policy Evaluation
        decision = self.policy_engine.evaluate_request(
            ctx,
            workspace=ws,
            target_paths=subpaths,
            dry_run=dry_run,
            has_approval=bool(approval_token),
        )

        if not decision.allowed:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability="workspace.patch_batch",
                    action="batch_evaluate",
                    policy_decision=decision.decision_type,
                    result="DENIED",
                    duration_ms=duration_ms,
                    principal=principal_id,
                    request_id=req_id,
                    workspace_id=workspace_id,
                    parameters_redacted={
                        "subpaths": subpaths,
                        "patch_count": len(clean_patches),
                        "dry_run": dry_run,
                        "reason": decision.reason,
                    },
                )
            )

            if decision.decision_type == "REQUIRE_APPROVAL":
                batch_hash = compute_canonical_batch_hash(clean_patches)
                ticket = self.approval_engine.create_ticket(
                    principal_id=principal_id,
                    action_type="workspace.patch_batch",
                    workspace_id=workspace_id,
                    target_path="*",
                    patch_hash=batch_hash,
                    metadata={
                        "request_id": req_id,
                        "patch_count": len(clean_patches),
                        "subpaths": sorted(subpaths),
                    },
                )
                raise TacpApprovalRequiredError(
                    f"Execution of 'workspace.patch_batch' requires explicit human approval. "
                    f"Ticket created: {ticket.token} (id: {ticket.id})"
                )
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Policy violation: {decision.reason}",
            )

        # Stage 8: Risk Evaluation
        risk = RiskEvaluator.evaluate("workspace.patch_batch", is_read_only=False, dry_run=dry_run)

        # Stage 10: Multi-Resource Lock Acquisition
        resource_ids = [f"{workspace_id}:{sp}" for sp in sorted(set(subpaths))]
        with self.lock_service.hold_many(
            resource_ids=resource_ids, owner_id=principal_id, ttl_seconds=45
        ):
            batch_hash = compute_canonical_batch_hash(clean_patches)

            # Stage 11: Approval Verification & Single-Use Consumption
            if not dry_run:
                if not approval_token:
                    ticket = self.approval_engine.create_ticket(
                        principal_id=principal_id,
                        action_type="workspace.patch_batch",
                        workspace_id=workspace_id,
                        target_path="*",
                        patch_hash=batch_hash,
                        metadata={
                            "request_id": req_id,
                            "patch_count": len(clean_patches),
                            "subpaths": sorted(subpaths),
                        },
                    )
                    raise TacpApprovalRequiredError(
                        f"Execution of 'workspace.patch_batch' requires explicit human approval. "
                        f"Ticket created: {ticket.token} (id: {ticket.id})"
                    )

                self.approval_engine.verify_and_consume(
                    token=approval_token,
                    principal_id=principal_id,
                    action_type="workspace.patch_batch",
                    workspace_id=workspace_id,
                    target_path="*",
                    patch_hash=batch_hash,
                )

            # Stage 12: Execution Contract Issuance
            contract_id = f"contract-{uuid.uuid4().hex[:8]}"
            contract = ExecutionContract(
                contract_id=contract_id,
                principal_id=principal_id,
                capability="workspace.patch_batch",
                target_resource=f"{workspace_id}:batch:{len(clean_patches)}_files",
                risk_level=risk.value,
                approval_id=approval_token,
                status="ACTIVE",
            )

            # Stage 13: Provider Atomic Batch Execution
            batch_id = f"batch-{uuid.uuid4().hex[:8]}"
            snapshot_dir = self.config.data_dir / "snapshots"
            provider_res = self.fs_provider.apply_patch_batch(
                workspace_root=ws.root_path,
                patches=clean_patches,
                dry_run=dry_run,
                batch_id=batch_id,
                snapshot_dir=snapshot_dir,
            )

            results_list: List[PatchResult] = []
            for r in provider_res["results"]:
                results_list.append(
                    PatchResult(
                        patch_id=r["patch_id"],
                        status=r["status"],
                        subpath=r["subpath"],
                        before_checksum=r["before_checksum"],
                        after_checksum=r["after_checksum"],
                        lines_added=r["lines_added"],
                        lines_removed=r["lines_removed"],
                        diff_preview=r["diff_preview"],
                        audit_id="",
                        message=r["message"],
                        details={"snapshot_path": r.get("snapshot_path")},
                    )
                )

            # Stage 14: Post-Verification Persist
            if not dry_run:
                conn = self.db.connect()
                now_iso = datetime.now(timezone.utc).isoformat()
                manifest_json = json.dumps(provider_res["snapshot_manifest"])
                results_json = json.dumps([r.to_dict() for r in results_list])
                metadata_json = json.dumps(
                    {
                        "contract_id": contract.contract_id,
                        "approval_token": approval_token,
                        "subpaths": subpaths,
                    }
                )
                conn.execute(
                    """
                    INSERT INTO batches (
                        id, workspace_id, batch_hash, patch_count, status,
                        applied_at, applied_by, snapshot_manifest_json, results_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        batch_id,
                        workspace_id,
                        batch_hash,
                        len(clean_patches),
                        "APPLIED",
                        now_iso,
                        principal_id,
                        manifest_json,
                        results_json,
                        metadata_json,
                    ),
                )
                conn.commit()

            # Stage 15 & 16: Audit & Result
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            audit_event = AuditEvent(
                capability="workspace.patch_batch",
                action="batch_simulate" if dry_run else "batch_apply",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=duration_ms,
                principal=principal_id,
                request_id=req_id,
                workspace_id=workspace_id,
                parameters_redacted={
                    "batch_id": batch_id,
                    "patch_count": len(clean_patches),
                    "subpaths": subpaths,
                    "dry_run": dry_run,
                },
            )
            self.audit_service.record_event(audit_event)

            return BatchPatchResult(
                batch_id=batch_id,
                status=PatchStatus.SIMULATED if dry_run else PatchStatus.APPLIED,
                workspace_id=workspace_id,
                results=results_list,
                audit_id=audit_event.id,
                message=provider_res["message"],
                details={
                    "contract_id": contract_id,
                    "dry_run": dry_run,
                    "snapshot_manifest": provider_res.get("snapshot_manifest", {}),
                },
            )

    def rollback_batch(
        self,
        batch_id: str,
        principal_id: str = "human_operator",
        request_id: Optional[str] = None,
        principal: Optional[Principal] = None,
        approval_token: Optional[str] = None,
    ) -> BatchPatchResult:
        start_time = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())

        is_human = (
            principal_id in ("human_operator", "operator")
            or "operator" in principal_id
            or "human" in principal_id
        )
        caller_principal = principal or (
            Principal.human_operator(principal_id)
            if is_human
            else Principal.local_agent(principal_id)
        )
        context = RequestContext(
            capability="workspace.batch_rollback",
            principal=caller_principal,
            request_id=req_id,
        )

        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, workspace_id, batch_hash, patch_count, status,
                   applied_at, applied_by, snapshot_manifest_json, results_json
            FROM batches WHERE id = ?;
            """,
            (batch_id,),
        )
        row = cur.fetchone()

        if not row:
            raise TacpNotFoundError(f"Batch record '{batch_id}' not found")

        ws_id = row[1]
        status = row[4]
        snapshot_manifest = json.loads(row[7]) if row[7] else {}
        results_json = json.loads(row[8]) if row[8] else []

        if status == "ROLLED_BACK":
            raise TacpConflictError(f"Batch '{batch_id}' has already been rolled back")

        if not snapshot_manifest:
            raise TacpNotFoundError(f"No snapshot manifest available for batch '{batch_id}'")

        ws = self.workspace_service.get_workspace(ws_id)
        subpaths = list(snapshot_manifest.keys())

        # Policy enforcement for batch rollback capability
        self.policy_engine.enforce(
            context=context,
            workspace=ws,
            target_paths=subpaths,
            has_approval=bool(approval_token),
        )

        resource_ids = [f"{ws_id}:{sp}" for sp in sorted(subpaths)]

        with self.lock_service.hold_many(
            resource_ids=resource_ids, owner_id=caller_principal.id, ttl_seconds=45
        ):
            expected_checksums = {r["subpath"]: r["after_checksum"] for r in results_json}
            restore_res = self.fs_provider.rollback_patch_batch(
                workspace_root=ws.root_path,
                snapshot_manifest=snapshot_manifest,
                expected_checksums=expected_checksums,
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            conn = self.db.connect()
            with conn:
                conn.execute(
                    """
                    UPDATE batches
                    SET status = 'ROLLED_BACK', rollback_at = ?
                    WHERE id = ?;
                    """,
                    (now_iso, batch_id),
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            audit_event = AuditEvent(
                capability="workspace.batch_rollback",
                action="batch_rollback",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=duration_ms,
                principal=caller_principal.id,
                request_id=req_id,
                workspace_id=ws_id,
                parameters_redacted={
                    "batch_id": batch_id,
                    "restored_files": [f["subpath"] for f in restore_res["restored_files"]],
                },
            )

            self.audit_service.record_event(audit_event)

            rolled_back_results = []
            for rf in restore_res["restored_files"]:
                exp_checksum = expected_checksums.get(rf["subpath"], "")
                rolled_back_results.append(
                    PatchResult(
                        patch_id=f"{batch_id}_{rf['subpath']}",
                        status=PatchStatus.ROLLED_BACK,
                        subpath=rf["subpath"],
                        before_checksum=exp_checksum,
                        after_checksum=rf["restored_checksum"],
                        audit_id=audit_event.id,
                        message=f"Rolled back {rf['subpath']} to pre-patch snapshot",
                    )
                )

            return BatchPatchResult(
                batch_id=batch_id,
                status=PatchStatus.ROLLED_BACK,
                workspace_id=ws_id,
                results=rolled_back_results,
                audit_id=audit_event.id,
                message=f"Batch '{batch_id}' successfully rolled back",
                details={"snapshot_manifest": snapshot_manifest},
            )

    def list_batches(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cur = conn.cursor()
        if workspace_id:
            cur.execute(
                """
                SELECT id, workspace_id, batch_hash, patch_count, status,
                       applied_at, applied_by, rollback_at
                FROM batches
                WHERE workspace_id = ?
                ORDER BY applied_at DESC
                LIMIT ?;
                """,
                (workspace_id, max(1, min(limit, 100))),
            )
        else:
            cur.execute(
                """
                SELECT id, workspace_id, batch_hash, patch_count, status,
                       applied_at, applied_by, rollback_at
                FROM batches
                ORDER BY applied_at DESC
                LIMIT ?;
                """,
                (max(1, min(limit, 100)),),
            )
        rows = cur.fetchall()

        batches = []
        for r in rows:
            batches.append(
                {
                    "id": r[0],
                    "workspace_id": r[1],
                    "batch_hash": r[2],
                    "patch_count": r[3],
                    "status": r[4],
                    "applied_at": r[5],
                    "applied_by": r[6],
                    "rollback_at": r[7],
                }
            )
        return batches

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, workspace_id, batch_hash, patch_count, status,
                   applied_at, applied_by, rollback_at, snapshot_manifest_json,
                   results_json, metadata_json
            FROM batches WHERE id = ?;
            """,
            (batch_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "workspace_id": row[1],
            "batch_hash": row[2],
            "patch_count": row[3],
            "status": row[4],
            "applied_at": row[5],
            "applied_by": row[6],
            "rollback_at": row[7],
            "snapshot_manifest": json.loads(row[8]) if row[8] else {},
            "results": json.loads(row[9]) if row[9] else [],
            "metadata": json.loads(row[10]) if row[10] else {},
        }

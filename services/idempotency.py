from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from db.supabase import supabase


class OperationConflictError(Exception):
    """Raised when a supplied record_id conflicts with existing tenant data."""


class OperationInProgressError(Exception):
    """Raised when the same operation_id is already being processed."""


def begin_operation(
    tenant_id: str,
    operation_id: str,
    entity_type: str,
    action: str,
    record_id: str | None = None,
) -> dict:
    """
    Idempotency gate for client→FastAPI mutations.

    Returns the operation row. Caller must NOT execute the business mutation
    again if status == 'completed'. Caller must retry later if status == 'processing'.
    """
    now = datetime.utcnow().isoformat()
    existing = (
        supabase.table("fbr_tbl_sync_operations")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("operation_id", operation_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        row = existing.data[0]
        if row["status"] == "completed":
            return {"status": "completed", "row": row, "can_proceed": False}
        if row["status"] == "processing":
            return {"status": "processing", "row": row, "can_proceed": False}
        if row["status"] == "failed":
            supabase.table("fbr_tbl_sync_operations").update(
                {
                    "status": "processing",
                    "last_error": None,
                    "created_at": now,
                }
            ).eq("id", row["id"]).execute()
            return {"status": "processing", "row": {**row, "status": "processing"}, "can_proceed": True}
        return {"status": "processing", "row": row, "can_proceed": False}

    inserted = (
        supabase.table("fbr_tbl_sync_operations")
        .insert(
            {
                "tenant_id": tenant_id,
                "operation_id": operation_id,
                "entity_type": entity_type,
                "action": action,
                "record_id": record_id,
                "status": "processing",
                "created_at": now,
            }
        )
        .execute()
    )
    return {"status": "processing", "row": inserted.data[0], "can_proceed": True}


def complete_operation(
    operation_row_id: str,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    now = datetime.utcnow().isoformat()
    supabase.table("fbr_tbl_sync_operations").update(
        {
            "status": "completed",
            "response_status": response_status,
            "response_body": response_body,
            "completed_at": now,
        }
    ).eq("id", operation_row_id).execute()


def fail_operation(operation_row_id: str, error: str) -> None:
    now = datetime.utcnow().isoformat()
    supabase.table("fbr_tbl_sync_operations").update(
        {
            "status": "failed",
            "last_error": error,
            "completed_at": now,
        }
    ).eq("id", operation_row_id).execute()

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from io import BytesIO
from services.bulk_processor import (
    parse_bulk_excel, parse_bulk_json,
    create_batch, submit_batch,
    upsert_customers, upsert_products
)
from services.excel_templates import generate_bulk_template
import openpyxl
from db.supabase import supabase
from routes.auth import get_current_tenant
from services.idempotency import begin_operation, complete_operation, fail_operation, OperationConflictError

router = APIRouter(prefix="/bulk", tags=["bulk"])


# ── Download bulk template ────────────────────────────────────────────────────
@router.get("/template")
def download_bulk_template():
    """Download Excel template with Invoices, Customers, Products sheets."""
    content = generate_bulk_template()
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fbr_bulk_template.xlsx"}
    )


# ── Upload + validate (Excel or JSON) ────────────────────────────────────────
@router.post("/upload")
async def upload_bulk_file(file: UploadFile = File(...), tenant_ctx: dict = Depends(get_current_tenant)):
    """
    Step 1: Upload file → parse → validate → return summary.
    Does NOT submit to FBR yet.
    """
    filename = file.filename or "upload"
    contents = await file.read()

    if filename.endswith(".json"):
        source_type = "json"
        parsed = parse_bulk_json(contents)
    elif filename.endswith((".xlsx", ".xls")):
        source_type = "excel"
        parsed = parse_bulk_excel(contents)
    else:
        raise HTTPException(400, "Only .xlsx, .xls, or .json files accepted")

    if not parsed["invoices"] and not parsed["customers"] and not parsed["products"]:
        raise HTTPException(400, "No data found in file. Check sheet names: Invoices, Customers, Products")

    result = create_batch(
        filename=filename,
        source_type=source_type,
        tenant_id=tenant_ctx["tenant_id"],
        parsed=parsed,
    )

    return result


# ── Confirm + submit batch to FBR ─────────────────────────────────────────────
@router.post("/confirm/{batch_id}")
async def confirm_batch(batch_id: str, tenant_ctx: dict = Depends(get_current_tenant)):
    """
    Step 2: User confirmed — submit all valid rows to FBR.
    """
    result = await submit_batch(batch_id, tenant_ctx["tenant_id"])
    return result


# ── Get batch status (for live progress) ─────────────────────────────────────
@router.get("/status/{batch_id}")
def get_batch_status(batch_id: str, tenant_ctx: dict = Depends(get_current_tenant)):
    batch = supabase.table("fbr_tbl_upload_batches").select("*").eq(
        "id", batch_id
    ).eq("tenant_id", tenant_ctx["tenant_id"]).single().execute()

    if not batch.data:
        raise HTTPException(404, "Batch not found")

    # Count by status
    rows = supabase.table("fbr_tbl_invoice_queue").select(
        "status, tracking_no, error_msg, row_number, validation_errors"
    ).eq("batch_id", batch_id).eq("tenant_id", tenant_ctx["tenant_id"]).execute()

    status_counts = {}
    for row in (rows.data or []):
        s = row["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "batch":         batch.data,
        "status_counts": status_counts,
        "rows":          rows.data,
    }


# ── Get all batches ───────────────────────────────────────────────────────────
@router.get("/batches")
def get_batches(tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_upload_batches").select("*").eq(
        "tenant_id", tenant_ctx["tenant_id"]
    ).order("created_at", desc=True).limit(20).execute()
    return {"batches": result.data}


# ── Customers CRUD ────────────────────────────────────────────────────────────
@router.get("/customers")
def get_customers(tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_customers").select("*").eq(
        "tenant_id", tenant_ctx["tenant_id"]
    ).eq("is_active", True).order("name").execute()
    return {"customers": result.data}


@router.post("/customers")
def save_customer(customer: dict, request: Request, tenant_ctx: dict = Depends(get_current_tenant)):
    operation_id = request.headers.get("X-Operation-Id", "")
    customer["tenant_id"] = tenant_ctx["tenant_id"]
    op = begin_operation(
        tenant_ctx["tenant_id"],
        operation_id,
        "CUSTOMER",
        "CREATE",
        customer.get("id"),
    )
    try:
        if op["status"] == "completed":
            return {"success": True, "data": op["row"]["response_body"], "cached": True}
        result = supabase.table("fbr_tbl_customers").upsert(
            customer, on_conflict="tenant_id,ntn_cnic"
        ).execute()
        complete_operation(op["row"]["id"], 200, result.data or {})
        return {"success": True, "data": result.data}
    except Exception as e:
        fail_operation(op["row"]["id"], str(e))
        raise HTTPException(500, str(e))


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, request: Request, tenant_ctx: dict = Depends(get_current_tenant)):
    operation_id = request.headers.get("X-Operation-Id", "")
    op = begin_operation(
        tenant_ctx["tenant_id"],
        operation_id,
        "CUSTOMER",
        "DELETE",
        customer_id,
    )
    try:
        if op["status"] == "completed":
            return {"success": True, "cached": True}
        supabase.table("fbr_tbl_customers").update({"is_active": False}).eq(
            "id", customer_id
        ).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
        complete_operation(op["row"]["id"], 200, {"deleted": customer_id})
        return {"success": True}
    except Exception as e:
        fail_operation(op["row"]["id"], str(e))
        raise HTTPException(500, str(e))


# ── Products CRUD ─────────────────────────────────────────────────────────────
@router.get("/products")
def get_products(tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_products").select("*").eq(
        "tenant_id", tenant_ctx["tenant_id"]
    ).eq("is_active", True).order("description").execute()
    return {"products": result.data}


@router.post("/products")
def save_product(product: dict, request: Request, tenant_ctx: dict = Depends(get_current_tenant)):
    operation_id = request.headers.get("X-Operation-Id", "")
    product["tenant_id"] = tenant_ctx["tenant_id"]
    op = begin_operation(
        tenant_ctx["tenant_id"],
        operation_id,
        "PRODUCT",
        "CREATE",
        product.get("id"),
    )
    try:
        if op["status"] == "completed":
            return {"success": True, "data": op["row"]["response_body"], "cached": True}
        result = supabase.table("fbr_tbl_products").upsert(
            product, on_conflict="tenant_id,hs_code"
        ).execute()
        complete_operation(op["row"]["id"], 200, result.data or {})
        return {"success": True, "data": result.data}
    except Exception as e:
        fail_operation(op["row"]["id"], str(e))
        raise HTTPException(500, str(e))


@router.delete("/products/{product_id}")
def delete_product(product_id: str, request: Request, tenant_ctx: dict = Depends(get_current_tenant)):
    operation_id = request.headers.get("X-Operation-Id", "")
    op = begin_operation(
        tenant_ctx["tenant_id"],
        operation_id,
        "PRODUCT",
        "DELETE",
        product_id,
    )
    try:
        if op["status"] == "completed":
            return {"success": True, "cached": True}
        supabase.table("fbr_tbl_products").update({"is_active": False}).eq(
            "id", product_id
        ).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
        complete_operation(op["row"]["id"], 200, {"deleted": product_id})
        return {"success": True}
    except Exception as e:
        fail_operation(op["row"]["id"], str(e))
        raise HTTPException(500, str(e))


# ── HS Code lookup ────────────────────────────────────────────────────────────
@router.get("/hs-codes/{code}")
def lookup_hs_code(code: str):
    result = supabase.table("fbr_tbl_hs_codes").select("*").eq("code", code).execute()
    if result.data:
        return result.data[0]
    # Try partial match
    result = supabase.table("fbr_tbl_hs_codes").select("*").ilike(
        "code", f"%{code}%"
    ).limit(5).execute()
    return {"matches": result.data} if result.data else {"description": None}


@router.get("/hs-codes")
def get_hs_codes(q: str = ""):
    if q:
        result = supabase.table("fbr_tbl_hs_codes").select("code,description,tax_rate").or_(
            f"code.ilike.%{q}%,description.ilike.%{q}%"
        ).limit(20).execute()
    else:
        result = supabase.table("fbr_tbl_hs_codes").select(
            "code,description,tax_rate"
        ).limit(50).execute()
    return {"hs_codes": result.data}


# ── Invoice queue management ──────────────────────────────────────────────────

@router.get("/invoices")
def get_queued_invoices(batch_id: str = "", status: str = "", tenant_ctx: dict = Depends(get_current_tenant)):
    """Get all invoices in queue with details for management UI."""
    q = supabase.table("fbr_tbl_invoice_queue").select(
        "id, batch_id, row_number, status, raw_data, invoice_payload, "
        "tracking_no, error_msg, validation_errors, attempts, "
        "created_at, submitted_at, source_type"
    ).eq("tenant_id", tenant_ctx["tenant_id"])

    if batch_id:
        q = q.eq("batch_id", batch_id)
    if status:
        q = q.eq("status", status)

    result = q.order("created_at", desc=True).limit(500).execute()

    # Enrich with readable fields from payload
    invoices = []
    for row in (result.data or []):
        payload = row.get("invoice_payload") or {}
        raw     = row.get("raw_data") or {}
        invoices.append({
            "id":            row["id"],
            "batch_id":      row.get("batch_id",""),
            "row_number":    row.get("row_number",0),
            "status":        row.get("status",""),
            "invoice_date":  payload.get("invoiceDate") or str(raw.get("invoice_date","")),
            "buyer_name":    payload.get("buyerBusinessName") or raw.get("buyer_name",""),
            "buyer_ntn":     payload.get("buyerNTNCNIC") or raw.get("buyer_ntn",""),
            "scenario_id":   payload.get("scenarioId",""),
            "ref_no":        payload.get("invoiceRefNo") or str(raw.get("invoice_ref_no","")),
            "items_count":   len(payload.get("items",[])),
            "tracking_no":   row.get("tracking_no",""),
            "error_msg":     row.get("error_msg",""),
            "warnings":      row.get("validation_errors") or [],
            "attempts":      row.get("attempts",0),
            "created_at":    row.get("created_at",""),
            "submitted_at":  row.get("submitted_at",""),
            # full data for edit dialog
            "payload":       payload,
            "raw_data":      raw,
        })

    # Stats
    all_rows = supabase.table("fbr_tbl_invoice_queue").select("status").eq(
        "tenant_id", tenant_ctx["tenant_id"]
    ).execute()
    counts = {}
    for r in (all_rows.data or []):
        s = r["status"]
        counts[s] = counts.get(s, 0) + 1

    return {"invoices": invoices, "total": len(invoices), "counts": counts}


@router.put("/invoices/{invoice_id}")
def update_queued_invoice(invoice_id: str, data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    """Edit a queued invoice before submission."""
    try:
        # Rebuild payload from updated raw_data if provided
        update = {}
        if "raw_data" in data:
            update["raw_data"] = data["raw_data"]
        if "invoice_payload" in data:
            update["invoice_payload"] = data["invoice_payload"]
        if "status" in data:
            update["status"] = data["status"]

        supabase.table("fbr_tbl_invoice_queue").update(update).eq(
            "id", invoice_id
        ).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/invoices/{invoice_id}")
def delete_queued_invoice(invoice_id: str, tenant_ctx: dict = Depends(get_current_tenant)):
    """Delete a queued invoice."""
    try:
        supabase.table("fbr_tbl_invoice_queue").delete().eq("id", invoice_id).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/invoices/submit-selected")
async def submit_selected_invoices(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    """Submit specific invoices by ID list."""
    ids     = data.get("ids", [])
    results = {"submitted": 0, "failed": 0, "errors": []}

    tenant = supabase.table("fbr_tbl_tenants").select("*").eq(
        "id", tenant_ctx["tenant_id"]
    ).single().execute()

    from services.fbr import post_invoice_to_fbr
    from datetime import datetime

    for inv_id in ids:
        row = supabase.table("fbr_tbl_invoice_queue").select("*").eq(
            "id", inv_id
        ).eq("tenant_id", tenant_ctx["tenant_id"]).single().execute()

        if not row.data:
            continue

        payload  = row.data.get("invoice_payload")
        attempts = row.data.get("attempts", 0) + 1

        supabase.table("fbr_tbl_invoice_queue").update({
            "status": "submitting", "attempts": attempts
        }).eq("id", inv_id).eq("tenant_id", tenant_ctx["tenant_id"]).execute()

        tenant = supabase.table("fbr_tbl_tenants").select("*").eq(
            "id", tenant_ctx["tenant_id"]
        ).single().execute()
        fbr_token = tenant.data.get("fbr_bearer_token", "") if tenant.data else ""
        result = await post_invoice_to_fbr(payload, bearer_token=fbr_token)

        if result["success"]:
            supabase.table("fbr_tbl_invoice_queue").update({
                "status":       "submitted",
                "tracking_no":  result.get("invoice_no"),
                "fbr_response": result["raw"],
                "error_msg":    None,
                "submitted_at": datetime.utcnow().isoformat(),
            }).eq("id", inv_id).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
            results["submitted"] += 1
        else:
            supabase.table("fbr_tbl_invoice_queue").update({
                "status":    "failed",
                "error_msg": result.get("error",""),
            }).eq("id", inv_id).eq("tenant_id", tenant_ctx["tenant_id"]).execute()
            results["failed"] += 1
            results["errors"].append(result.get("error",""))

    return results

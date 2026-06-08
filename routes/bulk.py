from fastapi import APIRouter, UploadFile, File, HTTPException
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

router = APIRouter(prefix="/bulk", tags=["bulk"])

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"


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
async def upload_bulk_file(file: UploadFile = File(...)):
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
        tenant_id=TEST_TENANT_ID,
        parsed=parsed,
    )

    return result


# ── Confirm + submit batch to FBR ─────────────────────────────────────────────
@router.post("/confirm/{batch_id}")
async def confirm_batch(batch_id: str):
    """
    Step 2: User confirmed — submit all valid rows to FBR.
    """
    result = await submit_batch(batch_id, TEST_TENANT_ID)
    return result


# ── Get batch status (for live progress) ─────────────────────────────────────
@router.get("/status/{batch_id}")
def get_batch_status(batch_id: str):
    batch = supabase.table("upload_batches").select("*").eq(
        "id", batch_id
    ).single().execute()

    if not batch.data:
        raise HTTPException(404, "Batch not found")

    # Count by status
    rows = supabase.table("invoice_queue").select(
        "status, tracking_no, error_msg, row_number, validation_errors"
    ).eq("batch_id", batch_id).execute()

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
def get_batches():
    result = supabase.table("upload_batches").select("*").eq(
        "tenant_id", TEST_TENANT_ID
    ).order("created_at", desc=True).limit(20).execute()
    return {"batches": result.data}


# ── Customers CRUD ────────────────────────────────────────────────────────────
@router.get("/customers")
def get_customers():
    result = supabase.table("customers").select("*").eq(
        "tenant_id", TEST_TENANT_ID
    ).eq("is_active", True).order("name").execute()
    return {"customers": result.data}


@router.post("/customers")
def save_customer(customer: dict):
    customer["tenant_id"] = TEST_TENANT_ID
    result = supabase.table("customers").upsert(
        customer, on_conflict="tenant_id,ntn_cnic"
    ).execute()
    return {"success": True, "data": result.data}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):
    supabase.table("customers").update({"is_active": False}).eq(
        "id", customer_id
    ).execute()
    return {"success": True}


# ── Products CRUD ─────────────────────────────────────────────────────────────
@router.get("/products")
def get_products():
    result = supabase.table("products").select("*").eq(
        "tenant_id", TEST_TENANT_ID
    ).eq("is_active", True).order("description").execute()
    return {"products": result.data}


@router.post("/products")
def save_product(product: dict):
    product["tenant_id"] = TEST_TENANT_ID
    result = supabase.table("products").upsert(
        product, on_conflict="tenant_id,hs_code"
    ).execute()
    return {"success": True, "data": result.data}


@router.delete("/products/{product_id}")
def delete_product(product_id: str):
    supabase.table("products").update({"is_active": False}).eq(
        "id", product_id
    ).execute()
    return {"success": True}

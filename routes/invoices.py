from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import StreamingResponse
from io import BytesIO
import uuid
from datetime import datetime

from db.supabase import supabase
from services.excel_parser import parse_excel, generate_excel_template
from services.validator import validate_invoice
from services.fbr import submit_invoice

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ── Download Excel template ───────────────────────────────────────────────────
@router.get("/template")
def download_template():
    """User downloads this, fills it, uploads it back."""
    content = generate_excel_template()
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fbr_invoice_template.xlsx"}
    )


# ── Upload + validate Excel ───────────────────────────────────────────────────
@router.post("/validate")
async def validate_excel_upload(file: UploadFile = File(...)):
    """
    Step 1: Upload Excel → get validation results instantly.
    No FBR call yet. Shows errors before submission.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only .xlsx or .xls files accepted")

    contents = await file.read()
    parsed = parse_excel(contents)

    if not parsed["success"]:
        return {"valid": False, "errors": parsed["errors"], "data": None}

    validation = validate_invoice(parsed["header"], parsed["items"])

    return {
        "valid": validation["valid"],
        "errors": validation["errors"],
        "data": {
            "header": parsed["header"],
            "items": parsed["items"],
            "item_count": len(parsed["items"])
        }
    }


# ── Submit to FBR ─────────────────────────────────────────────────────────────
@router.post("/submit")
async def submit_excel(
    file: UploadFile = File(...),
    tenant_id: str = None,    # from auth middleware in production
    fbr_token: str = None     # from tenant settings in Supabase
):
    """
    Step 2: Parse → validate → save to Supabase → post to FBR.
    Returns tracking numbers per invoice.
    """
    contents = await file.read()
    parsed = parse_excel(contents)

    if not parsed["success"]:
        raise HTTPException(400, {"errors": parsed["errors"]})

    validation = validate_invoice(parsed["header"], parsed["items"])
    if not validation["valid"]:
        raise HTTPException(422, {"errors": validation["errors"]})

    header = parsed["header"]
    items = parsed["items"]

    # Save invoice to Supabase
    invoice_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())

    invoice_row = {
        "id": invoice_id,
        "tenant_id": tenant_id or "test-tenant",
        "batch_id": batch_id,
        "invoice_type": int(header["invoice_type"]),
        "invoice_date": str(header["invoice_date"]),
        "ntn_cnic": str(header["ntn_cnic"]),
        "buyer_seller_name": header["buyer_seller_name"],
        "destination_address": header["destination_address"],
        "sale_type": int(header["sale_type"]),
        "total_retail_price": float(header["total_retail_price"]),
        "total_sales_tax": float(header.get("total_sales_tax") or 0),
        "status": "pending",
        "attempts": 0,
        "created_at": datetime.utcnow().isoformat()
    }

    supabase.table("invoices").insert(invoice_row).execute()

    # Save items
    item_rows = []
    for item in items:
        item_rows.append({
            "id": str(uuid.uuid4()),
            "invoice_id": invoice_id,
            **{k: item.get(k) for k in [
                "hs_code", "product_code", "product_description",
                "rate", "uom", "quantity", "value_excl_st",
                "sales_tax", "retail_price", "total_values",
                "cvt", "fed_payable", "further_tax", "extra_tax",
                "sro_schedule_no", "wh_it_1", "wh_it_2"
            ]}
        })

    if item_rows:
        supabase.table("invoice_items").insert(item_rows).execute()

    # Post to FBR
    fbr_token_to_use = fbr_token or "07eabd29-fb34-3a2a-ab73-1ff4eb282aef"  # sandbox default
    result = await submit_invoice(invoice_id, tenant_id or "test-tenant", fbr_token_to_use)

    return {
        "invoice_id": invoice_id,
        "batch_id": batch_id,
        "success": result["success"] if result else False,
        "tracking_no": result.get("tracking_no") if result else None,
        "error": result.get("error") if result else "Submission failed"
    }


# ── Get invoice status ────────────────────────────────────────────────────────
@router.get("/status/{invoice_id}")
def get_status(invoice_id: str):
    result = supabase.table("invoices").select(
        "id, status, tracking_no, error_msg, attempts, created_at"
    ).eq("id", invoice_id).single().execute()

    if not result.data:
        raise HTTPException(404, "Invoice not found")
    return result.data


# ── Invoice history ───────────────────────────────────────────────────────────
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"

@router.get("/history")
def get_history(limit: int = 50, offset: int = 0):
    result = supabase.table("invoices").select(
        "id, invoice_number, invoice_type, invoice_date, buyer_business_name, "
        "total_retail_price, total_sales_tax, publish_status, status, "
        "tracking_no, attempts, error_msg, created_at"
    ).eq("tenant_id", TEST_TENANT_ID).order(
        "created_at", desc=True
    ).range(offset, offset + limit - 1).execute()

    return {"invoices": result.data, "count": len(result.data)}


# ── Manual retry ──────────────────────────────────────────────────────────────
@router.post("/retry/{invoice_id}")
async def retry_invoice(invoice_id: str):
    inv = supabase.table("invoices").select("*").eq("id", invoice_id).single().execute()
    if not inv.data:
        raise HTTPException(404, "Invoice not found")
    if inv.data["status"] == "submitted":
        raise HTTPException(400, "Invoice already submitted successfully")

    result = await submit_invoice(
        invoice_id,
        inv.data["tenant_id"],
        "07eabd29-fb34-3a2a-ab73-1ff4eb282aef"  # replace with tenant's token
    )
    return result

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from db.supabase import supabase
from services.fbr import post_invoice_to_fbr, build_fbr_payload
from services.pdf_gen import generate_from_invoice_record
import uuid

router = APIRouter(prefix="/sales-invoices", tags=["sales-invoices"])

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"


# ── Models ────────────────────────────────────────────────────────────────────

class InvoiceItem(BaseModel):
    product_id:          Optional[str] = None
    hs_code:             str
    product_code:        Optional[str] = ""
    product_description: str
    uom:                 str    = "KG"
    size:                Optional[str] = ""
    qty:                 float
    rate:                float  = 0      # unit price
    mrp:                 float  = 0
    value_excl_st:       float  = 0
    gst_rate:            float  = 18
    gst_amount:          float  = 0
    further_tax_pct:     float  = 0
    further_tax_amt:     float  = 0
    discount_pct:        float  = 0
    discount_amt:        float  = 0
    fed_payable:         float  = 0
    val_incl_st:         float  = 0
    sale_type:           str    = "Goods at standard rate (default)"
    sro_schedule_no:     str    = ""
    sro_item_serial:     str    = ""


class InvoiceCreate(BaseModel):
    document_date:     str
    customer_id:       Optional[str] = None
    customer_name:     str           = "UNREGISTERED"
    buyer_ntn_cnic:    str           = "0000000"
    buyer_province:    str           = "SINDH"
    buyer_address:     str           = "PAKISTAN"
    buyer_reg_type:    str           = "Unregistered"
    reference_no:      Optional[str] = ""
    dc_no:             Optional[str] = ""
    dc_date:           Optional[str] = ""
    po_number:         Optional[str] = ""
    scenario_id:       Optional[str] = None   # auto-detected if empty
    remarks:           Optional[str] = ""
    items:             List[InvoiceItem]


# ── Helper ────────────────────────────────────────────────────────────────────

def auto_scenario(reg_type: str, items: list) -> str:
    if "unregist" in reg_type.lower():
        return "SN002"
    first_sale = items[0].sale_type if items else ""
    if "exempt" in first_sale.lower():   return "SN006"
    if "zero"   in first_sale.lower():   return "SN007"
    if "3rd"    in first_sale.lower():   return "SN008"
    if "reduced" in first_sale.lower():  return "SN005"
    return "SN001"

def calc_item(item: InvoiceItem) -> InvoiceItem:
    """Auto-calculate all amounts from qty + rate + gst_rate."""
    item.value_excl_st  = round(item.qty * item.rate, 2)
    item.gst_amount     = round(item.value_excl_st * item.gst_rate / 100, 2)
    item.further_tax_amt= round(item.value_excl_st * item.further_tax_pct / 100, 2)
    item.discount_amt   = round(item.value_excl_st * item.discount_pct / 100, 2)
    item.val_incl_st    = round(
        item.value_excl_st + item.gst_amount +
        item.further_tax_amt - item.discount_amt, 2
    )
    return item


# ── Create invoice (Save as Open) ─────────────────────────────────────────────

@router.post("")
def create_invoice(payload: InvoiceCreate):
    tenant = supabase.table("tenants").select("*").eq(
        "id", TEST_TENANT_ID
    ).single().execute().data

    if not tenant:
        raise HTTPException(400, "Tenant not found — check settings")

    # Auto-detect scenario
    scenario_id = payload.scenario_id or auto_scenario(
        payload.buyer_reg_type, payload.items
    )

    # Calculate all items
    items = [calc_item(i) for i in payload.items]

    # Totals
    total_excl  = round(sum(i.value_excl_st   for i in items), 2)
    total_gst   = round(sum(i.gst_amount      for i in items), 2)
    total_ft    = round(sum(i.further_tax_amt for i in items), 2)
    total_disc  = round(sum(i.discount_amt    for i in items), 2)
    total_fed   = round(sum(i.fed_payable     for i in items), 2)
    total_net   = round(sum(i.val_incl_st     for i in items), 2)

    invoice_id = str(uuid.uuid4())

    # Save invoice header
    inv_row = {
        "id":                   invoice_id,
        "tenant_id":            TEST_TENANT_ID,
        "invoice_type":         2,    # Sale Invoice
        "invoice_date":         payload.document_date,
        "buyer_ntn_cnic":       payload.buyer_ntn_cnic,
        "buyer_business_name":  payload.customer_name,
        "buyer_province":       payload.buyer_province,
        "buyer_address":        payload.buyer_address,
        "buyer_registration_type": payload.buyer_reg_type,
        "invoice_ref_no":       payload.reference_no or "",
        "scenario_id":          scenario_id,
        "total_retail_price":   total_net,
        "total_sales_tax":      total_gst,
        "pc_number":            payload.dc_no or "",
        "po_number":            payload.po_number or "",
        "publish_status":       "Open",
        "status":               "pending",
        "attempts":             0,
        "created_at":           datetime.utcnow().isoformat(),
    }
    supabase.table("invoices").insert(inv_row).execute()

    # Save items
    item_rows = []
    for it in items:
        item_rows.append({
            "id":                   str(uuid.uuid4()),
            "invoice_id":           invoice_id,
            "hs_code":              it.hs_code,
            "product_code":         it.product_code or "",
            "product_description":  it.product_description,
            "rate":                 it.rate,
            "uom":                  it.uom,
            "quantity":             it.qty,
            "value_excl_st":        it.value_excl_st,
            "sales_tax":            it.gst_amount,
            "retail_price":         it.mrp or it.val_incl_st,
            "total_values":         it.val_incl_st,
            "further_tax_pct":      it.further_tax_pct,
            "further_tax_amt":      it.further_tax_amt,
            "discount_pct":         it.discount_pct,
            "discount_amt":         it.discount_amt,
            "fed_payable":          it.fed_payable,
            "sale_type":            it.sale_type,
            "sro_schedule_no":      it.sro_schedule_no,
            "sro_item_serial":      it.sro_item_serial,
        })
    if item_rows:
        supabase.table("invoice_items").insert(item_rows).execute()

    # Fetch auto-generated invoice number
    inv = supabase.table("invoices").select("invoice_number").eq(
        "id", invoice_id
    ).single().execute()

    return {
        "success":        True,
        "invoice_id":     invoice_id,
        "invoice_number": inv.data.get("invoice_number",""),
        "scenario_id":    scenario_id,
        "totals": {
            "excl_st":   total_excl,
            "sales_tax": total_gst,
            "further_tax": total_ft,
            "discount":  total_disc,
            "fed":       total_fed,
            "net":       total_net,
        }
    }


# ── Submit to FBR (Open → Closed) ─────────────────────────────────────────────

@router.post("/{invoice_id}/submit")
async def submit_to_fbr(invoice_id: str):
    inv = supabase.table("invoices").select("*").eq(
        "id", invoice_id
    ).single().execute()
    if not inv.data:
        raise HTTPException(404, "Invoice not found")
    if inv.data.get("publish_status") == "Close":
        raise HTTPException(400, "Already submitted to FBR")

    items = supabase.table("invoice_items").select("*").eq(
        "invoice_id", invoice_id
    ).execute()
    tenant = supabase.table("tenants").select("*").eq(
        "id", TEST_TENANT_ID
    ).single().execute()

    seller = {
        "ntn_cnic":      tenant.data["ntn_cnic"],
        "business_name": tenant.data["name"],
        "province":      tenant.data.get("province","SINDH"),
        "address":       tenant.data.get("address","PAKISTAN"),
    }

    payload = build_fbr_payload(inv.data, items.data, seller)
    fbr_token = tenant.data.get("fbr_bearer_token","")
    result = await post_invoice_to_fbr(payload)

    update = {
        "fbr_raw_response": result["raw"],
        "attempts": inv.data.get("attempts",0) + 1,
    }

    if result["success"]:
        update["tracking_no"]    = result.get("invoice_no")
        update["fbr_barcode"]    = result.get("invoice_no")
        update["status"]         = "submitted"
        update["publish_status"] = "Close"
        update["publish_date"]   = datetime.utcnow().isoformat()
        update["error_msg"]      = None
    else:
        update["status"]    = "failed"
        update["error_msg"] = result.get("error","FBR submission failed")

    supabase.table("invoices").update(update).eq("id", invoice_id).execute()

    return {
        "success":    result["success"],
        "tracking_no": result.get("invoice_no"),
        "error":      result.get("error"),
    }


# ── Cancel invoice ────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/cancel")
def cancel_invoice(invoice_id: str):
    inv = supabase.table("invoices").select("publish_status").eq(
        "id", invoice_id
    ).single().execute()
    if not inv.data:
        raise HTTPException(404, "Invoice not found")
    if inv.data.get("publish_status") == "Close":
        raise HTTPException(400, "Cannot cancel — already submitted to FBR")

    supabase.table("invoices").update({
        "publish_status": "Cancel",
        "status":         "cancelled"
    }).eq("id", invoice_id).execute()
    return {"success": True}


# ── Get invoice list ──────────────────────────────────────────────────────────

@router.get("")
def get_invoices(status: str = "", limit: int = 100, offset: int = 0):
    q = supabase.table("invoices").select(
        "id, invoice_number, invoice_date, buyer_business_name, "
        "buyer_ntn_cnic, scenario_id, total_retail_price, total_sales_tax, "
        "publish_status, tracking_no, invoice_ref_no, created_at, attempts, error_msg"
    ).eq("tenant_id", TEST_TENANT_ID).eq("invoice_type", 2)

    if status:
        q = q.eq("publish_status", status)

    result = q.order("created_at", desc=True).range(
        offset, offset + limit - 1
    ).execute()

    # Stats
    all_inv = supabase.table("invoices").select("publish_status").eq(
        "tenant_id", TEST_TENANT_ID
    ).eq("invoice_type", 2).execute()

    stats = {"Open": 0, "Close": 0, "Cancel": 0, "Error": 0}
    for r in (all_inv.data or []):
        s = r.get("publish_status","Open")
        if s in stats:
            stats[s] += 1
        elif r.get("error_msg"):
            stats["Error"] += 1

    return {
        "invoices": result.data,
        "stats":    stats,
        "total":    len(result.data)
    }


# ── Get single invoice ────────────────────────────────────────────────────────

@router.get("/{invoice_id}")
def get_invoice(invoice_id: str):
    inv = supabase.table("invoices").select("*").eq(
        "id", invoice_id
    ).single().execute()
    if not inv.data:
        raise HTTPException(404, "Invoice not found")

    items = supabase.table("invoice_items").select("*").eq(
        "invoice_id", invoice_id
    ).execute()

    return {"invoice": inv.data, "items": items.data}


# ── PDF download ──────────────────────────────────────────────────────────────

@router.get("/{invoice_id}/pdf")
def download_pdf(invoice_id: str):
    inv = supabase.table("invoices").select("*").eq(
        "id", invoice_id
    ).single().execute()
    if not inv.data:
        raise HTTPException(404, "Invoice not found")

    items  = supabase.table("invoice_items").select("*").eq(
        "invoice_id", invoice_id
    ).execute()
    tenant = supabase.table("tenants").select("*").eq(
        "id", TEST_TENANT_ID
    ).single().execute()

    pdf = generate_from_invoice_record(inv.data, items.data, tenant.data)
    inv_no = inv.data.get("invoice_number","invoice")

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={inv_no}.pdf"}
    )


# ── Get products for item lookup ──────────────────────────────────────────────

@router.get("/lookup/products")
def lookup_products(q: str = ""):
    if q:
        result = supabase.table("products").select(
            "id, product_code, description, hs_code, uom, rate, "
            "sales_tax_pct, sale_type, sro_schedule_no, sro_item_serial, "
            "mrp, further_tax_pct, fed_percent"
        ).eq("tenant_id", TEST_TENANT_ID).eq("is_active", True).or_(
            f"description.ilike.%{q}%,hs_code.ilike.%{q}%,product_code.ilike.%{q}%"
        ).limit(20).execute()
    else:
        result = supabase.table("products").select(
            "id, product_code, description, hs_code, uom, rate, "
            "sales_tax_pct, sale_type, sro_schedule_no, sro_item_serial, "
            "mrp, further_tax_pct, fed_percent"
        ).eq("tenant_id", TEST_TENANT_ID).eq("is_active", True).limit(50).execute()
    return {"products": result.data}


# ── Get customers for lookup ──────────────────────────────────────────────────

@router.get("/lookup/customers")
def lookup_customers(q: str = ""):
    if q:
        result = supabase.table("customers").select(
            "id, name, ntn_cnic, registration_status, "
            "province, city, address, further_tax_percent"
        ).eq("tenant_id", TEST_TENANT_ID).eq("is_active", True).or_(
            f"name.ilike.%{q}%,ntn_cnic.ilike.%{q}%"
        ).limit(20).execute()
    else:
        result = supabase.table("customers").select(
            "id, name, ntn_cnic, registration_status, "
            "province, city, address, further_tax_percent"
        ).eq("tenant_id", TEST_TENANT_ID).eq("is_active", True).limit(50).execute()
    return {"customers": result.data}

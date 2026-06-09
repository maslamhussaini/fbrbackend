import uuid
import json
import logging
from datetime import datetime
from typing import Optional
from db.supabase import supabase
from services.fbr import post_invoice_to_fbr

logger = logging.getLogger(__name__)

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# ── Scenario auto-detection ───────────────────────────────────────────────────

def detect_scenario(registration_status: str, sale_type: str = "") -> str:
    """Auto-detect FBR scenario from customer registration status."""
    s = str(registration_status).lower()
    if "unregist" in s:
        return "SN002"
    t = str(sale_type).lower()
    if "exempt" in t:
        return "SN006"
    if "zero" in t:
        return "SN007"
    if "3rd schedule" in t or "third schedule" in t:
        return "SN008"
    if "reduced" in t:
        return "SN005"
    return "SN001"  # default: registered, standard rate


# ── Customer lookup ───────────────────────────────────────────────────────────

def get_customer(tenant_id: str, ntn_or_name: str) -> Optional[dict]:
    """Look up customer by NTN/CNIC or name."""
    result = supabase.table("customers").select("*").eq(
        "tenant_id", tenant_id
    ).eq("ntn_cnic", str(ntn_or_name)).execute()
    if result.data:
        return result.data[0]

    result = supabase.table("customers").select("*").eq(
        "tenant_id", tenant_id
    ).ilike("name", f"%{ntn_or_name}%").execute()
    if result.data:
        return result.data[0]

    # Fallback to UNREGISTERED
    result = supabase.table("customers").select("*").eq(
        "tenant_id", tenant_id
    ).eq("name", "UNREGISTERED").execute()
    return result.data[0] if result.data else None


def get_product(tenant_id: str, hs_code_or_code: str) -> Optional[dict]:
    """Look up product by HS code or product code."""
    result = supabase.table("products").select("*").eq(
        "tenant_id", tenant_id
    ).eq("hs_code", str(hs_code_or_code)).execute()
    if result.data:
        return result.data[0]

    result = supabase.table("products").select("*").eq(
        "tenant_id", tenant_id
    ).eq("product_code", str(hs_code_or_code)).execute()
    return result.data[0] if result.data else None


def get_tenant(tenant_id: str) -> Optional[dict]:
    result = supabase.table("tenants").select("*").eq("id", tenant_id).single().execute()
    return result.data


# ── Build FBR payload from queue row ─────────────────────────────────────────

def build_payload_from_row(row_data: dict, tenant: dict, tenant_id: str) -> tuple[dict, list]:
    """
    Enrich raw row data with customer/product master data.
    Returns (payload, errors).
    """
    errors = []

    # ── Normalize column names — map template headers to internal keys ────────
    ALIASES = {
        "invoice date":           "invoice_date",
        "invoice ref no":         "invoice_ref_no",
        "buyer ntn/cnic":         "buyer_ntn",
        "buyer name":             "buyer_name",
        "buyer province":         "buyer_province",
        "buyer address":          "buyer_address",
        "buyer registration":     "buyer_registration_type",
        "buyer registration type":"buyer_registration_type",
        "hs code":                "hs_code",
        "product description":    "product_description",
        "uom":                    "uom",
        "quantity":               "quantity",
        "value excl st":          "value_excl_st",
        "sales tax":              "sales_tax",
        "rate":                   "rate",
        "sale type":              "sale_type",
        "sro schedule no":        "sro_schedule_no",
        "sro item serial no":     "sro_item_serial",
        "further tax":            "further_tax_amt",
        "retail price":           "retail_price",
    }
    row_data = {ALIASES.get(k, k): v for k, v in row_data.items()}

    # Resolve customer
    buyer_id = row_data.get("buyer_ntn") or row_data.get("buyer_name") or ""
    customer = get_customer(tenant_id, buyer_id)

    if customer:
        reg_status = customer["registration_status"]
        buyer_ntn  = customer["ntn_cnic"] or buyer_id
        buyer_name = customer["name"]
        buyer_prov = customer.get("province", "SINDH")
        buyer_addr = customer.get("address") or customer.get("city", "PAKISTAN")
        further_tax = float(customer.get("further_tax_percent") or 0) / 100
    else:
        reg_status = row_data.get("buyer_registration_type", "Unregistered")
        buyer_ntn  = buyer_id
        buyer_name = row_data.get("buyer_name", "UNREGISTERED")
        buyer_prov = row_data.get("buyer_province", "SINDH")
        buyer_addr = row_data.get("buyer_address", "PAKISTAN")
        further_tax = 0.04 if "unregist" in reg_status.lower() else 0

    # Build items
    items_raw = row_data.get("items", [])
    if not items_raw and row_data.get("hs_code"):
        # Single-item row (flat Excel format)
        items_raw = [row_data]

    built_items = []
    for item in items_raw:
        hs = str(item.get("hs_code") or item.get("hsCode", ""))
        product = get_product(tenant_id, hs) if hs else None

        if product:
            rate       = product["rate"]
            uom        = product["uom"]
            sale_type  = product["sale_type"]
            sro_no     = product.get("sro_schedule_no", "")
            sro_serial = product.get("sro_item_serial", "")
            fed        = float(product.get("fed_percent") or 0)
            mrp        = float(product.get("mrp") or 0)
            tax_pct    = float(product.get("sales_tax_pct") or 18)
        else:
            rate       = str(item.get("rate", "18%"))
            uom        = str(item.get("uom") or item.get("uoM", "KG"))
            sale_type  = item.get("sale_type") or item.get("saleType",
                         "Goods at standard rate (default)")
            sro_no     = str(item.get("sro_schedule_no") or "")
            sro_serial = str(item.get("sro_item_serial") or "")
            fed        = float(item.get("fed_payable") or 0)
            mrp        = float(item.get("retail_price") or
                               item.get("fixedNotifiedValueOrRetailPrice") or 0)
            tax_pct    = 18

        qty          = float(item.get("quantity") or 0)
        value_excl   = float(item.get("value_excl_st") or
                             item.get("valueSalesExcludingST") or 0)
        sales_tax    = round(value_excl * tax_pct / 100, 2)
        total        = round(value_excl + sales_tax, 2)
        ft           = round(value_excl * further_tax, 2) if further_tax else 0

        if not hs:
            errors.append(f"Item missing HS Code")
        elif len(hs.replace(".", "")) != 8:
            errors.append(f"HS Code '{hs}' must be 8 digits")

        built_items.append({
            "hsCode":                          hs,
            "productDescription":              str(item.get("product_description") or
                                                   item.get("productDescription") or
                                                   (product["description"] if product else "")),
            "rate":                            rate,
            "uoM":                             uom,
            "quantity":                        qty,
            "totalValues":                     total,
            "valueSalesExcludingST":           value_excl,
            "fixedNotifiedValueOrRetailPrice": mrp,
            "salesTaxApplicable":              sales_tax,
            "salesTaxWithheldAtSource":        0,
            "extraTax":                        0,
            "furtherTax":                      ft,
            "sroScheduleNo":                   sro_no,
            "fedPayable":                      fed,
            "discount":                        float(item.get("discount") or 0),
            "saleType":                        sale_type,
            "sroItemSerialNo":                 sro_serial,
        })

    if not built_items:
        errors.append("No items found in row")

    # Detect scenario
    first_sale_type = built_items[0]["saleType"] if built_items else ""
    scenario = row_data.get("scenario_id") or detect_scenario(reg_status, first_sale_type)

    payload = {
        "invoiceType":            "Sale Invoice",
        "invoiceDate":            str(row_data.get("invoice_date") or
                                      datetime.today().strftime("%Y-%m-%d")),
        "sellerNTNCNIC":          tenant["ntn_cnic"],
        "sellerBusinessName":     tenant["name"],
        "sellerProvince":         tenant.get("province", "SINDH"),
        "sellerAddress":          tenant.get("address", "PAKISTAN"),
        "buyerNTNCNIC":           buyer_ntn,
        "buyerBusinessName":      buyer_name,
        "buyerProvince":          buyer_prov,
        "buyerAddress":           buyer_addr,
        "buyerRegistrationType":  reg_status,
        "invoiceRefNo":           str(row_data.get("invoice_ref_no") or ""),
        "scenarioId":             scenario,
        "items":                  built_items,
    }

    return payload, errors


# ── Parse Excel bulk file ─────────────────────────────────────────────────────

def parse_bulk_excel(file_bytes: bytes) -> dict:
    results = {"invoices": [], "customers": [], "products": [], "errors": []}

    # Try xlsx first, then xls
    wb = None
    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    except Exception:
        try:
            import xlrd
            xls = xlrd.open_workbook(file_contents=file_bytes)
            wb  = openpyxl.Workbook()
            wb.remove(wb.active)
            for sheet_name in xls.sheet_names():
                xls_ws = xls.sheet_by_name(sheet_name)
                ws = wb.create_sheet(title=sheet_name)
                for row in range(xls_ws.nrows):
                    for col in range(xls_ws.ncols):
                        ws.cell(row=row+1, column=col+1, value=xls_ws.cell(row, col).value)
        except Exception as e:
            results["errors"].append(f"Cannot open file: {str(e)}")
            return results

    if not wb:
        results["errors"].append("Could not open file")
        return results

    def _find_sheet(names: list) -> object:
        """Find sheet by any of the given names (case-insensitive)."""
        for name in names:
            for sname in wb.sheetnames:
                if sname.lower() == name.lower():
                    return wb[sname]
        return None

    def _read_sheet(ws) -> list:
        rows_out = []
        if not ws:
            return rows_out
        headers = [str(c.value or "").strip().lower()
                   for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not any(row):
                continue
            row_data = {headers[i]: row[i]
                        for i in range(len(headers)) if i < len(row)}
            rows_out.append({"row": row_idx, "data": row_data})
        return rows_out

    def _read_sheet_plain(ws) -> list:
        rows_out = []
        if not ws:
            return rows_out
        headers = [str(c.value or "").strip().lower()
                   for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            row_data = {headers[i]: row[i]
                        for i in range(len(headers)) if i < len(row)}
            rows_out.append(row_data)
        return rows_out

    # ── Invoices sheet — accept Sheet1/Invoices/Invoice/Data ─────────────────
    inv_ws = _find_sheet(["Invoices", "Invoice", "Sheet1", "Data", "Sale Sheet",
                          "Sales", "FBR", "Sheet"])
    results["invoices"] = _read_sheet(inv_ws)

    # ── Customers sheet ───────────────────────────────────────────────────────
    cust_ws = _find_sheet(["Customers", "Customer", "Buyers"])
    results["customers"] = _read_sheet_plain(cust_ws)

    # ── Products sheet ────────────────────────────────────────────────────────
    prod_ws = _find_sheet(["Products", "Product", "Items", "Inventory"])
    results["products"] = _read_sheet_plain(prod_ws)

    return results


# ── Parse JSON bulk file ──────────────────────────────────────────────────────

def parse_bulk_json(file_bytes: bytes) -> dict:
    data = json.loads(file_bytes.decode("utf-8"))
    results = {"invoices": [], "customers": [], "products": [], "errors": []}

    if isinstance(data, list):
        # Array of invoices
        for i, item in enumerate(data):
            results["invoices"].append({"row": i + 1, "data": item})
    elif isinstance(data, dict):
        if "invoices" in data:
            for i, item in enumerate(data["invoices"]):
                results["invoices"].append({"row": i + 1, "data": item})
        if "customers" in data:
            results["customers"] = data["customers"]
        if "products" in data:
            results["products"] = data["products"]
        # Single invoice
        if "invoiceDate" in data or "invoice_date" in data:
            results["invoices"].append({"row": 1, "data": data})

    return results


# ── Upsert customers/products from bulk file ──────────────────────────────────

def upsert_customers(customers: list, tenant_id: str) -> int:
    count = 0
    for c in customers:
        if not c.get("name") and not c.get("ntn") and not c.get("ntn_cnic"):
            continue
        row = {
            "tenant_id":           tenant_id,
            "name":                str(c.get("name") or c.get("buyer name") or ""),
            "ntn_cnic":            str(c.get("ntn") or c.get("ntn_cnic") or c.get("ntn/cnic") or ""),
            "registration_status": str(c.get("registration_status") or
                                       c.get("registration status") or "Unregistered"),
            "province":            str(c.get("province") or "SINDH"),
            "city":                str(c.get("city") or ""),
            "address":             str(c.get("address") or ""),
            "wht_percent":         float(c.get("wht_percent") or c.get("wht %") or 0),
            "further_tax_percent": float(c.get("further_tax_percent") or
                                         c.get("further tax %") or 0),
        }
        supabase.table("customers").upsert(row, on_conflict="tenant_id,ntn_cnic").execute()
        count += 1
    return count


def upsert_products(products: list, tenant_id: str) -> int:
    count = 0
    for p in products:
        if not p.get("hs_code") and not p.get("hs code"):
            continue
        row = {
            "tenant_id":       tenant_id,
            "product_code":    str(p.get("product_code") or p.get("product code") or ""),
            "description":     str(p.get("description") or p.get("product description") or ""),
            "hs_code":         str(p.get("hs_code") or p.get("hs code") or ""),
            "uom":             str(p.get("uom") or "KG"),
            "rate":            str(p.get("rate") or "18%"),
            "sales_tax_pct":   float(p.get("sales_tax_pct") or p.get("tax %") or 18),
            "sale_type":       str(p.get("sale_type") or
                                   "Goods at standard rate (default)"),
            "sro_schedule_no": str(p.get("sro_schedule_no") or ""),
            "sro_item_serial": str(p.get("sro_item_serial") or ""),
            "fed_percent":     float(p.get("fed_percent") or 0),
            "mrp":             float(p.get("mrp") or 0),
        }
        supabase.table("products").upsert(row, on_conflict="tenant_id,hs_code").execute()
        count += 1
    return count


# ── Create batch + queue rows ─────────────────────────────────────────────────

def create_batch(filename: str, source_type: str, tenant_id: str,
                 parsed: dict) -> dict:
    """
    Validate all rows, save to queue, return summary.
    Does NOT submit to FBR yet — waits for user confirmation.
    """
    batch_id = str(uuid.uuid4())
    tenant   = get_tenant(tenant_id)

    if not tenant:
        return {"error": "Tenant not found"}

    # Upsert master data first
    cust_count = upsert_customers(parsed.get("customers", []), tenant_id)
    prod_count = upsert_products(parsed.get("products", []), tenant_id)

    valid_rows   = 0
    invalid_rows = 0
    queue_rows   = []
    validation_summary = []

    for entry in parsed.get("invoices", []):
        row_num  = entry["row"]
        row_data = entry["data"]

        payload, errors = build_payload_from_row(row_data, tenant, tenant_id)

        if errors:
            status = "invalid"
            invalid_rows += 1
        else:
            status = "valid"
            valid_rows += 1

        queue_rows.append({
            "id":                str(uuid.uuid4()),
            "tenant_id":         tenant_id,
            "batch_id":          batch_id,
            "row_number":        row_num,
            "source_type":       source_type,
            "raw_data":          row_data,
            "invoice_payload":   payload,
            "status":            status,
            "validation_errors": errors,
            "attempts":          0,
        })

        validation_summary.append({
            "row":    row_num,
            "status": status,
            "errors": errors,
            "buyer":  payload.get("buyerBusinessName", ""),
            "scenario": payload.get("scenarioId", ""),
            "items":  len(payload.get("items", [])),
        })

    # Save batch record
    supabase.table("upload_batches").insert({
        "id":          batch_id,
        "tenant_id":   tenant_id,
        "filename":    filename,
        "source_type": source_type,
        "total_rows":  len(queue_rows),
        "valid_rows":  valid_rows,
        "invalid_rows":invalid_rows,
        "status":      "validated",
    }).execute()

    # Save queue rows in chunks of 50
    for i in range(0, len(queue_rows), 50):
        chunk = queue_rows[i:i+50]
        supabase.table("invoice_queue").insert(chunk).execute()

    return {
        "batch_id":          batch_id,
        "total":             len(queue_rows),
        "valid":             valid_rows,
        "invalid":           invalid_rows,
        "customers_added":   cust_count,
        "products_added":    prod_count,
        "validation_summary": validation_summary,
    }


# ── Submit confirmed batch to FBR ─────────────────────────────────────────────

async def submit_batch(batch_id: str, tenant_id: str) -> dict:
    """
    Submit all valid queued rows to FBR one by one.
    Called after user confirms.
    """
    tenant = get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    fbr_token = tenant.get("fbr_bearer_token", "")

    # Get all valid rows for this batch
    rows = supabase.table("invoice_queue").select("*").eq(
        "batch_id", batch_id
    ).eq("status", "valid").execute()

    if not rows.data:
        return {"error": "No valid rows found", "submitted": 0}

    # Update batch status
    supabase.table("upload_batches").update({
        "status": "processing"
    }).eq("id", batch_id).execute()

    submitted = 0
    failed    = 0

    for row in rows.data:
        # Mark as submitting
        supabase.table("invoice_queue").update({
            "status":   "submitting",
            "attempts": row["attempts"] + 1,
        }).eq("id", row["id"]).execute()

        payload = row["invoice_payload"]
        result  = await post_invoice_to_fbr(payload)

        if result["success"]:
            supabase.table("invoice_queue").update({
                "status":       "submitted",
                "tracking_no":  result.get("invoice_no"),
                "fbr_response": result["raw"],
                "submitted_at": datetime.utcnow().isoformat(),
                "error_msg":    None,
            }).eq("id", row["id"]).execute()
            submitted += 1
        else:
            attempts = row["attempts"] + 1
            supabase.table("invoice_queue").update({
                "status":    "retry" if attempts < 3 else "failed",
                "error_msg": result["error"],
                "fbr_response": result["raw"],
            }).eq("id", row["id"]).execute()
            failed += 1

    # Update batch complete
    final_status = "complete" if failed == 0 else "partial"
    supabase.table("upload_batches").update({
        "status":       final_status,
        "submitted":    submitted,
        "failed":       failed,
        "completed_at": datetime.utcnow().isoformat(),
    }).eq("id", batch_id).execute()

    return {
        "batch_id":  batch_id,
        "submitted": submitted,
        "failed":    failed,
        "status":    final_status,
    }

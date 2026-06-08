import httpx
import logging
from config import settings
from db.supabase import supabase

logger = logging.getLogger(__name__)

# ── Scenario ID reference ─────────────────────────────────────────────────────
# SN001 = Registered buyer, standard rate
# SN002 = Unregistered buyer, standard rate + further tax
# SN005 = Reduced rate (8th schedule)
# SN006 = Exempt goods (6th schedule)
# SN007 = Zero-rated goods
# SN008 = 3rd schedule goods (tax on retail price)
# SN016 = Processing/conversion of goods
# SN017 = Goods FED in ST mode
# SN024 = SRO 297(I)/2023
# SN026 = SN026 specific
# SN027 = 3rd schedule unregistered
# SN028 = Reduced rate unregistered

SCENARIO_MAP = {
    "SN001": "Registered buyer — standard rate 18%",
    "SN002": "Unregistered buyer — standard rate + further tax 4%",
    "SN005": "Reduced rate (8th Schedule)",
    "SN006": "Exempt goods (6th Schedule)",
    "SN007": "Zero-rated goods",
    "SN008": "3rd Schedule goods (tax on retail/fixed price)",
    "SN016": "Processing/conversion of goods",
    "SN017": "Goods FED in ST mode",
    "SN024": "Goods as per SRO.297(I)/2023",
    "SN026": "SN026",
    "SN027": "3rd Schedule goods unregistered",
    "SN028": "Reduced rate unregistered",
}

SALE_TYPE_MAP = {
    "SN001": "Goods at standard rate (default)",
    "SN002": "Goods at standard rate (default)",
    "SN005": "Goods at Reduced Rate",
    "SN006": "Exempt goods",
    "SN007": "Goods at zero-rate",
    "SN008": "3rd Schedule Goods",
    "SN016": "Processing/Conversion of Goods",
    "SN017": "Goods (FED in ST Mode)",
    "SN024": "Goods as per SRO.297(|)/2023",
    "SN026": "Goods at standard rate (default)",
    "SN027": "3rd Schedule Goods",
    "SN028": "Goods at Reduced Rate",
}


# ── FBR API call ──────────────────────────────────────────────────────────────

async def post_invoice_to_fbr(invoice_payload: dict, use_validate: bool = False) -> dict:
    """
    Post invoice to FBR API.
    use_validate=True hits the validate endpoint (no actual submission).
    Returns: { success: bool, invoice_no: str|None, error: str|None, raw: dict }
    """
    url = settings.FBR_VALIDATE_URL if use_validate else settings.FBR_URL

    headers = {
        "Authorization": f"Bearer {settings.FBR_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(url, json=invoice_payload, headers=headers)

        data = response.json()
        logger.info(f"FBR response: {data}")

        # FBR returns statusCode "00" for success (string, not int)
        validation = data.get("validationResponse", {})
        status_code = str(validation.get("statusCode", ""))
        status = validation.get("status", "")

        if status_code == "00" and status == "Valid":
            return {
                "success": True,
                "invoice_no": data.get("invoiceNumber") or data.get("dated"),
                "error": None,
                "raw": data
            }
        else:
            error_msg = validation.get("error") or "FBR validation failed"
            # Collect item-level errors too
            item_errors = []
            for item in validation.get("invoiceStatuses", []):
                if item.get("statusCode") != "00":
                    item_errors.append(f"Item {item['itemSNo']}: {item.get('error')}")
            if item_errors:
                error_msg += " | " + " | ".join(item_errors)

            return {
                "success": False,
                "invoice_no": None,
                "error": error_msg,
                "raw": data
            }

    except httpx.TimeoutException:
        return {"success": False, "invoice_no": None,
                "error": "FBR API timeout — will retry", "raw": {}}
    except Exception as e:
        logger.error(f"FBR call failed: {e}")
        return {"success": False, "invoice_no": None, "error": str(e), "raw": {}}


# ── Build FBR payload ─────────────────────────────────────────────────────────

def build_fbr_payload(invoice: dict, items: list, seller: dict) -> dict:
    """
    Build the exact JSON structure FBR expects.
    seller dict comes from tenant settings in Supabase.
    """
    scenario_id = invoice.get("scenario_id", "SN001")

    return {
        "invoiceType": "Sale Invoice",
        "invoiceDate": str(invoice["invoice_date"]),
        "sellerNTNCNIC": seller["ntn_cnic"],
        "sellerBusinessName": seller["business_name"],
        "sellerProvince": seller["province"],
        "sellerAddress": seller["address"],
        "buyerNTNCNIC": invoice["buyer_ntn_cnic"],
        "buyerBusinessName": invoice["buyer_business_name"],
        "buyerProvince": invoice.get("buyer_province", ""),
        "buyerAddress": invoice["buyer_address"],
        "buyerRegistrationType": invoice["buyer_registration_type"],  # "Registered" | "Unregistered"
        "invoiceRefNo": invoice.get("invoice_ref_no", ""),
        "scenarioId": scenario_id,
        "items": [build_item_payload(i, scenario_id) for i in items]
    }


def build_item_payload(item: dict, scenario_id: str) -> dict:
    is_exempt = scenario_id == "SN006"
    is_3rd_schedule = scenario_id in ("SN008", "SN027")

    return {
        "hsCode": item["hs_code"],
        "productDescription": item["product_description"],
        "rate": "Exempt" if is_exempt else str(item["rate"]),  # e.g. "18%", "0%", "Exempt"
        "uoM": item["uom"],                                     # string e.g. "KG", "Pieces"
        "quantity": float(item["quantity"]),
        "totalValues": float(item.get("total_values") or 0),
        "valueSalesExcludingST": float(item["value_excl_st"]),
        "fixedNotifiedValueOrRetailPrice": float(item.get("retail_price") or 0),
        "salesTaxApplicable": float(item["sales_tax"]),
        "salesTaxWithheldAtSource": float(item.get("st_withheld") or 0),
        "extraTax": item.get("extra_tax") or 0,
        "furtherTax": float(item.get("further_tax") or 0),
        "sroScheduleNo": item.get("sro_schedule_no") or "",
        "fedPayable": float(item.get("fed_payable") or 0),
        "discount": float(item.get("discount") or 0),
        "saleType": item.get("sale_type") or SALE_TYPE_MAP.get(scenario_id, "Goods at standard rate (default)"),
        "sroItemSerialNo": item.get("sro_item_serial_no") or ""
    }


# ── Submit invoice ────────────────────────────────────────────────────────────

async def submit_invoice(invoice_id: str, validate_only: bool = False):
    """
    Fetch invoice from Supabase, post to FBR, update status.
    """
    inv = supabase.table("invoices").select("*").eq("id", invoice_id).single().execute()
    items = supabase.table("invoice_items").select("*").eq("invoice_id", invoice_id).execute()
    tenant = supabase.table("tenants").select("*").eq("id", inv.data["tenant_id"]).single().execute()

    if not inv.data:
        logger.error(f"Invoice {invoice_id} not found")
        return None

    seller = {
        "ntn_cnic": tenant.data["ntn_cnic"],
        "business_name": tenant.data["name"],
        "province": tenant.data.get("province", ""),
        "address": tenant.data.get("address", ""),
    }

    payload = build_fbr_payload(inv.data, items.data, seller)
    result = await post_invoice_to_fbr(payload, use_validate=validate_only)

    if not validate_only:
        update = {
            "fbr_raw_response": result["raw"],
            "attempts": inv.data["attempts"] + 1,
        }
        if result["success"]:
            update["status"] = "submitted"
            update["tracking_no"] = result.get("invoice_no")
            update["error_msg"] = None
        else:
            attempts = inv.data["attempts"] + 1
            update["status"] = "retry" if attempts < 3 else "failed"
            update["error_msg"] = result["error"]

        supabase.table("invoices").update(update).eq("id", invoice_id).execute()

    return result

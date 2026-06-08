from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.supabase import supabase
from config import settings as app_settings
import httpx

router = APIRouter(prefix="/settings", tags=["settings"])

# Test tenant ID — replace with real auth in production
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class SettingsPayload(BaseModel):
    name:             str
    ntn_cnic:         str
    province:         str = ""
    address:          str = ""
    fbr_bearer_token: str = ""
    use_sandbox:      bool = True


class TokenTestPayload(BaseModel):
    token: str


# ── Get current settings ──────────────────────────────────────────────────────
@router.get("")
def get_settings():
    try:
        result = supabase.table("tenants").select(
            "id, name, ntn_cnic, province, address, fbr_bearer_token, plan"
        ).eq("id", TEST_TENANT_ID).single().execute()

        if not result.data:
            return {"success": False, "data": None}

        # Add use_sandbox flag from app config
        data = result.data
        data["use_sandbox"] = app_settings.FBR_USE_SANDBOX

        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


# ── Save settings ─────────────────────────────────────────────────────────────
@router.post("")
def save_settings(payload: SettingsPayload):
    try:
        update = {
            "name":             payload.name,
            "ntn_cnic":         payload.ntn_cnic,
            "province":         payload.province,
            "address":          payload.address,
            "fbr_bearer_token": payload.fbr_bearer_token,
        }

        # Update in Supabase
        result = supabase.table("tenants").update(update).eq(
            "id", TEST_TENANT_ID
        ).execute()

        if not result.data:
            # Tenant doesn't exist yet — insert it
            insert = {**update, "id": TEST_TENANT_ID, "plan": "starter"}
            supabase.table("tenants").insert(insert).execute()

        # Also update the .env file for the backend
        _update_env_file(payload.fbr_bearer_token, payload.use_sandbox)

        return {"success": True, "message": "Settings saved"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Test FBR token ────────────────────────────────────────────────────────────
@router.post("/test-token")
async def test_token(payload: TokenTestPayload):
    """
    Hit FBR validate endpoint with a minimal test payload.
    Returns valid=True if FBR accepts the token.
    """
    test_payload = {
        "invoiceType": "Sale Invoice",
        "invoiceDate": "2025-07-12",
        "sellerNTNCNIC": "4250124272389",
        "sellerBusinessName": "TEST",
        "sellerProvince": "SINDH",
        "sellerAddress": "KARACHI",
        "buyerNTNCNIC": "8352312-6",
        "buyerBusinessName": "TEST BUYER",
        "buyerProvince": "SINDH",
        "buyerAddress": "KARACHI",
        "buyerRegistrationType": "Registered",
        "invoiceRefNo": "TEST-001",
        "scenarioId": "SN001",
        "items": [{
            "hsCode": "3923.9090",
            "productDescription": "Test",
            "rate": "18%",
            "uoM": "KG",
            "quantity": 1,
            "totalValues": 0,
            "valueSalesExcludingST": 1,
            "fixedNotifiedValueOrRetailPrice": 0,
            "salesTaxApplicable": 0.18,
            "salesTaxWithheldAtSource": 0,
            "extraTax": 0,
            "furtherTax": 0,
            "sroScheduleNo": "",
            "fedPayable": 0,
            "discount": 0,
            "saleType": "Goods at standard rate (default)",
            "sroItemSerialNo": ""
        }]
    }

    headers = {
        "Authorization": f"Bearer {payload.token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            r = await client.post(
                app_settings.FBR_VALIDATE_URL,
                json=test_payload,
                headers=headers
            )
        data = r.json()

        # Check for credential error
        if "fault" in data:
            fault = data["fault"]
            return {
                "valid": False,
                "error": fault.get("message", "Invalid credentials")
            }

        status = data.get("validationResponse", {}).get("statusCode")
        if status == "00":
            return {"valid": True}
        else:
            error = data.get("validationResponse", {}).get("error", "Validation failed")
            return {"valid": False, "error": error}

    except Exception as e:
        return {"valid": False, "error": str(e)}


# ── Helper: update .env file ──────────────────────────────────────────────────
def _update_env_file(token: str, use_sandbox: bool):
    """Update backend .env with new token and sandbox setting."""
    env_path = ".env"
    lines = []

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        pass

    def set_or_add(lines, key, value):
        key_found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                new_lines.append(line)
        if not key_found:
            new_lines.append(f"{key}={value}\n")
        return new_lines

    lines = set_or_add(lines, "FBR_BEARER_TOKEN", token)
    lines = set_or_add(lines, "FBR_USE_SANDBOX", str(use_sandbox))

    with open(env_path, "w") as f:
        f.writelines(lines)

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from db.supabase import supabase

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class AuthPayload(BaseModel):
    email:    str
    password: str


class OTPPayload(BaseModel):
    email: str
    token: str


class OnboardingPayload(BaseModel):
    business_name: str
    ntn_cnic: str | None = None
    province: str
    address: str
    tax_registration_type: str


# ── Auth dependencies ──────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        user = supabase.auth.get_user(credentials.credentials)
        return {"id": str(user.user.id), "email": user.user.email}
    except Exception as e:
        raise HTTPException(401, "Invalid token") from e


async def get_current_tenant(current_user: dict = Depends(get_current_user)) -> dict:
    profile = supabase.table("fbr_tbl_user_profiles").select("tenant_id, role").eq(
        "id", current_user["id"]
    ).single().execute()

    if not profile.data:
        raise HTTPException(403, "User profile not found")

    tenant_id = profile.data.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "Tenant not assigned")

    return {"user_id": current_user["id"], "tenant_id": tenant_id, "role": profile.data.get("role")}


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login")
def login(payload: AuthPayload):
    try:
        result = supabase.auth.sign_in_with_password({
            "email":    payload.email,
            "password": payload.password
        })
        if not result.session:
            return {"success": False, "error": "Invalid email or password"}

        user = result.user
        profile = supabase.table("fbr_tbl_user_profiles").select("role, tenant_id").eq(
            "id", str(user.id)
        ).single().execute()

        role = "user"
        if profile.data:
            role = profile.data.get("role", "user")

        return {
            "success": True,
            "token":   result.session.access_token,
            "email":   user.email,
            "role":    role,
            "user_id": str(user.id)
        }
    except Exception as e:
        msg = str(e)
        if "Invalid login" in msg or "invalid_grant" in msg.lower():
            return {"success": False, "error": "Invalid email or password"}
        return {"success": False, "error": msg}


# ── Sign up ───────────────────────────────────────────────────────────────────
@router.post("/signup")
def signup(payload: AuthPayload):
    try:
        result = supabase.auth.sign_up({
            "email":    payload.email,
            "password": payload.password
        })
        if result.user:
            return {
                "success": True,
                "message": "Check your email for the confirmation code",
                "email":   payload.email
            }
        return {"success": False, "error": "Signup failed"}
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower():
            return {"success": False, "error": "Email already registered — sign in instead"}
        return {"success": False, "error": msg}


# ── Verify OTP ────────────────────────────────────────────────────────────────
@router.post("/verify-otp")
def verify_otp(payload: OTPPayload):
    try:
        result = supabase.auth.verify_otp({
            "email": payload.email,
            "token": payload.token,
            "type":  "signup"
        })
        if not result.session:
            return {"success": False, "error": "Invalid or expired code"}

        user = result.user

        # Create user profile with default role
        existing = supabase.table("fbr_tbl_user_profiles").select("id").eq(
            "id", str(user.id)
        ).execute()

        if not existing.data:
            supabase.table("fbr_tbl_user_profiles").insert({
                "id":        str(user.id),
                "role":      "user",
                "full_name": payload.email.split("@")[0]
            }).execute()

        return {
            "success": True,
            "token":   result.session.access_token,
            "email":   user.email,
            "role":    "user",
            "user_id": str(user.id)
        }
    except Exception as e:
        return {"success": False, "error": "Invalid or expired code"}


# ── Onboarding ───────────────────────────────────────────────────────────────
ALLOWED_TAX_TYPES = {"sales_tax_registered", "not_sales_tax_registered"}


@router.post("/onboarding")
def onboarding(payload: OnboardingPayload, current_user: dict = Depends(get_current_user)):
    try:
        business_name = payload.business_name.strip()
        province = payload.province.strip()
        address = payload.address.strip()
        tax_type = payload.tax_registration_type.strip()

        if not business_name:
            raise HTTPException(400, "business_name is required")
        if not province:
            raise HTTPException(400, "province is required")
        if not address:
            raise HTTPException(400, "address is required")
        if tax_type not in ALLOWED_TAX_TYPES:
            raise HTTPException(400, "tax_registration_type must be sales_tax_registered or not_sales_tax_registered")

        profile = supabase.table("fbr_tbl_user_profiles").select("tenant_id").eq(
            "id", current_user["id"]
        ).single().execute()

        tenant_id = profile.data.get("tenant_id") if profile.data else None

        if tenant_id:
            existing = supabase.table("fbr_tbl_tenants").select("*").eq(
                "id", tenant_id
            ).single().execute()
            if not existing.data:
                tenant_id = None
            else:
                update = {
                    "name":                  business_name,
                    "ntn_cnic":              payload.ntn_cnic,
                    "province":              province,
                    "address":               address,
                    "tax_registration_type": tax_type,
                }
                supabase.table("fbr_tbl_tenants").update(update).eq("id", tenant_id).execute()
                return {
                    "success": True,
                    "tenant_id": tenant_id,
                    "tax_registration_type": tax_type,
                    "message": "Company details updated",
                }

        if not tenant_id:
            new_tenant = supabase.table("fbr_tbl_tenants").insert({
                "name":                  business_name,
                "ntn_cnic":              payload.ntn_cnic,
                "province":              province,
                "address":               address,
                "tax_registration_type": tax_type,
                "plan":                  "starter",
            }).execute()
            tenant_id = new_tenant.data[0]["id"]

            supabase.table("fbr_tbl_user_profiles").update({
                "tenant_id": tenant_id,
            }).eq("id", current_user["id"]).execute()

        return {
            "success": True,
            "tenant_id": tenant_id,
            "tax_registration_type": tax_type,
            "message": "Onboarding complete",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Onboarding failed: {e}")


# ── Get current user ──────────────────────────────────────────────────────────
@router.get("/me")
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        user = supabase.auth.get_user(credentials.credentials)
        profile = supabase.table("fbr_tbl_user_profiles").select("role, tenant_id").eq(
            "id", str(user.user.id)
        ).single().execute()

        tenant_id = profile.data.get("tenant_id") if profile.data else None
        onboarding_required = True
        tax_registration_type = None

        if tenant_id:
            tenant = supabase.table("fbr_tbl_tenants").select("tax_registration_type").eq(
                "id", tenant_id
            ).single().execute()
            if tenant.data and tenant.data.get("tax_registration_type"):
                onboarding_required = False
                tax_registration_type = tenant.data["tax_registration_type"]

        return {
            "email":                  user.user.email,
            "role":                   profile.data.get("role", "user") if profile.data else "user",
            "user_id":                str(user.user.id),
            "tenant_id":              tenant_id,
            "onboarding_required":    onboarding_required,
            "tax_registration_type":  tax_registration_type,
        }
    except Exception as e:
        raise HTTPException(401, "Invalid token")

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
        profile = supabase.table("user_profiles").select("role, tenant_id").eq(
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
        existing = supabase.table("user_profiles").select("id").eq(
            "id", str(user.id)
        ).execute()

        if not existing.data:
            supabase.table("user_profiles").insert({
                "id":        str(user.id),
                "tenant_id": "00000000-0000-0000-0000-000000000001",
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


# ── Get current user ──────────────────────────────────────────────────────────
@router.get("/me")
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        user = supabase.auth.get_user(credentials.credentials)
        profile = supabase.table("user_profiles").select("role, tenant_id").eq(
            "id", str(user.user.id)
        ).single().execute()
        return {
            "email":   user.user.email,
            "role":    profile.data.get("role", "user") if profile.data else "user",
            "user_id": str(user.user.id)
        }
    except Exception as e:
        raise HTTPException(401, "Invalid token")

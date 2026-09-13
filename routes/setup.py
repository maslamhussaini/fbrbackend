from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from db.supabase import supabase
from routes.auth import get_current_tenant

router = APIRouter(prefix="/setup", tags=["setup"])


# ── HS Codes ──────────────────────────────────────────────────────────────────

@router.get("/hs-codes")
def get_hs_codes(q: str = "", limit: int = 100, tenant_ctx: dict = Depends(get_current_tenant)):
    if q:
        result = supabase.table("fbr_tbl_hs_codes").select("*").or_(
            f"code.ilike.%{q}%,description.ilike.%{q}%"
        ).limit(limit).execute()
    else:
        result = supabase.table("fbr_tbl_hs_codes").select("*").order(
            "code"
        ).limit(limit).execute()
    return {"hs_codes": result.data}


@router.post("/hs-codes")
def save_hs_code(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        if data.get("id"):
            supabase.table("fbr_tbl_hs_codes").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("fbr_tbl_hs_codes").upsert(
                data, on_conflict="code"
            ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/hs-codes/bulk")
def import_hs_codes(codes: List[dict], tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        if not codes:
            return {"success": False, "error": "No codes provided"}
        supabase.table("fbr_tbl_hs_codes").upsert(
            codes, on_conflict="code"
        ).execute()
        return {"success": True, "count": len(codes)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/hs-codes/{code}")
def lookup_hs_code(code: str, tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_hs_codes").select("*").eq("code", code).execute()
    if result.data:
        return result.data[0]
    result = supabase.table("fbr_tbl_hs_codes").select("*").ilike(
        "code", f"%{code}%"
    ).limit(5).execute()
    return {"matches": result.data} if result.data else {"description": None}


# ── Units ─────────────────────────────────────────────────────────────────────

@router.get("/units")
def get_units(tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_uom_master").select("*").order("code").execute()
    return {"units": result.data}


@router.post("/units")
def save_unit(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        supabase.table("fbr_tbl_uom_master").upsert(
            data, on_conflict="code"
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/units/{code}")
def delete_unit(code: str, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        supabase.table("fbr_tbl_uom_master").delete().eq("code", code).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Provinces ─────────────────────────────────────────────────────────────────

@router.get("/provinces")
def get_provinces(tenant_ctx: dict = Depends(get_current_tenant)):
    result = supabase.table("fbr_tbl_provinces").select("*").order("name").execute()
    return {"provinces": result.data}


@router.post("/provinces")
def save_province(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        supabase.table("fbr_tbl_provinces").upsert(
            data, on_conflict="code"
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Cities ────────────────────────────────────────────────────────────────────

@router.get("/cities")
def get_cities(province_code: str = "", tenant_ctx: dict = Depends(get_current_tenant)):
    q = supabase.table("fbr_tbl_cities").select("*")
    if province_code:
        q = q.eq("province_code", province_code)
    result = q.order("name").execute()
    return {"cities": result.data}


@router.post("/cities")
def save_city(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        if data.get("id"):
            supabase.table("fbr_tbl_cities").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("fbr_tbl_cities").insert(data).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/cities/{city_id}")
def delete_city(city_id: str, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        supabase.table("fbr_tbl_cities").delete().eq("id", city_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tax schedules ─────────────────────────────────────────────────────────────

@router.get("/tax-schedules")
def get_tax_schedules(schedule_type: str = "", tenant_ctx: dict = Depends(get_current_tenant)):
    q = supabase.table("fbr_tbl_tax_schedules").select("*")
    if schedule_type:
        q = q.eq("schedule_type", schedule_type)
    result = q.order("code").execute()
    return {"tax_schedules": result.data}


# ── Areas ─────────────────────────────────────────────────────────────────────

@router.get("/areas")
def get_areas(city_id: str = "", tenant_ctx: dict = Depends(get_current_tenant)):
    q = supabase.table("areas").select(
        "id, name, city_id, is_active, cities(name, province_code)"
    ).eq("is_active", True)
    if city_id:
        q = q.eq("city_id", city_id)
    result = q.order("name").execute()
    return {"areas": result.data}


@router.post("/areas")
def save_area(data: dict, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        if data.get("id"):
            supabase.table("areas").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("areas").insert(data).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/areas/{area_id}")
def delete_area(area_id: str, tenant_ctx: dict = Depends(get_current_tenant)):
    try:
        supabase.table("areas").update(
            {"is_active": False}
        ).eq("id", area_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

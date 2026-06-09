from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from db.supabase import supabase

router = APIRouter(prefix="/setup", tags=["setup"])


# ── HS Codes ──────────────────────────────────────────────────────────────────

@router.get("/hs-codes")
def get_hs_codes(q: str = "", limit: int = 100):
    if q:
        result = supabase.table("hs_codes").select("*").or_(
            f"code.ilike.%{q}%,description.ilike.%{q}%"
        ).limit(limit).execute()
    else:
        result = supabase.table("hs_codes").select("*").order(
            "code"
        ).limit(limit).execute()
    return {"hs_codes": result.data}


@router.post("/hs-codes")
def save_hs_code(data: dict):
    try:
        if data.get("id"):
            supabase.table("hs_codes").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("hs_codes").upsert(
                data, on_conflict="code"
            ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/hs-codes/bulk")
def import_hs_codes(codes: List[dict]):
    try:
        if not codes:
            return {"success": False, "error": "No codes provided"}
        supabase.table("hs_codes").upsert(
            codes, on_conflict="code"
        ).execute()
        return {"success": True, "count": len(codes)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/hs-codes/{code}")
def lookup_hs_code(code: str):
    result = supabase.table("hs_codes").select("*").eq("code", code).execute()
    if result.data:
        return result.data[0]
    result = supabase.table("hs_codes").select("*").ilike(
        "code", f"%{code}%"
    ).limit(5).execute()
    return {"matches": result.data} if result.data else {"description": None}


# ── Units ─────────────────────────────────────────────────────────────────────

@router.get("/units")
def get_units():
    result = supabase.table("uom_master").select("*").order("code").execute()
    return {"units": result.data}


@router.post("/units")
def save_unit(data: dict):
    try:
        supabase.table("uom_master").upsert(
            data, on_conflict="code"
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/units/{code}")
def delete_unit(code: str):
    try:
        supabase.table("uom_master").delete().eq("code", code).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Provinces ─────────────────────────────────────────────────────────────────

@router.get("/provinces")
def get_provinces():
    result = supabase.table("provinces").select("*").order("name").execute()
    return {"provinces": result.data}


@router.post("/provinces")
def save_province(data: dict):
    try:
        supabase.table("provinces").upsert(
            data, on_conflict="code"
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Cities ────────────────────────────────────────────────────────────────────

@router.get("/cities")
def get_cities(province_code: str = ""):
    q = supabase.table("cities").select("*")
    if province_code:
        q = q.eq("province_code", province_code)
    result = q.order("name").execute()
    return {"cities": result.data}


@router.post("/cities")
def save_city(data: dict):
    try:
        if data.get("id"):
            supabase.table("cities").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("cities").insert(data).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/cities/{city_id}")
def delete_city(city_id: str):
    try:
        supabase.table("cities").delete().eq("id", city_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tax schedules ─────────────────────────────────────────────────────────────

@router.get("/tax-schedules")
def get_tax_schedules(schedule_type: str = ""):
    q = supabase.table("tax_schedules").select("*")
    if schedule_type:
        q = q.eq("schedule_type", schedule_type)
    result = q.order("code").execute()
    return {"tax_schedules": result.data}


# ── Areas ─────────────────────────────────────────────────────────────────────

@router.get("/areas")
def get_areas(city_id: str = ""):
    q = supabase.table("areas").select(
        "id, name, city_id, is_active, cities(name, province_code)"
    ).eq("is_active", True)
    if city_id:
        q = q.eq("city_id", city_id)
    result = q.order("name").execute()
    return {"areas": result.data}


@router.post("/areas")
def save_area(data: dict):
    try:
        if data.get("id"):
            supabase.table("areas").update(data).eq("id", data["id"]).execute()
        else:
            supabase.table("areas").insert(data).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/areas/{area_id}")
def delete_area(area_id: str):
    try:
        supabase.table("areas").update(
            {"is_active": False}
        ).eq("id", area_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

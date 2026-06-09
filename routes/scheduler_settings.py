from fastapi import APIRouter
from pydantic import BaseModel
from db.supabase import supabase
from services.scheduler import get_settings, save_setting, reload_scheduler_jobs, scheduler

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class SettingUpdate(BaseModel):
    key:   str
    value: str


@router.get("/settings")
def get_scheduler_settings():
    """Get all scheduler settings with current values."""
    try:
        rows = supabase.table("scheduler_settings").select("*").execute()
        return {
            "settings": rows.data,
            "active":   get_settings(),
            "running":  scheduler.running,
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/settings")
async def update_scheduler_setting(payload: SettingUpdate):
    """Update a single setting and reload scheduler jobs."""
    try:
        save_setting(payload.key, payload.value)
        # Reload jobs with new intervals
        if scheduler.running:
            await reload_scheduler_jobs()
        return {"success": True, "key": payload.key, "value": payload.value}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/settings/bulk")
async def update_all_settings(settings: dict):
    """Update multiple settings at once."""
    try:
        for key, value in settings.items():
            save_setting(key, str(value))
        if scheduler.running:
            await reload_scheduler_jobs()
        return {"success": True, "updated": list(settings.keys())}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/status")
def scheduler_status():
    """Current scheduler status and job info."""
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id":       job.id,
                "name":     job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
    return {
        "running": scheduler.running,
        "jobs":    jobs,
        "config":  get_settings(),
    }


@router.post("/toggle")
async def toggle_auto_process():
    """Enable or disable auto processing."""
    cfg = get_settings()
    new_val = not cfg["auto_process"]
    save_setting("auto_process", str(new_val).lower())
    return {"success": True, "auto_process": new_val}

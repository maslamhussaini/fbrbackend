"""
Background job scheduler — all timing parameters loaded from DB.
Admin can change them in scheduler_settings table without redeploying.
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval  import IntervalTrigger
from db.supabase import supabase

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

# ── Defaults (used if DB read fails) ─────────────────────────────────────────
DEFAULTS = {
    "process_queue_seconds":  30,
    "retry_interval_minutes": 5,
    "health_check_minutes":   10,
    "max_attempts":           3,
    "batch_size":             10,
    "auto_process":           True,
}


def get_settings() -> dict:
    """Load scheduler settings from DB. Falls back to defaults on error."""
    try:
        rows = supabase.table("scheduler_settings").select("key,value").execute()
        cfg = dict(DEFAULTS)
        for row in (rows.data or []):
            k, v = row["key"], row["value"]
            if k in ("auto_process",):
                cfg[k] = str(v).lower() == "true"
            elif k in cfg:
                cfg[k] = type(DEFAULTS[k])(v)
        return cfg
    except Exception as e:
        logger.warning(f"[Scheduler] Could not load settings from DB: {e} — using defaults")
        return dict(DEFAULTS)


def save_setting(key: str, value: str):
    """Update a single scheduler setting in DB."""
    supabase.table("scheduler_settings").update({
        "value":      str(value),
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("key", key).execute()


# ── Core submit function ──────────────────────────────────────────────────────

async def _submit_queue_row(row: dict, max_attempts: int):
    from services.fbr import post_invoice_to_fbr

    row_id   = row["id"]
    attempts = row.get("attempts", 0) + 1

    supabase.table("invoice_queue").update({
        "status":   "submitting",
        "attempts": attempts,
    }).eq("id", row_id).execute()

    try:
        payload = row.get("invoice_payload")
        if not payload:
            supabase.table("invoice_queue").update({
                "status":    "invalid",
                "error_msg": "No invoice payload found",
            }).eq("id", row_id).execute()
            return

        result = await post_invoice_to_fbr(payload)

        if result["success"]:
            supabase.table("invoice_queue").update({
                "status":       "submitted",
                "tracking_no":  result.get("invoice_no"),
                "fbr_response": result["raw"],
                "error_msg":    None,
                "submitted_at": datetime.utcnow().isoformat(),
            }).eq("id", row_id).execute()
            logger.info(f"[Scheduler] ✓ Row {row_id[:8]} → FBR #{result.get('invoice_no','')}")
        else:
            new_status = "retry" if attempts < max_attempts else "failed"
            supabase.table("invoice_queue").update({
                "status":       new_status,
                "error_msg":    result.get("error","FBR error"),
                "fbr_response": result.get("raw",{}),
            }).eq("id", row_id).execute()
            logger.warning(f"[Scheduler] ✗ Row {row_id[:8]} ({attempts}/{max_attempts}): {result.get('error','')}")

    except Exception as e:
        new_status = "retry" if attempts < max_attempts else "failed"
        supabase.table("invoice_queue").update({
            "status":    new_status,
            "error_msg": str(e),
        }).eq("id", row_id).execute()
        logger.error(f"[Scheduler] Exception on row {row_id[:8]}: {e}")


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def process_pending_queue():
    cfg = get_settings()
    if not cfg["auto_process"]:
        logger.info("[Scheduler] Auto-process disabled — skipping")
        return

    batch_size   = cfg["batch_size"]
    max_attempts = cfg["max_attempts"]

    try:
        rows = supabase.table("invoice_queue").select("*").eq(
            "status", "queued"
        ).limit(batch_size).execute()

        if not rows.data:
            return

        logger.info(f"[Scheduler] Processing {len(rows.data)} queued invoices")
        for row in rows.data:
            await _submit_queue_row(row, max_attempts)

    except Exception as e:
        logger.error(f"[Scheduler] process_pending_queue: {e}")


async def retry_failed_invoices():
    cfg = get_settings()
    if not cfg["auto_process"]:
        return

    batch_size   = cfg["batch_size"]
    max_attempts = cfg["max_attempts"]

    try:
        rows = supabase.table("invoice_queue").select("*").eq(
            "status", "retry"
        ).lt("attempts", max_attempts).limit(batch_size).execute()

        if not rows.data:
            return

        logger.info(f"[Scheduler] Retrying {len(rows.data)} failed invoices")
        for row in rows.data:
            await _submit_queue_row(row, max_attempts)

    except Exception as e:
        logger.error(f"[Scheduler] retry_failed_invoices: {e}")


async def health_check():
    cfg = get_settings()
    max_attempts = cfg["max_attempts"]

    try:
        # Move exhausted retries to manual_review
        supabase.table("invoice_queue").update({
            "status":    "manual_review",
            "error_msg": f"Exceeded {max_attempts} attempts — manual review required"
        }).eq("status", "retry").gte("attempts", max_attempts).execute()

        rows = supabase.table("invoice_queue").select("status").execute()
        counts: dict = {}
        for r in (rows.data or []):
            s = r["status"]
            counts[s] = counts.get(s, 0) + 1

        if counts:
            logger.info(f"[Scheduler] Queue: {counts}")

        mr = counts.get("manual_review", 0)
        if mr > 0:
            logger.warning(f"[Scheduler] ⚠ {mr} invoice(s) need manual review")

    except Exception as e:
        logger.error(f"[Scheduler] health_check: {e}")


async def reload_scheduler_jobs():
    """
    Re-reads settings from DB and reschedules all jobs with new intervals.
    Called when admin saves new scheduler settings.
    """
    cfg = get_settings()
    logger.info(f"[Scheduler] Reloading with settings: {cfg}")

    for job_id in ["process_queue", "retry_failed", "health_check"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    scheduler.add_job(
        process_pending_queue,
        trigger=IntervalTrigger(seconds=cfg["process_queue_seconds"]),
        id="process_queue",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        retry_failed_invoices,
        trigger=IntervalTrigger(minutes=cfg["retry_interval_minutes"]),
        id="retry_failed",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(minutes=cfg["health_check_minutes"]),
        id="health_check",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        f"[Scheduler] Jobs rescheduled — "
        f"queue:{cfg['process_queue_seconds']}s "
        f"retry:{cfg['retry_interval_minutes']}m "
        f"health:{cfg['health_check_minutes']}m"
    )


# ── Start / Stop ──────────────────────────────────────────────────────────────

def start_scheduler():
    if scheduler.running:
        return
    cfg = get_settings()
    logger.info(f"[Scheduler] Starting with config: {cfg}")

    scheduler.add_job(
        process_pending_queue,
        trigger=IntervalTrigger(seconds=cfg["process_queue_seconds"]),
        id="process_queue",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        retry_failed_invoices,
        trigger=IntervalTrigger(minutes=cfg["retry_interval_minutes"]),
        id="retry_failed",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(minutes=cfg["health_check_minutes"]),
        id="health_check",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        f"[Scheduler] ✓ Started — "
        f"queue every {cfg['process_queue_seconds']}s, "
        f"retry every {cfg['retry_interval_minutes']}m, "
        f"health every {cfg['health_check_minutes']}m, "
        f"max_attempts={cfg['max_attempts']}, "
        f"batch={cfg['batch_size']}, "
        f"auto={cfg['auto_process']}"
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[Scheduler] Stopped")

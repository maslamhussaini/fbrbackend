import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routes.invoices           import router as invoice_router
from routes.settings           import router as settings_router
from routes.auth               import router as auth_router
from routes.bulk               import router as bulk_router
from routes.sales_invoice      import router as sales_router
from routes.scheduler_settings import router as scheduler_router
from routes.setup              import router as setup_router
from services.scheduler        import start_scheduler, stop_scheduler, scheduler, get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="FBR Digital Invoicing API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(invoice_router)
app.include_router(settings_router)
app.include_router(bulk_router)
app.include_router(sales_router)
app.include_router(scheduler_router)
app.include_router(setup_router)


@app.get("/")
def health():
    cfg = get_settings()
    return {
        "status":    "ok",
        "version":   "3.0.0",
        "scheduler": "running" if scheduler.running else "stopped",
        "config": {
            "queue_interval": f"{cfg['process_queue_seconds']}s",
            "auto_process":   cfg['auto_process'],
        }
    }


@app.get("/queue/status")
def queue_status():
    from db.supabase import supabase
    rows = supabase.table("invoice_queue").select("status").execute()
    counts: dict = {}
    for r in (rows.data or []):
        s = r["status"]
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    return {
        "total":     total,
        "submitted": counts.get("submitted", 0),
        "pending":   counts.get("queued", 0) + counts.get("submitting", 0),
        "retry":     counts.get("retry", 0),
        "failed":    counts.get("failed", 0) + counts.get("manual_review", 0),
        "counts":    counts,
        "scheduler": "running" if scheduler.running else "stopped",
    }


@app.post("/queue/process-now")
async def process_now():
    from services.scheduler import process_pending_queue, retry_failed_invoices
    await process_pending_queue()
    await retry_failed_invoices()
    return {"triggered": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

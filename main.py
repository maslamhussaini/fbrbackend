from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.invoices import router as invoice_router
from routes.settings import router as settings_router
from routes.auth     import router as auth_router
from routes.bulk     import router as bulk_router

app = FastAPI(title="FBR Digital Invoicing API", version="3.0.0")

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

@app.get("/")
def health():
    return {"status": "ok", "version": "3.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

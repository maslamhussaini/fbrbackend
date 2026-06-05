from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.invoices import router as invoice_router
from routes.settings import router as settings_router

app = FastAPI(title="FBR Digital Invoicing API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoice_router)
app.include_router(settings_router)


@app.get("/")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/ping-fbr")
async def ping_fbr():
    import httpx
    from config import settings

    test_payload = {
        "invoiceType": "Sale Invoice",
        "invoiceDate": "2025-07-12",
        "sellerNTNCNIC": "4250124272389",
        "sellerBusinessName": "FAIZAN ENGINEERING SERVICES",
        "sellerProvince": "SINDH",
        "sellerAddress": "KARACHI",
        "buyerNTNCNIC": "8352312-6",
        "buyerBusinessName": "AADAM TEXTILE",
        "buyerProvince": "SINDH",
        "buyerAddress": "PLOT NO CR-435, KARACHI",
        "buyerRegistrationType": "Registered",
        "invoiceRefNo": "667",
        "scenarioId": "SN001",
        "items": [{
            "hsCode": "3923.9090",
            "productDescription": "Test Product",
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

    token = settings.FBR_BEARER_TOKEN or "no-token-set"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            r = await client.post(settings.FBR_VALIDATE_URL, json=test_payload, headers=headers)
        data = r.json()
        status = data.get("validationResponse", {}).get("statusCode")
        return {
            "fbr_status": "VALID ✓" if status == "00" else "INVALID ✗",
            "status_code": status,
            "full_response": data
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

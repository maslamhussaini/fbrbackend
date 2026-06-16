import httpx
from config import API_BASE_URL


class ApiClient:
    def __init__(self):
        self.base    = API_BASE_URL
        self.timeout = 60.0
        self.token   = None

    def _headers(self):
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def login(self, email, password):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/auth/login", json={"email": email, "password": password})
            data = r.json()
            if data.get("success") and data.get("token"):
                self.token = data["token"]
            return data
        except Exception as e:
            return {"success": False, "error": str(e)}

    def signup(self, email, password):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/auth/signup", json={"email": email, "password": password})
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def verify_otp(self, email, otp):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/auth/verify-otp", json={"email": email, "token": otp})
            data = r.json()
            if data.get("success") and data.get("token"):
                self.token = data["token"]
            return data
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_role(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/auth/me", headers=self._headers())
            return r.json().get("role", "user")
        except Exception:
            return "user"

    def download_template(self, save_path):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/invoices/template", headers=self._headers())
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                return {"success": True}
            return {"success": False, "error": f"Server error {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def validate_excel(self, file_path):
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path, f, "application/octet-stream")}
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(f"{self.base}/invoices/validate", files=files, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"valid": False, "errors": [str(e)], "data": None}

    def submit_excel(self, file_path):
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path, f, "application/octet-stream")}
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(f"{self.base}/invoices/submit", files=files, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_history(self, limit=50):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/invoices/history", params={"limit": limit}, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"invoices": [], "error": str(e)}

    def retry_invoice(self, invoice_id):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/invoices/retry/{invoice_id}", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_settings(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/settings", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e), "data": None}

    def save_settings(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/settings", json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def test_fbr_token(self, token):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/settings/test-token", json={"token": token}, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def ping(self):
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base}/")
            return r.status_code == 200
        except Exception:
            return False

    def bulk_download_template(self, save_path):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/bulk/template", headers=self._headers())
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                return {"success": True}
            return {"success": False, "error": f"Server error {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bulk_upload(self, file_path):
        try:
            import os
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                mime = "application/json" if filename.endswith(".json") else "application/octet-stream"
                files = {"file": (filename, f, mime)}
                with httpx.Client(timeout=120.0) as c:
                    r = c.post(f"{self.base}/bulk/upload", files=files, headers=self._headers())
            if r.status_code == 200:
                return r.json()
            else:
                try:
                    return r.json()
                except Exception:
                    return {"error": f"Server error {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def bulk_confirm(self, batch_id):
        try:
            with httpx.Client(timeout=300.0) as c:
                r = c.post(f"{self.base}/bulk/confirm/{batch_id}", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def bulk_status(self, batch_id):
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(f"{self.base}/bulk/status/{batch_id}", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_customers(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/bulk/customers", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"customers": [], "error": str(e)}

    def save_customer(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/bulk/customers", json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_products(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/bulk/products", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"products": [], "error": str(e)}

    def save_product(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/bulk/products", json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def lookup_hs_code(self, code):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/bulk/hs-codes/{code}", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"description": None}

    # ── Sales invoices ────────────────────────────────────────────────────────
    def get_sales_invoices(self, status=""):
        try:
            params = {"status": status} if status else {}
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/sales-invoices", params=params, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"invoices": [], "stats": {}, "error": str(e)}

    def get_sales_invoice(self, invoice_id):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/sales-invoices/{invoice_id}", headers=self._headers())
            return r.json()
        except Exception as e:
            return None

    def create_sales_invoice(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/sales-invoices", json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_sales_invoice(self, invoice_id):
        try:
            with httpx.Client(timeout=60.0) as c:
                r = c.post(f"{self.base}/sales-invoices/{invoice_id}/submit",
                           headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_sales_invoice(self, invoice_id):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/sales-invoices/{invoice_id}/cancel",
                           headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_invoice_pdf(self, invoice_id, save_path):
        try:
            with httpx.Client(timeout=30.0) as c:
                r = c.get(f"{self.base}/sales-invoices/{invoice_id}/pdf",
                          headers=self._headers())
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                return {"success": True}
            return {"success": False, "error": f"Status {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def lookup(self, kind, q=""):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/sales-invoices/lookup/{kind}",
                          params={"q": q}, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"products": [], "customers": []}

    def get_queue_status(self):
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(f"{self.base}/queue/status", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"error": str(e), "total": 0}

    def trigger_queue_now(self):
        try:
            with httpx.Client(timeout=30.0) as c:
                r = c.post(f"{self.base}/queue/process-now", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_scheduler_settings(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/scheduler/status", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"running": False, "jobs": [], "config": {}}

    def save_scheduler_settings(self, settings: dict):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/scheduler/settings/bulk",
                           json=settings, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_auto_process(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/scheduler/toggle", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Setup screens ─────────────────────────────────────────────────────────
    def get_hs_codes(self, q=""):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/setup/hs-codes",
                          params={"q": q}, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"hs_codes": [], "error": str(e)}

    def save_hs_code(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/hs-codes",
                           json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_hs_codes(self, codes: list):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/hs-codes/bulk",
                           json=codes, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_units(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/setup/units", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"units": [], "error": str(e)}

    def save_unit(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/units",
                           json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_provinces(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/setup/provinces", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"provinces": [], "error": str(e)}

    def save_province(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/provinces",
                           json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_cities(self, province_code=""):
        try:
            params = {"province_code": province_code} if province_code else {}
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/setup/cities",
                          params=params, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"cities": [], "error": str(e)}

    def save_city(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/cities",
                           json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_areas(self, city_id=""):
        try:
            params = {"city_id": city_id} if city_id else {}
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/setup/areas",
                          params=params, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"areas": [], "error": str(e)}

    def save_area(self, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/setup/areas",
                           json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_bulk_invoices(self):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base}/bulk/invoices", headers=self._headers())
            return r.json()
        except Exception as e:
            return {"invoices": [], "counts": {}, "error": str(e)}

    def update_bulk_invoice(self, invoice_id, data):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.put(f"{self.base}/bulk/invoices/{invoice_id}",
                          json=data, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_bulk_invoice(self, invoice_id):
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.delete(f"{self.base}/bulk/invoices/{invoice_id}",
                             headers=self._headers())
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_bulk_invoices(self, ids: list):
        results = []
        for inv_id in ids:
            results.append(self.delete_bulk_invoice(inv_id))
        return {"deleted": len([r for r in results if r.get("success")])}

    def submit_selected_invoices(self, ids: list):
        try:
            with httpx.Client(timeout=120.0) as c:
                r = c.post(f"{self.base}/bulk/invoices/submit-selected",
                           json={"ids": ids}, headers=self._headers())
            return r.json()
        except Exception as e:
            return {"submitted": 0, "failed": len(ids), "error": str(e)}

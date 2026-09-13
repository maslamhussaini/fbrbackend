import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


@pytest.fixture
def mock_supabase():
    with patch('routes.auth.supabase') as auth_mock, \
         patch('routes.sales_invoice.supabase', auth_mock), \
         patch('services.idempotency.supabase', auth_mock):
        table_mocks = {}
        def make_table(name):
            if name not in table_mocks:
                table_mocks[name] = MagicMock()
            return table_mocks[name]
        auth_mock.table.side_effect = make_table
        yield auth_mock


def test_onboarding_requires_auth(mock_supabase):
    from routes.auth import onboarding
    from routes.auth import OnboardingPayload

    payload = OnboardingPayload(
        business_name="Test",
        province="SINDH",
        address="Addr",
        tax_registration_type="sales_tax_registered",
    )
    with pytest.raises(Exception):
        onboarding(payload)


def test_onboarding_creates_tenant_and_profile(mock_supabase):
    from routes.auth import onboarding
    from routes.auth import OnboardingPayload

    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": None,
    }
    insert_result = MagicMock()
    insert_result.data = [{"id": "tenant-1", "name": "Test"}]
    mock_supabase.table("fbr_tbl_tenants").insert.return_value.execute.return_value = insert_result

    payload = OnboardingPayload(
        business_name="Test Business",
        ntn_cnic="1234567",
        province="SINDH",
        address="Addr",
        tax_registration_type="sales_tax_registered",
    )
    result = onboarding(payload, {"id": "user-1", "email": "test@example.com"})
    assert result["success"] is True
    assert result["tenant_id"] == "tenant-1"
    assert result["tax_registration_type"] == "sales_tax_registered"


def test_onboarding_accepts_not_sales_tax_registered(mock_supabase):
    from routes.auth import onboarding
    from routes.auth import OnboardingPayload

    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": None,
    }
    insert_result = MagicMock()
    insert_result.data = [{"id": "tenant-1", "name": "Test"}]
    mock_supabase.table("fbr_tbl_tenants").insert.return_value.execute.return_value = insert_result

    payload = OnboardingPayload(
        business_name="Test Business",
        province="SINDH",
        address="Addr",
        tax_registration_type="not_sales_tax_registered",
    )
    result = onboarding(payload, {"id": "user-1", "email": "test@example.com"})
    assert result["success"] is True
    assert result["tax_registration_type"] == "not_sales_tax_registered"


def test_onboarding_rejects_invalid_tax_type(mock_supabase):
    from routes.auth import onboarding
    from routes.auth import OnboardingPayload

    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": None,
    }

    payload = OnboardingPayload(
        business_name="Test",
        province="SINDH",
        address="Addr",
        tax_registration_type="invalid_type",
    )
    with pytest.raises(HTTPException) as exc:
        onboarding(payload, {"id": "user-1", "email": "test@example.com"})
    assert exc.value.status_code == 400


def test_onboarding_retry_does_not_create_duplicate_tenant(mock_supabase):
    from routes.auth import onboarding
    from routes.auth import OnboardingPayload

    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )

    payload1 = OnboardingPayload(
        business_name="Test Business",
        province="SINDH",
        address="Addr",
        tax_registration_type="sales_tax_registered",
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": None,
    }
    insert_result = MagicMock()
    insert_result.data = [{"id": "tenant-1", "name": "Test"}]
    mock_supabase.table("fbr_tbl_tenants").insert.return_value.execute.return_value = insert_result

    result1 = onboarding(payload1, {"id": "user-1", "email": "test@example.com"})
    assert result1["success"] is True

    payload2 = OnboardingPayload(
        business_name="Test Business Updated",
        province="SINDH",
        address="Addr Updated",
        tax_registration_type="not_sales_tax_registered",
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": "tenant-1",
    }
    existing = MagicMock()
    existing.data = {"id": "tenant-1", "name": "Old"}
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value = existing

    result2 = onboarding(payload2, {"id": "user-1", "email": "test@example.com"})
    assert result2["success"] is True
    assert result2["tenant_id"] == "tenant-1"


def test_auth_me_tenantless_reports_onboarding_required(mock_supabase):
    from routes.auth import get_me

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="valid-token",
    )
    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": None,
    }

    result = get_me(credentials)
    assert result["onboarding_required"] is True
    assert result["tenant_id"] is None
    assert result["tax_registration_type"] is None


def test_auth_me_null_tax_reports_onboarding_required(mock_supabase):
    from routes.auth import get_me

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="valid-token",
    )
    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": "tenant-1",
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "tax_registration_type": None,
    }

    result = get_me(credentials)
    assert result["onboarding_required"] is True
    assert result["tax_registration_type"] is None


def test_auth_me_completed_tenant_reports_ready(mock_supabase):
    from routes.auth import get_me

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="valid-token",
    )
    mock_supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="user-1", email="test@example.com")
    )
    mock_supabase.table("fbr_tbl_user_profiles").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "user-1",
        "role": "user",
        "tenant_id": "tenant-1",
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "tax_registration_type": "sales_tax_registered",
    }

    result = get_me(credentials)
    assert result["onboarding_required"] is False
    assert result["tax_registration_type"] == "sales_tax_registered"


def test_validate_non_sales_tax_registered_blocked(mock_supabase):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "invoice_date": "2024-01-01",
        "buyer_ntn_cnic": "1234567",
        "buyer_business_name": "Buyer",
        "buyer_province": "SINDH",
        "buyer_address": "Addr",
        "buyer_registration_type": "Registered",
        "invoice_ref_no": "",
        "scenario_id": "SN001",
    }
    mock_supabase.table("fbr_tbl_invoice_items").select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "not_sales_tax_registered",
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "unavailable" in str(exc.value.detail).lower()


def test_validate_null_tax_registration_blocked(mock_supabase):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "invoice_date": "2024-01-01",
        "buyer_ntn_cnic": "1234567",
        "buyer_business_name": "Buyer",
        "buyer_province": "SINDH",
        "buyer_address": "Addr",
        "buyer_registration_type": "Registered",
        "invoice_ref_no": "",
        "scenario_id": "SN001",
    }
    mock_supabase.table("fbr_tbl_invoice_items").select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": None,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "unavailable" in str(exc.value.detail).lower()


def test_submit_non_sales_tax_registered_blocked(mock_supabase):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "pending",
        "attempts": 0,
        "invoice_date": "2024-01-01",
        "buyer_ntn_cnic": "1234567",
        "buyer_business_name": "Buyer",
        "buyer_province": "SINDH",
        "buyer_address": "Addr",
        "buyer_registration_type": "Registered",
        "invoice_ref_no": "",
        "scenario_id": "SN001",
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "not_sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "unavailable" in str(exc.value.detail).lower()


def test_submit_null_tax_registration_blocked(mock_supabase):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "pending",
        "attempts": 0,
        "invoice_date": "2024-01-01",
        "buyer_ntn_cnic": "1234567",
        "buyer_business_name": "Buyer",
        "buyer_province": "SINDH",
        "buyer_address": "Addr",
        "buyer_registration_type": "Registered",
        "invoice_ref_no": "",
        "scenario_id": "SN001",
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": None,
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "unavailable" in str(exc.value.detail).lower()

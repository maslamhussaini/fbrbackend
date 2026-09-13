import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


@pytest.fixture
def mock_supabase():
    with patch('routes.sales_invoice.supabase') as route_mock, \
         patch('services.idempotency.supabase', route_mock):
        table_mocks = {}
        def make_table(name):
            if name not in table_mocks:
                table_mocks[name] = MagicMock()
            return table_mocks[name]
        route_mock.table.side_effect = make_table
        yield route_mock


@pytest.fixture
def mock_fbr():
    with patch('routes.sales_invoice.post_invoice_to_fbr') as mock:
        yield mock


def _setup_success(mock_supabase, mock_fbr, operation_id="op-1"):
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
    mock_supabase.table("fbr_tbl_invoice_items").select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }
    mock_supabase.table("fbr_tbl_invoices").update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": "FBR-123",
        "error": None,
        "raw": {"validationResponse": {"statusCode": "00", "status": "Valid"}},
    }


def test_submit_own_eligible_invoice_succeeds(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    _setup_success(mock_supabase, mock_fbr)

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert result["success"] is True
    assert "flight" in result
    stages = [e["stage"] for e in result["flight"]]
    assert "PRE_DISPATCH" in stages
    assert "FBR_RESPONSE_RECEIVED" in stages
    assert "INVOICE_PERSISTED" in stages


def test_submit_nonexistent_returns_404(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("missing", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 404
    mock_fbr.assert_not_called()


def test_submit_cross_tenant_returns_404(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "other-tenant",
        "publish_status": "Open",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 404
    mock_fbr.assert_not_called()


def test_submit_already_submitted_rejected(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Close",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    mock_fbr.assert_not_called()


def test_submit_cancelled_rejected(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Cancel",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    mock_fbr.assert_not_called()


def test_submit_uncertain_invoice_rejected(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-1", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "uncertain",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    mock_fbr.assert_not_called()


def test_submit_definitive_fbr_rejection_marks_failed(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    _setup_success(mock_supabase, mock_fbr)
    mock_fbr.return_value = {
        "success": False,
        "invoice_no": None,
        "error": "Invalid invoice",
        "raw": {"validationResponse": {"statusCode": "01", "status": "Invalid"}},
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert result["success"] is False
    assert "flight" in result


def test_submit_timeout_after_dispatch_marks_uncertain(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    _setup_success(mock_supabase, mock_fbr)
    mock_fbr.side_effect = Exception("Timeout waiting for FBR response")

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert result["success"] is False
    assert "uncertain" in result["error"].lower()
    assert "flight" in result
    stages = [e["stage"] for e in result["flight"]]
    assert "OUTCOME_UNCERTAIN" in stages


def test_submit_connection_reset_after_dispatch_marks_uncertain(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    _setup_success(mock_supabase, mock_fbr)
    mock_fbr.side_effect = Exception("Connection reset while waiting for FBR response")

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert result["success"] is False
    assert "uncertain" in result["error"].lower()
    stages = [e["stage"] for e in result["flight"]]
    assert "OUTCOME_UNCERTAIN" in stages


def test_submit_token_not_returned_in_response(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    _setup_success(mock_supabase, mock_fbr)
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "secret-token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert "secret-token" not in str(result)
    assert "fbr_bearer_token" not in str(result)


def test_submit_double_submit_protected_by_idempotency(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    completed_row = {
        "id": "op-existing",
        "status": "completed",
        "response_body": {
            "success": True,
            "tracking_no": "FBR-CACHED",
            "error": None,
            "flight": [{"stage": "CACHED", "message": "cached"}],
        }
    }
    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [completed_row]

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "pending",
        "attempts": 0,
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-existing"

    result = asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert result["success"] is True
    assert result["tracking_no"] == "FBR-CACHED"
    mock_fbr.assert_not_called()


def test_submit_concurrent_same_operation_id_rejected(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    processing_row = {
        "id": "op-running",
        "status": "processing",
        "can_proceed": False,
    }
    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [processing_row]

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "pending",
        "attempts": 0,
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-running"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 409
    mock_fbr.assert_not_called()


def test_submit_new_operation_id_cannot_resubmit_submitted(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-new", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Close",
        "status": "submitted",
        "attempts": 1,
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-new"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "Already submitted" in str(exc.value.detail)
    mock_fbr.assert_not_called()


def test_submit_new_operation_id_cannot_resubmit_uncertain(mock_supabase, mock_fbr):
    from routes.sales_invoice import submit_to_fbr

    mock_supabase.table("fbr_tbl_sync_operations").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    insert_result = MagicMock()
    insert_result.data = [{"id": "op-new", "status": "processing", "can_proceed": True}]
    mock_supabase.table("fbr_tbl_sync_operations").insert.return_value.execute.return_value = insert_result

    mock_supabase.table("fbr_tbl_invoices").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "inv-1",
        "tenant_id": "tenant-1",
        "publish_status": "Open",
        "status": "uncertain",
        "attempts": 1,
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-new"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 400
    assert "uncertain" in str(exc.value.detail).lower()
    mock_fbr.assert_not_called()


def test_submit_payload_build_failure_is_not_uncertain(mock_supabase, mock_fbr):
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
        # Missing invoice_date and other required payload fields
    }
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "token",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(KeyError):
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    mock_fbr.assert_not_called()


def test_submit_tenant_config_missing_is_not_uncertain(mock_supabase, mock_fbr):
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
    mock_supabase.table("fbr_tbl_invoice_items").select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        # Missing ntn_cnic which is required directly in seller dict
        "name": "Seller",
        "tax_registration_type": "sales_tax_registered",
    }

    request = MagicMock()
    request.headers.get.return_value = "op-1"

    with pytest.raises(KeyError):
        asyncio.run(submit_to_fbr("inv-1", request, {"tenant_id": "tenant-1"}))
    mock_fbr.assert_not_called()

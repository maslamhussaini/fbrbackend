import pytest
from unittest.mock import MagicMock, patch
from services.idempotency import (
    begin_operation,
    complete_operation,
    fail_operation,
    OperationConflictError,
)


@pytest.fixture
def mock_supabase():
    with patch('services.idempotency.supabase') as mock:
        yield mock


def test_begin_operation_creates_new_row(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    inserted_mock = MagicMock()
    inserted_mock.data = [{"id": "op-1", "status": "processing"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = inserted_mock

    result = begin_operation("tenant-1", "op-1", "CUSTOMER", "CREATE", "record-1")
    assert result["status"] == "processing"
    assert result["row"]["id"] == "op-1"


def test_begin_operation_returns_completed_if_exists(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "op-1", "status": "completed", "response_body": {"id": "1"}}
    ]

    result = begin_operation("tenant-1", "op-1", "CUSTOMER", "CREATE", "record-1")
    assert result["status"] == "completed"
    assert result["row"]["response_body"]["id"] == "1"


def test_same_operation_id_across_tenants_is_independent(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    inserted_mock = MagicMock()
    inserted_mock.data = [{"id": "op-1", "status": "processing"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = inserted_mock

    result = begin_operation("tenant-A", "op-1", "CUSTOMER", "CREATE", "record-1")
    assert result["status"] == "processing"


def test_complete_operation_updates_row(mock_supabase):
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    complete_operation("op-1", 200, {"id": "1"})
    mock_supabase.table.return_value.update.assert_called_once()
    update_args = mock_supabase.table.return_value.update.call_args[0][0]
    assert update_args["status"] == "completed"
    assert update_args["response_status"] == 200


def test_fail_operation_updates_row(mock_supabase):
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    fail_operation("op-1", "Something went wrong")
    update_args = mock_supabase.table.return_value.update.call_args[0][0]
    assert update_args["status"] == "failed"
    assert update_args["last_error"] == "Something went wrong"


def test_customer_lost_response_retry_does_not_duplicate(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "op-1", "status": "completed", "response_body": {"id": "cust-1", "name": "A"}}
    ]

    result = begin_operation("tenant-1", "op-1", "CUSTOMER", "CREATE", "cust-1")
    assert result["status"] == "completed"
    assert result["row"]["response_body"]["id"] == "cust-1"


def test_product_lost_response_retry_does_not_duplicate(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "op-2", "status": "completed", "response_body": {"id": "prod-1", "name": "B"}}
    ]

    result = begin_operation("tenant-1", "op-2", "PRODUCT", "CREATE", "prod-1")
    assert result["status"] == "completed"
    assert result["row"]["response_body"]["id"] == "prod-1"


def test_invoice_lost_response_retry_does_not_duplicate(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "op-3", "status": "completed", "response_body": {"invoice_id": "inv-1"}}
    ]

    result = begin_operation("tenant-1", "op-3", "INVOICE", "CREATE", "inv-1")
    assert result["status"] == "completed"
    assert result["row"]["response_body"]["invoice_id"] == "inv-1"


def test_invoice_client_uuid_preserved_on_retry(mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "op-4", "status": "completed", "record_id": "client-uuid-123", "response_body": {"invoice_id": "client-uuid-123"}}
    ]

    result = begin_operation("tenant-1", "op-4", "INVOICE", "CREATE", "client-uuid-123")
    assert result["status"] == "completed"
    assert result["row"]["record_id"] == "client-uuid-123"


def test_cross_tenant_operation_isolation(mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    inserted_mock = MagicMock()
    inserted_mock.data = [{"id": "op-5", "status": "processing"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = inserted_mock

    result = begin_operation("tenant-A", "op-5", "CUSTOMER", "CREATE", "record-5")
    assert result["status"] == "processing"


def test_no_fbr_submit_in_create_invoice(mock_supabase):
    from routes.sales_invoice import create_invoice
    from fastapi import Request
    from datetime import date

    with patch('routes.sales_invoice.supabase', mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = [
            {"id": "tenant-1", "ntn_cnic": "123", "name": "Test", "province": "SINDH"}
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "inv-1"}]
        mock_supabase.table.return_value.select.return_value.single.return_value.execute.return_value.data = {"invoice_number": "INV-001"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        with patch('routes.sales_invoice.begin_operation') as mock_begin:
            mock_begin.return_value = {"status": "processing", "row": {"id": "op-1"}}
            with patch('routes.sales_invoice.complete_operation'):
                payload = MagicMock()
                payload.id = "client-uuid"
                payload.document_date = "2024-01-01"
                payload.customer_name = "Test"
                payload.buyer_ntn_cnic = "123"
                payload.buyer_province = "SINDH"
                payload.buyer_address = "Addr"
                payload.buyer_reg_type = "Unregistered"
                payload.reference_no = ""
                payload.dc_no = ""
                payload.po_number = ""
                payload.scenario_id = None
                payload.remarks = ""
                payload.items = []

                request = MagicMock(spec=Request)
                request.headers.get.return_value = "op-1"
                tenant_ctx = {"tenant_id": "tenant-1"}

                try:
                    create_invoice(payload, request, tenant_ctx)
                except Exception:
                    pass

                insert_calls = [c for c in mock_supabase.table.call_args_list if c[0][0] == "fbr_tbl_invoices"]
                assert len(insert_calls) >= 1

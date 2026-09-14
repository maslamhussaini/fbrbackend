import asyncio
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_supabase():
    with patch('routes.bulk.supabase') as mock:
        yield mock


def test_bulk_submit_cross_tenant_skips_other_tenant_invoice(mock_supabase):
    from routes.bulk import submit_selected_invoices

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    result = asyncio.run(submit_selected_invoices({"ids": ["inv-1"]}, {"tenant_id": "tenant-1"}))

    assert result["submitted"] == 0
    assert result["failed"] == 0


def test_bulk_submit_own_invoice_succeeds(mock_supabase):
    from routes.bulk import submit_selected_invoices

    select_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute
    select_chain.return_value.data = {
        "invoice_payload": {},
        "attempts": 0,
    }

    update_chain = mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_chain.return_value = MagicMock()

    tenant_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute
    tenant_chain.return_value.data = {"fbr_bearer_token": "token"}

    with patch('services.fbr.post_invoice_to_fbr', return_value={"success": True, "raw": {}, "invoice_no": "123"}):
        result = asyncio.run(submit_selected_invoices({"ids": ["inv-1"]}, {"tenant_id": "tenant-1"}))

    assert result["submitted"] == 1

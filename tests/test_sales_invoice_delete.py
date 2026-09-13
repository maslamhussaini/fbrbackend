import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


@pytest.fixture
def mock_supabase():
    with patch('routes.sales_invoice.supabase') as mock:
        yield mock


def test_delete_own_draft_succeeds(mock_supabase):
    from routes.sales_invoice import delete_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Open"
    }
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    result = delete_invoice("inv-1", {"tenant_id": "tenant-1"})
    assert result == {"success": True}
    assert mock_supabase.table.call_count >= 2


def test_delete_nonexistent_returns_404(mock_supabase):
    from routes.sales_invoice import delete_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    with pytest.raises(HTTPException) as exc:
        delete_invoice("missing-id", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 404


def test_delete_cross_tenant_returns_404(mock_supabase):
    from routes.sales_invoice import delete_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    with pytest.raises(HTTPException) as exc:
        delete_invoice("inv-other", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 404


def test_delete_submitted_invoice_rejected(mock_supabase):
    from routes.sales_invoice import delete_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Close"
    }

    with pytest.raises(HTTPException) as exc:
        delete_invoice("inv-1", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 400


def test_delete_cancelled_invoice_rejected(mock_supabase):
    from routes.sales_invoice import delete_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Cancel"
    }

    with pytest.raises(HTTPException) as exc:
        delete_invoice("inv-1", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 400


def test_delete_never_calls_fbr(mock_supabase):
    from routes.sales_invoice import delete_invoice, post_invoice_to_fbr

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Open"
    }
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    with patch('routes.sales_invoice.post_invoice_to_fbr') as mock_fbr:
        delete_invoice("inv-1", {"tenant_id": "tenant-1"})
        mock_fbr.assert_not_called()

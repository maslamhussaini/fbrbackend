import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


@pytest.fixture
def mock_supabase():
    with patch('routes.sales_invoice.supabase') as mock:
        yield mock


def test_cancel_own_open_invoice_succeeds(mock_supabase):
    from routes.sales_invoice import cancel_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Open"
    }
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

    result = cancel_invoice("inv-1", {"tenant_id": "tenant-1"})
    assert result == {"success": True}


def test_cancel_nonexistent_returns_404(mock_supabase):
    from routes.sales_invoice import cancel_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    with pytest.raises(HTTPException) as exc:
        cancel_invoice("missing-id", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 404


def test_cancel_cross_tenant_returns_404(mock_supabase):
    from routes.sales_invoice import cancel_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

    with pytest.raises(HTTPException) as exc:
        cancel_invoice("inv-other", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 404


def test_cancel_submitted_invoice_rejected(mock_supabase):
    from routes.sales_invoice import cancel_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "publish_status": "Close"
    }

    with pytest.raises(HTTPException) as exc:
        cancel_invoice("inv-1", {"tenant_id": "tenant-1"})
    assert exc.value.status_code == 400

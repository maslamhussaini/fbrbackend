import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


@pytest.fixture
def mock_supabase():
    with patch('routes.sales_invoice.supabase') as mock:
        yield mock


@pytest.fixture
def mock_fbr():
    with patch('routes.sales_invoice.post_invoice_to_fbr') as mock:
        yield mock


def _setup_tenant(mock_supabase, tax_type="sales_tax_registered"):
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN123",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "tenant-token",
        "tax_registration_type": tax_type,
    }


def test_validate_own_invoice_success(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "hs_code": "1234",
            "product_description": "Prod",
            "uom": "KG",
            "quantity": 1,
            "rate": 100,
            "sales_tax": 18,
            "value_excl_st": 100,
            "total_values": 118,
            "retail_price": 118,
            "further_tax": 0,
            "discount": 0,
            "fed_payable": 0,
            "sale_type": "Goods at standard rate (default)",
            "sro_schedule_no": "",
            "sro_item_serial_no": "",
        }
    ]
    _setup_tenant(mock_supabase)
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": None,
        "error": None,
        "raw": {
            "validationResponse": {
                "statusCode": "00",
                "status": "Valid",
            }
        },
    }

    result = asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert result["success"] is True
    assert result["valid"] is True
    assert result["status_code"] == "00"
    mock_fbr.assert_called_once()
    call_kwargs = mock_fbr.call_args.kwargs
    assert call_kwargs.get("use_validate") is True


def test_validate_nonexistent_returns_404(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    _setup_tenant(mock_supabase)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_invoice("missing", MagicMock(), {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 404
    mock_fbr.assert_not_called()


def test_validate_cross_tenant_returns_404(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    _setup_tenant(mock_supabase)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_invoice("inv-other", MagicMock(), {"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 404
    mock_fbr.assert_not_called()


def test_validate_uses_tenant_seller_config(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    _setup_tenant(mock_supabase)
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TNTN",
        "name": "TNAME",
        "province": "PUNJAB",
        "address": "TADDR",
        "fbr_bearer_token": "tenant-token",
        "tax_registration_type": "sales_tax_registered",
    }
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": None,
        "error": None,
        "raw": {
            "validationResponse": {
                "statusCode": "00",
                "status": "Valid",
            }
        },
    }

    asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    payload = mock_fbr.call_args.args[0]
    assert payload["sellerNTNCNIC"] == "TNTN"
    assert payload["sellerBusinessName"] == "TNAME"
    assert mock_fbr.call_args.kwargs.get("bearer_token") == "tenant-token"


def test_validate_does_not_mark_invoice_submitted(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    _setup_tenant(mock_supabase)
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": None,
        "error": None,
        "raw": {
            "validationResponse": {
                "statusCode": "00",
                "status": "Valid",
            }
        },
    }

    asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    update_calls = [
        c for c in mock_supabase.table.call_args_list
        if c.args and c.args[0] == "fbr_tbl_invoices" and "update" in str(c)
    ]
    assert len(update_calls) == 0


def test_validate_success_response_parsed(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    _setup_tenant(mock_supabase)
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": None,
        "error": None,
        "raw": {
            "validationResponse": {
                "statusCode": "00",
                "status": "Valid",
                "error": None,
                "invoiceStatuses": [],
            }
        },
    }

    result = asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert result["success"] is True
    assert result["valid"] is True
    assert result["status_code"] == "00"
    assert result["status"] == "Valid"
    assert result["item_errors"] == []


def test_validate_rejection_parsed(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    _setup_tenant(mock_supabase)
    mock_fbr.return_value = {
        "success": False,
        "invoice_no": None,
        "error": "Invalid HS Code",
        "raw": {
            "validationResponse": {
                "statusCode": "01",
                "status": "Invalid",
                "error": "Invalid HS Code",
                "invoiceStatuses": [
                    {
                        "itemSNo": "1",
                        "statusCode": "01",
                        "status": "Invalid",
                        "error": "Invalid HS Code",
                    }
                ],
            }
        },
    }

    result = asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert result["success"] is False
    assert result["valid"] is False
    assert result["status_code"] == "01"
    assert len(result["item_errors"]) == 1
    assert result["item_errors"][0]["error"] == "Invalid HS Code"


def test_validate_does_not_leak_token(mock_supabase, mock_fbr):
    from routes.sales_invoice import validate_invoice

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table("fbr_tbl_tenants").select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "ntn_cnic": "TN",
        "name": "Seller",
        "province": "SINDH",
        "address": "Addr",
        "fbr_bearer_token": "secret-token",
        "tax_registration_type": "sales_tax_registered",
    }
    mock_fbr.return_value = {
        "success": True,
        "invoice_no": None,
        "error": None,
        "raw": {
            "validationResponse": {
                "statusCode": "00",
                "status": "Valid",
            }
        },
    }

    result = asyncio.run(validate_invoice("inv-1", MagicMock(), {"tenant_id": "tenant-1"}))
    assert "secret-token" not in str(result)
    assert "fbr_bearer_token" not in str(result)

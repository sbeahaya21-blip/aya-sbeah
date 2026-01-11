import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from db_util import init_db, save_inv_extraction, get_db
from datetime import datetime


class TestInvoiceByVendorAPI(unittest.TestCase):
    """Comprehensive API tests for the /invoices/vendor/{vendor_name} endpoint"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        # Initialize database
        init_db()
        
        # Import app
        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            self.client = TestClient(app)

    def tearDown(self):
        """Clean up after each test"""
        # Clean up test data
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM items WHERE InvoiceId LIKE 'TEST_%'")
            cursor.execute("DELETE FROM confidences WHERE InvoiceId LIKE 'TEST_%'")
            cursor.execute("DELETE FROM invoices WHERE InvoiceId LIKE 'TEST_%'")

    def test_get_invoices_by_vendor_single_invoice(self):
        """Test retrieval of single invoice for a vendor"""
        vendor_name = "TestVendor"
        test_invoice_id = "TEST_VENDOR_001"
        
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": vendor_name,
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": [
                    {
                        "Description": "Test Item",
                        "Name": "Product",
                        "Quantity": 1,
                        "UnitPrice": 100.0,
                        "Amount": 100.0
                    }
                ]
            },
            "dataConfidence": {
                "VendorName": 0.95,
                "InvoiceDate": 0.99,
                "BillingAddressRecipient": 0.98,
                "ShippingAddress": 0.97,
                "SubTotal": 0.95,
                "ShippingCost": 0.96,
                "InvoiceTotal": 0.99
            }
        }
        save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()

            # Validate response structure
            self.assertEqual(result["VendorName"], vendor_name)
            self.assertEqual(result["TotalInvoices"], 1)
            self.assertEqual(len(result["invoices"]), 1)
            self.assertEqual(result["invoices"][0]["InvoiceId"], test_invoice_id)
            self.assertEqual(result["invoices"][0]["VendorName"], vendor_name)

    def test_get_invoices_by_vendor_multiple_invoices(self):
        """Test retrieval of multiple invoices for a vendor"""
        vendor_name = "MultiInvoiceVendor"
        
        # Create multiple invoices with different dates
        invoices_data = [
            {
                "InvoiceId": "TEST_MULTI_001",
                "InvoiceDate": "2012-01-15T00:00:00+00:00",
                "SubTotal": 100.0,
                "InvoiceTotal": 110.0
            },
            {
                "InvoiceId": "TEST_MULTI_002",
                "InvoiceDate": "2012-02-20T00:00:00+00:00",
                "SubTotal": 200.0,
                "InvoiceTotal": 220.0
            },
            {
                "InvoiceId": "TEST_MULTI_003",
                "InvoiceDate": "2012-03-25T00:00:00+00:00",
                "SubTotal": 300.0,
                "InvoiceTotal": 330.0
            }
        ]

        for inv_data in invoices_data:
            test_data = {
                "confidence": 0.95,
                "data": {
                    "InvoiceId": inv_data["InvoiceId"],
                    "VendorName": vendor_name,
                    "InvoiceDate": inv_data["InvoiceDate"],
                    "BillingAddressRecipient": "Test Recipient",
                    "ShippingAddress": "123 Test St",
                    "SubTotal": inv_data["SubTotal"],
                    "ShippingCost": 10.0,
                    "InvoiceTotal": inv_data["InvoiceTotal"],
                    "Items": []
                },
                "dataConfidence": {
                    "VendorName": 0.95,
                    "InvoiceDate": 0.99,
                    "BillingAddressRecipient": 0.98,
                    "ShippingAddress": 0.97,
                    "SubTotal": 0.95,
                    "ShippingCost": 0.96,
                    "InvoiceTotal": 0.99
                }
            }
            save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()

            self.assertEqual(result["VendorName"], vendor_name)
            self.assertEqual(result["TotalInvoices"], 3)
            self.assertEqual(len(result["invoices"]), 3)
            
            # Verify invoices are ordered by date (ascending)
            dates = [inv["InvoiceDate"] for inv in result["invoices"]]
            self.assertEqual(dates, sorted(dates))
            self.assertEqual(result["invoices"][0]["InvoiceId"], "TEST_MULTI_001")
            self.assertEqual(result["invoices"][2]["InvoiceId"], "TEST_MULTI_003")

    def test_get_invoices_by_vendor_not_found(self):
        """Test retrieval for vendor with no invoices"""
        vendor_name = "NonExistentVendor"

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()

            # Should return Unknown Vendor response
            self.assertEqual(result["VendorName"], "Unknown Vendor")
            self.assertEqual(result["TotalInvoices"], 0)
            self.assertEqual(len(result["invoices"]), 0)

    def test_get_invoices_by_vendor_case_sensitive(self):
        """Test that vendor name matching is case sensitive"""
        vendor_name_lower = "testvendor"
        vendor_name_upper = "TestVendor"
        test_invoice_id = "TEST_CASE_001"
        
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": vendor_name_upper,  # Store with capital T
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": []
            },
            "dataConfidence": {
                "VendorName": 0.95,
                "InvoiceDate": 0.99,
                "BillingAddressRecipient": 0.98,
                "ShippingAddress": 0.97,
                "SubTotal": 0.95,
                "ShippingCost": 0.96,
                "InvoiceTotal": 0.99
            }
        }
        save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            # Search with lowercase (should not find)
            response_lower = client.get(f"/invoices/vendor/{vendor_name_lower}")
            self.assertEqual(response_lower.status_code, 200)
            result_lower = response_lower.json()
            self.assertEqual(result_lower["VendorName"], "Unknown Vendor")
            self.assertEqual(result_lower["TotalInvoices"], 0)

            # Search with exact case (should find)
            response_upper = client.get(f"/invoices/vendor/{vendor_name_upper}")
            self.assertEqual(response_upper.status_code, 200)
            result_upper = response_upper.json()
            self.assertEqual(result_upper["VendorName"], vendor_name_upper)
            self.assertEqual(result_upper["TotalInvoices"], 1)

    def test_get_invoices_by_vendor_special_characters(self):
        """Test vendor name with special characters"""
        vendor_name = "Vendor & Co. Inc."
        test_invoice_id = "TEST_SPECIAL_001"
        
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": vendor_name,
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": []
            },
            "dataConfidence": {
                "VendorName": 0.95,
                "InvoiceDate": 0.99,
                "BillingAddressRecipient": 0.98,
                "ShippingAddress": 0.97,
                "SubTotal": 0.95,
                "ShippingCost": 0.96,
                "InvoiceTotal": 0.99
            }
        }
        save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            # URL encode special characters
            import urllib.parse
            encoded_vendor = urllib.parse.quote(vendor_name, safe='')
            response = client.get(f"/invoices/vendor/{encoded_vendor}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["VendorName"], vendor_name)
            self.assertEqual(result["TotalInvoices"], 1)

    def test_get_invoices_by_vendor_with_items(self):
        """Test retrieval of invoices with line items"""
        vendor_name = "VendorWithItems"
        test_invoice_id = "TEST_ITEMS_001"
        
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": vendor_name,
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 200.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 210.0,
                "Items": [
                    {
                        "Description": "Item 1",
                        "Name": "Product 1",
                        "Quantity": 2,
                        "UnitPrice": 50.0,
                        "Amount": 100.0
                    },
                    {
                        "Description": "Item 2",
                        "Name": "Product 2",
                        "Quantity": 1,
                        "UnitPrice": 100.0,
                        "Amount": 100.0
                    }
                ]
            },
            "dataConfidence": {
                "VendorName": 0.95,
                "InvoiceDate": 0.99,
                "BillingAddressRecipient": 0.98,
                "ShippingAddress": 0.97,
                "SubTotal": 0.95,
                "ShippingCost": 0.96,
                "InvoiceTotal": 0.99
            }
        }
        save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["TotalInvoices"], 1)
            self.assertEqual(len(result["invoices"][0]["Items"]), 2)
            self.assertEqual(result["invoices"][0]["Items"][0]["Name"], "Product 1")
            self.assertEqual(result["invoices"][0]["Items"][1]["Name"], "Product 2")

    def test_get_invoices_by_vendor_date_ordering(self):
        """Test that invoices are returned in ascending date order"""
        vendor_name = "OrderedVendor"
        
        # Create invoices with dates out of order
        invoices_data = [
            {
                "InvoiceId": "TEST_ORDER_003",
                "InvoiceDate": "2012-03-15T00:00:00+00:00",
            },
            {
                "InvoiceId": "TEST_ORDER_001",
                "InvoiceDate": "2012-01-10T00:00:00+00:00",
            },
            {
                "InvoiceId": "TEST_ORDER_002",
                "InvoiceDate": "2012-02-20T00:00:00+00:00",
            }
        ]

        for inv_data in invoices_data:
            test_data = {
                "confidence": 0.95,
                "data": {
                    "InvoiceId": inv_data["InvoiceId"],
                    "VendorName": vendor_name,
                    "InvoiceDate": inv_data["InvoiceDate"],
                    "BillingAddressRecipient": "Test Recipient",
                    "ShippingAddress": "123 Test St",
                    "SubTotal": 100.0,
                    "ShippingCost": 10.0,
                    "InvoiceTotal": 110.0,
                    "Items": []
                },
                "dataConfidence": {
                    "VendorName": 0.95,
                    "InvoiceDate": 0.99,
                    "BillingAddressRecipient": 0.98,
                    "ShippingAddress": 0.97,
                    "SubTotal": 0.95,
                    "ShippingCost": 0.96,
                    "InvoiceTotal": 0.99
                }
            }
            save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            # Verify ordering by date (ascending)
            self.assertEqual(result["TotalInvoices"], 3)
            invoice_ids = [inv["InvoiceId"] for inv in result["invoices"]]
            self.assertEqual(invoice_ids, ["TEST_ORDER_001", "TEST_ORDER_002", "TEST_ORDER_003"])

    def test_get_invoices_by_vendor_empty_vendor_name(self):
        """Test retrieval with empty vendor name"""
        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get("/invoices/vendor/")

            # FastAPI should handle empty path parameter
            self.assertIn(response.status_code, [404, 422])

    def test_get_invoices_by_vendor_spaces_in_name(self):
        """Test vendor name with spaces"""
        vendor_name = "Vendor With Spaces"
        test_invoice_id = "TEST_SPACES_001"
        
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": vendor_name,
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": []
            },
            "dataConfidence": {
                "VendorName": 0.95,
                "InvoiceDate": 0.99,
                "BillingAddressRecipient": 0.98,
                "ShippingAddress": 0.97,
                "SubTotal": 0.95,
                "ShippingCost": 0.96,
                "InvoiceTotal": 0.99
            }
        }
        save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            import urllib.parse
            encoded_vendor = urllib.parse.quote(vendor_name, safe='')
            response = client.get(f"/invoices/vendor/{encoded_vendor}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["VendorName"], vendor_name)
            self.assertEqual(result["TotalInvoices"], 1)

    def test_get_invoices_by_vendor_mixed_vendors(self):
        """Test that only invoices for specified vendor are returned"""
        vendor1 = "VendorOne"
        vendor2 = "VendorTwo"
        
        # Create invoices for different vendors
        for vendor_name, invoice_id in [(vendor1, "TEST_MIXED_001"), (vendor2, "TEST_MIXED_002")]:
            test_data = {
                "confidence": 0.95,
                "data": {
                    "InvoiceId": invoice_id,
                    "VendorName": vendor_name,
                    "InvoiceDate": "2012-03-06T00:00:00+00:00",
                    "BillingAddressRecipient": "Test Recipient",
                    "ShippingAddress": "123 Test St",
                    "SubTotal": 100.0,
                    "ShippingCost": 10.0,
                    "InvoiceTotal": 110.0,
                    "Items": []
                },
                "dataConfidence": {
                    "VendorName": 0.95,
                    "InvoiceDate": 0.99,
                    "BillingAddressRecipient": 0.98,
                    "ShippingAddress": 0.97,
                    "SubTotal": 0.95,
                    "ShippingCost": 0.96,
                    "InvoiceTotal": 0.99
                }
            }
            save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            # Query for vendor1
            response1 = client.get(f"/invoices/vendor/{vendor1}")
            self.assertEqual(response1.status_code, 200)
            result1 = response1.json()
            self.assertEqual(result1["VendorName"], vendor1)
            self.assertEqual(result1["TotalInvoices"], 1)
            self.assertEqual(result1["invoices"][0]["InvoiceId"], "TEST_MIXED_001")

            # Query for vendor2
            response2 = client.get(f"/invoices/vendor/{vendor2}")
            self.assertEqual(response2.status_code, 200)
            result2 = response2.json()
            self.assertEqual(result2["VendorName"], vendor2)
            self.assertEqual(result2["TotalInvoices"], 1)
            self.assertEqual(result2["invoices"][0]["InvoiceId"], "TEST_MIXED_002")

    def test_get_invoices_by_vendor_numeric_values(self):
        """Test that numeric values are correctly returned for all invoices"""
        vendor_name = "NumericVendor"
        
        invoices_data = [
            {
                "InvoiceId": "TEST_NUM_001",
                "SubTotal": 123.45,
                "ShippingCost": 6.78,
                "InvoiceTotal": 130.23
            },
            {
                "InvoiceId": "TEST_NUM_002",
                "SubTotal": 999.99,
                "ShippingCost": 0.01,
                "InvoiceTotal": 1000.00
            }
        ]

        for inv_data in invoices_data:
            test_data = {
                "confidence": 0.95,
                "data": {
                    "InvoiceId": inv_data["InvoiceId"],
                    "VendorName": vendor_name,
                    "InvoiceDate": "2012-03-06T00:00:00+00:00",
                    "BillingAddressRecipient": "Test Recipient",
                    "ShippingAddress": "123 Test St",
                    "SubTotal": inv_data["SubTotal"],
                    "ShippingCost": inv_data["ShippingCost"],
                    "InvoiceTotal": inv_data["InvoiceTotal"],
                    "Items": []
                },
                "dataConfidence": {
                    "VendorName": 0.95,
                    "InvoiceDate": 0.99,
                    "BillingAddressRecipient": 0.98,
                    "ShippingAddress": 0.97,
                    "SubTotal": 0.95,
                    "ShippingCost": 0.96,
                    "InvoiceTotal": 0.99
                }
            }
            save_inv_extraction(test_data)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
             patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)
            
            response = client.get(f"/invoices/vendor/{vendor_name}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["TotalInvoices"], 2)
            
            # Verify numeric values
            self.assertEqual(result["invoices"][0]["SubTotal"], 123.45)
            self.assertEqual(result["invoices"][0]["ShippingCost"], 6.78)
            self.assertEqual(result["invoices"][0]["InvoiceTotal"], 130.23)
            self.assertEqual(result["invoices"][1]["SubTotal"], 999.99)
            self.assertEqual(result["invoices"][1]["ShippingCost"], 0.01)
            self.assertEqual(result["invoices"][1]["InvoiceTotal"], 1000.00)


if __name__ == '__main__':
    unittest.main()


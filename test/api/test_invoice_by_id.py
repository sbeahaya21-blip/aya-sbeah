import unittest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from db_util import init_db, save_inv_extraction, get_db, get_cursor
from controllers.invoice_controller import InvoiceController
from models.invoice import Invoice
from models.item import Item


class TestInvoiceByIdAPI(unittest.TestCase):
    """Comprehensive API tests for the /invoices/{invoice_id} endpoint"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        # Set DB_BACKEND to sqlite for tests
        os.environ['DB_BACKEND'] = 'sqlite'
        # Initialize database
        init_db()

        # Import app
        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            self.client = TestClient(app)

    def tearDown(self):
        """Clean up after each test"""
        # Clean up test data using controller
        controller = InvoiceController()
        # Get all invoice IDs that start with TEST_
        with get_db() as conn:
            cursor = get_cursor(conn)
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("SELECT InvoiceId FROM invoices WHERE InvoiceId LIKE 'TEST_%'")
                rows = cursor.fetchall()
                invoice_ids = [row['InvoiceId'] for row in rows]
            else:
                cursor.execute("SELECT InvoiceId FROM invoices WHERE InvoiceId LIKE 'TEST_%'")
                rows = cursor.fetchall()
                invoice_ids = [row[0] for row in rows]
        
        # Delete each test invoice using controller
        for invoice_id in invoice_ids:
            controller.delete_invoice(invoice_id)

    def test_get_invoice_by_id_success(self):
        """Test successful retrieval of invoice by ID"""
        # Insert test invoice data
        test_invoice_id = "TEST_12345"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "TestVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": [
                    {
                        "Description": "Test Item 1",
                        "Name": "Item 1",
                        "Quantity": 2,
                        "UnitPrice": 50.0,
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

        # Test GET endpoint
        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()

            # Validate response structure
            self.assertEqual(result["InvoiceId"], test_invoice_id)
            self.assertEqual(result["VendorName"], "TestVendor")
            self.assertEqual(result["InvoiceDate"],
                             "2012-03-06T00:00:00+00:00")
            self.assertEqual(
                result["BillingAddressRecipient"], "Test Recipient")
            self.assertEqual(result["ShippingAddress"], "123 Test St")
            self.assertEqual(result["SubTotal"], 100.0)
            self.assertEqual(result["ShippingCost"], 10.0)
            self.assertEqual(result["InvoiceTotal"], 110.0)
            self.assertIn("Items", result)
            self.assertEqual(len(result["Items"]), 1)
            self.assertEqual(result["Items"][0]["Description"], "Test Item 1")

    def test_get_invoice_by_id_not_found(self):
        """Test retrieval of non-existent invoice ID"""
        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)

            response = client.get("/invoices/NONEXISTENT_99999")

            self.assertEqual(response.status_code, 404)

    def test_get_invoice_by_id_with_multiple_items(self):
        """Test retrieval of invoice with multiple line items"""
        test_invoice_id = "TEST_MULTI_123"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "MultiItemVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 250.0,
                "ShippingCost": 15.0,
                "InvoiceTotal": 265.0,
                "Items": [
                    {
                        "Description": "Item 1",
                        "Name": "Product 1",
                        "Quantity": 1,
                        "UnitPrice": 100.0,
                        "Amount": 100.0
                    },
                    {
                        "Description": "Item 2",
                        "Name": "Product 2",
                        "Quantity": 2,
                        "UnitPrice": 75.0,
                        "Amount": 150.0
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

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(len(result["Items"]), 2)
            self.assertEqual(result["Items"][0]["Name"], "Product 1")
            self.assertEqual(result["Items"][1]["Name"], "Product 2")

    def test_get_invoice_by_id_without_items(self):
        """Test retrieval of invoice without line items"""
        test_invoice_id = "TEST_NO_ITEMS_123"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "NoItemsVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 0.0,
                "ShippingCost": 0.0,
                "InvoiceTotal": 0.0,
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

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["InvoiceId"], test_invoice_id)
            self.assertIn("Items", result)
            self.assertEqual(len(result["Items"]), 0)

    def test_get_invoice_by_id_null_values(self):
        """Test retrieval of invoice with null/None values"""
        test_invoice_id = "TEST_NULL_123"

        # Create invoice with null values using controller
        controller = InvoiceController()
        invoice = Invoice(
            invoice_id=test_invoice_id,
            vendor_name="NullVendor",
            invoice_date="2012-03-06T00:00:00+00:00",
            billing_address_recipient=None,  # Null BillingAddressRecipient
            shipping_address=None,  # Null ShippingAddress
            sub_total=100.0,
            shipping_cost=None,  # Null ShippingCost
            invoice_total=100.0
        )
        controller.create_or_update_invoice(invoice)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["InvoiceId"], test_invoice_id)
            self.assertIsNone(result.get("BillingAddressRecipient"))
            self.assertIsNone(result.get("ShippingAddress"))

    def test_get_invoice_by_id_special_characters(self):
        """Test retrieval of invoice ID with special characters"""
        test_invoice_id = "TEST_SPECIAL-123_ABC"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "SpecialVendor",
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

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["InvoiceId"], test_invoice_id)

    def test_get_invoice_by_id_empty_string(self):
        """Test retrieval with empty string invoice ID"""
        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)

            response = client.get("/invoices/")

            # FastAPI should return 404 for empty path
            self.assertEqual(response.status_code, 404)

    def test_get_invoice_by_id_items_ordered(self):
        """Test that items are returned in correct order"""
        test_invoice_id = "TEST_ORDERED_123"

        # Create invoice and items using controller
        controller = InvoiceController()
        invoice = Invoice(
            invoice_id=test_invoice_id,
            vendor_name="OrderedVendor",
            invoice_date="2012-03-06T00:00:00+00:00",
            billing_address_recipient="Test Recipient",
            shipping_address="123 Test St",
            sub_total=300.0,
            shipping_cost=10.0,
            invoice_total=310.0
        )
        controller.create_or_update_invoice(invoice)

        # Insert items in specific order using controller
        items_data = [
            {"Description": "Item A", "Name": "Product A", "Quantity": 1, "UnitPrice": 100.0, "Amount": 100.0},
            {"Description": "Item B", "Name": "Product B", "Quantity": 2, "UnitPrice": 100.0, "Amount": 200.0},
        ]
        for item_data in items_data:
            item = Item(
                invoice_id=test_invoice_id,
                description=item_data["Description"],
                name=item_data["Name"],
                quantity=item_data["Quantity"],
                unit_price=item_data["UnitPrice"],
                amount=item_data["Amount"]
            )
            controller.create_item(item)

        with patch('oci.ai_document.AIServiceDocumentClient'), \
                patch('oci.config.from_file', return_value={}):
            from app import app
            client = TestClient(app)

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(len(result["Items"]), 2)
            self.assertEqual(result["Items"][0]["Name"], "Product A")
            self.assertEqual(result["Items"][1]["Name"], "Product B")

    def test_get_invoice_by_id_numeric_values(self):
        """Test that numeric values are correctly returned"""
        test_invoice_id = "TEST_NUMERIC_123"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "NumericVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 1234.56,
                "ShippingCost": 78.90,
                "InvoiceTotal": 1313.46,
                "Items": [
                    {
                        "Description": "Numeric Item",
                        "Name": "Product",
                        "Quantity": 5.5,
                        "UnitPrice": 123.45,
                        "Amount": 678.975
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

            response = client.get(f"/invoices/{test_invoice_id}")

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["SubTotal"], 1234.56)
            self.assertEqual(result["ShippingCost"], 78.90)
            self.assertEqual(result["InvoiceTotal"], 1313.46)
            self.assertEqual(result["Items"][0]["Quantity"], 5.5)
            self.assertEqual(result["Items"][0]["UnitPrice"], 123.45)


if __name__ == '__main__':
    unittest.main()

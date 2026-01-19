import unittest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from db_util import init_db, save_inv_extraction, get_db, get_cursor
from controllers.invoice_controller import InvoiceController
from models.invoice import Invoice
from models.item import Item


class TestInvoiceAPIRealDB(unittest.TestCase):
    """Integration tests for invoice API endpoints using real database connections"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        # Set DB_BACKEND to sqlite for tests
        os.environ['DB_BACKEND'] = 'sqlite'
        # Initialize database
        init_db()

        # Mock OCI client to avoid actual API calls
        self.oci_patcher = patch('oci.ai_document.AIServiceDocumentClient')
        self.config_patcher = patch('oci.config.from_file', return_value={})
        self.oci_patcher.start()
        self.config_patcher.start()

        # Import app - NO mocking of OCI client needed for these tests
        # as we're only testing the database and API endpoints
        from app import app
        self.client = TestClient(app)

    def tearDown(self):
        """Clean up after each test"""
        # Stop OCI patches
        self.oci_patcher.stop()
        self.config_patcher.stop()

        # Clean up test data using controller
        controller = InvoiceController()
        # Get all invoice IDs that start with REAL_DB_TEST_
        with get_db() as conn:
            cursor = get_cursor(conn)
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute(
                    "SELECT InvoiceId FROM invoices WHERE InvoiceId LIKE 'REAL_DB_TEST_%'")
                rows = cursor.fetchall()
                invoice_ids = [row['InvoiceId'] for row in rows]
            else:
                cursor.execute(
                    "SELECT InvoiceId FROM invoices WHERE InvoiceId LIKE 'REAL_DB_TEST_%'")
                rows = cursor.fetchall()
                invoice_ids = [row[0] for row in rows]

        # Delete each test invoice using controller
        for invoice_id in invoice_ids:
            controller.delete_invoice(invoice_id)

    def test_get_invoice_by_id_real_db(self):
        """Test invoice retrieval by ID using real database"""
        test_invoice_id = "REAL_DB_TEST_001"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "RealDBVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 150.0,
                "ShippingCost": 15.0,
                "InvoiceTotal": 165.0,
                "Items": [
                    {
                        "Description": "Real DB Item 1",
                        "Name": "Product 1",
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

        # Save to real database
        save_inv_extraction(test_data)

        # Test GET endpoint
        response = self.client.get(f"/invoices/{test_invoice_id}")

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Validate response structure
        self.assertEqual(result["InvoiceId"], test_invoice_id)
        self.assertEqual(result["VendorName"], "RealDBVendor")
        self.assertEqual(result["InvoiceDate"], "2012-03-06T00:00:00+00:00")
        self.assertEqual(result["BillingAddressRecipient"], "Test Recipient")
        self.assertEqual(result["ShippingAddress"], "123 Test St")
        self.assertEqual(result["SubTotal"], 150.0)
        self.assertEqual(result["ShippingCost"], 15.0)
        self.assertEqual(result["InvoiceTotal"], 165.0)
        self.assertIn("Items", result)
        self.assertEqual(len(result["Items"]), 1)
        self.assertEqual(result["Items"][0]["Description"], "Real DB Item 1")

    def test_get_invoice_by_id_not_found_real_db(self):
        """Test invoice retrieval with non-existent ID using real database"""
        response = self.client.get("/invoices/REAL_DB_TEST_NONEXISTENT")

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertIn("not found", result["detail"].lower())

    def test_get_invoices_by_vendor_real_db(self):
        """Test vendor invoice retrieval using real database"""
        vendor_name = "RealDBVendorMulti"

        # Insert multiple invoices for the same vendor
        test_data_1 = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": "REAL_DB_TEST_VENDOR_001",
                "VendorName": vendor_name,
                "InvoiceDate": "2012-01-01T00:00:00+00:00",
                "BillingAddressRecipient": "Recipient 1",
                "ShippingAddress": "Address 1",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": []
            },
            "dataConfidence": {}
        }

        test_data_2 = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": "REAL_DB_TEST_VENDOR_002",
                "VendorName": vendor_name,
                "InvoiceDate": "2012-02-01T00:00:00+00:00",
                "BillingAddressRecipient": "Recipient 2",
                "ShippingAddress": "Address 2",
                "SubTotal": 200.0,
                "ShippingCost": 20.0,
                "InvoiceTotal": 220.0,
                "Items": []
            },
            "dataConfidence": {}
        }

        # Save to real database
        save_inv_extraction(test_data_1)
        save_inv_extraction(test_data_2)

        # Test GET endpoint
        response = self.client.get(f"/invoices/vendor/{vendor_name}")

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Validate response structure
        self.assertEqual(result["VendorName"], vendor_name)
        self.assertEqual(result["TotalInvoices"], 2)
        self.assertIn("invoices", result)
        self.assertEqual(len(result["invoices"]), 2)

        # Verify invoices are ordered by date (ascending)
        self.assertEqual(result["invoices"][0]
                         ["InvoiceId"], "REAL_DB_TEST_VENDOR_001")
        self.assertEqual(result["invoices"][1]
                         ["InvoiceId"], "REAL_DB_TEST_VENDOR_002")

    def test_get_invoices_by_vendor_not_found_real_db(self):
        """Test vendor invoice retrieval with non-existent vendor using real database"""
        response = self.client.get("/invoices/vendor/NonExistentRealDBVendor")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["VendorName"], "Unknown Vendor")
        self.assertEqual(result["TotalInvoices"], 0)
        self.assertEqual(result["invoices"], [])

    def test_invoice_with_multiple_items_real_db(self):
        """Test invoice with multiple line items using real database"""
        test_invoice_id = "REAL_DB_TEST_MULTI_001"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "RealDBMultiItemVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 350.0,
                "ShippingCost": 35.0,
                "InvoiceTotal": 385.0,
                "Items": [
                    {
                        "Description": "Item 1",
                        "Name": "Product 1",
                        "Quantity": 1,
                        "UnitPrice": 150.0,
                        "Amount": 150.0
                    },
                    {
                        "Description": "Item 2",
                        "Name": "Product 2",
                        "Quantity": 2,
                        "UnitPrice": 100.0,
                        "Amount": 200.0
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

        # Save to real database
        save_inv_extraction(test_data)

        # Test GET endpoint
        response = self.client.get(f"/invoices/{test_invoice_id}")

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["Items"]), 2)
        self.assertEqual(result["Items"][0]["Name"], "Product 1")
        self.assertEqual(result["Items"][1]["Name"], "Product 2")
        self.assertEqual(result["SubTotal"], 350.0)
        self.assertEqual(result["InvoiceTotal"], 385.0)

    def test_database_persistence_real_db(self):
        """Test that data persists correctly in the real database"""
        test_invoice_id = "REAL_DB_TEST_PERSIST_001"
        test_data = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": test_invoice_id,
                "VendorName": "PersistenceTestVendor",
                "InvoiceDate": "2012-03-06T00:00:00+00:00",
                "BillingAddressRecipient": "Test Recipient",
                "ShippingAddress": "123 Test St",
                "SubTotal": 250.0,
                "ShippingCost": 25.0,
                "InvoiceTotal": 275.0,
                "Items": [
                    {
                        "Description": "Persist Item",
                        "Name": "Product",
                        "Quantity": 1,
                        "UnitPrice": 250.0,
                        "Amount": 250.0
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

        # Save to real database
        save_inv_extraction(test_data)

        # Verify data was saved using controller
        controller = InvoiceController()
        invoice = controller.get_invoice_by_id(test_invoice_id)

        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.invoice_id, test_invoice_id)
        self.assertEqual(invoice.vendor_name, "PersistenceTestVendor")
        self.assertEqual(invoice.invoice_total, 275.0)

        # Also verify via API
        response = self.client.get(f"/invoices/{test_invoice_id}")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["InvoiceId"], test_invoice_id)
        self.assertEqual(result["VendorName"], "PersistenceTestVendor")

    def test_vendor_invoice_ordering_real_db(self):
        """Test that vendor invoices are returned in correct date order using real database"""
        vendor_name = "RealDBOrderedVendor"

        # Insert invoices in non-chronological order
        test_data_3 = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": "REAL_DB_TEST_ORDER_003",
                "VendorName": vendor_name,
                "InvoiceDate": "2012-03-01T00:00:00+00:00",
                "BillingAddressRecipient": "Recipient 3",
                "ShippingAddress": "Address 3",
                "SubTotal": 300.0,
                "ShippingCost": 30.0,
                "InvoiceTotal": 330.0,
                "Items": []
            },
            "dataConfidence": {}
        }

        test_data_1 = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": "REAL_DB_TEST_ORDER_001",
                "VendorName": vendor_name,
                "InvoiceDate": "2012-01-01T00:00:00+00:00",
                "BillingAddressRecipient": "Recipient 1",
                "ShippingAddress": "Address 1",
                "SubTotal": 100.0,
                "ShippingCost": 10.0,
                "InvoiceTotal": 110.0,
                "Items": []
            },
            "dataConfidence": {}
        }

        test_data_2 = {
            "confidence": 0.95,
            "data": {
                "InvoiceId": "REAL_DB_TEST_ORDER_002",
                "VendorName": vendor_name,
                "InvoiceDate": "2012-02-01T00:00:00+00:00",
                "BillingAddressRecipient": "Recipient 2",
                "ShippingAddress": "Address 2",
                "SubTotal": 200.0,
                "ShippingCost": 20.0,
                "InvoiceTotal": 220.0,
                "Items": []
            },
            "dataConfidence": {}
        }

        # Insert in non-chronological order
        save_inv_extraction(test_data_3)
        save_inv_extraction(test_data_1)
        save_inv_extraction(test_data_2)

        # Test GET endpoint
        response = self.client.get(f"/invoices/vendor/{vendor_name}")

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Verify invoices are ordered by date (ascending)
        self.assertEqual(len(result["invoices"]), 3)
        self.assertEqual(result["invoices"][0]
                         ["InvoiceId"], "REAL_DB_TEST_ORDER_001")
        self.assertEqual(result["invoices"][1]
                         ["InvoiceId"], "REAL_DB_TEST_ORDER_002")
        self.assertEqual(result["invoices"][2]
                         ["InvoiceId"], "REAL_DB_TEST_ORDER_003")

    def test_invoice_items_ordering_real_db(self):
        """Test that invoice items are returned in correct order using real database"""
        test_invoice_id = "REAL_DB_TEST_ITEMS_ORDER_001"

        # Create invoice and items using controller
        controller = InvoiceController()
        invoice = Invoice(
            invoice_id=test_invoice_id,
            vendor_name="RealDBItemsOrderVendor",
            invoice_date="2012-03-06T00:00:00+00:00",
            billing_address_recipient="Test Recipient",
            shipping_address="123 Test St",
            sub_total=500.0,
            shipping_cost=50.0,
            invoice_total=550.0
        )
        controller.create_or_update_invoice(invoice)

        # Insert items in specific order using controller
        items_data = [
            {"Description": "Item A", "Name": "Product A",
                "Quantity": 1, "UnitPrice": 200.0, "Amount": 200.0},
            {"Description": "Item B", "Name": "Product B",
                "Quantity": 2, "UnitPrice": 150.0, "Amount": 300.0},
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

        # Test GET endpoint
        response = self.client.get(f"/invoices/{test_invoice_id}")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(len(result["Items"]), 2)
        self.assertEqual(result["Items"][0]["Name"], "Product A")
        self.assertEqual(result["Items"][1]["Name"], "Product B")


if __name__ == '__main__':
    unittest.main()

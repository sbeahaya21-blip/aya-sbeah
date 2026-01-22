import unittest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from db import init_db, get_db, SessionLocal
from db_util import save_inv_extraction
from controllers.invoice_controller import InvoiceController
from models.invoice import Invoice
from models.item import Item


class TestInvoiceAPIRealDB(unittest.TestCase):
    """Integration tests for invoice API endpoints using real database connections"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        # Set DB_BACKEND to sqlite for tests
        os.environ['DB_BACKEND'] = 'sqlite'
        # Use shared in-memory database for tests (allows multiple connections)
        self.test_engine = init_db("sqlite:///:memory:?cache=shared")
        
        # Capture the test database SessionLocal before app import
        # Re-import to ensure we get the updated SessionLocal after init_db()
        from db import SessionLocal as UpdatedSessionLocal
        self.test_session_local = UpdatedSessionLocal
        assert self.test_session_local is not None, "SessionLocal must be initialized"
        assert self.test_engine is not None, "Engine must be initialized"

        # Mock OCI client to avoid actual API calls
        self.oci_patcher = patch('oci.ai_document.AIServiceDocumentClient')
        self.config_patcher = patch('oci.config.from_file', return_value={})
        self.oci_patcher.start()
        self.config_patcher.start()

        # Import app - NO mocking of OCI client needed for these tests
        # as we're only testing the database and API endpoints
        from app import app
        
        # Create a test-specific get_db function that uses the test database
        def get_test_db():
            db = self.test_session_local()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = get_test_db
        self.client = TestClient(app)

    def _setup_app_dependency_override(self, app):
        """Helper method to set up dependency override for test database"""
        # Ensure we have a valid SessionLocal and tables are created
        if self.test_session_local is None or self.test_engine is None:
            self.test_engine = init_db("sqlite:///:memory:?cache=shared")
            from db import SessionLocal as UpdatedSessionLocal
            self.test_session_local = UpdatedSessionLocal
        
        # Ensure tables exist for the test database
        # Create tables using the engine bound to this sessionmaker
        from db import Base
        # Use the stored engine directly - it's bound to our sessionmaker
        Base.metadata.create_all(bind=self.test_engine)
        
        # Note: TestClient(app) without context manager doesn't run startup events
        # But we ensure tables exist anyway in case startup does run
        
        def get_test_db():
            db = self.test_session_local()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = get_test_db

    def tearDown(self):
        """Clean up after each test"""
        # Stop OCI patches
        self.oci_patcher.stop()
        self.config_patcher.stop()

        # Clear dependency overrides
        from app import app
        app.dependency_overrides.clear()

        # Clean up test data using SQLAlchemy (use test database directly)
        db = self.test_session_local()
        try:
            from models.invoice import Invoice
            test_invoices = db.query(Invoice).filter(
                Invoice.invoice_id.like('REAL_DB_TEST_%')
            ).all()
            invoice_ids = [inv.invoice_id for inv in test_invoices]

            # Delete each test invoice using controller
            controller = InvoiceController()
            for invoice_id in invoice_ids:
                controller.delete_invoice(invoice_id, db)
            db.commit()
        finally:
            db.close()

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

        # Save to real database (use test database directly)
        db = self.test_session_local()
        try:
            save_inv_extraction(test_data, db)
            db.commit()
        finally:
            db.close()

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

        # Save to real database (use test database directly)
        db = self.test_session_local()
        try:
            save_inv_extraction(test_data_1, db)
            save_inv_extraction(test_data_2, db)
            db.commit()
        finally:
            db.close()

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

        # Save to real database (use test database directly)
        db = self.test_session_local()
        try:
            save_inv_extraction(test_data, db)
            db.commit()
        finally:
            db.close()

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

        # Save to real database (use test database directly)
        db = self.test_session_local()
        try:
            save_inv_extraction(test_data, db)
            db.commit()
        finally:
            db.close()

        # Verify data was saved using controller (use test database directly)
        db = self.test_session_local()
        try:
            controller = InvoiceController()
            invoice = controller.get_invoice_by_id(test_invoice_id, db)

            self.assertIsNotNone(invoice)
        finally:
            db.close()
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

        # Insert in non-chronological order (use test database directly)
        db = self.test_session_local()
        try:
            save_inv_extraction(test_data_3, db)
            save_inv_extraction(test_data_1, db)
            save_inv_extraction(test_data_2, db)
            db.commit()
        finally:
            db.close()

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

        # Create invoice and items using controller (use test database directly)
        db = self.test_session_local()
        try:
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
            controller.create_or_update_invoice(invoice, db)

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
                controller.create_item(item, db)
            db.commit()
        finally:
            db.close()

        # Test GET endpoint
        response = self.client.get(f"/invoices/{test_invoice_id}")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(len(result["Items"]), 2)
        self.assertEqual(result["Items"][0]["Name"], "Product A")
        self.assertEqual(result["Items"][1]["Name"], "Product B")


if __name__ == '__main__':
    unittest.main()

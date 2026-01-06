import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
import json
import os
import sys
from db_util import init_db


class TestExtractAPI(unittest.TestCase):
    """Comprehensive API tests for the /extract endpoint"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        # Initialize database
        init_db()

    def tearDown(self):
        """Clean up after each test"""
        # Reload app module to reset any module-level state
        if 'app' in sys.modules:
            del sys.modules['app']

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_success_valid_pdf(self, mock_config, mock_client_class):
        """Test successful extraction with valid PDF file"""
        # Setup mock client BEFORE importing app
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock successful OCI response
        mock_analyze.return_value = self._create_mock_response(
            confidence=0.95,
            vendor_name="SuperStore",
            invoice_id="36259",
            invoice_date="Mar 06 2012"
        )

        # Import app AFTER patching
        from app import app, get_doc_client
        # Replace the client getter with our mock
        get_doc_client._client = mock_client_instance

        client = TestClient(app)

        # Test with valid PDF file
        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 200)
            result = response.json()

            # Validate response structure
            self.assertIn("confidence", result)
            self.assertIn("data", result)
            self.assertIn("dataConfidence", result)
            self.assertEqual(result["confidence"], 0.95)
            self.assertIn("VendorName", result["data"])

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_invalid_file_type(self, mock_config, mock_client_class):
        """Test extract endpoint with invalid file type (not PDF)"""
        from app import app
        client = TestClient(app)

        # Test with non-PDF file
        response = client.post(
            "/extract",
            files={"file": ("test.txt", b"not a pdf", "text/plain")}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid document", response.json()["detail"])

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_low_confidence(self, mock_config, mock_client_class):
        """Test extract endpoint with low confidence document"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock low confidence response
        mock_analyze.return_value = self._create_mock_response(
            confidence=0.85,  # Below 0.9 threshold
            vendor_name="TestVendor",
            invoice_id="12345",
            invoice_date="Jan 01 2020"
        )

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("Invalid document", response.json()["detail"])

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_oci_service_error(self, mock_config, mock_client_class):
        """Test extract endpoint when OCI service fails"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock OCI service exception
        mock_analyze.side_effect = Exception("OCI Service Error")

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 503)
            self.assertIn("unavailable", response.json()["detail"].lower())

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_with_items(self, mock_config, mock_client_class):
        """Test extract endpoint with invoice items"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock response with items
        mock_analyze.return_value = self._create_mock_response_with_items(
            confidence=0.95,
            vendor_name="SuperStore",
            invoice_id="36259",
            invoice_date="Mar 06 2012",
            items=[
                {
                    "Description": "Product 1",
                    "Name": "Product 1",
                    "Quantity": 2,
                    "UnitPrice": 10.50,
                    "Amount": 21.00
                }
            ]
        )

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertIn("Items", result["data"])
            self.assertEqual(len(result["data"]["Items"]), 1)
            self.assertEqual(result["data"]["Items"][0]
                             ["Description"], "Product 1")

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_amount_formatting(self, mock_config, mock_client_class):
        """Test that amount fields are properly formatted"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock response with formatted amounts
        mock_analyze.return_value = self._create_mock_response(
            confidence=0.95,
            vendor_name="SuperStore",
            invoice_id="36259",
            invoice_date="Mar 06 2012",
            invoice_total="$1,234.56",
            sub_total="$1,000.00"
        )

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 200)
            result = response.json()
            # Amounts should be converted to float
            self.assertIsInstance(result["data"].get(
                "InvoiceTotal"), (float, int))
            self.assertIsInstance(result["data"].get("SubTotal"), (float, int))

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_date_formatting(self, mock_config, mock_client_class):
        """Test that date fields are properly formatted"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock response with date
        mock_analyze.return_value = self._create_mock_response(
            confidence=0.95,
            vendor_name="SuperStore",
            invoice_id="36259",
            invoice_date="Mar 06 2012"
        )

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            self.assertEqual(response.status_code, 200)
            result = response.json()
            # Date should be ISO formatted
            date_value = result["data"].get("InvoiceDate")
            if date_value:
                self.assertIn("T", date_value)  # ISO format contains 'T'
                self.assertIn("+00:00", date_value)  # UTC timezone

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_missing_file(self, mock_config, mock_client_class):
        """Test extract endpoint without file"""
        from app import app
        client = TestClient(app)

        response = client.post("/extract")

        self.assertEqual(response.status_code, 422)  # FastAPI validation error

    @patch('oci.ai_document.AIServiceDocumentClient')
    @patch('oci.config.from_file', return_value={})
    def test_extract_empty_response(self, mock_config, mock_client_class):
        """Test extract endpoint with empty OCI response"""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        mock_analyze = mock_client_instance.analyze_document

        # Mock empty response
        mock_analyze.return_value = type('obj', (object,), {
            'data': None
        })()

        from app import app, get_doc_client
        get_doc_client._client = mock_client_instance
        client = TestClient(app)

        test_file_path = "invoices_sample/invoice_Aaron_Bergman_36259.pdf"
        if os.path.exists(test_file_path):
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/extract",
                    files={"file": ("test_invoice.pdf", f, "application/pdf")}
                )

            # Should handle gracefully
            self.assertIn(response.status_code, [200, 400])

    def _create_mock_response(self, confidence=0.95, vendor_name="TestVendor",
                              invoice_id="12345", invoice_date="Jan 01 2020",
                              invoice_total=100.0, sub_total=90.0):
        """Helper method to create mock OCI response"""
        return type('obj', (object,), {
            'data': type('obj', (object,), {
                'detected_document_types': [
                    type('obj', (object,), {
                        'document_type': 'INVOICE',
                        'confidence': confidence
                    })()
                ],
                'pages': [
                    type('obj', (object,), {
                        'document_fields': [
                            type('obj', (object,), {
                                'field_label': type('obj', (object,), {
                                    'name': 'VendorName',
                                    'confidence': 0.95
                                })(),
                                'field_value': type('obj', (object,), {
                                    'value': vendor_name
                                })()
                            })(),
                            type('obj', (object,), {
                                'field_label': type('obj', (object,), {
                                    'name': 'InvoiceId',
                                    'confidence': 0.99
                                })(),
                                'field_value': type('obj', (object,), {
                                    'value': invoice_id
                                })()
                            })(),
                            type('obj', (object,), {
                                'field_label': type('obj', (object,), {
                                    'name': 'InvoiceDate',
                                    'confidence': 0.99
                                })(),
                                'field_value': type('obj', (object,), {
                                    'value': invoice_date
                                })()
                            })(),
                            type('obj', (object,), {
                                'field_label': type('obj', (object,), {
                                    'name': 'InvoiceTotal',
                                    'confidence': 0.99
                                })(),
                                'field_value': type('obj', (object,), {
                                    'value': invoice_total
                                })()
                            })(),
                            type('obj', (object,), {
                                'field_label': type('obj', (object,), {
                                    'name': 'SubTotal',
                                    'confidence': 0.95
                                })(),
                                'field_value': type('obj', (object,), {
                                    'value': sub_total
                                })()
                            })()
                        ]
                    })()
                ]
            })()
        })()

    def _create_mock_response_with_items(self, confidence=0.95, vendor_name="TestVendor",
                                         invoice_id="12345", invoice_date="Jan 01 2020",
                                         items=None):
        """Helper method to create mock OCI response with items"""
        if items is None:
            items = []

        item_fields = []
        for item in items:
            item_sub_fields = []
            for key, value in item.items():
                item_sub_fields.append(
                    type('obj', (object,), {
                        'field_label': type('obj', (object,), {'name': key})(),
                        'field_value': type('obj', (object,), {'value': value})()
                    })()
                )

            item_fields.append(
                type('obj', (object,), {
                    'field_value': type('obj', (object,), {
                        'items': item_sub_fields
                    })()
                })()
            )

        # Create document fields list
        document_fields = [
            type('obj', (object,), {
                'field_label': type('obj', (object,), {
                    'name': 'VendorName',
                    'confidence': 0.95
                })(),
                'field_value': type('obj', (object,), {
                    'value': vendor_name
                })()
            })(),
            type('obj', (object,), {
                'field_label': type('obj', (object,), {
                    'name': 'InvoiceId',
                    'confidence': 0.99
                })(),
                'field_value': type('obj', (object,), {
                    'value': invoice_id
                })()
            })(),
            type('obj', (object,), {
                'field_label': type('obj', (object,), {
                    'name': 'InvoiceDate',
                    'confidence': 0.99
                })(),
                'field_value': type('obj', (object,), {
                    'value': invoice_date
                })()
            })(),
            type('obj', (object,), {
                'field_label': type('obj', (object,), {
                    'name': 'Items',
                    'confidence': None
                })(),
                'field_value': type('obj', (object,), {
                    'items': item_fields
                })()
            })()
        ]

        return type('obj', (object,), {
            'data': type('obj', (object,), {
                'detected_document_types': [
                    type('obj', (object,), {
                        'document_type': 'INVOICE',
                        'confidence': confidence
                    })()
                ],
                'pages': [
                    type('obj', (object,), {
                        'document_fields': document_fields
                    })()
                ]
            })()
        })()


if __name__ == '__main__':
    unittest.main()

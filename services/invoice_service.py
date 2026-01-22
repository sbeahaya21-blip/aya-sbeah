"""Service layer for invoice operations"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from db import get_db
from models.invoice import Invoice, InvoiceConfidence
from models.item import Item
from controllers.invoice_controller import InvoiceController


def save_inv_extraction(result: Dict[str, Any], db: Session):
    """
    Save invoice extraction result to database.
    
    Args:
        result: Dictionary containing extraction result with 'data' and 'dataConfidence' keys
        db: Database session (required)
    
    This function saves the extracted invoice data, confidence scores, and line items
    to the database using the InvoiceController.
    """
    controller = InvoiceController()

    data = result.get("data", {})
    data_confidence = result.get("dataConfidence", {})

    invoice_id = data.get("InvoiceId")
    if invoice_id:
        # Create invoice
        invoice = Invoice.from_dict(data)
        controller.create_or_update_invoice(invoice, db)

        # Create confidence
        confidence = InvoiceConfidence.from_dict(invoice_id, data_confidence)
        controller.create_or_update_confidence(confidence, db)

        # Create items
        line_items = data.get("Items", [])
        for item_data in line_items:
            item = Item.from_dict(invoice_id, item_data)
            controller.create_item(item, db)

"""Invoice controller with CRUD operations using SQLAlchemy ORM"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models.invoice import Invoice, InvoiceConfidence
from models.item import Item
from fastapi import HTTPException


class InvoiceController:
    """Controller for invoice-related database operations using SQLAlchemy ORM"""

    # ========== INVOICE CRUD OPERATIONS ==========

    def create_or_update_invoice(self, invoice: Invoice, db: Session) -> Invoice:
        """Create or update an invoice"""
        try:
            # Check if invoice exists
            existing = db.query(Invoice).filter(Invoice.invoice_id == invoice.invoice_id).first()
            
            if existing:
                # Update existing invoice
                existing.vendor_name = invoice.vendor_name
                existing.invoice_date = invoice.invoice_date
                existing.billing_address_recipient = invoice.billing_address_recipient
                existing.shipping_address = invoice.shipping_address
                existing.sub_total = invoice.sub_total
                existing.shipping_cost = invoice.shipping_cost
                existing.invoice_total = invoice.invoice_total
                db.commit()
                db.refresh(existing)
                return existing
            else:
                # Create new invoice
                db.add(invoice)
                db.commit()
                db.refresh(invoice)
                return invoice
        except IntegrityError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise

    def get_invoice_by_id(self, invoice_id: str, db: Session) -> Optional[Invoice]:
        """Get an invoice by ID"""
        return db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()

    def get_invoices_by_vendor(self, vendor_name: str, db: Session) -> List[str]:
        """Get invoice IDs for a specific vendor, ordered by date"""
        invoices = db.query(Invoice).filter(
            Invoice.vendor_name == vendor_name
        ).order_by(Invoice.invoice_date.asc()).all()
        return [invoice.invoice_id for invoice in invoices]

    def update_invoice(self, invoice: Invoice, db: Session) -> Invoice:
        """Update an existing invoice"""
        existing = db.query(Invoice).filter(Invoice.invoice_id == invoice.invoice_id).first()
        if not existing:
            raise ValueError(f"Invoice with ID {invoice.invoice_id} not found")

        existing.vendor_name = invoice.vendor_name
        existing.invoice_date = invoice.invoice_date
        existing.billing_address_recipient = invoice.billing_address_recipient
        existing.shipping_address = invoice.shipping_address
        existing.sub_total = invoice.sub_total
        existing.shipping_cost = invoice.shipping_cost
        existing.invoice_total = invoice.invoice_total

        db.commit()
        db.refresh(existing)
        return existing

    def delete_invoice(self, invoice_id: str, db: Session) -> bool:
        """Delete an invoice and its related data (cascade deletes items and confidences)"""
        invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
        if not invoice:
            return False

        db.delete(invoice)
        db.commit()
        return True

    # ========== CONFIDENCE CRUD OPERATIONS ==========

    def create_or_update_confidence(self, confidence: InvoiceConfidence, db: Session) -> InvoiceConfidence:
        """Create or update invoice confidence scores"""
        try:
            existing = db.query(InvoiceConfidence).filter(
                InvoiceConfidence.invoice_id == confidence.invoice_id
            ).first()

            if existing:
                # Update existing confidence
                existing.vendor_name = confidence.vendor_name
                existing.invoice_date = confidence.invoice_date
                existing.billing_address_recipient = confidence.billing_address_recipient
                existing.shipping_address = confidence.shipping_address
                existing.sub_total = confidence.sub_total
                existing.shipping_cost = confidence.shipping_cost
                existing.invoice_total = confidence.invoice_total
                db.commit()
                db.refresh(existing)
                return existing
            else:
                # Create new confidence
                db.add(confidence)
                db.commit()
                db.refresh(confidence)
                return confidence
        except IntegrityError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise

    def get_confidence_by_invoice_id(self, invoice_id: str, db: Session) -> Optional[InvoiceConfidence]:
        """Get confidence scores for an invoice"""
        return db.query(InvoiceConfidence).filter(
            InvoiceConfidence.invoice_id == invoice_id
        ).first()

    # ========== ITEM CRUD OPERATIONS ==========

    def create_item(self, item: Item, db: Session) -> Item:
        """Create a new invoice line item"""
        try:
            db.add(item)
            db.commit()
            db.refresh(item)
            return item
        except IntegrityError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise

    def get_items_by_invoice_id(self, invoice_id: str, db: Session) -> List[Item]:
        """Get all items for an invoice"""
        return db.query(Item).filter(
            Item.invoice_id == invoice_id
        ).order_by(Item.id.asc()).all()

    def update_item(self, item: Item, db: Session) -> Item:
        """Update an existing item"""
        if item.id is None:
            raise ValueError("Item ID is required for update")

        existing = db.query(Item).filter(Item.id == item.id).first()
        if not existing:
            raise ValueError(f"Item with ID {item.id} not found")

        existing.description = item.description
        existing.name = item.name
        existing.quantity = item.quantity
        existing.unit_price = item.unit_price
        existing.amount = item.amount

        db.commit()
        db.refresh(existing)
        return existing

    def delete_item(self, item_id: int, db: Session) -> bool:
        """Delete an item by ID"""
        item = db.query(Item).filter(Item.id == item_id).first()
        if not item:
            return False

        db.delete(item)
        db.commit()
        return True

    def delete_items_by_invoice_id(self, invoice_id: str, db: Session) -> int:
        """Delete all items for an invoice"""
        deleted_count = db.query(Item).filter(Item.invoice_id == invoice_id).delete()
        db.commit()
        return deleted_count

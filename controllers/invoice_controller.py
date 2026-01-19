"""Invoice controller with CRUD operations"""
import os
from typing import Optional, List, Dict, Any
from db_util import get_db, get_cursor
from models.invoice import Invoice, InvoiceConfidence
from models.item import Item
from fastapi import HTTPException


class InvoiceController:
    """Controller for invoice-related database operations"""
    
    # ========== INVOICE CRUD OPERATIONS ==========
    
    def create_or_update_invoice(self, invoice: Invoice) -> Invoice:
        """Create or update an invoice"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    INSERT INTO invoices 
                    (InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient, 
                     ShippingAddress, SubTotal, ShippingCost, InvoiceTotal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (InvoiceId) DO UPDATE SET
                        VendorName = EXCLUDED.VendorName,
                        InvoiceDate = EXCLUDED.InvoiceDate,
                        BillingAddressRecipient = EXCLUDED.BillingAddressRecipient,
                        ShippingAddress = EXCLUDED.ShippingAddress,
                        SubTotal = EXCLUDED.SubTotal,
                        ShippingCost = EXCLUDED.ShippingCost,
                        InvoiceTotal = EXCLUDED.InvoiceTotal
                """, (
                    invoice.invoice_id,
                    invoice.vendor_name,
                    invoice.invoice_date,
                    invoice.billing_address_recipient,
                    invoice.shipping_address,
                    invoice.sub_total,
                    invoice.shipping_cost,
                    invoice.invoice_total
                ))
            else:  # SQLite
                cursor.execute("""
                    INSERT OR REPLACE INTO invoices 
                    (InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient, 
                     ShippingAddress, SubTotal, ShippingCost, InvoiceTotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice.invoice_id,
                    invoice.vendor_name,
                    invoice.invoice_date,
                    invoice.billing_address_recipient,
                    invoice.shipping_address,
                    invoice.sub_total,
                    invoice.shipping_cost,
                    invoice.invoice_total
                ))
            
            conn.commit()
            return invoice
    
    def get_invoice_by_id(self, invoice_id: str) -> Optional[Invoice]:
        """Get an invoice by ID"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    SELECT InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                           ShippingAddress, SubTotal, ShippingCost, InvoiceTotal
                    FROM invoices
                    WHERE InvoiceId = %s
                """, (invoice_id,))
            else:  # SQLite
                cursor.execute("""
                    SELECT InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                           ShippingAddress, SubTotal, ShippingCost, InvoiceTotal
                    FROM invoices
                    WHERE InvoiceId = ?
                """, (invoice_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                # PostgreSQL returns dict-like row
                return Invoice(
                    invoice_id=row['InvoiceId'],
                    vendor_name=row['VendorName'],
                    invoice_date=row['InvoiceDate'],
                    billing_address_recipient=row['BillingAddressRecipient'],
                    shipping_address=row['ShippingAddress'],
                    sub_total=row['SubTotal'],
                    shipping_cost=row['ShippingCost'],
                    invoice_total=row['InvoiceTotal']
                )
            else:  # SQLite returns tuple
                return Invoice(
                    invoice_id=row[0],
                    vendor_name=row[1],
                    invoice_date=row[2],
                    billing_address_recipient=row[3],
                    shipping_address=row[4],
                    sub_total=row[5],
                    shipping_cost=row[6],
                    invoice_total=row[7]
                )
    
    def get_invoices_by_vendor(self, vendor_name: str) -> List[str]:
        """Get invoice IDs for a specific vendor, ordered by date"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    SELECT InvoiceId
                    FROM invoices
                    WHERE VendorName = %s
                    ORDER BY InvoiceDate ASC
                """, (vendor_name,))
            else:  # SQLite
                cursor.execute("""
                    SELECT InvoiceId
                    FROM invoices
                    WHERE VendorName = ?
                    ORDER BY InvoiceDate ASC
                """, (vendor_name,))
            
            rows = cursor.fetchall()
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                return [row['InvoiceId'] for row in rows]
            else:
                return [row[0] for row in rows]
    
    def update_invoice(self, invoice: Invoice) -> Invoice:
        """Update an existing invoice"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    UPDATE invoices SET
                        VendorName = %s,
                        InvoiceDate = %s,
                        BillingAddressRecipient = %s,
                        ShippingAddress = %s,
                        SubTotal = %s,
                        ShippingCost = %s,
                        InvoiceTotal = %s
                    WHERE InvoiceId = %s
                """, (
                    invoice.vendor_name,
                    invoice.invoice_date,
                    invoice.billing_address_recipient,
                    invoice.shipping_address,
                    invoice.sub_total,
                    invoice.shipping_cost,
                    invoice.invoice_total,
                    invoice.invoice_id
                ))
            else:  # SQLite
                cursor.execute("""
                    UPDATE invoices SET
                        VendorName = ?,
                        InvoiceDate = ?,
                        BillingAddressRecipient = ?,
                        ShippingAddress = ?,
                        SubTotal = ?,
                        ShippingCost = ?,
                        InvoiceTotal = ?
                    WHERE InvoiceId = ?
                """, (
                    invoice.vendor_name,
                    invoice.invoice_date,
                    invoice.billing_address_recipient,
                    invoice.shipping_address,
                    invoice.sub_total,
                    invoice.shipping_cost,
                    invoice.invoice_total,
                    invoice.invoice_id
                ))
            
            conn.commit()
            return invoice
    
    def delete_invoice(self, invoice_id: str) -> bool:
        """Delete an invoice and its related data"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            # Delete items first (foreign key constraint)
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("DELETE FROM items WHERE InvoiceId = %s", (invoice_id,))
                cursor.execute("DELETE FROM confidences WHERE InvoiceId = %s", (invoice_id,))
                cursor.execute("DELETE FROM invoices WHERE InvoiceId = %s", (invoice_id,))
            else:  # SQLite
                cursor.execute("DELETE FROM items WHERE InvoiceId = ?", (invoice_id,))
                cursor.execute("DELETE FROM confidences WHERE InvoiceId = ?", (invoice_id,))
                cursor.execute("DELETE FROM invoices WHERE InvoiceId = ?", (invoice_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== CONFIDENCE CRUD OPERATIONS ==========
    
    def create_or_update_confidence(self, confidence: InvoiceConfidence) -> InvoiceConfidence:
        """Create or update invoice confidence scores"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    INSERT INTO confidences 
                    (InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                     ShippingAddress, SubTotal, ShippingCost, InvoiceTotal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (InvoiceId) DO UPDATE SET
                        VendorName = EXCLUDED.VendorName,
                        InvoiceDate = EXCLUDED.InvoiceDate,
                        BillingAddressRecipient = EXCLUDED.BillingAddressRecipient,
                        ShippingAddress = EXCLUDED.ShippingAddress,
                        SubTotal = EXCLUDED.SubTotal,
                        ShippingCost = EXCLUDED.ShippingCost,
                        InvoiceTotal = EXCLUDED.InvoiceTotal
                """, (
                    confidence.invoice_id,
                    confidence.vendor_name,
                    confidence.invoice_date,
                    confidence.billing_address_recipient,
                    confidence.shipping_address,
                    confidence.sub_total,
                    confidence.shipping_cost,
                    confidence.invoice_total
                ))
            else:  # SQLite
                cursor.execute("""
                    INSERT OR REPLACE INTO confidences 
                    (InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                     ShippingAddress, SubTotal, ShippingCost, InvoiceTotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    confidence.invoice_id,
                    confidence.vendor_name,
                    confidence.invoice_date,
                    confidence.billing_address_recipient,
                    confidence.shipping_address,
                    confidence.sub_total,
                    confidence.shipping_cost,
                    confidence.invoice_total
                ))
            
            conn.commit()
            return confidence
    
    def get_confidence_by_invoice_id(self, invoice_id: str) -> Optional[InvoiceConfidence]:
        """Get confidence scores for an invoice"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    SELECT InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                           ShippingAddress, SubTotal, ShippingCost, InvoiceTotal
                    FROM confidences
                    WHERE InvoiceId = %s
                """, (invoice_id,))
            else:  # SQLite
                cursor.execute("""
                    SELECT InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
                           ShippingAddress, SubTotal, ShippingCost, InvoiceTotal
                    FROM confidences
                    WHERE InvoiceId = ?
                """, (invoice_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                return InvoiceConfidence(
                    invoice_id=row['InvoiceId'],
                    vendor_name=row['VendorName'],
                    invoice_date=row['InvoiceDate'],
                    billing_address_recipient=row['BillingAddressRecipient'],
                    shipping_address=row['ShippingAddress'],
                    sub_total=row['SubTotal'],
                    shipping_cost=row['ShippingCost'],
                    invoice_total=row['InvoiceTotal']
                )
            else:
                return InvoiceConfidence(
                    invoice_id=row[0],
                    vendor_name=row[1],
                    invoice_date=row[2],
                    billing_address_recipient=row[3],
                    shipping_address=row[4],
                    sub_total=row[5],
                    shipping_cost=row[6],
                    invoice_total=row[7]
                )
    
    # ========== ITEM CRUD OPERATIONS ==========
    
    def create_item(self, item: Item) -> Item:
        """Create a new invoice line item"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    INSERT INTO items 
                    (InvoiceId, Description, Name, Quantity, UnitPrice, Amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    item.invoice_id,
                    item.description,
                    item.name,
                    item.quantity,
                    item.unit_price,
                    item.amount
                ))
                item.id = cursor.fetchone()['id']
            else:  # SQLite
                cursor.execute("""
                    INSERT INTO items 
                    (InvoiceId, Description, Name, Quantity, UnitPrice, Amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item.invoice_id,
                    item.description,
                    item.name,
                    item.quantity,
                    item.unit_price,
                    item.amount
                ))
                item.id = cursor.lastrowid
            
            conn.commit()
            return item
    
    def get_items_by_invoice_id(self, invoice_id: str) -> List[Item]:
        """Get all items for an invoice"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    SELECT id, InvoiceId, Description, Name, Quantity, UnitPrice, Amount
                    FROM items
                    WHERE InvoiceId = %s
                    ORDER BY id ASC
                """, (invoice_id,))
            else:  # SQLite
                cursor.execute("""
                    SELECT id, InvoiceId, Description, Name, Quantity, UnitPrice, Amount
                    FROM items
                    WHERE InvoiceId = ?
                    ORDER BY id ASC
                """, (invoice_id,))
            
            rows = cursor.fetchall()
            items = []
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                for row in rows:
                    items.append(Item(
                        invoice_id=row['InvoiceId'],
                        description=row['Description'],
                        name=row['Name'],
                        quantity=row['Quantity'],
                        unit_price=row['UnitPrice'],
                        amount=row['Amount'],
                        id=row['id']
                    ))
            else:
                for row in rows:
                    items.append(Item(
                        invoice_id=row[1],
                        description=row[2],
                        name=row[3],
                        quantity=row[4],
                        unit_price=row[5],
                        amount=row[6],
                        id=row[0]
                    ))
            
            return items
    
    def update_item(self, item: Item) -> Item:
        """Update an existing item"""
        if item.id is None:
            raise ValueError("Item ID is required for update")
        
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("""
                    UPDATE items SET
                        Description = %s,
                        Name = %s,
                        Quantity = %s,
                        UnitPrice = %s,
                        Amount = %s
                    WHERE id = %s
                """, (
                    item.description,
                    item.name,
                    item.quantity,
                    item.unit_price,
                    item.amount,
                    item.id
                ))
            else:  # SQLite
                cursor.execute("""
                    UPDATE items SET
                        Description = ?,
                        Name = ?,
                        Quantity = ?,
                        UnitPrice = ?,
                        Amount = ?
                    WHERE id = ?
                """, (
                    item.description,
                    item.name,
                    item.quantity,
                    item.unit_price,
                    item.amount,
                    item.id
                ))
            
            conn.commit()
            return item
    
    def delete_item(self, item_id: int) -> bool:
        """Delete an item by ID"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
            else:  # SQLite
                cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_items_by_invoice_id(self, invoice_id: str) -> int:
        """Delete all items for an invoice"""
        with get_db() as conn:
            cursor = get_cursor(conn)
            
            if os.getenv('DB_BACKEND', 'sqlite').lower() == 'postgresql':
                cursor.execute("DELETE FROM items WHERE InvoiceId = %s", (invoice_id,))
            else:  # SQLite
                cursor.execute("DELETE FROM items WHERE InvoiceId = ?", (invoice_id,))
            
            conn.commit()
            return cursor.rowcount


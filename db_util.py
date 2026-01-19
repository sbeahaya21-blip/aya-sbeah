"""Database utility supporting both SQLite and PostgreSQL"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

# Try to import PostgreSQL adapter
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

DB_BACKEND = os.getenv('DB_BACKEND', 'sqlite').lower()
DB_PATH = os.getenv('DB_PATH', 'invoices.db')

# PostgreSQL connection parameters
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = os.getenv('PG_PORT', '5432')
PG_DATABASE = os.getenv('PG_DATABASE', 'invoices')
PG_USER = os.getenv('PG_USER', 'postgres')
PG_PASSWORD = os.getenv('PG_PASSWORD', '')


@contextmanager
def get_db():
    """
    Get database connection based on DB_BACKEND environment variable.
    Supports 'sqlite' and 'postgresql'.
    """
    if DB_BACKEND == 'postgresql':
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQL. Install it with: pip install psycopg2-binary"
            )
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:  # Default to SQLite
        conn = sqlite3.connect(DB_PATH)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def get_cursor(conn):
    """Get appropriate cursor based on database backend"""
    if DB_BACKEND == 'postgresql':
        return conn.cursor(cursor_factory=RealDictCursor)
    else:  # SQLite
        return conn.cursor()


def init_db():
    """Initialize database tables for both SQLite and PostgreSQL"""
    with get_db() as conn:
        cursor = get_cursor(conn)

        # Determine auto increment syntax based on backend
        if DB_BACKEND == 'postgresql':
            id_type = "SERIAL PRIMARY KEY"
            text_type = "TEXT"
            real_type = "REAL"
            foreign_key_syntax = "FOREIGN KEY (InvoiceId) REFERENCES invoices(InvoiceId)"
            create_if_not_exists = "CREATE TABLE IF NOT EXISTS"
        else:  # SQLite
            id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
            text_type = "TEXT"
            real_type = "REAL"
            foreign_key_syntax = "FOREIGN KEY (InvoiceId) REFERENCES invoices(InvoiceId)"
            create_if_not_exists = "CREATE TABLE IF NOT EXISTS"

        # Create invoices table
        cursor.execute(f"""
            {create_if_not_exists} invoices (
                InvoiceId {text_type} PRIMARY KEY,
                VendorName {text_type},
                InvoiceDate {text_type},
                BillingAddressRecipient {text_type},
                ShippingAddress {text_type},
                SubTotal {real_type},
                ShippingCost {real_type},
                InvoiceTotal {real_type}
            )
        """)

        # Create confidences table
        cursor.execute(f"""
            {create_if_not_exists} confidences (
                InvoiceId {text_type} PRIMARY KEY,
                VendorName {real_type},
                InvoiceDate {real_type},
                BillingAddressRecipient {real_type},
                ShippingAddress {real_type},
                SubTotal {real_type},
                ShippingCost {real_type},
                InvoiceTotal {real_type},
                {foreign_key_syntax}
            )
        """)

        # Create items table
        cursor.execute(f"""
            {create_if_not_exists} items (
                id {id_type},
                InvoiceId {text_type},
                Description {text_type},
                Name {text_type},
                Quantity {real_type},
                UnitPrice {real_type},
                Amount {real_type},
                {foreign_key_syntax}
            )
        """)

        conn.commit()


def save_inv_extraction(result):
    """
    Save invoice extraction result to database.
    This function is kept for backward compatibility but uses the new model structure.
    """
    from models.invoice import Invoice, InvoiceConfidence
    from models.item import Item
    from controllers.invoice_controller import InvoiceController

    controller = InvoiceController()

    data = result.get("data", {})
    data_confidence = result.get("dataConfidence", {})

    invoice_id = data.get("InvoiceId")
    if invoice_id:
        # Create invoice
        invoice = Invoice.from_dict(data)
        controller.create_or_update_invoice(invoice)

        # Create confidence
        confidence = InvoiceConfidence.from_dict(invoice_id, data_confidence)
        controller.create_or_update_confidence(confidence)

        # Create items
        line_items = data.get("Items", [])
        for item_data in line_items:
            item = Item.from_dict(invoice_id, item_data)
            controller.create_item(item)

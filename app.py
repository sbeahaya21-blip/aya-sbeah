import uvicorn
from fastapi import FastAPI, UploadFile, File, Depends
from sqlalchemy.orm import Session
import oci
import base64
import json
from fastapi import HTTPException
from contextlib import asynccontextmanager
from db import init_db, get_db, init_multi_db, get_db_by_name, list_databases
from services.invoice_service import save_inv_extraction
from controllers.invoice_controller import InvoiceController
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup: Initialize database(s)
    # Check if multiple databases are configured
    secondary_databases = {}
    
    # Check for additional database URLs in environment
    # Format: DB_NAME_URL=connection_string (e.g., ANALYTICS_DB_URL=postgresql://...)
    for env_var in os.environ:
        if env_var.endswith('_DB_URL') and env_var != 'DATABASE_URL':
            db_name = env_var.replace('_DB_URL', '').lower()
            db_url = os.environ[env_var]
            secondary_databases[db_name] = db_url
    
    if secondary_databases:
        # Initialize multiple databases
        primary_url = os.getenv("DATABASE_URL")
        init_multi_db(primary_db_url=primary_url, **secondary_databases)
    else:
        # Use single database (default behavior)
        init_db()
    
    yield
    # Shutdown: Add any cleanup code here if needed


app = FastAPI(lifespan=lifespan)


# Lazy initialization for OCI client (allows testing with mocks)


def get_doc_client():
    """Get or create the OCI document client (lazy initialization)"""
    if not hasattr(get_doc_client, '_client'):
        try:
            config = oci.config.from_file()
            get_doc_client._client = oci.ai_document.AIServiceDocumentClient(
                config)
        except (oci.exceptions.ConfigFileNotFound, oci.exceptions.InvalidKeyFilePath) as e:
            raise HTTPException(
                status_code=503,
                detail=f"OCI configuration error: {str(e)}"
            )
    return get_doc_client._client


@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    # ---------- PDF VALIDATION ----------
    pdf_type = file.content_type == "application/pdf"
    pdf_filename = file.filename.lower().endswith(".pdf")

    if not (pdf_type or pdf_filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid document. Please upload a valid PDF invoice with high confidence."
        )

    # ---------- ENCODE DOCUMENT ----------

    # Processes an uploaded PDF by encoding it to Base64 and submitting it to
    # OCI AI Document for key-value extraction and document classification.
    pdf_bytes = await file.read()
    encoded_pdf = base64.b64encode(pdf_bytes).decode(
        "utf-8")  # Base64 encode PDF

    document = oci.ai_document.models.InlineDocumentDetails(data=encoded_pdf)

    request = oci.ai_document.models.AnalyzeDocumentDetails(
        document=document,
        features=[
            oci.ai_document.models.DocumentFeature(
                feature_type="KEY_VALUE_EXTRACTION"
            ),
            oci.ai_document.models.DocumentClassificationFeature(
                max_results=5
            )
        ]
    )

    # ---------- CALL OCI SAFELY ----------
    try:
        response = get_doc_client().analyze_document(request)
    except HTTPException:
        # Re-raise HTTPException (like ConfigFileNotFound, InvalidKeyFilePath)
        raise
    except Exception as e:
        # Catch OCI service errors and other exceptions
        raise HTTPException(
            status_code=503,
            detail="The service is currently unavailable. Please try again later."
        )

    # ---------- DATA STRUCTURES ----------
    data = {}
    data_confidence = {}
    single_item = {}
    extracted_items = []

    # ---------- PARSE PAGES ----------
    pages = []
    if response and hasattr(response, 'data') and response.data:
        if hasattr(response.data, 'pages') and response.data.pages:
            pages = response.data.pages

    for page in pages:
        if page and hasattr(page, 'document_fields') and page.document_fields:
            for field in page.document_fields:

                field_name = field.field_label.name if field.field_label and hasattr(
                    field.field_label, 'name') and field.field_label.name else None

                # Handle both .text and .value attributes for field_value
                field_value = None
                if field.field_value:
                    if hasattr(field.field_value, 'text') and field.field_value.text:
                        field_value = field.field_value.text
                    elif hasattr(field.field_value, 'value') and field.field_value.value is not None:
                        field_value = field.field_value.value

                # Skip if field_name is None (field has no label)
                if field_name is None:
                    continue

                # ---------- DATE FORMAT ----------
                if field_name == "InvoiceDate":
                    field_value = format_date(field_value)

                # ---------- NUMERIC / MONEY FIELDS ----------
                if field_name in (
                    "InvoiceTotal",
                    "SubTotal",
                    "ShippingCost",
                    "Amount",
                    "UnitPrice",
                    "AmountDue"
                ):
                    field_value = amount_format(field_value) #from $1,200.5 -> 1200.5

                # ---------- CONFIDENCE ----------
                field_confidence = field.field_label.confidence if field.field_label and hasattr(
                    field.field_label, 'confidence') and field.field_label.confidence is not None else 0.0

                # ---------- HANDLE ITEMS ----------
                if field_name == "Items" and field.field_value and hasattr(field.field_value, 'items'):

                    # Reset the list for this invoice/document (avoid accumulating items across pages)
                    extracted_items = []

                    for sub_field in field.field_value.items: #if field_value has items, iterate through them
                        if not sub_field or not hasattr(sub_field, 'field_value') or not sub_field.field_value:
                            continue #if sub_field is None or doesn't have a field_value, skip
                        if not hasattr(sub_field.field_value, 'items'):
                            continue #if sub_field.field_value doesn't have items, skip

                        single_item = {}

                        for sub in sub_field.field_value.items:
                            if not sub:
                                continue

                            sub_key = sub.field_label.name if sub.field_label and hasattr(
                                sub.field_label, 'name') and sub.field_label.name else "" #check the name of the sub field

                            # Handle both .text and .value attributes for sub items
                            sub_value = ""
                            if sub.field_value:
                                if hasattr(sub.field_value, 'text') and sub.field_value.text:
                                    sub_value = sub.field_value.text #check the text of the sub field
                                elif hasattr(sub.field_value, 'value') and sub.field_value.value is not None:
                                    sub_value = sub.field_value.value #check the value of the sub field

                            # Clean numeric fields inside items
                            if sub_key in ("Quantity", "UnitPrice", "Amount"):
                                sub_value = amount_format(sub_value) #from $1,200.5 -> 1200.5

                            if sub_key:
                                single_item[sub_key] = sub_value #add the value to dictionary

                        extracted_items.append(single_item)

                    field_value = extracted_items

                if field_name:
                    data[field_name] = field_value

                    if field_name != "Items":
                        data_confidence[field_name] = field_confidence

    # ---------- DOCUMENT VALIDATION ----------
    confidence = None
    if response and hasattr(response, 'data') and response.data:
        if hasattr(response.data, 'detected_document_types') and response.data.detected_document_types:
            for doc_type in response.data.detected_document_types:
                if doc_type and hasattr(doc_type, 'confidence'):
                    confidence = doc_type.confidence
                    if confidence and confidence < 0.9:
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid document. Please upload a valid PDF invoice with high confidence."
                        )

    # ---------- FINAL RESPONSE ----------
    result = {
        "confidence": confidence,
        "data": data,
        "dataConfidence": data_confidence,
    }

    # Save to database using service layer
    # Create a database session for saving
    db_gen = get_db()
    db = next(db_gen)
    try:
        save_inv_extraction(result, db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    finally:
        db.close()

    return result


# ---------- HELPERS ----------
def format_date(date_text):
    """
    Converts date like:
    'Mar 06 2012' → '2012-03-06T00:00:00+00:00'
    """
    if not date_text:
        return ""
    try:
        dt = datetime.strptime(date_text.strip(), "%b %d %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return date_text


def amount_format(value):
    """
    Removes $ , and spaces → returns float
    '$58.11' → 58.11
    '4,293.55' → 4293.55
    """
    if not value:
        return ""
    try:
        return float(value.replace("$", "").replace(",", "").strip())
    except Exception:
        return value


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/invoices/vendor/{vendor_name}")
async def invoices_by_vendor(vendor_name: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Retrieve all invoices for a specific vendor.

    Args:
        vendor_name: The name of the vendor to filter invoices by.

    Returns:
        A dictionary containing:
            - VendorName: The vendor name (or "Unknown Vendor" if no invoices found)
            - TotalInvoices: The total number of invoices for this vendor
            - invoices: A list of invoice dictionaries, each containing invoice details

    Example:
        GET /invoices/vendor/SuperStore
        Returns:
        {
            "VendorName": "SuperStore",
            "TotalInvoices": 5,
            "invoices": [...]
        }
    """
    controller = InvoiceController()
    invoice_ids = controller.get_invoices_by_vendor(vendor_name, db)

    invoices = []
    for inv_id in invoice_ids:
        invoice = controller.get_invoice_by_id(inv_id, db)
        if invoice:
            invoice_dict = invoice.to_dict()
            # Get items for this invoice
            items = controller.get_items_by_invoice_id(inv_id, db)
            invoice_dict["Items"] = [item.to_dict() for item in items]
            invoices.append(invoice_dict)

    if not invoices:
        return {
            "VendorName": "Unknown Vendor",
            "TotalInvoices": 0,
            "invoices": []
        }

    return {
        "VendorName": vendor_name,
        "TotalInvoices": len(invoices),
        "invoices": invoices
    }


@app.get("/invoices/{invoice_id}")
def get_invoice_by_id(invoice_id: str, db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    """
    Retrieve a complete invoice by its ID, including line items.

    This function fetches the invoice header information from the invoices table
    and all associated line items from the items table, combining them into
    a single dictionary structure.

    Args:
        invoice_id: The unique identifier of the invoice to retrieve.

    Returns:
        A dictionary containing the complete invoice data including:
            - InvoiceId, VendorName, InvoiceDate, BillingAddressRecipient,
              ShippingAddress, SubTotal, ShippingCost, InvoiceTotal
            - Items: A list of line item dictionaries
        Returns None if the invoice ID is not found in the database.

    Example:
        invoice = get_invoice_by_id("36259")
        # Returns: {"InvoiceId": "36259", "VendorName": "SuperStore", "Items": [...], ...}
    """
    controller = InvoiceController()
    invoice = controller.get_invoice_by_id(invoice_id, db)

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail=f"Invoice with ID '{invoice_id}' not found"
        )

    # Convert invoice model to dictionary
    invoice_dict = invoice.to_dict()

    # Get items for this invoice
    items = controller.get_items_by_invoice_id(invoice_id, db)
    invoice_dict["Items"] = [item.to_dict() for item in items]

    return invoice_dict


@app.get("/databases")
async def list_configured_databases():
    """List all configured databases"""
    databases = list_databases()
    return {
        "databases": databases,
        "count": len(databases)
    }


# Example endpoint demonstrating multi-database usage
# You can create endpoints that use specific databases like this:
# @app.get("/analytics/stats")
# async def get_analytics_stats(db: Session = Depends(get_db_by_name("analytics"))):
#     # Query analytics database
#     # result = db.query(AnalyticsModel).all()
#     return {"message": "Query analytics database"}


if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8080)

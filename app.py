import uvicorn
from fastapi import FastAPI, UploadFile, File
import oci
import base64
import json
from fastapi import HTTPException
from db_util import init_db, save_inv_extraction
from controllers.invoice_controller import InvoiceController #MVC
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


app = FastAPI()


# Lazy initialization for OCI client (allows testing with mocks)


def get_doc_client():
    """Get or create the OCI document client"""
    if not hasattr(get_doc_client, '_client'):
        config = oci.config.from_file()
        get_doc_client._client = oci.ai_document.AIServiceDocumentClient(
            config)
    return get_doc_client._client


doc_client = get_doc_client()


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

    save_inv_extraction(result)

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
async def invoices_by_vendor(vendor_name: str) -> Dict[str, Any]:
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
    invoices = get_invoices_by_vendor(vendor_name)

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


def get_invoices_by_vendor(vendor_name: str) -> List[Dict[str, Any]]:
    """
    Fetch all invoices for a given vendor from the database.

    This function queries the database for all invoice IDs associated with the
    specified vendor, then retrieves the full invoice details for each ID.
    Invoices are returned in ascending order by invoice date.

    Args:
        vendor_name: The name of the vendor to search for.

    Returns:
        A list of invoice dictionaries. Each dictionary contains the complete
        invoice information including invoice ID, vendor name, date, addresses,
        totals, and line items. Returns an empty list if no invoices are found
        or if the vendor does not exist.

    Example:
        invoices = get_invoices_by_vendor("SuperStore")
        # Returns: [{"InvoiceId": "36259", "VendorName": "SuperStore", ...}, ...]
    """
    controller = InvoiceController()
    invoice_ids = controller.get_invoices_by_vendor(vendor_name)

    invoices = []
    for inv_id in invoice_ids:
        invoice = controller.get_invoice_by_id(inv_id)
        if invoice:
            invoice_dict = invoice.to_dict()
            # Get items for this invoice
            items = controller.get_items_by_invoice_id(inv_id)
            invoice_dict["Items"] = [item.to_dict() for item in items]
            invoices.append(invoice_dict)

    return invoices


@app.get("/invoices/{invoice_id}")
def get_invoice_by_id(invoice_id: str) -> Optional[Dict[str, Any]]:
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
    invoice = controller.get_invoice_by_id(invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail=f"Invoice with ID '{invoice_id}' not found"
        )

    # Convert invoice model to dictionary
    invoice_dict = invoice.to_dict()

    # Get items for this invoice
    items = controller.get_items_by_invoice_id(invoice_id)
    invoice_dict["Items"] = [item.to_dict() for item in items]

    return invoice_dict


if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8080)

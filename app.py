import sqlite3
from fastapi import FastAPI, UploadFile, File
import oci
import base64
import json
from fastapi import HTTPException
from db_util import init_db, save_inv_extraction
import time
from datetime import datetime, timezone


app = FastAPI()

# Load OCI config from ~/.oci/config
config = oci.config.from_file()
doc_client = oci.ai_document.AIServiceDocumentClient(config)


@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    # ---------- PDF VALIDATION ----------
    is_pdf_content_type = file.content_type == "application/pdf"
    is_pdf_filename = file.filename.lower().endswith(".pdf")

    if not (is_pdf_content_type or is_pdf_filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid document. Please upload a valid PDF invoice with high confidence."
        )

    # ---------- ENCODE DOCUMENT ----------
    pdf_bytes = await file.read()
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

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
        response = doc_client.analyze_document(request)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="The service is currently unavailable. Please try again later."
        )

    # ---------- DATA STRUCTURES ----------
    data = {}
    data_confidence = {}
    all_items = []

    # ---------- PARSE PAGES ----------
    for page in response.data.pages:
        if not page.document_fields:
            continue

        for f in page.document_fields:
            field_key = f.field_label.name if f.field_label and f.field_label.name else ""
            field_value = f.field_value.text if f.field_value and f.field_value.text else ""

            # ---------- DATE FORMAT ----------
            if field_key == "InvoiceDate":
                field_value = format_date_to_iso(field_value)

            # ---------- NUMERIC / MONEY FIELDS ----------
            if field_key in (
                "InvoiceTotal",
                "SubTotal",
                "ShippingCost",
                "Amount",
                "UnitPrice",
                "AmountDue"
            ):
                field_value = clean_amount(field_value)

            # ---------- CONFIDENCE ----------
            field_conf = f.field_label.confidence if f.field_label and f.field_label.confidence else 0.0

            # ---------- HANDLE ITEMS ----------
            if field_key == "Items" and f.field_value:
                # Some SDK versions expose .items and some expose ._items
                items_list = getattr(f.field_value, "items", None)
                if not items_list:
                    items_list = getattr(f.field_value, "_items", [])

                all_items = []

                for item in items_list:
                    single_item = {}

                    sub_fields = getattr(item.field_value, "items", [])
                    for sub in sub_fields:
                        sub_key = sub.field_label.name if sub.field_label else ""
                        sub_value = sub.field_value.text if sub.field_value and sub.field_value.text else ""

                        # Clean numeric fields inside items
                        if sub_key in ("Quantity", "UnitPrice", "Amount"):
                            sub_value = clean_amount(sub_value)

                        single_item[sub_key] = sub_value

                    all_items.append(single_item)

                field_value = all_items

            data[field_key] = field_value
            data_confidence[field_key] = field_conf

    # ---------- DOCUMENT VALIDATION ----------
    if response.data.detected_document_types:
        for doc_type in response.data.detected_document_types:
            confid = doc_type.confidence
            if confid < 0.9:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid document. Please upload a valid PDF invoice with high confidence."
                )

    # ---------- FINAL RESPONSE ----------
    result = {
        "confidence": confid,
        "data": data,
        "dataConfidence": data_confidence,
    }

    save_inv_extraction(result)

    return result


# ---------- HELPERS ----------
def format_date_to_iso(date_text):
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


def clean_amount(value):
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


if _name_ == "_main_":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8080)

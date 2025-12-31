from fastapi import FastAPI, UploadFile, File, HTTPException
import oci
import base64
import traceback
from db_util import init_db, save_inv_extraction


app = FastAPI()

# Load OCI config from ~/.oci/config
try:
    config = oci.config.from_file()
    doc_client = oci.ai_document.AIServiceDocumentClient(config)
except Exception as e:
    print(f"Warning: Failed to initialize OCI client: {str(e)}")
    config = None
    doc_client = None


def parse_number(value):
    """Convert string value to number, handling currency symbols and formatting."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # Remove currency symbols, commas, and whitespace
    cleaned = str(value).replace('$', '').replace(
        ',', '').replace(' ', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def normalize_items(items_data):
    """Normalize items array to match the required schema."""
    normalized_items = []
    seen_items = set()  # Track seen items to avoid duplicates

    if not items_data:
        return normalized_items

    for item in items_data:
        # Skip empty items (items with no meaningful data)
        has_data = False
        for key in ["Name", "name", "Description", "description", "Quantity", "quantity",
                    "UnitPrice", "unit_price", "unitPrice", "Amount", "amount"]:
            if item.get(key) not in [None, "", 0, 0.0]:
                has_data = True
                break

        if not has_data:
            continue

        # Extract Name and Description - handle cases where they might be combined
        name = item.get("Name") or item.get("name") or item.get(
            "Item") or item.get("item") or None
        description = item.get("Description") or item.get(
            "description") or None

        # If Name and Description are the same, try to split intelligently
        if name and description and name == description:
            # Try to split on common separators or use the full text as name
            # Description might be empty or we keep both the same
            pass  # Keep as is for now, OCI should separate them

        # If only one field exists, use it for Name
        if not name and description:
            name = description
            description = None
        elif not description and name:
            # Name exists, description can be None
            pass

        quantity = parse_number(item.get("Quantity") or item.get(
            "quantity") or item.get("Qty") or item.get("qty"))
        unit_price = parse_number(item.get("UnitPrice") or item.get(
            "unit_price") or item.get("unitPrice") or item.get("Rate") or item.get("rate"))
        amount = parse_number(item.get("Amount") or item.get("amount"))

        normalized_item = {
            "Description": description,
            "Name": name,
            "Quantity": quantity,
            "UnitPrice": unit_price,
            "Amount": amount
        }

        # Only add items that have at least Name or Description
        if normalized_item["Name"] or normalized_item["Description"]:
            # Create a signature to detect duplicates (same name/description and amount)
            item_signature = (
                str(normalized_item["Name"] or ""),
                str(normalized_item["Description"] or ""),
                normalized_item["Amount"]
            )

            # Skip if we've seen this exact item before (duplicate)
            if item_signature not in seen_items:
                seen_items.add(item_signature)
                normalized_items.append(normalized_item)
            # Also skip items that are clearly duplicates (same amount but no name/description)
            elif not normalized_item["Name"] and not normalized_item["Description"]:
                continue

    return normalized_items


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    try:
        if doc_client is None:
            raise HTTPException(
                status_code=500,
                detail="OCI Document AI client not initialized. Please check your OCI configuration."
            )

        pdf_bytes = await file.read()
        encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

        # InlineDocumentDetails only needs 'data' parameter - mime type is inferred
        document = oci.ai_document.models.InlineDocumentDetails(
            data=encoded_pdf
        )

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

        response = doc_client.analyze_document(request)

        # DEBUG: Print raw OCI response structure
        print("\n" + "="*80)
        print("DEBUG - RAW OCI RESPONSE STRUCTURE")
        print("="*80)

        # Print all document fields with their names and values
        if response.data and hasattr(response.data, 'pages') and response.data.pages:
            for page_idx, page in enumerate(response.data.pages):
                print(f"\n--- PAGE {page_idx + 1} ---")
                if hasattr(page, 'document_fields') and page.document_fields:
                    for field in page.document_fields:
                        field_name = field.field_label.name if field.field_label else "NO_NAME"
                        field_conf = field.field_label.confidence if field.field_label else None

                        # Get field value
                        field_value = None
                        if field.field_value:
                            field_value = getattr(field.field_value, 'value', None) or getattr(
                                field.field_value, 'text', None) or getattr(field.field_value, 'items', None)

                        print(
                            f"  Field Name: '{field_name}' | Confidence: {field_conf} | Value: {field_value}")

                        # If it's an Items field, print its structure
                        if field_name == "Items" and field.field_value:
                            print(
                                f"    Items field detected - value_type: {getattr(field.field_value, 'value_type', 'N/A')}")
                            items_list = getattr(
                                field.field_value, "items", None)
                            if not items_list:
                                items_list = getattr(
                                    field.field_value, "_items", None)
                            if not items_list and hasattr(field.field_value, "array_value"):
                                items_list = field.field_value.array_value

                            if items_list:
                                print(
                                    f"    Items list length: {len(items_list)}")
                                for item_idx, item in enumerate(items_list):
                                    print(f"      Item {item_idx + 1}:")
                                    sub_fields = getattr(
                                        item, "field_value", None)
                                    if sub_fields:
                                        sub_items = getattr(
                                            sub_fields, "items", None)
                                        if not sub_items:
                                            sub_items = getattr(
                                                sub_fields, "_items", None)
                                        if not sub_items and hasattr(sub_fields, "object_value"):
                                            sub_items = sub_fields.object_value

                                        if sub_items:
                                            for sub_field in sub_items:
                                                sub_name = sub_field.field_label.name if sub_field.field_label else "NO_NAME"
                                                sub_value = getattr(sub_field.field_value, 'value', None) or getattr(
                                                    sub_field.field_value, 'text', None) if sub_field.field_value else None
                                                print(
                                                    f"        - {sub_name}: {sub_value}")

        print("\n" + "="*80)
        print("END OF RAW OCI RESPONSE")
        print("="*80 + "\n")

        data = {}
        data_confidence = {}
        items = []

        # Extract fields from OCI response
        if response.data and hasattr(response.data, 'pages') and response.data.pages:
            for page in response.data.pages:
                if not hasattr(page, 'document_fields') or not page.document_fields:
                    continue

                for field in page.document_fields:
                    field_name = field.field_label.name if field.field_label else None
                    field_confidence = field.field_label.confidence if field.field_label else None

                    # Handle both .text and .value attributes (OCI SDK may use either)
                    if field.field_value:
                        field_value = getattr(field.field_value, 'value', None) or getattr(
                            field.field_value, 'text', None) or ""
                    else:
                        field_value = ""

                    if not field_name:
                        continue

                    # Handle Items array - OCI uses LINE_ITEM_GROUP with .items attribute
                    if field_name == "Items" and field.field_value:
                        # Some SDK versions expose .items and some expose ._items
                        items_list = getattr(field.field_value, "items", None)
                        if not items_list:
                            items_list = getattr(
                                field.field_value, "_items", None)
                        if not items_list and hasattr(field.field_value, "array_value"):
                            items_list = field.field_value.array_value

                        if items_list:
                            for item in items_list:
                                item_data = {}

                                # Access sub-fields from item.field_value.items
                                sub_fields = getattr(item, "field_value", None)
                                if sub_fields:
                                    sub_items = getattr(
                                        sub_fields, "items", None)
                                    if not sub_items:
                                        sub_items = getattr(
                                            sub_fields, "_items", None)
                                    if not sub_items and hasattr(sub_fields, "object_value"):
                                        sub_items = sub_fields.object_value

                                    if sub_items:
                                        for sub_field in sub_items:
                                            sub_name = sub_field.field_label.name if sub_field.field_label else None
                                            # Handle both .text and .value attributes
                                            if sub_field.field_value:
                                                sub_value = getattr(sub_field.field_value, 'value', None) or getattr(
                                                    sub_field.field_value, 'text', None) or ""
                                            else:
                                                sub_value = ""

                                            if sub_name:
                                                item_data[sub_name] = sub_value

                                # Only add item if it has meaningful data
                                # Check if item has at least Name/Description AND at least one numeric field
                                has_name_or_desc = bool(item_data.get("Name") or item_data.get("Description") or
                                                        item_data.get("name") or item_data.get("description") or
                                                        item_data.get("Item") or item_data.get("item"))
                                has_numeric = bool(item_data.get("Quantity") or item_data.get("quantity") or
                                                   item_data.get("UnitPrice") or item_data.get("unit_price") or item_data.get("unitPrice") or
                                                   item_data.get("Rate") or item_data.get("rate") or
                                                   item_data.get("Amount") or item_data.get("amount"))

                                if item_data and has_name_or_desc and has_numeric:
                                    items.append(item_data)
                    else:
                        # Store the original field name first
                        data[field_name] = field_value
                        data_confidence[field_name] = field_confidence

                        # Normalize field names for case-insensitive matching
                        # Handle common field name variations - check multiple patterns
                        field_lower = field_name.lower().replace(" ", "").replace(
                            "_", "").replace("-", "").replace(":", "")

                        # Map to normalized names
                        if field_lower in ["subtotal", "subtotal", "sub-total"]:
                            data["SubTotal"] = field_value
                            data_confidence["SubTotal"] = field_confidence
                        elif field_lower in ["amountdue", "amountdue", "balancedue", "balancedue", "balance"]:
                            data["AmountDue"] = field_value
                            data_confidence["AmountDue"] = field_confidence
                        elif field_lower in ["shippingcost", "shippingcost", "shipping", "shippingcost"]:
                            data["ShippingCost"] = field_value
                            data_confidence["ShippingCost"] = field_confidence
                        elif field_lower in ["invoicetotal", "invoicetotal", "total", "invoicetotal"]:
                            data["InvoiceTotal"] = field_value
                            data_confidence["InvoiceTotal"] = field_confidence

                        # Also check partial matches for common patterns
                        if "subtotal" in field_lower or "sub" in field_lower and "total" in field_lower:
                            if "SubTotal" not in data or not data.get("SubTotal"):
                                data["SubTotal"] = field_value
                                data_confidence["SubTotal"] = field_confidence
                        if "balance" in field_lower or "amount" in field_lower and "due" in field_lower:
                            if "AmountDue" not in data or not data.get("AmountDue"):
                                data["AmountDue"] = field_value
                                data_confidence["AmountDue"] = field_confidence

        # Get document classification confidence
        document_confidence = 1.0
        if response.data and hasattr(response.data, 'document_classification_results') and response.data.document_classification_results:
            document_confidence = float(
                response.data.document_classification_results[0].confidence)

        # Debug: Print all extracted field names to help identify issues
        print("DEBUG - Extracted field names:", list(data.keys()))
        print("DEBUG - Field values:",
              {k: v for k, v in data.items() if k not in ["Items"]})

        # Normalize items
        normalized_items = normalize_items(
            items if items else data.get("Items", []))

        # Helper function to normalize field name for matching
        def normalize_field_name(name):
            if not name:
                return ""
            return name.lower().replace(" ", "").replace("_", "").replace("-", "").replace(":", "").strip()

        # Helper function to get field value with variations - searches all keys
        def get_field_value(field_name, variations):
            # First try exact matches
            for var in [field_name] + variations:
                if var in data and data[var] not in [None, ""]:
                    return data[var]

            # Then try normalized matching against all keys
            target_normalized = normalize_field_name(field_name)
            for key in data.keys():
                if normalize_field_name(key) == target_normalized and data[key] not in [None, ""]:
                    return data[key]

            # Also check variations
            for variation in variations:
                var_normalized = normalize_field_name(variation)
                for key in data.keys():
                    if normalize_field_name(key) == var_normalized and data[key] not in [None, ""]:
                        return data[key]

            # Partial matching for common patterns
            if "subtotal" in target_normalized or ("sub" in target_normalized and "total" in target_normalized):
                for key in data.keys():
                    key_norm = normalize_field_name(key)
                    if ("subtotal" in key_norm or ("sub" in key_norm and "total" in key_norm)) and data[key] not in [None, ""]:
                        return data[key]

            if "balance" in target_normalized or "amountdue" in target_normalized:
                for key in data.keys():
                    key_norm = normalize_field_name(key)
                    if ("balance" in key_norm or "amountdue" in key_norm) and data[key] not in [None, ""]:
                        return data[key]

            return None

        def get_field_confidence(field_name, variations):
            # First try exact matches
            for var in [field_name] + variations:
                if var in data_confidence and data_confidence[var] is not None:
                    return data_confidence[var]

            # Then try normalized matching
            target_normalized = normalize_field_name(field_name)
            for key in data_confidence.keys():
                if normalize_field_name(key) == target_normalized and data_confidence[key] is not None:
                    return data_confidence[key]

            # Also check variations
            for variation in variations:
                var_normalized = normalize_field_name(variation)
                for key in data_confidence.keys():
                    if normalize_field_name(key) == var_normalized and data_confidence[key] is not None:
                        return data_confidence[key]

            return None

        # Build normalized output according to the required schema
        normalized_output = {
            "confidence": document_confidence,
            "data": {
                "VendorName": data.get("VendorName") or None,
                "VendorNameLogo": data.get("VendorNameLogo") or None,
                "InvoiceId": data.get("InvoiceId") or None,
                "InvoiceDate": data.get("InvoiceDate") or None,
                "ShippingAddress": data.get("ShippingAddress") or None,
                "BillingAddressRecipient": data.get("BillingAddressRecipient") or None,
                "AmountDue": parse_number(get_field_value("AmountDue", ["Balance Due", "BalanceDue", "Amount Due"])),
                "SubTotal": parse_number(get_field_value("SubTotal", ["Subtotal", "Sub Total", "Sub-Total"])),
                "ShippingCost": parse_number(get_field_value("ShippingCost", ["Shipping", "Shipping Cost"])),
                "InvoiceTotal": parse_number(get_field_value("InvoiceTotal", ["Total", "Invoice Total", "Invoice-Total"])),
                "Items": normalized_items
            },
            "dataConfidence": {
                "VendorName": float(data_confidence.get("VendorName")) if data_confidence.get("VendorName") is not None else None,
                "VendorNameLogo": float(data_confidence.get("VendorNameLogo")) if data_confidence.get("VendorNameLogo") is not None else None,
                "InvoiceId": float(data_confidence.get("InvoiceId")) if data_confidence.get("InvoiceId") is not None else None,
                "InvoiceDate": float(data_confidence.get("InvoiceDate")) if data_confidence.get("InvoiceDate") is not None else None,
                "ShippingAddress": float(data_confidence.get("ShippingAddress")) if data_confidence.get("ShippingAddress") is not None else None,
                "BillingAddressRecipient": float(data_confidence.get("BillingAddressRecipient")) if data_confidence.get("BillingAddressRecipient") is not None else None,
                "AmountDue": float(get_field_confidence("AmountDue", ["Balance Due", "BalanceDue", "Amount Due"])) if get_field_confidence("AmountDue", ["Balance Due", "BalanceDue", "Amount Due"]) is not None else None,
                "SubTotal": float(get_field_confidence("SubTotal", ["Subtotal", "Sub Total", "Sub-Total"])) if get_field_confidence("SubTotal", ["Subtotal", "Sub Total", "Sub-Total"]) is not None else None,
                "ShippingCost": float(get_field_confidence("ShippingCost", ["Shipping", "Shipping Cost"])) if get_field_confidence("ShippingCost", ["Shipping", "Shipping Cost"]) is not None else None,
                "InvoiceTotal": float(get_field_confidence("InvoiceTotal", ["Total", "Invoice Total", "Invoice-Total"])) if get_field_confidence("InvoiceTotal", ["Total", "Invoice Total", "Invoice-Total"]) is not None else None
            }
        }

        try:
            save_inv_extraction(normalized_output)
        except Exception as db_error:
            # Log database error but don't fail the request
            print(f"Database save error: {str(db_error)}")

        return normalized_output

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error in extract endpoint: {str(e)}")
        print(f"Traceback: {error_trace}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "traceback": error_trace
            }
        )


@app.get('/health')
def health():
    return {'status': 'ok'}


if __name__ == "__main__":
    import uvicorn

    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8080)

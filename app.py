from fastapi import FastAPI, UploadFile, File
import oci
import base64
import time

app = FastAPI()

config = oci.config.from_file()
doc_client = oci.ai_document.AIServiceDocumentClient(config)


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    document = oci.ai_document.models.InlineDocumentDetails(
        data=encoded_pdf,
        mime_type="application/pdf"
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

    # ⏱️ מדידת זמן החיזוי
    start_time = time.time()
    response = doc_client.analyze_document(request)
    end_time = time.time()
    prediction_time = round(end_time - start_time, 3)

    data = {}
    data_confidence = {}

    # ... מילוי data ו-data_confidence כמו שיש לך ...

    result = {
        "confidence": "1",
        "data": data,
        "dataConfidence": data_confidence,
        "predictionTime": prediction_time  # ⏱️ הערך החדש
    }

    return result

import json
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docxtpl import DocxTemplate
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import require_auth
from app.converter import convert_to_pdf
from app.storage import (
    check_connectivity,
    delete_file,
    download_file,
    file_exists,
    list_files,
    upload_file,
)

MAX_TEMPLATE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB

app = FastAPI()


def _error(status: int, message: str):
    return JSONResponse(
        status_code=status,
        content={"Title": "Error", "Message": message},
    )


def _is_valid_docx(data: bytes) -> bool:
    try:
        with ZipFile(BytesIO(data)) as zf:
            return "word/document.xml" in zf.namelist()
    except BadZipFile:
        return False


# --- Health ---


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/health", dependencies=[Depends(require_auth)])
async def health():
    if check_connectivity():
        return {"status": "ok", "spaces": "reachable"}
    return JSONResponse(
        status_code=503,
        content={"status": "unhealthy", "spaces": "unreachable"},
    )


# --- Templates ---


@app.post("/upload-template", dependencies=[Depends(require_auth)])
async def upload_template(file: UploadFile = File(...)):
    data = await file.read()

    if len(data) > MAX_TEMPLATE_SIZE:
        return _error(413, "File exceeds 10 MB.")

    if not data:
        return _error(400, "No file provided.")

    if not _is_valid_docx(data):
        return _error(400, "File is not a valid .docx.")

    template_id = str(uuid.uuid4())
    local_path = f"/tmp/{template_id}.docx"
    try:
        with open(local_path, "wb") as f:
            f.write(data)
        upload_file(local_path, f"templates/{template_id}.docx")
    except Exception:
        return _error(500, "Failed to upload to Spaces.")
    finally:
        Path(local_path).unlink(missing_ok=True)

    return {"templateId": template_id}


@app.get("/templates", dependencies=[Depends(require_auth)])
async def list_templates():
    keys = list_files("templates/")
    template_ids = [
        Path(k).stem for k in keys if k.endswith(".docx")
    ]
    return {"templates": template_ids}


@app.delete("/templates/{template_id}", dependencies=[Depends(require_auth)])
async def delete_template(template_id: str):
    remote_key = f"templates/{template_id}.docx"
    if not file_exists(remote_key):
        return JSONResponse(
            status_code=404,
            content={"Title": "Error", "Message": "The Template could not be found."},
        )
    delete_file(remote_key)
    return {"Title": "Deleted", "Message": "Template removed."}


# --- Generate ---


@app.post("/generate", dependencies=[Depends(require_auth)])
async def generate(request: Request):
    body = await request.body()
    if len(body) > MAX_BODY_SIZE:
        return _error(413, "Payload too large.")

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return _error(400, "Invalid JSON.")

    template_id = payload.get("templateId")
    if not template_id:
        return _error(400, "templateId is required.")

    remote_template = f"templates/{template_id}.docx"
    if not file_exists(remote_template):
        return _error(404, "The Template could not be found.")

    output_id = str(uuid.uuid4())
    local_template = f"/tmp/{output_id}_template.docx"
    local_output = f"/tmp/{output_id}.docx"

    try:
        download_file(remote_template, local_template)

        doc = DocxTemplate(local_template)
        doc.render(payload)
        doc.save(local_output)

        upload_file(local_output, f"generated/{output_id}.docx")

        pdf_filename = ""
        if payload.get("pdf"):
            pdf_path = await convert_to_pdf(local_output, output_id)
            upload_file(pdf_path, f"generated/{output_id}.pdf")
            pdf_filename = f"{output_id}.pdf"
            Path(pdf_path).unlink(missing_ok=True)

        return {
            "fileWordDoc": f"{output_id}.docx",
            "filePdfDoc": pdf_filename,
            "timeStamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
        }

    except RuntimeError as exc:
        return _error(500, str(exc))
    except Exception as exc:
        return _error(500, f"Document generation failed: {exc}")
    finally:
        Path(local_template).unlink(missing_ok=True)
        Path(local_output).unlink(missing_ok=True)


# --- File retrieval ---

CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


@app.get("/file", dependencies=[Depends(require_auth)])
async def get_file(fileName: str | None = None):
    if not fileName:
        return _error(400, "fileName parameter is required.")

    remote_key = f"generated/{fileName}"
    if not file_exists(remote_key):
        return _error(404, "The file could not be found.")

    local_path = f"/tmp/{fileName}"
    download_file(remote_key, local_path)

    ext = Path(fileName).suffix.lower()
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")

    def iterfile():
        with open(local_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk
        os.unlink(local_path)

    return StreamingResponse(
        iterfile(),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{fileName}"'},
    )

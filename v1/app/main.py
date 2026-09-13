import json
import re
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docxtpl import DocxTemplate
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from jinja2 import StrictUndefined, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from app.auth import require_auth
from app.config import MAX_TEMPLATE_UNCOMPRESSED_SIZE
from app.converter import convert_to_pdf
from app.logging_config import configure_logging, log_request
from app.storage import (
    check_connectivity,
    delete_file,
    download_file,
    file_exists,
    list_files,
    presigned_download_url,
    upload_file,
)

MAX_TEMPLATE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB

# (#3) A template ID is always a UUID we generated ourselves; a filename is
# always a UUID plus the extension we gave it. Anything else is rejected
# outright rather than being used to build a storage key or local path —
# this is also what closes off the path-traversal concern raised in #5.
_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_TEMPLATE_ID_RE = re.compile(rf"^{_UUID_RE}$")
_FILENAME_RE = re.compile(rf"^{_UUID_RE}\.(docx|pdf)$")

app = FastAPI()
logger = configure_logging()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    log_request(
        logger,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response


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


def _uncompressed_size_within_limit(data: bytes) -> bool:
    # (#15) A "zip bomb" style template can be small on disk but expand
    # into an enormous amount of data once opened. Check the *declared*
    # uncompressed size of every entry before anything actually unpacks it.
    with ZipFile(BytesIO(data)) as zf:
        total = sum(info.file_size for info in zf.infolist())
    return total <= MAX_TEMPLATE_UNCOMPRESSED_SIZE


def _render_environment() -> SandboxedEnvironment:
    # (#18) Templates are entirely user-authored and unchecked. docxtpl
    # renders using real Jinja2, which is a general templating language —
    # without a sandbox, a crafted "placeholder" could reach beyond simple
    # data substitution. StrictUndefined (#2) means a payload missing an
    # expected key raises a clear error instead of silently rendering blank.
    return SandboxedEnvironment(undefined=StrictUndefined)


# --- Health ---


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/health", dependencies=[Depends(require_auth)])
async def health():
    if await check_connectivity():
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

    if not _uncompressed_size_within_limit(data):
        return _error(400, "File expands to an unreasonably large size and was rejected.")

    template_id = str(uuid.uuid4())
    local_path = f"/tmp/{template_id}.docx"
    try:
        with open(local_path, "wb") as f:
            f.write(data)
        await upload_file(local_path, f"templates/{template_id}.docx")
    except Exception:
        return _error(500, "Failed to upload to Spaces.")
    finally:
        Path(local_path).unlink(missing_ok=True)

    return {"templateId": template_id}


@app.get("/templates", dependencies=[Depends(require_auth)])
async def list_templates():
    keys = await list_files("templates/")
    template_ids = [
        Path(k).stem for k in keys if k.endswith(".docx")
    ]
    return {"templates": template_ids}


@app.delete("/templates/{template_id}", dependencies=[Depends(require_auth)])
async def delete_template(template_id: str):
    if not _TEMPLATE_ID_RE.match(template_id):
        return _error(400, "templateId is not a valid identifier.")

    remote_key = f"templates/{template_id}.docx"
    if not await file_exists(remote_key):
        return JSONResponse(
            status_code=404,
            content={"Title": "Error", "Message": "The Template could not be found."},
        )
    await delete_file(remote_key)
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
    if not _TEMPLATE_ID_RE.match(template_id):
        return _error(400, "templateId is not a valid identifier.")

    remote_template = f"templates/{template_id}.docx"
    if not await file_exists(remote_template):
        return _error(404, "The Template could not be found.")

    output_id = str(uuid.uuid4())
    local_template = f"/tmp/{output_id}_template.docx"
    local_output = f"/tmp/{output_id}.docx"
    pdf_path: str | None = None

    try:
        await download_file(remote_template, local_template)

        doc = DocxTemplate(local_template)
        try:
            doc.render(payload, jinja_env=_render_environment())
        except UndefinedError as exc:
            return _error(400, f"Payload is missing data the template expects: {exc}")
        doc.save(local_output)

        await upload_file(local_output, f"generated/{output_id}.docx")

        response = {
            "fileWordDoc": f"{output_id}.docx",
            "filePdfDoc": "",
            "timeStamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
        }

        if payload.get("pdf"):
            # (#17) The Word document above has already been generated and
            # saved successfully by this point. If the PDF step fails, that
            # success shouldn't be thrown away — return the Word document
            # and flag the PDF failure, rather than a blanket error.
            try:
                pdf_path = await convert_to_pdf(local_output, output_id)
                await upload_file(pdf_path, f"generated/{output_id}.pdf")
                response["filePdfDoc"] = f"{output_id}.pdf"
            except Exception as exc:
                response["pdfError"] = f"PDF conversion failed: {exc}"

        return response

    except Exception as exc:
        return _error(500, f"Document generation failed: {exc}")
    finally:
        Path(local_template).unlink(missing_ok=True)
        Path(local_output).unlink(missing_ok=True)
        if pdf_path:
            Path(pdf_path).unlink(missing_ok=True)


# --- File retrieval ---


@app.get("/file", dependencies=[Depends(require_auth)])
async def get_file(fileName: str | None = None):
    if not fileName:
        return _error(400, "fileName parameter is required.")
    if not _FILENAME_RE.match(fileName):
        return _error(400, "fileName is not a valid identifier.")

    remote_key = f"generated/{fileName}"
    if not await file_exists(remote_key):
        return _error(404, "The file could not be found.")

    # (#10) Rather than downloading the file onto this server and streaming
    # it back out — double the transfer, and a worker held for the whole
    # download — hand back a short-lived, private, single-file link direct
    # to storage. The bucket itself stays private throughout.
    url = await presigned_download_url(remote_key, fileName)
    return RedirectResponse(url=url, status_code=302)

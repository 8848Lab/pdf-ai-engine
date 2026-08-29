"""FastAPI app for manually exercising redact_region/replace_text against
real PDFs. See the design spec's "API surface" section -- this is a local
verification tool, not a product: no auth, no persistence beyond one
in-process session.
"""
from pathlib import Path

from fastapi import FastAPI, File, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webui import session

app = FastAPI(title="8848 PDF AI -- manual verification tool")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


class RedactRequest(BaseModel):
    block_id: int


class ReplaceRequest(BaseModel):
    block_id: int
    new_text: str


@app.exception_handler(ValueError)
async def _value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(LookupError)
async def _lookup_error_handler(request, exc: LookupError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    pdf_bytes = await file.read()
    try:
        session.load_document(pdf_bytes)
    except Exception as exc:
        # A non-PDF or corrupted upload raises whatever PyMuPDF's own
        # exception type is (fitz.FileDataError, fitz.EmptyFileError, ...).
        # Normalize to ValueError so the handler above returns a clean 400
        # instead of a 500 -- a bad upload is an expected, recoverable user
        # error for this tool, not a server fault.
        raise ValueError(f"could not open the uploaded file as a PDF: {exc}") from exc
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.get("/api/page/{page_index}.png")
async def page_image(page_index: int) -> Response:
    handle = session.get_handle()
    if page_index < 0 or page_index >= handle.page_count:
        raise LookupError(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )
    png_bytes = handle[page_index].get_pixmap().tobytes("png")
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/redact")
async def redact(body: RedactRequest) -> dict:
    session.redact(body.block_id)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.post("/api/replace")
async def replace(body: ReplaceRequest) -> dict:
    session.replace(body.block_id, body.new_text)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.get("/api/export")
async def export_pdf() -> Response:
    pdf_bytes = session.export_current()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="edited.pdf"'},
    )


@app.post("/api/reset")
async def reset_session() -> dict:
    session.reset()
    return {"status": "ok"}

"""FastAPI app for manually exercising redact_region/replace_text against
real PDFs. See the design spec's "API surface" section -- this is a local
verification tool, not a product: no auth, no persistence beyond one
in-process session.
"""
from pathlib import Path

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webui import ai
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


class DeleteRequest(BaseModel):
    block_id: int


class MoveRequest(BaseModel):
    block_id: int
    destination_page_index: int | None = None
    target_position: tuple[float, float] | None = None
    offset: tuple[float, float] | None = None


class InsertRequest(BaseModel):
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    size: float
    font: str | None = None


@app.exception_handler(ValueError)
async def _value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(LookupError)
async def _lookup_error_handler(request, exc: LookupError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


def _state_payload() -> dict:
    """The session state every mutating route returns. One helper, not eight
    inline dicts: the frontend rebuilds its entire view from whichever
    response came back last, so an endpoint that omitted a key would make
    that part of the UI disappear until the next full refresh.
    """
    return {
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
        "images": session.get_images_summary(),
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    pdf_bytes = await file.read()
    try:
        session.load_document(pdf_bytes)
    except IndexError as exc:
        # M2: some malformed uploads make PyMuPDF's own page-size lookup
        # raise a bare IndexError ("list index out of range"), which is
        # correct but opaque to the operator. Name the real cause.
        raise ValueError(
            f"could not open the uploaded file as a PDF: PyMuPDF cannot "
            f"determine a page's size (IndexError)"
        ) from exc
    except Exception as exc:
        # A non-PDF or corrupted upload raises whatever PyMuPDF's own
        # exception type is (fitz.FileDataError, fitz.EmptyFileError, ...).
        # Normalize to ValueError so the handler above returns a clean 400
        # instead of a 500 -- a bad upload is an expected, recoverable user
        # error for this tool, not a server fault.
        raise ValueError(f"could not open the uploaded file as a PDF: {exc}") from exc
    return _state_payload()


@app.get("/api/state")
async def state() -> dict:
    """The current session's real state, for the frontend to re-sync with
    after a failed action -- an engine operation can mutate the document and
    then raise, so what the page is showing may no longer be true."""
    return _state_payload()


@app.get("/api/page/{page_index}.png")
async def page_image(page_index: int) -> Response:
    handle = session.get_handle()
    if page_index < 0 or page_index >= handle.page_count:
        raise LookupError(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )
    try:
        png_bytes = handle[page_index].get_pixmap().tobytes("png")
    except Exception as exc:
        # M1: a page PyMuPDF cannot lay out (e.g. an infinite MediaBox) makes
        # get_pixmap() raise whatever PyMuPDF's own exception type is. Route
        # it through the existing ValueError handler for a clean 400 instead
        # of a bare 500 -- rendering a preview is not something the operator
        # can fix, but it should not look like a server fault either.
        raise ValueError(f"page {page_index} cannot be rendered: {exc}") from exc
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/redact")
async def redact(body: RedactRequest) -> dict:
    session.redact(body.block_id)
    return _state_payload()


@app.post("/api/replace")
async def replace(body: ReplaceRequest) -> dict:
    session.replace(body.block_id, body.new_text)
    return _state_payload()


@app.post("/api/delete")
async def delete(body: DeleteRequest) -> dict:
    session.delete(body.block_id)
    return _state_payload()


@app.post("/api/move")
async def move(body: MoveRequest) -> dict:
    session.move(
        body.block_id,
        destination_page_index=body.destination_page_index,
        target_position=body.target_position,
        offset=body.offset,
    )
    return _state_payload()


@app.post("/api/insert")
async def insert(body: InsertRequest) -> dict:
    session.insert(body.page_index, body.bbox, body.text, body.size, font=body.font)
    return _state_payload()


@app.post("/api/replace-image")
async def replace_image(image_id: int = Form(...), file: UploadFile = File(...)) -> dict:
    # multipart/form-data, not JSON, because the payload is binary -- the
    # same shape /api/upload already uses. Every other mutating route takes
    # a JSON body.
    image_bytes = await file.read()
    session.replace_image(image_id, image_bytes)
    return _state_payload()


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


@app.get("/api/metadata")
async def metadata() -> dict:
    return session.get_metadata_summary()


@app.post("/api/sanitize")
async def sanitize() -> dict:
    result = session.sanitize_document()
    return {**result, **_state_payload()}


class AIInstructRequest(BaseModel):
    instruction: str
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/api/ai-instruct")
def ai_instruct(body: AIInstructRequest) -> dict:
    # Plain `def`, not `async def`: FastAPI runs sync route handlers in a
    # threadpool automatically, which keeps this (synchronous, blocking) AI
    # provider call from blocking the whole event loop during a request.
    resolved_key = ai.resolve_api_key(body.provider, body.api_key)
    summary = ai.run_instruction(body.instruction, body.provider, resolved_key, body.base_url, body.model)
    return {"summary": summary, **_state_payload()}

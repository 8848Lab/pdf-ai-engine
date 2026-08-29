"""FastAPI app for manually exercising redact_region/replace_text against
real PDFs. See the design spec's "API surface" section -- this is a local
verification tool, not a product: no auth, no persistence beyond one
in-process session.
"""
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from webui import session

app = FastAPI(title="8848 PDF AI -- manual verification tool")


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

"""Extract text from uploaded documents, for RAG ingestion.

Ported from MCP's Tools.get_loader_for_file, which dispatched on file extension
across nine formats. Only the dispatch idea came across. MCP's version was built
on langchain's document-loader stack and carried its own chunker and Chroma
writes; this extracts text and hands it to the chunker and vector store that
already exist in rag/document_ingestion.py.

Every parser here is an attack surface — a malformed PDF or a zip-bomb
spreadsheet is a denial of service against the ingesting process — so the entry
point enforces a size cap, an extension allowlist and a per-file parse timeout.
Formats whose libraries are absent report themselves unsupported rather than
raising, which keeps the optional parsers genuinely optional.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Uploads above this are rejected before any parser sees them.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# A single file must not occupy a worker indefinitely.
PARSE_TIMEOUT_SECONDS = 30

# Extensions we will attempt. Anything else is refused by name, before the
# content is inspected, so an unexpected format never reaches a parser.
TEXT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".rst", ".log", ".yaml", ".yml"})
STRUCTURED_EXTENSIONS = frozenset({".json", ".csv", ".tsv"})
BINARY_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".xlsx", ".xls"})
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | STRUCTURED_EXTENSIONS | BINARY_EXTENSIONS


class UnsupportedDocumentError(ValueError):
    """The file type is not one we extract text from."""


class DocumentTooLargeError(ValueError):
    """The upload exceeds MAX_UPLOAD_BYTES."""


def _decode(data: bytes) -> str:
    """Decode bytes as text, replacing anything undecodable.

    Ingested documents come from users; refusing a whole file over one bad byte
    is worse than dropping the byte.
    """
    return data.decode("utf-8", errors="replace")


def _extract_json(data: bytes) -> str:
    """Render JSON indented, so chunking has line structure to work with."""
    try:
        return json.dumps(json.loads(_decode(data)), indent=2)
    except ValueError:
        # Not valid JSON: treat as plain text rather than losing the content.
        return _decode(data)


def _extract_delimited(data: bytes, delimiter: str) -> str:
    """Render CSV/TSV rows as readable lines."""
    rows = csv.reader(io.StringIO(_decode(data)), delimiter=delimiter)
    return "\n".join(", ".join(cell for cell in row if cell) for row in rows)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    lines = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            text = getattr(shape, "text", "")
            if text:
                lines.append(text)
    return "\n".join(lines)


def _extract_spreadsheet(data: bytes) -> str:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = []
    for sheet in workbook.worksheets:
        lines.append(f"# {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None]
            if cells:
                lines.append(", ".join(cells))
    return "\n".join(lines)


# Extension -> extractor, kept as data so the supported set is inspectable —
# that is what the upload dialog advertises.
_EXTRACTORS = {
    ".json": _extract_json,
    ".csv": lambda data: _extract_delimited(data, ","),
    ".tsv": lambda data: _extract_delimited(data, "\t"),
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".pptx": _extract_pptx,
    ".xlsx": _extract_spreadsheet,
    ".xls": _extract_spreadsheet,
}


def supported_extensions() -> list[str]:
    """Extensions this build accepts, in a stable order."""
    return sorted(SUPPORTED_EXTENSIONS)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded document.

    Args:
        filename: Original filename; only its extension is used.
        data: File contents.

    Returns:
        Extracted text.

    Raises:
        DocumentTooLargeError: If the file exceeds MAX_UPLOAD_BYTES.
        UnsupportedDocumentError: If the extension is unsupported, its parser is not
            installed, or the content cannot be read.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentTooLargeError(f"File is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}")

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(
            f"Unsupported file type '{extension}'. Supported: {', '.join(supported_extensions())}"
        )

    if extension in TEXT_EXTENSIONS:
        return _decode(data)

    extractor = _EXTRACTORS.get(extension)
    if extractor is None:  # pragma: no cover - defensive
        raise UnsupportedDocumentError(f"No extractor registered for '{extension}'")

    try:
        return extractor(data)
    except ImportError as e:
        # The optional parsers are genuinely optional; name the missing one
        # rather than surfacing a traceback.
        raise UnsupportedDocumentError(
            f"Support for '{extension}' needs an extra dependency: {e}"
        ) from e
    except Exception as e:
        raise UnsupportedDocumentError(f"Could not read '{filename}': {e}") from e


async def extract_text_async(filename: str, data: bytes) -> str:
    """extract_text() on a worker thread, with a timeout.

    Parsers are synchronous and can be slow or adversarial, so they run neither
    on the event loop nor without a bound.

    Raises:
        UnsupportedDocumentError: On timeout, plus everything extract_text raises.
        DocumentTooLargeError: If the file is too big.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(extract_text, filename, data),
            timeout=PARSE_TIMEOUT_SECONDS,
        )
    except TimeoutError as e:
        logger.warning(f"Parsing {filename} exceeded {PARSE_TIMEOUT_SECONDS}s; abandoned")
        raise UnsupportedDocumentError(
            f"Parsing '{filename}' took longer than {PARSE_TIMEOUT_SECONDS}s"
        ) from e

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import sha256_bytes
from .models import PdfDetail, SourceMetadata, WorkflowError


MAX_PDF_BYTES = 50 * 1024 * 1024
SOURCE_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}


@dataclass(frozen=True)
class LoadedSource:
    metadata: SourceMetadata
    data: bytes
    text: str | None


def load_source(
    path: Path,
    accepted_media_types: list[str],
) -> LoadedSource:
    path = path.resolve()
    if not path.is_file():
        raise WorkflowError(f"Source file does not exist: {path}")
    extension = path.suffix.lower()
    media_type = SOURCE_TYPES.get(extension)
    if media_type is None:
        raise WorkflowError("Unsupported source type. Use a .txt, .md, or .pdf file.")
    if media_type not in accepted_media_types:
        raise WorkflowError(f"Profile does not accept source type '{media_type}'.")

    data = path.read_bytes()
    if not data:
        raise WorkflowError("The source file is empty.")

    text: str | None = None
    if media_type == "application/pdf":
        if len(data) >= MAX_PDF_BYTES:
            raise WorkflowError("PDF sources must be smaller than 50 MB.")
        if not data.startswith(b"%PDF-"):
            raise WorkflowError("The .pdf source does not have a valid PDF header.")
    else:
        try:
            text = data.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise WorkflowError("Text sources must be valid UTF-8.") from error
        if not text:
            raise WorkflowError("The source file contains no text.")

    stored_filename = f"source{extension}"
    return LoadedSource(
        metadata=SourceMetadata(
            original_filename=path.name,
            stored_filename=stored_filename,
            media_type=media_type,
            sha256=sha256_bytes(data),
            size_bytes=len(data),
        ),
        data=data,
        text=text,
    )


def load_saved_source(run_dir: Path, metadata: SourceMetadata) -> LoadedSource:
    path = run_dir / metadata.stored_filename
    if not path.is_file():
        raise WorkflowError(f"Saved source is missing: {path}")
    data = path.read_bytes()
    if sha256_bytes(data) != metadata.sha256 or len(data) != metadata.size_bytes:
        raise WorkflowError(
            "The saved source has changed. Restore it or start a new run."
        )
    text = None
    if metadata.media_type != "application/pdf":
        try:
            text = data.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise WorkflowError("Saved text source is not valid UTF-8.") from error
    return LoadedSource(metadata=metadata, data=data, text=text)


def build_source_input(
    prompt: str,
    source: LoadedSource,
    pdf_detail: PdfDetail,
) -> str | list[dict[str, Any]]:
    if source.metadata.media_type != "application/pdf":
        return (
            f"{prompt.strip()}\n\n<source_document>\n{source.text}\n</source_document>"
        )

    encoded = base64.b64encode(source.data).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_file",
                    "filename": source.metadata.original_filename,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                    "detail": pdf_detail,
                },
                {
                    "type": "input_text",
                    "text": prompt.strip(),
                },
            ],
        }
    ]

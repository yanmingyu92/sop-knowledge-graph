"""
doc_converter.py
----------------
Convert .doc files to .docx and/or .pdf using Microsoft Word COM automation.

Requires: pywin32 (pip install pywin32)
Requires: Microsoft Word installed on the system.

Usage:
    from src.doc_converter import convert_doc_to_docx, convert_to_pdf, batch_convert_docs

    # Single file
    docx_path = convert_doc_to_docx(Path("input.doc"), Path("output_dir"))

    # Batch convert all .doc files
    results = batch_convert_docs(Path("source_dir"), Path("output_dir"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Word format constants
WD_FORMAT_DOCX = 16  # wdFormatXMLDocument
WD_FORMAT_PDF = 17   # wdFormatPDF


def _get_word_app() -> Any:
    """Get or create a Word COM application instance."""
    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False
    return word


def convert_doc_to_docx(doc_path: Path, output_dir: Path) -> Path:
    """Convert a .doc file to .docx format."""
    output_dir.mkdir(parents=True, exist_ok=True)
    docx_path = output_dir / (doc_path.stem + ".docx")

    word = _get_word_app()
    try:
        doc = word.Documents.Open(str(doc_path.resolve()))
        doc.SaveAs2(str(docx_path.resolve()), FileFormat=WD_FORMAT_DOCX)
        doc.Close(False)
        log.info("Converted .doc -> .docx: %s", docx_path.name)
    finally:
        word.Quit()

    return docx_path


def convert_to_pdf(source_path: Path, output_dir: Path) -> Path:
    """Convert a .doc or .docx file to PDF format."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / (source_path.stem + ".pdf")

    word = _get_word_app()
    try:
        doc = word.Documents.Open(str(source_path.resolve()))
        doc.SaveAs2(str(pdf_path.resolve()), FileFormat=WD_FORMAT_PDF)
        doc.Close(False)
        log.info("Converted -> PDF: %s", pdf_path.name)
    finally:
        word.Quit()

    return pdf_path


def batch_convert_docs(
    source_dir: Path,
    docx_output_dir: Path,
    pdf_output_dir: Path,
) -> dict[str, list[Path]]:
    """
    Batch convert all .doc files to .docx and PDF.

    Opens Word once and processes all files for efficiency.

    Args:
        source_dir: Root directory containing .doc files
        docx_output_dir: Directory for converted .docx files
        pdf_output_dir: Directory for converted PDF files

    Returns:
        {"docx": [converted_paths], "pdf": [converted_paths], "errors": [failed_paths]}
    """
    doc_files = sorted(set(
        f.resolve() for f in source_dir.rglob("*.doc")
        if f.suffix.lower() == ".doc"
    ))

    if not doc_files:
        log.info("No .doc files found in %s", source_dir)
        return {"docx": [], "pdf": [], "errors": []}

    # Deduplicate by filename (source may have subdirectory copies)
    seen_names: dict[str, Path] = {}
    for f in doc_files:
        if f.name not in seen_names:
            seen_names[f.name] = f
    unique_docs = list(seen_names.values())

    log.info("Found %d unique .doc files (from %d total)", len(unique_docs), len(doc_files))

    docx_output_dir.mkdir(parents=True, exist_ok=True)
    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, list[Path]] = {"docx": [], "pdf": [], "errors": []}

    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False

    try:
        for i, doc_path in enumerate(unique_docs, 1):
            log.info("  [%d/%d] Converting %s ...", i, len(unique_docs), doc_path.name)

            docx_path = docx_output_dir / (doc_path.stem + ".docx")
            pdf_path = pdf_output_dir / (doc_path.stem + ".pdf")

            try:
                doc = word.Documents.Open(str(doc_path))
                doc.SaveAs2(str(docx_path.resolve()), FileFormat=WD_FORMAT_DOCX)
                results["docx"].append(docx_path)
                doc.SaveAs2(str(pdf_path.resolve()), FileFormat=WD_FORMAT_PDF)
                results["pdf"].append(pdf_path)
                doc.Close(False)
            except Exception as exc:
                log.error("  Failed to convert %s: %s", doc_path.name, exc)
                results["errors"].append(doc_path)

    finally:
        word.Quit()

    log.info("Batch conversion complete: %d .docx, %d PDF, %d errors",
             len(results["docx"]), len(results["pdf"]), len(results["errors"]))

    return results


def batch_convert_docx_to_pdf(
    source_dir: Path,
    pdf_output_dir: Path,
    file_list: list[Path] | None = None,
) -> dict[str, list[Path]]:
    """Batch convert .docx files to PDF."""
    if file_list is not None:
        docx_files = file_list
    else:
        docx_files = sorted(source_dir.glob("*.docx"))

    if not docx_files:
        log.info("No .docx files to convert")
        return {"pdf": [], "errors": []}

    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, list[Path]] = {"pdf": [], "errors": []}

    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False

    try:
        for i, docx_path in enumerate(docx_files, 1):
            if i % 25 == 0 or i == len(docx_files):
                log.info("  [%d/%d] Converting to PDF ...", i, len(docx_files))

            pdf_path = pdf_output_dir / (docx_path.stem + ".pdf")

            if pdf_path.exists() and pdf_path.stat().st_mtime > docx_path.stat().st_mtime:
                results["pdf"].append(pdf_path)
                continue

            try:
                doc = word.Documents.Open(str(docx_path.resolve()))
                doc.SaveAs2(str(pdf_path.resolve()), FileFormat=WD_FORMAT_PDF)
                doc.Close(False)
                results["pdf"].append(pdf_path)
            except Exception as exc:
                log.error("  Failed to convert %s: %s", docx_path.name, exc)
                results["errors"].append(docx_path)

    finally:
        word.Quit()

    log.info("PDF conversion: %d converted, %d errors", len(results["pdf"]), len(results["errors"]))
    return results

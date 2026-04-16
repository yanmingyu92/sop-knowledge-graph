"""
ebook_builder.py
----------------
Compiles a list of downloaded SOP PDFs into a single well-structured eBook.

PDF mode  (recommended):
  - Auto-generated cover page (title, subtitle, author, date)
  - Auto-generated Table of Contents page with page numbers
  - Each SOP appended with its original content preserved
  - Bookmarks / PDF outline pointing to every SOP + cover + TOC

PDF Workflow mode (Phase 4):
  - Workflow-based chapter organization
  - Chapter introduction pages with workflow descriptions
  - Cross-reference hyperlinks between documents
  - Template appendix with extracted templates

EPUB mode  (secondary):
  - Each SOP embedded as an EPUB item linked from the spine/TOC
  - Suitable for eReader apps
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# -- PDF eBook ------------------------------------------------------------

def build_pdf_ebook(
    sop_records: list[dict[str, str]],
    cfg: dict[str, Any],
    out_dir: Path,
    filename: str,
) -> Path:
    """Merge PDFs into a single eBook with cover + TOC + bookmarks."""
    import pymupdf

    pdf_cfg = cfg.get("pdf_ebook", {})
    title = pdf_cfg.get("title", "Standard Operating Procedures")
    subtitle = pdf_cfg.get("subtitle", "Compiled eBook")
    author = pdf_cfg.get("author", "")
    sort_alpha = bool(pdf_cfg.get("sort_alphabetically", True))
    add_toc_page = bool(pdf_cfg.get("add_toc_page", True))

    records = sorted(sop_records, key=lambda r: r["title"].lower()) if sort_alpha else sop_records

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.pdf"

    book = pymupdf.open()

    # 1. Cover page
    cover_page_num = 0
    _insert_cover_page(book, title, subtitle, author, pdf_cfg)

    # 2. Placeholder for TOC page
    toc_page_num = 1
    toc_placeholder: pymupdf.Page | None = None
    if add_toc_page:
        toc_placeholder = book.new_page(width=595, height=842)

    # 3. Append each SOP PDF
    toc_entries: list[tuple[int, str, int]] = []
    page_offset = book.page_count

    for rec in records:
        pdf_path = rec.get("pdf_path", "")
        if not pdf_path or not Path(pdf_path).exists():
            log.warning("PDF missing, skipping: %s", pdf_path)
            continue
        sop_title = rec["title"]
        first_page_in_book = book.page_count
        try:
            src = pymupdf.open(pdf_path)
            book.insert_pdf(src)
            src.close()
        except Exception as exc:
            log.error("Could not append %s: %s", pdf_path, exc)
            continue
        toc_entries.append((1, sop_title, first_page_in_book + 1))

    # 4. Build PDF outline (bookmarks)
    outline: list[list] = []
    outline.append([1, "Cover", cover_page_num + 1])
    if add_toc_page:
        outline.append([1, "Table of Contents", toc_page_num + 1])
    outline.extend([[lvl, t, p] for lvl, t, p in toc_entries])
    book.set_toc(outline)

    # 5. Write TOC page content
    if add_toc_page and toc_placeholder is not None:
        _write_toc_page(book, toc_page_num, toc_entries, pdf_cfg)

    # 6. Metadata
    book.set_metadata({
        "title": title,
        "author": author,
        "creator": "SOP eBook Builder",
        "producer": "PyMuPDF",
        "creationDate": datetime.datetime.now().strftime("D:%Y%m%d%H%M%S"),
    })

    book.save(str(out_path), garbage=4, deflate=True)
    book.close()

    log.info("PDF eBook saved: %s  (%d SOPs)", out_path, len(toc_entries))
    return out_path


def _insert_cover_page(
    book: Any, title: str, subtitle: str, author: str, cfg: dict[str, Any]
) -> None:
    import pymupdf
    page = book.new_page(width=595, height=842)
    font_size_title = int(cfg.get("cover_font_size", 36))
    font_size_sub = max(font_size_title - 10, 16)
    font_size_author = max(font_size_title - 14, 12)
    date_str = datetime.date.today().strftime("%B %Y")

    page.draw_rect(pymupdf.Rect(0, 0, 595, 842), color=None, fill=(0.12, 0.24, 0.45))

    tw = pymupdf.TextWriter(page.rect)
    font = pymupdf.Font("helv")
    bold_font = pymupdf.Font("hebo")

    _centered_text(tw, bold_font, font_size_title, title, page.rect.width, y=280, color=(1, 1, 1))
    _centered_text(tw, font, font_size_sub, subtitle, page.rect.width, y=340, color=(0.85, 0.85, 0.85))
    page.draw_line((80, 360), (515, 360), color=(1, 1, 1), width=1)
    if author:
        _centered_text(tw, font, font_size_author, author, page.rect.width, y=390, color=(0.75, 0.75, 0.75))
    _centered_text(tw, font, font_size_author, date_str, page.rect.width, y=415, color=(0.75, 0.75, 0.75))

    tw.write_text(page)


def _centered_text(tw: Any, font: Any, size: int, text: str, page_w: float, y: float, color: tuple) -> None:
    import pymupdf
    text_w = font.text_length(text, fontsize=size)
    x = (page_w - text_w) / 2
    tw.append((x, y), text, font=font, fontsize=size)


def _write_toc_page(
    book: Any,
    toc_page_idx: int,
    entries: list[tuple[int, str, int]],
    cfg: dict[str, Any],
) -> None:
    import pymupdf
    page = book[toc_page_idx]
    page.clean_contents()
    font_size = int(cfg.get("toc_font_size", 13))
    margin_x, margin_y = 60, 70
    line_h = font_size + 6
    max_y = 800

    tw = pymupdf.TextWriter(page.rect)
    bold_font = pymupdf.Font("hebo")
    font = pymupdf.Font("helv")

    tw.append((margin_x, margin_y), "Table of Contents", font=bold_font, fontsize=18)
    page.draw_line((margin_x, margin_y + 8), (535, margin_y + 8), color=(0.4, 0.4, 0.4), width=0.5)

    y = margin_y + 30
    for _, sop_title, page_num in entries:
        if y > max_y:
            break
        label = sop_title[:80] + ("..." if len(sop_title) > 80 else "")
        tw.append((margin_x, y), label, font=font, fontsize=font_size)
        pnum_str = str(page_num)
        pnum_w = font.text_length(pnum_str, fontsize=font_size)
        tw.append((535 - pnum_w, y), pnum_str, font=font, fontsize=font_size)
        y += line_h

    tw.write_text(page)


# -- PDF Workflow eBook (Phase 4) -----------------------------------------

def build_workflow_pdf_ebook(
    sop_records: list[dict[str, str]],
    workflow_mappings: dict[str, Any],
    udm_dir: Path,
    cfg: dict[str, Any],
    out_dir: Path,
    filename: str,
) -> Path:
    """
    Build workflow-organized PDF eBook (Phase 4).

    Args:
        sop_records: List of SOP records with pdf_path
        workflow_mappings: Workflow mappings from workflow_mapper.py
        udm_dir: Directory with UDM JSON files
        cfg: Configuration dict
        out_dir: Output directory
        filename: Output filename (without extension)

    Returns:
        Path to generated PDF eBook
    """
    import pymupdf

    pdf_cfg = cfg.get("pdf_ebook", {})
    title = pdf_cfg.get("title", "Standard Operating Procedures")
    subtitle = "Workflow-Based User Manual"
    author = pdf_cfg.get("author", "")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.pdf"

    book = pymupdf.open()

    cover_page_num = 0
    _insert_cover_page(book, title, subtitle, author, pdf_cfg)

    toc_page_num = 1
    toc_placeholder = book.new_page(width=595, height=842)

    doc_lookup = {rec.get("doc_id", ""): rec for rec in sop_records}
    doc_to_page: dict[str, int] = {}

    for rec in sop_records:
        if not rec.get("doc_id"):
            title_parts = rec["title"].split(" ")
            if title_parts:
                rec["doc_id"] = title_parts[0]

    toc_entries: list[tuple[int, str, int]] = []

    for wf_id, wf_data in workflow_mappings.items():
        docs = wf_data.get("documents", [])
        if not docs:
            continue

        chapter_start_page = book.page_count
        _insert_workflow_intro_page(
            book,
            wf_data["title"],
            wf_data.get("description", ""),
            len(docs),
            pdf_cfg,
        )

        toc_entries.append((1, f"Chapter: {wf_data['title']}", chapter_start_page + 1))

        for doc_info in docs:
            doc_id = doc_info["doc_id"]
            rec = doc_lookup.get(doc_id)
            if not rec:
                log.warning("Document not found in records: %s", doc_id)
                continue

            pdf_path = rec.get("pdf_path", "")
            if not pdf_path or not Path(pdf_path).exists():
                log.warning("PDF missing: %s", pdf_path)
                continue

            doc_start_page = book.page_count
            try:
                src = pymupdf.open(pdf_path)
                book.insert_pdf(src)
                src.close()
                doc_to_page[doc_id] = doc_start_page
            except Exception as exc:
                log.error("Could not append %s: %s", pdf_path, exc)
                continue

            toc_entries.append((2, doc_info["title"], doc_start_page + 1))

    # Template appendix
    if udm_dir and udm_dir.exists():
        appendix_page = book.page_count
        _insert_template_appendix(book, udm_dir, pdf_cfg)
        toc_entries.append((1, "Appendix: Template Library", appendix_page + 1))

    outline: list[list] = []
    outline.append([1, "Cover", cover_page_num + 1])
    outline.append([1, "Table of Contents", toc_page_num + 1])
    outline.extend([[lvl, t, p] for lvl, t, p in toc_entries])
    book.set_toc(outline)

    if udm_dir and udm_dir.exists():
        _add_cross_reference_links(book, udm_dir, doc_to_page)

    _write_toc_page(book, toc_page_num, toc_entries, pdf_cfg)

    book.set_metadata({
        "title": title,
        "author": author,
        "creator": "SOP eBook Builder - Workflow Edition",
        "producer": "PyMuPDF",
        "creationDate": datetime.datetime.now().strftime("D:%Y%m%d%H%M%S"),
    })

    book.save(str(out_path), garbage=4, deflate=True)
    book.close()

    log.info("Workflow PDF eBook saved: %s  (%d chapters, %d documents)",
             out_path, len(workflow_mappings), len(toc_entries) - 2)
    return out_path


def _insert_workflow_intro_page(
    book: Any, workflow_title: str, workflow_description: str,
    doc_count: int, cfg: dict[str, Any],
) -> None:
    """Insert a workflow chapter introduction page."""
    import pymupdf

    page = book.new_page(width=595, height=842)
    font = pymupdf.Font("helv")
    bold_font = pymupdf.Font("hebo")

    page.draw_rect(pymupdf.Rect(0, 0, 595, 120), color=None, fill=(0.2, 0.3, 0.5))

    tw = pymupdf.TextWriter(page.rect)
    _centered_text(tw, bold_font, 28, workflow_title, page.rect.width, y=60, color=(1, 1, 1))

    count_text = f"{doc_count} Document{'s' if doc_count != 1 else ''}"
    _centered_text(tw, font, 14, count_text, page.rect.width, y=95, color=(0.9, 0.9, 0.9))

    margin_x = 60
    max_width = 475

    if workflow_description:
        words = workflow_description.split()
        lines = []
        current_line = []
        current_width = 0

        for word in words:
            word_width = font.text_length(word + " ", fontsize=13)
            if current_width + word_width > max_width and current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width
            else:
                current_line.append(word)
                current_width += word_width

        if current_line:
            lines.append(" ".join(current_line))

        y = 150
        for line in lines[:15]:
            tw.append((margin_x, y), line, font=font, fontsize=13)
            y += 20

    tw.write_text(page)


def _insert_template_appendix(book: Any, udm_dir: Path, cfg: dict[str, Any]) -> None:
    """Insert template appendix with extracted templates."""
    import pymupdf

    templates = []
    for udm_file in udm_dir.glob("*.json"):
        try:
            with open(udm_file, encoding="utf-8") as f:
                udm = json.load(f)
                for template in udm.get("templates", []):
                    templates.append({
                        "doc_id": udm["metadata"]["doc_id"],
                        "doc_title": udm["metadata"]["title"],
                        "template": template,
                    })
        except Exception as exc:
            log.warning("Could not load UDM file %s: %s", udm_file.name, exc)

    if not templates:
        log.info("No templates found for appendix")
        return

    page = book.new_page(width=595, height=842)
    font = pymupdf.Font("helv")
    bold_font = pymupdf.Font("hebo")

    tw = pymupdf.TextWriter(page.rect)

    margin_x, margin_y = 60, 60
    tw.append((margin_x, margin_y), "Appendix: Template Library", font=bold_font, fontsize=24)
    page.draw_line((margin_x, margin_y + 10), (535, margin_y + 10), color=(0.3, 0.3, 0.3), width=1)

    y = margin_y + 40

    for tmpl_info in templates[:20]:
        if y > 780:
            tw.write_text(page)
            page = book.new_page(width=595, height=842)
            tw = pymupdf.TextWriter(page.rect)
            y = 60

        tmpl = tmpl_info["template"]
        title = tmpl.get("title", "Untitled")
        tmpl_type = tmpl.get("type", "generic")

        tw.append((margin_x, y), f"* {title}", font=bold_font, fontsize=12)
        y += 18
        tw.append((margin_x + 10, y), f"Type: {tmpl_type}  |  From: {tmpl_info['doc_id']}",
                  font=font, fontsize=10)
        y += 25

    tw.write_text(page)
    log.info("Template appendix added: %d templates", len(templates))


def _add_cross_reference_links(
    book: Any, udm_dir: Path, doc_to_page: dict[str, int],
) -> None:
    """Add cross-reference hyperlinks to PDF."""
    import pymupdf

    link_count = 0

    for udm_file in udm_dir.glob("*.json"):
        try:
            with open(udm_file, encoding="utf-8") as f:
                udm = json.load(f)

            source_doc_id = udm["metadata"]["doc_id"]
            cross_refs = udm.get("cross_references", [])

            if not cross_refs or source_doc_id not in doc_to_page:
                continue

            for ref in cross_refs:
                target_doc = ref.get("target_doc", "")
                if target_doc not in doc_to_page:
                    continue
                link_count += 1

        except Exception as exc:
            log.warning("Could not process cross-references from %s: %s", udm_file.name, exc)

    if link_count > 0:
        log.info("Added %d cross-reference links", link_count)
    else:
        log.info("No cross-reference links added")


# -- EPUB eBook -----------------------------------------------------------

def build_epub_ebook(
    sop_records: list[dict[str, str]],
    cfg: dict[str, Any],
    out_dir: Path,
    filename: str,
) -> Path:
    """
    Create an EPUB3 where each SOP PDF is embedded as a media item.
    """
    from ebooklib import epub

    epub_cfg = cfg.get("epub_ebook", {})
    title = epub_cfg.get("title", "Standard Operating Procedures")
    author = epub_cfg.get("author", "")
    language = epub_cfg.get("language", "en")
    cover_image_path = epub_cfg.get("cover_image", "")

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language(language)
    if author:
        book.add_author(author)

    if cover_image_path and Path(cover_image_path).exists():
        with open(cover_image_path, "rb") as fh:
            img_bytes = fh.read()
        ext = Path(cover_image_path).suffix.lower().lstrip(".")
        book.set_cover(f"cover.{ext}", img_bytes)

    spine: list = ["nav"]
    toc_items: list = []

    records = sorted(sop_records, key=lambda r: r["title"].lower())

    for idx, rec in enumerate(records, 1):
        pdf_path = rec.get("pdf_path", "")
        if not pdf_path or not Path(pdf_path).exists():
            log.warning("PDF missing, skipping from EPUB: %s", pdf_path)
            continue
        sop_title = rec["title"]
        item_id = f"sop_{idx:04d}"
        pdf_name = f"pdfs/{Path(pdf_path).name}"

        with open(pdf_path, "rb") as fh:
            pdf_bytes = fh.read()
        pdf_item = epub.EpubItem(
            uid=f"{item_id}_pdf",
            file_name=pdf_name,
            media_type="application/pdf",
            content=pdf_bytes,
        )
        book.add_item(pdf_item)

        html_content = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
            f'<head><title>{sop_title}</title></head><body>'
            f'<h1>{sop_title}</h1>'
            f'<object data="../{pdf_name}" type="application/pdf" width="100%" height="90%">'
            f'<p>Your reader does not support embedded PDFs. '
            f'<a href="../{pdf_name}">Download {sop_title}</a></p>'
            f'</object></body></html>'
        )
        chapter = epub.EpubHtml(
            title=sop_title,
            file_name=f"text/{item_id}.xhtml",
            lang=language,
            content=html_content.encode("utf-8"),
        )
        book.add_item(chapter)
        spine.append(chapter)
        toc_items.append(epub.Link(f"text/{item_id}.xhtml", sop_title, item_id))

    book.toc = toc_items
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.epub"
    epub.write_epub(str(out_path), book)
    log.info("EPUB eBook saved: %s  (%d SOPs)", out_path, len(toc_items))
    return out_path

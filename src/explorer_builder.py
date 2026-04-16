#!/usr/bin/env python3
"""
explorer_builder.py
-------------------
Build a self-contained HTML knowledge explorer from knowledge graph outputs.

Reads:
    output/knowledge_graph/documents.jsonl
    output/knowledge_graph/sections.jsonl
    output/knowledge_graph/workflows.jsonl
    output/relationships.json

Generates:
    output/explorer/index.html

Usage:
    python -m src.explorer_builder
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _is_duplicate(doc_id: str) -> bool:
    """Check if a doc_id is a subdirectory duplicate (contains '__')."""
    return "__" in doc_id


def load_documents(jsonl_path: Path) -> list[dict]:
    """Load document metadata from documents.jsonl, filtering duplicates."""
    docs = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            if not _is_duplicate(doc["@id"]):
                docs.append(doc)
    log.info("Loaded %d documents (filtered duplicates)", len(docs))
    return docs


def load_sections(jsonl_path: Path) -> list[dict]:
    """Load section outlines from sections.jsonl, filtering duplicates."""
    sections = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sec = json.loads(line)
            if not _is_duplicate(sec["document_id"]):
                sections.append(sec)
    log.info("Loaded %d sections (filtered duplicates)", len(sections))
    return sections


def load_workflows(jsonl_path: Path) -> list[dict]:
    """Load workflow summaries from workflows.jsonl, filtering duplicate doc refs."""
    workflows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            wf = json.loads(line)
            wf["documents"] = [d for d in wf["documents"] if not _is_duplicate(d)]
            wf["document_count"] = len(wf["documents"])
            workflows.append(wf)
    log.info("Loaded %d workflows", len(workflows))
    return workflows


def load_relationships(rel_path: Path) -> tuple[list[dict], list[dict]]:
    """Load relationship graph, filtering duplicate nodes and edges."""
    with open(rel_path, encoding="utf-8") as f:
        data = json.load(f)

    valid_ids = set()
    nodes = []
    for node in data["nodes"]:
        if not _is_duplicate(node["doc_id"]):
            nodes.append(node)
            valid_ids.add(node["doc_id"])

    edges = []
    for edge in data["edges"]:
        if edge["source"] in valid_ids and edge["target"] in valid_ids:
            edges.append(edge)

    log.info("Loaded %d nodes, %d edges (filtered duplicates)", len(nodes), len(edges))
    return nodes, edges


# -- Constants -------------------------------------------------------------

WORKFLOW_COLORS: dict[str, str] = {
    "study_setup": "#4CAF50",
    "data_collection": "#2196F3",
    "data_transformation": "#FF9800",
    "analysis_reporting": "#9C27B0",
    "regulatory_submission": "#F44336",
    "safety_monitoring": "#E91E63",
    "quality_compliance": "#00BCD4",
    "external_data": "#795548",
    "medical_writing": "#607D8B",
    "special_studies": "#FFEB3B",
}

DOC_TYPE_SHAPES: dict[str, str] = {
    "SOP": "ellipse",
    "Work Instruction": "rectangle",
    "Template": "diamond",
    "Guidance": "round-rectangle",
}

DEFAULT_SHAPE = "ellipse"
MIN_NODE_SIZE = 20
MAX_NODE_SIZE = 50


# -- Cytoscape elements ---------------------------------------------------

def build_cytoscape_elements(
    docs: list[dict],
    nodes: list[dict],
    edges: list[dict],
    workflows: list[dict],
) -> list[dict]:
    """Build Cytoscape.js elements array from graph data."""
    doc_workflow: dict[str, str] = {}
    for wf in workflows:
        for doc_id in wf["documents"]:
            if doc_id not in doc_workflow:
                doc_workflow[doc_id] = wf["@id"]

    doc_meta: dict[str, dict] = {d["@id"]: d for d in docs}
    max_refs = max((d.get("cross_reference_count", 0) for d in docs), default=1) or 1
    valid_ids = {n["doc_id"] for n in nodes if n["doc_id"] in doc_meta}

    elements: list[dict] = []

    for node in nodes:
        doc_id = node["doc_id"]
        if doc_id not in doc_meta:
            continue
        meta = doc_meta[doc_id]
        wf_id = doc_workflow.get(doc_id, "")
        refs = meta.get("cross_reference_count", 0)
        size = MIN_NODE_SIZE + (MAX_NODE_SIZE - MIN_NODE_SIZE) * (refs / max_refs)

        elements.append({
            "data": {
                "id": doc_id,
                "label": doc_id,
                "title": meta.get("title", doc_id),
                "doc_type": meta.get("type", "SOP"),
                "workflow": wf_id,
                "color": WORKFLOW_COLORS.get(wf_id, "#999999"),
                "shape": DOC_TYPE_SHAPES.get(meta.get("type", ""), DEFAULT_SHAPE),
                "size": round(size),
            }
        })

    for edge in edges:
        if edge["source"] in valid_ids and edge["target"] in valid_ids:
            elements.append({
                "data": {
                    "source": edge["source"],
                    "target": edge["target"],
                    "type": edge.get("type", "mention"),
                }
            })

    log.info("Built %d Cytoscape elements (%d nodes, %d edges)",
             len(elements),
             sum(1 for e in elements if "source" not in e.get("data", {})),
             sum(1 for e in elements if "source" in e.get("data", {})))
    return elements


# -- Search index ----------------------------------------------------------

def build_search_index(
    docs: list[dict],
    sections: list[dict],
    workflows: list[dict],
) -> dict:
    """Build a search index for client-side substring matching."""
    doc_index = []
    for d in docs:
        search_text = " ".join([
            d.get("@id", ""), d.get("title", ""), d.get("type", ""), d.get("owner", ""),
        ]).lower()
        doc_index.append({"id": d["@id"], "title": d.get("title", d["@id"]), "type": d.get("type", ""), "search_text": search_text})

    sec_index = []
    for s in sections:
        search_text = " ".join([s.get("title", ""), s.get("document_id", "")]).lower()
        sec_index.append({"doc_id": s["document_id"], "title": s.get("title", ""), "section_id": s.get("section_id", ""), "level": s.get("level", 1), "search_text": search_text})

    wf_index = []
    for w in workflows:
        search_text = " ".join([w.get("title", ""), w.get("description", ""), w.get("@id", "")]).lower()
        wf_index.append({"id": w["@id"], "title": w.get("title", ""), "doc_count": w.get("document_count", 0), "search_text": search_text})

    log.info("Search index: %d docs, %d sections, %d workflows", len(doc_index), len(sec_index), len(wf_index))
    return {"documents": doc_index, "sections": sec_index, "workflows": wf_index}


# -- PDF path mapping -----------------------------------------------------

def build_pdf_map(
    udm_dir: Path,
    pdf_renditions_dir: Path,
    relative_prefix: str = "../pdf_renditions",
) -> dict[str, str]:
    """Map doc_id to relative PDF path by checking UDM file_path against renditions."""
    pdf_map: dict[str, str] = {}
    for udm_file in sorted(udm_dir.glob("*.json")):
        try:
            with open(udm_file, encoding="utf-8") as f:
                udm = json.load(f)
            doc_id = udm["metadata"]["doc_id"]
            if _is_duplicate(doc_id):
                continue
            source_path = udm["metadata"].get("file_path", "")
            if not source_path:
                continue
            stem = Path(source_path).stem
            pdf_name = f"{stem}.pdf"
            pdf_path = pdf_renditions_dir / pdf_name
            if pdf_path.exists():
                pdf_map[doc_id] = f"{relative_prefix}/{pdf_name}"
        except Exception:
            continue
    log.info("PDF map: %d documents have PDF renditions", len(pdf_map))
    return pdf_map


# -- Section grouping ------------------------------------------------------

def group_sections_by_doc(sections: list[dict]) -> dict[str, list[dict]]:
    """Group sections by their parent document_id."""
    grouped: dict[str, list[dict]] = {}
    for sec in sections:
        doc_id = sec["document_id"]
        if doc_id not in grouped:
            grouped[doc_id] = []
        grouped[doc_id].append({
            "title": sec.get("title", ""),
            "section_id": sec.get("section_id", ""),
            "level": sec.get("level", 1),
            "content_length": sec.get("content_length", 0),
        })
    return grouped


from jinja2 import Environment, FileSystemLoader


# -- Doc details for right panel -------------------------------------------

def build_doc_details(
    docs: list[dict],
    sections_grouped: dict[str, list[dict]],
    edges: list[dict],
    workflows: list[dict],
) -> dict[str, dict]:
    """Build per-document detail objects for the right panel."""
    doc_workflows: dict[str, list[str]] = {}
    for wf in workflows:
        for doc_id in wf["documents"]:
            doc_workflows.setdefault(doc_id, []).append(wf["@id"])

    doc_related: dict[str, set[str]] = {}
    doc_title_map: dict[str, str] = {d["@id"]: d.get("title", d["@id"]) for d in docs}
    for edge in edges:
        doc_related.setdefault(edge["source"], set()).add(edge["target"])
        doc_related.setdefault(edge["target"], set()).add(edge["source"])

    details: dict[str, dict] = {}
    for d in docs:
        doc_id = d["@id"]
        related = [
            {"id": rid, "title": doc_title_map.get(rid, rid)}
            for rid in sorted(doc_related.get(doc_id, set()))
        ]
        details[doc_id] = {
            "id": doc_id,
            "title": d.get("title", doc_id),
            "doc_type": d.get("type", "SOP"),
            "version": d.get("version", ""),
            "owner": d.get("owner", ""),
            "workflows": doc_workflows.get(doc_id, []),
            "sections": sections_grouped.get(doc_id, []),
            "related": related,
        }
    return details


# -- Main build function ---------------------------------------------------

def build_explorer(
    kg_dir: Path,
    rel_file: Path,
    udm_dir: Path,
    pdf_dir: Path,
    out_dir: Path,
    template_path: Path | None = None,
) -> Path:
    """Build the self-contained HTML knowledge explorer."""
    if template_path is None:
        template_path = Path(__file__).parent / "explorer_template.html"

    docs = load_documents(kg_dir / "documents.jsonl")
    sections = load_sections(kg_dir / "sections.jsonl")
    workflows = load_workflows(kg_dir / "workflows.jsonl")
    nodes, edges = load_relationships(rel_file)

    elements = build_cytoscape_elements(docs, nodes, edges, workflows)
    search_index = build_search_index(docs, sections, workflows)
    pdf_map = build_pdf_map(udm_dir, pdf_dir, "../pdf_renditions")
    sections_grouped = group_sections_by_doc(sections)
    doc_details = build_doc_details(docs, sections_grouped, edges, workflows)

    workflow_meta = []
    for wf in workflows:
        workflow_meta.append({
            "id": wf["@id"],
            "title": wf.get("title", wf["@id"]),
            "doc_count": wf.get("document_count", 0),
            "color": WORKFLOW_COLORS.get(wf["@id"], "#999999"),
        })

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
    )
    template = env.get_template(template_path.name)

    from datetime import datetime
    html = template.render(
        elements_json=json.dumps(elements),
        search_index_json=json.dumps(search_index),
        doc_details_json=json.dumps(doc_details),
        workflow_meta_json=json.dumps(workflow_meta),
        pdf_map_json=json.dumps(pdf_map),
        total_docs=len(docs),
        total_workflows=len(workflows),
        total_edges=len(edges),
        generated_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    log.info("Explorer generated: %s (%.0f KB)", out_path, size_kb)
    return out_path


# -- CLI entry point -------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    base = Path(__file__).parent.parent
    result = build_explorer(
        kg_dir=base / "output" / "knowledge_graph",
        rel_file=base / "output" / "relationships.json",
        udm_dir=base / "output" / "udm",
        pdf_dir=base / "output" / "pdf_renditions",
        out_dir=base / "output" / "explorer",
    )
    print(f"Explorer: {result}")

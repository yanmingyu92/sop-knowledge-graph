"""
workflow_mapper.py
------------------
Phase 2: Workflow Taxonomy & Mapping

Maps documents to lifecycle workflow categories based on:
  - Keyword matching (content-based scoring)
  - Cross-reference analysis (document clustering)
  - Manual overrides (domain expert assignments)

Supports multi-workflow documents (e.g., a document can belong to both
"data_transformation" and "analysis_reporting").

Usage:
    mappings = map_documents_to_workflows(udm_files, taxonomy_path, overrides_path)
    save_workflow_mappings(mappings, "output/workflow_mappings.json")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


# =========================================================================
# Workflow Mapping
# =========================================================================

def map_documents_to_workflows(
    udm_files: list[Path],
    taxonomy_path: str | Path,
    overrides_path: str | Path,
    score_threshold: float = 0.3,
) -> dict[str, Any]:
    """
    Map UDM documents to workflows.

    Args:
        udm_files: List of paths to UDM JSON files
        taxonomy_path: Path to workflow_taxonomy.yaml
        overrides_path: Path to workflow_overrides.yaml
        score_threshold: Minimum score to assign a workflow (0.0-1.0)

    Returns:
        Workflow mappings dictionary:
        {
          "workflow_id": {
            "title": "Workflow Title",
            "documents": [
              {"doc_id": "...", "title": "...", "score": 0.95, "primary": true},
              ...
            ]
          }
        }
    """
    # Load taxonomy
    log.info("Loading workflow taxonomy from %s", taxonomy_path)
    with open(taxonomy_path, encoding="utf-8") as f:
        taxonomy_data = yaml.safe_load(f)
    workflows = {w["id"]: w for w in taxonomy_data["workflows"]}

    # Load overrides
    log.info("Loading manual overrides from %s", overrides_path)
    with open(overrides_path, encoding="utf-8") as f:
        overrides_data = yaml.safe_load(f) or {}
    overrides = overrides_data.get("manual_assignments", {})

    # Initialize workflow mappings
    mappings = {}
    for wf_id, wf_data in workflows.items():
        mappings[wf_id] = {
            "title": wf_data["title"],
            "description": wf_data["description"],
            "documents": [],
        }

    # Process each document
    log.info("Mapping %d documents to workflows...", len(udm_files))
    doc_scores = []

    for udm_file in udm_files:
        with open(udm_file, encoding="utf-8") as f:
            udm = json.load(f)

        doc_id = udm["metadata"]["doc_id"]
        doc_title = udm["metadata"]["title"]

        # Check for manual override
        if doc_id in overrides:
            workflow_ids = overrides[doc_id]
            log.info("  Manual override: %s -> %s", doc_id, workflow_ids)
            for idx, wf_id in enumerate(workflow_ids):
                if wf_id in mappings:
                    mappings[wf_id]["documents"].append({
                        "doc_id": doc_id,
                        "title": doc_title,
                        "score": 1.0,
                        "primary": (idx == 0),
                    })
            continue

        # Keyword-based scoring
        workflow_scores = {}
        for wf_id, wf_data in workflows.items():
            score = _score_document_for_workflow(udm, wf_data)
            if score >= score_threshold:
                workflow_scores[wf_id] = score

        if not workflow_scores:
            log.warning("  No workflow match for %s (threshold=%.2f)", doc_id, score_threshold)
            default_wf = _get_default_workflow(udm["metadata"]["type"])
            workflow_scores[default_wf] = score_threshold

        doc_scores.append(({"doc_id": doc_id, "title": doc_title}, workflow_scores))

    # Assign documents to workflows
    for doc_info, workflow_scores in doc_scores:
        sorted_workflows = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

        for idx, (wf_id, score) in enumerate(sorted_workflows):
            mappings[wf_id]["documents"].append({
                "doc_id": doc_info["doc_id"],
                "title": doc_info["title"],
                "score": round(score, 2),
                "primary": (idx == 0),
            })

    # Sort documents within each workflow by title
    for wf_id in mappings:
        mappings[wf_id]["documents"].sort(key=lambda d: d["title"].lower())

    log.info("Workflow mapping complete")
    return mappings


def _score_document_for_workflow(udm: dict[str, Any], workflow: dict[str, Any]) -> float:
    """
    Score a document against a workflow using keyword matching.

    Args:
        udm: Unified Document Model
        workflow: Workflow definition with keywords

    Returns:
        Score between 0.0 and 1.0
    """
    keywords = [k.lower() for k in workflow.get("keywords", [])]
    if not keywords:
        return 0.0

    searchable_text = _extract_searchable_text(udm).lower()

    matches = 0
    for keyword in keywords:
        if keyword in searchable_text:
            matches += 1

    score = matches / len(keywords)
    return min(score, 1.0)


def _extract_searchable_text(udm: dict[str, Any]) -> str:
    """Extract all text from UDM for keyword matching."""
    parts = []

    meta = udm["metadata"]
    parts.append(meta.get("title", ""))
    parts.append(meta.get("type", ""))

    for section in udm.get("sections", []):
        parts.append(section.get("title", ""))
        parts.append(section.get("content", ""))

    for proc in udm.get("procedures", []):
        parts.append(proc.get("action", ""))

    for table in udm.get("tables", [])[:5]:
        parts.append(table.get("title", ""))
        for row in table.get("rows", [])[:10]:
            parts.extend(str(v) for v in row.values())

    return " ".join(parts)


def _get_default_workflow(doc_type: str) -> str:
    """Fallback workflow assignment based on document type."""
    doc_type_lower = doc_type.lower()

    if "work instruction" in doc_type_lower:
        return "data_transformation"
    elif "job aid" in doc_type_lower:
        return "analysis_reporting"
    elif "template" in doc_type_lower:
        return "analysis_reporting"
    elif "guidance" in doc_type_lower:
        return "quality_compliance"
    else:
        return "quality_compliance"


def save_workflow_mappings(mappings: dict[str, Any], output_path: str | Path) -> None:
    """Save workflow mappings to JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)

    log.info("Workflow mappings saved to %s", path)

    total_docs = sum(len(wf["documents"]) for wf in mappings.values())
    log.info("")
    log.info("=== Workflow Mapping Summary ===")
    for wf_id, wf_data in mappings.items():
        doc_count = len(wf_data["documents"])
        primary_count = sum(1 for d in wf_data["documents"] if d["primary"])
        log.info("  %s: %d documents (%d primary)", wf_data["title"], doc_count, primary_count)
    log.info("  Total: %d document-workflow assignments", total_docs)


# =========================================================================
# Relationship Graph
# =========================================================================

def build_relationship_graph(udm_files: list[Path]) -> dict[str, Any]:
    """
    Build a document relationship graph from cross-references.

    Args:
        udm_files: List of paths to UDM JSON files

    Returns:
        Relationship graph:
        {
          "nodes": [{"doc_id": "...", "title": "..."}],
          "edges": [{"source": "...", "target": "...", "type": "..."}]
        }
    """
    nodes = []
    edges = []
    doc_ids = set()

    log.info("Building relationship graph from %d documents...", len(udm_files))

    for udm_file in udm_files:
        with open(udm_file, encoding="utf-8") as f:
            udm = json.load(f)

        doc_id = udm["metadata"]["doc_id"]
        doc_title = udm["metadata"]["title"]

        if doc_id not in doc_ids:
            nodes.append({"doc_id": doc_id, "title": doc_title})
            doc_ids.add(doc_id)

        for ref in udm.get("cross_references", []):
            target_doc = ref["target_doc"]
            ref_type = ref["reference_type"]

            edges.append({
                "source": doc_id,
                "target": target_doc,
                "type": ref_type,
            })

    log.info("Relationship graph: %d nodes, %d edges", len(nodes), len(edges))

    return {
        "nodes": nodes,
        "edges": edges,
    }


def save_relationship_graph(graph: dict[str, Any], output_path: str | Path) -> None:
    """Save relationship graph to JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

    log.info("Relationship graph saved to %s", path)

"""
knowledge_graph_builder.py
--------------------------
Phase 3: Knowledge Graph Generation

Builds multi-format knowledge graphs from extracted UDM documents and workflow mappings.
Generates 4 output formats:

  1. JSONL - Streaming format (one object per line)
  2. Hierarchical JSON - Organized by workflow for selective loading
  3. JSON-LD - Graph database ready (Neo4j, RDF stores)
  4. Index - Fast lookup metadata for progressive loading

Usage:
    builder = KnowledgeGraphBuilder(udm_dir, workflow_mappings)
    builder.build_all_formats(output_dir)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# =========================================================================
# Knowledge Graph Builder
# =========================================================================

class KnowledgeGraphBuilder:
    """Builds multi-format knowledge graphs from UDM + workflow mappings."""

    def __init__(
        self,
        udm_dir: str | Path,
        workflow_mappings: dict[str, Any],
    ):
        self.udm_dir = Path(udm_dir)
        self.workflow_mappings = workflow_mappings
        self.udm_cache: dict[str, dict] = {}

    def build_all_formats(self, output_dir: str | Path) -> None:
        """Generate all knowledge graph output formats."""
        kg_dir = Path(output_dir) / "knowledge_graph"
        kg_dir.mkdir(parents=True, exist_ok=True)

        log.info("Building knowledge graph in %s", kg_dir)

        self._load_udm_cache()

        self.generate_jsonl(kg_dir)
        self.generate_hierarchical_json(kg_dir)
        self.generate_json_ld(kg_dir)
        self.generate_index(kg_dir)

        log.info("Knowledge graph generation complete")

    def _load_udm_cache(self) -> None:
        """Load all UDM files into memory cache."""
        log.info("Loading UDM files from %s", self.udm_dir)

        udm_files = list(self.udm_dir.glob("*.json"))
        for udm_file in udm_files:
            with open(udm_file, encoding="utf-8") as f:
                udm = json.load(f)
                doc_id = udm["metadata"]["doc_id"]
                self.udm_cache[doc_id] = udm

        log.info("Loaded %d UDM files", len(self.udm_cache))

    # -- Format 1: JSONL (Streaming) --------------------------------------

    def generate_jsonl(self, output_dir: Path) -> None:
        """Generate JSONL files (one JSON object per line)."""
        log.info("Generating JSONL format...")

        docs_file = output_dir / "documents.jsonl"
        with open(docs_file, "w", encoding="utf-8") as f:
            for doc_id, udm in self.udm_cache.items():
                doc_node = self._create_document_node(udm)
                f.write(json.dumps(doc_node, ensure_ascii=False) + "\n")
        log.info("  %s (%d documents)", docs_file.name, len(self.udm_cache))

        workflows_file = output_dir / "workflows.jsonl"
        with open(workflows_file, "w", encoding="utf-8") as f:
            for wf_id, wf_data in self.workflow_mappings.items():
                wf_node = {
                    "@type": "Workflow",
                    "@id": wf_id,
                    "title": wf_data["title"],
                    "description": wf_data["description"],
                    "document_count": len(wf_data["documents"]),
                    "documents": [d["doc_id"] for d in wf_data["documents"]],
                }
                f.write(json.dumps(wf_node, ensure_ascii=False) + "\n")
        log.info("  %s (%d workflows)", workflows_file.name, len(self.workflow_mappings))

        sections_file = output_dir / "sections.jsonl"
        section_count = 0
        with open(sections_file, "w", encoding="utf-8") as f:
            for doc_id, udm in self.udm_cache.items():
                for section in udm.get("sections", []):
                    section_node = {
                        "@type": "Section",
                        "@id": f"{doc_id}__section_{section['id']}",
                        "document_id": doc_id,
                        "section_id": section["id"],
                        "level": section["level"],
                        "title": section["title"],
                        "content_length": len(section.get("content", "")),
                    }
                    f.write(json.dumps(section_node, ensure_ascii=False) + "\n")
                    section_count += 1
        log.info("  %s (%d sections)", sections_file.name, section_count)

    def _create_document_node(self, udm: dict[str, Any]) -> dict[str, Any]:
        """Create a document node for JSONL output."""
        meta = udm["metadata"]
        return {
            "@type": "Document",
            "@id": meta["doc_id"],
            "title": meta["title"],
            "type": meta["type"],
            "version": meta.get("version", ""),
            "owner": meta.get("owner", ""),
            "source_format": meta.get("source_format", ""),
            "section_count": len(udm.get("sections", [])),
            "procedure_count": len(udm.get("procedures", [])),
            "table_count": len(udm.get("tables", [])),
            "template_count": len(udm.get("templates", [])),
            "cross_reference_count": len(udm.get("cross_references", [])),
        }

    # -- Format 2: Hierarchical JSON (by workflow) -------------------------

    def generate_hierarchical_json(self, output_dir: Path) -> None:
        """Generate hierarchical JSON files organized by workflow."""
        log.info("Generating hierarchical JSON format...")

        by_workflow_dir = output_dir / "by_workflow"
        by_workflow_dir.mkdir(exist_ok=True)

        for wf_id, wf_data in self.workflow_mappings.items():
            workflow_graph = {
                "workflow": {
                    "id": wf_id,
                    "title": wf_data["title"],
                    "description": wf_data["description"],
                    "documents": [],
                }
            }

            for doc_info in wf_data["documents"]:
                doc_id = doc_info["doc_id"]
                if doc_id not in self.udm_cache:
                    log.warning("  UDM not found for %s", doc_id)
                    continue

                udm = self.udm_cache[doc_id]
                doc_node = {
                    "doc_id": doc_id,
                    "title": doc_info["title"],
                    "score": doc_info["score"],
                    "primary": doc_info["primary"],
                    "type": udm["metadata"]["type"],
                    "sections": udm.get("sections", []),
                    "procedures": udm.get("procedures", []),
                    "tables": udm.get("tables", []),
                    "templates": udm.get("templates", []),
                    "cross_references": udm.get("cross_references", []),
                }

                workflow_graph["workflow"]["documents"].append(doc_node)

            wf_file = by_workflow_dir / f"{wf_id}.json"
            with open(wf_file, "w", encoding="utf-8") as f:
                json.dump(workflow_graph, f, indent=2, ensure_ascii=False)

        log.info("  by_workflow/ (%d workflow files)", len(self.workflow_mappings))

    # -- Format 3: JSON-LD (Graph Database Ready) --------------------------

    def generate_json_ld(self, output_dir: Path) -> None:
        """Generate JSON-LD graph format for import into graph databases."""
        log.info("Generating JSON-LD format...")

        graph_nodes = []

        # Add workflow nodes
        for wf_id, wf_data in self.workflow_mappings.items():
            wf_node = {
                "@type": "sop:Workflow",
                "@id": f"sop:workflow/{wf_id}",
                "name": wf_data["title"],
                "description": wf_data["description"],
                "hasPart": [f"sop:doc/{d['doc_id']}" for d in wf_data["documents"]],
            }
            graph_nodes.append(wf_node)

        # Add document nodes
        for doc_id, udm in self.udm_cache.items():
            meta = udm["metadata"]
            doc_node = {
                "@type": "sop:Document",
                "@id": f"sop:doc/{doc_id}",
                "name": meta["title"],
                "documentType": meta["type"],
                "version": meta.get("version", ""),
                "author": meta.get("owner", ""),
                "references": [
                    f"sop:doc/{ref['target_doc']}"
                    for ref in udm.get("cross_references", [])
                ],
            }
            graph_nodes.append(doc_node)

            # Add section nodes
            for section in udm.get("sections", []):
                section_node = {
                    "@type": "sop:Section",
                    "@id": f"sop:doc/{doc_id}/section/{section['id']}",
                    "name": section["title"],
                    "level": section["level"],
                    "isPartOf": f"sop:doc/{doc_id}",
                }
                graph_nodes.append(section_node)

        # Build JSON-LD document
        json_ld = {
            "@context": {
                "@vocab": "http://schema.org/",
                "sop": "http://example.org/sop-ontology#",
                "references": {"@id": "sop:references", "@type": "@id"},
                "hasPart": {"@id": "schema:hasPart", "@type": "@id"},
                "isPartOf": {"@id": "schema:isPartOf", "@type": "@id"},
            },
            "@graph": graph_nodes,
        }

        jsonld_file = output_dir / "graph.jsonld"
        with open(jsonld_file, "w", encoding="utf-8") as f:
            json.dump(json_ld, f, indent=2, ensure_ascii=False)

        log.info("  %s (%d nodes)", jsonld_file.name, len(graph_nodes))

    # -- Format 4: Index (Progressive Loading) -----------------------------

    def generate_index(self, output_dir: Path) -> None:
        """Generate index.json for fast lookup and progressive loading."""
        log.info("Generating progressive loading index...")

        index = {
            "version": "1.0",
            "total_documents": len(self.udm_cache),
            "total_workflows": len(self.workflow_mappings),
            "workflows": {},
            "documents": {},
        }

        for wf_id, wf_data in self.workflow_mappings.items():
            wf_file = output_dir / "by_workflow" / f"{wf_id}.json"
            file_size = wf_file.stat().st_size if wf_file.exists() else 0

            top_docs = sorted(wf_data["documents"], key=lambda d: d["score"], reverse=True)[:3]

            index["workflows"][wf_id] = {
                "title": wf_data["title"],
                "document_count": len(wf_data["documents"]),
                "file_path": f"by_workflow/{wf_id}.json",
                "size_bytes": file_size,
                "top_documents": [d["doc_id"] for d in top_docs],
            }

        for doc_id, udm in self.udm_cache.items():
            meta = udm["metadata"]

            doc_workflows = []
            for wf_id, wf_data in self.workflow_mappings.items():
                if any(d["doc_id"] == doc_id for d in wf_data["documents"]):
                    doc_workflows.append(wf_id)

            index["documents"][doc_id] = {
                "title": meta["title"],
                "type": meta["type"],
                "workflows": doc_workflows,
                "sections": len(udm.get("sections", [])),
                "procedures": len(udm.get("procedures", [])),
                "tables": len(udm.get("tables", [])),
                "templates": len(udm.get("templates", [])),
            }

        index_file = output_dir / "index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        log.info("  %s", index_file.name)


# =========================================================================
# Convenience Functions
# =========================================================================

def build_knowledge_graph(
    udm_dir: str | Path,
    workflow_mappings_file: str | Path,
    output_dir: str | Path,
) -> None:
    """
    Build all knowledge graph formats from UDM files and workflow mappings.

    Args:
        udm_dir: Directory containing UDM JSON files
        workflow_mappings_file: Path to workflow_mappings.json
        output_dir: Output directory for knowledge graph
    """
    with open(workflow_mappings_file, encoding="utf-8") as f:
        workflow_mappings = json.load(f)

    builder = KnowledgeGraphBuilder(udm_dir, workflow_mappings)
    builder.build_all_formats(output_dir)

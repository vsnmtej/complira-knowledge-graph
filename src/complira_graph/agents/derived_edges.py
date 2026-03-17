#!/usr/bin/env python3
"""
DerivedEdgesAgent - Creates edges derived from existing graph data.

This agent creates edges that can be deterministically derived from existing
collections without requiring external data sources (except for ATT&CK-NIST mapping).

Edges Created:
1. technique_exploits_weakness (ATT&CK → CWE via CAPEC bridge)
   - Graph traversal: attack_techniques → capec_maps_to_attack → capec_patterns → capec_relates_to_cwe → weaknesses
   - Expected: ~5,562 edges

2. technique_mitigated_by_control (ATT&CK → NIST 800-53)
   - External mapping from MITRE (JSON format)
   - Expected: ~8,000 edges

Run Order: MUST run AFTER all base agents (ATT&CK, CAPEC, CWE, NIST 800-53)
"""

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import requests
from arango.database import StandardDatabase
from openpyxl import load_workbook

from complira_graph.agents.base import BaseIngestionAgent


class DerivedEdgesAgent(BaseIngestionAgent):
    """Agent for creating derived edge collections from existing graph data."""

    def __init__(self, db: StandardDatabase = None):
        """Initialize agent."""
        super().__init__(db)

        # Create edge collections if they don't exist
        self._ensure_edge_collections()

    def _get_primary_collection(self) -> str:
        """Get primary collection name for this agent."""
        return "technique_exploits_weakness"

    def _ensure_edge_collections(self):
        """Create edge collections if they don't exist."""
        collections = [
            "technique_exploits_weakness",
            "technique_mitigated_by_control",
        ]

        for coll_name in collections:
            if not self.db.has_collection(coll_name):
                self.logger.info(f"Creating edge collection: {coll_name}")
                collection = self.db.create_collection(coll_name, edge=True)

                # Add indexes for performance
                collection.add_hash_index(fields=["_from"], unique=False)
                collection.add_hash_index(fields=["_to"], unique=False)
                collection.add_hash_index(fields=["source"], unique=False)

                self.logger.info(f"Created edge collection with indexes: {coll_name}")

    def fetch_data(self) -> dict[str, list[dict]]:
        """
        Fetch data for both edge types.

        Returns dict with two keys:
        - 'technique_exploits_weakness': edges from graph traversal
        - 'technique_mitigated_by_control': edges from external mapping
        """
        self.logger.info("Fetching derived edge data")

        data = {
            "technique_exploits_weakness": self._derive_technique_weakness_edges(),
            "technique_mitigated_by_control": self._fetch_technique_control_mapping(),
        }

        self.logger.info(
            "Fetched derived edges",
            technique_exploits_weakness=len(data["technique_exploits_weakness"]),
            technique_mitigated_by_control=len(data["technique_mitigated_by_control"]),
        )

        return data

    def _derive_technique_weakness_edges(self) -> list[dict]:
        """
        Derive technique_exploits_weakness edges via graph traversal.

        Path: attack_techniques → capec_maps_to_attack → capec_patterns → capec_relates_to_cwe → weaknesses

        Returns list of edge dictionaries with:
        - technique_id: ATT&CK technique ID (e.g., 'T1059')
        - technique_name: ATT&CK technique name
        - cwe_id: CWE ID (e.g., 'CWE-78')
        - cwe_name: CWE name
        - capec_ids: List of CAPEC IDs in the path (for provenance)
        """
        self.logger.info("Deriving technique_exploits_weakness via graph traversal")

        # AQL query to traverse ATT&CK → CAPEC → CWE
        query = """
        FOR technique IN attack_techniques
          // Find CAPEC patterns that map to this ATT&CK technique
          FOR capec_attack_edge IN capec_maps_to_attack
            FILTER capec_attack_edge._to == technique._id

            LET capec = DOCUMENT(capec_attack_edge._from)
            FILTER capec != null

            // Find CWEs related to this CAPEC pattern
            FOR capec_cwe_edge IN capec_relates_to_cwe
              FILTER capec_cwe_edge._from == capec._id

              LET cwe = DOCUMENT(capec_cwe_edge._to)
              FILTER cwe != null

              COLLECT
                technique_id = technique._id,
                technique_key = technique._key,
                technique_name = technique.name,
                cwe_id = cwe._id,
                cwe_key = cwe._key,
                cwe_name = cwe.name
              AGGREGATE capec_ids = UNIQUE(capec._key)

              RETURN {
                technique_id: technique_id,
                technique_key: technique_key,
                technique_name: technique_name,
                cwe_id: cwe_id,
                cwe_key: cwe_key,
                cwe_name: cwe_name,
                capec_ids: capec_ids
              }
        """

        cursor = self.db.aql.execute(query)
        edges = list(cursor)

        self.logger.info(
            f"Derived {len(edges)} technique_exploits_weakness edges via CAPEC bridge"
        )

        return edges

    def _fetch_technique_control_mapping(self) -> list[dict]:
        """
        Fetch ATT&CK → NIST 800-53 mapping from MITRE.

        Source: https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings
        Excel file: https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings/raw/main/frameworks/attack_10_1/nist800_53_r5/nist800-53-r5-mappings.xlsx

        Returns list of mappings with:
        - technique_id: ATT&CK technique ID (e.g., 'T1059')
        - control_id: NIST 800-53 control ID (e.g., 'AC-3')
        """
        self.logger.info("Fetching ATT&CK → NIST 800-53 mapping from MITRE")

        url = "https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings/raw/main/frameworks/attack_10_1/nist800_53_r5/nist800-53-r5-mappings.xlsx"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            self.logger.info(
                f"Successfully fetched Excel file ({len(response.content):,} bytes)"
            )

        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch MITRE mapping Excel file: {e}")
            return []

        # Parse Excel file
        mappings = []

        try:
            # Load workbook from bytes
            wb = load_workbook(BytesIO(response.content), read_only=True, data_only=True)

            # The first sheet contains the mappings
            ws = wb.active

            # Headers are in row 1: ['Control ID', 'Control Name', 'Mapping Type', 'Technique ID', 'Technique Name']
            # We need columns 0 (Control ID) and 3 (Technique ID)

            for row in ws.iter_rows(min_row=2, values_only=True):  # Skip header row
                if not row or len(row) < 4:
                    continue

                control_id = row[0]
                technique_id = row[3]

                # Skip empty rows
                if not control_id or not technique_id:
                    continue

                # Validate format
                control_id = str(control_id).strip()
                technique_id = str(technique_id).strip()

                if not control_id or not technique_id:
                    continue

                mappings.append(
                    {
                        "technique_id": technique_id,
                        "control_id": control_id,
                    }
                )

            wb.close()

            self.logger.info(
                f"Parsed {len(mappings)} ATT&CK → NIST 800-53 mappings from Excel"
            )

        except Exception as e:
            self.logger.error(f"Failed to parse Excel file: {e}")
            return []

        return mappings

    def transform_data(self, raw_data: dict[str, list[dict]]) -> dict[str, list[dict]]:
        """
        Transform raw edge data into ArangoDB edge format.

        Args:
            raw_data: Dict with 'technique_exploits_weakness' and 'technique_mitigated_by_control' lists

        Returns:
            Dict with same keys, values are lists of edge documents ready for insertion
        """
        self.logger.info("Transforming derived edge data")

        transformed = {
            "technique_exploits_weakness": self._transform_weakness_edges(
                raw_data["technique_exploits_weakness"]
            ),
            "technique_mitigated_by_control": self._transform_control_edges(
                raw_data["technique_mitigated_by_control"]
            ),
        }

        self.logger.info(
            "Transformed edges",
            technique_exploits_weakness=len(transformed["technique_exploits_weakness"]),
            technique_mitigated_by_control=len(
                transformed["technique_mitigated_by_control"]
            ),
        )

        return transformed

    def _transform_weakness_edges(self, raw_edges: list[dict]) -> list[dict]:
        """Transform technique → weakness edges into ArangoDB edge format."""
        edges = []
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        for edge in raw_edges:
            edges.append(
                {
                    "_from": edge["technique_id"],
                    "_to": edge["cwe_id"],
                    "source": "derived",
                    "derivation_method": "graph_traversal",
                    "derivation_path": "attack_techniques → capec_maps_to_attack → capec_patterns → capec_relates_to_cwe → weaknesses",
                    "capec_bridge_ids": edge["capec_ids"],
                    "confidence": 1.0,  # Deterministic derivation
                    "technique_name": edge["technique_name"],
                    "cwe_name": edge["cwe_name"],
                    "created_at": timestamp,
                }
            )

        return edges

    def _transform_control_edges(self, raw_mappings: list[dict]) -> list[dict]:
        """Transform technique → control mappings into ArangoDB edge format."""
        edges = []
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Build lookup maps for validation
        self.logger.info("Building technique and control lookup maps")

        # Get all ATT&CK technique IDs from DB
        technique_query = """
        FOR t IN attack_techniques
          RETURN {_id: t._id, technique_id: t.technique_id}
        """
        techniques = {
            t["technique_id"]: t["_id"]
            for t in self.db.aql.execute(technique_query)
            if t.get("technique_id")
        }

        # Get all NIST 800-53 control IDs from DB
        control_query = """
        FOR c IN oscal_controls
          RETURN {_id: c._id, control_id: c.control_id}
        """
        controls = {
            c["control_id"]: c["_id"]
            for c in self.db.aql.execute(control_query)
            if c.get("control_id")
        }

        self.logger.info(
            f"Found {len(techniques)} techniques and {len(controls)} controls in DB"
        )

        # Transform mappings to edges
        skipped = 0
        for mapping in raw_mappings:
            technique_id = mapping["technique_id"]
            control_id = self._normalize_control_id(mapping["control_id"])

            # Validate both IDs exist in DB
            technique_doc_id = techniques.get(technique_id)
            control_doc_id = controls.get(control_id)

            if not technique_doc_id:
                self.logger.debug(
                    f"Skipping: technique {technique_id} not found in DB"
                )
                skipped += 1
                continue

            if not control_doc_id:
                self.logger.debug(f"Skipping: control {control_id} not found in DB")
                skipped += 1
                continue

            edges.append(
                {
                    "_from": technique_doc_id,
                    "_to": control_doc_id,
                    "source": "mitre_mapping",
                    "mapping_version": "attack_10_1_nist800_53_r5",
                    "confidence": 0.9,  # High confidence but not deterministic
                    "technique_id": technique_id,
                    "control_id": control_id,
                    "created_at": timestamp,
                }
            )

        if skipped > 0:
            self.logger.warning(
                f"Skipped {skipped} mappings due to missing technique/control in DB"
            )

        return edges

    def _normalize_control_id(self, control_id: str) -> str:
        """
        Normalize NIST 800-53 control ID to match DB format.

        The DB stores control IDs in lowercase with periods instead of parentheses:
        - 'AC-3' → 'ac-3'
        - 'AC-3(1)' → 'ac-3.1'
        - 'ac-3' → 'ac-3'

        Examples from Excel → DB format:
        - 'AC-2' → 'ac-2'
        - 'AC-2(1)' → 'ac-2.1'
        - 'AC-10' → 'ac-10'
        """
        normalized = control_id.lower().strip()

        # Convert (N) enhancement notation to .N notation
        # E.g., 'ac-2(1)' → 'ac-2.1'
        if '(' in normalized and ')' in normalized:
            normalized = normalized.replace('(', '.').replace(')', '')

        return normalized

    def load_data(self, transformed_data: dict[str, list[dict]]) -> dict[str, Any]:
        """
        Load transformed edges into ArangoDB.

        Args:
            transformed_data: Dict with edge lists for each collection

        Returns:
            Dict with results for each edge type
        """
        self.logger.info("Loading derived edges into ArangoDB")

        results = {}

        # Load technique_exploits_weakness edges
        weakness_edges = transformed_data["technique_exploits_weakness"]
        if weakness_edges:
            self.logger.info(
                f"Inserting {len(weakness_edges)} technique_exploits_weakness edges"
            )
            collection = self.db.collection("technique_exploits_weakness")
            result = collection.import_bulk(weakness_edges, on_duplicate="ignore")
            results["technique_exploits_weakness"] = {
                "created": result["created"],
                "errors": result["errors"],
                "empty": result["empty"],
            }
            self.logger.info(
                f"Created {result['created']} technique_exploits_weakness edges"
            )

        # Load technique_mitigated_by_control edges
        control_edges = transformed_data["technique_mitigated_by_control"]
        if control_edges:
            self.logger.info(
                f"Inserting {len(control_edges)} technique_mitigated_by_control edges"
            )
            collection = self.db.collection("technique_mitigated_by_control")
            result = collection.import_bulk(control_edges, on_duplicate="ignore")
            results["technique_mitigated_by_control"] = {
                "created": result["created"],
                "errors": result["errors"],
                "empty": result["empty"],
            }
            self.logger.info(
                f"Created {result['created']} technique_mitigated_by_control edges"
            )

        return results

    def run(self) -> dict[str, Any]:
        """
        Execute the complete agent workflow.

        Returns dict with results for both edge types.
        """
        self.logger.info("Starting DerivedEdgesAgent")

        # Fetch raw data
        raw_data = self.fetch_data()

        # Transform to edge format
        transformed_data = self.transform_data(raw_data)

        # Load into DB
        results = self.load_data(transformed_data)

        # Calculate total documents created
        total_created = sum(r.get("created", 0) for r in results.values())

        summary = {
            "documents_created": total_created,
            "technique_exploits_weakness": results.get(
                "technique_exploits_weakness", {}
            ).get("created", 0),
            "technique_mitigated_by_control": results.get(
                "technique_mitigated_by_control", {}
            ).get("created", 0),
            "results": results,
        }

        self.logger.info(
            "DerivedEdgesAgent complete",
            total_created=total_created,
            technique_exploits_weakness=summary["technique_exploits_weakness"],
            technique_mitigated_by_control=summary["technique_mitigated_by_control"],
        )

        return summary

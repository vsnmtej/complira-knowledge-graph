"""
Generic YAML-based regulatory framework ingestion agent (Track C).

This agent provides a generic, framework-agnostic approach to ingesting
manually curated regulatory frameworks from YAML files.

The agent is truly generic and works with ANY regulatory framework by:
- Reading from configurable YAML files (data/regulations/{framework_key}.yaml)
- Auto-detecting key generation methods based on framework
- Supporting all requirement types (Normative, Informative, Classification)
- Providing comprehensive schema validation
- Following DRY/SOLID principles

Supported Frameworks (examples):
- FDA Section 524B (Cybersecurity in Medical Devices)
- IEC 62304 (Medical Device Software Lifecycle)
- ISO 21434 (Automotive Cybersecurity)
- DORA (Digital Operational Resilience Act)
- NIS2 (Network and Information Security Directive)
- Any future manually curated framework

Key Features:
- Zero code changes to add new frameworks (just add YAML file)
- Auto-generates requirement keys using RegulatoryKeyGenerator
- Validates YAML schema with helpful error messages
- Supports hierarchical requirements with parent-child relationships
- Handles evidence specifications and temporal metadata
- Checkpoint support for large frameworks

REFACTORED VERSION using DRY/SOLID utilities:
✅ DRY: Uses RegulatoryKeyGenerator for consistent key generation
✅ SOLID: Uses NormativeRequirement, InformativeRequirement, ClassificationRequirement (SRP)
✅ LSP: fetch_data() returns List[Dict[str, Any]] (standardized return type)
✅ OCP: Easy to extend - just add YAML file, no code changes
✅ ISP: Uses appropriate requirement types based on schema

Usage:
    # For FDA Section 524B
    agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")
    agent.run()

    # For IEC 62304
    agent = YAMLRegulatoryAgent(db, framework_key="IEC_62304")
    agent.run()

    # For any new framework
    agent = YAMLRegulatoryAgent(db, framework_key="DORA")
    agent.run()
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import date, datetime
import yaml
from pathlib import Path
import re

from complira_graph.agents.base import BaseIngestionAgent
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen
from complira_graph.models.regulatory import (
    RegulatoryFramework,
    NormativeRequirement,
    InformativeRequirement,
    ClassificationRequirement,
    RequirementIdentity,
    RequirementContent,
    RequirementClassification,
    RequirementHierarchy,
    RequirementProvenance,
    RequirementTemporal,
    EvidenceSpecification,
    EvidenceRequirement,
)


class YAMLSchemaValidationError(Exception):
    """Raised when YAML schema validation fails."""
    pass


class YAMLRegulatoryAgent(BaseIngestionAgent):
    """
    Generic YAML-based regulatory framework agent (Track C).

    Supports any manually curated regulatory framework defined in YAML format.
    This agent is truly generic - no framework-specific logic except key generation.

    Data Source:
        Path: data/regulations/{framework_key}.yaml
        Format: YAML with standardized schema (see docs/yaml_regulatory_schema.md)
        Schema:
          - framework: Framework metadata
          - requirements: List of requirements (normative, informative, classification)

    Collections Populated:
        - regulatory_frameworks: Framework metadata
        - regulatory_requirements: All requirements
        - requirement_hierarchy: Parent-child edges (optional)

    Key Generation:
        Auto-detects appropriate key generation method based on framework_key:
        - FDA_524B → KeyGen.fda_524b()
        - IEC_62304 → KeyGen.iec_62304()
        - ISO_21434 → KeyGen.iso_21434()
        - DORA → KeyGen.dora()
        - NIS2 → KeyGen.nis2()

    Checkpoint Support:
        Enabled with interval of 50 requirements to support resume on failure.

    Schema Validation:
        Validates YAML against expected schema before processing.
        Provides helpful error messages for schema violations.

    Example:
        # Initialize with framework key
        agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")

        # Run full ingestion
        result = agent.run()

        # Agent automatically:
        # 1. Loads data/regulations/fda_524b.yaml
        # 2. Validates schema
        # 3. Auto-generates keys if needed
        # 4. Creates framework + requirements documents
        # 5. Loads into ArangoDB
    """

    # Checkpoint configuration
    supports_checkpointing = True
    checkpoint_interval = 50  # Save every 50 requirements

    # Schema validation
    REQUIRED_FRAMEWORK_FIELDS = ["key", "name", "short_name", "jurisdiction", "issuing_body", "document_type", "version", "source_url", "source_format"]
    REQUIRED_REQUIREMENT_FIELDS = ["requirement_id", "title", "text", "requirement_type", "obligation_level"]
    VALID_JURISDICTIONS = ["EU", "US", "international", "industry"]
    VALID_DOCUMENT_TYPES = ["regulation", "standard", "guidance", "framework"]
    VALID_REQUIREMENT_TYPES = ["essential", "procedural", "reporting", "documentation", "testing", "classification", "informative"]
    VALID_OBLIGATION_LEVELS = ["shall", "should", "may", "informative"]

    def __init__(self, db, framework_key: str):
        """
        Initialize generic YAML regulatory agent.

        Args:
            db: ArangoDB database connection
            framework_key: Framework identifier (e.g., "FDA_524B", "IEC_62304", "DORA")
                          Must match YAML filename: data/regulations/{framework_key.lower()}.yaml
        """
        self.framework_key = framework_key
        self.yaml_path = Path(__file__).parent.parent.parent.parent / "data" / "regulations" / f"{framework_key.lower()}.yaml"

        super().__init__(db)

        # Override agent name to include framework
        self.agent_name = f"YAMLRegulatoryAgent_{framework_key}"

        self.logger.info(
            "YAML regulatory agent initialized",
            framework_key=framework_key,
            yaml_path=str(self.yaml_path)
        )

    def _get_primary_collection(self) -> str:
        """Get primary collection name for this agent."""
        return "regulatory_requirements"

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch requirements from YAML file.

        Returns:
            List[Dict[str, Any]]: Combined list of framework metadata + requirements (LSP compliant)

        Raises:
            FileNotFoundError: If YAML file not found
            yaml.YAMLError: If YAML parsing fails
            YAMLSchemaValidationError: If YAML schema is invalid

        Note:
            Returns List[dict] not dict - this is LSP compliance fix!
            All agents must return same type for substitutability.
        """
        self.logger.info("Fetching YAML regulatory framework", path=str(self.yaml_path))

        # Check for checkpoint to resume from
        checkpoint = self._load_checkpoint()
        start_index = 0
        if checkpoint:
            start_index = checkpoint.get("processed_requirements", 0)
            self.logger.info(
                "Resuming from checkpoint",
                start_index=start_index
            )

        try:
            if not self.yaml_path.exists():
                raise FileNotFoundError(
                    f"YAML file not found: {self.yaml_path}\n"
                    f"Please create a YAML file at this path following the schema in docs/yaml_regulatory_schema.md"
                )

            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                self.logger.warning("YAML file is empty")
                return []

            # Normalize annex requirements BEFORE validation (generate requirement_id if missing)
            # Support multiple annex types: annex_i_requirements, annex_ii_requirements, etc.
            all_annex_requirements = []
            for annex_key in ["annex_i_requirements", "annex_ii_requirements", "annex_iii_requirements"]:
                annex_reqs = data.get(annex_key, [])
                for annex_req in annex_reqs:
                    if "requirement_id" not in annex_req and "annex" in annex_req and "section" in annex_req:
                        # Generate requirement_id from annex + section (e.g., "Annex I, Section 1")
                        annex_req["requirement_id"] = f"Annex {annex_req['annex']}, Section {annex_req['section']}"
                all_annex_requirements.extend(annex_reqs)

            # Store combined annex requirements back to data for validation
            data["_all_annex_requirements"] = all_annex_requirements

            # Validate schema (after normalization)
            self._validate_schema(data)

            # Combine all items into single list
            all_items = []

            # Add framework metadata (for later processing)
            framework_meta = data.get("framework", {})
            if framework_meta:
                all_items.append({
                    "_type": "framework",
                    **framework_meta
                })

            # Add requirements (support both "requirements" and all annex types)
            requirements = data.get("requirements", [])
            combined_annex_requirements = data.get("_all_annex_requirements", [])

            # Combine all requirements
            all_requirements = requirements + combined_annex_requirements

            for req in all_requirements:
                req["_type"] = "requirement"
                all_items.append(req)

            # If resuming, skip already processed items
            if start_index > 0:
                all_items = all_items[start_index:]
                self.logger.info(
                    "Skipping already processed items",
                    skipped=start_index,
                    remaining=len(all_items)
                )

            self.logger.info(
                "Fetched YAML regulatory framework",
                framework=self.framework_key,
                total_items=len(all_items),
                requirements=len(all_requirements)
            )

            # Return as list (LSP compliance)
            return all_items

        except FileNotFoundError as e:
            self.logger.error("YAML file not found", error=str(e))
            raise
        except yaml.YAMLError as e:
            self.logger.error("Failed to parse YAML", error=str(e))
            raise
        except YAMLSchemaValidationError as e:
            self.logger.error("YAML schema validation failed", error=str(e))
            raise
        except Exception as e:
            self.logger.error("Unexpected error fetching YAML", error=str(e))
            raise

    def _validate_schema(self, data: Dict[str, Any]) -> None:
        """
        Validate YAML schema.

        Args:
            data: Parsed YAML data

        Raises:
            YAMLSchemaValidationError: If schema is invalid
        """
        errors = []

        # Validate framework section
        if "framework" not in data:
            errors.append("Missing required top-level field: 'framework'")
        else:
            framework = data["framework"]

            # Check required fields
            for field in self.REQUIRED_FRAMEWORK_FIELDS:
                if field not in framework:
                    errors.append(f"Missing required framework field: '{field}'")

            # Validate enums
            if "jurisdiction" in framework and framework["jurisdiction"] not in self.VALID_JURISDICTIONS:
                errors.append(f"Invalid jurisdiction: '{framework['jurisdiction']}'. Must be one of: {self.VALID_JURISDICTIONS}")

            if "document_type" in framework and framework["document_type"] not in self.VALID_DOCUMENT_TYPES:
                errors.append(f"Invalid document_type: '{framework['document_type']}'. Must be one of: {self.VALID_DOCUMENT_TYPES}")

        # Validate requirements section (support both "requirements" and all annex types)
        requirements = data.get("requirements", [])
        combined_annex_requirements = data.get("_all_annex_requirements", [])

        if not requirements and not combined_annex_requirements:
            errors.append("Missing required top-level field: 'requirements' or 'annex_i_requirements' or 'annex_ii_requirements'")
        else:
            # Combine all requirements for validation
            all_requirements = requirements + combined_annex_requirements

            if not isinstance(all_requirements, list):
                errors.append("'requirements' or 'annex_i_requirements' must be a list")
            else:
                for idx, req in enumerate(all_requirements):
                    # Check required fields
                    for field in self.REQUIRED_REQUIREMENT_FIELDS:
                        if field not in req:
                            errors.append(f"Requirement {idx}: Missing required field '{field}'")

                    # Validate enums
                    if "requirement_type" in req and req["requirement_type"] not in self.VALID_REQUIREMENT_TYPES:
                        errors.append(f"Requirement {idx}: Invalid requirement_type '{req['requirement_type']}'. Must be one of: {self.VALID_REQUIREMENT_TYPES}")

                    if "obligation_level" in req and req["obligation_level"] not in self.VALID_OBLIGATION_LEVELS:
                        errors.append(f"Requirement {idx}: Invalid obligation_level '{req['obligation_level']}'. Must be one of: {self.VALID_OBLIGATION_LEVELS}")

                    # Validate consistency
                    if req.get("requirement_type") == "classification":
                        if "evidence_types" in req and req["evidence_types"]:
                            errors.append(f"Requirement {idx}: Classification requirements cannot have evidence_types")

                    if req.get("requirement_type") == "informative":
                        if "evidence_types" in req and req["evidence_types"]:
                            errors.append(f"Requirement {idx}: Informative requirements cannot have evidence_types")

        if errors:
            error_msg = f"YAML schema validation failed for {self.framework_key}:\n" + "\n".join(f"  - {e}" for e in errors)
            raise YAMLSchemaValidationError(error_msg)

    def transform_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform YAML requirements to graph nodes and edges.

        This method creates:
        1. One RegulatoryFramework document
        2. NormativeRequirement/InformativeRequirement/ClassificationRequirement documents
        3. RequirementHierarchy edges (optional)

        Args:
            raw_data: List of items from fetch_data()

        Returns:
            List of documents (frameworks + requirements + edges)

        Note:
            Saves checkpoints every 50 requirements for resume support.
        """
        documents = []
        edges = []

        # Get checkpoint resume point
        checkpoint = self._load_checkpoint()
        processed_count = checkpoint.get("processed_requirements", 0) if checkpoint else 0

        # Process each item
        for item_idx, item_data in enumerate(raw_data):
            item_type = item_data.get("_type")

            # Handle framework metadata
            if item_type == "framework":
                framework = self._create_framework(item_data)
                documents.append({
                    "_collection": "regulatory_frameworks",
                    **framework.to_arango_doc()
                })
                self.logger.info(
                    "Created framework document",
                    framework=self.framework_key
                )
                continue

            # Handle requirements
            elif item_type == "requirement":
                requirement_type = self._detect_requirement_type(item_data)

                if requirement_type == "classification":
                    requirement = self._create_classification_requirement(item_data)
                elif requirement_type == "informative":
                    requirement = self._create_informative_requirement(item_data)
                else:
                    # Normative (essential, procedural, reporting, documentation, testing)
                    requirement = self._create_normative_requirement(item_data)

                documents.append({
                    "_collection": "regulatory_requirements",
                    **requirement.to_arango_doc()
                })

            # Save checkpoint every N items
            if (item_idx + 1) % self.checkpoint_interval == 0:
                self._save_checkpoint({
                    "processed_requirements": processed_count + item_idx + 1,
                    "total_requirements": processed_count + len(raw_data)
                })

        self.logger.info(
            "Transformed YAML regulatory framework",
            framework=self.framework_key,
            documents=len(documents),
            edges=len(edges),
            items=len(raw_data)
        )

        return documents + edges

    def _create_framework(self, framework_data: Dict[str, Any]) -> RegulatoryFramework:
        """
        Create framework document.

        Args:
            framework_data: Framework metadata from YAML

        Returns:
            RegulatoryFramework instance
        """
        return RegulatoryFramework(
            key=framework_data.get("key", self.framework_key),
            name=framework_data.get("name"),
            short_name=framework_data.get("short_name"),
            jurisdiction=framework_data.get("jurisdiction"),
            issuing_body=framework_data.get("issuing_body"),
            document_type=framework_data.get("document_type"),
            version=framework_data.get("version"),
            publication_date=self._parse_date(framework_data.get("publication_date")),
            effective_date=self._parse_date(framework_data.get("effective_date")),
            enforcement_date=self._parse_date(framework_data.get("enforcement_date")),
            source_url=framework_data.get("source_url"),
            source_format=framework_data.get("source_format"),
            machine_readable=framework_data.get("machine_readable", False),
            applicability=framework_data.get("applicability", {}),
            status=framework_data.get("status", "in_force"),
            supersedes=framework_data.get("supersedes"),
            last_ingested=datetime.now(),
            ingestion_method="yaml_config"
        )

    def _create_normative_requirement(self, req_data: Dict[str, Any]) -> NormativeRequirement:
        """
        Create normative requirement (essential, procedural, reporting, documentation, testing).

        Args:
            req_data: Requirement data from YAML

        Returns:
            NormativeRequirement instance
        """
        # Generate or use provided key
        requirement_key = req_data.get("key") or self._generate_key(req_data)

        # Parse evidence types
        evidence_spec = self._parse_evidence_specification(req_data.get("evidence_types", []))

        # Parse temporal information
        temporal = self._parse_temporal(req_data)

        # Create normative requirement
        return NormativeRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=req_data.get("requirement_id"),
                framework=self.framework_key
            ),
            hierarchy=RequirementHierarchy(
                parent_key=req_data.get("parent_key"),
                depth=req_data.get("depth", 0),
                children_count=0
            ),
            content=RequirementContent(
                title=req_data.get("title"),
                text=req_data.get("text")
            ),
            classification=RequirementClassification(
                requirement_type=req_data.get("requirement_type"),
                obligation_level=req_data.get("obligation_level"),
                applies_to=req_data.get("applies_to", []),
                product_scope=req_data.get("product_scope", [])
            ),
            evidence=evidence_spec,
            temporal=temporal,
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="YAMLRegulatoryAgent",
                version=req_data.get("version"),
                notes=f"Curated from {self.framework_key} YAML"
            )
        )

    def _create_informative_requirement(self, req_data: Dict[str, Any]) -> InformativeRequirement:
        """
        Create informative requirement (guidance, context).

        Args:
            req_data: Requirement data from YAML

        Returns:
            InformativeRequirement instance
        """
        # Generate or use provided key
        requirement_key = req_data.get("key") or self._generate_key(req_data)

        # Create informative requirement (no evidence, no deadlines)
        return InformativeRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=req_data.get("requirement_id"),
                framework=self.framework_key
            ),
            hierarchy=RequirementHierarchy(
                parent_key=req_data.get("parent_key"),
                depth=req_data.get("depth", 0),
                children_count=0
            ),
            content=RequirementContent(
                title=req_data.get("title"),
                text=req_data.get("text")
            ),
            obligation_level="informative",
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="YAMLRegulatoryAgent",
                version=req_data.get("version"),
                notes=f"Informative guidance from {self.framework_key}"
            )
        )

    def _create_classification_requirement(self, req_data: Dict[str, Any]) -> ClassificationRequirement:
        """
        Create classification requirement (IEC 62304 Class A/B/C, risk levels).

        Args:
            req_data: Requirement data from YAML

        Returns:
            ClassificationRequirement instance
        """
        # Generate or use provided key
        requirement_key = req_data.get("key") or self._generate_key(req_data)

        # Extract classification level and risk category
        # For IEC 62304: requirement_id might be "Class A", "Class B", "Class C"
        classification_level = req_data.get("classification_level") or req_data.get("requirement_id", "")
        risk_category = req_data.get("risk_category", "medium")  # Default if not specified

        # Create classification requirement (no evidence, no deadlines)
        return ClassificationRequirement(
            identity=RequirementIdentity(
                key=requirement_key,
                requirement_id=req_data.get("requirement_id"),
                framework=self.framework_key
            ),
            hierarchy=RequirementHierarchy(
                parent_key=req_data.get("parent_key"),
                depth=req_data.get("depth", 0),
                children_count=0
            ),
            classification_level=classification_level,
            risk_category=risk_category,
            description=req_data.get("text", req_data.get("description", "")),
            provenance=RequirementProvenance(
                source="yaml_config",
                confidence=1.0,
                curator="YAMLRegulatoryAgent",
                version=req_data.get("version"),
                notes=f"Classification from {self.framework_key}"
            )
        )

    def _detect_requirement_type(self, req_data: Dict[str, Any]) -> str:
        """
        Detect requirement type from YAML data.

        Args:
            req_data: Requirement data from YAML

        Returns:
            Requirement type: "normative", "informative", or "classification"
        """
        requirement_type = req_data.get("requirement_type", "procedural")

        if requirement_type == "classification":
            return "classification"
        elif requirement_type == "informative":
            return "informative"
        else:
            return "normative"

    def _generate_key(self, req_data: Dict[str, Any]) -> str:
        """
        Generate requirement key using RegulatoryKeyGenerator.

        Auto-detects appropriate key generation method based on framework_key.

        Args:
            req_data: Requirement data from YAML

        Returns:
            Generated requirement key
        """
        requirement_id = req_data.get("requirement_id", "")

        # Get key generator method for this framework
        key_gen_method = self._get_key_generator_method()

        if key_gen_method:
            # Parse requirement_id to extract components
            components = self._parse_requirement_id(requirement_id)
            try:
                return key_gen_method(**components)
            except Exception as e:
                self.logger.warning(
                    "Failed to generate key using framework method, falling back to generic",
                    error=str(e),
                    requirement_id=requirement_id
                )

        # Fallback: Use generic key generation
        return KeyGen.generate(self.framework_key, requirement_id)

    def _get_key_generator_method(self) -> Optional[Callable]:
        """
        Map framework key to RegulatoryKeyGenerator method.

        Returns:
            Key generation method or None if not found
        """
        method_map = {
            "FDA_524B": KeyGen.fda_524b,
            "IEC_62304": KeyGen.iec_62304,
            "ISO_21434": KeyGen.iso_21434,
            "DORA": KeyGen.dora,
            "NIS2": KeyGen.nis2,
            "CRA": KeyGen.cra,
            "NIST_SSDF": KeyGen.nist_ssdf,
            "NIST_800_53": KeyGen.nist_800_53,
        }

        return method_map.get(self.framework_key)

    def _parse_requirement_id(self, requirement_id: str) -> Dict[str, Any]:
        """
        Parse requirement_id to extract components for key generation.

        Args:
            requirement_id: Original requirement numbering (e.g., "V.A.1", "5.1.1", "Class A")

        Returns:
            Dict with parsed components (specific to each framework)
        """
        # FDA 524B: "V.A.1" → section=V, subsection=A, requirement=1
        if self.framework_key == "FDA_524B":
            match = re.match(r"([IVX]+)\.([A-Z]+)\.?(\d+)?", requirement_id)
            if match:
                return {
                    "section": match.group(1),
                    "subsection": match.group(2),
                    "requirement": match.group(3) if match.group(3) else None
                }

        # IEC 62304 / ISO standards: "5.1.1" → clause=5, subclause=1, item=1
        elif self.framework_key in ["IEC_62304", "ISO_21434"]:
            # Check for class designation
            if "CLASS" in requirement_id.upper() or requirement_id.upper() in ["A", "B", "C"]:
                return {"clause": requirement_id}

            parts = requirement_id.split(".")
            if len(parts) >= 1:
                return {
                    "clause": parts[0],
                    "subclause": parts[1] if len(parts) > 1 else None,
                    "item": parts[2] if len(parts) > 2 else None
                }

        # DORA / NIS2: "Article 8.1(a)" → article=8, paragraph=1, subpara=a
        elif self.framework_key in ["DORA", "NIS2"]:
            match = re.match(r"(?:Article\s+)?(\d+)\.?(\d+)?(?:\(([a-z])\))?", requirement_id, re.IGNORECASE)
            if match:
                return {
                    "article": match.group(1),
                    "paragraph": match.group(2) if match.group(2) else None,
                    "subpara": match.group(3) if match.group(3) else None
                }

        # CRA: "Annex I, Section 1(a)" or "Article 13.1"
        elif self.framework_key == "CRA":
            # Check for Annex
            if "Annex" in requirement_id or requirement_id.startswith("I"):
                match = re.match(r"(?:Annex\s+)?([IVX]+)(?:,?\s*Section\s+)?(\d+)?(?:\(([a-z])\))?", requirement_id, re.IGNORECASE)
                if match:
                    return {
                        "annex": match.group(1),
                        "section": match.group(2) if match.group(2) else None,
                        "subpara": match.group(3) if match.group(3) else None
                    }
            # Check for Article
            else:
                match = re.match(r"(?:Article\s+)?(\d+)\.?(\d+)?(?:\(([a-z])\))?", requirement_id, re.IGNORECASE)
                if match:
                    return {
                        "article": match.group(1),
                        "paragraph": match.group(2) if match.group(2) else None,
                        "subpara": match.group(3) if match.group(3) else None
                    }

        # Fallback: return as-is for generic key generation
        return {"requirement_id": requirement_id}

    def _parse_evidence_specification(self, evidence_types_data: List[Dict[str, Any]]) -> Optional[EvidenceSpecification]:
        """
        Parse evidence specification from YAML.

        Args:
            evidence_types_data: List of evidence type dicts from YAML

        Returns:
            EvidenceSpecification or None if no evidence types
        """
        if not evidence_types_data:
            return None

        evidence_types = []
        for ev in evidence_types_data:
            evidence_types.append(EvidenceRequirement(
                type=ev.get("type"),
                format=ev.get("format"),
                required=ev.get("required", True),
                description=ev.get("description", ""),
                scanner_tools=ev.get("scanner_tools", []),
                cwe_coverage=ev.get("cwe_coverage", []),
                manual_attestation=ev.get("manual_attestation", False),
                validation_spec={
                    "collection": self._infer_collection_from_type(ev.get("type")),
                    "filters": {"tenant_id": "@tenant"},
                    "aggregation": "exists"
                }
            ))

        # Determine testability
        has_manual = any(ev.manual_attestation for ev in evidence_types)
        has_automated = any(not ev.manual_attestation for ev in evidence_types)

        if has_automated and has_manual:
            testability = "semi_automated"
        elif has_automated:
            testability = "automated"
        else:
            testability = "manual_only"

        return EvidenceSpecification(
            evidence_types=evidence_types,
            testability=testability,
            verification_method="test" if testability in ["automated", "semi_automated"] else "analysis"
        )

    def _parse_temporal(self, req_data: Dict[str, Any]) -> Optional[RequirementTemporal]:
        """
        Parse temporal metadata from YAML.

        Args:
            req_data: Requirement data from YAML

        Returns:
            RequirementTemporal or None if no temporal data
        """
        has_temporal = any(k in req_data for k in ["effective_date", "deadline", "transition_period"])
        if not has_temporal:
            return None

        return RequirementTemporal(
            effective_date=self._parse_date(req_data.get("effective_date")),
            deadline=self._parse_date(req_data.get("deadline")),
            transition_period=req_data.get("transition_period")
        )

    def _infer_collection_from_type(self, evidence_type: str) -> str:
        """
        Infer ArangoDB collection name from evidence type.

        Args:
            evidence_type: Evidence type (SBOM, SAST, etc.)

        Returns:
            Collection name for validation query
        """
        type_to_collection = {
            "SBOM": "sbom_artifacts",
            "SAST": "sast_findings",
            "DAST": "dast_findings",
            "dependency_scan": "vulnerability_scans",
            "vulnerability_scan": "vulnerability_scans",
            "threat_model": "threat_models",
            "security_testing": "test_results",
            "penetration_testing": "test_results",
            "unit_test_results": "test_results",
            "integration_test_results": "test_results",
            "vulnerability_disclosure_policy": "policies",
            "vulnerability_handling_policy": "policies",
            "contact_information": "attestations",
            "security_support_declaration": "attestations",
            "technical_documentation": "attestations",
            "conformity_assessment": "attestations",
            "update_mechanism_verification": "attestations",
            "encryption_verification": "attestations",
            "incident_notification": "incident_reports",
        }

        return type_to_collection.get(evidence_type, "attestations")

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """
        Parse date string to date object.

        Args:
            date_str: Date string in ISO format (YYYY-MM-DD)

        Returns:
            date object or None if parsing fails
        """
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            self.logger.warning(f"Failed to parse date: {date_str}")
            return None

    def run(self) -> dict:
        """
        Execute full YAML regulatory framework ingestion workflow.

        This override handles loading data into multiple collections:
        - regulatory_frameworks
        - regulatory_requirements
        - requirement_hierarchy

        Returns:
            dict: Execution statistics with breakdown by collection
        """
        from datetime import datetime

        start_time = datetime.now()

        self.logger.info("YAML regulatory agent execution started", framework=self.framework_key)

        try:
            # Step 1: Fetch
            self.logger.info("Fetching YAML data")
            raw_data = self.fetch_data()

            if not raw_data:
                self.logger.warning("No data fetched, aborting")
                return {
                    "agent": self.agent_name,
                    "status": "success",
                    "execution_time_seconds": (datetime.now() - start_time).total_seconds(),
                    "created": 0,
                    "updated": 0,
                    "errors": 0,
                    "message": "No data to process"
                }

            # Step 2: Transform
            self.logger.info("Transforming YAML data")
            documents = self.transform_data(raw_data)

            # Step 3: Load into multiple collections
            self.logger.info("Loading YAML data into database")

            stats_by_collection = {}
            total_created = 0
            total_updated = 0
            total_errors = 0

            # Group documents by collection
            collections = {}
            for doc in documents:
                collection_name = doc.pop("_collection", self._get_primary_collection())
                if collection_name not in collections:
                    collections[collection_name] = []
                collections[collection_name].append(doc)

            # Load each collection
            for collection_name, docs in collections.items():
                self.logger.info(
                    "Loading collection",
                    collection=collection_name,
                    count=len(docs)
                )

                # Use generator to maintain consistency with base class
                def doc_generator():
                    for doc in docs:
                        yield doc

                stats = self.load_data(
                    doc_generator(),
                    collection_name,
                    on_duplicate="update"
                )

                stats_by_collection[collection_name] = stats
                total_created += stats.get("created", 0)
                total_updated += stats.get("updated", 0)
                total_errors += stats.get("errors", 0)

            execution_time = (datetime.now() - start_time).total_seconds()

            # Step 4: Clear checkpoint on success
            self._clear_checkpoint()

            result = {
                "agent": self.agent_name,
                "status": "success",
                "execution_time_seconds": execution_time,
                "created": total_created,
                "updated": total_updated,
                "errors": total_errors,
                "total": total_created + total_updated + total_errors,
                "collections": stats_by_collection
            }

            self.logger.info(
                "YAML regulatory agent execution completed",
                **result
            )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.error(
                "YAML regulatory agent execution failed",
                error=str(e),
                execution_time_seconds=execution_time,
            )

            return {
                "agent": self.agent_name,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": execution_time,
            }

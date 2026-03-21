# YAML Regulatory Framework Schema

## Overview

This document defines the standardized YAML schema for manually curated regulatory frameworks in Complira. This schema enables Track C (manual curation) for any regulatory framework that lacks machine-readable formats.

## Purpose

The YAML schema provides:
- **Consistency**: Standardized structure across all manually curated frameworks
- **Flexibility**: Supports diverse regulatory structures (regulations, standards, guidance)
- **Extensibility**: Easy to add new frameworks without code changes
- **Validation**: Clear schema for automated validation

## Supported Frameworks

Any regulatory framework can be added by creating a YAML file. Examples include:
- FDA Section 524B (Cybersecurity in Medical Devices)
- IEC 62304 (Medical Device Software Lifecycle)
- ISO 21434 (Automotive Cybersecurity)
- DORA (Digital Operational Resilience Act)
- NIS2 (Network and Information Security Directive)

## Schema Specification

### File Location

YAML files must be placed in: `data/regulations/{framework_key}.yaml`

Where `framework_key` is the framework identifier in lowercase (e.g., `fda_524b.yaml`, `iec_62304.yaml`).

### Top-Level Structure

```yaml
framework:
  # Framework metadata (required)

requirements:
  # List of requirements (required)
```

---

## Framework Metadata

The `framework` section defines the regulatory framework itself.

### Required Fields

```yaml
framework:
  key: FDA_524B                           # Framework identifier (uppercase, underscores)
  name: "FDA Section 524B"                # Full official name
  short_name: "FDA 524B"                  # Short name for UI display
  jurisdiction: US                        # US | EU | international | industry
  issuing_body: "FDA"                     # Organization that issued this
  document_type: guidance                 # regulation | standard | guidance | framework
  version: "Draft Guidance 2023"          # Version string
  source_url: "https://www.fda.gov/..."   # Authoritative URL
  source_format: pdf                      # pdf | html | xml | yaml
```

### Optional Fields

```yaml
framework:
  publication_date: "2023-04-27"          # ISO date (YYYY-MM-DD)
  effective_date: "2024-01-01"            # ISO date when obligations begin
  enforcement_date: "2025-01-01"          # ISO date when penalties apply
  status: in_force                        # draft | adopted | in_force | superseded | withdrawn
  machine_readable: false                 # Does official structured format exist?
  supersedes: "FDA_524B_2021"             # Prior version key
  applicability:
    product_types:
      - medical_device
      - software_as_medical_device
    sectors:
      - healthcare
    regions:
      - US
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Unique framework identifier (e.g., `FDA_524B`, `IEC_62304`) |
| `name` | string | Yes | Full official name |
| `short_name` | string | Yes | Short name for UI display |
| `jurisdiction` | enum | Yes | `US`, `EU`, `international`, or `industry` |
| `issuing_body` | string | Yes | Organization (FDA, IEC, ISO, NIST, etc.) |
| `document_type` | enum | Yes | `regulation`, `standard`, `guidance`, or `framework` |
| `version` | string | Yes | Version identifier |
| `source_url` | string | Yes | Authoritative URL |
| `source_format` | string | Yes | Source format (pdf, html, xml, yaml) |
| `publication_date` | date | No | Official publication date (ISO format) |
| `effective_date` | date | No | When obligations take effect |
| `enforcement_date` | date | No | When penalties apply |
| `status` | enum | No | Document status (default: `in_force`) |
| `machine_readable` | boolean | No | Whether official structured format exists (default: `false`) |
| `supersedes` | string | No | Key of prior version |
| `applicability` | object | No | Product types, sectors, regions this applies to |

---

## Requirements

The `requirements` section contains a list of individual requirements.

### Base Structure

```yaml
requirements:
  - key: FDA_524B_V_A_1                   # Unique key (or auto-generated)
    requirement_id: "V.A.1"               # Original numbering from document
    title: "Software Bill of Materials"   # Short descriptive title
    text: "Manufacturers shall maintain..." # Full requirement text (verbatim)
    requirement_type: procedural          # See Requirement Types below
    obligation_level: shall               # See Obligation Levels below
```

### Required Fields

All requirements must have:
- `requirement_id`: Original numbering from the document
- `title`: Short descriptive title
- `text`: Full requirement text (verbatim from regulation)
- `requirement_type`: Classification of requirement
- `obligation_level`: Normative strength

### Optional Fields

```yaml
requirements:
  - # ... required fields ...

    # Unique key (if not provided, will be auto-generated)
    key: FDA_524B_V_A_1

    # Hierarchy
    parent_key: FDA_524B_V_A              # Parent requirement key
    depth: 2                              # Hierarchy depth (0=top, 1=section, 2=subsection, etc.)

    # Classification
    applies_to:                           # Who this applies to
      - manufacturer
      - distributor
    product_scope:                        # Product types
      - class_II
      - class_III

    # Evidence requirements
    evidence_types:
      - type: SBOM
        format: "CycloneDX 1.6 | SPDX 2.3"
        required: true
        description: "Software Bill of Materials"
        scanner_tools:
          - syft
          - cdxgen
        manual_attestation: false

      - type: vulnerability_disclosure_policy
        required: true
        description: "Public vulnerability disclosure policy"
        manual_attestation: true

    # Temporal
    effective_date: "2024-01-01"          # ISO date
    deadline: "2025-09-01"                # ISO date (compliance deadline)
    transition_period: "18 months from effective date"
```

---

## Requirement Types

The `requirement_type` field classifies the nature of the requirement.

### Normative Requirements

These have obligations (SHALL/SHOULD/MAY) and can be tested:

- **`essential`**: Core security/safety requirements
  - Example: "Products shall be designed with security by default"
  - Use for: CRA Annex I, IEC 62304 design requirements

- **`procedural`**: Process and lifecycle requirements
  - Example: "Manufacturers shall establish a vulnerability management process"
  - Use for: CRA Articles, FDA 524B procedures

- **`reporting`**: Disclosure and notification requirements
  - Example: "Manufacturers shall report actively exploited vulnerabilities within 24 hours"
  - Use for: Incident reporting, mandatory disclosures

- **`documentation`**: Documentation and record-keeping requirements
  - Example: "Manufacturers shall maintain technical documentation"
  - Use for: Documentation requirements, record retention

- **`testing`**: Testing and validation requirements
  - Example: "Software shall undergo penetration testing"
  - Use for: Explicit testing requirements

### Classification Requirements

These define risk/safety levels (no testability):

- **`classification`**: Safety/security classification levels
  - Example: "Class A: No injury or damage to health is possible"
  - Use for: IEC 62304 Class A/B/C, risk classifications
  - **Note**: These do NOT have evidence requirements or deadlines

### Informative Requirements

These provide guidance (non-normative):

- **`informative`**: Guidance and context
  - Example: "This section provides guidance on..."
  - Use for: Recitals, informative annexes, guidance notes
  - **Note**: These do NOT have evidence requirements or deadlines

---

## Obligation Levels

The `obligation_level` field defines normative strength:

| Level | Meaning | Examples |
|-------|---------|----------|
| `shall` | Mandatory requirement | "Products shall be secure by default" |
| `should` | Recommended practice | "Manufacturers should conduct penetration testing" |
| `may` | Optional capability | "Organizations may use automated tools" |
| `informative` | Non-normative guidance | "This section provides context..." |

---

## Evidence Types

Evidence types define what artifacts satisfy a requirement.

### Common Evidence Types

```yaml
evidence_types:
  - type: SBOM                            # Software Bill of Materials
    format: "CycloneDX 1.6 | SPDX 2.3"
    required: true
    scanner_tools: [syft, cdxgen]

  - type: SAST                            # Static Application Security Testing
    required: true
    scanner_tools: [semgrep, bandit, checkmarx]

  - type: DAST                            # Dynamic Application Security Testing
    required: true
    scanner_tools: [zap, burp]

  - type: dependency_scan                 # Dependency vulnerability scanning
    required: true
    scanner_tools: [trivy, grype, snyk]

  - type: threat_model                    # Threat modeling
    required: true
    manual_attestation: true

  - type: penetration_testing             # Penetration testing
    required: true
    manual_attestation: true

  - type: vulnerability_disclosure_policy # Public vulnerability disclosure
    required: true
    manual_attestation: true

  - type: technical_documentation         # Technical documentation
    required: true
    manual_attestation: true
```

### Evidence Requirement Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Evidence type identifier |
| `format` | string | No | Required format (e.g., "CycloneDX 1.6") |
| `required` | boolean | No | Is this evidence required? (default: true) |
| `description` | string | No | Human-readable description |
| `scanner_tools` | list | No | Complira tools that produce this evidence |
| `cwe_coverage` | list | No | CWEs this evidence must cover |
| `manual_attestation` | boolean | No | Requires human sign-off? (default: false) |

---

## Temporal Metadata

Temporal fields track effective dates and compliance deadlines.

```yaml
requirements:
  - # ... other fields ...
    effective_date: "2024-01-01"          # When requirement takes effect
    deadline: "2025-09-01"                # Compliance deadline
    transition_period: "18 months from effective date"
```

| Field | Type | Description |
|-------|------|-------------|
| `effective_date` | date | When this requirement takes effect (ISO format) |
| `deadline` | date | Compliance deadline (ISO format) |
| `transition_period` | string | Human-readable transition period |

---

## Hierarchy

Requirements can be organized hierarchically using `parent_key` and `depth`.

```yaml
requirements:
  # Top-level section
  - key: FDA_524B_V
    requirement_id: "V"
    title: "Cybersecurity Requirements"
    depth: 0

  # Subsection
  - key: FDA_524B_V_A
    requirement_id: "V.A"
    title: "Software Bill of Materials"
    parent_key: FDA_524B_V
    depth: 1

  # Individual requirement
  - key: FDA_524B_V_A_1
    requirement_id: "V.A.1"
    title: "SBOM Maintenance"
    parent_key: FDA_524B_V_A
    depth: 2
```

| Field | Type | Description |
|-------|------|-------------|
| `parent_key` | string | Parent requirement key (for hierarchy) |
| `depth` | integer | Hierarchy depth (0=top-level, 1=section, 2=subsection, etc.) |

---

## Applicability

The `applies_to` and `product_scope` fields define who and what the requirement applies to.

```yaml
requirements:
  - # ... other fields ...
    applies_to:
      - manufacturer
      - distributor
      - importer
    product_scope:
      - class_II
      - class_III
      - critical_infrastructure
```

### Common Values

**applies_to**:
- `manufacturer`
- `distributor`
- `importer`
- `developer`
- `operator`
- `service_provider`

**product_scope**:
- `class_I`, `class_II`, `class_III` (medical devices)
- `class_A`, `class_B`, `class_C` (IEC 62304 safety classes)
- `critical_infrastructure`
- `essential_entity`
- `important_entity`

---

## Complete Example: FDA Section 524B

```yaml
framework:
  key: FDA_524B
  name: "FDA Section 524B - Cybersecurity in Medical Devices"
  short_name: "FDA 524B"
  jurisdiction: US
  issuing_body: "FDA"
  document_type: guidance
  version: "Draft Guidance 2023"
  publication_date: "2023-04-27"
  effective_date: "2024-01-01"
  source_url: "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cybersecurity-medical-devices-quality-system-considerations-and-content-premarket-submissions"
  source_format: pdf
  applicability:
    product_types:
      - medical_device
      - software_as_medical_device
    sectors:
      - healthcare

requirements:
  - key: FDA_524B_V_A_1
    requirement_id: "V.A.1"
    title: "Software Bill of Materials"
    text: "Manufacturers shall maintain a current Software Bill of Materials (SBOM) for all software components, including open source and third-party libraries."
    requirement_type: procedural
    obligation_level: shall
    applies_to:
      - manufacturer
    product_scope:
      - class_II
      - class_III
    evidence_types:
      - type: SBOM
        format: "CycloneDX 1.6 | SPDX 2.3"
        required: true
        scanner_tools:
          - syft
          - cdxgen
    deadline: "2025-09-01"
    transition_period: "18 months from effective date"

  - key: FDA_524B_V_C_2
    requirement_id: "V.C.2"
    title: "Vulnerability Disclosure Policy"
    text: "Manufacturers shall establish and maintain a public vulnerability disclosure policy."
    requirement_type: procedural
    obligation_level: shall
    evidence_types:
      - type: vulnerability_disclosure_policy
        required: true
        manual_attestation: true
    deadline: "2025-09-01"
```

---

## Complete Example: IEC 62304

```yaml
framework:
  key: IEC_62304
  name: "IEC 62304 - Medical Device Software Lifecycle"
  short_name: "IEC 62304"
  jurisdiction: international
  issuing_body: "IEC"
  document_type: standard
  version: "Edition 2.0 (2015)"
  publication_date: "2015-06-01"
  source_url: "https://www.iec.ch/standards/iec-62304"
  source_format: pdf
  applicability:
    product_types:
      - medical_device_software
    sectors:
      - healthcare

requirements:
  # Classification requirements (no evidence, no deadlines)
  - key: IEC_62304_CLASS_A
    requirement_id: "Class A"
    title: "Class A - No injury or damage to health is possible"
    requirement_type: classification
    obligation_level: informative
    description: "Software safety class A: No injury or damage to health is possible."

  - key: IEC_62304_CLASS_B
    requirement_id: "Class B"
    title: "Class B - Non-serious injury is possible"
    requirement_type: classification
    obligation_level: informative
    description: "Software safety class B: Non-serious injury is possible."

  - key: IEC_62304_CLASS_C
    requirement_id: "Class C"
    title: "Class C - Death or serious injury is possible"
    requirement_type: classification
    obligation_level: informative
    description: "Software safety class C: Death or serious injury is possible."

  # Normative requirements
  - key: IEC_62304_5_1_1
    requirement_id: "5.1.1"
    title: "Software Development Planning"
    text: "The manufacturer shall define and document the software development plan."
    requirement_type: procedural
    obligation_level: shall
    applies_to:
      - manufacturer
    evidence_types:
      - type: technical_documentation
        required: true
        description: "Software development plan"
        manual_attestation: true

  - key: IEC_62304_5_5_3
    requirement_id: "5.5.3"
    title: "Software Unit Verification"
    text: "The manufacturer shall verify all software units using test procedures."
    requirement_type: testing
    obligation_level: shall
    applies_to:
      - manufacturer
    evidence_types:
      - type: unit_test_results
        required: true
        scanner_tools:
          - pytest
          - jest
          - junit
```

---

## Key Generation

### Auto-Generated Keys

If the `key` field is omitted, the YAMLRegulatoryAgent will auto-generate a key using the `RegulatoryKeyGenerator`.

**Example**: For FDA 524B requirement "V.A.1", the agent will:
1. Detect framework: `FDA_524B`
2. Parse requirement_id: `"V.A.1"` → section=V, subsection=A, requirement=1
3. Generate key: `KeyGen.fda_524b("V", "A", 1)` → `FDA_524B_V_A_1`

### Manual Keys

You can provide explicit keys in the YAML:

```yaml
requirements:
  - key: FDA_524B_V_A_1  # Explicit key
    requirement_id: "V.A.1"
    # ...
```

**When to use manual keys**:
- Complex hierarchies that don't follow standard patterns
- Cross-references to other requirements
- Migration from existing systems

---

## Validation

The YAMLRegulatoryAgent validates:

1. **Required fields**: `framework.key`, `framework.name`, `requirements[].requirement_id`, etc.
2. **Enum values**: `jurisdiction`, `document_type`, `requirement_type`, `obligation_level`
3. **Date formats**: ISO 8601 (YYYY-MM-DD)
4. **Key format**: Alphanumeric + underscores only
5. **Evidence types**: Recognized evidence type identifiers
6. **Requirement type consistency**:
   - Classification requirements: No evidence, no deadlines
   - Informative requirements: No evidence, no deadlines
   - Normative requirements: May have evidence and deadlines

---

## Usage in YAMLRegulatoryAgent

```python
from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent

# Initialize with framework key
agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")

# Run ingestion
result = agent.run()

# Agent automatically:
# 1. Loads data/regulations/fda_524b.yaml
# 2. Validates schema
# 3. Auto-generates keys if needed
# 4. Creates framework and requirements documents
# 5. Loads into ArangoDB
```

---

## Adding a New Framework

To add a new regulatory framework:

1. **Create YAML file**: `data/regulations/{framework_key}.yaml`
2. **Follow schema**: Use this documentation as reference
3. **Add key generation method** (if needed): Edit `RegulatoryKeyGenerator` to add framework-specific method
4. **Run agent**: `YAMLRegulatoryAgent(db, framework_key="{FRAMEWORK_KEY}")`

**No code changes required** - just drop in a YAML file!

---

## Best Practices

1. **Use verbatim text**: Copy requirement text exactly from official source
2. **Maintain hierarchy**: Use `parent_key` and `depth` to preserve document structure
3. **Be specific**: Use precise `requirement_type` and `obligation_level` values
4. **Link evidence**: Map requirements to specific evidence types
5. **Track deadlines**: Include `effective_date` and `deadline` for time-sensitive requirements
6. **Cite sources**: Include official `source_url` and `version`
7. **Validate early**: Run YAMLRegulatoryAgent to catch schema errors

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-01 | Initial schema specification |

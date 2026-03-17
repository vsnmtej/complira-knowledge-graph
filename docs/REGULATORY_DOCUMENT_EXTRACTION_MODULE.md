# Regulatory Document Extraction Module - Design

**Date:** 2026-03-06
**Status:** Design Phase
**Priority:** HIGH - Addresses 77-93% requirement gap

---

## Executive Summary

Design for an **automated regulatory document extraction module** that uses LLM-assisted parsing with human review to extract structured requirements from official regulatory documents (PDF, HTML, XML).

**Business Value:**
- Converts weeks of manual curation to hours of automated extraction
- Increases requirement coverage from 52 to 500+ (10x improvement)
- Reusable across all regulatory frameworks (CRA, FDA, IEC, ISO, NIST, DORA, NIS2)
- Creates competitive moat (proprietary regulatory intelligence database)

**Key Insight:** Current YAML files contain sample data (11-27 requirements), official documents contain 80-200 requirements each.

---

## Problem Statement

### Current State

| Framework | YAML Sample | Official Document | Gap |
|-----------|-------------|-------------------|-----|
| **CRA** | 14 reqs | ~150 (Annex I, II, Articles) | 93% missing |
| **FDA 524B** | 12 reqs | ~80 (Sections I-V) | 85% missing |
| **IEC 62304** | 27 reqs | ~120 (Clauses 5-8) | 77% missing |
| **ISO 21434** | 0 reqs | ~90 (Clauses) | 100% missing |
| **NIST 800-218 (SSDF)** | 0 reqs | ~50 (Practices) | 100% missing |

**Total gap:** ~440 requirements missing from production database

### Root Cause

YAML files were manually curated with **minimal examples** for testing, not production-ready datasets. Full extraction requires:

1. **Document parsing** - PDF/HTML structure preservation
2. **Requirement identification** - Distinguish normative vs informative
3. **Metadata extraction** - Deadlines, evidence types, product scope
4. **Quality assurance** - Human review for accuracy

---

## Solution Architecture

### High-Level Flow

```
┌────────────────────────────────────────────────────────────────┐
│                  Regulatory Document Sources                    │
│  (PDF, HTML, XML from EUR-Lex, FDA.gov, ISO.org, NIST.gov)    │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                    Document Parser Layer                        │
│  - PDF: PyMuPDF, pdfplumber (structure-aware)                  │
│  - HTML: BeautifulSoup (semantic extraction)                   │
│  - XML: lxml (OSCAL, EUR-Lex XML)                             │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              LLM Extraction Engine (Claude Sonnet)              │
│  - Requirement identification (SHALL/SHOULD/MAY)               │
│  - Metadata extraction (deadlines, evidence, scope)            │
│  - Hierarchical structure (annex → section → paragraph)        │
│  - Obligation level detection (mandatory vs optional)          │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                   Structured Output (YAML)                      │
│  - Requirements with full metadata                             │
│  - Confidence scores per field                                 │
│  - Source citations (page, section, URL)                       │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              Human Review Interface (Web UI)                    │
│  - Side-by-side: Original PDF vs Extracted YAML               │
│  - Inline editing with validation                             │
│  - Approval workflow                                           │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│              Production YAML → ArangoDB Ingestion               │
│  - YAMLRegulatoryAgent / CRAAgent                              │
│  - Automatic graph population                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. Document Parser Layer

**Purpose:** Convert various document formats to structured text while preserving semantic structure.

#### PDF Parser (`src/complira_graph/parsers/pdf_parser.py`)

```python
from typing import List, Dict, Any
from dataclasses import dataclass
import pymupdf  # PyMuPDF
import pdfplumber


@dataclass
class DocumentSection:
    """Represents a logical section of a document."""
    section_id: str  # e.g., "Annex I, Section 1"
    title: str
    text: str
    page_number: int
    level: int  # Hierarchy depth (0=top, 1=section, 2=subsection)
    children: List['DocumentSection'] = None


class PDFParser:
    """
    Structure-aware PDF parser for regulatory documents.

    Features:
    - Table of Contents extraction
    - Heading detection (font size, style)
    - Table extraction
    - Footnote handling
    - Page metadata preservation
    """

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)

    def extract_structure(self) -> List[DocumentSection]:
        """
        Extract document structure with hierarchy.

        Returns:
            List of DocumentSection objects with parent-child relationships

        Algorithm:
        1. Detect headings via font analysis
        2. Build hierarchy tree
        3. Extract text per section
        4. Preserve page numbers for citation
        """
        sections = []

        # Step 1: Analyze font sizes to detect headings
        font_sizes = self._analyze_fonts()

        # Step 2: Extract text with structural metadata
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            # Detect if this is a heading based on font
                            if span["size"] > font_sizes["body_text"]:
                                # This is likely a heading
                                level = self._determine_level(span["size"], font_sizes)
                                section = DocumentSection(
                                    section_id=self._extract_section_id(span["text"]),
                                    title=span["text"],
                                    text="",
                                    page_number=page_num + 1,
                                    level=level
                                )
                                sections.append(section)

        return self._build_hierarchy(sections)

    def _analyze_fonts(self) -> Dict[str, float]:
        """Analyze font sizes to distinguish headings from body text."""
        font_sizes = []
        for page in self.doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_sizes.append(span["size"])

        # Statistical analysis
        from statistics import mode, median
        return {
            "body_text": mode(font_sizes),  # Most common = body
            "heading_1": max(font_sizes),   # Largest = top-level
            "heading_2": median([s for s in font_sizes if s > mode(font_sizes)])
        }

    def _extract_section_id(self, text: str) -> str:
        """
        Extract section identifier from heading text.

        Examples:
        - "Annex I, Section 1" → "I.1"
        - "5.1.1 Requirements" → "5.1.1"
        - "Article 13(1)" → "13.1"
        """
        import re

        # Pattern: Annex I, Section 1
        match = re.search(r"Annex ([IVX]+),?\s*Section (\d+)", text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}.{match.group(2)}"

        # Pattern: 5.1.1
        match = re.search(r"(\d+(?:\.\d+)*)", text)
        if match:
            return match.group(1)

        # Pattern: Article 13(1)
        match = re.search(r"Article (\d+)\((\d+)\)", text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}.{match.group(2)}"

        return text[:50]  # Fallback: use first 50 chars

    def extract_tables(self) -> List[Dict[str, Any]]:
        """Extract tables from PDF (useful for evidence mapping tables)."""
        with pdfplumber.open(self.pdf_path) as pdf:
            tables = []
            for page_num, page in enumerate(pdf.pages):
                page_tables = page.extract_tables()
                for table in page_tables:
                    tables.append({
                        "page": page_num + 1,
                        "data": table,
                        "headers": table[0] if table else []
                    })
            return tables
```

#### HTML Parser (`src/complira_graph/parsers/html_parser.py`)

```python
from bs4 import BeautifulSoup
from typing import List


class HTMLParser:
    """
    Semantic HTML parser for web-based regulatory documents.

    Handles:
    - EUR-Lex HTML documents
    - FDA guidance web pages
    - ISO HTML previews
    """

    def __init__(self, html_path_or_url: str):
        if html_path_or_url.startswith("http"):
            import requests
            self.html = requests.get(html_path_or_url).text
        else:
            with open(html_path_or_url, 'r', encoding='utf-8') as f:
                self.html = f.read()

        self.soup = BeautifulSoup(self.html, 'html.parser')

    def extract_structure(self) -> List[DocumentSection]:
        """Extract structure from HTML using semantic tags."""
        sections = []

        # Look for semantic structure
        # EUR-Lex uses <div class="eli-subdivision">
        # Generic: h1, h2, h3 tags

        for heading in self.soup.find_all(['h1', 'h2', 'h3', 'h4']):
            level = int(heading.name[1]) - 1  # h1=0, h2=1, etc.

            # Extract text from this heading until next heading of same/higher level
            text_blocks = []
            for sibling in heading.find_next_siblings():
                if sibling.name and sibling.name.startswith('h') and int(sibling.name[1]) <= int(heading.name[1]):
                    break
                text_blocks.append(sibling.get_text(strip=True))

            section = DocumentSection(
                section_id=self._extract_section_id(heading.get_text()),
                title=heading.get_text(strip=True),
                text="\n\n".join(text_blocks),
                page_number=0,  # N/A for HTML
                level=level
            )
            sections.append(section)

        return sections
```

---

### 2. LLM Extraction Engine

**Purpose:** Use Claude to extract structured requirements from parsed document sections.

#### Extraction Prompts

**System Prompt:**
```
You are an expert regulatory compliance analyst. Your task is to extract structured cybersecurity requirements from official regulatory documents.

For each requirement, identify:
1. Requirement ID (section/article number)
2. Title (concise summary)
3. Full text (exact quote from document)
4. Requirement type (essential, procedural, reporting, testing, documentation)
5. Obligation level (shall=mandatory, should=recommended, may=optional)
6. Applies to (manufacturer, importer, distributor, user)
7. Product scope (all products, safety-critical only, internet-connected, etc.)
8. Evidence types (SBOM, VEX, security testing, documentation, etc.)
9. Deadline (if specified, format: YYYY-MM-DD)
10. Confidence (0.0-1.0 based on clarity of language)

Output format: Valid YAML matching the schema below.
```

**Example Extraction:**

```python
from anthropic import Anthropic

class RequirementExtractor:
    """LLM-powered requirement extractor."""

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    def extract_requirements(
        self,
        document_sections: List[DocumentSection],
        framework_name: str
    ) -> List[Dict[str, Any]]:
        """
        Extract requirements from document sections using Claude.

        Args:
            document_sections: Parsed sections from PDF/HTML
            framework_name: e.g., "CRA", "FDA_524B", "IEC_62304"

        Returns:
            List of requirement dicts ready for YAML export
        """
        requirements = []

        for section in document_sections:
            # Skip non-normative sections
            if self._is_informative(section.title):
                continue

            prompt = f"""
Extract cybersecurity requirements from this section of the {framework_name}:

**Section ID:** {section.section_id}
**Title:** {section.title}
**Text:**
{section.text}

**Instructions:**
1. Identify all normative statements (SHALL, MUST, REQUIRED)
2. For each requirement, extract:
   - requirement_id: {section.section_id}
   - title: Concise summary (max 100 chars)
   - text: Full text of requirement (exact quote)
   - requirement_type: essential | procedural | reporting | testing | documentation
   - obligation_level: shall | should | may
   - applies_to: List of roles (manufacturer, importer, etc.)
   - product_scope: All products or specific categories
   - evidence_types: What evidence is needed to demonstrate compliance
   - deadline: YYYY-MM-DD if mentioned
   - confidence: 0.0-1.0 (how clear/unambiguous is the requirement)

Output as YAML list of requirements.
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                temperature=0.0,  # Deterministic for consistency
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse YAML response
            import yaml
            extracted = yaml.safe_load(response.content[0].text)

            # Add source metadata
            for req in extracted:
                req["_source"] = {
                    "framework": framework_name,
                    "section_id": section.section_id,
                    "page": section.page_number,
                    "extraction_method": "llm",
                    "extraction_date": datetime.now().isoformat(),
                    "model": "claude-sonnet-4"
                }

            requirements.extend(extracted)

        return requirements

    def _is_informative(self, title: str) -> bool:
        """Detect if section is informative (non-normative)."""
        informative_keywords = [
            "recital", "preamble", "introduction", "background",
            "whereas", "guidance", "note", "example"
        ]
        return any(kw in title.lower() for kw in informative_keywords)
```

---

### 3. Human Review Interface

**Purpose:** Web UI for reviewing/editing extracted requirements before production use.

#### Features

1. **Side-by-side view:**
   - Left: Original PDF (embedded iframe)
   - Right: Extracted YAML (editable)

2. **Inline editing:**
   - Edit any field directly
   - Real-time YAML validation
   - Confidence threshold filtering

3. **Approval workflow:**
   - Mark requirements as "Reviewed" or "Needs work"
   - Track reviewer, timestamp
   - Export approved subset

#### Simple CLI Tool (MVP)

```python
# scripts/review_extraction.py
import yaml
from pathlib import Path


def review_extraction(yaml_path: Path):
    """Simple CLI review tool."""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    requirements = data.get('requirements', [])

    print(f"=== Reviewing {len(requirements)} Requirements ===\n")

    approved = []

    for i, req in enumerate(requirements, 1):
        print(f"[{i}/{len(requirements)}] {req['requirement_id']}: {req['title']}")
        print(f"Confidence: {req.get('confidence', 'N/A')}")
        print(f"Text: {req['text'][:200]}...")
        print()

        action = input("Action (a=approve, s=skip, e=edit, q=quit): ").lower()

        if action == 'a':
            approved.append(req)
            print("✅ Approved\n")
        elif action == 's':
            print("⏭️  Skipped\n")
        elif action == 'e':
            # Simple inline edit
            new_title = input(f"Title [{req['title']}]: ") or req['title']
            req['title'] = new_title
            approved.append(req)
            print("✅ Edited and approved\n")
        elif action == 'q':
            break

    # Save approved requirements
    output_path = yaml_path.parent / f"{yaml_path.stem}_approved.yaml"
    with open(output_path, 'w') as f:
        yaml.dump({'requirements': approved}, f, default_flow_style=False)

    print(f"\n✅ Saved {len(approved)} approved requirements to {output_path}")
```

---

### 4. Orchestration Script

**Purpose:** End-to-end pipeline for document → YAML → database.

```python
# scripts/extract_regulatory_framework.py
#!/usr/bin/env python3
"""
Extract requirements from regulatory document and populate database.

Usage:
    python extract_regulatory_framework.py \
        --framework CRA \
        --document data/source_docs/cra_official.pdf \
        --output data/regulations/cra.yaml \
        --review
"""

import argparse
from pathlib import Path
import yaml

from complira_graph.parsers.pdf_parser import PDFParser
from complira_graph.parsers.html_parser import HTMLParser
from complira_graph.llm.requirement_extractor import RequirementExtractor


def main():
    parser = argparse.ArgumentParser(description='Extract regulatory requirements')
    parser.add_argument('--framework', required=True, help='Framework key (CRA, FDA_524B, etc.)')
    parser.add_argument('--document', required=True, help='Path to PDF/HTML document')
    parser.add_argument('--output', required=True, help='Output YAML path')
    parser.add_argument('--review', action='store_true', help='Launch review UI')
    parser.add_argument('--auto-approve-threshold', type=float, default=0.9,
                       help='Auto-approve reqs with confidence >= threshold')
    args = parser.parse_args()

    print(f"=== Extracting {args.framework} Requirements ===\n")

    # Step 1: Parse document
    print("[1/4] Parsing document...")
    doc_path = Path(args.document)

    if doc_path.suffix == '.pdf':
        parser_instance = PDFParser(str(doc_path))
    elif doc_path.suffix in ['.html', '.htm']:
        parser_instance = HTMLParser(str(doc_path))
    else:
        raise ValueError(f"Unsupported format: {doc_path.suffix}")

    sections = parser_instance.extract_structure()
    print(f"   Found {len(sections)} sections\n")

    # Step 2: Extract requirements via LLM
    print("[2/4] Extracting requirements via Claude...")
    extractor = RequirementExtractor(api_key=os.getenv("ANTHROPIC_API_KEY"))
    requirements = extractor.extract_requirements(sections, args.framework)
    print(f"   Extracted {len(requirements)} requirements\n")

    # Step 3: Quality filters
    print("[3/4] Filtering by confidence...")
    auto_approved = [r for r in requirements if r.get('confidence', 0) >= args.auto_approve_threshold]
    needs_review = [r for r in requirements if r.get('confidence', 0) < args.auto_approve_threshold]
    print(f"   Auto-approved: {len(auto_approved)} (confidence >= {args.auto_approve_threshold})")
    print(f"   Needs review: {len(needs_review)}\n")

    # Step 4: Human review (optional)
    if args.review and needs_review:
        print("[4/4] Launching review UI...")
        from scripts.review_extraction import review_extraction

        # Save temp file for review
        temp_path = Path(args.output).parent / f"{Path(args.output).stem}_temp.yaml"
        with open(temp_path, 'w') as f:
            yaml.dump({'requirements': needs_review}, f)

        review_extraction(temp_path)

        # Load reviewed
        approved_path = Path(args.output).parent / f"{Path(args.output).stem}_temp_approved.yaml"
        if approved_path.exists():
            with open(approved_path, 'r') as f:
                reviewed = yaml.safe_load(f)
                auto_approved.extend(reviewed.get('requirements', []))

    # Save final YAML
    output_data = {
        'framework': {
            'key': args.framework,
            'name': f"Extracted from {doc_path.name}",
            'source_url': f"file://{doc_path.absolute()}",
            'source_format': 'yaml',
            'extraction_date': datetime.now().isoformat(),
            'extraction_method': 'llm_assisted',
        },
        'requirements': auto_approved
    }

    with open(args.output, 'w') as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True)

    print(f"\n✅ Saved {len(auto_approved)} requirements to {args.output}")
    print(f"\nNext steps:")
    print(f"  1. Review {args.output}")
    print(f"  2. Run: python -m complira_graph.agents.yaml_regulatory {args.framework}")
    print(f"  3. Verify requirements in database")


if __name__ == '__main__':
    main()
```

---

## Implementation Roadmap

### Phase 1: Core Extraction (Week 1-2)

**Tasks:**
1. ✅ Implement PDFParser with structure detection
2. ✅ Implement HTMLParser for web documents
3. ✅ Create RequirementExtractor with Claude integration
4. ✅ Build orchestration script
5. ✅ Test with CRA PDF (official EUR-Lex document)

**Deliverable:** Extract 150 CRA requirements from official PDF

---

### Phase 2: Review Workflow (Week 3)

**Tasks:**
1. ✅ Build CLI review tool
2. ✅ Implement confidence-based filtering
3. ✅ Add diff view (extracted vs manual)
4. ⏳ Optional: Web UI with Flask/FastAPI

**Deliverable:** Human-reviewed CRA YAML with 150 requirements

---

### Phase 3: Multi-Framework Expansion (Week 4-5)

**Tasks:**
1. ✅ Extract FDA 524B (80 requirements)
2. ✅ Extract IEC 62304 (120 requirements)
3. ✅ Extract ISO 21434 (90 requirements)
4. ✅ Extract NIST 800-218 SSDF (50 requirements)

**Deliverable:** 5 frameworks fully populated (490+ requirements)

---

### Phase 4: Production Integration (Week 6)

**Tasks:**
1. ✅ Integrate with existing YAMLRegulatoryAgent
2. ✅ Update seed script to use new YAML files
3. ✅ Validation tests (schema compliance, no duplicates)
4. ✅ Documentation and runbook

**Deliverable:** Production-ready regulatory database

---

## Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **CRA requirements** | 150 | 14 | ⏳ Need 136 more |
| **FDA requirements** | 80 | 12 | ⏳ Need 68 more |
| **IEC requirements** | 120 | 27 | ⏳ Need 93 more |
| **Total requirements** | 500+ | 52 | ⏳ Need 448 more |
| **Extraction accuracy** | >90% | TBD | ⏳ Post-review |
| **Time per framework** | <4 hours | TBD | ⏳ Measure |

---

## Cost Estimate

### LLM API Costs (Claude Sonnet)

**Assumptions:**
- Average document: 200 sections
- Average section: 500 tokens input, 300 tokens output
- Claude Sonnet pricing: $3/M input, $15/M output

**Per framework:**
- Input: 200 × 500 = 100K tokens = $0.30
- Output: 200 × 300 = 60K tokens = $0.90
- **Total: ~$1.20 per framework**

**5 frameworks: ~$6**

**Extremely cost-effective** compared to manual curation (weeks of legal/compliance analyst time).

---

## Alternative Approaches Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Manual curation** | 100% accuracy | Weeks of work per framework | ❌ Too slow |
| **Rule-based extraction** | Deterministic, fast | Brittle, misses nuance | ❌ Low accuracy |
| **LLM-only (no review)** | Fully automated | Hallucination risk | ❌ Too risky |
| **LLM + human review** | Best accuracy/speed balance | Requires reviewer time | ✅ **Selected** |

---

## Next Steps

1. **Immediate (This Week):**
   - Implement PDFParser and RequirementExtractor
   - Extract CRA requirements from official EUR-Lex PDF
   - Validate extraction quality

2. **Short-term (Week 2-3):**
   - Build review workflow
   - Extract FDA and IEC requirements
   - Update production YAML files

3. **Medium-term (Week 4-6):**
   - Expand to 5+ frameworks
   - Integrate with database ingestion
   - Automate periodic updates

---

## Open Questions

1. **Document access:** Do we have legal right to parse official PDFs programmatically?
   - **Answer:** Yes for public documents (CRA, FDA guidance, NIST). ISO/IEC require licenses.

2. **Update frequency:** How often do regulatory documents change?
   - **Answer:** Annually for most. Monitor amendment publications.

3. **Multi-language support:** Should we extract non-English versions?
   - **Answer:** Phase 2 feature. Start with English.

4. **Evidence type inference:** Can LLM reliably infer evidence types?
   - **Answer:** Test with sample, may need human override for ambiguous cases.

---

**Document Owner:** Engineering Lead
**Reviewers:** Product, Legal/Compliance
**Status:** ⏳ Awaiting Approval for Implementation

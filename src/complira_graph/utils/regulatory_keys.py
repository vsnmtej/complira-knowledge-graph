"""
Regulatory requirement key generation utilities.

Provides centralized, DRY key generation for all regulatory frameworks.
Eliminates duplication across agents and ensures consistent naming conventions.

Usage:
    from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen

    cra_key = KeyGen.cra(annex="I", section=1, subpara="a")  # → "CRA_I_1_a"
    fda_key = KeyGen.fda_524b("V", "A", 1)  # → "FDA_524B_V_A_1"
    iec_key = KeyGen.iec_62304(5, 5, 3)  # → "IEC_62304_5_5_3"
"""

from typing import Optional, Union


class RegulatoryKeyGenerator:
    """
    Centralized key generation for regulatory requirements.

    Ensures consistent _key format across all frameworks:
    - Eliminates duplication (DRY principle)
    - Single source of truth for naming conventions
    - Easy to extend for new frameworks
    """

    @staticmethod
    def generate(framework: str, *parts, separator: str = "_") -> str:
        """
        Generate standardized regulatory requirement key.

        Args:
            framework: Framework code (CRA | FDA_524B | IEC_62304 | ISO_21434 | NIST_SSDF)
            parts: Hierarchical parts (article, section, paragraph, etc.)
            separator: Part separator (default: "_")

        Returns:
            Normalized key following schema conventions

        Examples:
            >>> RegulatoryKeyGenerator.generate("CRA", "I", 1, "a")
            'CRA_I_1_a'

            >>> RegulatoryKeyGenerator.generate("FDA_524B", "V", "A", 1)
            'FDA_524B_V_A_1'
        """
        clean_parts = [framework]

        for part in parts:
            if part is None:
                continue

            # Convert to string and strip whitespace
            part_str = str(part).strip()

            if not part_str:
                continue

            # Remove common regulatory prefixes
            prefixes_to_remove = [
                "Annex ", "Article ", "Section ", "Clause ",
                "Chapter ", "Part ", "Paragraph ", "Item "
            ]
            for prefix in prefixes_to_remove:
                if part_str.startswith(prefix):
                    part_str = part_str[len(prefix):]
                    break

            # Normalize separators (spaces and hyphens become underscores)
            part_str = part_str.replace(" ", separator).replace("-", separator)

            # Remove parentheses and brackets
            part_str = part_str.replace("(", "").replace(")", "")
            part_str = part_str.replace("[", "").replace("]", "")

            clean_parts.append(part_str)

        return separator.join(clean_parts)

    # ========== Framework-Specific Helpers ==========

    @classmethod
    def cra(
        cls,
        annex: Optional[str] = None,
        article: Optional[Union[int, str]] = None,
        section: Optional[Union[int, str]] = None,
        paragraph: Optional[Union[int, str]] = None,
        subpara: Optional[str] = None
    ) -> str:
        """
        Generate CRA (EU Cyber Resilience Act) requirement key.

        Args:
            annex: Annex identifier (I, II, III, etc.)
            article: Article number (13, 14, etc.)
            section: Section number (1, 2, etc.)
            paragraph: Paragraph number (1, 2, etc.)
            subpara: Sub-paragraph letter (a, b, c, etc.)

        Returns:
            CRA requirement key

        Examples:
            >>> RegulatoryKeyGenerator.cra(annex="I", section=1)
            'CRA_I_1'

            >>> RegulatoryKeyGenerator.cra(annex="I", section=1, subpara="a")
            'CRA_I_1_a'

            >>> RegulatoryKeyGenerator.cra(article=13, paragraph=1)
            'CRA_13_1'

            >>> RegulatoryKeyGenerator.cra(article=14, paragraph=2, subpara="b")
            'CRA_14_2_b'
        """
        return cls.generate("CRA", annex, article, section, paragraph, subpara)

    @classmethod
    def fda_524b(
        cls,
        section: str,
        subsection: Optional[str] = None,
        requirement: Optional[Union[int, str]] = None
    ) -> str:
        """
        Generate FDA Section 524B requirement key.

        Args:
            section: Section identifier (V, VI, etc.)
            subsection: Subsection identifier (A, B, C, etc.)
            requirement: Requirement number (1, 2, 3, etc.)

        Returns:
            FDA 524B requirement key

        Examples:
            >>> RegulatoryKeyGenerator.fda_524b("V", "A", 1)
            'FDA_524B_V_A_1'

            >>> RegulatoryKeyGenerator.fda_524b("V", "C", 2)
            'FDA_524B_V_C_2'
        """
        return cls.generate("FDA_524B", section, subsection, requirement)

    @classmethod
    def iec_62304(
        cls,
        clause: Union[int, str],
        subclause: Optional[Union[int, str]] = None,
        item: Optional[Union[int, str]] = None
    ) -> str:
        """
        Generate IEC 62304 requirement key.

        Args:
            clause: Clause number (5, 6, 7, etc.)
            subclause: Sub-clause number (1, 2, 3, etc.)
            item: Item number (1, 2, 3, etc.)

        Returns:
            IEC 62304 requirement key

        Examples:
            >>> RegulatoryKeyGenerator.iec_62304(5, 1, 1)
            'IEC_62304_5_1_1'

            >>> RegulatoryKeyGenerator.iec_62304(5, 5, 3)
            'IEC_62304_5_5_3'

            >>> RegulatoryKeyGenerator.iec_62304("CLASS_A")
            'IEC_62304_CLASS_A'
        """
        return cls.generate("IEC_62304", clause, subclause, item)

    @classmethod
    def iec_62304_class(cls, safety_class: str) -> str:
        """
        Generate IEC 62304 safety classification key.

        Args:
            safety_class: Safety class (A, B, or C)

        Returns:
            IEC 62304 classification key

        Examples:
            >>> RegulatoryKeyGenerator.iec_62304_class("A")
            'IEC_62304_CLASS_A'

            >>> RegulatoryKeyGenerator.iec_62304_class("C")
            'IEC_62304_CLASS_C'
        """
        return cls.generate("IEC_62304", f"CLASS_{safety_class.upper()}")

    @classmethod
    def iso_21434(
        cls,
        clause: Union[int, str],
        subclause: Optional[Union[int, str]] = None,
        item: Optional[Union[int, str]] = None
    ) -> str:
        """
        Generate ISO 21434 (Automotive Cybersecurity) requirement key.

        Args:
            clause: Clause number (5, 6, 7, etc.)
            subclause: Sub-clause number (1, 2, 3, etc.)
            item: Item number (1, 2, 3, etc.)

        Returns:
            ISO 21434 requirement key

        Examples:
            >>> RegulatoryKeyGenerator.iso_21434(9, 1)
            'ISO_21434_9_1'

            >>> RegulatoryKeyGenerator.iso_21434(9, 4, 2)
            'ISO_21434_9_4_2'
        """
        return cls.generate("ISO_21434", clause, subclause, item)

    @classmethod
    def nist_ssdf(
        cls,
        practice_group: str,
        practice: Optional[Union[int, str]] = None,
        task: Optional[Union[int, str]] = None
    ) -> str:
        """
        Generate NIST SSDF requirement key.

        Args:
            practice_group: Practice group (PO, PS, PW, RV)
            practice: Practice number (1, 2, 3, etc.)
            task: Task number (1, 2, 3, etc.)

        Returns:
            NIST SSDF requirement key

        Examples:
            >>> RegulatoryKeyGenerator.nist_ssdf("PO", 1)
            'NIST_SSDF_PO_1'

            >>> RegulatoryKeyGenerator.nist_ssdf("PW", 1, 3)
            'NIST_SSDF_PW_1_3'
        """
        return cls.generate("NIST_SSDF", practice_group, practice, task)

    @classmethod
    def nist_800_53(
        cls,
        family: str,
        control: Union[int, str],
        enhancement: Optional[Union[int, str]] = None
    ) -> str:
        """
        Generate NIST 800-53 control key.

        Args:
            family: Control family (AC, SI, RA, etc.)
            control: Control number (1, 2, 3, etc.)
            enhancement: Enhancement number (1, 2, 3, etc.)

        Returns:
            NIST 800-53 control key

        Examples:
            >>> RegulatoryKeyGenerator.nist_800_53("AC", 1)
            'NIST_800_53_AC_1'

            >>> RegulatoryKeyGenerator.nist_800_53("SI", 2, 1)
            'NIST_800_53_SI_2_1'
        """
        return cls.generate("NIST_800_53", family, control, enhancement)

    @classmethod
    def dora(
        cls,
        article: Union[int, str],
        paragraph: Optional[Union[int, str]] = None,
        subpara: Optional[str] = None
    ) -> str:
        """
        Generate DORA (Digital Operational Resilience Act) requirement key.

        Args:
            article: Article number
            paragraph: Paragraph number
            subpara: Sub-paragraph letter

        Returns:
            DORA requirement key

        Examples:
            >>> RegulatoryKeyGenerator.dora(8, 1)
            'DORA_8_1'

            >>> RegulatoryKeyGenerator.dora(8, 2, "a")
            'DORA_8_2_a'
        """
        return cls.generate("DORA", article, paragraph, subpara)

    @classmethod
    def nis2(
        cls,
        article: Union[int, str],
        paragraph: Optional[Union[int, str]] = None,
        subpara: Optional[str] = None
    ) -> str:
        """
        Generate NIS2 Directive requirement key.

        Args:
            article: Article number
            paragraph: Paragraph number
            subpara: Sub-paragraph letter

        Returns:
            NIS2 requirement key

        Examples:
            >>> RegulatoryKeyGenerator.nis2(21, 1)
            'NIS2_21_1'

            >>> RegulatoryKeyGenerator.nis2(21, 2, "b")
            'NIS2_21_2_b'
        """
        return cls.generate("NIS2", article, paragraph, subpara)

    # ========== Validation Helpers ==========

    @staticmethod
    def validate_key(key: str) -> bool:
        """
        Validate a regulatory requirement key format.

        Args:
            key: Key to validate

        Returns:
            True if key follows conventions, False otherwise

        Examples:
            >>> RegulatoryKeyGenerator.validate_key("CRA_I_1_a")
            True

            >>> RegulatoryKeyGenerator.validate_key("cra-i-1-a")
            False

            >>> RegulatoryKeyGenerator.validate_key("CRA_I_1 a")
            False
        """
        if not key:
            return False

        # Must contain only alphanumeric and underscores
        if not all(c.isalnum() or c == "_" for c in key):
            return False

        # Must start with a known framework prefix
        valid_prefixes = [
            "CRA_", "FDA_524B_", "IEC_62304_", "ISO_21434_",
            "NIST_SSDF_", "NIST_800_53_", "DORA_", "NIS2_"
        ]

        if not any(key.startswith(prefix) for prefix in valid_prefixes):
            return False

        return True

    @staticmethod
    def extract_framework(key: str) -> Optional[str]:
        """
        Extract framework identifier from a requirement key.

        Args:
            key: Requirement key

        Returns:
            Framework identifier or None if invalid

        Examples:
            >>> RegulatoryKeyGenerator.extract_framework("CRA_I_1_a")
            'CRA'

            >>> RegulatoryKeyGenerator.extract_framework("FDA_524B_V_A_1")
            'FDA_524B'

            >>> RegulatoryKeyGenerator.extract_framework("IEC_62304_5_5_3")
            'IEC_62304'
        """
        if not key:
            return None

        # Known multi-part frameworks
        if key.startswith("FDA_524B_"):
            return "FDA_524B"
        if key.startswith("IEC_62304_"):
            return "IEC_62304"
        if key.startswith("ISO_21434_"):
            return "ISO_21434"
        if key.startswith("NIST_SSDF_"):
            return "NIST_SSDF"
        if key.startswith("NIST_800_53_"):
            return "NIST_800_53"

        # Single-part frameworks
        if key.startswith("CRA_"):
            return "CRA"
        if key.startswith("DORA_"):
            return "DORA"
        if key.startswith("NIS2_"):
            return "NIS2"

        return None

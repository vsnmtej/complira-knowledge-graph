"""
Deterministic key generation and normalization utilities.

ArangoDB requires _key values to be:
- Unique within a collection
- Valid format: alphanumeric + underscore only
- Max length: 254 characters

This module provides normalization functions for common ID formats:
- CVE-2024-1234 → CVE_2024_1234
- CWE-79 → CWE_79
- T1059.001 → T1059_001
- CAPEC-66 → CAPEC_66
- pkg:pypi/django@4.2.0 → pkg_pypi_django_4_2_0 (or hash for long PURLs)
"""

import re
import hashlib
from typing import Optional


def normalize_cve_id(cve_id: str) -> str:
    """
    Normalize CVE ID to ArangoDB _key format.

    Args:
        cve_id: CVE ID (e.g., "CVE-2024-1234")

    Returns:
        str: Normalized key (e.g., "CVE_2024_1234")

    Examples:
        >>> normalize_cve_id("CVE-2024-1234")
        'CVE_2024_1234'
    """
    return cve_id.replace("-", "_").upper()


def normalize_cwe_id(cwe_id: str) -> str:
    """
    Normalize CWE ID to ArangoDB _key format.

    Args:
        cwe_id: CWE ID (e.g., "CWE-79")

    Returns:
        str: Normalized key (e.g., "CWE_79")

    Examples:
        >>> normalize_cwe_id("CWE-79")
        'CWE_79'
    """
    return cwe_id.replace("-", "_").upper()


def normalize_attack_id(attack_id: str) -> str:
    """
    Normalize ATT&CK technique ID to ArangoDB _key format.

    Args:
        attack_id: ATT&CK technique ID (e.g., "T1059.001")

    Returns:
        str: Normalized key (e.g., "t1059_001")

    Examples:
        >>> normalize_attack_id("T1059.001")
        't1059_001'
        >>> normalize_attack_id("T1190")
        't1190'
    """
    return attack_id.replace(".", "_").lower()


def normalize_capec_id(capec_id: str) -> str:
    """
    Normalize CAPEC ID to ArangoDB _key format.

    Args:
        capec_id: CAPEC ID (e.g., "CAPEC-66")

    Returns:
        str: Normalized key (e.g., "CAPEC_66")

    Examples:
        >>> normalize_capec_id("CAPEC-66")
        'CAPEC_66'
    """
    return capec_id.replace("-", "_").upper()


def normalize_ghsa_id(ghsa_id: str) -> str:
    """
    Normalize GitHub Security Advisory ID to ArangoDB _key format.

    Args:
        ghsa_id: GHSA ID (e.g., "GHSA-xxxx-xxxx-xxxx")

    Returns:
        str: Normalized key (e.g., "GHSA_xxxx_xxxx_xxxx")

    Examples:
        >>> normalize_ghsa_id("GHSA-abcd-1234-efgh")
        'GHSA_abcd_1234_efgh'
    """
    return ghsa_id.replace("-", "_")


def normalize_purl(purl: str) -> str:
    """
    Normalize Package URL (PURL) to ArangoDB _key format.

    For PURLs longer than 254 characters, uses SHA256 hash prefix.

    Args:
        purl: Package URL (e.g., "pkg:pypi/django@4.2.0")

    Returns:
        str: Normalized key (e.g., "pkg_pypi_django_4_2_0")

    Examples:
        >>> normalize_purl("pkg:pypi/django@4.2.0")
        'pkg_pypi_django_4_2_0'
        >>> len(normalize_purl("pkg:npm/" + "a" * 300))
        37
    """
    # ArangoDB _key max length is 254 characters
    if len(purl) > 254:
        # Use hash-based key for very long PURLs
        hash_suffix = hashlib.sha256(purl.encode()).hexdigest()[:32]
        return f"purl_{hash_suffix}"

    # Replace special characters with underscores
    normalized = re.sub(r'[^a-zA-Z0-9_]', '_', purl)
    return normalized


def normalize_cpe(cpe: str) -> str:
    """
    Normalize CPE string to ArangoDB _key format.

    Args:
        cpe: CPE 2.3 formatted string

    Returns:
        str: Normalized key

    Examples:
        >>> normalize_cpe("cpe:2.3:a:microsoft:windows:10:*:*:*:*:*:*:*")
        'cpe_2_3_a_microsoft_windows_10'
    """
    # CPE strings can be very long, truncate and hash if needed
    if len(cpe) > 254:
        hash_suffix = hashlib.sha256(cpe.encode()).hexdigest()[:32]
        return f"cpe_{hash_suffix}"

    return re.sub(r'[^a-zA-Z0-9_]', '_', cpe)


def normalize_key(id_value: str, id_type: str) -> str:
    """
    Dispatch to appropriate normalizer based on ID type.

    Args:
        id_value: The identifier value
        id_type: Type of identifier (cve, cwe, attack, capec, purl, cpe, ghsa)

    Returns:
        str: Normalized key suitable for ArangoDB _key

    Raises:
        ValueError: If id_type is not recognized

    Examples:
        >>> normalize_key("CVE-2024-1234", "cve")
        'CVE_2024_1234'
        >>> normalize_key("CWE-79", "cwe")
        'CWE_79'
        >>> normalize_key("T1059.001", "attack")
        'T1059_001'
    """
    normalizers = {
        "cve": normalize_cve_id,
        "cwe": normalize_cwe_id,
        "attack": normalize_attack_id,
        "capec": normalize_capec_id,
        "purl": normalize_purl,
        "cpe": normalize_cpe,
        "ghsa": normalize_ghsa_id,
    }

    normalizer = normalizers.get(id_type.lower())
    if normalizer:
        return normalizer(id_value)

    # Default: replace hyphens and dots with underscores
    return id_value.replace("-", "_").replace(".", "_")


def generate_edge_key(from_id: str, to_id: str, edge_type: Optional[str] = None) -> str:
    """
    Generate deterministic edge _key from source and target IDs.

    Useful for idempotent edge creation (avoiding duplicates).

    Args:
        from_id: Source node _key
        to_id: Target node _key
        edge_type: Optional edge type for disambiguation

    Returns:
        str: Deterministic edge _key

    Examples:
        >>> generate_edge_key("CVE_2024_1234", "CWE_79")
        'CVE_2024_1234_CWE_79'
        >>> generate_edge_key("CVE_2024_1234", "CWE_79", "has_weakness")
        'CVE_2024_1234_has_weakness_CWE_79'
    """
    if edge_type:
        combined = f"{from_id}_{edge_type}_{to_id}"
    else:
        combined = f"{from_id}_{to_id}"

    # If combined key exceeds limit, hash it
    if len(combined) > 254:
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    return combined

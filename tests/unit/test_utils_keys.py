"""
Unit tests for key normalization utilities.
"""

import pytest
from complira_graph.utils.keys import (
    normalize_cve_id,
    normalize_cwe_id,
    normalize_capec_id,
    normalize_attack_id,
    normalize_purl,
    normalize_cpe,
)


class TestCVEIDNormalization:
    """Test CVE ID normalization."""

    def test_normalize_standard_cve(self):
        assert normalize_cve_id('CVE-2024-1234') == 'cve_2024_1234'

    def test_normalize_lowercase_cve(self):
        assert normalize_cve_id('cve-2024-1234') == 'cve_2024_1234'

    def test_normalize_uppercase_cve(self):
        assert normalize_cve_id('CVE-2024-1234') == 'cve_2024_1234'

    def test_normalize_cve_with_leading_zeros(self):
        assert normalize_cve_id('CVE-2024-0001') == 'cve_2024_0001'

    def test_normalize_cve_long_id(self):
        assert normalize_cve_id('CVE-2024-123456') == 'cve_2024_123456'


class TestCWEIDNormalization:
    """Test CWE ID normalization."""

    def test_normalize_standard_cwe(self):
        assert normalize_cwe_id('CWE-79') == 'cwe_79'

    def test_normalize_lowercase_cwe(self):
        assert normalize_cwe_id('cwe-79') == 'cwe_79'

    def test_normalize_cwe_with_leading_zeros(self):
        assert normalize_cwe_id('CWE-001') == 'cwe_001'

    def test_normalize_cwe_long_id(self):
        assert normalize_cwe_id('CWE-1234') == 'cwe_1234'


class TestCAPECIDNormalization:
    """Test CAPEC ID normalization."""

    def test_normalize_standard_capec(self):
        assert normalize_capec_id('CAPEC-66') == 'capec_66'

    def test_normalize_lowercase_capec(self):
        assert normalize_capec_id('capec-66') == 'capec_66'

    def test_normalize_capec_with_leading_zeros(self):
        assert normalize_capec_id('CAPEC-001') == 'capec_001'


class TestATTACKIDNormalization:
    """Test ATT&CK ID normalization."""

    def test_normalize_technique(self):
        assert normalize_attack_id('T1190') == 't1190'

    def test_normalize_subtechnique(self):
        assert normalize_attack_id('T1190.001') == 't1190_001'

    def test_normalize_lowercase_technique(self):
        assert normalize_attack_id('t1190') == 't1190'

    def test_normalize_group(self):
        assert normalize_attack_id('G0001') == 'g0001'


class TestPURLNormalization:
    """Test Package URL normalization."""

    def test_normalize_npm_purl(self):
        purl = 'pkg:npm/lodash@4.17.21'
        normalized = normalize_purl(purl)
        assert normalized == 'pkg_npm_lodash_4_17_21'

    def test_normalize_pypi_purl(self):
        purl = 'pkg:pypi/django@4.2.0'
        normalized = normalize_purl(purl)
        assert normalized == 'pkg_pypi_django_4_2_0'

    def test_normalize_maven_purl(self):
        purl = 'pkg:maven/org.springframework/spring-core@6.0.0'
        normalized = normalize_purl(purl)
        assert 'pkg_maven' in normalized
        assert 'spring_core' in normalized

    def test_normalize_purl_with_namespace(self):
        purl = 'pkg:npm/@types/node@18.0.0'
        normalized = normalize_purl(purl)
        assert normalized.startswith('pkg_npm')


class TestCPENormalization:
    """Test CPE normalization."""

    def test_normalize_cpe23(self):
        cpe = 'cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*'
        normalized = normalize_cpe(cpe)
        assert normalized.startswith('cpe_2_3')
        assert 'vendor' in normalized
        assert 'product' in normalized

    def test_normalize_cpe22(self):
        cpe = 'cpe:/a:vendor:product:1.0'
        normalized = normalize_cpe(cpe)
        assert 'vendor' in normalized
        assert 'product' in normalized

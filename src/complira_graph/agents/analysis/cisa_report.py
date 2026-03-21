"""
CISA Report Agent - Generate prioritized vulnerability patching reports.

Analyzes CISA-enriched vulnerabilities to create risk-based prioritization
reports using KEV status, SSVC scores, and CVSS severity.
"""

import json
from typing import Any
from datetime import datetime

from .base import BaseAnalysisAgent


class CISAReportAgent(BaseAnalysisAgent):
    """
    Generate prioritized patching reports using CISA enrichment data.

    Prioritization factors:
    - KEV status (Known Exploited Vulnerabilities) - Highest priority
    - SSVC Exploitation (active > poc > none)
    - SSVC Automatable (yes > no)
    - SSVC Technical Impact (total > partial)
    - CVSS severity (critical > high > medium > low)

    Priority scoring:
    - KEV: +50 points
    - Active exploitation: +30 points
    - PoC exploitation: +15 points
    - Automatable: +10 points
    - Total technical impact: +10 points
    - CVSS >= 9.0: +10 points
    - CVSS >= 7.0: +5 points
    """

    def query_data(self, **kwargs) -> list[dict]:
        """
        Query all CISA-enriched vulnerabilities.

        Args:
            **kwargs: Optional filters (not currently used)

        Returns:
            list[dict]: CISA-enriched vulnerabilities
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cisa_enriched == true
            RETURN vuln
        """

        cursor = self.db.aql.execute(query)
        vulns = list(cursor)

        self.logger.info("Queried CISA-enriched vulnerabilities", count=len(vulns))

        return vulns

    def _calculate_priority_score(self, vuln: dict) -> int:
        """
        Calculate priority score (0-110, higher = more urgent).

        Args:
            vuln: Vulnerability document

        Returns:
            int: Priority score
        """
        score = 0

        # KEV status (highest priority)
        if vuln.get('in_cisa_kev'):
            score += 50

        # SSVC Exploitation
        ssvc = vuln.get('cisa_ssvc', {})
        exploitation = ssvc.get('exploitation')
        if exploitation == 'active':
            score += 30
        elif exploitation == 'poc':
            score += 15

        # SSVC Automatable
        if ssvc.get('automatable') == 'yes':
            score += 10

        # SSVC Technical Impact
        if ssvc.get('technical_impact') == 'total':
            score += 10

        # CVSS severity
        cvss = vuln.get('cisa_cvss', {}).get('base_score') or vuln.get('cvss_v3_score')
        if cvss:
            if cvss >= 9.0:
                score += 10
            elif cvss >= 7.0:
                score += 5

        return score

    def analyze(self, vulns: list[dict]) -> dict:
        """
        Analyze vulnerabilities and calculate priority scores.

        Args:
            vulns: List of CISA-enriched vulnerabilities

        Returns:
            dict: Analysis results with priority rankings and statistics
        """
        if not vulns:
            return {
                "total": 0,
                "message": "No CISA-enriched vulnerabilities found"
            }

        # Calculate priority scores
        vulns_with_scores = []
        for vuln in vulns:
            score = self._calculate_priority_score(vuln)
            vulns_with_scores.append({
                "vuln": vuln,
                "priority_score": score
            })

        # Sort by priority score (descending)
        vulns_with_scores.sort(key=lambda x: x['priority_score'], reverse=True)

        # Categorize by priority
        kev_vulns = [v for v in vulns_with_scores if v['vuln'].get('in_cisa_kev')]
        active_vulns = [
            v for v in vulns_with_scores
            if v['vuln'].get('cisa_ssvc', {}).get('exploitation') == 'active'
            and not v['vuln'].get('in_cisa_kev')
        ]
        automatable_total_impact = [
            v for v in vulns_with_scores
            if v['vuln'].get('cisa_ssvc', {}).get('automatable') == 'yes'
            and v['vuln'].get('cisa_ssvc', {}).get('technical_impact') == 'total'
            and not v['vuln'].get('in_cisa_kev')
            and v['vuln'].get('cisa_ssvc', {}).get('exploitation') != 'active'
        ]
        poc_vulns = [
            v for v in vulns_with_scores
            if v['vuln'].get('cisa_ssvc', {}).get('exploitation') == 'poc'
            and not v['vuln'].get('in_cisa_kev')
        ]

        # Calculate statistics
        total = len(vulns)
        automatable_count = sum(
            1 for v in vulns
            if v.get('cisa_ssvc', {}).get('automatable') == 'yes'
        )
        total_impact_count = sum(
            1 for v in vulns
            if v.get('cisa_ssvc', {}).get('technical_impact') == 'total'
        )
        critical_cvss_count = sum(
            1 for v in vulns
            if (v.get('cisa_cvss', {}).get('base_score') or v.get('cvss_v3_score') or 0) >= 9.0
        )

        # Priority distribution
        high_priority = len([v for v in vulns_with_scores if v['priority_score'] >= 50])
        medium_priority = len([v for v in vulns_with_scores if 25 <= v['priority_score'] < 50])
        low_priority = len([v for v in vulns_with_scores if v['priority_score'] < 25])

        return {
            "total": total,
            "generated_at": datetime.utcnow().isoformat(),
            "categories": {
                "kev": {
                    "count": len(kev_vulns),
                    "percent": len(kev_vulns) / total * 100 if total > 0 else 0,
                    "vulns": kev_vulns[:20]  # Top 20
                },
                "active_exploitation": {
                    "count": len(active_vulns),
                    "percent": len(active_vulns) / total * 100 if total > 0 else 0,
                    "vulns": active_vulns[:20]
                },
                "automatable_total_impact": {
                    "count": len(automatable_total_impact),
                    "percent": len(automatable_total_impact) / total * 100 if total > 0 else 0,
                    "vulns": automatable_total_impact[:20]
                },
                "poc_available": {
                    "count": len(poc_vulns),
                    "percent": len(poc_vulns) / total * 100 if total > 0 else 0,
                    "vulns": poc_vulns[:10]
                }
            },
            "statistics": {
                "automatable": automatable_count,
                "total_impact": total_impact_count,
                "critical_cvss": critical_cvss_count
            },
            "priority_distribution": {
                "high": {"count": high_priority, "percent": high_priority / total * 100 if total > 0 else 0},
                "medium": {"count": medium_priority, "percent": medium_priority / total * 100 if total > 0 else 0},
                "low": {"count": low_priority, "percent": low_priority / total * 100 if total > 0 else 0}
            },
            "top_25": vulns_with_scores[:25]
        }

    def _format_text(self, analysis: dict) -> str:
        """Format analysis as text report."""
        if analysis.get("total", 0) == 0:
            return analysis.get("message", "No data available")

        lines = []
        lines.append("=" * 80)
        lines.append("  CISA-Enhanced Vulnerability Prioritization Report")
        lines.append("=" * 80)
        lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")

        total = analysis["total"]
        categories = analysis["categories"]
        stats = analysis["statistics"]
        priority_dist = analysis["priority_distribution"]

        # KEV Section
        kev_data = categories["kev"]
        lines.append("🚨 CRITICAL: Known Exploited Vulnerabilities (KEV)")
        lines.append("-" * 80)
        lines.append(f"ACTION REQUIRED: Patch {kev_data['count']} KEV vulnerabilities immediately per CISA directive.")
        lines.append("")

        if kev_data["vulns"]:
            lines.append(f"{'#':<4} {'CVE ID':<18} {'Score':<5} {'Exploit':<8} {'Auto':<5} {'Impact':<7} {'CVSS':<6}")
            lines.append("-" * 80)

            for idx, item in enumerate(kev_data["vulns"], 1):
                v = item["vuln"]
                score = item["priority_score"]
                ssvc = v.get('cisa_ssvc', {})

                exploitation = ssvc.get('exploitation', 'N/A')[:8]
                automatable = ssvc.get('automatable', 'N/A')[:3]
                impact = ssvc.get('technical_impact', 'N/A')[:7]
                cvss = v.get('cisa_cvss', {}).get('base_score') or v.get('cvss_v3_score') or 'N/A'
                cvss_str = f"{cvss:.1f}" if isinstance(cvss, (int, float)) else str(cvss)

                lines.append(f"{idx:>3}. {v['cve_id']:<18} {score:>3} {exploitation:<8} {automatable:<5} {impact:<7} {cvss_str:<6}")

        lines.append("")

        # Top 25 Overall
        lines.append("📊 Top 25 Vulnerabilities by Priority Score")
        lines.append("-" * 80)
        lines.append(f"{'#':<4} {'CVE ID':<18} {'Score':<5} {'Exploit':<8} {'Auto':<5} {'Impact':<7} {'CVSS':<6} {'KEV'}")
        lines.append("-" * 80)

        for idx, item in enumerate(analysis["top_25"], 1):
            v = item["vuln"]
            score = item["priority_score"]
            ssvc = v.get('cisa_ssvc', {})

            exploitation = ssvc.get('exploitation', 'N/A')[:8]
            automatable = ssvc.get('automatable', 'N/A')[:3]
            impact = ssvc.get('technical_impact', 'N/A')[:7]
            cvss = v.get('cisa_cvss', {}).get('base_score') or v.get('cvss_v3_score') or 'N/A'
            cvss_str = f"{cvss:.1f}" if isinstance(cvss, (int, float)) else str(cvss)
            kev_flag = "🚨" if v.get('in_cisa_kev') else ""

            lines.append(f"{idx:>3}. {v['cve_id']:<18} {score:>3} {exploitation:<8} {automatable:<5} {impact:<7} {cvss_str:<6} {kev_flag}")

        lines.append("")

        # Summary Statistics
        lines.append("📈 Summary Statistics")
        lines.append("-" * 80)
        lines.append(f"Total CISA-Enriched Vulnerabilities: {total:,}")
        lines.append("")
        lines.append("Risk Categories:")
        lines.append(f"  🚨 KEV Catalog (Critical):         {kev_data['count']:>4} ({kev_data['percent']:.1f}%)")
        lines.append(f"  🔥 Active Exploitation:            {categories['active_exploitation']['count']:>4} ({categories['active_exploitation']['percent']:.1f}%)")
        lines.append(f"  ⚠️  PoC Available:                  {categories['poc_available']['count']:>4} ({categories['poc_available']['percent']:.1f}%)")
        lines.append(f"  💣 Automatable:                    {stats['automatable']:>4} ({stats['automatable']/total*100:.1f}%)")
        lines.append(f"  💥 Total Technical Impact:         {stats['total_impact']:>4} ({stats['total_impact']/total*100:.1f}%)")
        lines.append(f"  🔴 CVSS >= 9.0 (Critical):         {stats['critical_cvss']:>4} ({stats['critical_cvss']/total*100:.1f}%)")
        lines.append("")
        lines.append("Priority Score Distribution:")
        lines.append(f"  High (50-110):   {priority_dist['high']['count']:>4} ({priority_dist['high']['percent']:.1f}%)")
        lines.append(f"  Medium (25-49):  {priority_dist['medium']['count']:>4} ({priority_dist['medium']['percent']:.1f}%)")
        lines.append(f"  Low (0-24):      {priority_dist['low']['count']:>4} ({priority_dist['low']['percent']:.1f}%)")
        lines.append("")

        # Recommendations
        lines.append("💡 Recommendations")
        lines.append("-" * 80)
        lines.append("1. IMMEDIATE ACTION (Next 7 Days):")
        lines.append(f"   - Patch all {kev_data['count']} KEV vulnerabilities (CISA directive)")
        if categories['active_exploitation']['count'] > 0:
            lines.append(f"   - Address {categories['active_exploitation']['count']} vulnerabilities with active exploitation")
        lines.append("")
        lines.append("2. SHORT-TERM (Next 30 Days):")
        lines.append(f"   - Prioritize {categories['automatable_total_impact']['count']} automatable + total impact vulnerabilities")
        lines.append(f"   - Review {stats['critical_cvss']} CVSS 9.0+ critical vulnerabilities")
        lines.append("")
        lines.append("3. ONGOING:")
        lines.append(f"   - Monitor {categories['poc_available']['count']} PoC-available vulnerabilities for exploitation trends")
        lines.append("   - Re-run CISA enrichment weekly: complira incremental CISAADPAgent")
        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

    def _format_json(self, analysis: dict) -> str:
        """Format analysis as JSON."""
        return json.dumps(analysis, indent=2, default=str)

    def _format_markdown(self, analysis: dict) -> str:
        """Format analysis as Markdown report."""
        if analysis.get("total", 0) == 0:
            return f"# No Data\n\n{analysis.get('message', 'No data available')}"

        lines = []
        lines.append("# CISA-Enhanced Vulnerability Prioritization Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        total = analysis["total"]
        categories = analysis["categories"]

        # KEV Section
        kev_data = categories["kev"]
        lines.append("## 🚨 CRITICAL: Known Exploited Vulnerabilities (KEV)")
        lines.append("")
        lines.append(f"**ACTION REQUIRED:** Patch {kev_data['count']} KEV vulnerabilities immediately per CISA directive.")
        lines.append("")

        if kev_data["vulns"]:
            lines.append("| # | CVE ID | Score | Exploit | Auto | Impact | CVSS |")
            lines.append("|---|--------|-------|---------|------|--------|------|")

            for idx, item in enumerate(kev_data["vulns"], 1):
                v = item["vuln"]
                score = item["priority_score"]
                ssvc = v.get('cisa_ssvc', {})

                exploitation = ssvc.get('exploitation', 'N/A')
                automatable = ssvc.get('automatable', 'N/A')
                impact = ssvc.get('technical_impact', 'N/A')
                cvss = v.get('cisa_cvss', {}).get('base_score') or v.get('cvss_v3_score') or 'N/A'

                lines.append(f"| {idx} | {v['cve_id']} | {score} | {exploitation} | {automatable} | {impact} | {cvss} |")

        lines.append("")
        lines.append(f"**Full report:** Use `complira report cisa --format text` for detailed output")
        lines.append("")

        return "\n".join(lines)

    def format_output(self, analysis: dict) -> str:
        """
        Format analysis results based on output_format.

        Args:
            analysis: Analysis results

        Returns:
            str: Formatted output
        """
        if self.output_format == "json":
            return self._format_json(analysis)
        elif self.output_format == "markdown":
            return self._format_markdown(analysis)
        else:  # text (default)
            return self._format_text(analysis)

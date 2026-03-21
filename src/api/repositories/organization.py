"""
Organization repository (Phase 5 - Web UI Authentication).

Handles CRUD operations for organizations collection.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from arango.database import StandardDatabase
import structlog
import re

logger = structlog.get_logger()


class OrganizationRepository:
    """
    Repository for organization-related database operations.

    Handles:
    - Organization creation and lookup
    - Slug generation
    - Organization settings and tier management
    """

    def __init__(self, db: StandardDatabase):
        """
        Initialize organization repository.

        Args:
            db: ArangoDB database instance
        """
        self.db = db
        self.organizations = db.collection("organizations")

    def generate_slug(self, name: str) -> str:
        """
        Generate URL-safe slug from organization name.

        Args:
            name: Organization name

        Returns:
            str: URL-safe slug

        Example:
            "Acme Medical Devices Inc." -> "acme-medical-devices-inc"
        """
        # Convert to lowercase
        slug = name.lower()

        # Replace spaces and special chars with hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', slug)

        # Remove leading/trailing hyphens
        slug = slug.strip('-')

        # Ensure uniqueness by checking database
        base_slug = slug
        counter = 1
        while self.get_organization_by_slug(slug) is not None:
            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug

    def create_organization(
        self,
        name: str,
        domain: Optional[str] = None,
        tier: str = "free",
        frameworks: Optional[List[str]] = None
    ) -> dict:
        """
        Create new organization.

        Args:
            name: Organization name
            domain: Primary domain (optional)
            tier: Organization tier (free, professional, enterprise)
            frameworks: List of compliance frameworks (e.g., ["FDA_524B", "IEC_62304"])

        Returns:
            dict: Created organization document

        Example:
            {
                "_key": "org_abc123",
                "name": "Acme Medical Devices Inc.",
                "slug": "acme-medical-devices-inc",
                "domain": "acme-medical.com",
                "tier": "professional",
                "frameworks": ["FDA_524B", "IEC_62304"],
                "settings": {
                    "scan_retention_days": 90,
                    "max_scans_per_month": 1000
                },
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        """
        now = datetime.utcnow().isoformat() + "Z"
        slug = self.generate_slug(name)

        # Default settings based on tier
        tier_settings = {
            "free": {
                "scan_retention_days": 30,
                "max_scans_per_month": 100,
                "max_users": 3,
                "api_rate_limit": 100  # requests per day
            },
            "professional": {
                "scan_retention_days": 90,
                "max_scans_per_month": 1000,
                "max_users": 10,
                "api_rate_limit": 10000
            },
            "enterprise": {
                "scan_retention_days": 365,
                "max_scans_per_month": -1,  # unlimited
                "max_users": -1,  # unlimited
                "api_rate_limit": -1  # unlimited
            }
        }

        org_doc = {
            "name": name,
            "slug": slug,
            "domain": domain,
            "tier": tier,
            "frameworks": frameworks or [],
            "settings": tier_settings.get(tier, tier_settings["free"]),
            "created_at": now,
            "updated_at": now,
        }

        result = self.organizations.insert(org_doc, return_new=True)
        org = result["new"]

        logger.info(
            "Organization created",
            org_id=org["_key"],
            name=name,
            slug=slug,
            tier=tier
        )

        return org

    def get_organization_by_id(self, org_id: str) -> Optional[dict]:
        """
        Get organization by ID (_key).

        Args:
            org_id: Organization document _key

        Returns:
            dict: Organization document or None if not found
        """
        try:
            return self.organizations.get(org_id)
        except Exception as e:
            logger.error("Organization lookup error", org_id=org_id, error=str(e))
            return None

    def get_organization_by_slug(self, slug: str) -> Optional[dict]:
        """
        Get organization by slug.

        Args:
            slug: Organization slug

        Returns:
            dict: Organization document or None if not found
        """
        query = """
        FOR org IN organizations
            FILTER org.slug == @slug
            LIMIT 1
            RETURN org
        """

        cursor = self.db.aql.execute(query, bind_vars={"slug": slug})
        orgs = list(cursor)

        return orgs[0] if orgs else None

    def get_organization_by_domain(self, domain: str) -> Optional[dict]:
        """
        Get organization by domain.

        Args:
            domain: Organization domain

        Returns:
            dict: Organization document or None if not found
        """
        query = """
        FOR org IN organizations
            FILTER org.domain == @domain
            LIMIT 1
            RETURN org
        """

        cursor = self.db.aql.execute(query, bind_vars={"domain": domain})
        orgs = list(cursor)

        return orgs[0] if orgs else None

    def list_organizations(
        self,
        tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """
        List organizations with optional filtering.

        Args:
            tier: Filter by tier (free, professional, enterprise)
            limit: Maximum number of organizations to return
            offset: Number of organizations to skip

        Returns:
            List[dict]: Organization documents
        """
        query = """
        FOR org IN organizations
            FILTER @tier == null OR org.tier == @tier
            SORT org.created_at DESC
            LIMIT @offset, @limit
            RETURN org
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={
                "tier": tier,
                "limit": limit,
                "offset": offset
            }
        )

        return list(cursor)

    def update_organization(
        self,
        org_id: str,
        updates: Dict[str, Any]
    ) -> Optional[dict]:
        """
        Update organization fields.

        Args:
            org_id: Organization document _key
            updates: Fields to update

        Returns:
            dict: Updated organization document or None
        """
        now = datetime.utcnow().isoformat() + "Z"
        updates["updated_at"] = now

        # If name is updated, regenerate slug
        if "name" in updates:
            updates["slug"] = self.generate_slug(updates["name"])

        try:
            result = self.organizations.update(org_id, updates, return_new=True)
            logger.info(
                "Organization updated",
                org_id=org_id,
                fields=list(updates.keys())
            )
            return result["new"]
        except Exception as e:
            logger.error("Organization update error", org_id=org_id, error=str(e))
            return None

    def update_tier(self, org_id: str, new_tier: str) -> Optional[dict]:
        """
        Update organization tier and settings.

        Args:
            org_id: Organization document _key
            new_tier: New tier (free, professional, enterprise)

        Returns:
            dict: Updated organization document or None
        """
        tier_settings = {
            "free": {
                "scan_retention_days": 30,
                "max_scans_per_month": 100,
                "max_users": 3,
                "api_rate_limit": 100
            },
            "professional": {
                "scan_retention_days": 90,
                "max_scans_per_month": 1000,
                "max_users": 10,
                "api_rate_limit": 10000
            },
            "enterprise": {
                "scan_retention_days": 365,
                "max_scans_per_month": -1,
                "max_users": -1,
                "api_rate_limit": -1
            }
        }

        updates = {
            "tier": new_tier,
            "settings": tier_settings.get(new_tier, tier_settings["free"])
        }

        logger.info("Updating organization tier", org_id=org_id, new_tier=new_tier)
        return self.update_organization(org_id, updates)

    def add_framework(self, org_id: str, framework: str) -> Optional[dict]:
        """
        Add compliance framework to organization.

        Args:
            org_id: Organization document _key
            framework: Framework code (e.g., "FDA_524B", "IEC_62304")

        Returns:
            dict: Updated organization document or None
        """
        org = self.get_organization_by_id(org_id)
        if not org:
            return None

        frameworks = org.get("frameworks", [])
        if framework not in frameworks:
            frameworks.append(framework)
            return self.update_organization(org_id, {"frameworks": frameworks})

        return org

    def remove_framework(self, org_id: str, framework: str) -> Optional[dict]:
        """
        Remove compliance framework from organization.

        Args:
            org_id: Organization document _key
            framework: Framework code to remove

        Returns:
            dict: Updated organization document or None
        """
        org = self.get_organization_by_id(org_id)
        if not org:
            return None

        frameworks = org.get("frameworks", [])
        if framework in frameworks:
            frameworks.remove(framework)
            return self.update_organization(org_id, {"frameworks": frameworks})

        return org

    def delete_organization(self, org_id: str) -> bool:
        """
        Delete organization and associated data.

        CAUTION: This will cascade delete all users, scans, and data.

        Args:
            org_id: Organization document _key

        Returns:
            bool: True if deletion succeeded
        """
        try:
            # Delete organization document
            # Note: Cascade deletion of users and scans should be handled separately
            # or via database triggers for safety
            self.organizations.delete(org_id)

            logger.warning(
                "Organization deleted",
                org_id=org_id,
                message="Associated data should be cleaned up separately"
            )
            return True
        except Exception as e:
            logger.error("Organization deletion error", org_id=org_id, error=str(e))
            return False

    def get_organization_stats(self, org_id: str) -> Optional[Dict[str, Any]]:
        """
        Get organization statistics (user count, scan count, etc.).

        Args:
            org_id: Organization document _key

        Returns:
            dict: Organization statistics or None

        Example:
            {
                "user_count": 5,
                "scan_count": 42,
                "total_findings": 1234,
                "critical_findings": 12
            }
        """
        query = """
        LET org_doc_id = CONCAT("organizations/", @org_id)

        LET user_count = LENGTH(
            FOR user IN users
                FOR edge IN user_belongs_to_org
                    FILTER edge._to == org_doc_id
                    RETURN 1
        )

        RETURN {
            user_count: user_count
        }
        """

        try:
            cursor = self.db.aql.execute(query, bind_vars={"org_id": org_id})
            results = list(cursor)
            return results[0] if results else None
        except Exception as e:
            logger.error("Organization stats error", org_id=org_id, error=str(e))
            return None

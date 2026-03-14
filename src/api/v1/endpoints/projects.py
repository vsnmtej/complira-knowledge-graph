"""
Project management endpoints.

POST /v1/projects - Create new project
GET /v1/projects - List projects
GET /v1/projects/{project_id} - Get project details
PUT /v1/projects/{project_id} - Update project
DELETE /v1/projects/{project_id} - Soft delete project
GET /v1/projects/{project_id}/summary - Get project summary with aggregated insights
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
import structlog
import secrets
from datetime import datetime

from api.core.security import Customer, get_current_customer
from api.core.database import get_database
from api.models.requests.projects import CreateProjectRequest, UpdateProjectRequest
from api.models.responses.projects import (
    CreateProjectResponse,
    ProjectResponse,
    ListProjectsResponse,
    ProjectSummaryResponse,
    DeleteProjectResponse,
)
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


def generate_project_id() -> str:
    """Generate a unique project ID."""
    return f"proj_{secrets.token_hex(12)}"


@router.post("", response_model=APIResponse[CreateProjectResponse])
async def create_project(
    request: CreateProjectRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/projects

    Create a new project for the authenticated customer.

    **Use Cases:**
    - Organize repositories by project (e.g., "Backend Services", "Mobile Apps")
    - Group related repositories for aggregated reporting
    - Apply tags for categorization

    **Example:**
    ```bash
    curl -X POST https://api.complira.dev/v1/projects \
      -H "X-API-Key: your_api_key" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "Backend Services",
        "description": "All backend microservices",
        "tags": ["backend", "production"]
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Generate project ID
        project_id = generate_project_id()
        created_at = datetime.utcnow()

        # Create project document
        project_doc = {
            "_key": project_id,
            "project_id": project_id,
            "customer_id": customer.id,
            "name": request.name,
            "description": request.description,
            "tags": request.tags or [],
            "repository_count": 0,
            "created_at": created_at.isoformat() + "Z",
            "updated_at": created_at.isoformat() + "Z",
            "last_scan_at": None,
            "active": True,
        }

        # Ensure projects collection exists
        if not db.has_collection("projects"):
            collection = db.create_collection("projects", edge=False)
            # Create indexes
            collection.add_hash_index(fields=["customer_id"], unique=False)
            collection.add_hash_index(fields=["project_id"], unique=True)
            collection.add_skiplist_index(fields=["customer_id", "active"], unique=False)
        else:
            collection = db.collection("projects")

        # Insert project
        collection.insert(project_doc)

        logger.info(
            "Project created",
            customer_id=customer.id,
            project_id=project_id,
            project_name=request.name,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=CreateProjectResponse(
                project_id=project_id,
                name=request.name,
                description=request.description,
                tags=request.tags or [],
                created_at=created_at.isoformat() + "Z",
                repository_count=0,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "Project creation failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during project creation"
        )


@router.get("", response_model=APIResponse[ListProjectsResponse])
async def list_projects(
    customer: Customer = Depends(get_current_customer),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
):
    """
    GET /v1/projects

    List all projects for the authenticated customer.

    **Query Parameters:**
    - active: Filter by active status (true/false)
    - tags: Filter by tags (comma-separated, e.g., "backend,production")

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/projects?active=true&tags=backend \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Build filter conditions
        filter_conditions = ["project.customer_id == @customer_id"]
        bind_vars = {"customer_id": customer.id}

        if active is not None:
            filter_conditions.append("project.active == @active")
            bind_vars["active"] = active

        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            filter_conditions.append("LENGTH(INTERSECTION(project.tags, @tags)) > 0")
            bind_vars["tags"] = tag_list

        filter_clause = " AND ".join(filter_conditions)

        # Query projects
        query = f"""
        FOR project IN projects
            FILTER {filter_clause}
            SORT project.created_at DESC
            RETURN project
        """

        cursor = db.aql.execute(query, bind_vars=bind_vars)
        projects = list(cursor)

        # Convert to response models
        project_responses = [
            ProjectResponse(
                project_id=p["project_id"],
                name=p["name"],
                description=p.get("description"),
                tags=p.get("tags", []),
                repository_count=p.get("repository_count", 0),
                created_at=p["created_at"],
                updated_at=p["updated_at"],
                last_scan_at=p.get("last_scan_at"),
                active=p.get("active", True),
            )
            for p in projects
        ]

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ListProjectsResponse(
                projects=project_responses,
                total=len(project_responses),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "Project listing failed",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(
    project_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/projects/{project_id}

    Get details for a specific project.

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/projects/proj_abc123 \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Query project
        query = """
        FOR project IN projects
            FILTER project.project_id == @project_id
            FILTER project.customer_id == @customer_id
            RETURN project
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        projects = list(cursor)

        if not projects:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}"
            )

        project = projects[0]

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ProjectResponse(
                project_id=project["project_id"],
                name=project["name"],
                description=project.get("description"),
                tags=project.get("tags", []),
                repository_count=project.get("repository_count", 0),
                created_at=project["created_at"],
                updated_at=project["updated_at"],
                last_scan_at=project.get("last_scan_at"),
                active=project.get("active", True),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Project retrieval failed",
            customer_id=customer.id,
            project_id=project_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    PUT /v1/projects/{project_id}

    Update an existing project.

    **Example:**
    ```bash
    curl -X PUT https://api.complira.dev/v1/projects/proj_abc123 \
      -H "X-API-Key: your_api_key" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "Backend Services (Updated)",
        "description": "All backend microservices - updated",
        "tags": ["backend", "production", "critical"]
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()
        collection = db.collection("projects")

        # Verify project exists and belongs to customer
        query = """
        FOR project IN projects
            FILTER project.project_id == @project_id
            FILTER project.customer_id == @customer_id
            RETURN project
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        projects = list(cursor)

        if not projects:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}"
            )

        project = projects[0]

        # Build update document
        update_doc = {
            "_key": project["_key"],
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

        if request.name is not None:
            update_doc["name"] = request.name
        if request.description is not None:
            update_doc["description"] = request.description
        if request.tags is not None:
            update_doc["tags"] = request.tags
        if request.active is not None:
            update_doc["active"] = request.active

        # Update project
        collection.update(update_doc)

        # Fetch updated project
        cursor = db.aql.execute(
            query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        updated_project = list(cursor)[0]

        logger.info(
            "Project updated",
            customer_id=customer.id,
            project_id=project_id,
            updates=list(update_doc.keys()),
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ProjectResponse(
                project_id=updated_project["project_id"],
                name=updated_project["name"],
                description=updated_project.get("description"),
                tags=updated_project.get("tags", []),
                repository_count=updated_project.get("repository_count", 0),
                created_at=updated_project["created_at"],
                updated_at=updated_project["updated_at"],
                last_scan_at=updated_project.get("last_scan_at"),
                active=updated_project.get("active", True),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Project update failed",
            customer_id=customer.id,
            project_id=project_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during project update"
        )


@router.delete("/{project_id}", response_model=APIResponse[DeleteProjectResponse])
async def delete_project(
    project_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    DELETE /v1/projects/{project_id}

    Soft delete a project (sets active=false).

    **Important:**
    - Repositories in this project are NOT deleted
    - Repositories will have their project_id set to null (unassigned)
    - Historical scan data is preserved

    **Example:**
    ```bash
    curl -X DELETE https://api.complira.dev/v1/projects/proj_abc123 \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()
        collection = db.collection("projects")

        # Verify project exists and belongs to customer
        query = """
        FOR project IN projects
            FILTER project.project_id == @project_id
            FILTER project.customer_id == @customer_id
            RETURN project
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        projects = list(cursor)

        if not projects:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}"
            )

        project = projects[0]

        # Check if already deleted
        if not project.get("active", True):
            raise HTTPException(
                status_code=400,
                detail=f"Project already deleted: {project_id}"
            )

        # Soft delete project
        deleted_at = datetime.utcnow()
        collection.update({
            "_key": project["_key"],
            "active": False,
            "updated_at": deleted_at.isoformat() + "Z",
        })

        # Unassign all repositories from this project
        if db.has_collection("repositories"):
            unassign_query = """
            FOR repo IN repositories
                FILTER repo.project_id == @project_id
                FILTER repo.customer_id == @customer_id
                UPDATE repo WITH {
                    project_id: null,
                    updated_at: @deleted_at
                } IN repositories
            """
            db.aql.execute(
                unassign_query,
                bind_vars={
                    "project_id": project_id,
                    "customer_id": customer.id,
                    "deleted_at": deleted_at.isoformat() + "Z",
                }
            )

        logger.warning(
            "Project deleted",
            customer_id=customer.id,
            project_id=project_id,
            project_name=project["name"],
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=DeleteProjectResponse(
                project_id=project_id,
                name=project["name"],
                deleted_at=deleted_at.isoformat() + "Z",
                message=f"Project '{project['name']}' has been deleted. Associated repositories have been unassigned.",
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Project deletion failed",
            customer_id=customer.id,
            project_id=project_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during project deletion"
        )


@router.get("/{project_id}/summary", response_model=APIResponse[ProjectSummaryResponse])
async def get_project_summary(
    project_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/projects/{project_id}/summary

    Get aggregated insights for a project across all repositories.

    **Returns:**
    - Repository count and breakdown
    - Total scan sessions across all repositories
    - Aggregated vulnerability findings (critical, high, medium, low)
    - Top CVEs across all repositories in this project
    - Compliance status summary

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/projects/proj_abc123/summary \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Verify project exists
        project_query = """
        FOR project IN projects
            FILTER project.project_id == @project_id
            FILTER project.customer_id == @customer_id
            RETURN project
        """

        cursor = db.aql.execute(
            project_query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        projects = list(cursor)

        if not projects:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}"
            )

        project = projects[0]

        # Get repositories in this project
        repos_query = """
        FOR repo IN repositories
            FILTER repo.project_id == @project_id
            FILTER repo.customer_id == @customer_id
            FILTER repo.active == true
            RETURN repo
        """

        cursor = db.aql.execute(
            repos_query,
            bind_vars={"project_id": project_id, "customer_id": customer.id}
        )
        repositories = list(cursor)

        # Aggregate scan data across repositories
        total_scans = sum(repo.get("scan_count", 0) for repo in repositories)

        # Placeholder aggregations (to be implemented with actual scan data)
        findings = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0,
        }

        top_vulnerabilities = []
        compliance_status = None

        # Build repository breakdown
        repository_breakdown = [
            {
                "repository_id": repo["repository_id"],
                "repository_name": repo["name"],
                "scan_count": repo.get("scan_count", 0),
                "last_scan_at": repo.get("last_scan_at"),
            }
            for repo in repositories
        ]

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ProjectSummaryResponse(
                project_id=project_id,
                project_name=project["name"],
                repository_count=len(repositories),
                total_scans=total_scans,
                findings=findings,
                top_vulnerabilities=top_vulnerabilities,
                compliance_status=compliance_status,
                repositories=repository_breakdown,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Project summary retrieval failed",
            customer_id=customer.id,
            project_id=project_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")

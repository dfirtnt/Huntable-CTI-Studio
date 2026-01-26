"""
Comprehensive CRUD tests for the annotation API endpoints.
"""

import pytest
import httpx
from typing import Dict, Any


class TestCreateAnnotation:
    """Test annotation creation endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_success(self, async_client: httpx.AsyncClient):
        """Test successfully creating an annotation."""
        # First get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create annotation with valid text length
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,  # Exactly 1000 characters
            "start_position": 0,
            "end_position": 1000,
            "context_before": "",
            "context_after": "",
            "confidence_score": 1.0
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "annotation" in data
        assert data["message"] == "Annotation created successfully"
        assert data["annotation"]["article_id"] == article_id
        assert data["annotation"]["annotation_type"] == "huntable"
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_text_too_short(self, async_client: httpx.AsyncClient):
        """Test creating annotation with text too short."""
        # Get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Try to create annotation with text too short
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 900,  # Too short (< 950)
            "start_position": 0,
            "end_position": 900
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Annotation text must be approximately 1000 characters" in data["detail"]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_text_too_long(self, async_client: httpx.AsyncClient):
        """Test creating annotation with text too long."""
        # Get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Try to create annotation with text too long
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1100,  # Too long (> 1050)
            "start_position": 0,
            "end_position": 1100
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Annotation text must be approximately 1000 characters" in data["detail"]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_article_not_found(self, async_client: httpx.AsyncClient):
        """Test creating annotation for non-existent article."""
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        response = await async_client.post(
            "/api/articles/99999/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "Article not found" in data["detail"]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_not_huntable(self, async_client: httpx.AsyncClient):
        """Test creating 'not_huntable' annotation."""
        # Get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create 'not_huntable' annotation
        annotation_data = {
            "annotation_type": "not_huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["annotation"]["annotation_type"] == "not_huntable"

    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="DEPRECATED: CMD observables features are deprecated")
    async def test_create_cmd_annotation(self, async_client: httpx.AsyncClient):
        """Test creating a CMD observable annotation.
        
        DEPRECATED: CMD observables features are deprecated.
        """
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        command_text = "cmd.exe /c whoami"
        annotation_data = {
            "annotation_type": "CMD",
            "selected_text": command_text,
            "start_position": 0,
            "end_position": len(command_text),
            "usage": "train"  # Required for observable annotations
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        # CMD annotations may fail validation - check for either success or expected error
        if response.status_code == 400:
            # Check if it's a validation error we expect
            data = response.json()
            error_detail = data.get("detail", "")
            # If it's about usage or other validation, that's acceptable
            assert "usage" in error_detail.lower() or "required" in error_detail.lower() or "annotation" in error_detail.lower()
        else:
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["annotation"]["annotation_type"] == "CMD"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_annotation_invalid_type(self, async_client: httpx.AsyncClient):
        """Test rejecting unsupported annotation types."""
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        annotation_data = {
            "annotation_type": "invalid_type",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        assert "Unsupported annotation type" in response.json()["detail"]


class TestGetArticleAnnotations:
    """Test getting annotations for an article."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotations_success(self, async_client: httpx.AsyncClient):
        """Test getting annotations for an article."""
        # Get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Get annotations
        response = await async_client.get(f"/api/articles/{article_id}/annotations")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["article_id"] == article_id
        assert "annotations" in data
        assert "count" in data
        assert isinstance(data["annotations"], list)
        assert data["count"] == len(data["annotations"])
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotations_article_not_found(self, async_client: httpx.AsyncClient):
        """Test getting annotations for non-existent article."""
        response = await async_client.get("/api/articles/99999/annotations")
        
        assert response.status_code == 404
        data = response.json()
        assert "Article not found" in data["detail"]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotations_empty_list(self, async_client: httpx.AsyncClient):
        """Test getting annotations when article has none."""
        # Get an article without annotations
        articles_response = await async_client.get("/api/articles?limit=100")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        # Find an article without annotations
        article_id = None
        for article in articles_data["articles"]:
            annotation_count = article.get("article_metadata", {}).get("annotation_count", 0)
            if annotation_count == 0:
                article_id = article["id"]
                break
        
        if article_id is None:
            pytest.skip("No articles without annotations found")
        
        # Get annotations
        response = await async_client.get(f"/api/articles/{article_id}/annotations")
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert len(data["annotations"]) == 0


class TestGetAnnotation:
    """Test getting a specific annotation."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotation_success(self, async_client: httpx.AsyncClient):
        """Test getting an existing annotation."""
        # First create an annotation
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create annotation
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        create_response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create annotation for testing")
        
        annotation_id = create_response.json()["annotation"]["id"]
        
        # Get the annotation
        response = await async_client.get(f"/api/annotations/{annotation_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "annotation" in data
        assert data["annotation"]["id"] == annotation_id
        assert data["annotation"]["article_id"] == article_id
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotation_not_found(self, async_client: httpx.AsyncClient):
        """Test getting non-existent annotation."""
        response = await async_client.get("/api/annotations/99999")
        
        assert response.status_code == 404
        data = response.json()
        assert "Annotation not found" in data["detail"]


class TestUpdateAnnotation:
    """Test updating an annotation."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_update_annotation_success(self, async_client: httpx.AsyncClient):
        """Test successfully updating an annotation."""
        # First create an annotation
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create annotation
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        create_response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create annotation for testing")
        
        annotation_id = create_response.json()["annotation"]["id"]
        
        # Update the annotation
        update_data = {
            "annotation_type": "not_huntable",
            "selected_text": "y" * 1000  # Update text
        }
        
        response = await async_client.put(
            f"/api/annotations/{annotation_id}",
            json=update_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "annotation" in data
        assert data["message"] == "Annotation updated successfully"
        assert data["annotation"]["annotation_type"] == "not_huntable"
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_update_annotation_not_found(self, async_client: httpx.AsyncClient):
        """Test updating non-existent annotation."""
        update_data = {
            "annotation_type": "huntable"
        }
        
        response = await async_client.put(
            "/api/annotations/99999",
            json=update_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "Annotation not found" in data["detail"]


class TestDeleteAnnotation:
    """Test deleting an annotation."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_annotation_by_id_success(self, async_client: httpx.AsyncClient):
        """Test deleting an annotation by ID."""
        # First create an annotation
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create annotation
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        create_response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create annotation for testing")
        
        annotation_id = create_response.json()["annotation"]["id"]
        
        # Delete the annotation
        response = await async_client.delete(f"/api/annotations/{annotation_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["message"] == "Annotation deleted successfully"
        
        # Verify it's deleted
        get_response = await async_client.get(f"/api/annotations/{annotation_id}")
        assert get_response.status_code == 404
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_annotation_by_article_id_success(self, async_client: httpx.AsyncClient):
        """Test deleting an annotation via article endpoint."""
        # First create an annotation
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # Create annotation
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        create_response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create annotation for testing")
        
        annotation_id = create_response.json()["annotation"]["id"]
        
        # Delete via article endpoint
        response = await async_client.delete(
            f"/api/articles/{article_id}/annotations/{annotation_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["message"] == "Annotation deleted successfully"
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_annotation_not_found(self, async_client: httpx.AsyncClient):
        """Test deleting non-existent annotation."""
        response = await async_client.delete("/api/annotations/99999")
        
        assert response.status_code == 404
        data = response.json()
        assert "Annotation not found" in data["detail"]
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_annotation_article_not_found(self, async_client: httpx.AsyncClient):
        """Test deleting annotation with invalid article ID."""
        response = await async_client.delete("/api/articles/99999/annotations/1")
        
        assert response.status_code == 404
        data = response.json()
        assert "Article not found" in data["detail"]


class TestAnnotationCRUDWorkflow:
    """Test complete CRUD workflow."""
    
    @pytest.mark.api
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_annotation_lifecycle(self, async_client: httpx.AsyncClient):
        """Test complete annotation lifecycle: create, read, update, delete."""
        # Get an article
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available for testing")
        
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available for testing")
        
        article_id = articles_data["articles"][0]["id"]
        
        # 1. CREATE
        annotation_data = {
            "annotation_type": "huntable",
            "selected_text": "x" * 1000,
            "start_position": 0,
            "end_position": 1000
        }
        
        create_response = await async_client.post(
            f"/api/articles/{article_id}/annotations",
            json=annotation_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert create_response.status_code == 200
        annotation_id = create_response.json()["annotation"]["id"]
        
        # 2. READ - Get by ID
        get_response = await async_client.get(f"/api/annotations/{annotation_id}")
        assert get_response.status_code == 200
        assert get_response.json()["annotation"]["id"] == annotation_id
        
        # 3. READ - Get by article
        get_article_response = await async_client.get(f"/api/articles/{article_id}/annotations")
        assert get_article_response.status_code == 200
        assert annotation_id in [a["id"] for a in get_article_response.json()["annotations"]]
        
        # 4. UPDATE
        update_data = {
            "annotation_type": "not_huntable"
        }
        
        update_response = await async_client.put(
            f"/api/annotations/{annotation_id}",
            json=update_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert update_response.status_code == 200
        assert update_response.json()["annotation"]["annotation_type"] == "not_huntable"
        
        # 5. DELETE
        delete_response = await async_client.delete(f"/api/annotations/{annotation_id}")
        assert delete_response.status_code == 200
        
        # 6. VERIFY DELETION
        verify_response = await async_client.get(f"/api/annotations/{annotation_id}")
        assert verify_response.status_code == 404


class TestAnnotationStats:
    """Test annotation statistics endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotation_stats(self, async_client: httpx.AsyncClient):
        """Test getting annotation statistics."""
        response = await async_client.get("/api/annotations/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stats" in data


class TestAnnotationTypesEndpoint:
    """Test annotation types endpoint."""
    
    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_annotation_types(self, async_client: httpx.AsyncClient):
        """Test getting annotation types."""
        response = await async_client.get("/api/annotations/types")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "modes" in data
        # Check that observables includes "cmd" (lowercase, not "CMD")
        assert "observables" in data["modes"]
        assert "cmd" in data["modes"]["observables"]

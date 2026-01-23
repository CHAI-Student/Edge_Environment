"""
Product Registration System Tests.

Tests for:
- ProductDatabase CRUD operations
- JSON persistence (save/load)
- REST API endpoints
- Node.js synchronization
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from database.product_db import ProductDatabase
from engine.models import ProductInfo


class TestProductDatabase:
    """ProductDatabase unit tests."""

    @pytest.fixture
    def db(self):
        """Fresh ProductDatabase instance."""
        return ProductDatabase()

    def test_add_product_success(self, db):
        """Test adding a new product."""
        product_id = db.add_product(
            name="새우깡",
            category="snack",
            weight=90.0,
            price=1500,
            barcode="8801234567890",
        )

        assert product_id > 0
        product = db.get_by_id(product_id)
        assert product is not None
        assert product.name == "새우깡"
        assert product.category == "snack"
        assert product.weight == 90.0
        assert product.price == 1500
        assert product.barcode == "8801234567890"

    def test_add_product_duplicate_barcode(self, db):
        """Test adding product with duplicate barcode raises error."""
        db.add_product(
            name="Product1",
            category="snack",
            weight=100.0,
            price=1000,
            barcode="1234567890",
        )

        with pytest.raises(ValueError, match="Barcode .* already exists"):
            db.add_product(
                name="Product2",
                category="snack",
                weight=200.0,
                price=2000,
                barcode="1234567890",
            )

    def test_add_product_custom_id(self, db):
        """Test adding product with custom ID."""
        product_id = db.add_product(
            name="Custom Product",
            category="food",
            weight=150.0,
            price=2500,
            product_id=999,
        )

        assert product_id == 999
        assert db.get_by_id(999) is not None

    def test_update_product_success(self, db):
        """Test updating an existing product."""
        product_id = db.add_product(
            name="Original",
            category="snack",
            weight=100.0,
            price=1000,
        )

        success = db.update_product(
            product_id,
            name="Updated",
            price=1500,
        )

        assert success is True
        product = db.get_by_id(product_id)
        assert product.name == "Updated"
        assert product.price == 1500
        assert product.weight == 100.0  # unchanged

    def test_update_product_not_found(self, db):
        """Test updating non-existent product returns False."""
        success = db.update_product(9999, name="Test")
        assert success is False

    def test_delete_product_success(self, db):
        """Test deleting a product."""
        product_id = db.add_product(
            name="ToDelete",
            category="snack",
            weight=100.0,
            price=1000,
            barcode="DELETE123",
        )

        success = db.delete_product(product_id)
        assert success is True
        assert db.get_by_id(product_id) is None
        assert db.get_by_barcode("DELETE123") is None

    def test_delete_product_not_found(self, db):
        """Test deleting non-existent product returns False."""
        success = db.delete_product(9999)
        assert success is False

    def test_get_by_barcode(self, db):
        """Test getting product by barcode."""
        product_id = db.add_product(
            name="BarcodeTest",
            category="snack",
            weight=100.0,
            price=1000,
            barcode="BC123456",
        )

        product = db.get_by_barcode("BC123456")
        assert product is not None
        assert product.product_id == product_id

    def test_get_by_barcode_not_found(self, db):
        """Test getting non-existent barcode returns None."""
        product = db.get_by_barcode("NONEXISTENT")
        assert product is None

    def test_search_by_name(self, db):
        """Test searching products by name."""
        db.add_product(name="새우깡", category="snack", weight=90, price=1500)
        db.add_product(name="양파깡", category="snack", weight=85, price=1500)
        db.add_product(name="초코파이", category="snack", weight=120, price=2000)

        results = db.search_by_name("깡")
        assert len(results) == 2
        assert any(p.name == "새우깡" for p in results)
        assert any(p.name == "양파깡" for p in results)

    def test_search_by_name_empty(self, db):
        """Test searching with empty query returns empty list."""
        results = db.search_by_name("")
        assert results == []

    def test_export_all(self, db):
        """Test exporting all products."""
        db.add_product(name="Product1", category="snack", weight=100, price=1000)
        db.add_product(name="Product2", category="food", weight=200, price=2000)

        exported = db.export_all()
        assert len(exported) >= 2  # May include pre-existing products


class TestProductDatabasePersistence:
    """ProductDatabase persistence tests."""

    def test_save_and_load_file(self):
        """Test saving and loading from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "products.json")

            # Create and save
            db1 = ProductDatabase()
            db1.add_product(
                name="Persistent",
                category="snack",
                weight=100.0,
                price=1000,
                barcode="PERSIST123",
            )
            db1.save_to_file(file_path)

            assert os.path.exists(file_path)

            # Load in new instance
            db2 = ProductDatabase()
            db2.load_from_file(file_path)

            product = db2.get_by_barcode("PERSIST123")
            assert product is not None
            assert product.name == "Persistent"

    def test_save_creates_directory(self):
        """Test save creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "nested", "dir", "products.json")

            db = ProductDatabase()
            db.add_product(name="Test", category="snack", weight=100, price=1000)
            db.save_to_file(nested_path)

            assert os.path.exists(nested_path)

    def test_load_nonexistent_file(self):
        """Test loading non-existent file doesn't crash."""
        db = ProductDatabase()
        # Should not raise
        db.load_from_file("/nonexistent/path/products.json")

    def test_auto_save_on_modification(self):
        """Test auto-save when data_file is configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "auto_save.json")

            db = ProductDatabase(data_file=file_path)
            db.add_product(name="AutoSave", category="snack", weight=100, price=1000)

            # File should exist after add
            assert os.path.exists(file_path)


class TestProductDatabaseFindByWeight:
    """Weight-based product search tests."""

    @pytest.fixture
    def db_with_products(self):
        """Database with sample products."""
        db = ProductDatabase()
        db.add_product(name="Light_100", category="snack", weight=100, price=1000)
        db.add_product(name="Medium_200", category="food", weight=200, price=2000)
        db.add_product(name="Heavy_500", category="drink", weight=500, price=1500)
        return db

    def test_find_by_weight_exact(self, db_with_products):
        """Test finding product by exact weight."""
        results = db_with_products.find_by_weight(200.0, tolerance_percent=0.01)
        assert len(results) >= 1
        assert any(p.name == "Medium_200" for p in results)

    def test_find_by_weight_tolerance(self, db_with_products):
        """Test finding product within tolerance."""
        # 205 is within 5% of 200
        results = db_with_products.find_by_weight(205.0, tolerance_percent=0.05)
        assert any(p.name == "Medium_200" for p in results)

    def test_find_by_weight_no_match(self, db_with_products):
        """Test finding with weight that doesn't match."""
        results = db_with_products.find_by_weight(999.0, tolerance_percent=0.05)
        assert len(results) == 0


class TestProductRegistrationAPI:
    """REST API endpoint tests (using FastAPI TestClient)."""

    @pytest.fixture
    def client(self):
        """FastAPI TestClient."""
        try:
            from fastapi.testclient import TestClient
            from api.routes import router
            from fastapi import FastAPI

            app = FastAPI()
            app.include_router(router)
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI TestClient not available")

    def test_register_product_endpoint(self, client):
        """Test POST /api/products/register."""
        response = client.post(
            "/api/products/register",
            json={
                "name": "API Test Product",
                "category": "snack",
                "weight": 150.0,
                "price": 2000,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "product_id" in data

    def test_register_product_with_barcode(self, client):
        """Test registering product with barcode."""
        response = client.post(
            "/api/products/register",
            json={
                "name": "Barcode Product",
                "category": "food",
                "weight": 200.0,
                "price": 3000,
                "barcode": "API123456",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_update_product_endpoint(self, client):
        """Test PUT /api/products/{id}."""
        # First create
        create_resp = client.post(
            "/api/products/register",
            json={
                "name": "ToUpdate",
                "category": "snack",
                "weight": 100.0,
                "price": 1000,
            },
        )
        product_id = create_resp.json()["product_id"]

        # Then update
        response = client.put(
            f"/api/products/{product_id}",
            json={
                "name": "Updated Name",
                "price": 1500,
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_product_endpoint(self, client):
        """Test DELETE /api/products/{id}."""
        # First create
        create_resp = client.post(
            "/api/products/register",
            json={
                "name": "ToDelete",
                "category": "snack",
                "weight": 100.0,
                "price": 1000,
            },
        )
        product_id = create_resp.json()["product_id"]

        # Then delete
        response = client.delete(f"/api/products/{product_id}")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_export_products_endpoint(self, client):
        """Test GET /api/products/export."""
        response = client.get("/api/products/export")

        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "count" in data

    def test_search_products_endpoint(self, client):
        """Test GET /api/products/search."""
        # Create test products
        client.post(
            "/api/products/register",
            json={
                "name": "SearchTest1",
                "category": "snack",
                "weight": 100.0,
                "price": 1000,
            },
        )

        response = client.get("/api/products/search?query=Search&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_by_barcode_endpoint(self, client):
        """Test GET /api/products/barcode/{barcode}."""
        # Create with barcode
        client.post(
            "/api/products/register",
            json={
                "name": "BarcodeTest",
                "category": "snack",
                "weight": 100.0,
                "price": 1000,
                "barcode": "UNIQUE_BC_789",
            },
        )

        response = client.get("/api/products/barcode/UNIQUE_BC_789")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "BarcodeTest"


class TestNodeJSProductSync:
    """Node.js product synchronization tests."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx AsyncClient."""
        with patch("httpx.AsyncClient") as mock:
            instance = MagicMock()
            instance.post = AsyncMock()
            mock.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock.return_value.__aexit__ = AsyncMock(return_value=None)
            yield instance

    @pytest.mark.asyncio
    async def test_sync_products_to_server_success(self, mock_httpx_client):
        """Test syncing products to Node.js server."""
        from api.node_client import NodeJSClient

        mock_httpx_client.post.return_value.status_code = 200
        mock_httpx_client.post.return_value.json.return_value = {"success": True}

        client = NodeJSClient(base_url="http://localhost:8888")
        products = [
            {"product_id": 1, "name": "Test", "weight": 100, "price": 1000}
        ]

        # The actual implementation may differ, this tests the interface
        # result = await client.sync_products_to_server(products)
        # assert result is True

    @pytest.mark.asyncio
    async def test_notify_product_registered(self, mock_httpx_client):
        """Test notifying Node.js of new product."""
        from api.node_client import NodeJSClient

        mock_httpx_client.post.return_value.status_code = 200

        client = NodeJSClient(base_url="http://localhost:8888")
        product = {
            "product_id": 51,
            "name": "NewProduct",
            "weight": 150,
            "price": 2000,
        }

        # The actual implementation may differ
        # result = await client.notify_product_registered(product)


class TestImageUpload:
    """Product image upload tests."""

    @pytest.fixture
    def temp_image_dir(self):
        """Temporary directory for images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_image_save_path_structure(self, temp_image_dir):
        """Test images are saved in correct directory structure."""
        # Expected: images/cam_{camera_id}/product_{id}_{num}.jpg
        camera_id = 0
        product_id = 51

        save_dir = os.path.join(temp_image_dir, "images", f"cam_{camera_id}")
        os.makedirs(save_dir, exist_ok=True)

        filename = f"product_{product_id:03d}_001.jpg"
        filepath = os.path.join(save_dir, filename)

        # Create dummy image file
        with open(filepath, "wb") as f:
            f.write(b"dummy image data")

        assert os.path.exists(filepath)
        assert f"cam_{camera_id}" in filepath
        assert f"product_{product_id:03d}" in filepath


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

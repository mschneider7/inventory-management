"""
Tests for tasks and purchase order API endpoints.
"""
import pytest


class TestTasksEndpoints:
    """Test suite for task endpoints."""

    def _create(self, client, **overrides):
        payload = {"title": "Review stock", "priority": "high", "dueDate": "2025-10-08"}
        payload.update(overrides)
        return client.post("/api/tasks", json=payload)

    def test_get_tasks_empty(self, client):
        """Test that no tasks exist initially."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task."""
        response = self._create(client)
        assert response.status_code == 201

        task = response.json()
        assert task["title"] == "Review stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"
        # Ids must be strings so they cannot collide with the client's integer mock-task ids
        assert isinstance(task["id"], str)

    def test_get_tasks_newest_first(self, client):
        """Test that tasks are listed newest first."""
        self._create(client, title="first")
        self._create(client, title="second")

        titles = [t["title"] for t in client.get("/api/tasks").json()]
        assert titles == ["second", "first"]

    def test_create_task_invalid_priority(self, client):
        """Test that an unknown priority is rejected."""
        assert self._create(client, priority="urgent").status_code == 422

    def test_create_task_empty_title(self, client):
        """Test that an empty title is rejected."""
        assert self._create(client, title="").status_code == 422

    def test_toggle_task(self, client):
        """Test toggling a task back and forth."""
        task_id = self._create(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/task-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_task(self, client):
        """Test deleting a task."""
        task_id = self._create(client).json()["id"]

        assert client.delete(f"/api/tasks/{task_id}").status_code == 200
        assert client.get("/api/tasks").json() == []

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/task-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def _backlog_id(self, client):
        return client.get("/api/backlog").json()[0]["id"]

    def _payload(self, backlog_id, **overrides):
        payload = {
            "backlog_item_id": backlog_id,
            "supplier_name": "Acme Supply",
            "quantity": 350,
            "unit_cost": 12.5,
            "expected_delivery_date": "2025-11-15",
            "notes": "Rush",
        }
        payload.update(overrides)
        return payload

    def test_create_purchase_order(self, client):
        """Test creating a purchase order for a backlog item."""
        backlog_id = self._backlog_id(client)
        response = client.post("/api/purchase-orders", json=self._payload(backlog_id))
        assert response.status_code == 201

        po = response.json()
        assert po["backlog_item_id"] == backlog_id
        assert po["supplier_name"] == "Acme Supply"
        assert po["quantity"] == 350
        assert po["status"] == "Pending"
        assert po["notes"] == "Rush"
        assert "id" in po and "created_date" in po

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test fetching a purchase order by its backlog item id."""
        backlog_id = self._backlog_id(client)
        created = client.post("/api/purchase-orders", json=self._payload(backlog_id)).json()

        response = client.get(f"/api/purchase-orders/{backlog_id}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_backlog_flags_purchase_order(self, client):
        """Test that /api/backlog reports has_purchase_order after creation."""
        backlog_id = self._backlog_id(client)
        client.post("/api/purchase-orders", json=self._payload(backlog_id))

        item = next(b for b in client.get("/api/backlog").json() if b["id"] == backlog_id)
        assert item["has_purchase_order"] is True

    def test_create_duplicate_purchase_order(self, client):
        """Test that a backlog item can only have one purchase order."""
        backlog_id = self._backlog_id(client)
        client.post("/api/purchase-orders", json=self._payload(backlog_id))

        response = client.post("/api/purchase-orders", json=self._payload(backlog_id))
        assert response.status_code == 409

    def test_create_purchase_order_unknown_backlog_item(self, client):
        """Test creating a purchase order for a nonexistent backlog item."""
        response = client.post("/api/purchase-orders", json=self._payload("nonexistent-999"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("field,value", [("quantity", 0), ("quantity", -5), ("unit_cost", -1)])
    def test_create_purchase_order_invalid_numbers(self, client, field, value):
        """Test that non-positive quantity and negative cost are rejected."""
        payload = self._payload(self._backlog_id(client), **{field: value})
        assert client.post("/api/purchase-orders", json=payload).status_code == 422

    def test_get_nonexistent_purchase_order(self, client):
        """Test fetching a purchase order that doesn't exist."""
        response = client.get("/api/purchase-orders/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

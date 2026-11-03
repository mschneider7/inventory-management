"""
Tests for restocking API endpoints.
"""
from datetime import datetime, timedelta

import pytest


class TestRestockingEndpoints:
    """Test suite for restocking recommendations and submitted orders."""

    def _forecasts(self, client):
        return {f["item_sku"]: f for f in client.get("/api/demand").json()}

    def test_demand_forecasts_include_pricing_fields(self, client):
        """Test that forecasts carry the cost, supplier and lead time fields."""
        for forecast in client.get("/api/demand").json():
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert isinstance(forecast["supplier"], str)
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["lead_time_days"] > 0

    def test_recommendations_zero_budget(self, client):
        """Test that a zero budget recommends nothing."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0
        assert data["max_lead_time_days"] == 0

    def test_recommendations_never_exceed_budget(self, client):
        """Test that total cost stays within the budget at every level."""
        for budget in [100, 1000, 5000, 10000, 50000, 1000000]:
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert abs(data["total_cost"] + data["remaining_budget"] - budget) < 0.01

    def test_recommendations_exclude_decreasing_and_flat_demand(self, client):
        """Test that only items with growing demand are recommended."""
        forecasts = self._forecasts(client)
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert len(data["items"]) > 0

        for item in data["items"]:
            forecast = forecasts[item["sku"]]
            assert forecast["trend"] != "decreasing"
            assert forecast["forecasted_demand"] > forecast["current_demand"]

    def test_recommendations_quantity_and_line_cost(self, client):
        """Test that quantity equals the demand gap and line cost is consistent."""
        forecasts = self._forecasts(client)
        data = client.get("/api/restocking/recommendations?budget=1000000").json()

        for item in data["items"]:
            forecast = forecasts[item["sku"]]
            gap = forecast["forecasted_demand"] - forecast["current_demand"]
            assert item["quantity"] == gap
            assert abs(item["line_cost"] - item["quantity"] * item["unit_cost"]) < 0.01

    def test_recommendations_ordered_by_demand_gap(self, client):
        """Test that larger demand gaps come first."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        quantities = [item["quantity"] for item in data["items"]]
        assert quantities == sorted(quantities, reverse=True)

    def test_recommendations_skip_unaffordable_but_fill_with_cheaper(self, client):
        """Test that an item too expensive for the budget does not block cheaper ones."""
        full = client.get("/api/restocking/recommendations?budget=1000000").json()
        # Budget one cent short of the first (largest-gap) item's line cost
        first = full["items"][0]
        data = client.get(
            f"/api/restocking/recommendations?budget={first['line_cost'] - 0.01}"
        ).json()

        assert first["sku"] not in [i["sku"] for i in data["items"]]
        assert data["total_cost"] <= first["line_cost"] - 0.01

    def test_recommendations_max_lead_time(self, client):
        """Test that the reported max lead time matches the recommended items."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert data["max_lead_time_days"] == max(i["lead_time_days"] for i in data["items"])

    def test_recommendations_negative_budget_rejected(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_create_restock_order(self, client):
        """Test submitting an order computes totals and lead time server-side."""
        forecasts = self._forecasts(client)
        payload = {"items": [
            {"sku": "GSK-203", "quantity": 100},
            {"sku": "WDG-001", "quantity": 10},
        ]}

        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        expected_total = (
            100 * forecasts["GSK-203"]["unit_cost"] + 10 * forecasts["WDG-001"]["unit_cost"]
        )
        assert abs(order["total_cost"] - expected_total) < 0.01
        assert order["lead_time_days"] == max(
            forecasts["GSK-203"]["lead_time_days"], forecasts["WDG-001"]["lead_time_days"]
        )
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert len(order["items"]) == 2

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery - order_date == timedelta(days=order["lead_time_days"])

    def test_create_restock_order_empty_rejected(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_create_restock_order_unknown_sku_rejected(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post(
            "/api/restocking/orders", json={"items": [{"sku": "NOPE-000", "quantity": 1}]}
        )
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_create_restock_order_invalid_quantity_rejected(self, client, quantity):
        """Test that zero or negative quantities fail validation."""
        response = client.post(
            "/api/restocking/orders", json={"items": [{"sku": "GSK-203", "quantity": quantity}]}
        )
        assert response.status_code == 422

    def test_client_supplied_prices_are_ignored(self, client):
        """Test that prices sent by the client cannot change the order total."""
        forecasts = self._forecasts(client)
        response = client.post(
            "/api/restocking/orders",
            json={"items": [{"sku": "GSK-203", "quantity": 10, "unit_cost": 0.01}]},
        )
        assert response.status_code == 201
        expected = 10 * forecasts["GSK-203"]["unit_cost"]
        assert abs(response.json()["total_cost"] - expected) < 0.01

    def test_get_submitted_orders_empty(self, client):
        """Test that there are no submitted orders initially."""
        response = client.get("/api/submitted-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_submitted_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        first = client.post(
            "/api/restocking/orders", json={"items": [{"sku": "GSK-203", "quantity": 1}]}
        ).json()
        second = client.post(
            "/api/restocking/orders", json={"items": [{"sku": "FLT-405", "quantity": 1}]}
        ).json()

        data = client.get("/api/submitted-orders").json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]
        assert first["order_number"] != second["order_number"]

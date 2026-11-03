"""
Tests for reports API endpoints.
"""
import pytest


class TestReportsEndpoints:
    """Test suite for quarterly and monthly report endpoints."""

    def test_quarterly_structure(self, client):
        """Test quarterly report rows have the expected fields and types."""
        response = client.get("/api/reports/quarterly")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for row in data:
            assert row["quarter"].startswith("Q")
            assert isinstance(row["total_orders"], int)
            assert isinstance(row["total_revenue"], (int, float))
            assert 0 <= row["fulfillment_rate"] <= 100

    def test_quarterly_sorted(self, client):
        """Test quarters are returned in order."""
        quarters = [r["quarter"] for r in client.get("/api/reports/quarterly").json()]
        assert quarters == sorted(quarters)

    def test_monthly_structure_and_sorted(self, client):
        """Test monthly rows have the expected fields and are sorted."""
        data = client.get("/api/reports/monthly-trends").json()
        assert len(data) > 0
        for row in data:
            assert len(row["month"]) == 7
            assert row["order_count"] > 0
        months = [r["month"] for r in data]
        assert months == sorted(months)

    def test_reports_totals_match_orders(self, client):
        """Test report totals agree with the raw orders endpoint."""
        orders = client.get("/api/orders").json()
        quarterly = client.get("/api/reports/quarterly").json()
        monthly = client.get("/api/reports/monthly-trends").json()

        assert sum(r["total_orders"] for r in quarterly) == len(orders)
        assert sum(r["order_count"] for r in monthly) == len(orders)
        assert abs(sum(r["revenue"] for r in monthly) - sum(o["total_value"] for o in orders)) < 0.01

    def test_monthly_warehouse_filter(self, client):
        """Test the warehouse filter narrows the monthly trends."""
        orders = client.get("/api/orders?warehouse=Tokyo").json()
        monthly = client.get("/api/reports/monthly-trends?warehouse=Tokyo").json()
        assert sum(r["order_count"] for r in monthly) == len(orders)

    def test_quarterly_category_and_status_filters(self, client):
        """Test category and status filters apply to the quarterly report."""
        orders = client.get("/api/orders?category=Sensors&status=Delivered").json()
        quarterly = client.get("/api/reports/quarterly?category=Sensors&status=Delivered").json()
        assert sum(r["total_orders"] for r in quarterly) == len(orders)
        # Only delivered orders are included, so every bucket is fully fulfilled
        assert all(r["fulfillment_rate"] == 100 for r in quarterly)

    def test_month_filter(self, client):
        """Test a month filter limits both reports to that month."""
        orders = client.get("/api/orders?month=2025-03").json()
        monthly = client.get("/api/reports/monthly-trends?month=2025-03").json()
        quarterly = client.get("/api/reports/quarterly?month=2025-03").json()

        assert [r["month"] for r in monthly] == (["2025-03"] if orders else [])
        assert sum(r["total_orders"] for r in quarterly) == len(orders)

    def test_quarter_filter(self, client):
        """Test a quarter filter limits the reports to that quarter."""
        quarterly = client.get("/api/reports/quarterly?month=Q2-2025").json()
        assert all(r["quarter"] == "Q2-2025" for r in quarterly)

    def test_filter_with_no_matches(self, client):
        """Test filters that match nothing return empty lists, not errors."""
        assert client.get("/api/reports/quarterly?month=2030-01").json() == []
        assert client.get("/api/reports/monthly-trends?month=2030-01").json() == []

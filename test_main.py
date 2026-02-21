"""
test_main.py
============
Unit tests for the Coupons Management API.

Covers:
- CRUD operations for coupons
- Cart-wise coupon applicability and discount computation
- Product-wise coupon applicability and discount computation
- BxGy coupon applicability, repetition limits, and discount computation
- Error cases: coupon not found, conditions not met, expired coupon
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from main import app, get_db

# ── In-memory SQLite for tests ──
TEST_DATABASE_URL = "sqlite:///./test_coupons.db"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    """Create fresh tables before each test and drop them after."""
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


client = TestClient(app)


# ══════════════════════════════════════════════
#  Helper functions
# ══════════════════════════════════════════════

def create_cart_wise_coupon(threshold=100, discount=10):
    return client.post("/coupons", json={
        "type": "cart-wise",
        "details": {"threshold": threshold, "discount": discount}
    })


def create_product_wise_coupon(product_id=1, discount=20):
    return client.post("/coupons", json={
        "type": "product-wise",
        "details": {"product_id": product_id, "discount": discount}
    })


def create_bxgy_coupon(buy_products=None, get_products=None, repition_limit=2):
    if buy_products is None:
        buy_products = [{"product_id": 1, "quantity": 3}, {"product_id": 2, "quantity": 3}]
    if get_products is None:
        get_products = [{"product_id": 3, "quantity": 1}]
    return client.post("/coupons", json={
        "type": "bxgy",
        "details": {
            "buy_products": buy_products,
            "get_products": get_products,
            "repition_limit": repition_limit
        }
    })


SAMPLE_CART = {
    "cart": {
        "items": [
            {"product_id": 1, "quantity": 6, "price": 50},
            {"product_id": 2, "quantity": 3, "price": 30},
            {"product_id": 3, "quantity": 2, "price": 25}
        ]
    }
}


# ══════════════════════════════════════════════
#  CRUD Tests
# ══════════════════════════════════════════════

class TestCouponCRUD:

    def test_create_cart_wise_coupon(self):
        resp = create_cart_wise_coupon()
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "cart-wise"
        assert body["details"]["threshold"] == 100
        assert body["details"]["discount"] == 10
        assert body["is_active"] is True
        assert "id" in body

    def test_create_product_wise_coupon(self):
        resp = create_product_wise_coupon()
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "product-wise"
        assert body["details"]["product_id"] == 1

    def test_create_bxgy_coupon(self):
        resp = create_bxgy_coupon()
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "bxgy"
        assert body["details"]["repition_limit"] == 2

    def test_get_all_coupons(self):
        create_cart_wise_coupon()
        create_product_wise_coupon()
        resp = client.get("/coupons")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_coupon_by_id(self):
        created = create_cart_wise_coupon().json()
        resp = client.get(f"/coupons/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_coupon_not_found(self):
        resp = client.get("/coupons/9999")
        assert resp.status_code == 404

    def test_update_coupon(self):
        created = create_cart_wise_coupon().json()
        resp = client.put(f"/coupons/{created['id']}", json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_delete_coupon(self):
        created = create_cart_wise_coupon().json()
        resp = client.delete(f"/coupons/{created['id']}")
        assert resp.status_code == 204
        resp = client.get(f"/coupons/{created['id']}")
        assert resp.status_code == 404

    def test_delete_coupon_not_found(self):
        resp = client.delete("/coupons/9999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════
#  Validation Tests
# ══════════════════════════════════════════════

class TestValidation:

    def test_invalid_coupon_type(self):
        resp = client.post("/coupons", json={
            "type": "super-sale",
            "details": {}
        })
        assert resp.status_code == 422

    def test_cart_wise_negative_threshold(self):
        resp = client.post("/coupons", json={
            "type": "cart-wise",
            "details": {"threshold": -50, "discount": 10}
        })
        assert resp.status_code == 422

    def test_product_wise_discount_over_100(self):
        resp = client.post("/coupons", json={
            "type": "product-wise",
            "details": {"product_id": 1, "discount": 110}
        })
        assert resp.status_code == 422

    def test_bxgy_empty_buy_products(self):
        resp = client.post("/coupons", json={
            "type": "bxgy",
            "details": {
                "buy_products": [],
                "get_products": [{"product_id": 3, "quantity": 1}],
                "repition_limit": 1
            }
        })
        assert resp.status_code == 422


# ══════════════════════════════════════════════
#  Applicable Coupons Tests
# ══════════════════════════════════════════════

class TestApplicableCoupons:

    def test_cart_wise_applicable(self):
        """Cart total = 6*50 + 3*30 + 2*25 = 300+90+50 = 440 > 100, so applicable"""
        create_cart_wise_coupon(threshold=100, discount=10)
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.status_code == 200
        coupons = resp.json()["applicable_coupons"]
        assert len(coupons) == 1
        assert coupons[0]["type"] == "cart-wise"
        assert coupons[0]["discount"] == 44.0  # 10% of 440

    def test_cart_wise_not_applicable_below_threshold(self):
        """Cart total 440 >= threshold 500, so NOT applicable"""
        create_cart_wise_coupon(threshold=500, discount=10)
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.status_code == 200
        assert resp.json()["applicable_coupons"] == []

    def test_product_wise_applicable(self):
        """Product 1 is in the cart with quantity 6 at price 50"""
        create_product_wise_coupon(product_id=1, discount=20)
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.status_code == 200
        coupons = resp.json()["applicable_coupons"]
        assert len(coupons) == 1
        assert coupons[0]["discount"] == 60.0  # 20% of 6*50=300

    def test_product_wise_not_applicable(self):
        """Product 99 is not in the cart"""
        create_product_wise_coupon(product_id=99, discount=20)
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.json()["applicable_coupons"] == []

    def test_bxgy_applicable(self):
        """
        Buy 3 of P1 or P2. Cart has 6 of P1 and 3 of P2.
        buy_qty_needed = 3+3 = 6. total buy units = 6+3 = 9. repetitions = 9 // 6 = 1 (but limit=2).
        Actually with buy_products=[{p1,q3},{p2,q3}], buy_qty_needed = 3+3 = 6.
        total buy units from p1=6, p2=3 => 9. repetitions = 9//6 = 1, capped at 2.
        So 1 repetition => 1 free unit of p3 (price=25). discount=25.
        """
        create_bxgy_coupon(
            buy_products=[{"product_id": 1, "quantity": 3}, {"product_id": 2, "quantity": 3}],
            get_products=[{"product_id": 3, "quantity": 1}],
            repition_limit=2
        )
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.status_code == 200
        coupons = resp.json()["applicable_coupons"]
        assert len(coupons) == 1
        assert coupons[0]["type"] == "bxgy"
        assert coupons[0]["discount"] == 25.0

    def test_inactive_coupon_excluded(self):
        """Inactive coupons should not appear in applicable-coupons"""
        created = create_cart_wise_coupon().json()
        client.put(f"/coupons/{created['id']}", json={"is_active": False})
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        assert resp.json()["applicable_coupons"] == []


# ══════════════════════════════════════════════
#  Apply Coupon Tests
# ══════════════════════════════════════════════

class TestApplyCoupon:

    def test_apply_cart_wise_coupon(self):
        """10% off on 440 = 44 discount, final = 396"""
        created = create_cart_wise_coupon(threshold=100, discount=10).json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 200
        cart = resp.json()["updated_cart"]
        assert cart["total_price"] == 440.0
        assert cart["total_discount"] == 44.0
        assert cart["final_price"] == 396.0

    def test_apply_product_wise_coupon(self):
        """20% off on product 1 (6*50=300) => discount=60, final=440-60=380"""
        created = create_product_wise_coupon(product_id=1, discount=20).json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 200
        cart = resp.json()["updated_cart"]
        assert cart["total_discount"] == 60.0
        assert cart["final_price"] == 380.0
        # Only product 1 item should have discount
        items = cart["items"]
        p1_item = next(i for i in items if i["product_id"] == 1)
        assert p1_item["total_discount"] == 60.0

    def test_apply_bxgy_coupon(self):
        """1 free unit of product 3 (price=25). discount=25"""
        created = create_bxgy_coupon().json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 200
        cart = resp.json()["updated_cart"]
        assert cart["total_discount"] == 25.0
        # Product 3 quantity should increase by 1
        p3_item = next(i for i in cart["items"] if i["product_id"] == 3)
        assert p3_item["quantity"] == 3  # 2 original + 1 free

    def test_apply_coupon_not_found(self):
        resp = client.post("/apply-coupon/9999", json=SAMPLE_CART)
        assert resp.status_code == 404

    def test_apply_inactive_coupon(self):
        created = create_cart_wise_coupon().json()
        client.put(f"/coupons/{created['id']}", json={"is_active": False})
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 400
        assert "not active" in resp.json()["detail"].lower()

    def test_apply_coupon_conditions_not_met(self):
        """Cart total is 440 but threshold is 500"""
        created = create_cart_wise_coupon(threshold=500, discount=10).json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 400

    def test_apply_expired_coupon(self):
        created = client.post("/coupons", json={
            "type": "cart-wise",
            "details": {"threshold": 100, "discount": 10},
            "expiration_date": "2020-01-01T00:00:00"
        }).json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════
#  BxGy Edge Cases
# ══════════════════════════════════════════════

class TestBxGyEdgeCases:

    def test_bxgy_repetition_limit_respected(self):
        """
        Cart: 6 of P1, threshold=3. With limit=1, only 1 repetition allowed.
        Discount = 1 * 1 * price_p3 * qty_get = 1 * 25 = 25
        """
        created = client.post("/coupons", json={
            "type": "bxgy",
            "details": {
                "buy_products": [{"product_id": 1, "quantity": 3}],
                "get_products": [{"product_id": 3, "quantity": 1}],
                "repition_limit": 1
            }
        }).json()
        resp = client.post(f"/apply-coupon/{created['id']}", json=SAMPLE_CART)
        assert resp.status_code == 200
        cart = resp.json()["updated_cart"]
        assert cart["total_discount"] == 25.0

    def test_bxgy_not_enough_buy_products(self):
        """
        Buy qty needed = 10, but cart only has 6 of P1. Not applicable.
        BxGy returns 0 discount — apply-coupon should succeed but with 0 discount.
        """
        created = client.post("/coupons", json={
            "type": "bxgy",
            "details": {
                "buy_products": [{"product_id": 1, "quantity": 10}],
                "get_products": [{"product_id": 3, "quantity": 1}],
                "repition_limit": 1
            }
        }).json()
        # applicable-coupons should not include this
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        applicable_ids = [c["coupon_id"] for c in resp.json()["applicable_coupons"]]
        assert created["id"] not in applicable_ids

    def test_bxgy_get_product_not_in_cart(self):
        """
        Free product (P99) is not in the cart at all. It should be added with qty=free_qty.
        But discount value = 0 since price is unknown.
        """
        created = client.post("/coupons", json={
            "type": "bxgy",
            "details": {
                "buy_products": [{"product_id": 1, "quantity": 3}],
                "get_products": [{"product_id": 99, "quantity": 1}],
                "repition_limit": 1
            }
        }).json()
        # Check applicable — discount=0 so it won't appear
        resp = client.post("/applicable-coupons", json=SAMPLE_CART)
        applicable_ids = [c["coupon_id"] for c in resp.json()["applicable_coupons"]]
        assert created["id"] not in applicable_ids

# Coupons Management API

A RESTful API to manage and apply discount coupons for an e-commerce platform, built with **FastAPI** and **SQLite**.

---

## 🚀 Tech Stack

| Layer        | Technology                    |
|--------------|-------------------------------|
| Framework    | FastAPI 0.110                 |
| Language     | Python 3.10+                  |
| Database     | SQLite (via SQLAlchemy ORM)   |
| Validation   | Pydantic v2                   |
| Testing      | Pytest + HTTPX TestClient     |
| Server       | Uvicorn                       |

---

## 📁 Project Structure

```
├── main.py            # FastAPI app & all route handlers
├── models.py          # SQLAlchemy ORM model
├── schemas.py         # Pydantic request/response models
├── coupon_engine.py   # Core discount computation logic
├── database.py        # DB session & engine setup
├── test_main.py       # Full unit test suite
├── requirements.txt   # Python dependencies
└── README.md
```

---

## ⚙️ Setup & Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the server

```bash
uvicorn main:app --reload
```

API will be available at: **http://127.0.0.1:8000**

Interactive Swagger UI: **http://127.0.0.1:8000/docs**

### 3. Run tests

```bash
pytest test_main.py -v
```

---

## 🔗 API Endpoints

| Method | Endpoint                   | Description                              |
|--------|----------------------------|------------------------------------------|
| POST   | `/coupons`                 | Create a new coupon                      |
| GET    | `/coupons`                 | Retrieve all coupons                     |
| GET    | `/coupons/{id}`            | Retrieve a specific coupon               |
| PUT    | `/coupons/{id}`            | Update a specific coupon                 |
| DELETE | `/coupons/{id}`            | Delete a specific coupon                 |
| POST   | `/applicable-coupons`      | Get all applicable coupons for a cart    |
| POST   | `/apply-coupon/{id}`       | Apply a specific coupon to the cart      |

---

## 📦 Coupon Types & Payloads

### 1. Cart-wise Coupon
Applies a % discount to the entire cart if the total exceeds a threshold.

```json
POST /coupons
{
  "type": "cart-wise",
  "details": {
    "threshold": 100,
    "discount": 10
  }
}
```

### 2. Product-wise Coupon
Applies a % discount to a specific product wherever it appears in the cart.

```json
POST /coupons
{
  "type": "product-wise",
  "details": {
    "product_id": 1,
    "discount": 20
  }
}
```

### 3. BxGy Coupon
Buy X qualifying products, get Y products free (with repetition limit).

```json
POST /coupons
{
  "type": "bxgy",
  "details": {
    "buy_products": [
      {"product_id": 1, "quantity": 3},
      {"product_id": 2, "quantity": 3}
    ],
    "get_products": [
      {"product_id": 3, "quantity": 1}
    ],
    "repition_limit": 2
  }
}
```

---

## ✅ Implemented Cases

### Cart-wise
- ✅ Apply % discount to entire cart when total ≥ threshold
- ✅ Discount is spread proportionally across items (for clear reporting)
- ✅ Rounding adjustments on the last item to avoid floating-point drift
- ✅ No discount if total < threshold

### Product-wise
- ✅ Apply % discount to a specific product (all units in cart)
- ✅ Zero discount if the targeted product is absent from cart

### BxGy
- ✅ Count qualifying buy-product units across all listed buy_products
- ✅ Compute repetitions: `total_buy_units // buy_qty_needed`
- ✅ Cap repetitions by `repition_limit`
- ✅ Free products distributed cheapest-first (ascending unit price)
- ✅ Free product quantity added to existing cart item
- ✅ If a "get" product is not in the cart, it is appended with qty = free_qty

### General
- ✅ Coupon expiration date (bonus feature)
- ✅ Active/inactive flag per coupon
- ✅ Inactive and expired coupons excluded from `/applicable-coupons`
- ✅ Inactive and expired coupons rejected in `/apply-coupon/{id}`
- ✅ Full CRUD for coupons

---

## ❌ Unimplemented Cases (with Reasoning)

| Case | Reason Not Implemented |
|------|------------------------|
| **Stacking multiple coupons** | Requires a coupon-priority or exclusivity model. Complex interaction between discount types (e.g., cart-wise after product-wise). Out of scope for this task. |
| **BxGy where buy and get overlap** | E.g., "buy 2 of A, get 1 of A free". Needs careful inventory counting to avoid double-counting. |
| **Minimum quantity for product-wise** | E.g., "20% off product A if you buy at least 3". Schema extension needed. |
| **User-level usage limits** | "Coupon can only be used once per user." Requires user authentication and usage tracking. |
| **Category-based coupons** | "10% off all Electronics." Needs a product-category mapping service, which is external to this API. |
| **Tiered discounts** | E.g., "10% off if cart > 100, 20% off if cart > 200." Multi-threshold schema required. |
| **Coupon codes (alphanumeric)** | Currently use numeric IDs. A `code` field can be added for human-readable coupon codes. |
| **Limit on total coupon uses** | "Coupon valid for first 100 redemptions." Requires an atomic counter or database lock. |
| **Flat-amount discounts** | All discounts are percentage-based. Flat ₹50 off would need schema support. |
| **Free shipping coupon** | Requires a shipping cost field in the cart model. |

---

## ⚠️ Limitations

1. **SQLite concurrency**: SQLite has limitations under high concurrent write load. Replace with PostgreSQL or MySQL for production.
2. **No authentication**: The API is open. In production, protect endpoints with JWT/OAuth2.
3. **BxGy free product price**: If a free product is not present in the cart, its unit price is unknown and the discount value is reported as `0`. The product is still added to the cart.
4. **Floating-point precision**: Currency calculations use Python `float`. For production financial systems, use Python's `decimal.Decimal` throughout.
5. **No pagination**: `GET /coupons` returns all records. Add pagination for large datasets.

---

## 📐 Assumptions

1. **Prices are per unit** in the cart payload.
2. **Discount percentages** are expressed as `0–100` (not `0–1`).
3. **BxGy buy quantity** is the total of all `buy_products` quantities combined, not per product.
4. **BxGy cheapest-first** strategy: free units go to the cheapest "get" products first to minimize customer pay.
5. **Coupon type is immutable** in spirit — updating `type` and `details` together is allowed but the caller is responsible for consistency.
6. **Expiration date** with no timezone is compared to local server time as naive datetime.
7. **Cart totals** are not stored; they are always computed fresh from the submitted cart payload.

---

## 🧪 Test Coverage Summary

| Test Class               | Coverage                                   |
|--------------------------|--------------------------------------------|
| `TestCouponCRUD`         | Create, read, update, delete, 404 cases    |
| `TestValidation`         | Invalid type, negative values, over 100%   |
| `TestApplicableCoupons`  | All three types, inactive exclusion        |
| `TestApplyCoupon`        | All three types, errors, expired coupon    |
| `TestBxGyEdgeCases`      | Repetition limit, insufficient buy qty     |


d:\Coupons Management API for an E-commerce Website\
├── main.py           # FastAPI app with all 7 API endpoints
├── models.py         # SQLAlchemy ORM model (Coupon table)
├── schemas.py        # Pydantic v2 request/response schemas  
├── coupon_engine.py  # Core discount computation logic
├── database.py       # SQLite database setup
├── test_main.py      # 29 unit tests (all passing ✅)
├── requirements.txt  # Dependencies
└── README.md         # Full documentation



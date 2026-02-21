"""
main.py
=======
FastAPI application entry point.

Endpoints:
  POST   /coupons               - Create a coupon
  GET    /coupons               - List all coupons
  GET    /coupons/{id}          - Get coupon by ID
  PUT    /coupons/{id}          - Update coupon
  DELETE /coupons/{id}          - Delete coupon
  POST   /applicable-coupons    - Get all applicable coupons for a given cart
  POST   /apply-coupon/{id}     - Apply a specific coupon to the cart
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import coupon_engine
from database import engine, get_db

# Create DB tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Coupons Management API",
    description="RESTful API to manage cart-wise, product-wise, and BxGy discount coupons for an e-commerce platform.",
    version="1.0.0",
)


# ═══════════════════════════════════════════════════
#  COUPON CRUD
# ═══════════════════════════════════════════════════

@app.post(
    "/coupons",
    response_model=schemas.CouponResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Coupons"],
    summary="Create a new coupon",
)
def create_coupon(coupon: schemas.CouponCreate, db: Session = Depends(get_db)):
    """
    Create a new coupon. Supports three types:
    - **cart-wise**: Percentage off entire cart if total exceeds a threshold.
    - **product-wise**: Percentage off a specific product.
    - **bxgy**: Buy X get Y free with a repetition limit.
    """
    db_coupon = models.Coupon(
        type=coupon.type.value,
        details=coupon.details,
        expiration_date=coupon.expiration_date,
    )
    db.add(db_coupon)
    db.commit()
    db.refresh(db_coupon)
    return db_coupon


@app.get(
    "/coupons",
    response_model=List[schemas.CouponResponse],
    tags=["Coupons"],
    summary="Get all coupons",
)
def get_all_coupons(db: Session = Depends(get_db)):
    """Retrieve all coupons (both active and inactive)."""
    return db.query(models.Coupon).all()


@app.get(
    "/coupons/{coupon_id}",
    response_model=schemas.CouponResponse,
    tags=["Coupons"],
    summary="Get a coupon by ID",
)
def get_coupon(coupon_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific coupon by its ID."""
    coupon = db.query(models.Coupon).filter(models.Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail=f"Coupon with id={coupon_id} not found")
    return coupon


@app.put(
    "/coupons/{coupon_id}",
    response_model=schemas.CouponResponse,
    tags=["Coupons"],
    summary="Update a coupon",
)
def update_coupon(coupon_id: int, update_data: schemas.CouponUpdate, db: Session = Depends(get_db)):
    """
    Update a specific coupon. All fields are optional — only provided fields are updated.
    """
    coupon = db.query(models.Coupon).filter(models.Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail=f"Coupon with id={coupon_id} not found")

    if update_data.type is not None:
        coupon.type = update_data.type.value
    if update_data.details is not None:
        coupon.details = update_data.details
    if update_data.is_active is not None:
        coupon.is_active = update_data.is_active
    if update_data.expiration_date is not None:
        coupon.expiration_date = update_data.expiration_date

    db.commit()
    db.refresh(coupon)
    return coupon


@app.delete(
    "/coupons/{coupon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Coupons"],
    summary="Delete a coupon",
)
def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    """Delete a specific coupon by its ID."""
    coupon = db.query(models.Coupon).filter(models.Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail=f"Coupon with id={coupon_id} not found")
    db.delete(coupon)
    db.commit()
    return None


# ═══════════════════════════════════════════════════
#  APPLICABLE COUPONS
# ═══════════════════════════════════════════════════

@app.post(
    "/applicable-coupons",
    response_model=schemas.ApplicableCouponsResponse,
    tags=["Apply Coupons"],
    summary="Fetch all applicable coupons for a given cart",
)
def get_applicable_coupons(request: schemas.CartRequest, db: Session = Depends(get_db)):
    """
    Given a cart (list of items with product_id, quantity, price),
    returns all currently applicable and non-expired coupons along with
    the computed discount each would provide.
    """
    items = request.cart.items
    all_coupons = db.query(models.Coupon).filter(models.Coupon.is_active == True).all()

    applicable = []
    for coupon in all_coupons:
        # Skip expired coupons
        if coupon_engine.is_coupon_expired(coupon.expiration_date):
            continue

        discount = 0.0
        try:
            if coupon.type == schemas.CouponType.cart_wise.value:
                discount, _ = coupon_engine.compute_cart_wise_discount(items, coupon.details)

            elif coupon.type == schemas.CouponType.product_wise.value:
                discount, _ = coupon_engine.compute_product_wise_discount(items, coupon.details)

            elif coupon.type == schemas.CouponType.bxgy.value:
                discount, _, _ = coupon_engine.compute_bxgy_discount(items, coupon.details)

        except Exception:
            # Malformed coupon details — skip silently
            continue

        if discount > 0:
            applicable.append(schemas.ApplicableCoupon(
                coupon_id=coupon.id,
                type=coupon.type,
                discount=discount,
            ))

    return schemas.ApplicableCouponsResponse(applicable_coupons=applicable)


# ═══════════════════════════════════════════════════
#  APPLY COUPON
# ═══════════════════════════════════════════════════

@app.post(
    "/apply-coupon/{coupon_id}",
    response_model=schemas.ApplyCouponResponse,
    tags=["Apply Coupons"],
    summary="Apply a specific coupon to the cart",
)
def apply_coupon(coupon_id: int, request: schemas.CartRequest, db: Session = Depends(get_db)):
    """
    Apply a specific coupon to the cart.

    Returns an updated cart showing:
    - Each item's quantity, price, and discount applied.
    - Total price (before discount), total discount, and final price.

    For BxGy coupons, free products may be added to the cart with increased quantity.
    """
    coupon = db.query(models.Coupon).filter(models.Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail=f"Coupon with id={coupon_id} not found")

    if not coupon.is_active:
        raise HTTPException(status_code=400, detail="Coupon is not active")

    if coupon_engine.is_coupon_expired(coupon.expiration_date):
        raise HTTPException(status_code=400, detail="Coupon has expired")

    items = request.cart.items
    per_item_discounts = [0.0] * len(items)
    total_discount = 0.0
    final_items = list(items)

    try:
        if coupon.type == schemas.CouponType.cart_wise.value:
            total_discount, per_item_discounts = coupon_engine.compute_cart_wise_discount(items, coupon.details)

        elif coupon.type == schemas.CouponType.product_wise.value:
            total_discount, per_item_discounts = coupon_engine.compute_product_wise_discount(items, coupon.details)

        elif coupon.type == schemas.CouponType.bxgy.value:
            total_discount, per_item_discounts, final_items = coupon_engine.compute_bxgy_discount(items, coupon.details)
            # Pad discounts if new items were added
            while len(per_item_discounts) < len(final_items):
                per_item_discounts.append(0.0)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown coupon type: {coupon.type}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not apply coupon: {str(e)}")

    if total_discount == 0.0 and coupon.type != schemas.CouponType.bxgy.value:
        raise HTTPException(
            status_code=400,
            detail="Coupon conditions are not met for the current cart"
        )

    # Build response items
    total_price = sum(item.price * item.quantity for item in items)  # original cart total
    final_price = round(total_price - total_discount, 2)

    updated_items = []
    for i, item in enumerate(final_items):
        disc = per_item_discounts[i] if i < len(per_item_discounts) else 0.0
        updated_items.append(schemas.UpdatedCartItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price,
            total_discount=round(disc, 2),
        ))

    return schemas.ApplyCouponResponse(
        updated_cart=schemas.UpdatedCart(
            items=updated_items,
            total_price=round(total_price, 2),
            total_discount=round(total_discount, 2),
            final_price=final_price,
        )
    )


# ═══════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════

@app.get("/", tags=["Health"], summary="Health check")
def root():
    return {"status": "ok", "message": "Coupons Management API is running 🚀"}

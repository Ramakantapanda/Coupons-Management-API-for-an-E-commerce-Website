"""
coupon_engine.py
================
Core business logic for computing discounts.

Implemented Cases:
------------------
1. cart-wise:
   - Applies a percentage discount to the entire cart if total >= threshold.
   - Discount is spread proportionally across all items.

2. product-wise:
   - Applies a percentage discount to every unit of a specific product in the cart.

3. bxgy (Buy X, Get Y):
   - Customer buys a qualifying quantity from "buy_products" group.
   - Earns free units from "get_products" group in proportion.
   - Capped by repetition_limit.
   - Free products are distributed in ascending price order (cheapest first).
   - If a "get" product is not in the cart, it is added with quantity = free_qty and
     a full discount (entire price covered).

Unimplemented / Noted Cases:
-----------------------------
- Stacking multiple coupons on the same cart simultaneously.
- BxGy where free quantity comes from the same pool as buy products.
- Minimum quantity constraints for product-wise coupons.
- User-level coupon usage limits.
- Expired coupon rejection is handled in the route layer.
- Coupon applicability based on product category (not just product ID).
"""

from datetime import datetime, timezone
from typing import List, Tuple
from schemas import CartItem, CartWiseDetails, ProductWiseDetails, BxGyDetails, BxGyProduct


def _cart_total(items: List[CartItem]) -> float:
    return sum(item.price * item.quantity for item in items)


# ─────────────────────────── Cart-wise ───────────────────────────

def compute_cart_wise_discount(items: List[CartItem], details: dict) -> Tuple[float, List[float]]:
    """
    Returns (total_discount, per_item_discounts list).
    Discount is split proportionally by item subtotal.
    """
    d = CartWiseDetails(**details)
    total = _cart_total(items)
    if total < d.threshold:
        return 0.0, [0.0] * len(items)

    total_discount = round(total * d.discount / 100, 2)
    per_item = []
    for item in items:
        item_subtotal = item.price * item.quantity
        share = round(item_subtotal / total * total_discount, 2)
        per_item.append(share)

    # Fix rounding drift on last item
    diff = round(total_discount - sum(per_item), 2)
    if per_item:
        per_item[-1] = round(per_item[-1] + diff, 2)

    return total_discount, per_item


# ─────────────────────────── Product-wise ───────────────────────────

def compute_product_wise_discount(items: List[CartItem], details: dict) -> Tuple[float, List[float]]:
    """
    Returns (total_discount, per_item_discounts list).
    Only the target product item gets a discount.
    """
    d = ProductWiseDetails(**details)
    per_item = []
    total_discount = 0.0

    for item in items:
        if item.product_id == d.product_id:
            disc = round(item.price * item.quantity * d.discount / 100, 2)
            per_item.append(disc)
            total_discount += disc
        else:
            per_item.append(0.0)

    return round(total_discount, 2), per_item


# ─────────────────────────── BxGy ───────────────────────────

def compute_bxgy_discount(items: List[CartItem], details: dict) -> Tuple[float, List[float], List[CartItem]]:
    """
    Returns (total_discount, per_item_discounts, updated_items_with_free_products).

    Algorithm:
    1. Count how many qualifying "buy" products are in the cart (by product_id).
    2. Determine how many repetitions are earned (capped by repition_limit).
    3. For each repetition, grant free_qty units from "get_products" whose products
       are already in the cart (or add them if missing).
    4. Free units are given to the cheapest "get" products first.
    """
    d = BxGyDetails(**details)

    # Build a lookup for items already in cart
    cart_map = {item.product_id: item for item in items}

    # ── Step 1: count qualifying buy-product units ──
    total_buy_units = 0
    buy_qty_needed = sum(bp.quantity for bp in d.buy_products)

    for bp in d.buy_products:
        if bp.product_id in cart_map:
            total_buy_units += cart_map[bp.product_id].quantity

    if buy_qty_needed == 0:
        return 0.0, [0.0] * len(items), list(items)

    repetitions = total_buy_units // buy_qty_needed
    repetitions = min(repetitions, d.repition_limit)

    if repetitions == 0:
        return 0.0, [0.0] * len(items), list(items)

    # ── Step 2: determine free units from "get" list ──
    # Sort by ascending unit price (cheapest first)
    get_products_in_cart = []
    for gp in d.get_products:
        if gp.product_id in cart_map:
            get_products_in_cart.append((gp, cart_map[gp.product_id].price))
        else:
            # Product not in cart — will be added as free
            get_products_in_cart.append((gp, 0.0))  # price unknown, treat as 0

    get_products_in_cart.sort(key=lambda x: x[1])

    total_discount = 0.0
    free_map: dict[int, int] = {}  # product_id -> free_qty

    for _ in range(repetitions):
        for gp, price in get_products_in_cart:
            free_qty = gp.quantity
            free_map[gp.product_id] = free_map.get(gp.product_id, 0) + free_qty
            if gp.product_id in cart_map:
                discount_val = cart_map[gp.product_id].price * free_qty
            else:
                # Not in cart, no discount value calculable
                discount_val = 0.0
            total_discount += discount_val

    # ── Step 3: build updated items list ──
    updated_items = []
    per_item_discounts = []

    for item in items:
        free_qty = free_map.pop(item.product_id, 0)
        if free_qty > 0:
            disc = round(item.price * free_qty, 2)
            per_item_discounts.append(disc)
            updated_items.append(CartItem(
                product_id=item.product_id,
                quantity=item.quantity + free_qty,
                price=item.price
            ))
        else:
            per_item_discounts.append(0.0)
            updated_items.append(item)

    # Add get_products not already in cart
    for pid, qty in free_map.items():
        per_item_discounts.append(0.0)
        updated_items.append(CartItem(product_id=pid, quantity=qty, price=0.0))

    return round(total_discount, 2), per_item_discounts, updated_items


# ─────────────────────────── Expiry Check ───────────────────────────

def is_coupon_expired(expiration_date) -> bool:
    if expiration_date is None:
        return False
    if expiration_date.tzinfo is None:
        return expiration_date < datetime.now()
    return expiration_date < datetime.now(timezone.utc)

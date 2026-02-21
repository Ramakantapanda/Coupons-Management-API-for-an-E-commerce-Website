from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# ─────────────── Coupon Type Enum ───────────────

class CouponType(str, Enum):
    cart_wise = "cart-wise"
    product_wise = "product-wise"
    bxgy = "bxgy"


# ─────────────── Detail Sub-schemas ───────────────

class CartWiseDetails(BaseModel):
    threshold: float  # Minimum cart total to apply the discount
    discount: float   # Percentage discount (e.g., 10 => 10%)

    @field_validator("threshold", "discount")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be a positive number")
        return v

    @field_validator("discount")
    @classmethod
    def discount_max_100(cls, v: float) -> float:
        if v > 100:
            raise ValueError("Discount percentage cannot exceed 100")
        return v


class ProductWiseDetails(BaseModel):
    product_id: int   # Target product
    discount: float   # Percentage discount

    @field_validator("discount")
    @classmethod
    def discount_max_100(cls, v: float) -> float:
        if v > 100:
            raise ValueError("Discount percentage cannot exceed 100")
        return v


class BxGyProduct(BaseModel):
    product_id: int
    quantity: int

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be positive")
        return v


class BxGyDetails(BaseModel):
    buy_products: List[BxGyProduct]   # Products the customer must buy
    get_products: List[BxGyProduct]   # Products given for free
    repition_limit: int = 1            # Max number of times the coupon can repeat

    @field_validator("repition_limit")
    @classmethod
    def limit_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Repetition limit must be positive")
        return v

    @field_validator("buy_products", "get_products")
    @classmethod
    def not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Product list cannot be empty")
        return v


# ─────────────── Coupon Request / Response ───────────────

class CouponCreate(BaseModel):
    type: CouponType
    details: Any  # Validated per type in validator below
    expiration_date: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_details_by_type(self) -> "CouponCreate":
        type_ = self.type
        details = self.details
        if type_ == CouponType.cart_wise:
            self.details = CartWiseDetails(**details).model_dump()
        elif type_ == CouponType.product_wise:
            self.details = ProductWiseDetails(**details).model_dump()
        elif type_ == CouponType.bxgy:
            parsed = BxGyDetails(**details)
            self.details = parsed.model_dump()
        return self


class CouponUpdate(BaseModel):
    type: Optional[CouponType] = None
    details: Optional[Any] = None
    is_active: Optional[bool] = None
    expiration_date: Optional[datetime] = None


class CouponResponse(BaseModel):
    id: int
    type: CouponType
    details: Any
    is_active: bool
    expiration_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─────────────── Cart schemas ───────────────

class CartItem(BaseModel):
    product_id: int
    quantity: int
    price: float  # Price per unit

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be positive")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


class Cart(BaseModel):
    items: List[CartItem]


class CartRequest(BaseModel):
    cart: Cart


# ─────────────── Applicable Coupons Response ───────────────

class ApplicableCoupon(BaseModel):
    coupon_id: int
    type: CouponType
    discount: float  # Absolute discount value


class ApplicableCouponsResponse(BaseModel):
    applicable_coupons: List[ApplicableCoupon]


# ─────────────── Apply Coupon Response ───────────────

class UpdatedCartItem(BaseModel):
    product_id: int
    quantity: int
    price: float
    total_discount: float


class UpdatedCart(BaseModel):
    items: List[UpdatedCartItem]
    total_price: float
    total_discount: float
    final_price: float


class ApplyCouponResponse(BaseModel):
    updated_cart: UpdatedCart

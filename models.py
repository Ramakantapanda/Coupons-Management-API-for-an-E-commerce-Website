from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base


class Coupon(Base):
    """
    Database model for coupons.

    type: 'cart-wise' | 'product-wise' | 'bxgy'
    details: JSON field storing type-specific discount details.
        - cart-wise:    { "threshold": <int>, "discount": <float (percent)> }
        - product-wise: { "product_id": <int>, "discount": <float (percent)> }
        - bxgy:         {
                            "buy_products": [{"product_id": <int>, "quantity": <int>}, ...],
                            "get_products": [{"product_id": <int>, "quantity": <int>}, ...],
                            "repition_limit": <int>
                        }
    """
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    type = Column(String, nullable=False)
    details = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expiration_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

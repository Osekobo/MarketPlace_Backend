"""User account model (Customer / Vendor / Rider)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.vendor import Vendor


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # A vendor user owns exactly one vendor profile.
    vendor: Mapped["Vendor | None"] = relationship(
        back_populates="owner",
        uselist=False,
        cascade="all, delete-orphan",
    )

    customer_orders: Mapped[list["Order"]] = relationship(
        back_populates="customer",
        foreign_keys="Order.customer_id",
    )
    rider_orders: Mapped[list["Order"]] = relationship(
        back_populates="rider",
        foreign_keys="Order.rider_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role.value})>"

"""Item model using SQLAlchemy ORM"""
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from db import Base


class Item(Base):
    """Invoice line item SQLAlchemy ORM model"""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column("InvoiceId", String, ForeignKey("invoices.InvoiceId"), nullable=False)
    description = Column("Description", String, nullable=True)
    name = Column("Name", String, nullable=True)
    quantity = Column("Quantity", Float, nullable=True)
    unit_price = Column("UnitPrice", Float, nullable=True)
    amount = Column("Amount", Float, nullable=True)

    # Relationship
    invoice = relationship("Invoice", back_populates="items")

    def to_dict(self) -> Dict[str, Any]:
        """Convert item to dictionary"""
        return {
            "Description": self.description,
            "Name": self.name,
            "Quantity": self.quantity,
            "UnitPrice": self.unit_price,
            "Amount": self.amount
        }

    @classmethod
    def from_dict(cls, invoice_id: str, data: Dict[str, Any], item_id: Optional[int] = None) -> 'Item':
        """Create item from dictionary"""
        return cls(
            invoice_id=invoice_id,
            description=data.get("Description"),
            name=data.get("Name"),
            quantity=data.get("Quantity"),
            unit_price=data.get("UnitPrice"),
            amount=data.get("Amount"),
            id=item_id
        )

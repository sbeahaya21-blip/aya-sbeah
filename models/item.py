"""Item model and database operations"""
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class Item:
    """Invoice line item data model"""
    invoice_id: str
    description: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    id: Optional[int] = None  # Database primary key

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


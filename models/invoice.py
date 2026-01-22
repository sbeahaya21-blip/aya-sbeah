"""Invoice model using SQLAlchemy ORM"""
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from db import Base


class Invoice(Base):
    """Invoice SQLAlchemy ORM model"""
    __tablename__ = "invoices"

    invoice_id = Column("InvoiceId", String, primary_key=True)
    vendor_name = Column("VendorName", String, nullable=True)
    invoice_date = Column("InvoiceDate", String, nullable=True)
    billing_address_recipient = Column("BillingAddressRecipient", String, nullable=True)
    shipping_address = Column("ShippingAddress", String, nullable=True)
    sub_total = Column("SubTotal", Float, nullable=True)
    shipping_cost = Column("ShippingCost", Float, nullable=True)
    invoice_total = Column("InvoiceTotal", Float, nullable=True)

    # Relationships
    confidences = relationship("InvoiceConfidence", back_populates="invoice", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="invoice", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        """Convert invoice to dictionary"""
        return {
            "InvoiceId": self.invoice_id,
            "VendorName": self.vendor_name,
            "InvoiceDate": self.invoice_date,
            "BillingAddressRecipient": self.billing_address_recipient,
            "ShippingAddress": self.shipping_address,
            "SubTotal": self.sub_total,
            "ShippingCost": self.shipping_cost,
            "InvoiceTotal": self.invoice_total
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Invoice':
        """Create invoice from dictionary"""
        return cls(
            invoice_id=data.get("InvoiceId", ""),
            vendor_name=data.get("VendorName"),
            invoice_date=data.get("InvoiceDate"),
            billing_address_recipient=data.get("BillingAddressRecipient"),
            shipping_address=data.get("ShippingAddress"),
            sub_total=data.get("SubTotal"),
            shipping_cost=data.get("ShippingCost"),
            invoice_total=data.get("InvoiceTotal")
        )


class InvoiceConfidence(Base):
    """Invoice confidence scores SQLAlchemy ORM model"""
    __tablename__ = "confidences"

    invoice_id = Column("InvoiceId", String, ForeignKey("invoices.InvoiceId"), primary_key=True)
    vendor_name = Column("VendorName", Float, nullable=True)
    invoice_date = Column("InvoiceDate", Float, nullable=True)
    billing_address_recipient = Column("BillingAddressRecipient", Float, nullable=True)
    shipping_address = Column("ShippingAddress", Float, nullable=True)
    sub_total = Column("SubTotal", Float, nullable=True)
    shipping_cost = Column("ShippingCost", Float, nullable=True)
    invoice_total = Column("InvoiceTotal", Float, nullable=True)

    # Relationship
    invoice = relationship("Invoice", back_populates="confidences")

    def to_dict(self) -> Dict[str, Any]:
        """Convert confidence to dictionary"""
        return {
            "VendorName": self.vendor_name,
            "InvoiceDate": self.invoice_date,
            "BillingAddressRecipient": self.billing_address_recipient,
            "ShippingAddress": self.shipping_address,
            "SubTotal": self.sub_total,
            "ShippingCost": self.shipping_cost,
            "InvoiceTotal": self.invoice_total
        }

    @classmethod
    def from_dict(cls, invoice_id: str, data: Dict[str, Any]) -> 'InvoiceConfidence':
        """Create confidence from dictionary"""
        return cls(
            invoice_id=invoice_id,
            vendor_name=data.get("VendorName"),
            invoice_date=data.get("InvoiceDate"),
            billing_address_recipient=data.get("BillingAddressRecipient"),
            shipping_address=data.get("ShippingAddress"),
            sub_total=data.get("SubTotal"),
            shipping_cost=data.get("ShippingCost"),
            invoice_total=data.get("InvoiceTotal")
        )

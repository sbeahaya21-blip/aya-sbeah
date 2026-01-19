"""Invoice model and database operations"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Invoice:
    """Invoice data model"""
    invoice_id: str
    vendor_name: Optional[str] = None
    invoice_date: Optional[str] = None
    billing_address_recipient: Optional[str] = None
    shipping_address: Optional[str] = None
    sub_total: Optional[float] = None
    shipping_cost: Optional[float] = None
    invoice_total: Optional[float] = None

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


@dataclass
class InvoiceConfidence:
    """Invoice confidence scores model"""
    invoice_id: str
    vendor_name: Optional[float] = None
    invoice_date: Optional[float] = None
    billing_address_recipient: Optional[float] = None
    shipping_address: Optional[float] = None
    sub_total: Optional[float] = None
    shipping_cost: Optional[float] = None
    invoice_total: Optional[float] = None

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


from typing import List, Optional
from pydantic import BaseModel, EmailStr
from fastapi import UploadFile

class ProductCreate(BaseModel):
    shop_id: int
    shopify_product_id: str
    shopify_variant_id: str
    title: str
    image_url:str
    reorder_days: int

class UpdateProduct(BaseModel):
    shop_id: int
    shopify_product_id: str
    shopify_variant_id:str
    reorder_days: Optional[int] = None

class ShopCreate(BaseModel):
    shopify_domain: str
    shop_name: Optional[str] = None
    shop_logo: Optional[str] = None  # Optional field
    email: Optional[EmailStr] = None # Ensures email is valid
    host: Optional[str] = None
    accessToken : Optional[str] = None

class LineItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int
    status:str
    price: str

class OrderPayload(BaseModel):
    shop:str
    shopify_order_id: int
    customer_id: int
    customer_email: str
    customer_name: str
    customer_phone: Optional[str] = None
    shipping_phone:Optional[str] = None
    billing_phone:Optional[str] = None
    line_items: List[LineItem]
    order_date: str
    order_source:bool

class DeletePayload(BaseModel):
    shop:str
    product_id:int

class GeneralSettings(BaseModel):
    shop_name:str
    bannerImage:UploadFile
    tab: str
class EmailTemplateSettings(BaseModel):
    shop_name:str
    tab: str
    subject: str
    fromName: str
    fromEmail: EmailStr
    coupon: Optional[str] = None
    discountPercent: Optional[str] = None
    bufferTime: Optional[int] = None

class TriggerEmailRequest(BaseModel):
    to: EmailStr
    template_name: str
    store_name: str

class TemplateCreateRequest(BaseModel):
    templatename: str
    subject: str
    html_body: str

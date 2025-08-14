from sqlalchemy import Boolean, Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Shop(Base):
    __tablename__ = "shop"

    shop_id = Column(Integer, primary_key=True, index=True)
    shopify_domain = Column(String, index=True)  # Shopify domain is a string
    shop_name = Column(String, index=True)  # Shop name is a string
    shop_logo = Column(String, nullable=True)  # Logo path or URL as string
    email = Column(String, index=True)  # Email should be a string
    message_template_id = Column(Integer, nullable=True)  # Assuming template ID is an integer
    buffer_time = Column(String, nullable=True,default=5)
    coupon = Column(String, nullable=True)
    discountpercent= Column(String, nullable=True)
    order_flag=Column(Boolean, default=False)
    order_sync_count=Column(Integer,default=10)
    plan = Column(String, nullable=True,default='Free')
    host = Column(String, nullable=True)
    accesstoken = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)  # Boolean to indicate deletion


    customers = relationship("ShopCustomer", back_populates="shop", cascade="all, delete-orphan")
    orders = relationship("Orders", back_populates="shop", cascade="all, delete-orphan")
    products = relationship("Products", back_populates="shop", cascade="all, delete-orphan")

class ShopCustomer(Base):
    __tablename__ = "shop_customer"

    shop_customer_id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shop.shop_id"))
    shopify_id = Column(Integer, index=True)  # Shopify ID is a string
    email = Column(String, index=True)  # Email should be a string
    mobile = Column(String, index=True)  # Mobile number as a string
    shipping_mobile_no = Column(String, index=True)  # Mobile number as a string
    billing_mobile_no = Column(String, index=True)  # Mobile number as a string
    first_name = Column(String, index=True)  # First name is a string
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)  # Boolean for deletion

    shop = relationship("Shop", back_populates="customers")
    reminders = relationship("Reminder", back_populates="customer", cascade="all, delete-orphan")


class OrderProduct(Base):
    __tablename__ = "order_product"

    order_product_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), index=True)  # Relates to orders
    shopify_product_id = Column(Integer, index=True)  # Assuming it's an integer
    shopify_variant_id = Column(Integer, index=True)
    quantity = Column(Integer, index=True)  # Quantity as integer
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    


class Orders(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shop.shop_id"), index=True)  # Relates to shop
    shopify_order_id = Column(String, index=True)  # Shopify order ID is a string
    customer_id = Column(Integer, ForeignKey("shop_customer.shop_customer_id"), index=True)  # Relates to customer
    order_date = Column(DateTime, index=True)  # Date should be a DateTime
    total_amount = Column(Float, index=True)  # Total amount as float
    status = Column(String, index=True)  # Order status as a string
    order_source=Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    shop = relationship("Shop", back_populates="orders")
    customer = relationship("ShopCustomer")
    order_products = relationship("OrderProduct", cascade="all, delete-orphan")

class Products(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shop.shop_id"), index=True)  # Relates to shop
    shopify_product_id = Column(String, index=True)  # Shopify product ID is a string
    shopify_variant_id = Column(String, index=True) 
    title = Column(String, index=True)  # Product title as a string
    image_url=Column(String, index=True)
    reorder_days = Column(Integer, index=True)  # Reorder days as integer
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    shop = relationship("Shop", back_populates="products")
    reminders = relationship("Reminder", back_populates="product", cascade="all, delete-orphan")


class Reminder(Base):
    __tablename__ = "reminder"

    reminder_id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("shop_customer.shop_customer_id"), index=True)  # Relates to customer
    product_id = Column(Integer, ForeignKey("products.product_id"), index=True)  # Relates to product
    order_id = Column(Integer, ForeignKey("orders.order_id"), index=True)  # Relates to order
    reminder_date = Column(DateTime, index=True)  # Date should be DateTime
    status = Column(String, index=True,default='Pending')  # Reminder status as string
    shop_id=Column(String,index=True)
    product_title=Column(String,index=True)
    product_quantity=Column(Integer, index=True) 
    image_url=Column(String,index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)
    customer = relationship("ShopCustomer", back_populates="reminders")
    product = relationship("Products", back_populates="reminders")

class Message_Template(Base):
    __tablename__ ="message_template"

    message_template_id = Column(Integer, primary_key=True, index=True)
    message_template = Column(String, index=True)
    message_channel = Column(String, index=True)
    mail_server = Column(String, index=True)
    port=Column(Integer, index=True)
    fromname = Column(String, index=True)
    fromemail= Column(String, index=True)
    subject = Column(String, index=True)
    body_template=Column(String,index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)
    shop_name=Column(String, index=True)
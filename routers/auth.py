
from datetime import timedelta
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
import models
from constants import AWS_BUCKET,AWS_REGION,TRIGGER_EMAIL_FROM,REPLY_TO_EMAIL
from models import Products,Shop,Orders,ShopCustomer,OrderProduct,Reminder,Message_Template
from schemas import ProductCreate,UpdateProduct,ShopCreate,LineItem,OrderPayload,DeletePayload,GeneralSettings,EmailTemplateSettings,TriggerEmailRequest,TemplateCreateRequest
from dependencies import get_s3_client,send_email,send_email_template,create_email_template
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import engine ,get_db
from pydantic import BaseModel, EmailStr
from datetime import datetime
import pytz
import boto3
from dateutil import parser
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import os
from constants import AWS_BUCKET,AWS_REGION,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY,CONFIGURATION_SET
from botocore.client import BaseClient
from fastapi.responses import RedirectResponse
from jinja2 import Template
from fastapi import BackgroundTasks


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"user": "Not authorized"},500:{"user":"Internal Server Error"},400:{"user":"Invalid Request"}}
)

models.Base.metadata.create_all(bind=engine)
db_dependency=Annotated[Session,Depends(get_db)]

API_KEY=os.getenv("SENDINBLUE_API_KEY")


DEFAULT_EMAIL_TEMPLATE="""<!DOCTYPE html>
                    <html lang="en">
                    <head>
                    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                    </head>
                    <body style="margin:0; padding:0; background-color:#f4f4f4;">
                    <table role="presentation" width="100%" bgcolor="#f4f4f4" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                        <td align="center">
                            <table role="presentation" width="600" bgcolor="#ffffff" cellpadding="0" cellspacing="0" border="0" style="margin:20px auto; padding:20px; border-radius:8px;">

                            {% if image_path %}
                            <tr>
                                <td align="center" bgcolor="#eeeeee" style="padding:20px; border-radius:8px 8px 0 0;">
                                <img src="{{ image_path }}" alt="{{ shop }}" width="120" style="display:block;">
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td align="center" bgcolor="#eeeeee" style="padding:20px; border-radius:8px 8px 0 0;">
                                <h1 style="font-size:30px; color:#333333; font-family:Arial, sans-serif;">{{ shop }}</h1>
                                </td>
                            </tr>
                            {% endif %}

                            <tr>
                                <td align="center" style="padding:20px; font-family:Arial, sans-serif; color:#333333;">
                                <p style="font-size:16px;">Hello {{ first_name }},</p>
                                <p style="font-size:16px;">Just a quick reminder - based on your last purchase, you might be running low on <b>{{ product_name }}</b>.</p>
                                
                                </td>
                            </tr>

                            <tr>
                                <td align="center" style="padding:10px;">
                                <img src="{{ product_image }}" alt="{{ product_name }}" width="150" style="display:block; margin:0 auto; border-radius:5px;">
                                </td>
                            </tr>

                            <tr>
                                <td align="center" style="padding:5px 20px; font-family:Arial, sans-serif;">
                                <p style="font-size:16px;">To make sure you don't run out, you can easily reorder it here:</p>
                                
                                </td>
                            </tr>

                            <tr>
                                <td align="center" style="padding:20px;">
                                <a href="{{ reorder_url }}" target="_blank" style="display:inline-block; padding:12px 20px; background-color:#007bff; color:#ffffff; text-decoration:none; border-radius:5px; font-size:16px; font-weight:bold;">
                                    REORDER NOW
                                </a>
                                </td>
                            </tr>

                            {% if plan == "PRO" and coupon %}
                            <tr>
                                <td align="center" bgcolor="#f9f1dc" style="padding:15px; border-radius:5px;">
                                <h3 style="color:#d67e00; margin:0;">SPECIAL OFFER</h3>
                                <p style="font-size:16px;">Use code <span style="font-size:18px; font-weight:bold; color:#d67e00; background:#fff; padding:5px 10px; border-radius:4px;">{{ coupon }}</span> at checkout</p>
                                <p style="font-size:16px;">{{ discountpercent }}</p>
                                </td>
                            </tr>
                            {% endif %}

                            <tr>
                                <td align="center" style="padding:20px; font-size:12px; color:#777777; font-family:Arial, sans-serif;">
                                <p>{{ shop }} | {{ mail_to }}</p>
                                
                                </td>
                            </tr>

                            </table>
                        </td>
                        </tr>
                    </table>
                    </body>
                    </html>
                    """

@router.get("/products/{shop_id}")
async def get_products(shop_id:int, db: Session = Depends(get_db)):
    """
    Get all products or filter by `shop_id`.

    Args:
    - shop_id (Optional[int]): The ID of the shop to filter products.
    - db (Session): The database session.

    Returns:
    - List of products or filtered products.
    """
    try:
        # Query all products if no `shop_id` is provided
        products = db.query(Products).filter((Products.shop_id == shop_id )&(Products.is_deleted == False)).order_by(desc(Products.created_at)).all()
        # products = db.query(Products).all()
        
        if not products:
            product_list=[]
        
        # Convert products to dictionaries for response
        product_list = [
            {
                "product_id": product.product_id,
                "shop_id": product.shop_id,
                "shopify_product_id": product.shopify_product_id,
                "shopify_variant_id":product.shopify_variant_id,
                "title": product.title,
                "reorder_days": product.reorder_days,
                "productImage":product.image_url,
                "created_at":product.created_at,
            }
            for product in products
        ]
        
        return product_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching products: {e}")

    
@router.post("/products")
async def create_product(products: List[ProductCreate], db: Session = Depends(get_db)):
    reorder_details = []

    for product in products:
        try:
            # Check for existing product
            existingproduct = (db.query(Products).filter((Products.shopify_product_id == product.shopify_product_id) &(Products.shopify_variant_id == product.shopify_variant_id)).first())
            
            # Common fields
    
            print(product)

            if existingproduct:
                # Update existing product details
                existingproduct.reorder_days = product.reorder_days
                existingproduct.image_url=product.image_url
                existingproduct.created_at=datetime.utcnow()
                existingproduct.is_deleted = False

                db.commit()
                db.refresh(existingproduct)

                reorder_details.append({
                    "product_id": existingproduct.product_id,
                    "shop_id": existingproduct.shop_id,
                    "shopify_product_id": existingproduct.shopify_product_id,
                    "shopify_variant_id": existingproduct.shopify_variant_id,
                    "title": existingproduct.title,
                    "productImage":existingproduct.image_url,
                    "reorder_days": existingproduct.reorder_days,
                    "created_at": existingproduct.created_at,
                })
            else:
                # Create new product
                new_product = Products(
                    shop_id=product.shop_id,
                    shopify_product_id=product.shopify_product_id,
                    shopify_variant_id=product.shopify_variant_id,
                    title=product.title,
                    image_url=product.image_url,
                    reorder_days=product.reorder_days,
                )
                db.add(new_product)
                db.commit()
                db.refresh(new_product)

                reorder_details.append({
                    "product_id": new_product.product_id,
                    "shop_id": new_product.shop_id,
                    "shopify_product_id": new_product.shopify_product_id,
                    "shopify_variant_id": new_product.shopify_variant_id,
                    "title": new_product.title,
                    "productImage":new_product.image_url,
                    "reorder_days": new_product.reorder_days,
                    "created_at": new_product.created_at,
                })
                

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating product: {e}")
    print(reorder_details)
    return reorder_details

@router.patch("/products/{product_id}")
async def update_product(product_id: int,product: UpdateProduct,db: Session = Depends(get_db)):
    # Fetch the existing product by product_id
    reorder_details = []
    shop = db.query(Shop).filter((Shop.shop_id == product.shop_id)&(Shop.is_deleted == False)).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    existing_product = (db.query(Products).filter((Products.shopify_product_id == product_id) &(Products.shopify_variant_id == product.shopify_variant_id) &(Products.shop_id == product.shop_id)).first())
    if not existing_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    reminders = db.query(Reminder).filter_by(product_id=existing_product.product_id,status="Pending",is_deleted=False,shop_id=shop.shopify_domain).all()

    if product.shopify_product_id is not None:
        existing_product.reorder_days = product.reorder_days
        if product.reorder_days is None:
            existing_product.is_deleted = True
            if reminders:
                for reminder in reminders:
                    reminder.is_deleted = True
            
        else:
            if reminders:
                for reminder in reminders:
                    order = (db.query(Orders).filter(Orders.order_id == reminder.order_id).first())
                    order_product = (db.query(OrderProduct).filter(OrderProduct.order_id == reminder.order_id).first())
                    print(type(order.order_date))
                    order_date = parser.parse(order.order_date)
                    # order_date = datetime.strptime(order.order_date, "%Y-%m-%d %H:%M:%S%z")
                    print(type(order_date))   
                    if order and order_product:
                        try:
                            reminder.reminder_date = (order_date +(order_product.quantity * timedelta(days=int(product.reorder_days))) -timedelta(days=shop.buffer_time))

                        except Exception as e:
                            db.rollback()
                            raise HTTPException(status_code=500, detail=f"Error parsing order date: {str(e)}")
            reorder_details.append({
                    "product_id": existing_product.product_id,
                    "shop_id": existing_product.shop_id,
                    "shopify_product_id": existing_product.shopify_product_id,
                    "shopify_variant_id": int(existing_product.shopify_variant_id),
                    "title": existing_product.title,
                    "productImage":existing_product.image_url,
                    "reorder_days": existing_product.reorder_days,
                    "created_at": existing_product.created_at,
                })
            

    try:
        db.commit()
        db.refresh(existing_product)
        for reminder in reminders:
            db.refresh(reminder)
        
        return reorder_details
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating product: {str(e)}")

@router.post("/shops")
async def create_shop(shop: ShopCreate, db: Session = Depends(get_db),background_tasks: BackgroundTasks = None,):

    # Check if shop already exists by domain or email
    existing_shop = db.query(Shop).filter(Shop.shopify_domain == shop.shopify_domain).first()
    print(existing_shop)
    
    if existing_shop:
        if existing_shop.is_deleted:
            existing_shop.shop_name = shop.shop_name
            existing_shop.shop_logo = shop.shop_logo
            existing_shop.email = shop.email
            existing_shop.host = shop.host
            existing_shop.accesstoken = shop.accessToken
            existing_shop.message_template_id=None
            existing_shop.is_deleted = False
            existing_shop.plan='Free'
            existing_shop.order_flag=False
            existing_shop.modified_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_shop)

            background_tasks.add_task(send_email_template,to=shop.email,sender=TRIGGER_EMAIL_FROM,template_name="WelcomeTemplate",store_name=shop.shop_name,reply_to=REPLY_TO_EMAIL)

            return {"message": "Shop reactivated successfully", "shop_id": existing_shop.shop_id,
                    "buffer_time":existing_shop.buffer_time,
                    "email":existing_shop.email,
                    "template_id":existing_shop.message_template_id,
                    "logo":existing_shop.shop_logo,
                    "coupon":existing_shop.coupon,
                    "discount":existing_shop.discountpercent}
        else:
            return {"message": "Shop Already Created", "shop_id": existing_shop.shop_id,
                    "buffer_time":existing_shop.buffer_time,
                    "email":existing_shop.email,
                    "template_id":existing_shop.message_template_id,
                    "logo":existing_shop.shop_logo,
                    "coupon":existing_shop.coupon,
                    "discount":existing_shop.discountpercent}
    
    # Create a new Shop instance
    new_shop = Shop(
        shopify_domain=shop.shopify_domain,
        shop_name=shop.shop_name,
        shop_logo=shop.shop_logo,
        email=shop.email,
        host=shop.host,
        accesstoken=shop.accessToken,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db.add(new_shop)
    db.commit()
    db.refresh(new_shop)

    background_tasks.add_task(send_email_template,to=new_shop.email,sender=TRIGGER_EMAIL_FROM,template_name="WelcomeTemplate",store_name=shop.shop_name,reply_to=REPLY_TO_EMAIL)
    return {"message": "Shop created successfully",
            "shop_id": new_shop.shop_id,
            "buffer_time":new_shop.buffer_time,
            "email":new_shop.email,
            "template_id":new_shop.message_template_id,
            "logo":new_shop.shop_logo,
            "coupon":new_shop.coupon,
            "discount":new_shop.discountpercent
            }


@router.get("/shops/{shop_domain}")
async def get_shop(shop_domain: str, db: Session = Depends(get_db)):
    # Query the database for the shop by shop_id
    shop = db.query(Shop).filter((Shop.shopify_domain == shop_domain)&(Shop.is_deleted == False)).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    product_count = db.query(Products).filter((Products.shop_id == shop.shop_id) & (Products.is_deleted == False)).count()
    # Return shop details
    return {
        "shop_id": shop.shop_id,
        "buffer_time":shop.buffer_time,
        "email":shop.email,
        "template_id":shop.message_template_id,
        "logo":shop.shop_logo,
        "coupon":shop.coupon,
        "discount":shop.discountpercent,
        "createdAt":shop.created_at,
        "product_count":product_count,
        "order_sync_count":shop.order_sync_count
    }

@router.patch("/shops/{shop_id}")
async def update_shop(shop_id: int,plan:str, db: Session = Depends(get_db)):
    # Fetch the existing shop by shop_id
    existing_shop = db.query(Shop).filter((Shop.shop_id == shop_id)&(Shop.is_deleted == False)).first()
    
    if not existing_shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # if shop.email:
    #     existing_shop.email = shop.email
    existing_shop.plan=plan
    existing_shop.modified_at = datetime.utcnow()

    # Commit the changes to the database
    db.commit()
    db.refresh(existing_shop)

    return {"message": "Shop updated successfully", "shop_id": existing_shop.shop_id}


@router.delete("/webhook/uninstallApp")
async def delete_shop(shop_domain: str, db: Session = Depends(get_db)):
    try:
        shop = db.query(Shop).filter((Shop.shopify_domain == shop_domain)&(Shop.is_deleted == False)).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")  
        message_template = db.query(Message_Template).filter((Message_Template.message_template_id == shop.message_template_id) |(Message_Template.shop_name == shop.shopify_domain)).first()

        if message_template and not message_template.is_deleted:
            # db.delete(message_template)
            message_template.is_deleted= True
            message_template.modified_at = datetime.utcnow()

        orders = db.query(Orders).filter_by(shop_id=shop.shop_id, is_deleted=False).all()
        for order in orders:
            order.is_deleted = True
            order.modified_at = datetime.utcnow()
            order_products = db.query(OrderProduct).filter_by(order_id = order.order_id, is_deleted=False).all()
            for op in order_products:
                op.is_deleted = True
                op.modified_at = datetime.utcnow()
            db.query(Reminder).filter_by(order_id = order.order_id, is_deleted=False).update({"is_deleted": True,"modified_at": datetime.utcnow()})
            
        db.query(ShopCustomer).filter(ShopCustomer.shop_id == shop.shop_id).update({"is_deleted": True,"modified_at": datetime.utcnow()})   
        db.query(Products).filter(Products.shop_id == shop.shop_id).update({"is_deleted": True,"updated_at": datetime.utcnow()})
        shop.is_deleted=True
        shop.modified_at = datetime.utcnow()
        db.commit()
        return {"message": "Deleted Successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")


@router.post("/webhook/orderfullfilled")
async def receive_order(order: OrderPayload, db: Session = Depends(get_db)):
    try:
    # Process the order payload
        print(f"Received order: {order}")
        shop = db.query(Shop).filter((Shop.shopify_domain == order.shop)&(Shop.is_deleted == False)).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        customer=db.query(ShopCustomer).filter((ShopCustomer.shopify_id == order.customer_id)&(ShopCustomer.is_deleted == False)).first()
        print(customer)
        order_date = datetime.strptime(order.order_date, "%Y-%m-%dT%H:%M:%S%z")
        for line_item in order.line_items:

            print(type(order.order_date))
            print(type(order_date))
            product = db.query(Products).filter((Products.shopify_product_id == line_item.product_id)&(Products.shopify_variant_id == str(line_item.variant_id))&(Products.is_deleted == False)).first()
            if not product:
                print(f"Skipped: product not found (product_id={line_item.product_id}, variant_id={line_item.variant_id})")
                continue

            if not customer:
                new_customer=ShopCustomer(
                    shopify_id=order.customer_id,
                    email=order.customer_email,
                    mobile=order.customer_phone,
                    first_name=order.customer_name,
                    billing_mobile_no=order.billing_phone,
                    shipping_mobile_no=order.shipping_phone,
                    shop_id=shop.shop_id
                )
                db.add(new_customer)
                db.flush() 
                customer = new_customer
        # Add the order
            new_order = Orders(
                shop_id=shop.shop_id,
                shopify_order_id=order.shopify_order_id,
                customer_id=customer.shop_customer_id,
                order_date=order_date,  # Ensure datetime conversion
                total_amount=line_item.price,
                status=line_item.status,
                order_source=order.order_source,  # Ensure 'status' exists in line_item
            )
            db.add(new_order)
            db.flush() 

        # Add the order product
            new_order_product = OrderProduct(
                order_id=new_order.order_id,
                shopify_product_id=line_item.product_id,
                quantity=line_item.quantity,
                shopify_variant_id=line_item.variant_id,
            )
            db.add(new_order_product)
            
        # Add reminder entry
    
            print(type(line_item.quantity))
            print(type(timedelta(days=int(product.reorder_days))))
            print(type(shop.buffer_time))
            reminder_date = order_date + (line_item.quantity * timedelta(days=int(product.reorder_days))) - timedelta(shop.buffer_time)
            print(type(reminder_date))
            create_reminder_entry = Reminder(
                customer_id=customer.shop_customer_id,
                product_id=product.product_id,
                order_id=new_order.order_id,
                reminder_date=reminder_date,
                shop_id=order.shop,
                product_title=product.title,
                product_quantity=line_item.quantity,
                image_url=product.image_url
                
            )
            db.add(create_reminder_entry)

        db.commit()
        return {"message": "Order received successfully"}
        # Add the new product to the database
          # Refresh to get the ID
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating product: {e}")

    

@router.post("/orderSync")
async def ordersync(pastOrders:List[OrderPayload],db: Session = Depends(get_db)):
    try:
    # Process the order payload
        print(f"Received order: {pastOrders}")
        orders_created = 0
        for order in pastOrders:
            shop = db.query(Shop).filter((Shop.shopify_domain == order.shop)&(Shop.is_deleted == False)).first()
            if not shop:
                raise HTTPException(status_code=404, detail="Shop not found")
            customer=db.query(ShopCustomer).filter((ShopCustomer.shopify_id == order.customer_id)&(ShopCustomer.is_deleted == False)).first()
            print(customer)
            
            for line_item in order.line_items:
                # Check product in database
                print(type(order.order_date))
                order_date = datetime.strptime(order.order_date, "%Y-%m-%dT%H:%M:%S%z")
                print(type(order_date))
                product = db.query(Products).filter((Products.shopify_product_id == line_item.product_id)&(Products.is_deleted == False)).first()
                if not product:
                    print(f"Skipped: product not found (product_id={line_item.product_id}, variant_id={line_item.variant_id})")
                    continue
                if not customer:
                    new_customer=ShopCustomer(
                        shopify_id=order.customer_id,
                        email=order.customer_email,
                        mobile=order.customer_phone,
                        first_name=order.customer_name,
                        billing_mobile_no=order.billing_phone,
                        shipping_mobile_no=order.shipping_phone,
                        shop_id=shop.shop_id

                    )
                    db.add(new_customer)
                    db.flush()
                    customer = new_customer
            # Add the order
                new_order = Orders(
                    shop_id=shop.shop_id,
                    shopify_order_id=order.shopify_order_id,
                    customer_id=customer.shop_customer_id,
                    order_date=order_date,  # Ensure datetime conversion
                    total_amount=line_item.price,
                    status=line_item.status,  # Ensure 'status' exists in line_item
                )
                db.add(new_order)
                db.flush()
                orders_created += 1
                

            # Add the order product
                new_order_product = OrderProduct(
                    order_id=new_order.order_id,
                    shopify_product_id=line_item.product_id,
                    quantity=line_item.quantity,
                    shopify_variant_id=line_item.variant_id,
                )
                db.add(new_order_product)
                
                print(type(line_item.quantity))
                print(type(timedelta(days=int(product.reorder_days))))
                print(type(shop.buffer_time))
                reminder_date = order_date + (line_item.quantity * timedelta(days=int(product.reorder_days))) - timedelta(shop.buffer_time)
                print(type(reminder_date))
                create_reminder_entry = Reminder(
                    customer_id=customer.shop_customer_id,
                    product_id=product.product_id,
                    order_id=new_order.order_id,
                    reminder_date=reminder_date,
                    shop_id=order.shop,
                    product_title=product.title,
                    product_quantity=line_item.quantity,
                    image_url=product.image_url
                )
                db.add(create_reminder_entry)

        shop.order_flag=True
        db.commit()
        db.refresh(shop)
        print("orders_inserted:",orders_created)
        return {"message": "Order synced Successfully","orders_inserted": orders_created} 
            
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating product: {e}")

       

@router.post("/save-settings")
async def save_settings(emailTemplateSettings: EmailTemplateSettings, db: Session = Depends(get_db)):
    
    if emailTemplateSettings:
        print(emailTemplateSettings)
        shop = db.query(Shop).filter((Shop.shopify_domain == emailTemplateSettings.shop_name)&(Shop.is_deleted == False)).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        
        if not shop.message_template_id:

            new_message_template = Message_Template(
                                        message_template=' ',
                                        message_channel = "email",
                                        shop_name=emailTemplateSettings.shop_name,
                                        fromname = emailTemplateSettings.fromName,
                                        fromemail=emailTemplateSettings.fromEmail,
                                        subject = emailTemplateSettings.subject,
                                        body_template=DEFAULT_EMAIL_TEMPLATE,
                                        created_at=datetime.utcnow(),
                                        modified_at=datetime.utcnow(),
                                        )
            db.add(new_message_template)
            db.commit()
            db.refresh(new_message_template)
            shop.message_template_id=new_message_template.message_template_id
        else:
            update_message_Template=db.query(Message_Template).filter(Message_Template.message_template_id == shop.message_template_id).first()
            if emailTemplateSettings.fromName:
                update_message_Template.fromname=emailTemplateSettings.fromName
            if emailTemplateSettings.fromEmail:
                update_message_Template.fromemail=emailTemplateSettings.fromEmail
            if emailTemplateSettings.subject:
                update_message_Template.subject = emailTemplateSettings.subject
            update_message_Template.modified_at=datetime.utcnow()
            db.commit()
            db.refresh(update_message_Template)

        if emailTemplateSettings.bufferTime:
            shop.buffer_time=emailTemplateSettings.bufferTime
        shop.coupon=emailTemplateSettings.coupon

        shop.discountpercent=emailTemplateSettings.discountPercent
        
        
        db.commit()
        db.refresh(shop)
        return {"Your email template has been saved successfully! All future reminders will use this updated template to engage your customers." }

    else:
        raise HTTPException(status_code=400, detail="Invalid request payload")

@router.get("/get-settings")
async def get_settings(shop_name: str , db: Session = Depends(get_db),s3: BaseClient = Depends(get_s3_client)):
    # Fetch the shop based on shop_name
    shop = db.query(Shop).filter((Shop.shopify_domain == shop_name)&(Shop.is_deleted == False)).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    if shop.shop_logo:
        s3_path = f"{shop.shop_id}/{shop.shop_logo}"
        # client_action='get_object'
        # url = s3.generate_presigned_url(
        #      client_action, Params={"Bucket": AWS_BUCKET, "Key": s3_path}, ExpiresIn = 3600
        # )
        url = f"https://s3.{AWS_REGION}.amazonaws.com/{AWS_BUCKET}/{s3_path}"
    

    # General settings
        general_settings = {
            "bannerImage":url,
            "bannerImageName":shop.shop_logo,
            "syncStatus":shop.order_flag
        }
    else:
        general_settings = {
            "syncStatus":shop.order_flag
        }

    # Email template settings
    email_template = db.query(Message_Template).filter((Message_Template.shop_name == shop_name)&(Message_Template.is_deleted == False)).first()
    if email_template:
        email_template_settings = {
            "coupon": shop.coupon,
            "bufferTime": shop.buffer_time,
            "discountPercent": shop.discountpercent,
            "fromName": email_template.fromname,
            "fromEmail" : email_template.fromemail,
            "subject": email_template.subject,
            "message_channel": email_template.message_channel,
        }
        print(email_template_settings)
    else:
        email_template_settings = {"bufferTime": shop.buffer_time}

    settings_data={ "email_template_settings":email_template_settings,"general_settings":general_settings}
    print(settings_data)
    return settings_data

@router.post("/upload_to_aws/{shop_name}")
async def upload_file_to_server(shop_name:str,db:db_dependency,s3: BaseClient = Depends(get_s3_client),bannerImage: UploadFile = File(...)):
    try:
        print(shop_name)
        print(bannerImage.filename)
        shop = db.query(Shop).filter((Shop.shopify_domain ==shop_name)&(Shop.is_deleted == False)).first()
        if not bannerImage:
            raise HTTPException(status_code=400, detail="No file provided")
        folder_name = f"{shop.shop_id}/{bannerImage.filename}"
        print(folder_name)
        print(AWS_BUCKET)
        s3.upload_fileobj(bannerImage.file, AWS_BUCKET, folder_name)
        
        shop.shop_logo=bannerImage.filename
        db.commit()
        db.refresh(shop)
        return {"Your Logo Image has been uploaded successfully!" }
    except HTTPException as e:
        raise HTTPException(status_code=400, detail='File Type not Supported')   
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail='Something went wrong')


@router.delete("/webhook/product_delete")
async def delete_product(payload:DeletePayload, db: Session = Depends(get_db)):
    try:
    # Process the order payload
        print(f"Received order: {payload.product_id}")
        shop = db.query(Shop).filter((Shop.shopify_domain == payload.shop)&(Shop.is_deleted == False)).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        products = db.query(Products).filter((Products.shopify_product_id == payload.product_id)).all()
        if not products:
            return {"message": "No Products Found", "payload": payload}
        for product in products:
            reminder=db.query(Reminder).filter((Reminder.product_id==product.product_id)).first()
            if reminder:
                db.delete(reminder)
                email_template=f'''<!DOCTYPE html>
                                    <html lang="en">
                                    <head>
                                        <meta charset="UTF-8">
                                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                        <title>Product Deletion Notification</title>
                                        <style>
                                            body {{
                                                font-family: Arial, sans-serif;
                                                line-height: 1.6;
                                                color: #333;
                                                margin: 20px;
                                            }}
                                            .container {{
                                                max-width: 600px;
                                                margin: auto;
                                                padding: 20px;
                                                border: 1px solid #ddd;
                                                border-radius: 8px;
                                                background-color: #f9f9f9;
                                            }}
                                            h1 {{
                                                font-size: 20px;
                                                color: #444;
                                            }}
                                            p {{
                                                margin: 10px 0;
                                            }}
                                            .footer {{
                                                margin-top: 20px;
                                                font-size: 14px;
                                                color: #666;
                                            }}
                                        </style>
                                    </head>
                                    <body>
                                        <div class="container">
                                            <h1>Notification: Product Deletion and Impact on Reorder Emails</h1>
                                            <p>Dear <strong>{shop.shop_name}</strong>,</p>
                                            <p>We hope this email finds you well.</p>
                                            <p>This is to inform you that the product <strong>{reminder.product_title}</strong> has been deleted from your Shopify store. As a result, our <strong>{shop.shop_name}</strong> will no longer be able to send reorder reminder emails to customers for this product.</p>
                                            <p>We want to ensure that you are aware of this change, as it may impact your customer engagement and sales for this product. If this deletion was unintentional, we recommend restoring the product to maintain seamless communication with your customers.</p>
                                            <p>If you have any questions or need assistance, please don’t hesitate to reach out to us. We’re here to help.</p>
                                            <p>Thank you for using <strong>{shop.shop_name}</strong>!</p>
                                            <div class="footer">
                                            <p>Powered by ReOrder Reminder Pro</p>
                                            <p>Need help? <a href="mailto:support@yourstore.com">support@yourstore.com</a></p>
                                            </div>
                                        </div>
                                    </body>
                                    </html>
                                    '''
                send_email(
                to=shop.email,
                subject='Notification: Product Deletion and Impact on Reorder Emails',
                body=email_template,
                sender_email='ReorderPro',
                sender_name=shop.shop_name
                )
            db.delete(product)
            db.commit()
            return {"message": "Deleted Successfully", "payload": payload}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")

@router.delete("/webhook/product_update")
async def update_product(payload:Request,db:Session=Depends(get_db)) :
    try:
        payload = await payload.json()
        print(payload)

        product_id = payload.get("product_id")  # Fix key mismatch
        shop_domain = payload.get("shop")
        variants = payload.get("variants") or [] 

        if not product_id or not shop_domain:
            raise HTTPException(status_code=400, detail="Missing product ID or shop domain")

        shop = db.query(Shop).filter((Shop.shopify_domain == shop_domain)&(Shop.is_deleted == False)).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        # Get products from the database
        products = db.query(Products).filter((Products.shopify_product_id == product_id)&(Products.is_deleted == False)).all()
        if not products:
            return {"message": "No Products Found", "payload": payload}

        # Get variant IDs from the database
        # payload_variant_ids = {variant["id"] for variant in variants}
        payload_variant_ids = {str(variant) for variant in variants}
        db_variant_ids = {product.shopify_variant_id for product in products}
        print(payload_variant_ids)
        print(db_variant_ids)
        variants_to_delete = db_variant_ids - payload_variant_ids
       
        print(variants_to_delete)
        # Delete Variants from Database
        if variants_to_delete:
            for variant in variants_to_delete:
                product_to_delete=db.query(Products).filter((Products.shopify_product_id==str(product_id))&(Products.shopify_variant_id==variant)&(Products.is_deleted == False)).first()
                if product_to_delete:
                    db.delete(product_to_delete)
            


        # Delete Product and Reminder if needed
        for product in products:
            reminder = db.query(Reminder).filter((Reminder.product_id == product.product_id)&(Reminder.is_deleted == False)).first()
            if reminder:
                db.delete(reminder)
                # Send email notification
                email_template = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Product Deletion Notification</title>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            margin: 20px;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: auto;
                            padding: 20px;
                            border: 1px solid #ddd;
                            border-radius: 8px;
                            background-color: #f9f9f9;
                        }}
                        h1 {{
                            font-size: 20px;
                            color: #444;
                        }}
                        p {{
                            margin: 10px 0;
                        }}
                        .footer {{
                            margin-top: 20px;
                            font-size: 14px;
                            color: #666;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Notification: Product Deletion and Impact on Reorder Emails</h1>
                        <p>Dear <strong>{shop.shop_name}</strong>,</p>
                        <p>We hope this email finds you well.</p>
                        <p>This is to inform you that the product <strong>{reminder.product_title}</strong> has been deleted from your Shopify store. As a result, our <strong>{shop.shop_name}</strong> will no longer be able to send reorder reminder emails to customers for this product.</p>
                        <p>We want to ensure that you are aware of this change, as it may impact your customer engagement and sales for this product. If this deletion was unintentional, we recommend restoring the product to maintain seamless communication with your customers.</p>
                        <p>If you have any questions or need assistance, please don’t hesitate to reach out to us. We’re here to help.</p>
                        <p>Thank you for using <strong>{shop.shop_name}</strong>!</p>
                        <div class="footer">
                            <p>Powered by ReOrder Reminder Pro</p>
                            <p>Need help? <a href="mailto:support@yourstore.com">support@yourstore.com</a></p>
                        </div>
                    </div>
                </body>
                </html>
                """
                try:
                    send_email(
                        to=shop.email,
                        subject="Notification: Product Deletion and Impact on Reorder Emails",
                        body=email_template,
                        sender_email="ReOrderReminderPro@decagrowth.com",
                        sender_name=shop.shop_name
                    )
                except Exception as e:
                    print(f"Email sending failed: {e}")



        db.commit()
        return {"message": "Deleted Successfully", "deleted_variants": list(variants_to_delete), "payload": payload}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")


@router.get("/email-status_count")
async def getScheduledEmailCount(product_id: str,variant_id: str,shop_id: int,db:Session=Depends(get_db)) :
    try:
        product=(db.query(Products).filter((Products.shopify_product_id == product_id) &(Products.shopify_variant_id == variant_id) &(Products.shop_id == shop_id)&(Products.is_deleted == False)).first())
        print(product)
        if not product:
            return {
                "Scheduled_Count": 0,
                "Dispatched_Count": 0,
                "Reorder Email Source":0,
            }
        scheduled_email_count=db.query(Reminder).filter((Reminder.status=='Pending')&(Reminder.product_id==product.product_id)&(Reminder.is_deleted == False)).count()
        dispatched_email_count=db.query(Reminder).filter((Reminder.status=='Send')&(Reminder.product_id==product.product_id)&(Reminder.is_deleted == False)).count()
        product_reminders=db.query(Reminder).filter((Reminder.product_id==product.product_id)&(Reminder.is_deleted == False)).all()
        order_source_total_count = sum(
                                    db.query(Orders)
                                    .filter((Orders.order_id == reminder.order_id) & (Orders.order_source == True)&(Orders.is_deleted == False))
                                    .count()
                                    for reminder in product_reminders
                            )

        
        return {
                "Scheduled_Count": scheduled_email_count,
                "Dispatched_Count": dispatched_email_count,
                "Reorder_Email_Source":order_source_total_count,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fetch Failed: {e}")

@router.post("/test-email-reminder")
async def testEmailReminder(product_id:str,variant_id:str,shop_id:int,db:Session=Depends(get_db)):
    
    try:
        shop = (db.query(Shop).filter(Shop.shop_id ==shop_id, Shop.is_deleted == False).first())
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        message_template = (db.query(Message_Template).filter(Message_Template.shop_name == shop.shopify_domain,Message_Template.is_deleted == False,).first())
        if not message_template:
            raise HTTPException(status_code=404, detail="Message template not found")

        reminder_product=db.query(Products).filter((Products.shopify_product_id==product_id)&(Products.shopify_variant_id==variant_id)&(Products.shop_id == shop_id)&(Products.is_deleted==False)).first()
        if not reminder_product:
            raise HTTPException(status_code=404, detail="Product not found")
        quantity=1
        shopName = shop.host if shop.host else shop.shopify_domain
        if shop.plan=='Free':
            url=f"https://rrpapp.decagrowth.com/redirect?shop_domain={shopName}&variant_id={reminder_product.shopify_variant_id}&quantity={quantity}"
        else:
            url=f"https://rrpapp.decagrowth.com/redirect?shop_domain={shopName}&variant_id={reminder_product.shopify_variant_id}&quantity={quantity}&discount={shop.coupon}"
        reminder_days = (1 * int(reminder_product.reorder_days)) - int(shop.buffer_time)
        placeholders={"first_name": shop.shop_name,
                        "product_name": reminder_product.title,
                        "shop":shop.shop_name,
                        "product_image":reminder_product.image_url,
                        "quantity": quantity,
                        "mail_to":shop.email,
                        "remaining_days": reminder_days,
                        "reorder_url":url,
                        "image_path":f"https://s3.{AWS_REGION}.amazonaws.com/{AWS_BUCKET}/{shop.shop_id}/{shop.shop_logo}",
                        "shop": shop.shop_name,
                        "plan": shop.plan,
                        "coupon": shop.coupon or "",
                        "discountpercent": shop.discountpercent or "0"

                                }          
        template_str = message_template.body_template
        template = Template(template_str)
        email_template = template.render(**placeholders)
        text_template = """ Hi {{ first_name }},\n
            Just a quick reminder - based on your last purchase, you might be running low on {{ product_name }}.\n
            Reorder here: {{ reorder_url }}\n
            {% if plan == "PRO" and coupon %}Use coupon code {{ coupon }} - {{ discountpercent }}{% endif %}\n
            {{ shop }} | {{ mail_to }} """

        email_text = Template(text_template).render(**placeholders)
        send_email(
                      to=shop.email,
                      subject=f"{message_template.subject}-Test Mail",
                      html_body=email_template,
                      plain_body=email_text,
                      sender_email="ReOrderReminderPro@decagrowth.com",
                      sender_name=message_template.fromname,
                      reply_to=message_template.fromemail,
                  )
        return {"message": f"Your test email has been sent successfully to {shop.email}"}
    except ApiException as e:
        print(f"Error sending email: {e}")

@router.post("/trigger_emails")
async def triggerEmails(data:TriggerEmailRequest,db:Session=Depends(get_db)):
  
    try:
        response=send_email_template(data.to, TRIGGER_EMAIL_FROM, data.template_name, data.store_name,REPLY_TO_EMAIL)
        return {"message": "Email sent", "message_id": response["MessageId"]}
    except Exception as e:
        print("Error sending templated email:", e)
        return {"error": str(e)}

@router.post("/create_template")
async def createTemplate(data: TemplateCreateRequest,db:Session=Depends(get_db)):
    try:
        result = create_email_template(data.templatename, data.subject, data.html_body)
        return result
    except client.exceptions.AlreadyExistsException:
        raise HTTPException(status_code=400, detail="Template already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_template")
async def updateTemplate(data: TemplateCreateRequest,db:Session=Depends(get_db)):
    client = boto3.client('sesv2',region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    TEXT_TEMPLATE = """Hello {{store_name}},

            Welcome to ReOrder Reminder Pro!

            Thanks for installing ReOrder Reminder Pro. We're excited to help you automate reorder emails and boost your repeat sales.

            🎥 Watch the demo video: https://www.youtube.com/watch?v=rJFaR6rXD68

            🌐 Visit our website: https://reorderreminderpro.decagrowth.com/#faq

            If you have any questions, just reply to this email or contact us via WhatsApp in the app.

            Best regards,  
            Leo  
            Founder, DecaGrowth"""
    try:
        response = client.update_email_template(
            TemplateName=data.templatename,
            TemplateContent={
                "Subject": data.subject,
                "Text": TEXT_TEMPLATE,
                "Html": data.html_body
            }
        )
        return {"message": "Template updated successfully", "template": data.templatename}
    except client.exceptions.AlreadyExistsException:
        return {"error": f"Template '{templatename}' already exists"}
    except Exception as e:
        return {"error": str(e)}
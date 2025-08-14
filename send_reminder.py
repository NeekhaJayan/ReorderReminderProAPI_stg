from fastapi import FastAPI
from sqlalchemy.orm import Session
from database import SessionLocal
from dependencies import send_email
from models import Products, Shop, Orders, ShopCustomer, OrderProduct, Reminder, Message_Template
from datetime import datetime
from sqlalchemy import func
import os
from jinja2 import Template

app = FastAPI()


AWS_BUCKET=os.getenv("AWS_BUCKET")
AWS_REGION=os.getenv("AWS_REGION_NAME")
# AWS_REGION = "ap-south-1"



def send_reminders():
    # Create a database session
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        print(datetime.utcnow())
        reminders = (
            db.query(Reminder)
            .filter(func.date(Reminder.reminder_date) == today, Reminder.is_deleted == False ,Reminder.status=="Pending")
            .all()
        )
        print(reminders)
        if not reminders:
            print("No reminders to process today.")
            return

        for reminder in reminders:
            try:
                reminder_product=db.query(Products).filter((Products.product_id==reminder.product_id)&(Products.is_deleted==False)).first()
               
                

                if reminder_product:
                  customer = (
                      db.query(ShopCustomer)
                      .filter(
                          ShopCustomer.shop_customer_id == reminder.customer_id,
                          ShopCustomer.is_deleted == False,
                      )
                      .first()
                  )

                  shop = (
                      db.query(Shop)
                      .filter(Shop.shopify_domain == reminder.shop_id, Shop.is_deleted == False)
                      .first()
                  )

                  message_template = (
                      db.query(Message_Template)
                      .filter(
                          Message_Template.shop_name == shop.shopify_domain,
                          Message_Template.is_deleted == False,
                      )
                      .first()
                  )
                  
                  order=db.query(Orders).filter(Orders.order_id==reminder.order_id).first()
                  if not customer or not shop or not message_template:
                      print(
                          f"Skipping reminder {reminder.reminder_id}: Missing required data."
                      )
                      continue
                
                  shopName = shop.host if shop.host else shop.shopify_domain
                  if shop.plan=='Free':
                    url=f"https://rrpapp.decagrowth.com/redirect?shop_domain={shopName}&variant_id={reminder_product.shopify_variant_id}&quantity={reminder.product_quantity}"
                  else:
                    url=f"https://rrpapp.decagrowth.com/redirect?shop_domain={shopName}&variant_id={reminder_product.shopify_variant_id}&quantity={reminder.product_quantity}&discount={shop.coupon}"
                  print(url)
                  reminder_days = (reminder.product_quantity * int(reminder_product.reorder_days)) - int(shop.buffer_time)
                  placeholders={"first_name": customer.first_name,
                                "product_name": reminder.product_title,
                                "shop":shop.shop_name,
                                "product_image":reminder.image_url,
                                "quantity": reminder.product_quantity,
                                "mail_to":shop.email,
                                "remaining_days": reminder_days,
                                "reorder_url":url,
                                "image_path":f"https://s3.{AWS_REGION}.amazonaws.com/{AWS_BUCKET}/{shop.shop_id}/{shop.shop_logo}",
                                "shop": shop.shop_name,
                                "plan": shop.plan,
                                "coupon": shop.coupon or "",
                                "discountpercent": shop.discountpercent or "0"

                                }
                  # https://deca-development-store.myshopify.com/cart/clear?return_to=/cart/add?items[][id]=42034558533741&items[][quantity]=1&return_to=/checkout?discount=EXTRA5
                  print(customer.first_name,message_template.fromname)
                
                  
                  template_str = message_template.body_template
                  template = Template(template_str)
                  email_template = template.render(**placeholders)
                  senderName =shop.shop_name
                  text_template = """ Hi {{ first_name }},\n
            Just a quick reminder - based on your last purchase, you might be running low on {{ product_name }}.\n
            Reorder here: {{ reorder_url }}\n
            {% if plan == "PRO" and coupon %}Use coupon code {{ coupon }} - {{ discountpercent }}{% endif %}\n
            {{ shop }} | {{ mail_to }} """

                  email_text = Template(text_template).render(**placeholders)
                  send_email(
                      to=customer.email,
                      subject=message_template.subject,
                      html_body=email_template,
                      plain_body=email_text,
                      sender_email="ReOrderReminderPro@decagrowth.com",
                      sender_name=message_template.fromname,
                      reply_to=message_template.fromemail,
                  )

                
                  reminder.status='Send'
                  db.commit()
                 
                    

            except Exception as e:
                print(f"Error processing reminder {reminder.reminder_id}: {e}")

    finally:
        # Ensure the database session is closed
        db.close()


# Automatically execute reminders when run directly
if __name__ == "__main__":
    send_reminders()

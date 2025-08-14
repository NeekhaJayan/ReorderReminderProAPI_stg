import boto3
from botocore.exceptions import ClientError
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from constants import AWS_BUCKET,AWS_REGION,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY,CONFIGURATION_SET
import json

s3_resource = boto3.resource('s3',region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
BUCKET=s3_resource.Bucket(AWS_BUCKET)

def get_s3_client():
    return boto3.client('s3',region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

def get_sesv2_client():
    return boto3.client('sesv2',region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

def send_email(to, subject,html_body, plain_body, sender_email,sender_name,reply_to):
    # CONFIGURATION_SET = "my-first-configuration-set"
    SENDER=f'{sender_name}<{sender_email}>'
    CHARSET = "UTF-8"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SENDER
    msg['To'] = to
    msg['Reply-To'] = reply_to

    msg.attach(MIMEText(plain_body, 'plain', CHARSET))
    msg.attach(MIMEText(html_body, 'html', CHARSET))
    
    client = boto3.client('ses',region_name=AWS_REGION,aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    try:
    
        response = client.send_raw_email(
            Source=SENDER,
            Destinations=[to],
            RawMessage={'Data': msg.as_string()},
            ConfigurationSetName=CONFIGURATION_SET
        )
        print("Email sent! Message ID:", response['MessageId'])
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def send_email_template(to,sender,template_name,store_name,reply_to):
    
    template_data = {
        "store_name": store_name
    }
    client = get_sesv2_client()
    try:
        response = client.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [to]},
            Content={
                "Template": {
                    "TemplateName": template_name,
                    "TemplateData": json.dumps(template_data)
                }
            },
            ReplyToAddresses=reply_to,
            ConfigurationSetName=CONFIGURATION_SET
        )
        print("Templated email sent. Message ID:", response["MessageId"])
        return response
    except Exception as e:
        print("Error sending templated email:", e)
        return {"error": str(e)}

def create_email_template(templatename,subject,html_body):

    client = get_sesv2_client()
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
        response = client.create_email_template(
                TemplateName=templatename,
                TemplateContent={
                    "Subject": subject,
                    "Text": TEXT_TEMPLATE,
                    "Html": html_body
                }
            )
        
        return {"message": "Template created successfully", "template": templatename}
    except client.exceptions.AlreadyExistsException:
        return {"error": f"Template '{templatename}' already exists"}
    except Exception as e:
        return {"error": str(e)}
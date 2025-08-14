import os 

AWS_BUCKET=os.getenv("AWS_BUCKET")
AWS_ACCESS_KEY_ID=os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY=os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION=os.getenv("AWS_REGION")
CONFIGURATION_SET = "my-first-configuration-set"
TRIGGER_EMAIL_FROM='ReOrderReminderPro<ReOrderReminderPro@decagrowth.com>'
REPLY_TO_EMAIL = ["ReOrderReminderPro@decagrowth.com"]
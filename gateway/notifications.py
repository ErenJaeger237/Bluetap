import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# 🔧 CONFIGURATION (EDIT THIS PART)
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# REPLACE THESE TWO LINES WITH YOUR REAL INFO
SENDER_EMAIL = "jordanebua2@gmail.com"        # <--- Your REAL email
SENDER_PASSWORD = "yjax pged yclo hrfh"      # <--- Your 16-char APP PASSWORD

# ==========================================

def send_real_email(to_email, otp_code):
    # We removed the safety check so it tries to send now
    subject = "Bluetap Login Code"
    body = f"""
    Welcome to Bluetap Cloud!
    
    Your secure login code is: {otp_code}
    
    This code expires in 5 minutes.
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail Server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        
        print(f"📧 EMAIL SENT to {to_email}")
        return True
    except Exception as e:
        print(f"❌ EMAIL FAILED: {e}")
        print("   (Did you use an App Password? Regular passwords often fail.)")
        return False

def send_notification(contact, otp):
    # If it looks like an email, send email
    if "@" in contact:
        return send_real_email(contact, otp)
    else:
        print(f"📱 [SMS SIMULATION] Sending OTP {otp} to {contact}")
        return True
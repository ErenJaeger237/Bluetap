import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# 🔧 CONFIGURATION (YOU MUST CHANGE THIS)
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your_email@gmail.com"        # <--- PUT YOUR GMAIL HERE
SENDER_PASSWORD = "xxxx xxxx xxxx xxxx"      # <--- PUT YOUR APP PASSWORD HERE
# ==========================================

def send_real_email(to_email, otp_code):
    if "your_email" in SENDER_EMAIL:
        print("⚠️ [CONFIG ERROR] You must edit gateway/notifications.py with your real email credentials!")
        return False

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
        return False

def send_notification(contact, otp):
    # If it looks like an email, send email
    if "@" in contact:
        return send_real_email(contact, otp)
    else:
        # Placeholder for SMS (Twilio would go here)
        print(f"📱 [SMS SIMULATION] Sending OTP {otp} to {contact}")
        return True
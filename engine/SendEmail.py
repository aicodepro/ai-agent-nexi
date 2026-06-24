import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pyttsx3
import eel
def send_email(recipient, subject, content):
    try:
        sender_email = "Darshyadav07@gmail.com"
        sender_password = "auxq ocdt fchh euvv"

        if not sender_email or not sender_password:
            #speak("Email or password not set in environment variables.")
            print("Email or password not set in environment variables.")

            return

        # Create the email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Subject'] = subject

        msg.attach(MIMEText(content, 'plain'))

        # Connect to the server and send the email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient, text)
        server.quit()

        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")



"""Communication — email and location search."""

import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(recipient: str, subject: str, content: str) -> dict:
    sender = os.getenv("NEXI_EMAIL_ADDRESS", "")
    password = os.getenv("NEXI_EMAIL_PASSWORD", "")
    if not sender or not password:
        return {"handled": False, "message": "Email not configured. Set NEXI_EMAIL_ADDRESS and NEXI_EMAIL_PASSWORD."}

    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain"))
    except Exception as e:
        return {"handled": False, "message": f"Failed to create email: {e}"}

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        return {"handled": False, "message": "Email authentication failed. Check credentials."}
    except smtplib.SMTPRecipientsRefused:
        return {"handled": False, "message": f"Email refused by server for {recipient}."}
    except Exception as e:
        return {"handled": False, "message": f"Email failed: {e}"}
    return {"handled": True, "message": f"Email sent to {recipient}."}


def extract_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", text)
    return match.group() if match else ""


def find_places(keyword: str, limit: int = 3) -> dict:
    """Search Google for nearby places."""
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://www.google.com/search?q={keyword}+near+me"
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")

        places = []
        for item in soup.select(".VkpGBb")[:limit]:
            name = item.select_one(".dbg0pd")
            address = item.select_one(".rllt__details")
            places.append({
                "name": name.get_text(strip=True) if name else "Unknown",
                "address": address.get_text(strip=True) if address else "",
            })

        if places:
            lines = [f"- {p['name']}: {p['address']}" for p in places]
            return {"handled": True, "message": "Found:\n" + "\n".join(lines), "places": places}
        return {"handled": True, "message": f"No results found for '{keyword}'."}
    except Exception as e:
        return {"handled": False, "message": f"Search failed: {e}"}

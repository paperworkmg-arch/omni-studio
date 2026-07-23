"""
Email notification module — sends alerts when new DAW exports are detected.
Uses Gmail App Password via SMTP (no service account needed).
"""
import os
import json
import logging
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("email_notifier")

# Load .env from parent directory
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Config
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "paperworkmg@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "paperworkmg@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")


async def send_export_notification(filename: str, size_mb: float, drive_url: str = ""):
    """Send email notification about a new DAW export."""
    subject = f"🎵 New Export: {filename}"
    body = f"""New song exported from Logic Pro!

Track: {filename}
Size: {size_mb:.1f} MB
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{"Google Drive: " + drive_url if drive_url else ""}

— Omni-Studio Auto-Notification
"""

    if SMTP_PASS:
        try:
            await _send_via_smtp(subject, body)
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            _save_notification(subject, body, drive_url)
            return
    else:
        # No SMTP configured — log only
        logger.info(f"[NOTIFICATION - NOT SENT] {subject}\n{body}")
        _save_notification(subject, body, drive_url)
        return

    _save_notification(subject, body, drive_url)


async def _send_via_smtp(subject: str, body: str):
    """Send email using Gmail SMTP with App Password."""
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER or NOTIFY_EMAIL
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    def _send():
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)
    logger.info(f"SMTP email sent to {NOTIFY_EMAIL}")


def _save_notification(subject: str, body: str, drive_url: str = ""):
    """Save notification to local log for dashboard display."""
    log_file = Path(__file__).parent / "data" / "notifications.json"
    notifications = []
    if log_file.exists():
        try:
            notifications = json.loads(log_file.read_text())
        except Exception:
            notifications = []

    notifications.append({
        "subject": subject,
        "body": body,
        "drive_url": drive_url,
        "sent_at": datetime.now().isoformat(),
    })

    # Keep last 100
    notifications = notifications[-100:]
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(notifications, indent=2))

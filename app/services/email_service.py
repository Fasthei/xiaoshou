import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Iterable

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    to: str | Iterable[str],
    subject: str,
    body: str,
    html: bool = False,
) -> bool:
    s = get_settings()
    if not (s.SMTP_SERVER and s.SMTP_EMAIL and s.SMTP_PASSWORD):
        logger.warning("SMTP not configured, skip send to %s", to)
        return False

    recipients = [to] if isinstance(to, str) else list(to)

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((s.SMTP_FROM_NAME, s.SMTP_EMAIL))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if html else "plain", "utf-8"))

    try:
        if s.SMTP_USE_SSL:
            client = smtplib.SMTP_SSL(s.SMTP_SERVER, s.SMTP_PORT, timeout=15)
        else:
            client = smtplib.SMTP(s.SMTP_SERVER, s.SMTP_PORT, timeout=15)
            client.starttls()
        with client:
            client.login(s.SMTP_EMAIL, s.SMTP_PASSWORD)
            client.sendmail(s.SMTP_EMAIL, recipients, msg.as_string())
        return True
    except Exception as e:
        logger.exception("SMTP send failed: %s", e)
        return False

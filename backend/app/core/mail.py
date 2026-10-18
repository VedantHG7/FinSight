"""Send account recovery mail through a configured SMTP relay."""
from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


def send_password_reset(email: str, url: str) -> None:
    message = EmailMessage()
    message['Subject'] = 'Reset your FinSight password'
    message['From'] = settings.SMTP_FROM_EMAIL
    message['To'] = email
    message.set_content(
        'A password reset was requested for your FinSight account.\n\n'
        f'Open this link within 30 minutes:\n{url}\n\n'
        'If you did not request this, you can ignore this email.\n'
    )
    transport = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with transport(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls(context=ssl.create_default_context())
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)

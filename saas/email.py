from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import SaaSConfig


def send_completed(cfg: SaaSConfig, recipient: str, filename: str, job_url: str, success: bool=True) -> None:
    message = EmailMessage()
    message["From"], message["To"] = cfg.from_email, recipient
    message["Subject"] = ("Your TESDA files are ready" if success else "Your TESDA build needs attention")
    outcome = "finished successfully" if success else "stopped because a step needs attention"
    message.set_content(f"Your build for {filename} {outcome}.\n\nOpen the job: {job_url}\n")
    context = ssl.create_default_context()
    if cfg.smtp_port == 465:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=30) as smtp:
            smtp.login(cfg.smtp_username, cfg.smtp_password); smtp.send_message(message)
    else:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context); smtp.login(cfg.smtp_username, cfg.smtp_password); smtp.send_message(message)

from __future__ import annotations

import firebase_admin
from firebase_admin import auth, credentials

from .config import load_config
def main() -> None:
    cfg = load_config()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cfg.firebase_service_account_path), {"projectId":cfg.firebase_project_id})
    try:
        user = auth.get_user_by_email(cfg.admin_email)
        created = False
    except auth.UserNotFoundError:
        user = auth.create_user(email=cfg.admin_email, email_verified=False, display_name="TESDA Administrator")
        created = True
    action = auth.ActionCodeSettings(url=cfg.public_url + "/login", handle_code_in_app=False)
    verification = auth.generate_email_verification_link(cfg.admin_email, action)
    reset = auth.generate_password_reset_link(cfg.admin_email, action)
    # Use the verified SMTP account rather than exposing one-time links in logs.
    from email.message import EmailMessage
    import smtplib, ssl
    message=EmailMessage(); message["From"]=cfg.from_email; message["To"]=cfg.admin_email
    message["Subject"]="Finish setting up your TESDA Academic Tools administrator account"
    message.set_content(f"Verify your administrator email:\n{verification}\n\nSet or change your password:\n{reset}\n\nThen sign in at {cfg.public_url}/login\n")
    context=ssl.create_default_context()
    if cfg.smtp_port == 465:
        with smtplib.SMTP_SSL(cfg.smtp_host,cfg.smtp_port,context=context,timeout=30) as smtp:
            smtp.login(cfg.smtp_username,cfg.smtp_password); smtp.send_message(message)
    else:
        with smtplib.SMTP(cfg.smtp_host,cfg.smtp_port,timeout=30) as smtp:
            smtp.starttls(context=context); smtp.login(cfg.smtp_username,cfg.smtp_password); smtp.send_message(message)
    print("Administrator account ready; setup email sent" if created else "Administrator setup email refreshed")


if __name__ == "__main__":
    main()

"""Email notification adapter."""

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class EmailConfig:
    """Email configuration."""

    smtp_host: str
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    from_email: str = "dataing@example.com"
    from_name: str = "Dataing"
    use_tls: bool = True


class EmailNotifier:
    """Delivers notifications via email (SMTP)."""

    def __init__(self, config: EmailConfig):
        """Initialize the email notifier.

        Args:
            config: Email configuration settings.
        """
        self.config = config

    def send(
        self,
        to_emails: list[str],
        subject: str,
        body_html: str,
        body_text: str | None = None,
    ) -> bool:
        """Send email notification.

        Returns True if the email was sent successfully.
        Note: This is synchronous - use in a thread pool for async contexts.
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.config.from_name} <{self.config.from_email}>"
            msg["To"] = ", ".join(to_emails)

            # Add plain text version
            if body_text:
                msg.attach(MIMEText(body_text, "plain"))

            # Add HTML version
            msg.attach(MIMEText(body_html, "html"))

            # Connect and send
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()

                if self.config.smtp_user and self.config.smtp_password:
                    server.login(self.config.smtp_user, self.config.smtp_password)

                server.sendmail(
                    self.config.from_email,
                    to_emails,
                    msg.as_string(),
                )

            logger.info(
                "email_sent",
                to=to_emails,
                subject=subject,
            )

            return True

        except smtplib.SMTPException as e:
            logger.error(
                "email_error",
                to=to_emails,
                subject=subject,
                error=str(e),
            )
            return False

    def send_investigation_completed(
        self,
        to_emails: list[str],
        investigation_id: str,
        finding: dict[str, Any],
    ) -> bool:
        """Send investigation completed email."""
        subject = f"Investigation Completed: {investigation_id}"

        root_cause = finding.get("root_cause", "Unknown")
        confidence = finding.get("confidence", 0)
        summary = finding.get("summary", "No summary available")

        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #36a64f;">Investigation Completed</h2>

            <p><strong>Investigation ID:</strong> {investigation_id}</p>

            <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Root Cause</h3>
                <p>{root_cause}</p>
                <p><strong>Confidence:</strong> {confidence:.0%}</p>
            </div>

            <h3>Summary</h3>
            <p>{summary}</p>

            <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
            <p style="color: #666; font-size: 12px;">
                This email was sent by Dataing. Please do not reply to this email.
            </p>
        </body>
        </html>
        """

        body_text = f"""
Investigation Completed

Investigation ID: {investigation_id}

Root Cause: {root_cause}
Confidence: {confidence:.0%}

Summary:
{summary}

---
This email was sent by Dataing. Please do not reply to this email.
        """

        return self.send(to_emails, subject, body_html, body_text)

    def send_approval_required(
        self,
        to_emails: list[str],
        investigation_id: str,
        approval_url: str,
        context: dict[str, Any],
    ) -> bool:
        """Send approval request email."""
        subject = f"Approval Required: Investigation {investigation_id}"

        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #ffc107;">Approval Required</h2>

            <p>An investigation requires your approval to proceed.</p>

            <p><strong>Investigation ID:</strong> {investigation_id}</p>

            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #856404;">Context</h3>
                <p>Please review the context and approve or reject this investigation.</p>
            </div>

            <p style="text-align: center; margin: 30px 0;">
                <a href="{approval_url}" style="background: #007bff; color: white;
                padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Review and Approve
                </a>
            </p>

            <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
            <p style="color: #666; font-size: 12px;">
                This email was sent by Dataing. Please do not reply to this email.
            </p>
        </body>
        </html>
        """

        body_text = f"""
Approval Required

An investigation requires your approval to proceed.

Investigation ID: {investigation_id}

Please review and approve at: {approval_url}

---
This email was sent by Dataing. Please do not reply to this email.
        """

        return self.send(to_emails, subject, body_html, body_text)

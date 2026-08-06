from email.message import EmailMessage
import smtplib
from config import settings


def send_html_email(recipient: str, subject: str, html_body: str) -> None:
    if not settings.smtp_user or not settings.smtp_password or not settings.mail_from:
        raise RuntimeError("SMTP credentials are not configured.")
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("Please view this message in an HTML-capable email client.")
    message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def assignment_email(student_name: str, practical_title: str, deadline: str, faculty_name: str) -> str:
    return f"""
    <html><body>
      <h2>New practical assigned</h2>
      <p>Hello {student_name},</p>
      <p><strong>{practical_title}</strong> is now available in TPEMS.</p>
      <p>Deadline: <strong>{deadline}</strong><br>Faculty: {faculty_name}</p>
      <p>Submit a public GitHub repository URL from your student dashboard.</p>
    </body></html>
    """

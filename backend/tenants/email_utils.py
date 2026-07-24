from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone


def _send_with_connection(
    *,
    subject,
    text_content,
    html_content=None,
    from_email=None,
    to_emails=None,
    cc_emails=None,
):
    to_emails = [email for email in (to_emails or []) if email]

    if not to_emails:
        return {
            "success": False,
            "error": "No recipient email provided."
        }

    connection = get_connection()

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=to_emails,
        cc=cc_emails or [],
        connection=connection,
    )

    if html_content:
        email_message.attach_alternative(
            html_content,
            "text/html"
        )

    email_message.send()

    return {
        "success": True
    }


def send_company_email(
    company=None,
    *,
    subject,
    text_content,
    html_content=None,
    to_emails,
    cc_emails=None,
):
    try:
        return _send_with_connection(
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=to_emails,
            cc_emails=cc_emails,
        )

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)
        }


def send_employee_invite_email(company, employee, raw_password):
    login_url = getattr(
        settings,
        "FRONTEND_LOGIN_URL",
        "http://localhost:5173/login",
    )

    html_content = render_to_string(
        "emails/employee_invite.html",
        {
            "employee_name": employee.user.first_name or employee.user.email,
            "company_name": company.name, 
            "email": employee.user.email,
            "department": (
                employee.department.name
                if employee.department else "Not Assigned"
            ),
            "role": (
                employee.company_role.name
                if employee.company_role else employee.role
            ),
            "temporary_password": raw_password,
            "login_url": login_url,
        },
    )

    text_content = strip_tags(html_content)

    return send_company_email(
        company=company,
        subject=f"Welcome to ZepEx - {company.name}",
        text_content=text_content,
        html_content=html_content,
        to_emails=[employee.user.email],
    )


def send_company_registration_otp(email, otp):
    html_content = render_to_string(
        "emails/company_registration_otp.html",
        {
            "otp": otp,
            "year": timezone.now().year,
        }
    )

    text_content = strip_tags(html_content)

    try:
        return _send_with_connection(
            subject="Verify your company registration - ZepEx",
            text_content=text_content,
            html_content=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=[email],
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
from email_validator import EmailNotValidError, validate_email


def normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower()
    if value.startswith("@"):
        value = value[1:]
    return value


def admin_email_matches_company_domain(admin_email: str, company_domain: str) -> bool:
    email = (admin_email or "").strip().lower()
    if "@" not in email:
        return False
    email_domain = email.rsplit("@", 1)[-1]
    return email_domain == normalize_domain(company_domain)


def validate_company_email_domain(email: str) -> tuple[bool, str | None]:
    """
    Validate whether the email domain exists (DNS / deliverability).
    Returns (True, None) if valid, (False, error_message) otherwise.
    """
    try:
        validate_email(email, check_deliverability=True)
        return True, None
    except EmailNotValidError as exc:
        return False, str(exc)


def validate_company_domain(company_domain: str) -> tuple[bool, str | None]:
    """Check that company_domain has DNS/MX records before OTP is sent."""
    domain = normalize_domain(company_domain)
    if not domain:
        return False, "company_domain is required."
    if "." not in domain:
        return False, "Enter a valid company domain (e.g. bitloom.ai)."

    return validate_company_email_domain(f"verify@{domain}")


def validate_registration_admin_email(
    admin_email: str,
    company_domain: str,
    *,
    verify_domain: bool = False,
) -> tuple[bool, str | None, str | None, str | None]:
    """
    Registration checks for admin email + company domain.

    verify_domain=True runs DNS/MX on company_domain (use before sending OTP).

    Returns (ok, user_message, details, error_code).
    """
    email = (admin_email or "").strip().lower()
    domain = normalize_domain(company_domain)

    if not email:
        return False, "admin_email is required.", None, "INVALID_ADMIN_EMAIL"

    if not domain:
        return False, "company_domain is required.", None, "INVALID_COMPANY_DOMAIN"

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        return False, "Enter a valid admin email address.", str(exc), "INVALID_ADMIN_EMAIL"

    if not admin_email_matches_company_domain(email, domain):
        return (
            False,
            f"Admin email must use your company domain (@{domain}).",
            None,
            "ADMIN_EMAIL_DOMAIN_MISMATCH",
        )

    if verify_domain:
        is_valid, detail = validate_company_domain(domain)
        if not is_valid:
            return (
                False,
                "The company domain could not be verified.",
                detail,
                "INVALID_COMPANY_EMAIL_DOMAIN",
            )

    return True, None, None, None

from tenants.role_schema import company_role_flag


def has_company_permission(
    profile,
    permission_name,
):
    """
    COMPANY_ADMIN always has access.

    Other users need the corresponding
    CompanyRole permission.
    """

    if not profile:
        return False

    if profile.role == "COMPANY_ADMIN":
        return True

    return company_role_flag(profile.company_role, permission_name)
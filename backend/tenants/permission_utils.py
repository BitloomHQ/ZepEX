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

    if not profile.company_role:
        return False

    return bool(
        getattr(
            profile.company_role,
            permission_name,
            False,
        )
    )
import logging

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from tenants.models import (
    Department,
    UserProfile,
    CompanyRole,
)

from integrations.models import (
    IntegrationEmployeeMapping,
    IntegrationChangeLog,
)


logger = logging.getLogger(__name__)


class BambooHRSyncError(Exception):
    pass


# ==========================================================
# HELPERS
# ==========================================================


def _clean(value):
    if value is None:
        return ""

    return str(value).strip()


def _get_employee_id(employee):
    return _clean(
        employee.get("employeeId")
        or employee.get("id")
    )


def _get_email(employee):
    return _clean(
        employee.get("workEmail")
    ).lower()


def _get_department(employee):
    return _clean(
        employee.get("department")
    )


def _get_first_name(employee):
    return _clean(
        employee.get("firstName")
    )


def _get_last_name(employee):
    return _clean(
        employee.get("lastName")
    )


def _get_job_title(employee):
    """Return the BambooHR employee job title / position."""
    return _clean(
        employee.get("jobTitle")
    )


def _get_supervisor_employee_id(employee):
    """
    Return BambooHR supervisor employee ID.
    """

    return _clean(
        employee.get("supervisorEId")
        or employee.get("supervisorEid")
        or employee.get("supervisorId")
    )


def _get_employee_status(employee):
    """
    Return normalized BambooHR employee status.

    Common value:
        Active

    We normalize it to lowercase:
        active
    """

    return _clean(
        employee.get("status")
    ).lower()


def _should_employee_be_active(employee):
    """
    Determine whether the ZepEx login should remain active.

    IMPORTANT:
    If BambooHR does not return a status because of field
    permissions or another API limitation, we do NOT
    deactivate the user.

    This prevents accidental mass deactivation.
    """

    employee_status = _get_employee_status(
        employee
    )

    if not employee_status:
        return True

    return employee_status == "active"


def _display_user_profile(profile):
    """Return a human-readable UserProfile name for change logs."""

    if not profile:
        return ""

    user = getattr(profile, "user", None)

    if not user:
        return str(profile.pk)

    full_name = (
        f"{user.first_name or ''} "
        f"{user.last_name or ''}"
    ).strip()

    return (
        full_name
        or user.email
        or user.username
        or str(profile.pk)
    )


def _display_employee_name(
    *,
    first_name="",
    last_name="",
    email="",
):
    full_name = (
        f"{first_name or ''} "
        f"{last_name or ''}"
    ).strip()

    return full_name or email or "Unknown Employee"


def _create_change_log(
    *,
    integration,
    sync_log=None,
    resource_type,
    external_resource_id=None,
    resource_name=None,
    change_type,
    field_name=None,
    old_value=None,
    new_value=None,
    details=None,
):
    """Persist one actual external-integration change."""

    return IntegrationChangeLog.objects.create(
        integration=integration,
        sync_log=sync_log,
        resource_type=resource_type,
        external_resource_id=(
            str(external_resource_id)
            if external_resource_id is not None
            else None
        ),
        resource_name=resource_name,
        change_type=change_type,
        field_name=field_name,
        old_value=(
            str(old_value)
            if old_value is not None
            else None
        ),
        new_value=(
            str(new_value)
            if new_value is not None
            else None
        ),
        details=details or {},
    )

@transaction.atomic
def sync_bamboohr_departments(
    *,
    integration,
    employees,
    sync_log=None,
):
    """
    Synchronize BambooHR departments into ZepEx.

    This function only handles departments.
    It does not create/update employees or managers.
    """

    company = integration.company

    stats = {
        "received": len(employees),
        "departments_found": 0,
        "departments_created": 0,
        "departments_existing": 0,
    }

    errors = []

    # ==========================================================
    # 1. COLLECT UNIQUE DEPARTMENT NAMES
    # ==========================================================

    department_names = set()

    for employee in employees:

        department_name = _get_department(
            employee
        )

        if not department_name:
            continue

        department_name = str(
            department_name
        ).strip()

        if department_name:
            department_names.add(
                department_name
            )

    stats["departments_found"] = len(
        department_names
    )

    # ==========================================================
    # 2. CREATE MISSING DEPARTMENTS
    # ==========================================================

    for department_name in department_names:

        department = (
            Department.objects
            .filter(
                company=company,
                name__iexact=department_name,
            )
            .first()
        )

        if department:

            stats[
                "departments_existing"
            ] += 1

            # If a previously inactive department appears
            # in BambooHR again, reactivate it.
            if not department.is_active:

                department.is_active = True

                department.save(
                    update_fields=[
                        "is_active",
                    ]
                )

                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=(
                        IntegrationChangeLog
                        .RESOURCE_DEPARTMENT
                    ),
                    external_resource_id=department.id,
                    resource_name=department.name,
                    change_type=(
                        IntegrationChangeLog
                        .CHANGE_ACTIVATED
                    ),
                    field_name="is_active",
                    old_value=False,
                    new_value=True,
                    details={
                        "department_id": str(department.id),
                        "source": "BAMBOOHR",
                    },
                )

            continue

        try:

            department = Department.objects.create(
                company=company,
                name=department_name,
                is_active=True,
            )

            stats[
                "departments_created"
            ] += 1

            _create_change_log(
                integration=integration,
                sync_log=sync_log,
                resource_type=(
                    IntegrationChangeLog
                    .RESOURCE_DEPARTMENT
                ),
                external_resource_id=department.id,
                resource_name=department.name,
                change_type=(
                    IntegrationChangeLog
                    .CHANGE_CREATED
                ),
                field_name="department",
                old_value=None,
                new_value=department.name,
                details={
                    "department_id": str(department.id),
                    "source": "BAMBOOHR",
                },
            )

        except Exception as exc:

            errors.append(
                {
                    "department": (
                        department_name
                    ),
                    "error": str(exc),
                }
            )

    # ==========================================================
    # 3. RESULT
    # ==========================================================

    return {
        "success": len(errors) == 0,
        "provider": "BAMBOOHR",
        "resource": "DEPARTMENTS",
        "stats": stats,
        "errors": errors,
    }


@transaction.atomic
def sync_bamboohr_employees_only(
    *,
    integration,
    employees,
    sync_log=None,
):
    """
    Synchronize BambooHR employees into ZepEx.

    This function handles only:

    - Django User creation/update
    - UserProfile creation/update
    - employee active/inactive lifecycle
    - department assignment
    - BambooHR <-> ZepEx employee mappings

    It does NOT:

    - create departments
    - synchronize reporting managers
    - infer department managers
    """

    company = integration.company

    # CompanyRole controls ZepEx permissions/workflow.
    # BambooHR jobTitle is stored separately and must never be used
    # as a CompanyRole. Existing assigned roles are preserved.
    default_employee_role = (
        CompanyRole.objects
        .filter(
            company=company,
            name__iexact="Employee",
            is_active=True,
        )
        .first()
    )

    stats = {
        "received": len(employees),

        "users_created": 0,
        "users_updated": 0,

        "profiles_created": 0,
        "profiles_updated": 0,

        "mappings_created": 0,
        "mappings_updated": 0,

        "employees_activated": 0,
        "employees_deactivated": 0,

        "departments_missing": 0,

        "job_titles_updated": 0,
        "company_roles_assigned": 0,
        "company_role_missing": 0,

        "skipped": 0,
    }

    errors = []

    # ==========================================================
    # EMPLOYEE SYNC
    # ==========================================================

    for employee_data in employees:

        external_id = _get_employee_id(
            employee_data
        )

        email = _get_email(
            employee_data
        )

        first_name = _get_first_name(
            employee_data
        )

        last_name = _get_last_name(
            employee_data
        )

        department_name = _get_department(
            employee_data
        )

        job_title = _get_job_title(
            employee_data
        )

        employee_status = _get_employee_status(
            employee_data
        )

        should_be_active = (
            _should_employee_be_active(
                employee_data
            )
        )

        # ======================================================
        # 1. BAMBOOHR EMPLOYEE ID REQUIRED
        # ======================================================

        if not external_id:

            stats["skipped"] += 1

            errors.append(
                {
                    "employee": (
                        email
                        or "unknown"
                    ),
                    "error": (
                        "BambooHR employee ID "
                        "is missing."
                    ),
                }
            )

            continue

        # ======================================================
        # 2. WORK EMAIL REQUIRED
        # ======================================================

        if not email:

            stats["skipped"] += 1

            errors.append(
                {
                    "external_employee_id": (
                        external_id
                    ),
                    "error": (
                        "Employee work email "
                        "is missing."
                    ),
                }
            )

            continue

        # ======================================================
        # 3. RESOLVE DEPARTMENT
        # ======================================================

        department = None

        if department_name:

            department = (
                Department.objects
                .filter(
                    company=company,
                    name__iexact=(
                        department_name
                    ),
                    is_active=True,
                )
                .first()
            )

            # --------------------------------------------------
            # Department sync is independent now.
            #
            # Do NOT create the department here.
            # Do NOT clear an employee's existing department
            # just because department sync was not run first.
            # --------------------------------------------------

            if not department:

                stats[
                    "departments_missing"
                ] += 1

                errors.append(
                    {
                        "external_employee_id": (
                            external_id
                        ),
                        "email": email,
                        "department": (
                            department_name
                        ),
                        "warning": (
                            "Department does not "
                            "exist in ZepEx. Run "
                            "department synchronization "
                            "first."
                        ),
                    }
                )

        # ======================================================
        # 4. FIND EXISTING BAMBOOHR MAPPING
        # ======================================================

        mapping = (
            IntegrationEmployeeMapping.objects
            .select_related(
                "user_profile",
                "user_profile__user",
            )
            .filter(
                integration=integration,
                external_employee_id=(
                    external_id
                ),
            )
            .first()
        )

        # ======================================================
        # 5. EXISTING BAMBOOHR MAPPING
        # ======================================================

        if mapping:

            profile = mapping.user_profile
            user = profile.user

            old_email = user.email or ""
            old_first_name = user.first_name or ""
            old_last_name = user.last_name or ""
            old_is_active = user.is_active
            old_department = profile.department
            old_job_title = profile.job_title or ""
            old_company_role = profile.company_role

            # --------------------------------------------------
            # Tenant safety
            # --------------------------------------------------

            if (
                profile.company_id
                != company.id
            ):

                stats[
                    "skipped"
                ] += 1

                errors.append(
                    {
                        "external_employee_id": (
                            external_id
                        ),
                        "error": (
                            "Existing integration "
                            "mapping belongs to "
                            "another company."
                        ),
                    }
                )

                continue

            # ==================================================
            # UPDATE DJANGO USER
            # ==================================================

            changed_user_fields = []

            if (
                user.email.lower()
                != email.lower()
            ):

                user.email = email

                changed_user_fields.append(
                    "email"
                )

            if (
                user.first_name
                != first_name
            ):

                user.first_name = (
                    first_name
                )

                changed_user_fields.append(
                    "first_name"
                )

            if (
                user.last_name
                != last_name
            ):

                user.last_name = (
                    last_name
                )

                changed_user_fields.append(
                    "last_name"
                )

            # --------------------------------------------------
            # Employee lifecycle
            # --------------------------------------------------

            if (
                user.is_active
                != should_be_active
            ):

                user.is_active = (
                    should_be_active
                )

                changed_user_fields.append(
                    "is_active"
                )

                if should_be_active:

                    stats[
                        "employees_activated"
                    ] += 1

                else:

                    stats[
                        "employees_deactivated"
                    ] += 1

            if changed_user_fields:

                user.save(
                    update_fields=(
                        changed_user_fields
                    )
                )

                stats[
                    "users_updated"
                ] += 1

            # ==================================================
            # UPDATE USER PROFILE
            # ==================================================

            changed_profile_fields = []

            # --------------------------------------------------
            # Only change department when BambooHR department
            # actually exists in ZepEx.
            # --------------------------------------------------

            if department:

                if (
                    profile.department_id
                    != department.id
                ):

                    profile.department = (
                        department
                    )

                    changed_profile_fields.append(
                        "department"
                    )

            if (profile.job_title or "") != job_title:
                profile.job_title = job_title or None
                changed_profile_fields.append("job_title")
                stats["job_titles_updated"] += 1

            # Assign the default Employee CompanyRole only when no
            # CompanyRole is currently assigned. Never overwrite an
            # existing Manager/Finance/Admin/custom role.
            if profile.company_role_id is None:
                if default_employee_role:
                    profile.company_role = default_employee_role
                    changed_profile_fields.append("company_role")
                    stats["company_roles_assigned"] += 1
                else:
                    stats["company_role_missing"] += 1

            if changed_profile_fields:

                profile.save(
                    update_fields=(
                        changed_profile_fields
                    )
                )

                stats[
                    "profiles_updated"
                ] += 1

            resource_name = _display_employee_name(
                first_name=first_name,
                last_name=last_name,
                email=email,
            )

            if old_email.lower() != email.lower():
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_UPDATED,
                    field_name="email",
                    old_value=old_email,
                    new_value=email,
                )

            if old_first_name != first_name:
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_UPDATED,
                    field_name="first_name",
                    old_value=old_first_name,
                    new_value=first_name,
                )

            if old_last_name != last_name:
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_UPDATED,
                    field_name="last_name",
                    old_value=old_last_name,
                    new_value=last_name,
                )

            if old_job_title != job_title:
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_UPDATED,
                    field_name="job_title",
                    old_value=old_job_title or None,
                    new_value=job_title or None,
                )

            if old_company_role is None and profile.company_role_id:
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_UPDATED,
                    field_name="company_role",
                    old_value=None,
                    new_value=profile.company_role.name,
                    details={"source": "ZEPEX_DEFAULT_ROLE"},
                )

            if old_is_active != should_be_active:
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=(
                        IntegrationChangeLog.CHANGE_ACTIVATED
                        if should_be_active
                        else IntegrationChangeLog.CHANGE_DEACTIVATED
                    ),
                    field_name="is_active",
                    old_value=old_is_active,
                    new_value=should_be_active,
                )

            if (
                department
                and (
                    not old_department
                    or old_department.id != department.id
                )
            ):
                _create_change_log(
                    integration=integration,
                    sync_log=sync_log,
                    resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                    external_resource_id=external_id,
                    resource_name=resource_name,
                    change_type=IntegrationChangeLog.CHANGE_DEPARTMENT_CHANGED,
                    field_name="department",
                    old_value=(
                        old_department.name
                        if old_department
                        else None
                    ),
                    new_value=department.name,
                )

            # ==================================================
            # UPDATE MAPPING
            # ==================================================

            mapping_fields_to_update = [
                "last_synced_at",
                "updated_at",
            ]

            if (
                (mapping.external_email or "").lower()
                != email.lower()
            ):
                mapping.external_email = email
                mapping_fields_to_update.insert(
                    0,
                    "external_email",
                )

                stats[
                    "mappings_updated"
                ] += 1

            mapping.last_synced_at = (
                timezone.now()
            )

            mapping.save(
                update_fields=(
                    mapping_fields_to_update
                )
            )

            logger.info(
                (
                    "BambooHR employee "
                    "synchronized. "
                    "company=%s employee=%s "
                    "status=%s active=%s"
                ),
                company.id,
                external_id,
                (
                    employee_status
                    or "unknown"
                ),
                should_be_active,
            )

            continue

        # ======================================================
        # 6. NO EXTERNAL MAPPING
        # ======================================================

        existing_user = (
            User.objects
            .filter(
                email__iexact=email
            )
            .first()
        )

        # ======================================================
        # 7. EXISTING DJANGO USER
        # ======================================================

        if existing_user:

            try:

                profile = (
                    existing_user.profile
                )

            except UserProfile.DoesNotExist:

                profile = (
                    UserProfile.objects.create(
                        user=existing_user,
                        company=company,
                        department=department,
                        job_title=job_title or None,
                        role="EMPLOYEE",
                        company_role=default_employee_role,
                    )
                )

                stats[
                    "profiles_created"
                ] += 1

                if default_employee_role:
                    stats["company_roles_assigned"] += 1
                else:
                    stats["company_role_missing"] += 1

            else:

                # ----------------------------------------------
                # Tenant safety
                # ----------------------------------------------

                if (
                    profile.company_id
                    and
                    profile.company_id
                    != company.id
                ):

                    stats[
                        "skipped"
                    ] += 1

                    errors.append(
                        {
                            "external_employee_id": (
                                external_id
                            ),
                            "email": email,
                            "error": (
                                "A ZepEx user with "
                                "this email belongs "
                                "to another company."
                            ),
                        }
                    )

                    continue

                changed_profile_fields = []

                if (
                    profile.company_id
                    != company.id
                ):

                    profile.company = (
                        company
                    )

                    changed_profile_fields.append(
                        "company"
                    )

                if department:

                    if (
                        profile.department_id
                        != department.id
                    ):

                        profile.department = (
                            department
                        )

                        changed_profile_fields.append(
                            "department"
                        )

                if (profile.job_title or "") != job_title:
                    profile.job_title = job_title or None
                    changed_profile_fields.append("job_title")
                    stats["job_titles_updated"] += 1

                if profile.company_role_id is None:
                    if default_employee_role:
                        profile.company_role = default_employee_role
                        changed_profile_fields.append("company_role")
                        stats["company_roles_assigned"] += 1
                    else:
                        stats["company_role_missing"] += 1

                if changed_profile_fields:

                    profile.save(
                        update_fields=(
                            changed_profile_fields
                        )
                    )

                    stats[
                        "profiles_updated"
                    ] += 1

            user = existing_user

            changed_fields = []

            if (
                user.first_name
                != first_name
            ):

                user.first_name = (
                    first_name
                )

                changed_fields.append(
                    "first_name"
                )

            if (
                user.last_name
                != last_name
            ):

                user.last_name = (
                    last_name
                )

                changed_fields.append(
                    "last_name"
                )

            if (
                user.is_active
                != should_be_active
            ):

                user.is_active = (
                    should_be_active
                )

                changed_fields.append(
                    "is_active"
                )

                if should_be_active:

                    stats[
                        "employees_activated"
                    ] += 1

                else:

                    stats[
                        "employees_deactivated"
                    ] += 1

            if changed_fields:

                user.save(
                    update_fields=(
                        changed_fields
                    )
                )

                stats[
                    "users_updated"
                ] += 1

        # ======================================================
        # 8. NEW DJANGO USER
        # ======================================================

        else:

            username_base = email
            username = username_base

            counter = 1

            while User.objects.filter(
                username=username
            ).exists():

                username = (
                    f"{username_base}-"
                    f"{counter}"
                )

                counter += 1

            user = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=(
                    should_be_active
                ),
            )

            # ----------------------------------------------
            # BambooHR users do not receive a password here.
            # Invitation/access flow handles this separately.
            # ----------------------------------------------

            user.set_unusable_password()

            user.save(
                update_fields=[
                    "password",
                ]
            )

            stats[
                "users_created"
            ] += 1

            profile = (
                UserProfile.objects.create(
                    user=user,
                    company=company,
                    department=department,
                    job_title=job_title or None,
                    role="EMPLOYEE",
                    company_role=default_employee_role,
                    force_password_change=True,
                )
            )

            stats[
                "profiles_created"
            ] += 1

            if default_employee_role:
                stats["company_roles_assigned"] += 1
            else:
                stats["company_role_missing"] += 1

        # ======================================================
        # 9. CREATE BAMBOOHR ↔ ZEPEX MAPPING
        # ======================================================

        IntegrationEmployeeMapping.objects.create(
            integration=integration,
            user_profile=profile,
            external_employee_id=(
                external_id
            ),
            external_email=email,
            last_synced_at=(
                timezone.now()
            ),
        )

        stats[
            "mappings_created"
        ] += 1

        _create_change_log(
            integration=integration,
            sync_log=sync_log,
            resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
            external_resource_id=external_id,
            resource_name=_display_employee_name(
                first_name=first_name,
                last_name=last_name,
                email=email,
            ),
            change_type=IntegrationChangeLog.CHANGE_CREATED,
            old_value=None,
            new_value=email,
            details={
                "email": email,
                "department": (
                    department.name
                    if department
                    else None
                ),
                "active": should_be_active,
                "source": "BAMBOOHR",
            },
        )

    # ==========================================================
    # 10. RESULT
    # ==========================================================

    return {
        "success": True,
        "provider": "BAMBOOHR",
        "resource": "EMPLOYEES",
        "stats": stats,
        "errors": errors,
    }

@transaction.atomic
def sync_bamboohr_managers(
    *,
    integration,
    employees,
    sync_log=None,
):
    """
    Synchronize BambooHR reporting-manager relationships
    into ZepEx.

    Synchronization order:

    1. Employee -> reporting manager
    2. BambooHR department -> inferred department manager

    Important:

    - supervisorEId is the authoritative BambooHR
      employee-manager relationship.

    - Existing ZepEx departments that are not represented
      in the current BambooHR employee dataset are not
      modified.

    - A department can legitimately have no inferred
      manager when its employees do not have supervisors
      in BambooHR.

    This function assumes departments and employees have
    already been synchronized.
    """

    company = integration.company

    stats = {
        "received": len(employees),

        "managers_mapped": 0,
        "managers_updated": 0,
        "managers_not_found": 0,

        "bamboohr_departments_considered": 0,

        "department_managers_mapped": 0,
        "department_managers_updated": 0,
        "department_managers_not_found": 0,

        "skipped": 0,
    }

    errors = []

    # ==========================================================
    # 1. COLLECT BAMBOOHR DEPARTMENTS
    # ==========================================================
    #
    # Department-manager synchronization must only operate
    # on departments represented by BambooHR.
    #
    # This prevents existing/manual ZepEx departments from
    # being incorrectly counted as BambooHR manager failures.
    # ==========================================================

    bamboohr_department_names = set()

    for employee_data in employees:

        department_name = (
            _get_department(
                employee_data
            )
        )

        if not department_name:
            continue

        department_name = str(
            department_name
        ).strip()

        if department_name:

            bamboohr_department_names.add(
                department_name
            )

    stats[
        "bamboohr_departments_considered"
    ] = len(
        bamboohr_department_names
    )

    # ==========================================================
    # PASS 1 — EMPLOYEE -> REPORTING MANAGER
    # ==========================================================

    for employee_data in employees:

        employee_external_id = (
            _get_employee_id(
                employee_data
            )
        )

        # ------------------------------------------------------
        # Employee ID required
        # ------------------------------------------------------

        if not employee_external_id:

            stats[
                "skipped"
            ] += 1

            errors.append(
                {
                    "error": (
                        "BambooHR employee ID "
                        "is missing."
                    ),
                }
            )

            continue

        supervisor_external_id = (
            _get_supervisor_employee_id(
                employee_data
            )
        )

        # ------------------------------------------------------
        # No supervisor
        # ------------------------------------------------------
        #
        # This is valid for top-level employees such as
        # company heads / CEOs.
        # ------------------------------------------------------

        if not supervisor_external_id:
            continue

        # ------------------------------------------------------
        # Find employee mapping
        # ------------------------------------------------------

        employee_mapping = (
            IntegrationEmployeeMapping.objects
            .select_related(
                "user_profile",
                "user_profile__user",
            )
            .filter(
                integration=integration,
                external_employee_id=(
                    employee_external_id
                ),
            )
            .first()
        )

        if not employee_mapping:

            stats[
                "managers_not_found"
            ] += 1

            errors.append(
                {
                    "external_employee_id": (
                        employee_external_id
                    ),
                    "error": (
                        "Employee mapping not found "
                        "during manager synchronization."
                    ),
                }
            )

            continue

        # ------------------------------------------------------
        # Find supervisor mapping
        # ------------------------------------------------------

        manager_mapping = (
            IntegrationEmployeeMapping.objects
            .select_related(
                "user_profile",
                "user_profile__user",
            )
            .filter(
                integration=integration,
                external_employee_id=(
                    supervisor_external_id
                ),
            )
            .first()
        )

        if not manager_mapping:

            stats[
                "managers_not_found"
            ] += 1

            errors.append(
                {
                    "external_employee_id": (
                        employee_external_id
                    ),
                    "supervisor_external_id": (
                        supervisor_external_id
                    ),
                    "error": (
                        "Reporting manager could not "
                        "be mapped to a ZepEx employee."
                    ),
                }
            )

            continue

        employee_profile = (
            employee_mapping.user_profile
        )

        manager_profile = (
            manager_mapping.user_profile
        )

        # ------------------------------------------------------
        # Tenant safety
        # ------------------------------------------------------

        if (
            employee_profile.company_id
            != company.id
        ):

            stats[
                "skipped"
            ] += 1

            continue

        if (
            manager_profile.company_id
            != company.id
        ):

            stats[
                "skipped"
            ] += 1

            continue

        # ------------------------------------------------------
        # Prevent self-management
        # ------------------------------------------------------

        if (
            employee_profile.id
            == manager_profile.id
        ):

            stats[
                "skipped"
            ] += 1

            errors.append(
                {
                    "external_employee_id": (
                        employee_external_id
                    ),
                    "error": (
                        "Employee cannot be "
                        "their own reporting manager."
                    ),
                }
            )

            continue

        # ------------------------------------------------------
        # First manager assignment
        # ------------------------------------------------------

        if not (
            employee_profile
            .reporting_manager_id
        ):

            old_manager = employee_profile.reporting_manager

            employee_profile.reporting_manager = (
                manager_profile
            )

            employee_profile.save(
                update_fields=[
                    "reporting_manager",
                ]
            )

            stats[
                "managers_mapped"
            ] += 1

            _create_change_log(
                integration=integration,
                sync_log=sync_log,
                resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                external_resource_id=employee_external_id,
                resource_name=_display_user_profile(employee_profile),
                change_type=IntegrationChangeLog.CHANGE_MANAGER_CHANGED,
                field_name="reporting_manager",
                old_value=(
                    _display_user_profile(old_manager)
                    if old_manager
                    else None
                ),
                new_value=_display_user_profile(manager_profile),
                details={
                    "old_manager_profile_id": (
                        str(old_manager.id)
                        if old_manager
                        else None
                    ),
                    "new_manager_profile_id": str(manager_profile.id),
                    "bamboohr_supervisor_id": supervisor_external_id,
                },
            )

            continue

        # ------------------------------------------------------
        # Existing manager changed in BambooHR
        # ------------------------------------------------------

        if (
            employee_profile.reporting_manager_id
            != manager_profile.id
        ):

            old_manager = employee_profile.reporting_manager

            employee_profile.reporting_manager = (
                manager_profile
            )

            employee_profile.save(
                update_fields=[
                    "reporting_manager",
                ]
            )

            stats[
                "managers_updated"
            ] += 1

            _create_change_log(
                integration=integration,
                sync_log=sync_log,
                resource_type=IntegrationChangeLog.RESOURCE_EMPLOYEE,
                external_resource_id=employee_external_id,
                resource_name=_display_user_profile(employee_profile),
                change_type=IntegrationChangeLog.CHANGE_MANAGER_CHANGED,
                field_name="reporting_manager",
                old_value=(
                    _display_user_profile(old_manager)
                    if old_manager
                    else None
                ),
                new_value=_display_user_profile(manager_profile),
                details={
                    "old_manager_profile_id": (
                        str(old_manager.id)
                        if old_manager
                        else None
                    ),
                    "new_manager_profile_id": str(manager_profile.id),
                    "bamboohr_supervisor_id": supervisor_external_id,
                },
            )

    # ==========================================================
    # PASS 2 — BAMBOOHR DEPARTMENT MANAGERS
    # ==========================================================

    for department_name in (
        bamboohr_department_names
    ):

        # ------------------------------------------------------
        # Find corresponding ZepEx department
        # ------------------------------------------------------

        department = (
            Department.objects
            .filter(
                company=company,
                name__iexact=(
                    department_name
                ),
                is_active=True,
            )
            .first()
        )

        if not department:

            stats[
                "department_managers_not_found"
            ] += 1

            errors.append(
                {
                    "department": (
                        department_name
                    ),
                    "error": (
                        "BambooHR department does "
                        "not exist in ZepEx."
                    ),
                }
            )

            continue

        # ------------------------------------------------------
        # Get active employees belonging to department
        # ------------------------------------------------------

        department_employees = (
            UserProfile.objects
            .filter(
                company=company,
                department=department,
                user__is_active=True,
            )
            .select_related(
                "user",
                "reporting_manager",
                "reporting_manager__user",
            )
        )

        manager_counts = {}

        # ------------------------------------------------------
        # Count reporting managers
        # ------------------------------------------------------

        for employee_profile in (
            department_employees
        ):

            manager = (
                employee_profile
                .reporting_manager
            )

            if not manager:
                continue

            # --------------------------------------------------
            # Tenant safety
            # --------------------------------------------------

            if (
                manager.company_id
                != company.id
            ):
                continue

            # --------------------------------------------------
            # Ignore inactive manager
            # --------------------------------------------------

            if not manager.user.is_active:
                continue

            manager_id = (
                manager.id
            )

            if (
                manager_id
                not in manager_counts
            ):

                manager_counts[
                    manager_id
                ] = {
                    "manager": (
                        manager
                    ),
                    "count": 0,
                }

            manager_counts[
                manager_id
            ]["count"] += 1

        # ------------------------------------------------------
        # No inferable department manager
        # ------------------------------------------------------
        #
        # This is not necessarily an error.
        #
        # Example:
        # Company -> CEO -> no supervisor
        #
        # We record the statistic but do not add an error.
        # ------------------------------------------------------

        if not manager_counts:

            stats[
                "department_managers_not_found"
            ] += 1

            continue

        # ------------------------------------------------------
        # Select manager with most direct reports
        # ------------------------------------------------------

        best_manager_data = max(
            manager_counts.values(),
            key=lambda item: (
                item["count"]
            ),
        )

        manager_profile = (
            best_manager_data[
                "manager"
            ]
        )

        # ------------------------------------------------------
        # Extra tenant safety
        # ------------------------------------------------------

        if (
            manager_profile.company_id
            != company.id
        ):

            stats[
                "department_managers_not_found"
            ] += 1

            continue

        # ------------------------------------------------------
        # First department manager assignment
        # ------------------------------------------------------

        if not department.manager_id:

            old_department_manager = department.manager

            department.manager = (
                manager_profile
            )

            department.save(
                update_fields=[
                    "manager",
                ]
            )

            stats[
                "department_managers_mapped"
            ] += 1

            _create_change_log(
                integration=integration,
                sync_log=sync_log,
                resource_type=IntegrationChangeLog.RESOURCE_DEPARTMENT,
                external_resource_id=department.id,
                resource_name=department.name,
                change_type=IntegrationChangeLog.CHANGE_MANAGER_CHANGED,
                field_name="manager",
                old_value=(
                    _display_user_profile(old_department_manager)
                    if old_department_manager
                    else None
                ),
                new_value=_display_user_profile(manager_profile),
                details={
                    "old_manager_profile_id": (
                        str(old_department_manager.id)
                        if old_department_manager
                        else None
                    ),
                    "new_manager_profile_id": str(manager_profile.id),
                },
            )

            continue

        # ------------------------------------------------------
        # Existing department manager changed
        # ------------------------------------------------------

        if (
            department.manager_id
            != manager_profile.id
        ):

            old_department_manager = department.manager

            department.manager = (
                manager_profile
            )

            department.save(
                update_fields=[
                    "manager",
                ]
            )

            stats[
                "department_managers_updated"
            ] += 1

            _create_change_log(
                integration=integration,
                sync_log=sync_log,
                resource_type=IntegrationChangeLog.RESOURCE_DEPARTMENT,
                external_resource_id=department.id,
                resource_name=department.name,
                change_type=IntegrationChangeLog.CHANGE_MANAGER_CHANGED,
                field_name="manager",
                old_value=(
                    _display_user_profile(old_department_manager)
                    if old_department_manager
                    else None
                ),
                new_value=_display_user_profile(manager_profile),
                details={
                    "old_manager_profile_id": (
                        str(old_department_manager.id)
                        if old_department_manager
                        else None
                    ),
                    "new_manager_profile_id": str(manager_profile.id),
                },
            )

    # ==========================================================
    # RESULT
    # ==========================================================

    return {
        "success": (
            len(errors) == 0
        ),
        "provider": "BAMBOOHR",
        "resource": "MANAGERS",
        "stats": stats,
        "errors": errors,
    }
@transaction.atomic
def sync_bamboohr_all(
    *,
    integration,
    employees,
    sync_log=None,
):
    """
    Run complete BambooHR synchronization in the correct order:

    1. Departments
    2. Employees
    3. Managers

    The same BambooHR employee dataset is passed through
    all three synchronization stages.

    Important:
    "received" represents the number of unique BambooHR
    employees received, not the sum of employees processed
    by each synchronization stage.
    """

    # ==========================================================
    # 1. SYNC DEPARTMENTS
    # ==========================================================

    departments_result = (
        sync_bamboohr_departments(
            integration=integration,
            employees=employees,
            sync_log=sync_log,
        )
    )

    # ==========================================================
    # 2. SYNC EMPLOYEES
    # ==========================================================

    employees_result = (
        sync_bamboohr_employees_only(
            integration=integration,
            employees=employees,
            sync_log=sync_log,
        )
    )

    # ==========================================================
    # 3. SYNC MANAGERS
    # ==========================================================

    managers_result = (
        sync_bamboohr_managers(
            integration=integration,
            employees=employees,
            sync_log=sync_log,
        )
    )

    # ==========================================================
    # 4. BUILD COMBINED STATS
    # ==========================================================

    # "received" must represent the unique BambooHR
    # employee dataset, not:
    #
    # 109 departments stage
    # + 109 employees stage
    # + 109 managers stage
    # = 327
    #
    # There are actually only 109 BambooHR employees.

    combined_stats = {
        "received": len(
            employees
        ),
    }

    for result in (
        departments_result,
        employees_result,
        managers_result,
    ):

        stats = (
            result.get(
                "stats"
            )
            or {}
        )

        for key, value in stats.items():

            # ==================================================
            # DO NOT ADD RECEIVED MULTIPLE TIMES
            # ==================================================

            if key == "received":
                continue

            # ==================================================
            # COMBINE NUMERIC STATS
            # ==================================================

            if isinstance(
                value,
                int,
            ):

                combined_stats[key] = (
                    combined_stats.get(
                        key,
                        0,
                    )
                    + value
                )

            # ==================================================
            # NON-NUMERIC STATS
            # ==================================================

            else:

                combined_stats[key] = (
                    value
                )

    # ==========================================================
    # 5. COMBINE ERRORS
    # ==========================================================

    errors = []

    for result in (
        departments_result,
        employees_result,
        managers_result,
    ):

        result_errors = (
            result.get(
                "errors"
            )
            or []
        )

        errors.extend(
            result_errors
        )

    # ==========================================================
    # 6. FINAL SUCCESS STATUS
    # ==========================================================

    success = (
        departments_result.get(
            "success",
            False,
        )
        and employees_result.get(
            "success",
            False,
        )
        and managers_result.get(
            "success",
            False,
        )
    )

    # ==========================================================
    # 7. RESPONSE
    # ==========================================================

    return {
        "success": success,
        "provider": "BAMBOOHR",
        "resource": "ALL",

        "stats": combined_stats,

        "errors": errors,

        "resources": {
            "departments": (
                departments_result
            ),
            "employees": (
                employees_result
            ),
            "managers": (
                managers_result
            ),
        },
    }

# ==========================================================
# BACKWARD-COMPATIBILITY WRAPPER
# ==========================================================


@transaction.atomic
def sync_bamboohr_employees(
    *,
    integration,
    employees,
    sync_log=None,
):
    """
    Backward-compatible BambooHR employee sync.

    Older views/services may still import
    sync_bamboohr_employees().

    The actual employee synchronization is handled by
    sync_bamboohr_employees_only().
    """

    return sync_bamboohr_employees_only(
        integration=integration,
        employees=employees,
        sync_log=sync_log,
    )
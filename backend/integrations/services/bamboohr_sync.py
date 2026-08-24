import logging

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from tenants.models import (
    Department,
    UserProfile,
)

from integrations.models import (
    IntegrationEmployeeMapping,
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

@transaction.atomic
def sync_bamboohr_departments(
    *,
    integration,
    employees,
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

            continue

        try:

            Department.objects.create(
                company=company,
                name=department_name,
                is_active=True,
            )

            stats[
                "departments_created"
            ] += 1

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

            if changed_profile_fields:

                profile.save(
                    update_fields=(
                        changed_profile_fields
                    )
                )

            # ==================================================
            # UPDATE MAPPING
            # ==================================================

            mapping.external_email = email

            mapping.last_synced_at = (
                timezone.now()
            )

            mapping.save(
                update_fields=[
                    "external_email",
                    "last_synced_at",
                    "updated_at",
                ]
            )

            stats[
                "users_updated"
            ] += 1

            stats[
                "profiles_updated"
            ] += 1

            stats[
                "mappings_updated"
            ] += 1

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
                        role="EMPLOYEE",
                    )
                )

                stats[
                    "profiles_created"
                ] += 1

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
                    role="EMPLOYEE",
                    force_password_change=True,
                )
            )

            stats[
                "profiles_created"
            ] += 1

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
):
    """
    Synchronize BambooHR reporting-manager relationships
    and infer ZepEx department managers.

    This function assumes employee mappings already exist.

    It does NOT:
    - create departments
    - create employees
    """

    company = integration.company

    stats = {
        "received": len(employees),

        "managers_mapped": 0,
        "managers_updated": 0,
        "managers_not_found": 0,

        "department_managers_mapped": 0,
        "department_managers_updated": 0,
        "department_managers_not_found": 0,

        "skipped": 0,
    }

    errors = []

    # ==========================================================
    # PASS 1 — REPORTING MANAGERS
    # ==========================================================

    for employee_data in employees:

        employee_external_id = (
            _get_employee_id(
                employee_data
            )
        )

        if not employee_external_id:
            stats["skipped"] += 1

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

        # No supervisor in BambooHR
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
        # Find manager mapping
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
            stats["skipped"] += 1
            continue

        if (
            manager_profile.company_id
            != company.id
        ):
            stats["skipped"] += 1
            continue

        # ------------------------------------------------------
        # Prevent self manager
        # ------------------------------------------------------

        if (
            employee_profile.id
            == manager_profile.id
        ):

            stats["skipped"] += 1

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

            continue

        # ------------------------------------------------------
        # Manager changed
        # ------------------------------------------------------

        if (
            employee_profile.reporting_manager_id
            != manager_profile.id
        ):

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

    # ==========================================================
    # PASS 2 — DEPARTMENT MANAGERS
    # ==========================================================

    departments = (
        Department.objects
        .filter(
            company=company,
            is_active=True,
        )
    )

    for department in departments:

        department_employees = (
            UserProfile.objects
            .filter(
                company=company,
                department=department,
                user__is_active=True,
            )
            .select_related(
                "reporting_manager",
                "reporting_manager__user",
            )
        )

        manager_counts = {}

        for employee_profile in (
            department_employees
        ):

            manager = (
                employee_profile
                .reporting_manager
            )

            if not manager:
                continue

            # ----------------------------------------------
            # Tenant safety
            # ----------------------------------------------

            if (
                manager.company_id
                != company.id
            ):
                continue

            # ----------------------------------------------
            # Ignore inactive managers
            # ----------------------------------------------

            if not manager.user.is_active:
                continue

            # ----------------------------------------------
            # Same department only
            # ----------------------------------------------

            if (
                manager.department_id
                != department.id
            ):
                continue

            manager_id = manager.id

            if (
                manager_id
                not in manager_counts
            ):

                manager_counts[
                    manager_id
                ] = {
                    "manager": manager,
                    "count": 0,
                }

            manager_counts[
                manager_id
            ]["count"] += 1

        # ------------------------------------------------------
        # No manager candidate
        # ------------------------------------------------------

        if not manager_counts:

            stats[
                "department_managers_not_found"
            ] += 1

            continue

        # ------------------------------------------------------
        # Candidate with most direct reports
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
        # First assignment
        # ------------------------------------------------------

        if not department.manager_id:

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

            continue

        # ------------------------------------------------------
        # Manager changed
        # ------------------------------------------------------

        if (
            department.manager_id
            != manager_profile.id
        ):

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

    # ==========================================================
    # RESULT
    # ==========================================================

    return {
        "success": True,
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
):
    """
    Run complete BambooHR synchronization in the correct order:

    1. Departments
    2. Employees
    3. Managers

    This keeps the individual sync services reusable
    while providing one "Sync All" operation.
    """

    # ==========================================================
    # 1. SYNC DEPARTMENTS
    # ==========================================================

    departments_result = (
        sync_bamboohr_departments(
            integration=integration,
            employees=employees,
        )
    )

    # ==========================================================
    # 2. SYNC EMPLOYEES
    # ==========================================================

    employees_result = (
        sync_bamboohr_employees_only(
            integration=integration,
            employees=employees,
        )
    )

    # ==========================================================
    # 3. SYNC MANAGERS
    # ==========================================================

    managers_result = (
        sync_bamboohr_managers(
            integration=integration,
            employees=employees,
        )
    )

    # ==========================================================
    # 4. BUILD COMBINED STATS
    # ==========================================================

    combined_stats = {}

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

            if (
                isinstance(
                    value,
                    int,
                )
            ):

                combined_stats[key] = (
                    combined_stats.get(
                        key,
                        0,
                    )
                    + value
                )

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
# MAIN BAMBOOHR SYNC
# ==========================================================


@transaction.atomic
def sync_bamboohr_employees(
    *,
    integration,
    employees,
):
    """
    Synchronize BambooHR employees into ZepEx.

    Pass 1:
        Departments

    Pass 2:
        Users / UserProfiles / external mappings
        + employee active/inactive lifecycle

    Pass 3:
        Reporting manager relationships

    Pass 4:
        Department manager inference
    """

    company = integration.company

    stats = {
        "received": len(employees),

        "departments_created": 0,

        "users_created": 0,
        "users_updated": 0,

        "profiles_created": 0,
        "profiles_updated": 0,

        "mappings_created": 0,
        "mappings_updated": 0,

        "employees_activated": 0,
        "employees_deactivated": 0,

        "managers_mapped": 0,
        "managers_updated": 0,
        "managers_not_found": 0,

        "department_managers_mapped": 0,
        "department_managers_updated": 0,
        "department_managers_not_found": 0,

        "skipped": 0,
    }

    errors = []

    # ==========================================================
    # PASS 1 — DEPARTMENTS
    # ==========================================================

    department_names = set()

    for employee in employees:

        department_name = _get_department(
            employee
        )

        if department_name:

            department_names.add(
                department_name
            )

    for department_name in department_names:

        department = (
            Department.objects
            .filter(
                company=company,
                name__iexact=department_name,
            )
            .first()
        )

        if not department:

            Department.objects.create(
                company=company,
                name=department_name,
                is_active=True,
            )

            stats[
                "departments_created"
            ] += 1

    # ==========================================================
    # PASS 2 — EMPLOYEES + LIFECYCLE STATUS
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

        employee_status = _get_employee_status(
            employee_data
        )

        should_be_active = (
            _should_employee_be_active(
                employee_data
            )
        )

        # ------------------------------------------------------
        # External employee ID required
        # ------------------------------------------------------

        if not external_id:

            stats["skipped"] += 1

            errors.append(
                {
                    "employee": (
                        email or "unknown"
                    ),
                    "error": (
                        "BambooHR employee ID "
                        "is missing."
                    ),
                }
            )

            continue

        # ------------------------------------------------------
        # Work email required
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Resolve department
        # ------------------------------------------------------

        department = None

        if department_name:

            department = (
                Department.objects
                .filter(
                    company=company,
                    name__iexact=department_name,
                )
                .first()
            )

        # ------------------------------------------------------
        # Find by BambooHR external employee ID
        # ------------------------------------------------------

        mapping = (
            IntegrationEmployeeMapping.objects
            .select_related(
                "user_profile",
                "user_profile__user",
            )
            .filter(
                integration=integration,
                external_employee_id=external_id,
            )
            .first()
        )

        # ======================================================
        # EXISTING BAMBOOHR MAPPING
        # ======================================================

        if mapping:

            profile = mapping.user_profile
            user = profile.user

            # --------------------------------------------------
            # Tenant safety
            # --------------------------------------------------

            if profile.company_id != company.id:

                stats["skipped"] += 1

                errors.append(
                    {
                        "external_employee_id": (
                            external_id
                        ),
                        "error": (
                            "Existing integration mapping "
                            "belongs to another company."
                        ),
                    }
                )

                continue

            # --------------------------------------------------
            # Update Django User
            # --------------------------------------------------

            changed_user_fields = []

            if (
                user.email.lower()
                != email.lower()
            ):

                user.email = email

                changed_user_fields.append(
                    "email"
                )

            if user.first_name != first_name:

                user.first_name = first_name

                changed_user_fields.append(
                    "first_name"
                )

            if user.last_name != last_name:

                user.last_name = last_name

                changed_user_fields.append(
                    "last_name"
                )

            # --------------------------------------------------
            # Synchronize employee lifecycle
            # --------------------------------------------------

            if user.is_active != should_be_active:

                user.is_active = should_be_active

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

            # --------------------------------------------------
            # Update UserProfile
            # --------------------------------------------------

            changed_profile_fields = []

            department_id = (
                department.id
                if department
                else None
            )

            if (
                profile.department_id
                != department_id
            ):

                profile.department = department

                changed_profile_fields.append(
                    "department"
                )

            if changed_profile_fields:

                profile.save(
                    update_fields=(
                        changed_profile_fields
                    )
                )

            # --------------------------------------------------
            # Update integration mapping
            # --------------------------------------------------

            mapping.external_email = email
            mapping.last_synced_at = timezone.now()

            mapping.save(
                update_fields=[
                    "external_email",
                    "last_synced_at",
                    "updated_at",
                ]
            )

            stats["users_updated"] += 1
            stats["profiles_updated"] += 1
            stats["mappings_updated"] += 1

            logger.info(
                (
                    "BambooHR employee synchronized. "
                    "company=%s employee=%s "
                    "status=%s active=%s"
                ),
                company.id,
                external_id,
                employee_status or "unknown",
                should_be_active,
            )

            continue

        # ======================================================
        # NO EXTERNAL MAPPING
        # ======================================================

        existing_user = (
            User.objects
            .filter(
                email__iexact=email
            )
            .first()
        )

        # ======================================================
        # EXISTING DJANGO USER
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
                        role="EMPLOYEE",
                    )
                )

                stats[
                    "profiles_created"
                ] += 1

            else:

                # --------------------------------------------------
                # Do not move another company's employee
                # --------------------------------------------------

                if (
                    profile.company_id
                    and
                    profile.company_id
                    != company.id
                ):

                    stats["skipped"] += 1

                    errors.append(
                        {
                            "external_employee_id": (
                                external_id
                            ),
                            "email": email,
                            "error": (
                                "A ZepEx user with this "
                                "email belongs to "
                                "another company."
                            ),
                        }
                    )

                    continue

                profile.company = company
                profile.department = department

                profile.save(
                    update_fields=[
                        "company",
                        "department",
                    ]
                )

                stats[
                    "profiles_updated"
                ] += 1

            user = existing_user

            changed_fields = []

            if user.first_name != first_name:

                user.first_name = first_name

                changed_fields.append(
                    "first_name"
                )

            if user.last_name != last_name:

                user.last_name = last_name

                changed_fields.append(
                    "last_name"
                )

            # --------------------------------------------------
            # Existing user lifecycle
            # --------------------------------------------------

            if user.is_active != should_be_active:

                user.is_active = should_be_active

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
                    update_fields=changed_fields
                )

            stats[
                "users_updated"
            ] += 1

        # ======================================================
        # NEW DJANGO USER
        # ======================================================

        else:

            username_base = email
            username = username_base

            counter = 1

            while User.objects.filter(
                username=username
            ).exists():

                username = (
                    f"{username_base}-{counter}"
                )

                counter += 1

            user = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=should_be_active,
            )

            # --------------------------------------------------
            # BambooHR users don't receive a password here.
            # Invitation/access flow handles that separately.
            # --------------------------------------------------

            user.set_unusable_password()

            user.save(
                update_fields=[
                    "password",
                ]
            )

            stats[
                "users_created"
            ] += 1

            profile = UserProfile.objects.create(
                user=user,
                company=company,
                department=department,
                role="EMPLOYEE",
                force_password_change=True,
            )

            stats[
                "profiles_created"
            ] += 1

        # ======================================================
        # CREATE BAMBOOHR ↔ ZEPEX MAPPING
        # ======================================================

        IntegrationEmployeeMapping.objects.create(
            integration=integration,
            user_profile=profile,
            external_employee_id=external_id,
            external_email=email,
            last_synced_at=timezone.now(),
        )

        stats[
            "mappings_created"
        ] += 1

    # ==========================================================
    # PASS 3 — REPORTING MANAGERS
    # ==========================================================

    for employee_data in employees:

        employee_external_id = (
            _get_employee_id(
                employee_data
            )
        )

        if not employee_external_id:
            continue

        supervisor_external_id = (
            _get_supervisor_employee_id(
                employee_data
            )
        )

        # Employee has no BambooHR supervisor.
        if not supervisor_external_id:
            continue

        # ------------------------------------------------------
        # Find employee
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
        # Find manager
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
                        "Reporting manager could "
                        "not be mapped to a "
                        "ZepEx employee."
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
            continue

        if (
            manager_profile.company_id
            != company.id
        ):
            continue

        # ------------------------------------------------------
        # Prevent self-manager
        # ------------------------------------------------------

        if (
            employee_profile.id
            == manager_profile.id
        ):

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

        if (
            not employee_profile
            .reporting_manager_id
        ):

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

            continue

        # ------------------------------------------------------
        # Manager changed
        # ------------------------------------------------------

        if (
            employee_profile.reporting_manager_id
            != manager_profile.id
        ):

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

    # ==========================================================
    # PASS 4 — DEPARTMENT MANAGERS
    # ==========================================================
    #
    # Department.manager is inferred from the synchronized
    # reporting hierarchy.
    #
    # For each department, the same-department manager with
    # the largest number of direct reports becomes the
    # department manager.
    # ==========================================================

    departments = (
        Department.objects
        .filter(
            company=company,
            is_active=True,
        )
    )

    for department in departments:

        department_employees = (
            UserProfile.objects
            .filter(
                company=company,
                department=department,
                user__is_active=True,
            )
            .select_related(
                "reporting_manager",
                "reporting_manager__user",
            )
        )

        manager_counts = {}

        for employee_profile in (
            department_employees
        ):

            manager = (
                employee_profile.reporting_manager
            )

            if not manager:
                continue

            # --------------------------------------------------
            # Tenant safety
            # --------------------------------------------------

            if manager.company_id != company.id:
                continue

            # --------------------------------------------------
            # Ignore inactive managers
            # --------------------------------------------------

            if not manager.user.is_active:
                continue

            # --------------------------------------------------
            # Manager must belong to same department
            # --------------------------------------------------

            if (
                manager.department_id
                != department.id
            ):
                continue

            manager_id = manager.id

            if manager_id not in manager_counts:

                manager_counts[
                    manager_id
                ] = {
                    "manager": manager,
                    "count": 0,
                }

            manager_counts[
                manager_id
            ]["count"] += 1

        # ------------------------------------------------------
        # No candidate
        # ------------------------------------------------------

        if not manager_counts:

            stats[
                "department_managers_not_found"
            ] += 1

            continue

        # ------------------------------------------------------
        # Candidate with most direct reports
        # ------------------------------------------------------

        best_manager_data = max(
            manager_counts.values(),
            key=lambda item: item["count"],
        )

        manager_profile = (
            best_manager_data["manager"]
        )

        # ------------------------------------------------------
        # First assignment
        # ------------------------------------------------------

        if not department.manager_id:

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

            continue

        # ------------------------------------------------------
        # Manager changed
        # ------------------------------------------------------

        if (
            department.manager_id
            != manager_profile.id
        ):

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

    # ==========================================================
    # FINAL RESULT
    # ==========================================================

    return {
        "success": True,
        "stats": stats,
        "errors": errors,
    }
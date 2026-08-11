from .models import Integration


PROVIDER_CONFIG = {

    # -----------------------------
    # HRMS
    # -----------------------------

    Integration.PROVIDER_BAMBOOHR: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "API_KEY",
        "requires_client_id": False,
        "requires_client_secret": False,
    },

    Integration.PROVIDER_RIPPLING: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_WORKDAY: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_HIBOB: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_DEEL: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_ZOHO_PEOPLE: {
        "category": Integration.CATEGORY_HRMS,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    # -----------------------------
    # PAYROLL
    # -----------------------------

    Integration.PROVIDER_ADP: {
        "category": Integration.CATEGORY_PAYROLL,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_GUSTO: {
        "category": Integration.CATEGORY_PAYROLL,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_PAYCHEX: {
        "category": Integration.CATEGORY_PAYROLL,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_UKG: {
        "category": Integration.CATEGORY_PAYROLL,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_PAYLOCITY: {
        "category": Integration.CATEGORY_PAYROLL,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    # -----------------------------
    # ACCOUNTING
    # -----------------------------

    Integration.PROVIDER_QUICKBOOKS: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_XERO: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_SAGE: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_ZOHO_BOOKS: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_FRESHBOOKS: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_NETSUITE: {
        "category": Integration.CATEGORY_ACCOUNTING,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    # -----------------------------
    # IT / IDENTITY
    # -----------------------------

    Integration.PROVIDER_MICROSOFT_ENTRA: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_OKTA: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_GOOGLE_WORKSPACE: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_ONELOGIN: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_JUMPCLOUD: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "API_KEY",
        "requires_client_id": False,
        "requires_client_secret": False,
    },

    Integration.PROVIDER_PING_IDENTITY: {
        "category": Integration.CATEGORY_IT,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    # -----------------------------
    # ERP
    # -----------------------------

    Integration.PROVIDER_SAP: {
        "category": Integration.CATEGORY_ERP,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_ORACLE: {
        "category": Integration.CATEGORY_ERP,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_MICROSOFT_DYNAMICS: {
        "category": Integration.CATEGORY_ERP,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },

    Integration.PROVIDER_ODOO: {
        "category": Integration.CATEGORY_ERP,
        "auth_type": "API_KEY",
        "requires_client_id": False,
        "requires_client_secret": False,
    },

    Integration.PROVIDER_ACUMATICA: {
        "category": Integration.CATEGORY_ERP,
        "auth_type": "OAUTH2",
        "requires_client_id": True,
        "requires_client_secret": True,
    },
}
from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"

    def ready(self):
        from .email_poller import start_imap_poller_if_enabled

        start_imap_poller_if_enabled()

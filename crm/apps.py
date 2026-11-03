from django.apps import AppConfig

class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm"

    def ready(self):
        from . import signals  # noqa: F401
        from django.db.models.signals import post_migrate
        from django.dispatch import receiver

        @receiver(post_migrate, dispatch_uid="crm.create_role_groups")
        def create_role_groups(**kwargs):
            from django.contrib.auth.models import Group
            for name in ("Admin", "Manager", "Sales Executive"):
                Group.objects.get_or_create(name=name)

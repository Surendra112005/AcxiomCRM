from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .models import AuditLog

def _ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR") or None)

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(user=user, action="LOGIN", entity="Authentication", record_id=str(user.pk), ip_address=_ip(request))

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    AuditLog.objects.create(user=user, action="LOGOUT", entity="Authentication", record_id=str(user.pk) if user else "", ip_address=_ip(request))

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    username = credentials.get("username", "")
    AuditLog.objects.create(user=None, action="FAILED_LOGIN", entity="Authentication", record_id=username[:100],
                            new_data={"username": username[:150]}, ip_address=_ip(request) if request else None)

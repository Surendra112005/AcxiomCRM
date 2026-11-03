from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .models import Activity, AuditLog, Customer, FollowUp, Lead, Opportunity

class AdminOnlyMixin:
    def allowed(self, request):
        user = request.user
        return user.is_superuser or user.groups.filter(name="Admin").exists()
    def has_module_permission(self, request):
        return self.allowed(request)
    def has_view_permission(self, request, obj=None):
        return self.allowed(request)
    def has_add_permission(self, request):
        return self.allowed(request)
    def has_change_permission(self, request, obj=None):
        return self.allowed(request)
    def has_delete_permission(self, request, obj=None):
        return self.allowed(request)

for model in (Customer, Lead, Opportunity, FollowUp, Activity, AuditLog):
    admin.site.register(model, type(f"{model.__name__}Admin", (AdminOnlyMixin, admin.ModelAdmin), {}))

User = get_user_model()
for model in (User, Group):
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
admin.site.register(User, type("ProtectedUserAdmin", (AdminOnlyMixin, UserAdmin), {}))
admin.site.register(Group, type("ProtectedGroupAdmin", (AdminOnlyMixin, admin.ModelAdmin), {}))

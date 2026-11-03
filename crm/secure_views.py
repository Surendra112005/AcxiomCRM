import csv
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_POST
from rest_framework import serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .forms import (ActivityForm, CustomerForm, FollowUpForm, LeadForm, ManagedUserChangeForm,
                    ManagedUserCreationForm, OpportunityForm, normalize_phone)
from .models import Activity, AuditLog, Customer, FollowUp, Lead, Opportunity

User = get_user_model()
ROLES = ("Admin", "Manager", "Sales Executive")
MODEL_MAP = {"customers": (Customer, CustomerForm), "leads": (Lead, LeadForm),
             "opportunities": (Opportunity, OpportunityForm), "followups": (FollowUp, FollowUpForm),
             "activities": (Activity, ActivityForm)}

def role(user):
    if user.is_superuser or user.groups.filter(name="Admin").exists():
        return "Admin"
    if user.groups.filter(name="Manager").exists():
        return "Manager"
    return "Sales Executive"

def is_admin(user):
    return user.is_authenticated and role(user) == "Admin"

def visible(queryset, user):
    if is_admin(user) or role(user) == "Manager":
        return queryset
    model = queryset.model
    if model is Activity:
        return queryset.filter(user=user)
    if model in (Customer, Lead, Opportunity, FollowUp):
        return queryset.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True, created_by=user))
    return queryset.none()

def audit(request, action, entity, obj=None, old=None, new=None):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(user=request.user if request.user.is_authenticated else None,
        action=action, entity=entity, record_id=str(obj.pk) if obj else "",
        old_data=old, new_data=new, ip_address=ip or None)

def snapshot(obj):
    if not obj:
        return None
    return {f.name: str(getattr(obj, f.name)) for f in obj._meta.fields}

@login_required
def dashboard(request):
    customers = visible(Customer.objects.all(), request.user)
    leads = visible(Lead.objects.all(), request.user)
    opportunities = visible(Opportunity.objects.all(), request.user)
    followups = visible(FollowUp.objects.all(), request.user)
    now = timezone.now()
    lead_data = list(leads.values("status").annotate(count=Count("id")).order_by("status"))
    stage_data = list(opportunities.values("stage").annotate(count=Count("id")).order_by("stage"))
    pipeline_data = list(opportunities.exclude(stage__in=("Won", "Lost")).values("stage").annotate(total=Sum("amount")).order_by("stage"))
    sales = list(opportunities.filter(stage="Won").annotate(month=TruncMonth("created_at")).values("month").annotate(total=Sum("amount")).order_by("month"))
    upcoming = followups.filter(status="Planned", followup_date__gte=now).order_by("followup_date")
    overdue = followups.filter(status="Planned", followup_date__lt=now).order_by("followup_date")
    return render(request, "crm/dashboard_v2.html", {
        "customers": customers.count(), "leads": leads.count(),
        "open_leads": leads.exclude(status__in=["Converted", "Lost"]).count(),
        "opportunities": opportunities.count(), "pipeline": opportunities.exclude(stage__in=["Won", "Lost"]).aggregate(v=Sum("amount"))["v"] or 0,
        "won": opportunities.filter(stage="Won").count(), "lost": opportunities.filter(stage="Lost").count(),
        "upcoming_count": upcoming.count(), "overdue_count": overdue.count(), "upcoming": upcoming[:8],
        "lead_labels": json.dumps([x["status"] for x in lead_data]), "lead_values": json.dumps([x["count"] for x in lead_data]),
        "stage_labels": json.dumps([x["stage"] for x in stage_data]), "stage_values": json.dumps([x["count"] for x in stage_data]),
        "pipeline_labels": json.dumps([x["stage"] for x in pipeline_data]), "pipeline_values": json.dumps([float(x["total"] or 0) for x in pipeline_data]),
        "monthly_labels": json.dumps([x["month"].strftime("%b %Y") for x in sales]), "monthly_values": json.dumps([float(x["total"] or 0) for x in sales]),
    })

@login_required
def listing(request, kind):
    if kind not in MODEL_MAP:
        return redirect("dashboard")
    model, _ = MODEL_MAP[kind]
    qs = visible(model.objects.all(), request.user)
    q = request.GET.get("q", "").strip()
    if q:
        fields = {"customers": ("name", "email", "company", "phone", "city"), "leads": ("name", "email", "company", "phone", "status", "source"), "opportunities": ("name", "stage"), "followups": ("title", "remarks", "followup_type", "status"), "activities": ("title", "activity_type", "description")}[kind]
        query = Q()
        for field in fields:
            query |= Q(**{field + "__icontains": q})
        qs = qs.filter(query)
    for field in ("status", "source", "stage"):
        value = request.GET.get(field)
        if value and field in [f.name for f in model._meta.fields]:
            qs = qs.filter(**{field: value})
    assignee_field = "user" if model is Activity else "assigned_to"
    assignee_id = request.GET.get("assigned_to")
    if assignee_id and assignee_field in [f.name for f in model._meta.fields] and role(request.user) != "Sales Executive":
        qs = qs.filter(**{assignee_field + "_id": assignee_id})
    sort = request.GET.get("sort", "-id")
    allowed = {f.name for f in model._meta.fields}
    sort_field = sort.lstrip("-")
    qs = qs.order_by(sort if sort_field in allowed else "-id")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "crm/list.html", {"kind": kind, "objects": page, "page_obj": page,
        "q": q, "model_name": model.__name__, "can_delete": is_admin(request.user) or role(request.user) == "Sales Executive", "role": role(request.user),
        "statuses": getattr(model, "STATUS_CHOICES", ()), "sources": getattr(model, "SOURCE_CHOICES", ()), "stages": getattr(model, "STAGE_CHOICES", ()),
        "assigned_users": User.objects.filter(is_active=True).order_by("username") if role(request.user) != "Sales Executive" else (),
        "sort_fields": {"customers": ("name", "created_at", "status"), "leads": ("name", "created_at", "status"), "opportunities": ("name", "amount", "stage", "expected_close_date"), "followups": ("title", "followup_date", "status"), "activities": ("title", "activity_date", "activity_type")}[kind], "sort": sort})

@login_required
def detail(request, kind, pk):
    if kind not in MODEL_MAP:
        return redirect("dashboard")
    model, _ = MODEL_MAP[kind]
    obj = get_object_or_404(visible(model.objects.all(), request.user), pk=pk)
    context = {"kind": kind, "obj": obj}
    if model is Customer:
        context.update(opportunities=visible(obj.opportunities.all(), request.user),
                       activities=visible(obj.activities.select_related("user").all(), request.user),
                       followups=visible(obj.followups.order_by("followup_date"), request.user))
    elif model is Lead:
        context.update(opportunities=visible(obj.opportunities.all(), request.user),
                       activities=visible(obj.activities.select_related("user").all(), request.user),
                       followups=visible(obj.followups.order_by("followup_date"), request.user))
    elif model is Opportunity:
        context.update(activities=visible(obj.activities.select_related("user").all(), request.user),
                       followups=visible(obj.followups.order_by("followup_date"), request.user))
    elif model is Activity:
        context.update(related_customer=obj.customer if not obj.customer_id or visible(Customer.objects.filter(pk=obj.customer_id), request.user).exists() else None,
                       related_lead=obj.lead if not obj.lead_id or visible(Lead.objects.filter(pk=obj.lead_id), request.user).exists() else None,
                       related_opportunity=obj.opportunity if not obj.opportunity_id or visible(Opportunity.objects.filter(pk=obj.opportunity_id), request.user).exists() else None)
    return render(request, "crm/detail.html", context)

@login_required
@require_POST
@transaction.atomic
def convert_lead(request, pk):
    lead = get_object_or_404(visible(Lead.objects.select_for_update(), request.user), pk=pk)
    if lead.status == "Converted":
        messages.info(request, "This lead has already been converted.")
        return redirect("detail", kind="leads", pk=lead.pk)
    owner_id = lead.assigned_to_id or lead.created_by_id
    if role(request.user) == "Sales Executive" and owner_id != request.user.id:
        return HttpResponseForbidden("You cannot convert another user's lead.")
    all_matches = Customer.objects.filter(Q(email__iexact=lead.email) | Q(phone=lead.phone))
    matches = visible(all_matches, request.user)
    if role(request.user) == "Sales Executive" and all_matches.exists() and not matches.exists():
        return HttpResponseForbidden("The matching customer is outside your assignments.")
    if matches.count() > 1:
        messages.error(request, "This lead matches multiple customers. Resolve the duplicate before converting.")
        return redirect("detail", kind="leads", pk=lead.pk)
    customer = matches.first()
    customer_created = customer is None
    if customer_created:
        customer = Customer.objects.create(name=lead.name, email=lead.email, phone=lead.phone,
            company=lead.company, status="Active", created_by=request.user,
            assigned_to=lead.assigned_to or request.user)
        audit(request, "CREATE", "Customer", customer, None, snapshot(customer))
    if request.POST.get("create_opportunity"):
        opportunity = Opportunity.objects.create(name=request.POST.get("opportunity_name", "").strip() or f"{lead.company or lead.name} opportunity",
            customer=customer, lead=lead, amount=lead.expected_value, stage="Prospecting", probability=0,
            assigned_to=lead.assigned_to or request.user, created_by=request.user)
        audit(request, "CREATE", "Opportunity", opportunity, None, snapshot(opportunity))
    old = snapshot(lead)
    lead.status = "Converted"
    lead.save(update_fields=["status", "updated_at"])
    audit(request, "UPDATE", "Lead", lead, old, snapshot(lead))
    messages.success(request, "Lead converted to customer." if customer_created else "Lead linked to the existing customer.")
    return redirect("detail", kind="customers", pk=customer.pk)

@login_required
@require_POST
def complete_followup(request, pk):
    followup = get_object_or_404(visible(FollowUp.objects.all(), request.user), pk=pk)
    if role(request.user) == "Sales Executive" and (followup.assigned_to_id or followup.created_by_id) != request.user.id:
        return HttpResponseForbidden("You cannot update another user's follow-up.")
    old = snapshot(followup)
    followup.status = "Completed"
    followup.save(update_fields=["status"])
    audit(request, "UPDATE", "FollowUp", followup, old, snapshot(followup))
    messages.success(request, "Follow-up marked completed.")
    return redirect("listing", kind="followups")

@login_required
def edit(request, kind, pk=None):
    if kind not in MODEL_MAP:
        return redirect("dashboard")
    model, form_class = MODEL_MAP[kind]
    obj = get_object_or_404(visible(model.objects.all(), request.user), pk=pk) if pk else None
    owner_id = (getattr(obj, "assigned_to_id", None) or getattr(obj, "user_id", None)
                or getattr(obj, "created_by_id", None)) if obj else None
    if obj and role(request.user) == "Sales Executive" and owner_id != request.user.id:
        return HttpResponseForbidden("You cannot edit this record.")
    form = form_class(request.POST or None, instance=obj)
    if role(request.user) == "Sales Executive":
        for name in ("customer", "lead", "opportunity"):
            if name in form.fields:
                form.fields[name].queryset = visible(form.fields[name].queryset, request.user)
    if role(request.user) == "Sales Executive" and "assigned_to" in form.fields:
        form.fields["assigned_to"].queryset = User.objects.filter(pk=request.user.pk)
        form.fields["assigned_to"].initial = request.user
    if role(request.user) == "Sales Executive" and "user" in form.fields:
        form.fields["user"].queryset = User.objects.filter(pk=request.user.pk)
        form.fields["user"].initial = request.user
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if not obj and hasattr(item, "created_by_id"):
            item.created_by = request.user
        if isinstance(item, Activity) and role(request.user) == "Sales Executive":
            item.user = request.user
        if role(request.user) == "Sales Executive" and hasattr(item, "assigned_to_id"):
            item.assigned_to = request.user
        old = snapshot(obj)
        item.save()
        form.save_m2m()
        audit(request, "UPDATE" if obj else "CREATE", model.__name__, item, old, snapshot(item))
        messages.success(request, f"{model.__name__} saved.")
        return redirect("listing", kind=kind)
    return render(request, "crm/form.html", {"form": form, "kind": kind, "obj": obj})

@login_required
def delete(request, kind, pk):
    if kind not in MODEL_MAP:
        return redirect("dashboard")
    model, _ = MODEL_MAP[kind]
    obj = get_object_or_404(visible(model.objects.all(), request.user), pk=pk)
    if role(request.user) == "Manager":
        return HttpResponseForbidden("Managers cannot delete CRM records.")
    owner_id = getattr(obj, "assigned_to_id", None) or getattr(obj, "user_id", None) or getattr(obj, "created_by_id", None)
    if role(request.user) == "Sales Executive" and owner_id != request.user.id:
        return HttpResponseForbidden("You cannot delete another user's record.")
    if request.method == "POST":
        old = snapshot(obj)
        record_id = obj.pk
        obj.delete()
        audit(request, "DELETE", model.__name__, type("Record", (), {"pk": record_id})(), old, None)
        messages.success(request, f"{model.__name__} deleted.")
        return redirect("listing", kind=kind)
    return render(request, "crm/delete.html", {"obj": obj, "kind": kind})

@login_required
def audit_list(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")
    return render(request, "crm/audit.html", {"logs": logs[:300]})

@login_required
def users(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")
    qs = User.objects.prefetch_related("groups").order_by("username")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return render(request, "crm/users.html", {"users": Paginator(qs, 25).get_page(request.GET.get("page")), "q": q})

@login_required
def user_create(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")
    form = ManagedUserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request, "CREATE", "User", user, None, {"username": user.username, "role": role(user), "is_active": user.is_active})
        return redirect("users")
    return render(request, "crm/user_form.html", {"form": form, "title": "Create user"})

@login_required
def user_edit(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser and user != request.user:
        return HttpResponseForbidden("You cannot change another system administrator.")
    old = {"role": role(user), "is_active": user.is_active}
    form = ManagedUserChangeForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        changed = form.cleaned_data["role"].name != old["role"]
        updated = form.save()
        action = "ROLE_CHANGE" if changed else ("ACTIVATE" if updated.is_active and not old["is_active"] else "DEACTIVATE" if not updated.is_active and old["is_active"] else "UPDATE")
        audit(request, action, "User", updated, old, {"role": role(updated), "is_active": updated.is_active})
        return redirect("users")
    return render(request, "crm/user_form.html", {"form": form, "title": "Edit user", "target": user})

@login_required
@require_POST
def user_toggle(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser:
        return HttpResponseForbidden("System administrators cannot be deactivated here.")
    old = {"is_active": user.is_active}
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    audit(request, "ACTIVATE" if user.is_active else "DEACTIVATE", "User", user, old, {"is_active": user.is_active})
    return redirect("users")

@login_required
def reports(request, report_type="customers"):
    if role(request.user) == "Sales Executive":
        return HttpResponseForbidden("Reports are available to managers and administrators.")
    if report_type == "sales":
        won = visible(Opportunity.objects.all(), request.user).filter(stage="Won")
        for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
            value = request.GET.get(key)
            if value:
                try:
                    date.fromisoformat(value)
                    won = won.filter(**{lookup: value})
                except ValueError:
                    pass
        if request.GET.get("user"):
            won = won.filter(assigned_to_id=request.GET["user"])
        aggregates = list(won.annotate(month=TruncMonth("created_at")).values("month", "assigned_to__username").annotate(deals=Count("id"), revenue=Sum("amount")).order_by("month", "assigned_to__username"))
        columns = ["Month", "Sales executive", "Won deals", "Revenue"]
        rows = [[item["month"].strftime("%b %Y"), item["assigned_to__username"] or "Unassigned", str(item["deals"]), str(item["revenue"] or 0)] for item in aggregates]
        if request.GET.get("export") == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="sales-performance.csv"'
            writer = csv.writer(response)
            writer.writerow(columns)
            writer.writerows(rows)
            return response
        return render(request, "crm/reports.html", {"report_type": report_type, "objects": None, "columns": columns, "rows": rows,
            "total": sum(item["deals"] for item in aggregates), "summary": {"amount": sum((item["revenue"] or 0 for item in aggregates), 0)},
            "users": User.objects.filter(is_active=True).order_by("username"), "filters": request.GET, "statuses": (), "stages": (), "sources": ()})
    opportunities = visible(Opportunity.objects.all(), request.user)
    datasets = {"customers": visible(Customer.objects.all(), request.user), "leads": visible(Lead.objects.all(), request.user),
        "opportunities": opportunities, "followups": visible(FollowUp.objects.all(), request.user),
        "pipeline": opportunities.exclude(stage__in=("Won", "Lost")),
        "won-lost": opportunities.filter(stage__in=("Won", "Lost"))}
    qs = datasets.get(report_type, datasets["customers"])
    search = request.GET.get("q", "").strip()
    searchable = {"customers": ("name", "email", "company"), "leads": ("name", "email", "company"),
                  "opportunities": ("name",), "pipeline": ("name",), "won-lost": ("name",),
                  "followups": ("title", "remarks")}.get(report_type, ())
    if search:
        query = Q()
        for field in searchable:
            query |= Q(**{field + "__icontains": search})
        qs = qs.filter(query)
    status = request.GET.get("status")
    if status and "status" in [f.name for f in qs.model._meta.fields]:
        qs = qs.filter(status=status)
    stage = request.GET.get("stage")
    if stage and qs.model is Opportunity:
        qs = qs.filter(stage=stage)
    source = request.GET.get("source")
    if source and "source" in [f.name for f in qs.model._meta.fields]:
        qs = qs.filter(source=source)
    start_date, end_date = request.GET.get("date_from"), request.GET.get("date_to")
    date_field = "followup_date" if qs.model is FollowUp else "created_at"
    if start_date:
        try:
            date.fromisoformat(start_date)
            qs = qs.filter(**{date_field + "__date__gte": start_date})
        except ValueError:
            pass
    if end_date:
        try:
            date.fromisoformat(end_date)
            qs = qs.filter(**{date_field + "__date__lte": end_date})
        except ValueError:
            pass
    user_id = request.GET.get("user")
    if user_id:
        user_field = "user_id" if qs.model is Activity else "assigned_to_id"
        if user_field[:-3] in [f.name for f in qs.model._meta.fields]:
            qs = qs.filter(**{user_field: user_id})
    relations = [field.name for field in qs.model._meta.fields if field.is_relation and field.many_to_one]
    qs = qs.select_related(*relations)
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{report_type}-report.csv"'
        writer = csv.writer(response)
        fields = [f.name for f in qs.model._meta.fields]
        writer.writerow(fields)
        for obj in qs.iterator():
            values = [str(getattr(obj, field)) for field in fields]
            writer.writerow([("'" + value) if value.startswith(("=", "+", "-", "@")) else value for value in values])
        return response
    page = Paginator(qs.order_by("-id"), 25).get_page(request.GET.get("page"))
    columns = [field.verbose_name.title() for field in qs.model._meta.fields]
    rows = [[str(getattr(obj, field.name) or "") for field in qs.model._meta.fields] for obj in page.object_list]
    summary = {}
    if qs.model is Opportunity:
        summary = {"amount": qs.aggregate(amount=Sum("amount"))["amount"] or 0,
                   "won": qs.filter(stage="Won").count(), "lost": qs.filter(stage="Lost").count(),
                   "pipeline": qs.exclude(stage__in=("Won", "Lost")).aggregate(amount=Sum("amount"))["amount"] or 0}
    return render(request, "crm/reports.html", {"report_type": report_type, "objects": page, "columns": columns, "rows": rows, "total": qs.count(), "summary": summary,
        "users": User.objects.filter(is_active=True).order_by("username"), "filters": request.GET,
        "statuses": getattr(qs.model, "STATUS_CHOICES", ()), "stages": getattr(qs.model, "STAGE_CHOICES", ()),
        "sources": getattr(qs.model, "SOURCE_CHOICES", ())})

class OwnedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = type("CRMPageNumberPagination", (PageNumberPagination,), {"page_size": 20, "page_size_query_param": "page_size", "max_page_size": 100})
    def get_queryset(self):
        model = self.serializer_class.Meta.model
        qs = visible(model.objects.all(), self.request.user)
        for key in ("status", "source", "stage", "assigned_to"):
            if self.request.query_params.get(key) and key in [f.name for f in model._meta.fields]:
                if key != "assigned_to" or role(self.request.user) != "Sales Executive":
                    qs = qs.filter(**{key: self.request.query_params[key]})
        search = self.request.query_params.get("search", "").strip()
        if search:
            search_fields = {Customer: ("name", "email", "company", "phone"), Lead: ("name", "email", "company", "phone"), Opportunity: ("name", "stage")}.get(model, ())
            query = Q()
            for field in search_fields:
                query |= Q(**{field + "__icontains": search})
            qs = qs.filter(query)
        return qs.order_by("-id")
    def perform_create(self, serializer):
        data = {}
        model = self.serializer_class.Meta.model
        if any(f.name == "created_by" for f in model._meta.fields):
            data["created_by"] = self.request.user
        if role(self.request.user) == "Sales Executive" and any(f.name == "assigned_to" for f in model._meta.fields):
            data["assigned_to"] = self.request.user
        instance = serializer.save(**data)
        audit(self.request, "CREATE", model.__name__, instance, None, snapshot(instance))
    def perform_update(self, serializer):
        old = snapshot(serializer.instance)
        save_data = {}
        if role(self.request.user) == "Sales Executive" and any(f.name == "assigned_to" for f in serializer.instance._meta.fields):
            save_data["assigned_to"] = self.request.user
        instance = serializer.save(**save_data)
        audit(self.request, "UPDATE", instance.__class__.__name__, instance, old, snapshot(instance))
    def perform_destroy(self, instance):
        if role(self.request.user) == "Manager":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Managers cannot delete CRM records.")
        old = snapshot(instance)
        audit(self.request, "DELETE", instance.__class__.__name__, instance, old, None)
        instance.delete()

def validate_sales_references(attrs, request):
    if request and role(request.user) == "Sales Executive":
        for name in ("customer", "lead", "opportunity"):
            value = attrs.get(name)
            if value and not visible(value.__class__.objects.filter(pk=value.pk), request.user).exists():
                raise serializers.ValidationError({name: "You cannot reference a record outside your assignments."})

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")
    def validate_phone(self, value):
        value = normalize_phone(value)
        qs = Customer.objects.exclude(pk=self.instance.pk) if self.instance else Customer.objects.all()
        if qs.filter(phone=value).exists():
            raise serializers.ValidationError("A customer with this phone already exists.")
        return value
    def validate_email(self, value):
        qs = Customer.objects.exclude(pk=self.instance.pk) if self.instance else Customer.objects.all()
        if qs.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value
    def validate(self, attrs):
        request = self.context.get("request")
        if request and role(request.user) == "Sales Executive":
            validate_sales_references(attrs, request)
            attrs["assigned_to"] = request.user
        return attrs
class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")
    def validate_phone(self, value):
        return normalize_phone(value)
    def validate(self, attrs):
        duplicates = Lead.objects.exclude(pk=self.instance.pk) if self.instance else Lead.objects.all()
        email, phone = attrs.get("email", getattr(self.instance, "email", None)), attrs.get("phone", getattr(self.instance, "phone", None))
        if email and duplicates.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "A lead with this email already exists."})
        if phone and duplicates.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "A lead with this phone already exists."})
        request = self.context.get("request")
        if request and role(request.user) == "Sales Executive":
            validate_sales_references(attrs, request)
            attrs["assigned_to"] = request.user
        return attrs
class OpportunitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Opportunity
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")
    def validate(self, attrs):
        request = self.context.get("request")
        if request and role(request.user) == "Sales Executive":
            validate_sales_references(attrs, request)
            attrs["assigned_to"] = request.user
        return attrs
class CustomerAPI(OwnedModelViewSet):
    serializer_class = CustomerSerializer
class LeadAPI(OwnedModelViewSet):
    serializer_class = LeadSerializer
class OpportunityAPI(OwnedModelViewSet):
    serializer_class = OpportunitySerializer

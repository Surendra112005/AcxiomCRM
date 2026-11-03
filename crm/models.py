from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


# =========================
# CUSTOMER MODEL
# =========================

class Customer(models.Model):

    STATUS_CHOICES = [
        ("Active", "Active"),
        ("Inactive", "Inactive"),
        ("Prospect", "Prospect"),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    company = models.CharField(max_length=150, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Active"
    )

    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_customers"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_customers"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# =========================
# LEAD MODEL
# =========================

class Lead(models.Model):

    STATUS_CHOICES = [
        ("New", "New"),
        ("Contacted", "Contacted"),
        ("Qualified", "Qualified"),
        ("Converted", "Converted"),
        ("Lost", "Lost"),
    ]

    SOURCE_CHOICES = [
        ("Website", "Website"),
        ("Referral", "Referral"),
        ("Social Media", "Social Media"),
        ("Email Campaign", "Email Campaign"),
        ("Other", "Other"),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    company = models.CharField(max_length=150, blank=True)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="Other"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="New"
    )

    expected_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_leads"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# =========================
# OPPORTUNITY MODEL
# =========================

class Opportunity(models.Model):

    STAGE_CHOICES = [
        ("Prospecting", "Prospecting"),
        ("Qualification", "Qualification"),
        ("Proposal", "Proposal"),
        ("Negotiation", "Negotiation"),
        ("Won", "Won"),
        ("Lost", "Lost"),
    ]

    name = models.CharField(max_length=200)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    stage = models.CharField(
        max_length=30,
        choices=STAGE_CHOICES,
        default="Prospecting"
    )

    probability = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100)
        ]
    )

    expected_close_date = models.DateField(
        null=True,
        blank=True
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_opportunities"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_opportunities"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# =========================
# FOLLOW-UP MODEL
# =========================

class FollowUp(models.Model):

    TYPE_CHOICES = [
        ("Call", "Call"),
        ("Meeting", "Meeting"),
        ("Email", "Email"),
        ("Task", "Task"),
    ]

    STATUS_CHOICES = [
        ("Planned", "Planned"),
        ("Completed", "Completed"),
        ("Cancelled", "Cancelled"),
    ]

    title = models.CharField(max_length=200)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="followups"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="followups"
    )

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="followups"
    )

    followup_date = models.DateTimeField()

    followup_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="Call"
    )

    remarks = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Planned"
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_followups"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_followups"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# =========================
# ACTIVITY MODEL
# =========================

class Activity(models.Model):

    TYPE_CHOICES = [
        ("Call", "Call"),
        ("Meeting", "Meeting"),
        ("Email", "Email"),
        ("Task", "Task"),
    ]

    title = models.CharField(max_length=200)

    activity_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="Call"
    )

    description = models.TextField(blank=True)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities"
    )

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activities"
    )

    activity_date = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# =========================
# AUDIT LOG MODEL
# =========================

class AuditLog(models.Model):

    ACTION_CHOICES = [
        ("LOGIN", "Login"),
        ("FAILED_LOGIN", "Failed Login"),
        ("LOGOUT", "Logout"),
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DELETE", "Delete"),
        ("ROLE_CHANGE", "Role Change"),
        ("ACTIVATE", "Activate user"),
        ("DEACTIVATE", "Deactivate user"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES
    )

    entity = models.CharField(max_length=100)

    record_id = models.CharField(max_length=100, blank=True)

    old_data = models.JSONField(null=True, blank=True)

    new_data = models.JSONField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.entity} - {self.timestamp}"

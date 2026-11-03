from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from .models import Activity, Customer, Lead, Opportunity, FollowUp

User = get_user_model()
ROLE_NAMES = ("Admin", "Manager", "Sales Executive")

def normalize_phone(value):
    value = value.strip()
    if not value.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "").isdigit():
        raise ValidationError("Enter a valid phone number.")
    normalized = ("+" if value.startswith("+") else "") + "".join(ch for ch in value if ch.isdigit())
    if len(normalized) < 7 or len(normalized) > 15:
        raise ValidationError("Enter a phone number between 7 and 15 digits.")
    return normalized

class BootstrapForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

class CustomerForm(BootstrapForm):
    class Meta:
        model = Customer
        exclude = ["created_at", "updated_at", "created_by"]
    def clean_phone(self):
        value = normalize_phone(self.cleaned_data["phone"])
        qs = Customer.objects.exclude(pk=self.instance.pk) if self.instance.pk else Customer.objects.all()
        if qs.filter(phone=value).exists():
            raise ValidationError("A customer with this phone already exists.")
        return value
    def clean_email(self):
        value = self.cleaned_data["email"].strip()
        qs = Customer.objects.exclude(pk=self.instance.pk) if self.instance.pk else Customer.objects.all()
        if qs.filter(email__iexact=value).exists():
            raise ValidationError("A customer with this email already exists.")
        return value

class LeadForm(BootstrapForm):
    class Meta:
        model = Lead
        exclude = ["created_at", "updated_at", "created_by"]
    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])
    def clean(self):
        cleaned = super().clean()
        email, phone = cleaned.get("email"), cleaned.get("phone")
        duplicates = Lead.objects.exclude(pk=self.instance.pk) if self.instance.pk else Lead.objects.all()
        if email and duplicates.filter(email__iexact=email).exists():
            self.add_error("email", "A lead with this email already exists.")
        if phone and duplicates.filter(phone=phone).exists():
            self.add_error("phone", "A lead with this phone already exists.")
        return cleaned

class OpportunityForm(BootstrapForm):
    class Meta:
        model = Opportunity
        exclude = ["created_at", "updated_at", "created_by"]

class FollowUpForm(BootstrapForm):
    class Meta:
        model = FollowUp
        exclude = ["created_by", "created_at"]
    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(field) for field in ("customer", "lead", "opportunity")):
            raise ValidationError("Link the follow-up to a customer, lead, or opportunity.")
        return cleaned

class ActivityForm(BootstrapForm):
    class Meta:
        model = Activity
        exclude = ["created_at"]

class ManagedUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ModelChoiceField(queryset=Group.objects.filter(name__in=ROLE_NAMES))
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_active")
    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.groups.set([self.cleaned_data["role"]])
        return user

class ManagedUserChangeForm(forms.ModelForm):
    role = forms.ModelChoiceField(queryset=Group.objects.filter(name__in=ROLE_NAMES))
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_active", "role")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["role"].initial = self.instance.groups.filter(name__in=ROLE_NAMES).first()
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.groups.set([self.cleaned_data["role"]])
        return user

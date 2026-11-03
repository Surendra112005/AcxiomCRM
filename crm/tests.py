from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Activity, AuditLog, Customer, FollowUp, Lead, Opportunity

User = get_user_model()

class CRMTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group, _ = Group.objects.get_or_create(name="Admin")
        cls.manager_group, _ = Group.objects.get_or_create(name="Manager")
        cls.sales_group, _ = Group.objects.get_or_create(name="Sales Executive")
        cls.admin = User.objects.create_user("crm_admin", password="Example-pass-862!", is_staff=True)
        cls.admin.groups.add(cls.admin_group)
        cls.manager = User.objects.create_user("crm_manager", password="Example-pass-862!", is_staff=True)
        cls.manager.groups.add(cls.manager_group)
        cls.sales = User.objects.create_user("crm_sales", password="Example-pass-862!")
        cls.sales.groups.add(cls.sales_group)
        cls.other_sales = User.objects.create_user("crm_sales2", password="Example-pass-862!")
        cls.other_sales.groups.add(cls.sales_group)

    def client_for(self, user):
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        return client

    def test_authentication_and_role_boundaries(self):
        anonymous = Client(HTTP_HOST="localhost")
        self.assertEqual(anonymous.get(reverse("dashboard")).status_code, 302)
        self.assertEqual(self.client_for(self.manager).get(reverse("users")).status_code, 403)
        self.assertEqual(self.client_for(self.manager).get(reverse("audit")).status_code, 403)
        sales_client = self.client_for(self.sales)
        self.assertEqual(sales_client.get(reverse("users")).status_code, 403)
        self.assertEqual(sales_client.get(reverse("audit")).status_code, 403)
        self.assertEqual(sales_client.get(reverse("reports")).status_code, 403)
        self.assertEqual(self.client_for(self.admin).get(reverse("users")).status_code, 200)

    def test_staff_manager_cannot_bypass_rbac_in_django_admin(self):
        client = self.client_for(self.manager)
        self.assertEqual(client.get("/admin/crm/customer/add/").status_code, 403)
        self.assertEqual(client.get("/admin/auth/user/add/").status_code, 403)

    def test_sales_record_scope_and_detail_idor(self):
        mine = Customer.objects.create(name="My Customer", email="mine@example.test", phone="1111111111", created_by=self.sales, assigned_to=self.sales)
        theirs = Customer.objects.create(name="Other Customer", email="other@example.test", phone="2222222222", created_by=self.other_sales, assigned_to=self.other_sales)
        client = self.client_for(self.sales)
        response = client.get(reverse("listing", args=("customers",)))
        self.assertContains(response, mine.name)
        self.assertNotContains(response, theirs.name)
        self.assertEqual(client.get(reverse("detail", args=("customers", theirs.pk))).status_code, 404)
        self.assertEqual(client.get(reverse("edit", args=("customers", theirs.pk))).status_code, 404)
        self.assertEqual(client.get(reverse("delete", args=("customers", theirs.pk))).status_code, 404)
        self.assertEqual(client.get(reverse("detail", args=("customers", mine.pk))).status_code, 200)

    def test_detail_does_not_leak_related_other_owner_records(self):
        customer = Customer.objects.create(name="Visible customer", email="visible@example.test", phone="1212121212", created_by=self.sales, assigned_to=self.sales)
        hidden = Opportunity.objects.create(name="Confidential deal", amount=Decimal("999"), customer=customer, assigned_to=self.other_sales, created_by=self.other_sales)
        response = self.client_for(self.sales).get(reverse("detail", args=("customers", customer.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, hidden.name)

    def test_customer_crud_validation_and_audit(self):
        client = self.client_for(self.admin)
        url = reverse("new", args=("customers",))
        bad = client.post(url, {"name": "Bad", "email": "not-email", "phone": "phone"})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(Customer.objects.filter(name="Bad").exists())
        payload = {"name": "Northwind", "email": "northwind@example.test", "phone": "+1 555-111-2222", "company": "Northwind", "address": "1 Main", "city": "Seattle", "state": "WA", "status": "Active"}
        self.assertEqual(client.post(url, payload).status_code, 302)
        customer = Customer.objects.get(email=payload["email"])
        self.assertTrue(AuditLog.objects.filter(entity="Customer", record_id=str(customer.pk), action="CREATE").exists())
        edit_url = reverse("edit", args=("customers", customer.pk))
        payload["name"] = "Northwind Updated"
        self.assertEqual(client.post(edit_url, payload).status_code, 302)
        self.assertEqual(Customer.objects.get(pk=customer.pk).name, payload["name"])
        self.assertEqual(client.post(reverse("delete", args=("customers", customer.pk))).status_code, 302)
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())

    def test_customer_duplicate_and_required_field_validation(self):
        Customer.objects.create(name="Existing", email="duplicate@example.test", phone="+15551234567")
        client = self.client_for(self.admin)
        url = reverse("new", args=("customers",))
        base = {"name": "Duplicate", "email": "new@example.test", "phone": "5551234568", "status": "Active"}
        self.assertEqual(client.post(url, {**base, "email": "DUPLICATE@example.test"}).status_code, 200)
        self.assertEqual(client.post(url, {**base, "phone": "+1 (555) 123-4567"}).status_code, 200)
        self.assertEqual(client.post(url, {**base, "name": ""}).status_code, 200)
        self.assertEqual(client.post(url, {**base, "phone": "bad-phone"}).status_code, 200)
        self.assertEqual(Customer.objects.count(), 1)

    def test_lead_crud_conversion_and_duplicate_prevention(self):
        client = self.client_for(self.sales)
        lead_payload = {"name": "Form lead", "email": "lead-form@example.test", "phone": "3333333334", "company": "Form Co", "source": "Website", "status": "New", "expected_value": "50.00", "assigned_to": self.sales.pk}
        self.assertEqual(client.post(reverse("new", args=("leads",)), lead_payload).status_code, 302)
        form_lead = Lead.objects.get(email="lead-form@example.test")
        self.assertEqual(form_lead.assigned_to, self.sales)
        lead_payload["name"] = "Form lead edited"
        self.assertEqual(client.post(reverse("edit", args=("leads", form_lead.pk)), lead_payload).status_code, 302)
        self.assertEqual(Lead.objects.get(pk=form_lead.pk).name, "Form lead edited")
        self.assertEqual(client.post(reverse("delete", args=("leads", form_lead.pk))).status_code, 302)
        lead = Lead.objects.create(name="Contoso", email="contoso@example.test", phone="3333333333", company="Contoso", expected_value=Decimal("1200"), created_by=self.sales, assigned_to=self.sales)
        response = client.post(reverse("lead_convert", args=(lead.pk,)), {"create_opportunity": "on"})
        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "Converted")
        customer = Customer.objects.get(email=lead.email)
        self.assertEqual(Opportunity.objects.filter(lead=lead, customer=customer).count(), 1)
        client.post(reverse("lead_convert", args=(lead.pk,)), {"create_opportunity": "on"})
        self.assertEqual(Opportunity.objects.filter(lead=lead).count(), 1)
        self.assertTrue(AuditLog.objects.filter(entity="Lead", record_id=str(lead.pk), action="UPDATE").exists())

    def test_opportunity_probability_validation_and_visibility(self):
        opportunity = Opportunity.objects.create(name="Private deal", amount=Decimal("100"), probability=75, assigned_to=self.other_sales, created_by=self.other_sales)
        self.assertEqual(self.client_for(self.sales).get(reverse("detail", args=("opportunities", opportunity.pk))).status_code, 404)
        self.assertEqual(self.client_for(self.manager).get(reverse("detail", args=("opportunities", opportunity.pk))).status_code, 200)

    def test_opportunity_form_crud(self):
        client = self.client_for(self.admin)
        customer = Customer.objects.create(name="Deal customer", email="deal@example.test", phone="7777777777", created_by=self.admin)
        payload = {"name": "New deal", "customer": customer.pk, "amount": "800.00", "stage": "Proposal", "probability": "50", "expected_close_date": "2030-01-01", "assigned_to": self.sales.pk}
        invalid = {**payload, "name": "Invalid deal", "amount": "-10", "probability": "101"}
        self.assertEqual(client.post(reverse("new", args=("opportunities",)), invalid).status_code, 200)
        self.assertFalse(Opportunity.objects.filter(name="Invalid deal").exists())
        self.assertEqual(client.post(reverse("new", args=("opportunities",)), payload).status_code, 302)
        opportunity = Opportunity.objects.get(name="New deal")
        self.assertEqual(client.get(reverse("detail", args=("opportunities", opportunity.pk))).status_code, 200)
        payload["name"] = "Updated deal"
        payload["probability"] = "150"
        self.assertEqual(client.post(reverse("edit", args=("opportunities", opportunity.pk)), payload).status_code, 200)
        self.assertEqual(Opportunity.objects.get(pk=opportunity.pk).probability, 50)
        payload["probability"] = "75"
        self.assertEqual(client.post(reverse("edit", args=("opportunities", opportunity.pk)), payload).status_code, 302)
        self.assertEqual(Opportunity.objects.get(pk=opportunity.pk).probability, 75)
        self.assertEqual(client.post(reverse("delete", args=("opportunities", opportunity.pk))).status_code, 302)
        self.assertFalse(Opportunity.objects.filter(pk=opportunity.pk).exists())

    def test_followup_past_date_is_recorded_as_overdue(self):
        client = self.client_for(self.admin)
        customer = Customer.objects.create(name="Past date customer", email="past-date@example.test", phone="7777777778", created_by=self.admin)
        past = (timezone.localtime(timezone.now()) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = client.post(reverse("new", args=("followups",)), {"title": "Overdue check", "customer": customer.pk,
            "followup_date": past, "followup_type": "Call", "status": "Planned"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FollowUp.objects.filter(title="Overdue check", followup_date__lt=timezone.now(), status="Planned").exists())

    def test_followup_completion_and_access(self):
        customer = Customer.objects.create(name="Follow customer", email="follow@example.test", phone="4444444444", created_by=self.sales, assigned_to=self.sales)
        followup = FollowUp.objects.create(title="Call", customer=customer, followup_date=timezone.now() + timedelta(days=1), assigned_to=self.sales, created_by=self.sales)
        client = self.client_for(self.sales)
        self.assertEqual(client.post(reverse("followup_complete", args=(followup.pk,))).status_code, 302)
        followup.refresh_from_db()
        self.assertEqual(followup.status, "Completed")
        self.assertTrue(AuditLog.objects.filter(entity="FollowUp", record_id=str(followup.pk), action="UPDATE").exists())

    def test_followup_form_create_update_and_delete(self):
        client = self.client_for(self.admin)
        customer = Customer.objects.create(name="Form customer", email="form-cust@example.test", phone="8888888888", created_by=self.admin)
        form_date = (timezone.localtime(timezone.now()) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        payload = {"title": "Follow-up form", "customer": customer.pk, "followup_date": form_date, "followup_type": "Meeting", "remarks": "Discuss renewal", "status": "Planned", "assigned_to": self.sales.pk}
        self.assertEqual(client.post(reverse("new", args=("followups",)), payload).status_code, 302)
        followup = FollowUp.objects.get(title="Follow-up form")
        payload["title"] = "Updated follow-up"
        self.assertEqual(client.post(reverse("edit", args=("followups", followup.pk)), payload).status_code, 302)
        self.assertEqual(FollowUp.objects.get(pk=followup.pk).title, "Updated follow-up")
        self.assertEqual(client.post(reverse("delete", args=("followups", followup.pk))).status_code, 302)

    def test_activity_create_edit_and_customer_history(self):
        client = self.client_for(self.sales)
        customer = Customer.objects.create(name="Activity customer", email="activity@example.test", phone="8888888889", created_by=self.sales, assigned_to=self.sales)
        payload = {"title": "Renewal call", "activity_type": "Call", "description": "Discussed renewal", "customer": customer.pk, "activity_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "user": self.sales.pk}
        self.assertEqual(client.post(reverse("new", args=("activities",)), payload).status_code, 302)
        activity = Activity.objects.get(title="Renewal call")
        self.assertEqual(activity.user, self.sales)
        self.assertContains(client.get(reverse("detail", args=("customers", customer.pk))), "Renewal call")
        payload["title"] = "Renewal email"
        payload["activity_type"] = "Email"
        self.assertEqual(client.post(reverse("edit", args=("activities", activity.pk)), payload).status_code, 302)
        self.assertEqual(Activity.objects.get(pk=activity.pk).title, "Renewal email")
        self.assertEqual(client.post(reverse("delete", args=("activities", activity.pk))).status_code, 302)

    def test_login_failed_logout_audit(self):
        client = Client(HTTP_HOST="localhost")
        client.post(reverse("login"), {"username": self.sales.username, "password": "wrong-password"})
        self.assertTrue(AuditLog.objects.filter(action="FAILED_LOGIN").exists())
        self.assertTrue(client.login(username="crm_sales", password="Example-pass-862!"))
        client.post(reverse("logout"))
        self.assertTrue(AuditLog.objects.filter(user=self.sales, action="LOGIN").exists())
        self.assertTrue(AuditLog.objects.filter(user=self.sales, action="LOGOUT").exists())

    def test_api_auth_scope_create_update_delete_and_pagination(self):
        mine = Customer.objects.create(name="API mine", email="api-mine@example.test", phone="5555555551", created_by=self.sales, assigned_to=self.sales)
        theirs = Customer.objects.create(name="API theirs", email="api-theirs@example.test", phone="5555555552", created_by=self.other_sales, assigned_to=self.other_sales)
        anon = APIClient()
        self.assertEqual(anon.get("/api/customers/").status_code, 403)
        api = APIClient()
        api.force_authenticate(self.sales)
        listing = api.get("/api/customers/")
        self.assertEqual(listing.status_code, 200)
        self.assertIn("results", listing.data)
        self.assertEqual(api.get("/api/customers/", {"search": "API mine"}).data["count"], 1)
        self.assertEqual(api.get("/api/leads/").status_code, 200)
        self.assertEqual(api.get("/api/opportunities/").status_code, 200)
        self.assertEqual(api.get(f"/api/customers/{theirs.pk}/").status_code, 404)
        self.assertEqual(api.get(f"/api/customers/{mine.pk}/").status_code, 200)
        forbidden_link = api.post("/api/opportunities/", {"name": "Cross-owner deal", "amount": "900.00", "customer": theirs.pk, "stage": "Proposal", "probability": 35}, format="json")
        self.assertEqual(forbidden_link.status_code, 400)
        created = api.post("/api/customers/", {"name": "API created", "email": "api-created@example.test", "phone": "5555555553", "status": "Active", "assigned_to": self.other_sales.pk}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["assigned_to"], self.sales.pk)
        self.assertEqual(api.patch(f"/api/customers/{created.data['id']}/", {"name": "API updated"}, format="json").status_code, 200)
        self.assertEqual(api.delete(f"/api/customers/{created.data['id']}/").status_code, 204)
        lead_response = api.post("/api/leads/", {"name": "API lead", "email": "api-lead@example.test", "phone": "5555555554", "source": "Referral", "status": "New", "expected_value": "250.00"}, format="json")
        self.assertEqual(lead_response.status_code, 201)
        self.assertEqual(api.patch(f"/api/leads/{lead_response.data['id']}/", {"status": "Qualified"}, format="json").status_code, 200)
        self.assertEqual(api.delete(f"/api/leads/{lead_response.data['id']}/").status_code, 204)
        opportunity_response = api.post("/api/opportunities/", {"name": "API deal", "amount": "900.00", "stage": "Proposal", "probability": 35}, format="json")
        self.assertEqual(opportunity_response.status_code, 201)
        self.assertEqual(api.patch(f"/api/opportunities/{opportunity_response.data['id']}/", {"stage": "Won"}, format="json").status_code, 200)
        self.assertEqual(api.delete(f"/api/opportunities/{opportunity_response.data['id']}/").status_code, 204)
        invalid_customer = api.post("/api/customers/", {"name": "Bad API", "email": "not-email", "phone": "xx", "status": "Active"}, format="json")
        self.assertEqual(invalid_customer.status_code, 400)
        invalid_opp = api.post("/api/opportunities/", {"name": "Bad deal", "amount": "-10", "stage": "Proposal", "probability": 101}, format="json")
        self.assertEqual(invalid_opp.status_code, 400)

    def test_listing_search_filters_sorting_and_pagination(self):
        for index in range(23):
            Customer.objects.create(name=f"Customer {index:02}", email=f"list-{index}@example.test", phone=f"900000{index:04}", status="Active" if index % 2 else "Prospect", created_by=self.manager)
        client = self.client_for(self.manager)
        paginated = client.get(reverse("listing", args=("customers",)))
        self.assertTrue(paginated.context["page_obj"].has_next())
        page_two = client.get(reverse("listing", args=("customers",)), {"page": 2})
        self.assertEqual(page_two.status_code, 200)
        filtered = client.get(reverse("listing", args=("customers",)), {"q": "Customer 03", "status": "Active"})
        self.assertEqual(filtered.context["page_obj"].paginator.count, 1)
        sorted_page = client.get(reverse("listing", args=("customers",)), {"sort": "name"})
        self.assertEqual(sorted_page.context["objects"][0].name, "Customer 00")

    def test_dashboard_reports_and_csv(self):
        customer = Customer.objects.create(name="Metric customer", email="metric@example.test", phone="6666666666", created_by=self.manager)
        Lead.objects.create(name="Metric lead", email="metric-lead@example.test", phone="6666666667", source="Referral", status="New", created_by=self.manager)
        Opportunity.objects.create(name="Pipeline", amount=Decimal("500"), stage="Proposal", probability=50, customer=customer, created_by=self.manager)
        Opportunity.objects.create(name="Won deal", amount=Decimal("200"), stage="Won", probability=100, customer=customer, assigned_to=self.manager, created_by=self.manager)
        FollowUp.objects.create(title="Metric followup", customer=customer, followup_date=timezone.now() + timedelta(days=1), created_by=self.manager)
        client = self.client_for(self.manager)
        dashboard = client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["pipeline"], Decimal("500"))
        report = client.get(reverse("reports_type", args=("pipeline",)), {"date_from": "2020-01-01"})
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.context["total"], 1)
        for report_type in ("customers", "leads", "opportunities", "pipeline", "won-lost", "followups", "sales"):
            with self.subTest(report=report_type):
                self.assertEqual(client.get(reverse("reports_type", args=(report_type,))).status_code, 200)
                csv_response = client.get(reverse("reports_type", args=(report_type,)), {"export": "csv", "date_from": "2020-01-01"})
                self.assertEqual(csv_response.status_code, 200)
                self.assertIn("text/csv", csv_response["Content-Type"])

    def test_user_create_role_and_activation(self):
        client = self.client_for(self.admin)
        role = Group.objects.get(name="Sales Executive")
        response = client.post(reverse("user_create"), {"username": "created_exec", "email": "exec@example.test", "role": role.pk,
            "password1": "A-strong-demo-password-938!", "password2": "A-strong-demo-password-938!", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="created_exec")
        self.assertEqual(user.groups.first(), role)
        self.assertTrue(AuditLog.objects.filter(entity="User", record_id=str(user.pk), action="CREATE").exists())
        self.assertEqual(client.post(reverse("user_toggle", args=(user.pk,))).status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        manager = Group.objects.get(name="Manager")
        edit_response = client.post(reverse("user_edit", args=(user.pk,)), {"username": user.username, "email": user.email,
            "role": manager.pk, "is_active": "on"})
        self.assertEqual(edit_response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.groups.first(), manager)
        self.assertTrue(AuditLog.objects.filter(entity="User", record_id=str(user.pk), action="ROLE_CHANGE").exists())

# AcxiomCRM

AcxiomCRM is a Django-based customer relationship management application for managing customers, leads, opportunities, follow-ups, activities, users, reports, and audit history. It includes role-aware web pages and authenticated REST APIs.

## Features

- Role-based access for Admin, Manager, and Sales Executive accounts.
- Customer, lead, opportunity, follow-up, and activity management.
- Lead conversion into a customer, optionally creating an opportunity.
- Dashboard KPIs and Chart.js lead, opportunity, sales, and pipeline charts.
- Search, filters, sorting, pagination, detail pages, and responsive navigation.
- User management, role assignment, account activation, and audit logs.
- Filterable reports with CSV exports.
- Authenticated, role-scoped REST APIs for customers, leads, and opportunities.
- Django password validation and audit events for authentication and CRM changes.

## Technologies

- Python 3.11+
- Django 5.2
- Django REST Framework
- SQLite for local development
- Bootstrap 5, CSS, JavaScript, and Chart.js

## Installation

Open PowerShell in this folder. The commands below create a virtual environment, install dependencies, and prepare a local-only secret file. `.env` and the SQLite database are excluded from Git.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace `DJANGO_SECRET_KEY` with a unique random value. For example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `DJANGO_DEBUG=True` for local development and include `127.0.0.1,localhost` in `DJANGO_ALLOWED_HOSTS`. Keep `.env` private.

## Run the application

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The first superuser has Admin access. Use **Users** in the CRM to create accounts and assign the **Admin**, **Manager**, or **Sales Executive** role. Role groups are created automatically after migrations. Existing superusers retain Admin access.

The existing database is `db.sqlite3`. The customer assignment migration adds a nullable field, preserving existing customer records. Back up the database before applying future migrations.

## Tests and checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

The test suite covers authentication, role restrictions, CRUD workflows, lead conversion, API access and validation, reports, CSV export, dashboard metrics, and audit events. Browser test evidence, when available, is recorded in `ACXIOMCRM_FINAL_TEST_REPORT.md` and `browser_artifacts/`.

## REST API

The authenticated API routes are:

- `/api/customers/`
- `/api/leads/`
- `/api/opportunities/`

List endpoints support pagination, search, and model filters. Sales Executives receive assigned-record scope; Manager and Admin access follows the CRM role policy.

## Project structure

```text
acxiomcrm_django/
├── acxiomcrm/             # Django project settings and URL configuration
├── crm/                   # CRM models, forms, views, APIs, and signals
│   ├── migrations/        # Database migrations
│   ├── static/crm/        # CRM stylesheet
│   ├── templates/         # Login and CRM templates
│   └── tests.py           # Automated Django tests
├── .env.example           # Safe local environment template
├── manage.py
├── requirements.txt
└── README.md
```

## Deployment notes

Before deployment, set a private `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, and a production `DJANGO_ALLOWED_HOSTS` list through the hosting environment. Do not deploy `.env`, `db.sqlite3`, or development credentials. Configure HTTPS, secure cookies, a production database, database backups, static file hosting, logging, and an appropriate WSGI/ASGI server. Run `python manage.py migrate` and `python manage.py collectstatic` as part of deployment.

Bootstrap and Chart.js are currently loaded from public CDNs; production deployments should account for those external dependencies or serve the assets locally.
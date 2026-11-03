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
- SQLite for local development and PostgreSQL in production
- Gunicorn, WhiteNoise, and psycopg for Render deployment
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

For local development, keep `DATABASE_URL` empty to use SQLite. In production, configure a PostgreSQL `DATABASE_URL` and `DJANGO_DEBUG=False`.

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

### Deploy to Render with PostgreSQL

1. Sign in to [Render](https://render.com/) and choose **Continue with GitHub**. Authorize Render to access the `Surendra112005/AcxiomCRM` repository.
2. In the Render dashboard, create a **PostgreSQL** database. Choose a region and plan, then copy its **Internal Database URL** from the database page. Keep that URL private.
3. Create a **Web Service**, connect `https://github.com/Surendra112005/AcxiomCRM`, and select the `main` branch and Python runtime. Set the service root directory to `acxiomcrm_django` only if the repository is later changed to a monorepo; in the current repository the Django project files are at its root, so leave it blank.
4. Set the build command to `bash build.sh` and the start command to `gunicorn acxiomcrm.wsgi:application`.
5. Add these web service environment variables:

   | Key | Value |
   | --- | --- |
   | `DJANGO_SECRET_KEY` | Generate a new private value in Render. Do not reuse the local `.env` key. |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | The Render hostname, for example `acxiomcrm.onrender.com` (without `https://`). |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | The Render origin, for example `https://acxiomcrm.onrender.com`. |
   | `DATABASE_URL` | The PostgreSQL database's **Internal Database URL**. |

   `RENDER_EXTERNAL_HOSTNAME`, when provided by Render, is also added automatically to allowed hosts and CSRF origins. Keep the Render database and web service in the same region so the internal URL can be used.
6. Create the service and wait for the build and deploy to finish. The build installs requirements, runs Django system checks, collects static files, and applies pending migrations. It does not create an admin account automatically.
7. In the web service's **Shell**, run `python manage.py createsuperuser` and follow the prompts. Then open the service's `https://<service-name>.onrender.com` URL and sign in at `/admin/` or the CRM login page.

For a custom domain, add its hostname to `DJANGO_ALLOWED_HOSTS` and its `https://` origin to `DJANGO_CSRF_TRUSTED_ORIGINS`. Render terminates HTTPS and forwards the original scheme; Django redirects HTTP to HTTPS and enables secure cookies and HSTS when `DJANGO_DEBUG=False`.

To confirm PostgreSQL persistence, create a harmless test record, restart or redeploy the web service, and confirm that the record remains. The database is a separate Render service; do not use SQLite on an ephemeral web-service filesystem for production data. Back up the PostgreSQL database before schema or data maintenance.

The local `db.sqlite3` remains excluded and is not copied or migrated by deployment. Existing migrations are applied normally with `manage.py migrate`; no database reset or destructive migration command is used.

Bootstrap and Chart.js are currently loaded from public CDNs; production deployments should account for those external dependencies or serve the assets locally.

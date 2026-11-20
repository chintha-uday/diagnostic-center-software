# Diagnostic Center Software

A Django-based starter for diagnostic centers, designed to run as either a hosted multi-center service or a separate installation for one center. Each patient, order, and test belongs to a center; every application query is scoped to the signed-in user's selected center.

## MVP workflow

- Register patients and create diagnostic test orders.
- Record sample collection and enter test results.
- Require a reviewer to release completed results.
- View a printable report only after release.
- Keep tenant data separated by center membership.

This is an early development starter, not a validated clinical or regulatory product. Do not use real patient information until security, privacy, backup, clinical, and local regulatory requirements have been independently reviewed. Public repository content must contain synthetic data only.

## Run locally

Requirements: Python 3.13 and PostgreSQL for deployment. SQLite is used by default for local development.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_center --name "Demo Diagnostic Center" --username <superuser>
python manage.py runserver
```

Sign in at `http://127.0.0.1:8000/accounts/login/`. The `setup_center` command attaches the existing superuser to the new center and adds a small test catalog.

## Deployment

The same application supports both deployment models:

- **Cloud SaaS:** set `DATABASE_URL` to a managed PostgreSQL database and deploy one application instance. Create a separate `Center` and membership for each customer.
- **Single-center installation:** deploy the same container stack for one center and create one center membership. Its database and backups remain separate from other installations.

Copy `.env.example` to `.env` for local container development. Start the stack with `docker compose up --build`; apply migrations with `docker compose exec web python manage.py migrate`. Static files are served by WhiteNoise. Before internet deployment, set `DEBUG=0`, a unique `SECRET_KEY`, the deployment's `ALLOWED_HOSTS`, and its `DATABASE_URL`, and put the app behind an HTTPS-terminating reverse proxy. Never commit `.env` or production credentials.

The included Docker Compose database is suitable for development, not as a substitute for a production backup, monitoring, and recovery plan.

The starter records center-scoped events for patient registration, order creation, sample collection, result entry, and result release. This is not a tamper-proof or compliance-certified audit system.

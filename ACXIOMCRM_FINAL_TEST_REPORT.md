# AcxiomCRM Verification Report

Date: 2026-11-03

## Automated checks

- `python manage.py check`: passed; no issues reported.
- `python manage.py makemigrations --check --dry-run`: passed; no model changes pending.
- `python manage.py test`: passed; 18 tests, 0 failures.

## Browser verification

A headless Chromium session exercised the application against a cloned copy of the existing SQLite database. Test accounts and browser-created records existed only in that clone. The original `db.sqlite3` was not used for browser mutations.

- 46 browser checks passed, 0 failed.
- Covered login/logout, dashboard charts and KPIs, customer CRUD/search/duplicate validation, lead creation/filter/conversion, opportunity stage changes, follow-up creation/completion, activity history, user management, reports and CSV download, audit logs, Manager and Sales Executive restrictions, direct URL access, mobile navigation, and responsive rendering at 1920x1080, 1366x768, 768x1024, and 390x844.
- No browser JavaScript page exceptions or horizontal overflow were observed.
- Expected HTTP 403/404 responses occurred during deliberate permission-denial checks. The browser reported `ERR_ABORTED` for the CSV request because the download completed and navigated the download flow.
- Browser credentials were temporary fixture accounts, not existing production accounts. Browser results and screenshots are in `browser_artifacts/`.

## Screenshots

- [Admin dashboard](browser_artifacts/admin-dashboard-desktop.png)
- [Desktop dashboard](browser_artifacts/dashboard-desktop.png)
- [Laptop dashboard](browser_artifacts/dashboard-laptop.png)
- [Tablet dashboard](browser_artifacts/dashboard-tablet.png)
- [Mobile dashboard](browser_artifacts/dashboard-mobile.png)
- [Customer detail](browser_artifacts/customer-detail.png)

## Limitations

- Browser tests ran locally in headless Chromium; no manual interactive browser testing was performed.
- Browser validation used a cloned existing database and temporary test accounts. It did not validate external production services or deployment hosting.
- `sales-performance.csv` is a generated sample export and is excluded from version control.

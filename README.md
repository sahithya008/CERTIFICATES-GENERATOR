# Student Certificate Generator System 🎓

A lightweight Flask web application that automates generation of student certificates (Bonafide, Course Completion, Fee details, Custodium, etc.) using Excel-based student data and on-the-fly PDF creation.

---

## Table of contents

- Overview
- Features
- Quick start
- Manual tests & verification
- Automated tests
- Managing student data
- Admin access
- Troubleshooting
- Contributing
- License & Maintainer

---

## Overview

This application streamlines certificate issuance for educational institutions. It validates student eligibility from a maintained Excel spreadsheet and generates PDF certificates using ReportLab. Admins can review and perform bulk downloads; all download events are logged to a SQLite database.

---

## Features

- Web UI for student requests and admin dashboard
- Eligibility checks based on student status
- PDF generation for individual or bulk certificates
- Upload support for payment proof images
- Audit logs stored in SQLite (`downloads.db`)
- Simple data source: `student_certificates.xlsx` (editable spreadsheet)

---

## Quick start (minimal)

Prerequisites: Python 3.10+, git

1. Clone the repository and enter the project folder:

   ```bash
   git clone <repo-url>
   cd CERTIFICATES-GENERATOR
   ```

2. Create and activate a virtual environment:

   Linux / macOS:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   Windows (PowerShell):
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. (Optional) Set admin credentials: in `app.py` set `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

5. Run the application:

   ```bash
   python app.py
   # Open http://localhost:5000/
   ```

---

## New in this fork — Feature 1 of 3 ✅

**Admin API — Programmatic student creation**

A concise, authenticated API endpoint has been added to this fork to allow administrators to add students directly to the project's canonical Excel data source (`student_certificates.xlsx`). This capability is intended to make onboarding, bulk provisioning, and scripted workflows easy without manual spreadsheet edits.

- **Endpoint:** `POST /admin/api/students` (JSON)
- **Authentication:** Admin session (via `/admin` login) or HTTP Basic Auth using `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
- **Required fields:** `HALLTICKET`, `NAME`, `STATUS` (one of `STUDYING`, `COMPLETED`, `PASSOUT`). Additional columns present in the spreadsheet can be supplied and will be preserved if present.

Example usage (Basic Auth):

```bash
curl -X POST -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"HALLTICKET":"HT2025EX","NAME":"Demo Student","STATUS":"STUDYING"}' \
  http://localhost:5000/admin/api/students
```

Response: `201 Created` with a JSON body `{ "success": true, "student": { ... } }` on success; errors return a JSON `error` message and an appropriate HTTP status.

---

### This fork roadmap (short)

- **Feature 1 (this PR):** Admin API — add student (programmatic) ✅
- **Planned Feature 2:** Admin UI for student management (create/edit rows from the dashboard)
- **Planned Feature 3:** CSV/Excel import endpoint for bulk student uploads

> Note: This repository is maintained in the fork and the above feature is the first official enhancement added here; the next two features will be added iteratively and documented in subsequent PRs.

---

## Manual tests & verification

- Home page loads at `/`.
- Check status for a hall ticket (replace `<HALLTICKET>`):

  ```bash
  curl -s http://localhost:5000/check_status/<HALLTICKET>
  ```

  Expected result: JSON with `status` (e.g., `STUDYING`, `COMPLETED`, `PASSOUT`, or `invalid`).

- Request a certificate via the UI:
  - Enter a valid hall ticket, select certificate(s), proceed to payment.
  - On `/payment`, upload a payment proof image and provide a transaction ID.
  - After submission, a PDF (single) or ZIP (multiple) should download.
  - Uploaded proofs are stored in `static/uploads` and logs are recorded in `downloads.db`.

- Admin functionality (after setting credentials):
  - Login at `/admin`, search download logs, perform bulk download, or clear logs by date.

### Admin API — Add student (programmatic)

A simple authenticated API is available to add a student row to `student_certificates.xlsx`.

Endpoint: `POST /admin/api/students`

- Authentication: Either an active admin session (log in via `/admin`) or HTTP Basic Auth using `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
- Payload (JSON): at minimum include `HALLTICKET`, `NAME`, and `STATUS` (one of `STUDYING`, `COMPLETED`, `PASSOUT`). Additional columns present in the spreadsheet will be preserved if provided.

Example (using basic auth):

```bash
curl -X POST -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"HALLTICKET":"HT2025EX","NAME":"Demo Student","STATUS":"STUDYING"}' \
  http://localhost:5000/admin/api/students
```

Response: `201 Created` with `{ "success": true, "student": { ... } }` on success. Errors return JSON with `error` and appropriate 4xx/5xx code.

---

## Automated tests

The repository supports Pytest-based tests. Example commands:

```bash
pip install pytest pytest-flask
pytest -q
```

Suggested test coverage:

- Unit tests for `parse_fee`, `is_cert_eligible`, and `create_certificate` behaviors
- Endpoint tests for `/check_status/<hallticket>`, `/payment` (form validation), and `/verify_payment` (file upload flow)

A minimal example test file can be added at `tests/test_basic.py` to validate key behaviors and endpoints.

---

## Managing student data

- Student data is kept in `student_certificates.xlsx`.
- Required columns (recommended): `HALLTICKET`, `NAME`, `STATUS` (`STUDYING` | `COMPLETED` | `PASSOUT`).
- To add a student: edit the spreadsheet directly and restart the application to reload data.

Optional helper script pattern (Python + pandas) can be added to automate insertion of rows.

---

## Admin access & configuration

- Admin credentials are configured in `app.py` using `ADMIN_USERNAME` and `ADMIN_PASSWORD` (plain values for local/dev use).
- For production, environment variables or a secrets manager is recommended.

---

## Troubleshooting

- Excel load errors: confirm `openpyxl` is installed and `student_certificates.xlsx` is present and well-formed.
- Database schema changes: delete `downloads.db` and restart the app to recreate tables.
- If the web form seems unresponsive: open browser devtools (Console and Network) to inspect form submission and view server logs for flash messages or exceptions.

---

## Contributing

1. Fork the repository and create a feature branch.
2. Open pull requests with clear descriptions and test coverage where appropriate.
3. Use GitHub issues to report bugs or request enhancements.

---

## License & Maintainer

- License: see `LICENSE` file in the repository (if present).
- Maintainer: project maintainer (for support or contributions, please open an issue on the repository).

---

*This README provides concise, third‑person documentation to set up, test, and contribute to the project.*

## 🔗 Repository

📎 **GitHub Repo:** [CERTIFICATES-GENERATOR](https://github.com/sahithya008/CERTIFICATES-GENERATOR)
⭐ *If you like this project, consider giving it a star!*

---

## ✅ Quick Testing & Quick Start

Follow these minimal steps to set up, run and test the app locally.

### 1) Create & activate virtual environment

- Linux/macOS:

  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

- Windows (PowerShell):

  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  # If blocked: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  ```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) (Optional) Set admin credentials

Open `app.py` and set **ADMIN_USERNAME** and **ADMIN_PASSWORD** (they are blank by default) so you can use the admin dashboard.

### 4) Run the app

```bash
python app.py
# Open http://localhost:5000/ in a browser
```

### 5) Manual smoke tests

- Home page loads at `/` ✅
- Check a hallticket status (replace `<HALLTICKET>`):
  ```bash
  curl -s http://localhost:5000/check_status/<HALLTICKET>
  ```
- Request a certificate via the web UI:
  - Enter a valid `HALLTICKET`, select one or more certificates and click **Proceed to Payment**
  - On `/payment` upload a small image (transaction proof) and a transaction id
  - Submit and confirm a PDF (single) or a ZIP (multiple) is downloaded
- Confirm upload saved under `static/uploads` and a log entry exists in `downloads.db`

### 6) Add a student (quick)

- Manually open `student_certificates.xlsx` and add a row with at least these columns:
  - `HALLTICKET`, `NAME`, `STATUS` (use `STUDYING` / `COMPLETED` / `PASSOUT`)
- Save the file and **restart** the app so it reloads the Excel data.

> Tip: Use the `curl /check_status/<HALLTICKET>` command above to verify the new entry.

### 7) Run automated tests (optional)

- Install test tools:

```bash
pip install pytest pytest-flask
```

- Example tests (create `tests/test_basic.py`):

```python
import io
from app import app, is_cert_eligible

def test_is_cert_eligible():
    assert is_cert_eligible("Bonafide", "STUDYING", "") is True
    assert is_cert_eligible("Course Completion", "STUDYING", "") is False

def test_check_status_endpoint():
    client = app.test_client()
    rv = client.get("/check_status/invalid_ticket")
    assert rv.status_code == 200
    assert b'invalid' in rv.data
```

- Run tests:

```bash
pytest -q
```

### 8) Troubleshooting

- If Excel fails to load: confirm `openpyxl` is installed and `student_certificates.xlsx` exists.
- If DB schema errors appear after modifying models: delete `downloads.db` and restart the app to recreate it.
- If the form appears to do nothing: open browser devtools (Console & Network) to verify the POST request to `/payment` and check server logs for flash messages.

---


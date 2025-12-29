from flask import Flask, flash, render_template, request, send_file, redirect, url_for, session, jsonify
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Indenter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from io import StringIO, BytesIO
from datetime import datetime, timezone, timedelta
import os
import csv
import uuid
import pandas as pd
import html
import zipfile
from flask_sqlalchemy import SQLAlchemy
import pytz

IST = pytz.timezone("Asia/Kolkata")

def clean_val(val):
    if pd.isna(val):
        return ""
    return str(val).replace("\n", " ").replace("\r", " ").strip()

def ist_now():
    return datetime.now(IST)

CSV_FILE = "student_audit_log.csv"

def write_audit_log(entry):
    """
    entry: dict with keys:
    ['Date','Time','Hall Ticket','Student Name',
    'Certificate','Transaction ID','Status','Reference']
    """
    os.makedirs(os.path.dirname(CSV_FILE) or ".", exist_ok=True)
    write_header = not os.path.isfile(CSV_FILE) or os.path.getsize(CSV_FILE) == 0

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'Date','Time','Hall Ticket','Student Name',
                'Certificate','Transaction ID','Status','Reference'],
            quoting=csv.QUOTE_ALL
        )
        if write_header:
            writer.writeheader()
        clean_entry = {k: clean_val(entry.get(k, "")) for k in writer.fieldnames}

       
        now = datetime.now()
        if not clean_entry['Date']:
            clean_entry['Date'] = now.strftime("%Y-%m-%d")
        if not clean_entry['Time']:
            clean_entry['Time'] = now.strftime("%H:%M:%S")

        writer.writerow(clean_entry)

app = Flask(__name__)
app.secret_key = "yoursecretkey"

def utc_to_ist(utc_dt):
    """Convert UTC datetime to IST (UTC+5:30)."""
    if not utc_dt:
        return ""
    return (utc_dt + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

# SQLAlchemy setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///downloads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Upload folder for payment proofs
app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

STUDENT_RECORDS_FILE = "logs/student_records.csv"
def save_student_record(student, hallticket, cert_type, purpose, transaction_id):
    file_exists = os.path.isfile(STUDENT_RECORDS_FILE)

    with open(STUDENT_RECORDS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "hallticket",
                "name",
                "status",
                "certificate_type",
                "transaction_id"

            ])
        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": ist_now().strftime("%d-%m-%Y %H:%M:%S"),
            "hallticket": clean_val(hallticket),
            "name":student["NAME"].values[0],
            "status": student["STATUS"].values[0],
            "certificate_type": clean_val(cert_type),
            "transaction_id": clean_val(transaction_id)
        })


# Excel setup
EXCEL_FILE = "student_certificates.xlsx"
students = pd.read_excel(EXCEL_FILE, engine="openpyxl")
students.columns = [c.strip() for c in students.columns]
students["HALLTICKET"] = students["HALLTICKET"].astype(str).str.strip().str.upper()

def parse_fee(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s.upper() in ("NULL", "NAN", ""):
        return None
    s2 = s.replace(",", "")
    try:
        if "." in s2:
            return float(s2)
        return int(s2)
    except Exception:
        return None

for col in ["TUITION FEE", "COLLEGE FEE", "NBA FEE", "JNTUH FEE", "HOSTEL FEE", "BUS FEE", "TOTAL"]:
    if col in students.columns:
        students[col] = students[col].apply(parse_fee)

# Audit logging

AUDIT_LOG_FILE = "logs/certificate_audit_log.csv"
os.makedirs("logs", exist_ok=True)

def append_audit_log(event_type, data):
    """
    Writes an append-only audit log row with separate date and time.
    """
    fieldnames = [
        "log_id",
        "date",
        "time",
        "hallticket",
        "name",
        "certificate",
        "transaction_id",
        "purpose",
        "status",
        "reference",
    ]
    
    file_exists = os.path.isfile(AUDIT_LOG_FILE)
    
    now = datetime.now(IST)
    date_str = now.strftime("%d-%m-%Y")
    time_str = now.strftime("%H:%M:%S")

    
    with open(AUDIT_LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists or os.path.getsize(AUDIT_LOG_FILE) == 0:
            writer.writeheader()
        
        row = {key: "" for key in fieldnames}

        row.update({
            "hallticket": data.get("hallticketno") or data.get("hall_ticket", ""),
            "name": data.get("name", ""),
            "certificate": data.get("certificate") or data.get("certificate_type", ""),
            "transaction_id": data.get("transaction_id", ""),
            "purpose": data.get("purpose", ""),
            "status": data.get("status"),
            "reference": data.get("reference", ""),
        })

        row["log_id"] = str(uuid.uuid4())
        row["date"] = date_str
        row["time"] = time_str
        
        writer.writerow(row)


# Temporary and Permanent CSV files
TEMP_CSV = "temp_editable.csv"
PERMANENT_CSV = "logs/permanent_edits.csv"

def create_temp_csv():
    """Create temporary CSV from current database data."""
    logs = CertificateDownload.query.order_by(CertificateDownload.downloaded_at.desc()).all()
    
    with open(TEMP_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "hallticket", "certificate_type", "transaction_id", "proof_filename", "downloaded_at"
        ])
        writer.writeheader()
        for log in logs:
            ist_time = log.downloaded_at.astimezone(IST) if log.downloaded_at else ""
            writer.writerow({
                "id": log.id,
                "hallticket": log.student_hallticket,
                "certificate_type": log.certificate_type,
                "transaction_id": log.transaction_id or "",
                "proof_filename": log.proof_filename or "",
                "downloaded_at": ist_time.strftime("%Y-%m-%d %H:%M:%S") if ist_time else ""
            })

def append_permanent_edit(edit_data):
    """Append an edit to the permanent CSV with timestamp."""
    os.makedirs(os.path.dirname(PERMANENT_CSV), exist_ok=True)
    file_exists = os.path.isfile(PERMANENT_CSV)
    
    with open(PERMANENT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "hallticket", "field_changed", "old_value", "new_value", "edited_by"
        ])
        if not file_exists:
            writer.writeheader()
        
        writer.writerow({
            "timestamp": ist_now().strftime("%Y-%m-%d %H:%M:%S"),
            "hallticket": edit_data.get("hallticket", ""),
            "field_changed": edit_data.get("field_changed", ""),
            "old_value": edit_data.get("old_value", ""),
            "new_value": edit_data.get("new_value", ""),
            "edited_by": edit_data.get("edited_by", "admin")
        })

def get_permanent_edits():
    """Get all permanent edits."""
    if not os.path.exists(PERMANENT_CSV):
        return []
    
    edits = []
    with open(PERMANENT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            edits.append(row)
    return edits


@app.route("/admin/export_certificates_csv")
def export_certificates_csv():
    # Download the permanent edits CSV
    if not os.path.exists(PERMANENT_CSV):
        flash("No permanent edit data available", "warning")
        return redirect(url_for("admin_dashboard"))

    return send_file(
        PERMANENT_CSV,
        as_attachment=True,
        download_name="permanent_edits.csv",
        mimetype="text/csv"
    )

@app.route("/admin/download_database")
def download_database():
    # Create and download the temporary CSV
    create_temp_csv()
    if not os.path.exists(TEMP_CSV):
        flash("No data available for download", "warning")
        return redirect(url_for("admin_dashboard"))

    return send_file(
        TEMP_CSV,
        as_attachment=True,
        download_name="editable_database.csv",
        mimetype="text/csv"
    )

@app.route("/admin/edit_data")
def edit_data():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    logs = CertificateDownload.query.order_by(CertificateDownload.downloaded_at.desc()).all()
    return render_template("edit_data.html", logs=logs)

@app.route("/admin/save_edits", methods=["POST"])
def save_edits():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Get form data
    ids = request.form.getlist("id")
    halltickets = request.form.getlist("hallticket")
    certificate_types = request.form.getlist("certificate_type")
    transaction_ids = request.form.getlist("transaction_id")
    proof_filenames = request.form.getlist("proof_filename")

    edits_count = 0
    for i, log_id in enumerate(ids):
        log = CertificateDownload.query.get(int(log_id))
        if log:
            original = {
                "hallticket": log.student_hallticket,
                "certificate_type": log.certificate_type,
                "transaction_id": log.transaction_id or "",
                "proof_filename": log.proof_filename or ""
            }
            new_values = {
                "hallticket": halltickets[i].strip(),
                "certificate_type": certificate_types[i].strip(),
                "transaction_id": transaction_ids[i].strip(),
                "proof_filename": proof_filenames[i].strip()
            }

            # Update database
            log.student_hallticket = new_values["hallticket"]
            log.certificate_type = new_values["certificate_type"]
            log.transaction_id = new_values["transaction_id"] or None
            log.proof_filename = new_values["proof_filename"] or None

            # Log changes
            for field in ["hallticket", "certificate_type", "transaction_id", "proof_filename"]:
                if original[field] != new_values[field]:
                    append_permanent_edit({
                        "hallticket": new_values["hallticket"],
                        "field_changed": field,
                        "old_value": original[field],
                        "new_value": new_values[field],
                        "edited_by": "admin"
                    })
                    edits_count += 1

    db.session.commit()
    flash(f"Edits saved: {edits_count} changes logged.", "success")
    return redirect(url_for("edit_data"))
    
# Database model
IST_OFFSET = timedelta(hours=5, minutes=30)

class CertificateDownload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_hallticket = db.Column(db.String(50), nullable=False)
    certificate_type = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    proof_filename = db.Column(db.String(200), nullable=True)
    downloaded_at = db.Column(db.DateTime, default=ist_now)

class CertificateAudit(db.Model):
    __tablename__ = "certificate_audit"

    id = db.Column(db.Integer, primary_key=True)
    hallticket = db.Column(db.String(50), nullable=False)
    certificate_type = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    proof_filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=ist_now)


# Database initialization
with app.app_context():
    db.create_all()

# Certificate eligibility
def is_cert_eligible(cert_type: str, status: str, purpose: str) -> bool:
    if status is None:
        return False
    s = str(status).strip().upper()
    cert = cert_type.strip()
    if s == "STUDYING":
        if cert in ("Bonafide", "Bonafide (scholarship purpose)", "Fee details for IT purpose", "Fee structure for bank loan"):
            return True
        if cert == "Custodium":
            return bool(str(purpose or "").strip())
        return False
    elif s in ("COMPLETED", "PASSOUT"):
        return cert in ("Bonafide", "Course Completion")
    else:
        return cert == "Bonafide"

# ------------------ Routes ------------------ #
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin/view_db")
def view_db():
    """View Temporary Database - Same data as dashboard"""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Define IST timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(timezone.utc).astimezone(ist)
    yesterday_ist = now_ist - timedelta(days=1)

    # Fetch logs from TEMPORARY DB (CertificateDownload)
    logs = CertificateDownload.query.order_by(CertificateDownload.downloaded_at.desc()).all()

    # Convert timestamps and mark new entries
    formatted_logs = []
    for log in logs:
        if log.downloaded_at:
            downloaded_ist = log.downloaded_at.astimezone(ist)
            is_new = downloaded_ist >= yesterday_ist
        else:
            downloaded_ist = None
            is_new = False

        formatted_logs.append({
            "id": log.id,
            "hallticket": log.student_hallticket,
            "certificate_type": log.certificate_type,
            "transaction_id": log.transaction_id or "",
            "proof_filename": log.proof_filename or "",
            "downloaded_at": downloaded_ist.strftime("%Y-%m-%d %H:%M:%S") if downloaded_ist else "",
            "is_new": is_new
        })

    return render_template("admin_db_view.html", logs=formatted_logs)

@app.route("/check_status/<hallticket>")
def check_status(hallticket):
    hallticket = str(hallticket).strip().upper()
    student = students.loc[students["HALLTICKET"] == hallticket]

    if student.empty:
        return jsonify({"status": "INVALID"})

    status = str(student["STATUS"].values[0]).strip().upper()
    return jsonify({"status": status})

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("❌ Invalid credentials", "danger")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin/view_audit")
def view_audit():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    audits = CertificateAudit.query.order_by(CertificateAudit.created_at.desc()).all()

    # Convert UTC timestamps to IST
    audit_list = []
    for a in audits:
        audit_list.append({
            "hallticket": a.hallticket,
            "certificate_type": a.certificate_type,
            "transaction_id": a.transaction_id,
            "proof_filename": a.proof_filename or "-",
            "created_at": utc_to_ist(a.created_at)
        })

    return render_template("admin_view_audit.html", audits=audit_list)


@app.route("/admin/download_audit_log")
def download_audit_log():
    """Download the CSV audit log file (separate from database)"""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    audit_file = AUDIT_LOG_FILE  # logs/certificate_audit_log.csv

    if not os.path.exists(audit_file):
        flash("❌ Audit log file not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    return send_file(
        audit_file,
        as_attachment=True,
        download_name="certificate_audit_log.csv",
        mimetype="text/csv"
    )



@app.route("/admin/download_all", methods=["POST"])
def download_all():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    cert_types = request.form.getlist("admin_cert_types")
    if not cert_types:
        flash("❌ Please select at least one certificate type.", "warning")
        return redirect(url_for("admin_dashboard"))

    if "all" in cert_types:
        cert_types = [
            "Bonafide",
            "Course Completion",
            "Custodium",
            "Fee details for IT purpose",
            "Fee structure for bank loan"
        ]

    generated_files = []

    for _, student_row in students.iterrows():
        hallticketno = str(student_row["HALLTICKET"]).strip()
        student_df = pd.DataFrame([student_row])
        status = str(student_row.get("STATUS", "")).strip().upper()

        for cert_type in cert_types:
            if not is_cert_eligible(cert_type, status, purpose="Admin Bulk Download"):
                continue

            buf = create_certificate(cert_type, student_df, hallticketno, purpose="Admin Bulk Download")
            if not buf:
                continue

            filename = f"{cert_type}_{hallticketno}.pdf"
            generated_files.append((filename, buf))

            # Append to logs
            append_audit_log("ADMIN_BULK_GENERATE", {
                "hall_ticket": hallticketno,
                "name": student_row.get("NAME"),
                "certificate_type": cert_type,
                "purpose": "ADMIN BULK DOWNLOAD",
                "transaction_id": "ADMIN",
                "purpose": "ADMIN BULK DOWNLOAD",
                "status": "ADMIN",
                "reference": "BULK_ZIP"
            })

            # Log in database
            db.session.add(CertificateDownload(
                student_hallticket=hallticketno,
                certificate_type=cert_type,
                transaction_id="ADMIN",
                proof_filename=""
            ))
            db.session.add(CertificateAudit(
                hallticket=hallticketno,
                certificate_type=cert_type,
                transaction_id="ADMIN",
                proof_filename=""
            ))

    if not generated_files:
        flash("❌ No eligible certificates were generated.", "danger")
        return redirect(url_for("admin_dashboard"))

    db.session.commit()

    # Log additions to permanent edits
    for hallticketno, cert_type in generated_files:
        append_permanent_edit({
            "hallticket": hallticketno,
            "field_changed": "certificate_added",
            "old_value": "",
            "new_value": cert_type,
            "edited_by": "system"
        })

    # Create ZIP
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, buf in generated_files:
            buf.seek(0)
            zf.writestr(filename, buf.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name="bulk_certificates.zip", mimetype="application/zip")

@app.route("/admin/export_permanent_db")
def export_permanent_db():
    """Export the permanent database (CertificateAudit) as CSV"""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['ID', 'Hall Ticket', 'Certificate Type', 'Transaction ID', 'Proof Filename', 'Created At (IST)'])
    
    # Fetch from permanent database
    ist = timezone(timedelta(hours=5, minutes=30))
    audits = CertificateAudit.query.order_by(CertificateAudit.created_at.desc()).all()
    
    for audit in audits:
        created_ist = audit.created_at.astimezone(ist) if audit.created_at else None
        writer.writerow([
            audit.id,
            audit.hallticket,
            audit.certificate_type,
            audit.transaction_id or "",
            audit.proof_filename or "",
            created_ist.strftime("%Y-%m-%d %H:%M:%S") if created_ist else ""
        ])
    
    output.seek(0)
    
    # Convert to BytesIO for send_file
    byte_output = BytesIO()
    byte_output.write(output.getvalue().encode('utf-8'))
    byte_output.seek(0)
    
    return send_file(
        byte_output,
        as_attachment=True,
        download_name="permanent_certificate_records.csv",
        mimetype="text/csv"
    )

@app.route("/admin/search", methods=["POST"])
def admin_search():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    query = request.form.get("search_hallticket", "").strip()

    # Define IST timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(timezone.utc).astimezone(ist)
    yesterday_ist = now_ist - timedelta(days=1)

    # Search in TEMPORARY database (CertificateDownload)
    logs = CertificateDownload.query.filter(
        CertificateDownload.student_hallticket.contains(query)
    ).order_by(CertificateDownload.downloaded_at.desc()).all()

    # Convert timestamps and mark new entries
    formatted_logs = []
    for log in logs:
        if log.downloaded_at:
            downloaded_ist = log.downloaded_at.astimezone(ist)
            is_new = downloaded_ist >= yesterday_ist
        else:
            downloaded_ist = None
            is_new = False

        formatted_logs.append({
            "id": log.id,
            "hallticket": log.student_hallticket,
            "certificate_type": log.certificate_type,
            "transaction_id": log.transaction_id or "",
            "proof_filename": log.proof_filename or "",
            "downloaded_at": downloaded_ist.strftime("%Y-%m-%d %H:%M:%S") if downloaded_ist else "",
            "is_new": is_new
        })

    return render_template(
        "admin_dashboard.html",
        logs=formatted_logs,
        is_search=True,
        search_query=query
    )




@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Define IST timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(timezone.utc).astimezone(ist)
    yesterday_ist = now_ist - timedelta(days=1)

    # Fetch logs from TEMPORARY database (CertificateDownload)
    logs = CertificateDownload.query.order_by(CertificateDownload.downloaded_at.desc()).all()

    # Convert timestamps and mark new entries
    formatted_logs = []
    for log in logs:
        if log.downloaded_at:
            downloaded_ist = log.downloaded_at.astimezone(ist)
            is_new = downloaded_ist >= yesterday_ist
        else:
            downloaded_ist = None
            is_new = False

        formatted_logs.append({
            "id": log.id,
            "hallticket": log.student_hallticket,
            "certificate_type": log.certificate_type,
            "transaction_id": log.transaction_id or "",
            "proof_filename": log.proof_filename or "",
            "downloaded_at": downloaded_ist.strftime("%Y-%m-%d %H:%M:%S") if downloaded_ist else "",
            "is_new": is_new
        })

    return render_template(
        "admin_dashboard.html",
        logs=formatted_logs,
        is_search=False,
        search_query=""
    )



@app.route("/admin/update_tem", methods=["POST"])
def update_tem():
    flash(
        "⚠️ This action is not configured. If you have a form using url_for('update_tem'), update it to point to an existing admin endpoint.",
        "warning",
    )
    return redirect(url_for("admin_dashboard"))



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/payment", methods=["GET", "POST"])
def payment_page():
    if request.method == "GET":
        cert_types = session.get("cert_types", [])
        hallticketno = session.get("hallticketno")
        purpose = session.get("purpose", "")
        if not hallticketno or not cert_types:
            return redirect(url_for("home"))
        student = students.loc[students["HALLTICKET"] == hallticketno]
        if student.empty:
            flash("❌ Invalid Hall Ticket Number", "danger")
            return redirect(url_for("home"))
        amount_per_cert = 100
        total_amount = len(cert_types) * amount_per_cert
        return render_template("payment.html", cert_types=cert_types, hallticketno=hallticketno, purpose=purpose, total_amount=total_amount)

    # POST request
    cert_types = request.form.getlist("cert_types")
    hallticketno = request.form.get("hallticketno", "").strip().upper()
    purpose = request.form.get("purpose", "").strip()
    if not hallticketno or not cert_types or ("Custodium" in cert_types and not purpose):
        flash("❌ Please fill required fields.", "warning")
        return redirect(url_for("home"))
    student = students.loc[students["HALLTICKET"] == hallticketno]
    if student.empty:
        flash("❌ Invalid Hall Ticket Number", "danger")
        return redirect(url_for("home"))
    status = str(student["STATUS"].values[0]).strip().upper()
    eligible_certs = [cert for cert in cert_types if is_cert_eligible(cert, status, purpose)]
    if not eligible_certs:
        flash("❌ None of the selected certificates are eligible for this student.", "danger")
        return redirect(url_for("home"))

    session["cert_types"] = eligible_certs
    session["hallticketno"] = hallticketno
    session["purpose"] = purpose
    return redirect(url_for("payment_page"))

@app.route("/verify_payment", methods=["POST"])
def verify_payment():
    cert_types = session.get("cert_types", [])
    hallticketno = session.get("hallticketno")
    purpose = session.get("purpose", "")
    
    if not hallticketno or not cert_types:
        flash("❌ Session expired or no certificates selected.", "danger")
        return redirect(url_for("home"))

    transaction_id = request.form.get("transaction_id", "").strip()
    proof_file = request.files.get("payment_proof")
    
    if not transaction_id or not proof_file or proof_file.filename == "":
        flash("❌ Please upload both Transaction ID and Payment Proof.", "warning")
        return redirect(url_for("payment_page"))

    # Save proof file
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    ext = os.path.splitext(proof_file.filename)[1].lower()
    safe_filename = f"{hallticketno}_{transaction_id}"
    safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in ("-", "_"))
    filename = safe_filename + (ext if ext else ".png")
    proof_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    student = students.loc[students["HALLTICKET"] == hallticketno]
    student = students.loc[students["HALLTICKET"] == hallticketno]

    # Generate certificates
    generated = []
    for cert_type in cert_types:
        buf = create_certificate(cert_type, student, hallticketno, purpose)
        if buf:
            generated.append((cert_type, buf))

    if not generated:
        flash("❌ No eligible certificates were generated.", "danger")
        return redirect(url_for("home"))

    save_student_record(student, hallticketno, ", ".join(cert_types), purpose, transaction_id)

    # Log in both CertificateDownload and permanent CertificateAudit
    for cert_type, _ in generated:
        db.session.add(CertificateDownload(
            student_hallticket=hallticketno,
            certificate_type=cert_type,
            transaction_id=transaction_id,
            proof_filename=filename
        ))
        db.session.add(CertificateAudit(
            hallticket=hallticketno,
            certificate_type=cert_type,
            transaction_id=transaction_id,
            proof_filename=filename
        ))
        append_audit_log("CERTIFICATE_GENERATED", {
            "hall_ticket": hallticketno,
            "name": student["NAME"].values[0],
            "certificate_type": cert_type,
            "transaction_id": transaction_id,
            "purpose": purpose,
            "status": student["STATUS"].values[0],
            "reference": f"{cert_type}_{hallticketno}.pdf"
        })

    db.session.commit()

    # Log additions to permanent edits
    for cert_type, _ in generated:
        append_permanent_edit({
            "hallticket": hallticketno,
            "field_changed": "certificate_added",
            "old_value": "",
            "new_value": cert_type,
            "edited_by": "system"
        })

    # Clear session
    session.pop("cert_types", None)
    session.pop("hallticketno", None)
    session.pop("purpose", None)

    # Send files
    if len(generated) == 1:
        cert_type, buffer = generated[0]
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"{cert_type}_{hallticketno}.pdf", mimetype="application/pdf")
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for cert_type, buffer in generated:
            buffer.seek(0)
            zf.writestr(f"{cert_type}_{hallticketno}.pdf", buffer.getvalue())
    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name=f"{hallticketno}_certificates.zip", mimetype="application/zip")

@app.route("/admin/permanent-records")
def permanent_records():
    """View Permanent Database - NEVER gets cleared"""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Define IST timezone
    ist = timezone(timedelta(hours=5, minutes=30))

    # Fetch from PERMANENT database (CertificateAudit)
    audits = CertificateAudit.query.order_by(CertificateAudit.created_at.desc()).all()

    # Convert timestamps
    audit_list = []
    for audit in audits:
        if audit.created_at:
            created_ist = audit.created_at.astimezone(ist)
        else:
            created_ist = None

        audit_list.append({
            "id": audit.id,
            "hallticket": audit.hallticket,
            "certificate_type": audit.certificate_type,
            "transaction_id": audit.transaction_id or "-",
            "proof_filename": audit.proof_filename or "-",
            "created_at": created_ist.strftime("%Y-%m-%d %H:%M:%S") if created_ist else ""
        })

    return render_template("permanent_records.html", logs=audit_list)

@app.route("/admin/clear_logs_by_date", methods=["POST"])
def clear_logs_by_date():
    """Clear ONLY temporary logs - Permanent database stays untouched"""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    cutoff_date_str = request.form.get("cutoff_date")

    if cutoff_date_str:
        try:
            # Parse the cutoff date and make it timezone-aware (IST)
            cutoff_naive = datetime.strptime(cutoff_date_str, "%Y-%m-%d")
            ist = timezone(timedelta(hours=5, minutes=30))
            cutoff = cutoff_naive.replace(tzinfo=ist)
            
            # Delete records from TEMPORARY database only
            deleted = CertificateDownload.query.filter(
                CertificateDownload.downloaded_at < cutoff
            ).delete()
            
            db.session.commit()
            
            # Log this action to permanent edits CSV
            append_permanent_edit({
                "hallticket": "SYSTEM",
                "field_changed": "bulk_delete",
                "old_value": f"{deleted} records",
                "new_value": f"Deleted before {cutoff_date_str}",
                "edited_by": "admin"
            })
            
            flash(f"✅ {deleted} temporary logs cleared successfully! Permanent records are safe.", "success")
        except Exception as e:
            db.session.rollback()
            print("Error clearing logs:", e)
            flash(f"❌ Error clearing logs: {str(e)}", "danger")
    else:
        flash("❌ Please provide a cutoff date.", "warning")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/upload_edited_csv", methods=["POST"])
def upload_edited_csv():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    file = request.files.get("edited_csv")
    if not file or file.filename == "":
        flash("No file uploaded", "warning")
        return redirect(url_for("admin_dashboard"))

    # Read uploaded CSV
    uploaded_data = []
    try:
        content = file.read().decode("utf-8")
        reader = csv.DictReader(StringIO(content))
        for row in reader:
            uploaded_data.append(row)
    except Exception as e:
        flash(f"Error reading CSV: {str(e)}", "danger")
        return redirect(url_for("admin_dashboard"))

    # Get current DB data
    logs = CertificateDownload.query.all()
    db_data = {log.id: {
        "hallticket": log.student_hallticket,
        "certificate_type": log.certificate_type,
        "transaction_id": log.transaction_id or "",
        "proof_filename": log.proof_filename or "",
        "downloaded_at": log.downloaded_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if log.downloaded_at else ""
    } for log in logs}

    # Compare and log edits
    edits_count = 0
    for row in uploaded_data:
        row_id = int(row.get("id", 0))
        if row_id in db_data:
            original = db_data[row_id]
            for field in ["hallticket", "certificate_type", "transaction_id", "proof_filename"]:
                new_value = row.get(field, "").strip()
                old_value = original.get(field, "").strip()
                if new_value != old_value:
                    append_permanent_edit({
                        "hallticket": row.get("hallticket", ""),
                        "field_changed": field,
                        "old_value": old_value,
                        "new_value": new_value,
                        "edited_by": "admin"
                    })
                    edits_count += 1

    flash(f"Edits processed: {edits_count} changes logged to permanent records.", "success")
    return redirect(url_for("admin_dashboard"))


# ----------------- Certificate Creation ----------------- #
def create_certificate(cert_type, student, hallticketno, purpose=""):
    """
    Generate PDF for a student.
    Original PDF content preserved as in your code.
    """
    def safe_get(col):
        return student[col].values[0] if col in student.columns else ""

    # Extract student info
    name = safe_get("NAME")
    parent_name = safe_get("PARENT NAME")
    branch = safe_get("BRANCH")
    year = safe_get("YEAR")
    academic_year = safe_get("ACADEMIC YEAR")
    join_year = safe_get("JOINING YEAR")
    pass_year = safe_get("PASSOUT YEAR")
    status = str(safe_get("STATUS")).strip().lower()
    admin_no = safe_get("ADMIN NO")
    hsno = safe_get("R/O") if "R/O" in student.columns else ""
    mandal = safe_get("MANDAL")
    village = safe_get("VILLAGE")
    distance = safe_get("DISTANCE")
    district = safe_get("DISTRICT")
    caste = safe_get("CASTE")
    sub_caste = safe_get("SUB CASTE") if "SUB CASTE" in student.columns else ""
    tuition_fee = safe_get("TUITION FEE")
    college_fee = safe_get("COLLEGE FEE")
    NBA_fee = safe_get("NBA FEE")
    JNTUH_fee = safe_get("JNTUH FEE")
    bus_fee = safe_get("BUS FEE")
    hostel_fee = safe_get("HOSTEL FEE")
    total = safe_get("TOTAL")

    # Eligibility check
    if cert_type == "Course Completion" and status != "completed":
        return None
    if cert_type == "Custodium" and (not purpose.strip() or status != "studying"):
        return None
    if cert_type in ("Fee details for IT purpose", "Fee structure for bank loan") and status != "studying":
        return None

    buffer = BytesIO()
    page_margin = 1 * cm
    logo_height = 5 * cm
    extra_gap = 1 * cm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=page_margin,
        rightMargin=page_margin,
        topMargin=page_margin + logo_height + extra_gap,
        bottomMargin=page_margin + 2 * cm
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", alignment=1, fontSize=20, spaceAfter=20))
    styles.add(ParagraphStyle(name="Justify", alignment=4, fontSize=12, leading=18))
    heading_style_custom = ParagraphStyle(name="HeadingCustom", fontName="Helvetica-Bold", fontSize=14, alignment=1, spaceAfter=20, leading=16)
    normal_style_custom = ParagraphStyle(name="NormalCustom", fontName="Helvetica", fontSize=11, alignment=4, spaceAfter=12, leading=15)

    flow = []

    # ---- PDF content code remains unchanged ---- #
    # Certificate contents
    if cert_type == "Bonafide":
        flow.append(Paragraph("<b>BONAFIDE / CONDUCT CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"Was a bonafide student of this college during the academic year <b>{html.escape(str(academic_year))}</b>, "
            f"and studied <b>{html.escape(str(year))}</b>, "
            f"<b>B.Tech {html.escape(str(branch))}</b>, "
            f"His/Her Roll No. <b>{html.escape(str(hallticketno))}</b>, "
            f"& Admin. No <b>{html.escape(str(admin_no))}</b>, "
            f"His/Her Conduct is <b>Satisfactory</b>, "
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 20))

        flow.append(PageBreak())
        
        flow.append(Paragraph("<b>BONAFIDE / CONDUCT CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 20))

        
    elif cert_type == "Bonafide (scholarship purpose)":
        flow.append(Paragraph("<b>BONAFIDE CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"bearing Hall Ticket No. <b>{html.escape(str(hallticketno))}</b>, "
            f"studying (year & branch) <b>{html.escape(str(year))} {html.escape(str(branch))}</b> "
            f"during the academic year <b>{html.escape(str(academic_year))}</b>. "
            f"R/O <b>{html.escape(str(hsno))}</b> "
            f"belonging to village <b>{html.escape(str(village))}</b> "
            f"located at a distance of <b>{html.escape(str(distance))}</b> KM from the college, "
            f"Mandal <b>{html.escape(str(mandal))}</b> "
            f"District <b>{html.escape(str(district))}</b>. "
            f"She belongs to <b>{html.escape(str(caste))}</b> caste "
            f"<b>{html.escape(str(sub_caste))}</b> Sub Caste.<br/><br/>"
            "The tuition fee may remitted to the College Bank Account Number 30957508604 "
            "Bank State Bank Of India, Hanamkonda Branch."
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6*cm))

# Define style for signature block
        signature_style = ParagraphStyle(
            name="SignatureStyle",
            fontName="Helvetica",
            fontSize=11,
            leading=14,       # line spacing to prevent descenders from being cut
            textColor=colors.black,
            alignment=2       # 2 = right-aligned
    )

# Combine all lines into one string with <br/> for line breaks
        signature_text = (
            "Signature & Name of Principal<br/>"
            "of the Educational Institution<br/>"
            "(with seal)<br/>"
            "Tel.No.: 0870 - 2818302"
    )

# Indent from left so text is not touching right border (adjust left=12*cm as needed)
        flow.append(Indenter(left=10*cm))
        flow.append(Paragraph(signature_text, signature_style))
        flow.append(Indenter(left=-10*cm))
        flow.append(Spacer(1, 24))
        flow.append(PageBreak())
        flow.append(Paragraph("<b>BONAFIDE CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6*cm))

# Define style for signature block
        signature_style = ParagraphStyle(
            name="SignatureStyle",
            fontName="Helvetica",
            fontSize=11,
            leading=14,       # line spacing to prevent descenders from being cut
            textColor=colors.black,
            alignment=2       # 2 = right-aligned
    )

# Combine all lines into one string with <br/> for line breaks
        signature_text = (
            "Signature & Name of Principal<br/>"
            "of the Educational Institution<br/>"
            "(with seal)<br/>"
            "Tel.No.: 0870 - 2818302"
    )

# Indent from left so text is not touching right border (adjust left=12*cm as needed)
        flow.append(Indenter(left=10*cm))
        flow.append(Paragraph(signature_text, signature_style))
        flow.append(Indenter(left=-10*cm))

        flow.append(Spacer(1, 24))

    elif cert_type == "Course Completion":
        flow.append(Paragraph("<b>COURSE COMPLETION CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"bearing Hall Ticket No. <b>{html.escape(str(hallticketno))}</b>, "
            "was a bonafide student of our college. "
            f"She pursued her <b>BTECH</b> in <b>{html.escape(str(branch))}</b> "
            f"during the academic year <b>{html.escape(str(join_year))}</b> - <b>{html.escape(str(pass_year))}</b>."
            "<br/><br/>She has successfully completed the four-year engineering course."
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 24))
        flow.append(PageBreak())
        flow.append(Paragraph("<b>COURSE COMPLETION CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 24))

    elif cert_type == "Custodium":
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"is a bonafide student of our College studying B.Tech "
            f"<b>{html.escape(str(branch))}</b> <b>{html.escape(str(year))}</b> "
            f"bearing Roll No. <b>{html.escape(str(hallticketno))}</b> "
            f"during the academic year <b>{html.escape(str(academic_year))}</b>, "
            "and her original certificates i.e.,<b> SSC, Inter and Study Certificates of Tenth and Inter</b> are with us.<br/><br/>"
            f"This certificate is issued to enable her to apply for the <b>{html.escape(str(purpose))}</b>."
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 24))
        flow.append(PageBreak())
        
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 24))

    elif cert_type == "Fee details for IT purpose":
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 12))
        text = (
            "This is to certify that Ms.<b>" + html.escape(str(name)) + "</b>, "
            "D/o <b>" + html.escape(str(parent_name)) + "</b>, "
            "is a bonafide student of this Institution studying <b>B.Tech</b> "
            "<b>" + html.escape(str(branch)) + "</b> "
            "<b>" + html.escape(str(year)) + "</b> "
            "bearing <b>Hall Ticket No.</b> <b>" + html.escape(str(hallticketno)) + "</b> "
            "during the academic year <b>" + html.escape(str(academic_year)) + "</b>. "
            "<br/><br/>DETAILS OF FEE PAID BY THIS STUDENT ARE GIVEN BELOW:" 
        )
        flow.append(Paragraph(text, normal_style_custom))
        flow.append(Spacer(1, 12))
        fee_data = [
            ["S.NO.","Particular", str(year) + " " + str(academic_year)],
            ["1.","Tuition Fee", str(tuition_fee) if tuition_fee is not None else ""],
            ["2.","College Fee", str(college_fee) if college_fee is not None else ""],
            ["3.","NBA Fee", str(NBA_fee) if NBA_fee is not None else ""],
            [" ","TOTAL", str(total) if total is not None else ""]
        ]
        col_count = len(fee_data[0])
        col_widths = [doc.width / col_count] * col_count
        table = Table(fee_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        flow.append(table)
        flow.append(Spacer(1, 40))
        flow.append(Paragraph("This certificate is issued for IT returns.", styles["Justify"]))
        flow.append(Spacer(1, 2 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 40))
        flow.append(PageBreak())
        
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))
        table = Table(fee_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        flow.append(table)
        flow.append(Spacer(1, 40))
        flow.append(Paragraph("This certificate is issued for IT returns.", styles["Justify"]))
        flow.append(Spacer(1, 2 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
    )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 40))
        
    elif cert_type == "Fee structure for bank loan":
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 12))
        text = (
            "This is to certify that Ms.<b>" + html.escape(str(name)) + "</b>, "
            "D/o <b>" + html.escape(str(parent_name)) + "</b>, "
            "is a bonafide student of our College studying B.Tech "
            "<b>" + html.escape(str(year)) + "</b> "
            "<b>" + html.escape(str(branch)) + "</b> "
            "bearing Hall Ticket No. <b>" + html.escape(str(hallticketno)) + "</b> "
            "during the academic year    <b>" + html.escape(str(academic_year)) + "</b>. "
            "<br/><br/>DETAILS OF FEE PARTICULARS PAYABLE BY THIS STUDENT ARE GIVEN BELOW:" 
        )
        flow.append(Paragraph(text, normal_style_custom))
        flow.append(Spacer(1, 12))
        fee_data = [
            ["S.No","Particular", "I YEAR","II YEAR","III YEAR","IV YEAR"],
            ["1.","Tuition Fee", str(tuition_fee) if tuition_fee is not None else "", str(tuition_fee) if tuition_fee is not None else "", str(tuition_fee) if tuition_fee is not None else "", str(tuition_fee) if tuition_fee is not None else ""],
            ["2.","College Fee", str(college_fee) if college_fee is not None else "", str(college_fee) if college_fee is not None else "", str(college_fee) if college_fee is not None else "", str(college_fee) if college_fee is not None else ""],
            ["3.","NBA Fee", str(NBA_fee) if NBA_fee is not None else "", str(NBA_fee) if NBA_fee is not None else "", str(NBA_fee) if NBA_fee is not None else "", str(NBA_fee) if NBA_fee is not None else ""],
            ["4.","JNTUH Fee", str(JNTUH_fee) if JNTUH_fee is not None else "", str(JNTUH_fee) if JNTUH_fee is not None else "", str(JNTUH_fee) if JNTUH_fee is not None else "", str(JNTUH_fee) if JNTUH_fee is not None else ""],
            ["5.","BUS Fee", str(bus_fee) if bus_fee is not None else "", str(bus_fee) if bus_fee is not None else "", str(bus_fee) if bus_fee is not None else "", str(bus_fee) if bus_fee is not None else ""],
            ["6.","Hostel Fee", str(hostel_fee) if hostel_fee is not None else "", str(hostel_fee) if hostel_fee is not None else "", str(hostel_fee) if hostel_fee is not None else "", str(hostel_fee) if hostel_fee is not None else ""],
            [" ","TOTAL", str(total) if total is not None else "", str(total) if total is not None else "", str(total) if total is not None else "", str(total) if total is not None else ""]
        ]

        col_count = len(fee_data[0])
        col_widths = [doc.width / col_count] * col_count
        table = Table(fee_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        flow.append(table)
        flow.append(Spacer(1,15))
        flow.append(Paragraph("<b>Laptop Required</b>", styles["Justify"]))
        flow.append(Paragraph(
            "<b>Our College Fees Bank Details:</b><br/>"
            "Account holder Name: Principal SRITW<br/>"
            "Name of the Bank & Branch: STATE BANK OF INDIA, Hasanparthy<br/>"
            "Account No: 62303929482<br/>"
            "Branch IFSC Code: SBIN0020155<br/>"
            "<b>Our Hostel Fees Bank Details:</b><br/>"
            "Account holder Name: SR Engineering College<br/>"
            "Name of the Bank & Branch: UNION BANK, Hasanparthy<br/>"
            "Account No: 122411011001142<br/>"
            "Branch IFSC Code: UBIN0819123",
            styles["Justify"]
        ))


        flow.append(Spacer(1, 0.6 * cm))  # 2 cm gap below content
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
        )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        flow.append(Spacer(1, 12))
        
        flow.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 12))
        table = Table(fee_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        flow.append(table)
        flow.append(Spacer(1,15))
        flow.append(Paragraph("<b>Laptop Required</b>", styles["Justify"]))
        flow.append(Paragraph(
            "<b>Our College Fees Bank Details:</b><br/>"
            "Account holder Name: Principal SRITW<br/>"
            "Name of the Bank & Branch: STATE BANK OF INDIA, Hasanparthy<br/>"
            "Account No: 62303929482<br/>"
            "Branch IFSC Code: SBIN0020155<br/>"
            "<b>Our Hostel Fees Bank Details:</b><br/>"
            "Account holder Name: SR Engineering College<br/>"
            "Name of the Bank & Branch: UNION BANK, Hasanparthy<br/>"
            "Account No: 122411011001142<br/>"
            "Branch IFSC Code: UBIN0819123",
            styles["Justify"]
        ))
        flow.append(Spacer(1,0.5))
        principal_style = ParagraphStyle(
            name="PrincipalStyle",
            fontName="Helvetica-Bold",
            fontSize=12,       # Increase size (adjust as needed)
            textColor=colors.black,
            alignment=2        # 2 = RIGHT
        )

# Table for right-aligned "Principal"
        principal_table = Table(
            [[Paragraph("PRINCIPAL", principal_style)]],
            colWidths=[5 * cm],  # adjust width if needed
            hAlign='RIGHT'
        )
        principal_table.setStyle(TableStyle([
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * cm),  # 3 cm gap from page edge
        ]))
        flow.append(principal_table)
        

    else:
        flow.append(Paragraph("Invalid certificate type selected!", styles["Justify"]))
        flow.append(Spacer(1, 24))


    # Build document
    def draw_first_page(canvas, doc):
        width, height = A4
        margin = 1 * cm
        canvas.saveState()
        # Border and Original Label
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2 * margin, height - 2 * margin)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.red)
        text_x = width - margin - 3 * cm
        text_y = height - margin - 1.2 * cm
        canvas.rect(text_x - 0.3 * cm, text_y - 0.2 * cm, 2.6 * cm, 0.8 * cm)
        canvas.drawString(text_x, text_y, "ORIGINAL")
        if os.path.exists("logo.png"):
            canvas.drawImage("logo.png", margin + (width - 2*margin - 8*cm)/2, height - margin - logo_height - 10, width=8*cm, height=5*cm, preserveAspectRatio=True, mask='auto')
            today = datetime.now().strftime("%d-%m-%Y")
            canvas.setFont("Helvetica-Bold", 11)
            canvas.setFillColor(colors.black)
            date_y = height - margin - logo_height - 19
            canvas.drawRightString(width - margin - 1*cm, date_y, f"Date: {today}")
        canvas.restoreState()

    def draw_later_pages(canvas, doc):
        width, height = A4
        margin = 1 * cm
        canvas.saveState()
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2*margin, height - 2*margin)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.red)
        text_x = width - margin - 3*cm
        text_y = height - margin - 1.2*cm
        canvas.rect(text_x - 0.3*cm, text_y - 0.2*cm, 2.9*cm, 0.8*cm)
        canvas.drawString(text_x, text_y, "DUPLICATE")
        if os.path.exists("logo.png"):
            canvas.drawImage("logo.png", margin + (width - 2*margin - 8*cm)/2, height - margin - logo_height - 10, width=8*cm, height=5*cm, preserveAspectRatio=True, mask='auto')
            today = datetime.now().strftime("%d-%m-%Y")
            canvas.setFont("Helvetica-Bold", 11)
            canvas.setFillColor(colors.black)
            date_y = height - margin - logo_height - 19
            canvas.drawRightString(width - margin - 1*cm, date_y, f"Date: {today}")
        canvas.restoreState()

    doc.build(flow, onFirstPage=draw_first_page, onLaterPages=draw_later_pages)
    buffer.seek(0)
    return buffer

# ----------------- Run App ----------------- #
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

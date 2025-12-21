from flask import Flask, flash, render_template, request, send_file, redirect, url_for, session, jsonify
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Indenter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from io import BytesIO
import datetime
import os
import pandas as pd
import html
import zipfile
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "yoursecretkey"

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

# Excel setup
EXCEL_FILE = "student_certificates.xlsx"
students = pd.read_excel(EXCEL_FILE, engine="openpyxl")
students.columns = [c.strip() for c in students.columns]

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

for col in ["TUITION FEE", "COLLEGE FEE", "NBA FEE", "JNTUH FEE", "HOSTEL FEE","BUS FEE", "TOTAL"]:
    if col in students.columns:
        students[col] = students[col].apply(parse_fee)

# Database model
class CertificateDownload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_hallticket = db.Column(db.String(50), nullable=False)
    certificate_type = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    proof_filename = db.Column(db.String(200), nullable=True)
    downloaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# Database initialization with migration
with app.app_context():
    try:
        db.create_all()
        CertificateDownload.query.first()
        print("Database schema is up to date!")
    except Exception as e:
        print(f"Database migration needed: {e}")
        print("Recreating database with new schema...")
        db.drop_all()
        db.create_all()
        print("Database migration completed successfully!")

def is_cert_eligible(cert_type: str, status: str, purpose: str) -> bool:
    if status is None:
        return False
    s = str(status).strip().upper()
    cert = cert_type.strip()
    if s == "STUDYING":
        if cert == "Bonafide":
            return True
        if cert == "Bonafide (scholarship purpose)":
            return True
        if cert == "Custodium":
            return bool(str(purpose or "").strip())
        if cert in ("Fee details for IT purpose", "Fee structure for bank loan"):
            return True
        if cert == "Course Completion":
            return False
    elif s == "COMPLETED" or s == "PASSOUT":
        if cert in ("Bonafide", "Course Completion"):
            return True
        return False
    else:
        return cert == "Bonafide"


@app.route("/admin/search", methods=["GET", "POST"])
def admin_search():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    logs = []
    query = ""
    if request.method == "POST":
        query = request.form["search_hallticket"].strip()
        if query:
            logs = CertificateDownload.query.filter(
                CertificateDownload.student_hallticket.like(f"%{query}%")
            ).order_by(CertificateDownload.downloaded_at.desc()).all()
    return render_template("admin_dashboard.html", logs=logs, search_query=query, is_search=True)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/check_status/<hallticket>")
def check_status(hallticket):
    hallticket = str(hallticket).strip()
    student = students.loc[students["HALLTICKET"] == hallticket]
    if student.empty:
        return jsonify({"status": "invalid"})
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
        else:
            flash("❌ Invalid credentials", "danger")
            return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    logs = CertificateDownload.query.order_by(CertificateDownload.downloaded_at.desc()).all()
    return render_template("admin_dashboard.html", logs=logs)

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
            flash("❌ Hall Ticket number not found!", "danger")
            return redirect(url_for("home"))
        amount_per_cert = 100
        total_amount = len(cert_types) * amount_per_cert
        return render_template("payment.html", cert_types=cert_types, hallticketno=hallticketno, purpose=purpose, total_amount=total_amount)

    cert_types = request.form.getlist("cert_types")
    hallticketno = request.form.get("hallticketno", "").strip()
    purpose = request.form.get("purpose", "").strip()

    if not hallticketno:
        flash("❌ Please enter Hall Ticket number.", "warning")
        return redirect(url_for("home"))
    if not cert_types:
        flash("❌ Please select at least one certificate.", "warning")
        return redirect(url_for("home"))
    if "Custodium" in cert_types and not purpose:
        flash("❌ Purpose is required for Custodium certificate.", "warning")
        return redirect(url_for("home"))
    
    student = students.loc[students["HALLTICKET"] == hallticketno]
    if student.empty:
        flash("❌ Hall Ticket number not found!", "danger")
        return redirect(url_for("home"))
    
    status = str(student["STATUS"].values[0]).strip().upper()
    eligible_certs = []
    for cert in cert_types:
        if is_cert_eligible(cert, status, purpose):
            eligible_certs.append(cert)
    
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
        flash("❌ Session expired or no certificates selected. Please re-start the process.", "danger")
        return redirect(url_for("home"))

    transaction_id = request.form.get("transaction_id", "").strip()
    proof_file = request.files.get("payment_proof")

    if not transaction_id or not proof_file or proof_file.filename == "":
        flash("❌ Please upload both Transaction ID and Payment Proof.", "warning")
        return redirect(url_for("payment_page"))

    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        ext = os.path.splitext(proof_file.filename)[1].lower()
        safe_filename = f"{hallticketno}_{transaction_id}"
        safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in ("-", "_"))
        filename = safe_filename + (ext if ext else ".png")
        proof_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        proof_file.save(proof_path)
    except Exception as e:
        flash(f"❌ Error saving file: {str(e)}", "danger")
        return redirect(url_for("payment_page"))

    student = students.loc[students["HALLTICKET"] == hallticketno]
    if student.empty:
        flash("❌ Hall Ticket number not found!", "danger")
        return redirect(url_for("home"))
    
    generated = []
    for cert_type in cert_types:
        status = str(student["STATUS"].values[0]).strip().upper()
        if not is_cert_eligible(cert_type, status, purpose):
            continue
        buf = create_certificate(cert_type, student, hallticketno, purpose)
        if buf:
            generated.append((cert_type, buf))
    
    if not generated:
        flash("❌ No eligible certificates were generated.", "danger")
        return redirect(url_for("home"))

    for cert_type, _ in generated:
        new_log = CertificateDownload(
            student_hallticket=hallticketno,
            certificate_type=cert_type,
            transaction_id=transaction_id,
            proof_filename=filename
        )
        db.session.add(new_log)
    db.session.commit()

    session.pop("cert_types", None)
    session.pop("hallticketno", None)
    session.pop("purpose", None)

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

# ADMIN BULK DOWNLOAD
@app.route("/download_all", methods=["POST"])
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
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for _, student_row in students.iterrows():
            hallticketno = student_row["HALLTICKET"]
            student_df = pd.DataFrame([student_row])
            for cert_type in cert_types:
                buf = create_certificate(cert_type, student_df, hallticketno, purpose="Admin Bulk Download")
                if buf:
                    filename = f"{cert_type}_{hallticketno}.pdf"
                    zf.writestr(filename, buf.getvalue())
                    new_log = CertificateDownload(
                        student_hallticket=hallticketno, 
                        certificate_type=cert_type, 
                        transaction_id="ADMIN", 
                        proof_filename=""
                    )
                    db.session.add(new_log)
        db.session.commit()
    
    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name="bulk_certificates.zip", mimetype="application/zip")

@app.route("/admin/clear_logs_by_date", methods=["POST"])
def clear_logs_by_date():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    
    cutoff_date_str = request.form.get("cutoff_date")
    if cutoff_date_str:
        try:
            cutoff = datetime.datetime.strptime(cutoff_date_str, "%Y-%m-%d")
            deleted = CertificateDownload.query.filter(CertificateDownload.downloaded_at < cutoff).delete()
            db.session.commit()
            flash(f"✅ {deleted} logs cleared successfully!", "success")
        except Exception as e:
            print("Error clearing logs:", e)
            flash("❌ Error clearing logs.", "danger")
    return redirect(url_for("admin_dashboard"))


def _check_admin_auth():
    """Return True if the request is authenticated as admin via session or basic-auth."""
    # Session-based authentication (from admin login)
    if session.get("admin"):
        return True
    # HTTP Basic Auth fallback
    auth = request.authorization
    if auth and auth.username == ADMIN_USERNAME and auth.password == ADMIN_PASSWORD:
        return True
    return False


@app.route('/admin/api/students', methods=['POST'])
def admin_api_add_student():
    """Add a student row to the Excel data source.

    Authentication: session admin or HTTP Basic auth matching ADMIN_USERNAME / ADMIN_PASSWORD.

    Expected JSON payload (application/json):
      {
        "HALLTICKET": "string",
        "NAME": "string",
        "STATUS": "STUDYING" | "COMPLETED" | "PASSOUT",
        ... optional other columns ...
      }

    Returns JSON {"success": True, "student": {...}} on 201 or error message with 4xx code.
    """
    if not _check_admin_auth():
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(force=True, silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"error": "invalid JSON payload"}), 400

    required = ["HALLTICKET", "NAME", "STATUS"]
    missing = [r for r in required if not payload.get(r)]
    if missing:
        return jsonify({"error": f"missing required fields: {', '.join(missing)}"}), 400

    hall = str(payload.get("HALLTICKET")).strip()
    status = str(payload.get("STATUS")).strip().upper()
    if status not in ("STUDYING", "COMPLETED", "PASSOUT"):
        return jsonify({"error": "invalid STATUS. Use STUDYING, COMPLETED, or PASSOUT"}), 400

    # Use global students variable and prevent duplicate hallticket
    global students
    if hall in students["HALLTICKET"].astype(str).values:
        return jsonify({"error": "HALLTICKET already exists"}), 400

    # Append row to Excel file
    try:
        df = pd.read_excel(EXCEL_FILE, engine="openpyxl")
    except Exception as e:
        return jsonify({"error": f"failed to read Excel: {e}"}), 500

    new_row = {k: payload.get(k, "") for k in df.columns}
    # Ensure mandatory fields are set even if columns missing
    new_row.update({"HALLTICKET": hall, "NAME": payload.get("NAME", ""), "STATUS": status})

    try:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(EXCEL_FILE, index=False, engine="openpyxl")
    except Exception as e:
        return jsonify({"error": f"failed to write to Excel: {e}"}), 500

    # Reload in-memory students DataFrame
    try:
        students = pd.read_excel(EXCEL_FILE, engine="openpyxl")
        students.columns = [c.strip() for c in students.columns]
    except Exception:
        # If reload fails, we still added the row to disk. Log and continue.
        print("Warning: failed to reload students DataFrame after adding student")

    return jsonify({"success": True, "student": {"HALLTICKET": hall, "NAME": payload.get("NAME", ""), "STATUS": status}}), 201


def create_certificate(cert_type, student, hallticketno, purpose=""):
    def safe_get(col):
        return student[col].values[0] if col in student.columns else ""

    name = safe_get("NAME")
    branch = safe_get("BRANCH")
    join_year = safe_get("JOINING YEAR")
    pass_year = safe_get("PASSOUT YEAR")
    parent_name = safe_get("PARENT NAME")
    status = str(safe_get("STATUS")).strip().lower()
    academic_year = safe_get("ACADEMIC YEAR")
    tuition_fee = safe_get("TUITION FEE") if "TUITION FEE" in student.columns else None
    college_fee = safe_get("COLLEGE FEE") if "COLLEGE FEE" in student.columns else None
    NBA_fee = safe_get("NBA FEE") if "NBA FEE" in student.columns else None
    JNTUH_fee = safe_get("JNTUH FEE") if "JNTUH FEE" in student.columns else None
    bus_fee = safe_get("BUS FEE") if "BUS FEE" in student.columns else None
    hostel_fee = safe_get("HOSTEL FEE") if "HOSTEL FEE" in student.columns else None
    total = safe_get("TOTAL") if "TOTAL" in student.columns else None
    year = safe_get("YEAR")
    hsno = safe_get("R/O") if "R/O" in student.columns else ""
    mandal = safe_get("MANDAL")
    village = safe_get("VILLAGE")
    distance = safe_get("DISTANCE")
    district = safe_get("DISTRICT")
    caste = safe_get("CASTE")
    sub_caste = safe_get("SUB CASTE") if "SUB CASTE" in student.columns else ""
    admin_no = safe_get("ADMIN NO")
    
    if cert_type == "Course Completion" and status != "completed":
        return None
    if cert_type == "Custodium":
        if not purpose.strip():
            return None
        if status != "studying":
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
    heading_style_custom = ParagraphStyle(
        name="HeadingCustom",
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=1,
        spaceAfter=20,
        leading=16
    )
    normal_style_custom = ParagraphStyle(
        name="NormalCustom",
        fontName="Helvetica",
        fontSize=11,
        alignment=4,
        spaceAfter=12,
        leading=15
    )

    flow = []

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
        def add_principal(flow):
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
        flow.append(Spacer(1,15))
        flow.append(PageBreak())
        
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
        add_principal(flow)

    else:
        flow.append(Paragraph("Invalid certificate type selected!", styles["Justify"]))
        flow.append(Spacer(1, 24))

    def draw_first_page(canvas, doc):
        width, height = A4
        margin = 1 * cm
        canvas.saveState()

    # Border
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    # ORIGINAL text box - top right corner
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.red)
        text_x = width - margin - 3 * cm
        text_y = height - margin - 1.2 * cm
        canvas.rect(text_x - 0.3 * cm, text_y - 0.2 * cm, 2.6 * cm, 0.8 * cm)
        canvas.drawString(text_x, text_y, "ORIGINAL")

    # Logo (center top)
        if os.path.exists("logo.png"):
            logo_width = 8 * cm
            logo_height = 5 * cm
            logo_x = margin + (width - 2 * margin - logo_width) / 2
            logo_y = height - margin - logo_height - 10
            canvas.drawImage(
                "logo.png",
                logo_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask='auto'
            )

        # Date below logo (1 line gap)
            today = datetime.datetime.now().strftime("%d-%m-%Y")
            canvas.setFont("Helvetica-Bold", 11)
            canvas.setFillColor(colors.black)
            date_y = logo_y - 9  # 1 line gap below logo
            canvas.drawRightString(width - margin - 1 * cm, date_y, f"Date: {today}")
        canvas.restoreState()


    def draw_later_pages(canvas, doc):
        width, height = A4
        margin = 1 * cm
        canvas.saveState()

    # Border
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    # DUPLICATE text box - top right corner
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.red)
        text_x = width - margin - 3 * cm
        text_y = height - margin - 1.2 * cm
        canvas.rect(text_x - 0.3 * cm, text_y - 0.2 * cm, 2.9 * cm, 0.8 * cm)
        canvas.drawString(text_x, text_y, "DUPLICATE")

    # Logo
        if os.path.exists("logo.png"):
            logo_width = 8 * cm
            logo_height = 5 * cm
            logo_x = margin + (width - 2 * margin - logo_width) / 2
            logo_y = height - margin - logo_height - 10
            canvas.drawImage(
                "logo.png",
                logo_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask='auto'
            )

        # Date below logo
            today = datetime.datetime.now().strftime("%d-%m-%Y")
            canvas.setFont("Helvetica-Bold", 11)
            canvas.setFillColor(colors.black)
            date_y = logo_y - 9
            canvas.drawRightString(width - margin - 1 * cm, date_y, f"Date: {today}")    
        canvas.restoreState()


# Build document
    doc.build(flow, onFirstPage=draw_first_page, onLaterPages=draw_later_pages)

    buffer.seek(0)
    return buffer


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

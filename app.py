from flask import Flask, flash, render_template, request, send_file, redirect, url_for, session
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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

# ------------------ Flask setup ------------------
app = Flask(__name__)
app.secret_key = "yoursecretkey"

# SQLAlchemy setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///downloads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------ Admin credentials ------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ------------------ PDF styles ------------------
heading_style = ParagraphStyle(
    name="Heading",
    fontName="Helvetica-Bold",
    fontSize=14,
    alignment=1,
    spaceAfter=20,
    leading=16
)

normal_style = ParagraphStyle(
    name="Normal",
    fontName="Helvetica",
    fontSize=11,
    alignment=4,
    spaceAfter=12,
    leading=15
)

# ------------------ Excel setup ------------------
EXCEL_FILE = "student_certificates.xlsx"
students = pd.read_excel(EXCEL_FILE, engine="openpyxl")

# ------------------ Database model ------------------
class CertificateDownload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_hallticket = db.Column(db.String(50), nullable=False)
    certificate_type = db.Column(db.String(100), nullable=False)
    downloaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

with app.app_context():
    db.create_all()

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("index.html")

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

# ------------------ Certificate generation ------------------
def create_certificate(cert_type, student, hallticketno, purpose=""):
    # Extract student info
    name = student["NAME"].values[0]
    branch = student["BRANCH"].values[0]
    course = student["COURSE"].values[0]
    join_year = student["JOINING YEAR"].values[0]
    pass_year = student["PASSOUT YEAR"].values[0]
    parent_name = student["PARENT NAME"].values[0]
    status = str(student["STATUS"].values[0]).strip().lower()
    academic_year = student["ACADEMIC YEAR"].values[0]
    tuition_fee = student["TUITION FEE"].values[0]
    college_fee = student["COLLEGE FEE"].values[0]
    NBA_fee = student["NBA FEE"].values[0]
    JNTUH_fee = student["JNTUH FEE"].values[0]
    hostel_fee = student["HOSTEL FEE"].values[0]
    total = student["TOTAL"].values[0]
    year = student["YEAR"].values[0]
    hsno = student["R/O"].values[0]
    mandal = student["MANDAL"].values[0]
    village = student["VILLAGE"].values[0]
    distance = student["DISTANCE"].values[0]
    district = student["DISTRICT"].values[0]
    caste = student["CASTE"].values[0]
    sub_caste = student["SUB CASTE"].values[0]

    buffer = BytesIO()
    page_margin = 1*cm
    logo_height = 5*cm
    extra_gap = 1*cm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=page_margin,
        rightMargin=page_margin,
        topMargin=page_margin + logo_height + extra_gap,
        bottomMargin=page_margin + 2*cm
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

    # --- Certificate contents ---
    if cert_type == "Bonafide":
        flow.append(Paragraph("<b>[ORIGINAL] BONAFIDE CERTIFICATE</b>", styles["CenterTitle"]))
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
        flow.append(Spacer(1, 24))  # 2 lines
        flow.append(PageBreak())

        flow.append(Paragraph("<b>[DUPLICATE] BONAFIDE CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))

    elif cert_type == "Course Completion":
        if status != "completed":
            return None
        flow.append(Paragraph("<b>[ORIGINAL] COURSE COMPLETION CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"bearing Hall Ticket No. <b>{html.escape(str(hallticketno))}</b>, "
            "was a bonafide student of our college. "
            f"She pursued her <b>{html.escape(str(course))}</b> in <b>{html.escape(str(branch))}</b> "
            f"during the academic year <b>{html.escape(str(join_year))}</b> - <b>{html.escape(str(pass_year))}</b>."
            "<br/><br/>She has successfully completed the four-year engineering course."
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))
        flow.append(PageBreak())

        flow.append(Paragraph("<b>[DUPLICATE] COURSE COMPLETION CERTIFICATE</b>", styles["CenterTitle"]))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))

    elif cert_type == "Custodium":
        if not purpose.strip():
            return None
        if status != "studying":
            return None
        flow.append(Paragraph("<b>[ORIGINAL] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        text = (
            f"This is to certify that Ms.<b>{html.escape(str(name))}</b>, "
            f"D/o <b>{html.escape(str(parent_name))}</b>, "
            f"is a bonafide student of our College studying B.Tech "
            f"<b>{html.escape(str(branch))}</b> <b>{html.escape(str(year))}</b> "
            f"bearing Roll No. <b>{html.escape(str(hallticketno))}</b> "
            f"during the academic year <b>{html.escape(str(academic_year))}</b>, "
            "and her original certificates i.e., SSC, Inter and Study Certificates of Tenth and Inter are with us.<br/><br/>"
            f"This certificate is issued to enable her to apply for the <b>{html.escape(str(purpose))}</b>."
        )
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))
        flow.append(PageBreak())

        flow.append(Paragraph("<b>[DUPLICATE] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))

    elif cert_type == "Fee details for IT purpose":
        if status != "studying":
            return None
        flow.append(Paragraph("<b>[ORIGINAL] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 12))
        text = (
            "This is to certify that Ms.<b>" + html.escape(str(name)) + "</b>, "
            "D/o <b>" + html.escape(str(parent_name)) + "</b>, "
            "is a bonafide student of our College studying B.Tech "
            "<b>" + html.escape(str(year)) + "</b> "
            "<b>" + html.escape(str(branch)) + "</b> "
            "bearing Hall Ticket No. <b>" + html.escape(str(hallticketno)) + "</b> "
            "during the academic year <b>" + html.escape(str(academic_year)) + "</b>. "
            "<br/><br/>DETAILS OF FEE PAID BY THIS STUDENT ARE GIVEN BELOW:" 
        )
        flow.append(Paragraph(text, normal_style_custom))
        flow.append(Spacer(1, 12))

        fee_data = [
            ["S.NO.","Particular", str(year) + str(academic_year)],
            ["1.","Tuition Fee", str(tuition_fee)],
            ["2.","College Fee", str(college_fee)],
            ["3.","NBA Fee", str(NBA_fee)],
            ["4.","Total", str(total)]
        ]
        table = Table(fee_data, colWidths=[200, 150])
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
        flow.append(Spacer(1, 40))
        flow.append(PageBreak())

        flow.append(Paragraph("<b>[DUPLICATE] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))
        table = Table(fee_data, colWidths=[200, 150])
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
        flow.append(Spacer(1, 40))
        
    elif cert_type == "Fee structure for bank loan":
        if status != "studying":
            return None
        flow.append(Paragraph("<b>[ORIGINAL] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
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
            ["S.No","Particular", "I YEAR" ,"II YEAR" ,"III YEAR" ,"IV YEAR" ],
            ["1.","Tuition Fee", str(tuition_fee), str(tuition_fee), str(tuition_fee), str(tuition_fee)],
            ["2.","Hostel Fee", str(hostel_fee),str(hostel_fee),str(hostel_fee),str(hostel_fee)],
            ["3.","College Fee", str(college_fee),str(college_fee),str(college_fee),str(college_fee)],
            ["4.","NBA Fee", str(NBA_fee),str(NBA_fee),str(NBA_fee),str(NBA_fee)],
            ["5.","JNTUH Fee", str(JNTUH_fee),str(JNTUH_fee),str(JNTUH_fee),str(JNTUH_fee)],
            ["6.","Total", str(total),str(total),str(total),str(total)]
        ]
        table = Table(fee_data, colWidths=[100, 70])
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
        flow.append(Paragraph("This certificate is issued with reference to her application to apply for EDUCATIONAL LOAN PURPOSE.", styles["Justify"]))
        flow.append(Spacer(1,15))
        flow.append(PageBreak())

        flow.append(Paragraph("<b>[DUPLICATE] TO WHOMSOEVER IT MAY CONCERN</b>", heading_style_custom))
        flow.append(Spacer(1, 20))
        flow.append(Paragraph(text, styles["Justify"]))
        flow.append(Spacer(1, 24))
        table = Table(fee_data, colWidths=[100, 70])
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
        flow.append(Paragraph("This certificate is issued with reference to her application to apply for EDUCATIONAL LOAN PURPOSE.", styles["Justify"]))
        flow.append(Spacer(1,15))

    else:
        flow.append(Paragraph("Invalid certificate type selected!", styles["Justify"]))
        flow.append(Spacer(1, 24)) 

    # --- Footer & logo ---
    def draw_footer(canvas, doc):
        width, height = A4
        margin = 1*cm
        today = datetime.date.today().strftime("%d-%m-%Y")
        canvas.saveState()

        # Footer
        canvas.setFont("Helvetica", 10)
        canvas.drawString(margin + 1*cm, margin + 2.5*cm, "Place: Ananthasagar")
        canvas.drawString(margin + 1*cm, margin + 2*cm, f"Date: {today}")
        signature_texts = [
            "Signature & Name of Principal",
            "of the Educational Institution",
            "(with seal)",
            "Tel.No.: 0870 - 2818302"
        ]
        for i, text in enumerate(signature_texts):
            canvas.drawRightString(width - margin - 1*cm, margin + 2.5*cm - i*12, text)

        # border
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2*margin, height - 2*margin)

        # logo
        if os.path.exists("logo.png"):
            logo_width = 8*cm
            logo_height = 5*cm
            canvas.drawImage(
                "logo.png",
                margin + (width - 2*margin - logo_width)/2,
                height - margin - logo_height - 10,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask='auto'
            )
        canvas.restoreState()

    doc.build(flow, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)
    return buffer

# ------------------ PDF routes ------------------
@app.route("/generate", methods=["POST"])
def generate_pdf():
    hallticketno = request.form["hallticketno"].strip()
    cert_types = request.form.getlist("cert_types")
    purpose = request.form.get("purpose", "")

    student = students.loc[students["HALLTICKET"] == hallticketno]
    if student.empty:
        return f"❌ Student with Hall Ticket {hallticketno} not found!"

    if not cert_types:
        return "❌ Please select at least one certificate."

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for cert_type in cert_types:
            buffer = create_certificate(cert_type, student, hallticketno, purpose)
            if buffer:
                zf.writestr(f"{cert_type}_{hallticketno}.pdf", buffer.getvalue())
                # log download
                new_log = CertificateDownload(student_hallticket=hallticketno, certificate_type=cert_type)
                db.session.add(new_log)
        db.session.commit()

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{hallticketno}_certificates.zip",
        mimetype="application/zip"
    )

# ------------------ Admin bulk download ------------------
@app.route("/download_all", methods=["POST"])
def download_all():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    cert_types = request.form.getlist("admin_cert_types")
    if not cert_types:
        return "❌ Please select at least one certificate type."
    if "all" in cert_types:
        cert_types = [
            "Bonafide",
            "Course Completion",
            "Custodium",
            "Fee details for IT purpose",
            "Fee structure for bank loan",
        ]

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for _, student in students.iterrows():
            hallticketno = student["HALLTICKET"]
            student_df = pd.DataFrame([student])
            for cert_type in cert_types:
                buffer = create_certificate(cert_type, student_df, hallticketno, purpose="Admin Bulk Download")
                if buffer:
                    filename = f"{cert_type}_{hallticketno}.pdf"
                    zf.writestr(filename, buffer.getvalue())
                    new_log = CertificateDownload(student_hallticket=hallticketno, certificate_type=cert_type)
                    db.session.add(new_log)
        db.session.commit()

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name="bulk_certificates.zip", mimetype="application/zip")

# ------------------ Clear logs ------------------
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

# ------------------ Run server ------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

from flask import Flask, render_template, request, send_file
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from io import BytesIO
import datetime
import os

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate_pdf():
    # Get form data
    name = request.form["name"]
    parent_name = request.form["parent_name"]
    hallticketno = request.form["hallticketno"]
    year_branch = request.form["year & branch"]
    academic_year = request.form["academic_year"]

    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", alignment=1, fontSize=20, spaceAfter=20))
    styles.add(ParagraphStyle(name="Justify", alignment=4, fontSize=12, leading=18))

    story = []

    # Logo
    if os.path.exists("logo.png"):
        story.append(Image("logo.png", width=300, height=100))
        story.append(Spacer(1, 20))

    # Title
    story.append(Paragraph("BONAFIDE CERTIFICATE", styles["CenterTitle"]))
    story.append(Spacer(1, 20))

    # Main text (continuous paragraph)
    text = f"""
    This is to certify that Ms.<b>{name}</b>, D/o <b>{parent_name}</b>, 
    bearing Hall Ticket No. <b>{hallticketno}</b>, is a bonafide student of 
    <b>{year_branch}</b> in Sumathi Reddy Institution Of Technology For Women,
    Ananthasagar during the academic year <b>{academic_year}</b>.
    """
    story.append(Paragraph(text, styles["Justify"]))
    story.append(Spacer(1, 40))

    # Place & Date
    today = datetime.date.today().strftime("%d-%m-%Y")
    story.append(Paragraph("Place: Ananthasagar", styles["Normal"]))
    story.append(Paragraph(f"Date: {today}", styles["Normal"]))
    story.append(Spacer(1, 40))

    # Signature block(right aligned)
    right_style = ParagraphStyle(name="RightAlign", parent=styles["Normal"], alignment=2)
    story.append(Paragraph("Signature & Name of Principal", right_style))
    story.append(Paragraph("of the Educational Institution", right_style))
    story.append(Paragraph("(with seal)", right_style))
    story.append(Paragraph("Tel.No.: 0870 - 2818302", right_style))

    # PDF border
    def draw_border(canvas, doc):
        width, height = A4
        margin = 40  # adjust for padding
        canvas.setLineWidth(2)
        canvas.rect(margin, margin, width - 2*margin, height - 2*margin)

    #Build pdf
    doc.build(story, onFirstPage=draw_border, onLaterPages=draw_border)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="bonafide_certificate.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
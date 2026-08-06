from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ASSET_DIR = Path(__file__).resolve().parent / "assets"


def _fit_font(text: str, font: str, preferred: int, max_width: float, minimum: int = 14) -> int:
    size = preferred
    while size > minimum and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _certificate_text(value: object) -> str:
    """Keep generated PDFs compatible with common Windows PDF viewers."""
    return (
        str(value or "")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2011", "-")
        .replace("\u2022", "|")
    )


def build_certificate_pdf(
    name: str,
    project: str,
    duration: str,
    certificate_no: str,
    issued_date: str,
    verification_url: str = "",
    college: str = "Individual Internship",
    technology: str = "",
    track: str = "",
    starts_on: str = "",
    completed_on: str = "",
) -> bytes:
    name = _certificate_text(name)
    project = _certificate_text(project)
    duration = _certificate_text(duration)
    certificate_no = _certificate_text(certificate_no)
    issued_date = _certificate_text(issued_date)
    college = _certificate_text(college)
    technology = _certificate_text(technology)
    track = _certificate_text(track)
    starts_on = _certificate_text(starts_on)
    completed_on = _certificate_text(completed_on)

    buffer = BytesIO()
    width, height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(width, height), pageCompression=1)
    navy = HexColor("#223A69")
    navy_dark = HexColor("#10284E")
    gold = HexColor("#C99822")
    gold_light = HexColor("#F1D77A")
    muted = HexColor("#304568")

    pdf.setFillColor(HexColor("#FFFEFB"))
    pdf.rect(0, 0, width, height, stroke=0, fill=1)

    # Formal navy-and-gold corner treatment based on the approved reference.
    pdf.setFillColor(navy_dark)
    path = pdf.beginPath()
    path.moveTo(width - 220, height)
    path.lineTo(width, height)
    path.lineTo(width, height - 160)
    path.close()
    pdf.drawPath(path, stroke=0, fill=1)
    path = pdf.beginPath()
    path.moveTo(0, 0)
    path.lineTo(230, 0)
    path.lineTo(0, 150)
    path.close()
    pdf.drawPath(path, stroke=0, fill=1)
    pdf.setStrokeColor(gold)
    pdf.setLineWidth(4)
    pdf.line(width - 232, height, width, height - 168)
    pdf.line(0, 160, 245, 0)

    pdf.setStrokeColor(gold)
    pdf.setLineWidth(2.2)
    pdf.rect(36, 31, width - 72, height - 62, stroke=1, fill=0)
    pdf.setStrokeColor(gold_light)
    pdf.setLineWidth(0.7)
    pdf.rect(44, 39, width - 88, height - 78, stroke=1, fill=0)

    # Use the approved GAINT globe mark as the only centre watermark.
    watermark_path = ASSET_DIR / "gaint-logo-watermark.png"
    if watermark_path.exists():
        watermark_width = 350
        watermark_height = 345
        pdf.drawImage(
            ImageReader(watermark_path),
            (width - watermark_width) / 2,
            160,
            width=watermark_width,
            height=watermark_height,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )

    seal_path = ASSET_DIR / "gold-seal.png"
    if seal_path.exists():
        pdf.drawImage(
            ImageReader(seal_path),
            width - 117,
            height - 137,
            width=74,
            height=94,
            preserveAspectRatio=True,
            mask="auto",
        )

    pdf.setFillColor(navy_dark)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, height - 57, f"CERTIFICATE ID: {certificate_no}")
    pdf.setFillColor(navy)
    pdf.setFont("Times-Roman", 62)
    pdf.drawCentredString(width / 2, height - 126, "CERTIFICATE")
    pdf.setFont("Times-Italic", 30)
    pdf.drawCentredString(width / 2, height - 165, "of Internship")

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(width / 2, height - 202, "We Present This Certificate To")
    pdf.setFillColor(gold)
    name_size = _fit_font(name, "Times-BoldItalic", 37, width - 260, 22)
    pdf.setFont("Times-BoldItalic", name_size)
    pdf.drawCentredString(width / 2, height - 249, name)
    pdf.setStrokeColor(HexColor("#9BA5B5"))
    pdf.setLineWidth(1)
    pdf.line(170, height - 263, width - 170, height - 263)

    technology_value = technology.replace("_", " ").strip() or "Not specified"
    track_value = track.replace("_", " ").strip() or "Not specified"
    program_value = duration.replace("_", " ").strip() or "Not specified"

    start_value = starts_on or "Start date recorded"
    end_value = completed_on or issued_date
    statement = (
        "THIS IS TO CERTIFY THAT THE PROJECT ENTITLED "
        f'<b>"{escape(project.upper())}"</b> IS A BONA FIDE WORK CARRIED OUT BY '
        f"<b>{escape(name.upper())}</b> AT <b>GAINT CLOUT TECHNOLOGIES PVT LTD</b>, "
        f"HYDERABAD, DURING THE PERIOD FROM <b>{escape(start_value.upper())}</b> "
        f"TO <b>{escape(end_value.upper())}</b>."
    )
    paragraph_width = width - 190
    paragraph_size = 10.7
    while True:
        paragraph_style = ParagraphStyle(
            "certificate_statement",
            fontName="Helvetica",
            fontSize=paragraph_size,
            leading=paragraph_size + 4.3,
            textColor=navy,
            alignment=TA_CENTER,
            allowWidows=0,
            allowOrphans=0,
        )
        paragraph = Paragraph(statement, paragraph_style)
        _, paragraph_height = paragraph.wrap(paragraph_width, 74)
        if paragraph_height <= 61 or paragraph_size <= 8:
            break
        paragraph_size -= 0.5
    paragraph.drawOn(pdf, 95, height - 294 - paragraph_height)

    # One aligned line replaces the old crowded technology metadata card.
    details = f"{program_value.upper()}  |  {technology_value.upper()}  |  {track_value.upper()}"
    details_size = _fit_font(details, "Helvetica-Bold", 9, width - 310, 7)
    detail_y = height - 370
    pdf.setFillColor(HexColor("#FBF5E3"))
    pdf.roundRect(190, detail_y - 25, width - 380, 40, 7, stroke=0, fill=1)
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", details_size)
    pdf.drawCentredString(width / 2, detail_y + 1, details)
    affiliation = college if college and college != "Individual Internship" else "Individual Internship"
    affiliation_size = _fit_font(affiliation, "Helvetica", 8, width - 360, 7)
    pdf.setFont("Helvetica", affiliation_size)
    pdf.setFillColor(muted)
    pdf.drawCentredString(width / 2, detail_y - 15, affiliation)

    def draw_signature(
        asset_name: str,
        centre_x: float,
        image_width: float,
        image_height: float,
        person: str,
        title: str,
    ) -> None:
        asset_path = ASSET_DIR / asset_name
        if asset_path.exists():
            pdf.drawImage(
                ImageReader(asset_path),
                centre_x - image_width / 2,
                77,
                width=image_width,
                height=image_height,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        pdf.setStrokeColor(HexColor("#A8B0BD"))
        pdf.setLineWidth(0.7)
        pdf.line(centre_x - 80, 78, centre_x + 80, 78)
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawCentredString(centre_x, 60, person)
        pdf.setFont("Helvetica", 9)
        pdf.drawCentredString(centre_x, 45, title)

    draw_signature("prasad-k-signature.png", 190, 130, 75, "PRASAD K", "CHAIRMAN")
    draw_signature("srinivasa-rao-k-signature.png", width - 205, 150, 55, "SRINIVASA RAO K", "CEO")

    verify_value = verification_url or certificate_no
    qr = QrCodeWidget(verify_value)
    bounds = qr.getBounds()
    drawing = Drawing(
        58,
        58,
        transform=[58 / (bounds[2] - bounds[0]), 0, 0, 58 / (bounds[3] - bounds[1]), 0, 0],
    )
    drawing.add(qr)
    renderPDF.draw(drawing, pdf, width - 106, 45)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(width - 110, 42, "Scan to verify")
    pdf.setFillColor(white)
    pdf.drawString(48, 43, f"Issued: {issued_date}")

    pdf.setTitle(f"GAINT Internship Certificate - {name}")
    pdf.setAuthor("GAINT Clout Technologies Pvt. Ltd.")
    pdf.save()
    return buffer.getvalue()


def build_evaluation_report_pdf(student: dict, assignment: dict, attendance: dict) -> bytes:
    """Create a source-free college report from stored Judge0 results and hashes."""
    buffer = BytesIO()
    width, height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    navy, blue, muted = HexColor("#071B33"), HexColor("#2563EB"), HexColor("#53677D")

    def header() -> float:
        pdf.setFillColor(navy)
        pdf.rect(0, height - 70, width, 70, stroke=0, fill=1)
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(42, height - 38, "GAINT INTERNS HUB")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(42, height - 54, "Verified task evaluation report - source code is not stored")
        return height - 98

    def line(label: str, value: object, y: float) -> float:
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(42, y, label.upper())
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica", 10)
        for text_line in simpleSplit(str(value or "-"), "Helvetica", 10, width - 190):
            pdf.drawString(150, y, text_line)
            y -= 13
        return y - 4

    y = header()
    for label, value in [
        ("Student", student.get("name")), ("Enrollment", student.get("enrollment_type")),
        ("College", student.get("college_name") or "Individual internship"),
        ("Project", assignment.get("variant_title")), ("Technology", assignment.get("project", {}).get("technology")),
        ("Internship", student.get("internship_type", "").replace("_", " ")),
        ("Attendance", f"{attendance.get('percentage')}%" if attendance.get("percentage") is not None else "Not used for individual internship"),
        ("Local fingerprint", assignment.get("project_fingerprint") or "Not recorded"),
    ]:
        y = line(label, value, y)

    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(42, y - 4, "TASK EVALUATIONS")
    y -= 28
    for task in assignment.get("tasks", []):
        if y < 120:
            pdf.showPage()
            y = header()
        run = task.get("judge0") or {}
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(42, y, f"Task {task['order_no']}: {task['title']}")
        y -= 15
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(muted)
        values = (
            f"Status: {task['status']}   Judge0: {run.get('passed_cases', 0)}/{run.get('total_cases', 0)}   "
            f"File: {', '.join(run.get('file_names', [])) or '-'}"
        )
        pdf.drawString(52, y, values[:115])
        y -= 12
        pdf.drawString(52, y, f"SHA-256: {run.get('source_hash', '-')}")
        y -= 20

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(42, 48, "GAINT verification record")
    pdf.setFont("Helvetica", 7)
    pdf.setFillColor(muted)
    pdf.drawString(42, 36, "The complete project remains on the student's local computer; GAINT stores only evaluation evidence and hashes.")
    pdf.setTitle(f"GAINT Evaluation Report - {student.get('name', 'Student')}")
    pdf.save()
    return buffer.getvalue()

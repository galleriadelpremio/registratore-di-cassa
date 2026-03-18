from reportlab.lib.pagesizes import A5
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from datetime import datetime


def genera_ricevuta_pdf(incasso: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        rightMargin=1.8*cm,
        leftMargin=1.8*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    elementi = []

    st_ente = ParagraphStyle("ente", fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#6b6b65"), leading=14)
    st_titolo = ParagraphStyle("titolo", fontSize=15, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a18"), leading=20, spaceAfter=2)
    st_sub = ParagraphStyle("sub", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor("#9a9a94"), leading=12)
    st_num = ParagraphStyle("num", fontSize=11, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=colors.HexColor("#b5892a"), leading=16)
    st_label = ParagraphStyle("label", fontSize=8, textColor=colors.HexColor("#9a9a94"), leading=12)
    st_valore = ParagraphStyle("valore", fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a18"), leading=16)
    st_importo = ParagraphStyle("importo", fontSize=22, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a18"), leading=28)
    st_note = ParagraphStyle("note", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor("#9a9a94"), leading=12)

    elementi.append(Paragraph("CITTÀ DI SUZZARA — Prov. di Mantova", st_ente))
    elementi.append(Spacer(1, 0.2*cm))
    elementi.append(Paragraph("Galleria del Premio", st_titolo))
    elementi.append(Paragraph("Gestione Attività Museale — Incassi", st_sub))
    elementi.append(Spacer(1, 0.4*cm))
    elementi.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ddd4")))
    elementi.append(Spacer(1, 0.4*cm))

    data_str = datetime.fromisoformat(incasso["data"]).strftime("%d/%m/%Y")
    elementi.append(Paragraph(f"Ricevuta n. {incasso['numero_ricevuta']:04d} / {incasso['anno']}", st_num))
    elementi.append(Spacer(1, 0.5*cm))

    dati_tabella = [
        [Paragraph("Data", st_label), Paragraph("Prodotto", st_label), Paragraph("Modalità", st_label)],
        [
            Paragraph(data_str, st_valore),
            Paragraph(incasso["prodotto_nome"], st_valore),
            Paragraph(incasso["modalita"], st_valore),
        ],
    ]

    if incasso.get("quantita", 1) > 1:
        dati_tabella[0].insert(2, Paragraph("Quantità", st_label))
        dati_tabella[1].insert(2, Paragraph(str(incasso["quantita"]), st_valore))

    t = Table(dati_tabella, colWidths=None)
    t.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#e2ddd4")),
    ]))
    elementi.append(t)
    elementi.append(Spacer(1, 0.6*cm))

    elementi.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ddd4")))
    elementi.append(Spacer(1, 0.4*cm))
    elementi.append(Paragraph(f"€ {incasso['importo_totale']:.2f}".replace(".", ","), st_importo))
    elementi.append(Spacer(1, 0.4*cm))
    elementi.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ddd4")))

    if incasso.get("note"):
        elementi.append(Spacer(1, 0.3*cm))
        elementi.append(Paragraph(f"Note: {incasso['note']}", st_note))

    elementi.append(Spacer(1, 0.6*cm))
    elementi.append(Paragraph(f"Emessa da: {incasso['operatore_nome']}", st_note))
    elementi.append(Spacer(1, 0.2*cm))
    elementi.append(Paragraph("Documento non fiscale — uso interno", st_note))

    doc.build(elementi)
    return buffer.getvalue()

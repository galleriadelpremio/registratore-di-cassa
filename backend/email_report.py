import os
import json
import urllib.request
import urllib.error
from datetime import datetime, date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
DESTINATARI = [
    "galleriapremio@comune.suzzara.it",
    "erika.vecchietti@comune.suzzara.it",
]
MITTENTE = "onboarding@resend.dev"


def fmteur(n):
    return f"€ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def genera_pdf_giornaliero(incassi: list, data: date) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    st_ente   = ParagraphStyle('ente',   fontSize=9,  alignment=TA_CENTER, textColor=colors.HexColor('#6b6b65'), leading=14)
    st_titolo = ParagraphStyle('titolo', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a18'), leading=22)
    st_sub    = ParagraphStyle('sub',    fontSize=9,  alignment=TA_CENTER, textColor=colors.HexColor('#9a9a94'), leading=13)
    st_data   = ParagraphStyle('data',   fontSize=12, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=18)
    st_label  = ParagraphStyle('label',  fontSize=8,  textColor=colors.HexColor('#9a9a94'), leading=12)
    st_val    = ParagraphStyle('val',    fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a18'), leading=16)
    st_tot    = ParagraphStyle('tot',    fontSize=18, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a18'), leading=24)
    st_note   = ParagraphStyle('note',   fontSize=8,  alignment=TA_CENTER, textColor=colors.HexColor('#9a9a94'), leading=12)

    hr = HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e2ddd4'))
    hr_dark = HRFlowable(width='100%', thickness=1, color=colors.HexColor('#b5892a'))

    elementi = []

    elementi.append(Paragraph("CITTA' DI SUZZARA — Prov. di Mantova", st_ente))
    elementi.append(Spacer(1, 0.2*cm))
    elementi.append(Paragraph("Galleria del Premio", st_titolo))
    elementi.append(Paragraph("Report giornaliero incassi", st_sub))
    elementi.append(Spacer(1, 0.4*cm))
    elementi.append(hr_dark)
    elementi.append(Spacer(1, 0.3*cm))
    elementi.append(Paragraph(data.strftime("%d/%m/%Y"), st_data))
    elementi.append(Spacer(1, 0.5*cm))

    if not incassi:
        elementi.append(Paragraph("Nessun incasso registrato per questa giornata.", st_note))
    else:
        tot = sum(i['importo_totale'] for i in incassi)
        cont = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'Contante')
        pos = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'POS')

        # Riepilogo totali
        dati_riepilogo = [
            [Paragraph('Totale incassato', st_label), Paragraph('Contante', st_label), Paragraph('POS', st_label)],
            [Paragraph(fmteur(tot), ParagraphStyle('tv', fontSize=14, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=20)),
             Paragraph(fmteur(cont), ParagraphStyle('tc', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#2d6a4f'), leading=18)),
             Paragraph(fmteur(pos), ParagraphStyle('tp', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a4e7a'), leading=18))],
        ]
        t_riepilogo = Table(dati_riepilogo, colWidths=[6*cm, 5*cm, 5*cm])
        t_riepilogo.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#e2ddd4')),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fafaf8')),
            ('ROUNDEDCORNERS', [4]),
        ]))
        elementi.append(t_riepilogo)
        elementi.append(Spacer(1, 0.5*cm))
        elementi.append(hr)
        elementi.append(Spacer(1, 0.4*cm))

        # Dettaglio per prodotto
        prodotti = {}
        for i in incassi:
            k = (i['prodotto_nome'], i['prodotto_prezzo'])
            if k not in prodotti:
                prodotti[k] = {'cont_n': 0, 'cont_imp': 0, 'pos_n': 0, 'pos_imp': 0}
            if i['modalita'] == 'Contante':
                prodotti[k]['cont_n'] += i['quantita']
                prodotti[k]['cont_imp'] += i['importo_totale']
            else:
                prodotti[k]['pos_n'] += i['quantita']
                prodotti[k]['pos_imp'] += i['importo_totale']

        header_det = [
            Paragraph('Prodotto', st_label),
            Paragraph('Prezzo', st_label),
            Paragraph('Cont. n.', st_label),
            Paragraph('Cont. €', st_label),
            Paragraph('POS n.', st_label),
            Paragraph('POS €', st_label),
            Paragraph('Totale', st_label),
        ]
        righe_det = [header_det]
        for (nome, prezzo), v in prodotti.items():
            tot_prod = v['cont_imp'] + v['pos_imp']
            righe_det.append([
                Paragraph(nome, st_val),
                Paragraph(fmteur(prezzo), st_val),
                Paragraph(str(v['cont_n']) if v['cont_n'] else '—', st_val),
                Paragraph(fmteur(v['cont_imp']) if v['cont_imp'] else '—', st_val),
                Paragraph(str(v['pos_n']) if v['pos_n'] else '—', st_val),
                Paragraph(fmteur(v['pos_imp']) if v['pos_imp'] else '—', st_val),
                Paragraph(fmteur(tot_prod), ParagraphStyle('tb', fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=16)),
            ])

        t_det = Table(righe_det, colWidths=[4.5*cm, 2*cm, 1.8*cm, 2.2*cm, 1.8*cm, 2.2*cm, 2.5*cm])
        t_det.setStyle(TableStyle([
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#1a1a18')),
            ('LINEBELOW', (0,1), (-1,-1), 0.3, colors.HexColor('#e2ddd4')),
        ]))
        elementi.append(t_det)
        elementi.append(Spacer(1, 0.5*cm))
        elementi.append(hr)
        elementi.append(Spacer(1, 0.4*cm))

        # Dettaglio ricevute
        elementi.append(Paragraph("Dettaglio ricevute", ParagraphStyle('h3', fontSize=10, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a4a46'), leading=14)))
        elementi.append(Spacer(1, 0.2*cm))

        header_ric = [
            Paragraph('N°', st_label),
            Paragraph('Prodotto', st_label),
            Paragraph('Qta', st_label),
            Paragraph('Importo', st_label),
            Paragraph('Modalita\'', st_label),
            Paragraph('Operatore', st_label),
        ]
        righe_ric = [header_ric]
        for i in sorted(incassi, key=lambda x: x['numero_ricevuta']):
            righe_ric.append([
                Paragraph(f"{i['numero_ricevuta']:04d}", st_val),
                Paragraph(i['prodotto_nome'], st_val),
                Paragraph(str(i['quantita']), st_val),
                Paragraph(fmteur(i['importo_totale']), st_val),
                Paragraph(i['modalita'], st_val),
                Paragraph(i['operatore_nome'], st_val),
            ])

        t_ric = Table(righe_ric, colWidths=[1.5*cm, 5.5*cm, 1.5*cm, 2.5*cm, 2.5*cm, 3.5*cm])
        t_ric.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#1a1a18')),
            ('LINEBELOW', (0,1), (-1,-1), 0.3, colors.HexColor('#e2ddd4')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ffffff'), colors.HexColor('#fafaf8')]),
        ]))
        elementi.append(t_ric)

    elementi.append(Spacer(1, 0.6*cm))
    elementi.append(Paragraph("Report generato automaticamente — Galleria del Premio, Suzzara", st_note))

    doc.build(elementi)
    return buffer.getvalue()


def genera_pdf_mensile(incassi: list, mese: int, anno: int) -> bytes:
    from calendar import monthrange
    MESI = ['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
            'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    st_ente   = ParagraphStyle('ente',   fontSize=9,  alignment=TA_CENTER, textColor=colors.HexColor('#6b6b65'), leading=14)
    st_titolo = ParagraphStyle('titolo', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a18'), leading=22)
    st_sub    = ParagraphStyle('sub',    fontSize=9,  alignment=TA_CENTER, textColor=colors.HexColor('#9a9a94'), leading=13)
    st_data   = ParagraphStyle('data',   fontSize=13, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=18)
    st_label  = ParagraphStyle('label',  fontSize=8,  textColor=colors.HexColor('#9a9a94'), leading=12)
    st_val    = ParagraphStyle('val',    fontSize=10, textColor=colors.HexColor('#1a1a18'), leading=15)
    st_note   = ParagraphStyle('note',   fontSize=8,  alignment=TA_CENTER, textColor=colors.HexColor('#9a9a94'), leading=12)

    hr = HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e2ddd4'))
    hr_dark = HRFlowable(width='100%', thickness=1, color=colors.HexColor('#b5892a'))

    elementi = []
    elementi.append(Paragraph("CITTA' DI SUZZARA — Prov. di Mantova", st_ente))
    elementi.append(Spacer(1, 0.2*cm))
    elementi.append(Paragraph("Galleria del Premio", st_titolo))
    elementi.append(Paragraph("Riepilogo mensile incassi", st_sub))
    elementi.append(Spacer(1, 0.4*cm))
    elementi.append(hr_dark)
    elementi.append(Spacer(1, 0.3*cm))
    elementi.append(Paragraph(f"{MESI[mese]} {anno}", st_data))
    elementi.append(Spacer(1, 0.5*cm))

    tot = sum(i['importo_totale'] for i in incassi)
    cont = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'Contante')
    pos = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'POS')
    n_ric = len(incassi)

    # Totali
    dati_tot = [
        [Paragraph('Totale mese', st_label), Paragraph('Contante', st_label), Paragraph('POS', st_label), Paragraph('N. ricevute', st_label)],
        [
            Paragraph(fmteur(tot), ParagraphStyle('tv', fontSize=14, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=20)),
            Paragraph(fmteur(cont), ParagraphStyle('tc', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#2d6a4f'), leading=18)),
            Paragraph(fmteur(pos), ParagraphStyle('tp', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a4e7a'), leading=18)),
            Paragraph(str(n_ric), ParagraphStyle('tn', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a18'), leading=18)),
        ],
    ]
    t_tot = Table(dati_tot, colWidths=[4.5*cm, 4*cm, 4*cm, 4.5*cm])
    t_tot.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#e2ddd4')),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fafaf8')),
    ]))
    elementi.append(t_tot)
    elementi.append(Spacer(1, 0.5*cm))
    elementi.append(hr)
    elementi.append(Spacer(1, 0.4*cm))

    # Riepilogo per prodotto
    prodotti = {}
    for i in incassi:
        k = i['prodotto_nome']
        if k not in prodotti:
            prodotti[k] = {'n': 0, 'imp': 0}
        prodotti[k]['n'] += i['quantita']
        prodotti[k]['imp'] += i['importo_totale']

    header_prod = [Paragraph('Prodotto', st_label), Paragraph('Quantita\'', st_label), Paragraph('Totale', st_label)]
    righe_prod = [header_prod]
    for nome, v in prodotti.items():
        righe_prod.append([Paragraph(nome, st_val), Paragraph(str(v['n']), st_val), Paragraph(fmteur(v['imp']), st_val)])

    t_prod = Table(righe_prod, colWidths=[9*cm, 4*cm, 4*cm])
    t_prod.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#1a1a18')),
        ('LINEBELOW', (0,1), (-1,-1), 0.3, colors.HexColor('#e2ddd4')),
    ]))
    elementi.append(t_prod)
    elementi.append(Spacer(1, 0.5*cm))
    elementi.append(hr)
    elementi.append(Spacer(1, 0.4*cm))

    # Riepilogo per giorno
    elementi.append(Paragraph("Dettaglio giornaliero", ParagraphStyle('h3', fontSize=10, fontName='Helvetica-Bold', textColor=colors.HexColor('#4a4a46'), leading=14)))
    elementi.append(Spacer(1, 0.2*cm))

    per_giorno = {}
    for i in incassi:
        g = i['data'][:10]
        if g not in per_giorno:
            per_giorno[g] = {'tot': 0, 'cont': 0, 'pos': 0, 'n': 0}
        per_giorno[g]['tot'] += i['importo_totale']
        per_giorno[g]['n'] += 1
        if i['modalita'] == 'Contante':
            per_giorno[g]['cont'] += i['importo_totale']
        else:
            per_giorno[g]['pos'] += i['importo_totale']

    header_g = [Paragraph('Data', st_label), Paragraph('N. ric.', st_label), Paragraph('Contante', st_label), Paragraph('POS', st_label), Paragraph('Totale', st_label)]
    righe_g = [header_g]
    for g in sorted(per_giorno.keys()):
        v = per_giorno[g]
        d = datetime.strptime(g, '%Y-%m-%d').strftime('%d/%m/%Y')
        righe_g.append([
            Paragraph(d, st_val),
            Paragraph(str(v['n']), st_val),
            Paragraph(fmteur(v['cont']) if v['cont'] else '—', st_val),
            Paragraph(fmteur(v['pos']) if v['pos'] else '—', st_val),
            Paragraph(fmteur(v['tot']), ParagraphStyle('tg', fontSize=10, fontName='Helvetica-Bold', textColor=colors.HexColor('#b5892a'), leading=15)),
        ])

    t_g = Table(righe_g, colWidths=[3.5*cm, 2.5*cm, 4*cm, 4*cm, 3*cm])
    t_g.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#1a1a18')),
        ('LINEBELOW', (0,1), (-1,-1), 0.3, colors.HexColor('#e2ddd4')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ffffff'), colors.HexColor('#fafaf8')]),
    ]))
    elementi.append(t_g)
    elementi.append(Spacer(1, 0.6*cm))
    elementi.append(Paragraph("Report generato automaticamente — Galleria del Premio, Suzzara", st_note))

    doc.build(elementi)
    return buffer.getvalue()


def invia_email(oggetto: str, corpo_html: str, allegati: list = None) -> bool:
    """Invia email via Resend API. allegati = [{'nome': 'file.pdf', 'contenuto': bytes}]"""
    if not RESEND_API_KEY:
        print("RESEND_API_KEY non configurata")
        return False

    import base64
    attachments = []
    if allegati:
        for a in allegati:
            attachments.append({
                "filename": a['nome'],
                "content": base64.b64encode(a['contenuto']).decode('utf-8'),
            })

    payload = {
        "from": f"Galleria del Premio <{MITTENTE}>",
        "to": DESTINATARI,
        "subject": oggetto,
        "html": corpo_html,
    }
    if attachments:
        payload["attachments"] = attachments

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Email inviata: {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Errore invio email: {e.code} — {e.read().decode()}")
        return False


def html_giornaliero(incassi: list, data: date) -> str:
    tot = sum(i['importo_totale'] for i in incassi)
    cont = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'Contante')
    pos = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'POS')

    righe_det = ""
    for i in sorted(incassi, key=lambda x: x['numero_ricevuta']):
        righe_det += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #f0ece4">{i['numero_ricevuta']:04d}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0ece4">{i['prodotto_nome']}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0ece4;text-align:center">{i['quantita']}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0ece4;text-align:right;font-weight:500">{fmteur(i['importo_totale'])}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0ece4">{i['modalita']}</td>
        </tr>"""

    return f"""
    <div style="font-family:'DM Sans',Arial,sans-serif;max-width:600px;margin:0 auto;background:#f7f5f0;padding:20px">
      <div style="background:#1a1a18;padding:24px;border-radius:12px 12px 0 0;text-align:center">
        <p style="color:#b5892a;font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin:0 0 4px">Città di Suzzara</p>
        <h1 style="color:#fff;font-size:20px;margin:0">Galleria del Premio</h1>
        <p style="color:rgba(255,255,255,.5);font-size:12px;margin:4px 0 0">Report giornaliero — {data.strftime('%d/%m/%Y')}</p>
      </div>
      <div style="background:#fff;padding:24px;border-radius:0 0 12px 12px">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">Totale</p>
            <p style="font-size:20px;font-weight:700;color:#b5892a;margin:0">{fmteur(tot)}</p>
          </div>
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">Contante</p>
            <p style="font-size:18px;font-weight:700;color:#2d6a4f;margin:0">{fmteur(cont)}</p>
          </div>
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">POS</p>
            <p style="font-size:18px;font-weight:700;color:#1a4e7a;margin:0">{fmteur(pos)}</p>
          </div>
        </div>
        {'<p style="color:#9a9a94;text-align:center;font-size:14px">Nessun incasso registrato oggi.</p>' if not incassi else f'''
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f0ece4">
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#9a9a94;font-weight:500">N°</th>
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#9a9a94;font-weight:500">Prodotto</th>
              <th style="padding:8px 12px;text-align:center;font-size:11px;color:#9a9a94;font-weight:500">Qta</th>
              <th style="padding:8px 12px;text-align:right;font-size:11px;color:#9a9a94;font-weight:500">Importo</th>
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#9a9a94;font-weight:500">Modalita\'</th>
            </tr>
          </thead>
          <tbody>{righe_det}</tbody>
        </table>'''}
        <p style="font-size:11px;color:#c0c0b8;text-align:center;margin-top:24px">
          Report automatico — Galleria del Premio, Suzzara<br>
          Documento non fiscale — uso interno
        </p>
      </div>
    </div>"""


def html_mensile(incassi: list, mese: int, anno: int) -> str:
    MESI = ['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
            'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
    tot = sum(i['importo_totale'] for i in incassi)
    cont = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'Contante')
    pos = sum(i['importo_totale'] for i in incassi if i['modalita'] == 'POS')

    prodotti = {}
    for i in incassi:
        k = i['prodotto_nome']
        if k not in prodotti:
            prodotti[k] = {'n': 0, 'imp': 0}
        prodotti[k]['n'] += i['quantita']
        prodotti[k]['imp'] += i['importo_totale']

    righe_prod = ""
    for nome, v in prodotti.items():
        righe_prod += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f0ece4">{nome}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0ece4;text-align:center">{v['n']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0ece4;text-align:right;font-weight:600;color:#b5892a">{fmteur(v['imp'])}</td>
        </tr>"""

    return f"""
    <div style="font-family:'DM Sans',Arial,sans-serif;max-width:600px;margin:0 auto;background:#f7f5f0;padding:20px">
      <div style="background:#1a1a18;padding:24px;border-radius:12px 12px 0 0;text-align:center">
        <p style="color:#b5892a;font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin:0 0 4px">Citta\' di Suzzara</p>
        <h1 style="color:#fff;font-size:20px;margin:0">Galleria del Premio</h1>
        <p style="color:rgba(255,255,255,.5);font-size:12px;margin:4px 0 0">Riepilogo mensile — {MESI[mese]} {anno}</p>
      </div>
      <div style="background:#fff;padding:24px;border-radius:0 0 12px 12px">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">Totale mese</p>
            <p style="font-size:20px;font-weight:700;color:#b5892a;margin:0">{fmteur(tot)}</p>
          </div>
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">Contante</p>
            <p style="font-size:18px;font-weight:700;color:#2d6a4f;margin:0">{fmteur(cont)}</p>
          </div>
          <div style="background:#f7f5f0;padding:16px;border-radius:8px;text-align:center">
            <p style="font-size:11px;color:#9a9a94;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em">POS</p>
            <p style="font-size:18px;font-weight:700;color:#1a4e7a;margin:0">{fmteur(pos)}</p>
          </div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f0ece4">
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#9a9a94;font-weight:500">Prodotto</th>
              <th style="padding:8px 12px;text-align:center;font-size:11px;color:#9a9a94;font-weight:500">Quantita\'</th>
              <th style="padding:8px 12px;text-align:right;font-size:11px;color:#9a9a94;font-weight:500">Totale</th>
            </tr>
          </thead>
          <tbody>{righe_prod}</tbody>
        </table>
        <p style="font-size:11px;color:#c0c0b8;text-align:center;margin-top:24px">
          Report automatico — Galleria del Premio, Suzzara<br>
          Il modulo corrispettivi Excel e\' allegato a questa email.
        </p>
      </div>
    </div>"""


async def invia_report_giornaliero(db):
    """Da chiamare ogni giorno alle 18:00"""
    from database import Incasso
    oggi = date.today()
    incassi = db.query(Incasso).filter(
        Incasso.anno == oggi.year,
        Incasso.mese == oggi.month,
    ).all()
    # Filtra solo oggi
    incassi_oggi = [i for i in incassi if i.data.date() == oggi]

    payload = [
        {
            'numero_ricevuta': i.numero_ricevuta,
            'prodotto_nome': i.prodotto_nome,
            'prodotto_prezzo': i.prodotto_prezzo,
            'quantita': i.quantita,
            'importo_totale': i.importo_totale,
            'modalita': i.modalita,
            'operatore_nome': i.operatore_nome,
            'data': i.data.isoformat(),
        }
        for i in incassi_oggi
    ]

    pdf = genera_pdf_giornaliero(payload, oggi)
    html = html_giornaliero(payload, oggi)
    oggetto = f"Galleria del Premio — Incassi {oggi.strftime('%d/%m/%Y')}"
    if not payload:
        oggetto += " — Nessun incasso"

    return invia_email(oggetto, html, [{'nome': f"report_{oggi.isoformat()}.pdf", 'contenuto': pdf}])


async def invia_report_mensile(db, mese: int, anno: int):
    """Da chiamare l'ultimo giorno del mese alle 18:00"""
    from database import Incasso
    from modulo_excel import genera_modulo_excel
    MESI = ['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
            'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']

    incassi = db.query(Incasso).filter(
        Incasso.anno == anno,
        Incasso.mese == mese,
    ).order_by(Incasso.data).all()

    payload = [
        {
            'numero_ricevuta': i.numero_ricevuta,
            'prodotto_nome': i.prodotto_nome,
            'prodotto_prezzo': i.prodotto_prezzo,
            'quantita': i.quantita,
            'importo_totale': i.importo_totale,
            'modalita': i.modalita,
            'operatore_nome': i.operatore_nome,
            'data': i.data.isoformat(),
            'ricevuta_da': i.ricevuta_da,
            'ricevuta_a': i.ricevuta_a,
            'note': i.note,
        }
        for i in incassi
    ]

    pdf = genera_pdf_mensile(payload, mese, anno)
    xlsx = genera_modulo_excel(payload, mese, anno)
    html = html_mensile(payload, mese, anno)
    nome_mese = MESI[mese]
    oggetto = f"Galleria del Premio — Riepilogo {nome_mese} {anno}"

    return invia_email(oggetto, html, [
        {'nome': f"report_mensile_{nome_mese}_{anno}.pdf", 'contenuto': pdf},
        {'nome': f"Corrispettivi_{nome_mese}_{anno}.xlsx", 'contenuto': xlsx},
    ])

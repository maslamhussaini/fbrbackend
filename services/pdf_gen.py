"""
FBR Sales Tax Invoice PDF Generator
A4 Landscape — matches HAMRA ENTERPRISES format exactly
"""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from io import BytesIO
import qrcode

# ── Page setup (Landscape) ────────────────────────────────────────────────────
PW, PH = landscape(A4)   # 841.89 x 595.27 points
ML  = 12 * mm
MR  = 12 * mm
MT  = 8  * mm
MB  = 8  * mm
USE_W = PW - ML - MR
USE_H = PH - MT - MB

BLACK = colors.black
WHITE = colors.white
GRAY  = colors.HexColor("#666666")
LGRAY = colors.HexColor("#f0f0f0")
DGRAY = colors.HexColor("#e0e0e0")
BORD  = colors.HexColor("#999999")


def fmt(n):
    try:
        return f"{float(n or 0):,.2f}"
    except Exception:
        return "0.00"


def number_to_words(n: float) -> str:
    ones  = ["","One","Two","Three","Four","Five","Six","Seven","Eight","Nine",
             "Ten","Eleven","Twelve","Thirteen","Fourteen","Fifteen","Sixteen",
             "Seventeen","Eighteen","Nineteen"]
    tens  = ["","","Twenty","Thirty","Forty","Fifty","Sixty","Seventy","Eighty","Ninety"]

    def _b1000(n):
        if n == 0:   return ""
        elif n < 20: return ones[n]
        elif n < 100:return tens[n//10]+(" "+ones[n%10] if n%10 else "")
        else:        return ones[n//100]+" Hundred"+(" "+_b1000(n%100) if n%100 else "")

    rupees = int(n)
    paisa  = round((n - rupees) * 100)

    if   rupees == 0:       w = "Zero"
    elif rupees < 1000:     w = _b1000(rupees)
    elif rupees < 100000:   w = _b1000(rupees//1000)+" Thousand"+(" "+_b1000(rupees%1000) if rupees%1000 else "")
    elif rupees < 10000000: w = _b1000(rupees//100000)+" Lac"+(" "+_b1000((rupees%100000)//1000)+" Thousand" if (rupees%100000)//1000 else "")+(" "+_b1000(rupees%1000) if rupees%1000 else "")
    else:                   w = _b1000(rupees//10000000)+" Crore"+(" "+_b1000((rupees%10000000)//100000)+" Lac" if (rupees%10000000)//100000 else "")+(" "+_b1000(rupees%1000) if rupees%1000 else "")

    result = "Rupees " + w
    if paisa:
        result += f" and {_b1000(paisa)} Paisa"
    return result + " Only"


def generate_fbr_invoice_pdf(invoice: dict, company: dict, items: list) -> bytes:
    buf = BytesIO()
    cv  = canvas.Canvas(buf, pagesize=landscape(A4))
    y   = PH - MT

    # ── Helpers ───────────────────────────────────────────────────────────────
    def line(x1,y1,x2,y2,w=0.4,col=BORD):
        cv.setStrokeColor(col); cv.setLineWidth(w); cv.line(x1,y1,x2,y2)

    def box(x,y,w,h,fill=None,stroke=BORD,lw=0.4):
        cv.setLineWidth(lw); cv.setStrokeColor(stroke)
        if fill: cv.setFillColor(fill); cv.rect(x,y,w,h,fill=1,stroke=1)
        else:    cv.rect(x,y,w,h,fill=0,stroke=1)
        cv.setFillColor(BLACK)

    def txt(x,y,s,sz=7,bold=False,align="left",col=BLACK):
        cv.setFillColor(col)
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", sz)
        s = str(s)
        if   align=="center": cv.drawCentredString(x,y,s)
        elif align=="right":  cv.drawRightString(x,y,s)
        else:                 cv.drawString(x,y,s)
        cv.setFillColor(BLACK)

    def cell(x,y,w,h,s,sz=6.5,bold=False,align="center",
             fill=None,pad_r=2,pad_l=2):
        box(x,y,w,h,fill=fill)
        s = str(s)
        cy = y + h/2 - sz*0.35
        if   align=="center": txt(x+w/2,  cy, s, sz, bold, "center")
        elif align=="right":  txt(x+w-pad_r, cy, s, sz, bold, "right")
        else:                 txt(x+pad_l,   cy, s, sz, bold, "left")

    def multi_line_cell(x,y,w,h,lines,sz=5.5,bold=False,fill=None):
        box(x,y,w,h,fill=fill)
        n    = len(lines)
        step = sz * 1.3
        start_y = y + h/2 + (n-1)*step/2 - sz*0.3
        for i,ln in enumerate(lines):
            cv.setFont("Helvetica-Bold" if bold else "Helvetica", sz)
            cv.drawCentredString(x+w/2, start_y - i*step, ln)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. COMPANY HEADER
    # ══════════════════════════════════════════════════════════════════════════
    txt(PW/2, y-12, company.get("name","").upper(), sz=15, bold=True, align="center")
    y -= 16
    txt(PW/2, y-8, company.get("address","").upper(), sz=7, bold=True, align="center")
    y -= 12

    ph = company.get("phone",""); mb = company.get("mobile","")
    if ph or mb:
        contact = ("Phone : "+ph if ph else "") + ("      Mobile : "+mb if mb else "")
        txt(PW/2, y-7, contact, sz=7, align="center")
        y -= 10

    txt(PW/2, y-7, f"NTN : {company.get('ntn','')}      STRN : {company.get('strn','')}", sz=7, align="center")
    y -= 12

    txt(PW/2, y-9, "SALES TAX INVOICE", sz=13, bold=True, align="center")
    y -= 16

    # ══════════════════════════════════════════════════════════════════════════
    # 2. CUSTOMER / INVOICE DETAILS BOX
    # ══════════════════════════════════════════════════════════════════════════
    box_h  = 62
    box_y  = y - box_h

    # Three columns
    c1w = USE_W * 0.45   # Customer info
    c2w = USE_W * 0.22   # NTN / STRN
    c3w = USE_W * 0.18   # Invoice No / Date / Ref
    c4w = USE_W * 0.15   # Remarks

    x1 = ML
    x2 = x1 + c1w
    x3 = x2 + c2w
    x4 = x3 + c3w

    box(x1, box_y, c1w, box_h)
    box(x2, box_y, c2w, box_h)
    box(x3, box_y, c3w, box_h)
    box(x4, box_y, c4w, box_h)

    # Col 1 — Customer
    fy = y - 10
    for lbl, val in [
        ("CUSTOMER :", invoice.get("customer_name","UNREGISTERED")),
        ("PHONE :",    invoice.get("customer_phone","-")),
        ("CNIC NO :",  invoice.get("customer_cnic","-")),
        ("ADDRESS :",  invoice.get("customer_address","-")),
    ]:
        txt(x1+3,  fy, lbl, sz=7, bold=True)
        txt(x1+42, fy, str(val or "-"), sz=7)
        fy -= 12

    # Col 2 — NTN/STRN
    fy = y - 10
    for lbl, val in [
        ("NTN :",  invoice.get("customer_ntn","-")),
        ("STRN :", invoice.get("customer_strn","-")),
    ]:
        txt(x2+4,  fy, lbl, sz=7, bold=True)
        txt(x2+30, fy, str(val or "-"), sz=7)
        fy -= 12

    # Col 3 — Invoice details
    fy = y - 10
    for lbl, val in [
        ("INVOICE NO :", invoice.get("invoice_number","")),
        ("DATE :",        invoice.get("invoice_date","")),
        ("REF NO. :",     invoice.get("ref_no","")),
    ]:
        txt(x3+4,  fy, lbl, sz=7, bold=True)
        txt(x3+42, fy, str(val or "-"), sz=7)
        fy -= 12

    # Col 4 — Remarks
    txt(x4+4, y-10, "Remarks", sz=7, bold=True)
    txt(x4+4, y-22, str(invoice.get("remarks","-") or "-"), sz=7)

    y = box_y - 3

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ITEMS TABLE
    # ══════════════════════════════════════════════════════════════════════════
    # Column definitions: (header lines, width_mm, align)
    COLS = [
        (["S.NO"],                                      9*mm,  "center"),
        (["HS CODE"],                                   17*mm, "center"),
        (["DESCRIPTION","OF GOOD'S"],                   25*mm, "left"),
        (["UOM"],                                        9*mm, "center"),
        (["QTY"],                                       14*mm, "right"),
        (["UNIT","PRICE"],                              16*mm, "right"),
        (["VALUE OF","EXCL. ST"],                       20*mm, "right"),
        (["SALES","TAX %"],                             13*mm, "center"),
        (["AMOUNT","OF SALE","TAX"],                    20*mm, "right"),
        (["FURTHER","TAX %"],                           13*mm, "center"),
        (["AMOUNT","OF FURTHER","TAX"],                 19*mm, "right"),
        (["DISC.","%"],                                 11*mm, "center"),
        (["DISC.","AMOUNT"],                            16*mm, "right"),
        (["VALUE","INCLUDING","SALES TAX"],             22*mm, "right"),
    ]

    HDR_H  = 24
    ROW_H  = 16
    tbl_x  = ML

    # Verify total width fits
    total_cw = sum(c[1] for c in COLS)
    if total_cw > USE_W:
        scale = USE_W / total_cw
        COLS = [(h, w*scale, a) for h,w,a in COLS]

    # Header row
    tx = tbl_x
    for headers, cw, _ in COLS:
        multi_line_cell(tx, y-HDR_H, cw, HDR_H, headers, sz=5.5, bold=True, fill=DGRAY)
        tx += cw
    y -= HDR_H

    # Data rows
    total_excl = total_st = total_ft = total_disc = total_net = 0
    total_qty  = 0

    for i, item in enumerate(items, 1):
        excl   = float(item.get("value_excl_st") or 0)
        qty    = float(item.get("qty") or item.get("quantity") or 0)
        up     = float(item.get("unit_price") or (excl/qty if qty else 0))
        st_pct = float(item.get("sales_tax_pct") or 0)
        st_amt = float(item.get("sales_tax_amt") or item.get("salesTaxApplicable") or excl*st_pct/100)
        ft_pct = float(item.get("further_tax_pct") or 0)
        ft_amt = float(item.get("further_tax_amt") or 0)
        d_pct  = float(item.get("discount_pct") or 0)
        d_amt  = float(item.get("discount_amt") or 0)
        total  = excl + st_amt + ft_amt - d_amt

        total_excl += excl; total_st += st_amt; total_ft += ft_amt
        total_disc += d_amt; total_net += total; total_qty += qty

        values = [
            str(i), item.get("hs_code",""),
            item.get("description",""),
            item.get("uom","KG"),
            fmt(qty), fmt(up), fmt(excl),
            f"{st_pct:.2f}", fmt(st_amt),
            f"{ft_pct:.2f}", fmt(ft_amt),
            f"{d_pct:.2f}", fmt(d_amt),
            fmt(total),
        ]

        bg = WHITE if i%2==0 else colors.HexColor("#fafafa")
        tx = tbl_x
        for j, ((_, cw, align), val) in enumerate(zip(COLS, values)):
            cell(tx, y-ROW_H, cw, ROW_H, val, sz=6.5, align=align, fill=bg)
            tx += cw
        y -= ROW_H

    # Bottom border of table
    line(tbl_x, y, tbl_x+total_cw, y, w=0.6, col=BLACK)
    y -= 5

    # ══════════════════════════════════════════════════════════════════════════
    # 4. SUMMARY SECTION
    # ══════════════════════════════════════════════════════════════════════════
    sum_y = y

    # Left: item count + words
    txt(ML, sum_y-8, f"No. of Items : {len(items):.2f}      Qty. : {total_qty:,.2f}",
        sz=7, bold=True)

    words_y = sum_y - 22
    words_style = ParagraphStyle("w", fontName="Helvetica-Bold", fontSize=7,
                                  leading=10, textColor=BLACK)
    p = Paragraph(f"Amount In Word : {number_to_words(total_net)}", words_style)
    pw2, ph2 = p.wrap(USE_W*0.52, 40)
    p.drawOn(cv, ML, words_y - ph2)

    # Right: totals box
    tot_x   = ML + USE_W * 0.54
    tot_lw  = USE_W * 0.30
    tot_vw  = USE_W * 0.16
    tot_y   = sum_y
    row_h_t = 11

    st_pct_display = items[0].get("sales_tax_pct", 0) if items else 0
    ft_pct_display = items[0].get("further_tax_pct", 0) if items else 0

    totals = [
        ("EXCL. TAX AMOUNT :",                          fmt(total_excl), False),
        (f"SALES TAX ({st_pct_display:.0f}i) % :",       fmt(total_st),   False),
        (f"FURTHER TAX ( {ft_pct_display:.0f} ) % :",    fmt(total_ft),   False),
        ("TOTAL DISCOUNT ( _ 0.00% :",                  fmt(total_disc), False),
        ("ADVANCE TAX U/S 236G ( _ 0.00% :",            "0.00",          False),
        ("NET AMOUNT :",                                 fmt(total_net),  True),
    ]

    for lbl, val, is_last in totals:
        bg_fill = LGRAY if is_last else WHITE
        cell(tot_x,         tot_y-row_h_t, tot_lw, row_h_t, lbl,
             sz=6.5, bold=is_last, align="right", fill=bg_fill, pad_r=3)
        cell(tot_x+tot_lw,  tot_y-row_h_t, tot_vw, row_h_t, val,
             sz=6.5, bold=is_last, align="right", fill=bg_fill, pad_r=3)
        tot_y -= row_h_t

    y = min(words_y - ph2, tot_y) - 10

    # ══════════════════════════════════════════════════════════════════════════
    # 5. BARCODE + FBR QR BOX
    # ══════════════════════════════════════════════════════════════════════════
    tracking = str(invoice.get("tracking_no",""))

    # Barcode (left)
    bc_h = 20*mm; bc_w = 55*mm
    bc_x = ML; bc_y = y - bc_h - 4

    if bc_y > MB:
        cv.setFillColor(BLACK)
        bar_w = 1.4
        for bi in range(int(bc_w / (bar_w*2))):
            bx = bc_x + bi*bar_w*2
            if bi % 3 != 1:
                cv.rect(bx, bc_y, bar_w, bc_h, fill=1, stroke=0)
        if tracking:
            txt(bc_x+bc_w/2, bc_y-7, tracking, sz=5.5, align="center")

        # FBR box (right)
        if tracking:
            fb_w = 65*mm; fb_h = 30*mm
            fb_x = PW - MR - fb_w; fb_y = y - fb_h - 4

            box(fb_x, fb_y, fb_w, fb_h, stroke=BORD, lw=1)
            txt(fb_x+fb_w/2, fb_y+fb_h-9,  "FBR Invoice #", sz=9, bold=True, align="center")
            txt(fb_x+fb_w/2, fb_y+fb_h-19, tracking,        sz=6.5, align="center")

            # QR Code
            try:
                qr = qrcode.QRCode(version=1, box_size=2, border=1,
                                   error_correction=qrcode.constants.ERROR_CORRECT_L)
                qr.add_data(tracking); qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_buf = BytesIO(); qr_img.save(qr_buf, format="PNG"); qr_buf.seek(0)
                qr_sz = 22*mm
                cv.drawImage(qr_buf, fb_x+4, fb_y+3, width=qr_sz, height=qr_sz,
                             preserveAspectRatio=True)
            except Exception:
                pass

        y = bc_y - 12

    # ══════════════════════════════════════════════════════════════════════════
    # 6. FOOTER
    # ══════════════════════════════════════════════════════════════════════════
    footer_y = MB + 14
    line(ML, footer_y+8, PW-MR, footer_y+8)
    txt(PW/2, footer_y+2,
        "THIS IS SYSTEM GENERATED INVOICE NOT REQUIRED ANY STAMP OR SIGN",
        sz=7, bold=True, align="center")
    txt(PW/2, footer_y-8, "Solution By: FBR Digital Invoicing System",
        sz=6.5, align="center", col=GRAY)

    cv.save()
    buf.seek(0)
    return buf.read()


def generate_from_invoice_record(invoice_record: dict, items: list, tenant: dict) -> bytes:
    company = {
        "name":    tenant.get("name",""),
        "address": tenant.get("address",""),
        "phone":   tenant.get("phone",""),
        "mobile":  tenant.get("mobile",""),
        "ntn":     tenant.get("ntn_cnic",""),
        "strn":    tenant.get("strn",""),
    }
    invoice = {
        "invoice_number":   invoice_record.get("invoice_number",""),
        "invoice_date":     str(invoice_record.get("invoice_date","")),
        "ref_no":           invoice_record.get("invoice_ref_no",""),
        "customer_name":    invoice_record.get("buyer_business_name","UNREGISTERED"),
        "customer_ntn":     invoice_record.get("buyer_ntn_cnic",""),
        "customer_strn":    "",
        "customer_phone":   "",
        "customer_cnic":    "",
        "customer_address": invoice_record.get("buyer_address",""),
        "remarks":          "",
        "tracking_no":      invoice_record.get("tracking_no",""),
    }
    built_items = []
    for it in items:
        excl   = float(it.get("value_excl_st") or 0)
        qty    = float(it.get("quantity") or 1)
        st_pct = float(it.get("sales_tax_pct") or 18)
        st_amt = float(it.get("sales_tax") or excl * st_pct / 100)
        up     = excl / qty if qty else 0
        built_items.append({
            "hs_code":         it.get("hs_code",""),
            "description":     it.get("product_description",""),
            "uom":             it.get("uom","KG"),
            "qty":             qty,
            "unit_price":      up,
            "value_excl_st":   excl,
            "sales_tax_pct":   st_pct,
            "sales_tax_amt":   st_amt,
            "further_tax_pct": float(it.get("further_tax_pct") or 0),
            "further_tax_amt": float(it.get("further_tax_amt") or 0),
            "discount_pct":    float(it.get("discount_pct") or 0),
            "discount_amt":    float(it.get("discount_amt") or 0),
        })
    return generate_fbr_invoice_pdf(invoice, company, built_items)

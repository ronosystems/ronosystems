# apps/epa_shop/barcode_utils.py
"""
Barcode + label generation for EPA Shop.

Label layout (fixed spacing, no overlap):

    ┌──────────────────────────────┐
    │                              │
    │   ┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃    │  ← bars only (no text baked in)
    │                              │
    │          F000004             │  ← product code drawn by ReportLab
    │                              │
    └──────────────────────────────┘
"""

import io
import barcode
from barcode.writer import ImageWriter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


LABEL_SIZES = {
    'small':    (40, 20),
    'medium':   (50, 25),
    'large':    (60, 30),
    'square':   (50, 50),
    'a4_sheet': (210, 297),
}


def generate_barcode_image(code: str, module_width=0.2, module_height=10.0):
    """
    Return a BytesIO containing ONLY the bars (no human-readable text).
    We draw the code ourselves below the bars for pixel-perfect layout.
    """
    code = str(code).strip()
    if not code:
        raise ValueError("Cannot generate barcode for empty code")

    barcode_class = barcode.get_barcode_class('code128')
    buffer = io.BytesIO()
    writer = ImageWriter()

    bc = barcode_class(code, writer=writer)
    bc.write(buffer, options={
        'module_width':  module_width,
        'module_height': module_height,
        'quiet_zone':    2.0,
        'write_text':    False,     # 👈 KEY: no baked-in text
        'background':    'white',
        'foreground':    'black',
    })
    buffer.seek(0)
    return buffer


def _draw_label(c, x, y, w, h, product_code):
    """
    Draw ONE label: barcode bars on top, product code below.

    Layout (from top of label to bottom):
        ┌───────────────────────────┐
        │  top padding              │
        │                           │
        │   ┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃    │  barcode region (≈68% of height)
        │                           │
        │  gap                      │
        │                           │
        │       F000004             │  code text (≈22% of height)
        │                           │
        │  bottom padding           │
        └───────────────────────────┘
    """
    padding_x = 2.5 * mm
    padding_top = 2.0 * mm
    padding_bottom = 2.0 * mm

    # Text row gets about a quarter of the label height.
    # Whatever remains is given to the barcode region.
    text_zone_h = max(4 * mm, h * 0.24)
    gap = 0.6 * mm

    barcode_h = h - padding_top - padding_bottom - text_zone_h - gap
    barcode_w = w - (2 * padding_x)

    # Safety: if the label is very short, keep the barcode positive.
    if barcode_h < 4 * mm:
        barcode_h = max(4 * mm, h * 0.5)
        text_zone_h = h - padding_top - padding_bottom - barcode_h - gap

    # --- 1) Barcode bars (image) ---------------------------------
    try:
        bc_buffer = generate_barcode_image(product_code)
        img = ImageReader(bc_buffer)

        # Position: top of the label minus padding_top, anchored at its bottom edge
        img_y = y + padding_bottom + text_zone_h + gap
        c.drawImage(
            img,
            x + padding_x,
            img_y,
            width=barcode_w,
            height=barcode_h,
            preserveAspectRatio=True,
            anchor='c',           # centre the image inside its box
            mask='auto',
        )
    except Exception:
        # Fallback so the PDF never breaks silently
        c.setFont("Helvetica", 6)
        c.drawCentredString(x + w / 2, y + h / 2, f"[barcode error: {product_code}]")

    # --- 2) Product code text (drawn below the bars) ------------
    # Auto-shrink the font if the code is long
    text_len = len(str(product_code))
    if text_len <= 8:
        font_size = 11
    elif text_len <= 12:
        font_size = 9
    else:
        font_size = 7

    c.setFont("Helvetica-Bold", font_size)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(
        x + w / 2,
        y + padding_bottom + (text_zone_h / 2) - (font_size * 0.35),
        str(product_code),
    )


def build_label_pdf(products, size='medium'):
    """
    Build a PDF with one label per page — for thermal roll printers.
    `products` = iterable with a `product_code` attribute.
    """
    width_mm, height_mm = LABEL_SIZES.get(size, LABEL_SIZES['medium'])
    page_w = width_mm * mm
    page_h = height_mm * mm

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))

    for product in products:
        code = getattr(product, 'product_code', None)
        if not code:
            continue

        _draw_label(c, x=0, y=0, w=page_w, h=page_h, product_code=code)
        c.showPage()  # each product = new page

    c.save()
    buffer.seek(0)
    return buffer


def build_label_sheet_pdf(products, size='medium', cols=4, rows=10):
    """
    Build a single A4 page with a grid of labels (for laser printers
    on sticker sheets).
    """
    label_w_mm, label_h_mm = LABEL_SIZES.get(size, LABEL_SIZES['medium'])
    label_w = label_w_mm * mm
    label_h = label_h_mm * mm

    a4_w, a4_h = 210 * mm, 297 * mm

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(a4_w, a4_h))

    margin_x = 5 * mm
    margin_y = 5 * mm

    col = 0
    row = 0

    for product in products:
        code = getattr(product, 'product_code', None)
        if not code:
            continue

        x = margin_x + col * label_w
        y = a4_h - margin_y - (row + 1) * label_h

        _draw_label(c, x=x, y=y, w=label_w, h=label_h, product_code=code)

        col += 1
        if col >= cols:
            col = 0
            row += 1
            if row >= rows:
                c.showPage()
                row = 0

    c.save()
    buffer.seek(0)
    return buffer
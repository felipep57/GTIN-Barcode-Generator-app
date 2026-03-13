import os
import re
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from reportlab.graphics.barcode import eanbc
from reportlab.lib.colors import black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


APP_TITLE = "Carton Label Generator"
PDF_FILENAME = "carton_label.pdf"


# -----------------------------
# Validation helpers
# -----------------------------
def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def ean13_check_digit_ok(gtin13: str) -> bool:
    if not re.fullmatch(r"\d{13}", gtin13):
        return False

    digits = [int(d) for d in gtin13]
    check = digits[-1]
    body = digits[:-1]

    total = 0
    for idx, digit in enumerate(body):
        total += digit * (1 if idx % 2 == 0 else 3)

    calc = (10 - (total % 10)) % 10
    return calc == check


def normalize_gtin_for_ean13(gtin: str) -> str:
    raw = digits_only(gtin)

    if len(raw) == 13 and ean13_check_digit_ok(raw):
        return raw

    if len(raw) == 14 and raw.startswith("0"):
        converted = raw[1:]
        if ean13_check_digit_ok(converted):
            return converted

    raise ValueError(
        "GTIN must be a valid 13-digit GTIN or a 14-digit GTIN starting with 0 that converts to a valid EAN-13."
    )


# -----------------------------
# PDF label drawing
# -----------------------------
def fit_text(c: canvas.Canvas, text: str, font_name: str, max_size: int, min_size: int, width: float) -> int:
    size = max_size
    while size >= min_size:
        if c.stringWidth(text, font_name, size) <= width:
            return size
        size -= 1
    return min_size


class LabelPDFBuilder:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.page_width = 8.5 * inch
        self.page_height = 8.5 * inch
        self.margin = 0.35 * inch
        self.label_x = self.margin
        self.label_y = self.margin
        self.label_w = self.page_width - (self.margin * 2)
        self.label_h = self.page_height - (self.margin * 2)

    def build(self, data: dict):
        c = canvas.Canvas(self.pdf_path, pagesize=(self.page_width, self.page_height))
        c.setTitle("Carton Label")

        x = self.label_x
        y = self.label_y
        w = self.label_w
        h = self.label_h

        # Background
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(x, y, w, h, stroke=0, fill=1)
        c.setFillColor(black)

        pad = 0.28 * inch
        left_x = x + pad
        right_x = x + w - pad
        top_y = y + h - pad

        # Top row headings
        c.setFont("Helvetica", 16)
        c.drawString(left_x, top_y, "VENDOR STK NO.")
        c.drawRightString(right_x, top_y, "PACK, UNITS")

        # Top row values
        vendor = data["vendor_stk_no"].strip() or "-"
        pack_units = f"{data['pack'].strip()} {data['units'].strip()}".strip() or "-"

        vendor_size = fit_text(c, vendor, "Helvetica", 48, 18, (w / 2) - pad)
        pack_size = fit_text(c, pack_units, "Helvetica", 48, 18, (w / 2) - pad)

        c.setFont("Helvetica", vendor_size)
        c.drawString(left_x, top_y - 0.6 * inch, vendor)

        c.setFont("Helvetica", pack_size)
        c.drawRightString(right_x, top_y - 0.6 * inch, pack_units)

        # Description section
        desc_title_y = top_y - 1.7 * inch
        c.setFont("Helvetica", 16)
        c.drawCentredString(x + w / 2, desc_title_y, "DESCRIPTION")

        description = data["description"].strip() or "-"
        desc_max_width = w - (pad * 2)
        desc_font = fit_text(c, description, "Helvetica-Bold", 28, 12, desc_max_width)
        c.setFont("Helvetica-Bold", desc_font)
        c.drawCentredString(x + w / 2, desc_title_y - 0.45 * inch, description)

        # Color / size row
        row_title_y = desc_title_y - 1.25 * inch
        c.setFont("Helvetica", 16)
        c.drawString(left_x, row_title_y, "COLOR")
        c.drawRightString(right_x, row_title_y, "SIZE, STYLE")

        color = data["color"].strip() or "-"
        size_style = data["size"].strip() or "-"

        color_font = fit_text(c, color, "Helvetica", 42, 14, (w / 2) - pad)
        size_font = fit_text(c, size_style, "Helvetica", 42, 14, (w / 2) - pad)

        c.setFont("Helvetica", color_font)
        c.drawString(left_x, row_title_y - 0.55 * inch, color)

        c.setFont("Helvetica", size_font)
        c.drawRightString(right_x, row_title_y - 0.55 * inch, size_style)

        # Divider line
        divider_y = y + 2.35 * inch
        c.setLineWidth(5)
        c.line(left_x, divider_y, right_x, divider_y)

        # Barcode box
        box_margin = 0.6 * inch
        box_w = w - (box_margin * 2)
        box_h = 1.55 * inch
        box_x = x + (w - box_w) / 2
        box_y = divider_y - 1.8 * inch

        c.setFillColor(white)
        c.setStrokeColor(black)
        c.setLineWidth(10)
        c.rect(box_x, box_y, box_w, box_h, stroke=1, fill=1)
        c.setFillColor(black)

        barcode_value = normalize_gtin_for_ean13(data["gtin"])
        barcode = eanbc.Ean13BarcodeWidget(barcode_value)
        bounds = barcode.getBounds()
        b_width = bounds[2] - bounds[0]
        b_height = bounds[3] - bounds[1]

        target_w = box_w - 0.45 * inch
        target_h = box_h - 0.45 * inch
        scale_x = target_w / b_width
        scale_y = target_h / b_height
        scale = min(scale_x, scale_y)

        draw_x = box_x + (box_w - (b_width * scale)) / 2
        draw_y = box_y + (box_h - (b_height * scale)) / 2

        c.saveState()
        c.translate(draw_x, draw_y)
        c.scale(scale, scale)
        barcode.drawOn(c, 0, 0)
        c.restoreState()

        c.showPage()
        c.save()


# -----------------------------
# UI
# -----------------------------
class CartonLabelApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("700x520")
        self.root.minsize(700, 520)

        self.vars = {
            "vendor_stk_no": tk.StringVar(),
            "pack": tk.StringVar(),
            "units": tk.StringVar(),
            "description": tk.StringVar(),
            "color": tk.StringVar(),
            "size": tk.StringVar(),
            "gtin": tk.StringVar(),
        }

        self.last_pdf_path = None

        self.build_ui()

    def build_ui(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="Carton Label Generator", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        fields = [
            ("Vendor STK NO.", "vendor_stk_no"),
            ("PACK", "pack"),
            ("UNITS", "units"),
            ("DESCRIPTION", "description"),
            ("COLOR", "color"),
            ("SIZE", "size"),
            ("GTIN", "gtin"),
        ]

        for idx, (label_text, key) in enumerate(fields, start=1):
            ttk.Label(frame, text=label_text).grid(row=idx, column=0, sticky="w", padx=(0, 14), pady=8)
            entry = ttk.Entry(frame, textvariable=self.vars[key], width=55)
            entry.grid(row=idx, column=1, sticky="ew", pady=8)

        frame.columnconfigure(1, weight=1)

        note = (
            "Barcode rule: enter a valid 13-digit GTIN, or a 14-digit GTIN that starts with 0.\n"
            "The app will convert GTIN-14 to EAN-13 when needed."
        )
        ttk.Label(frame, text=note, foreground="#555555").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(12, 18)
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=9, column=0, columnspan=2, sticky="w")

        ttk.Button(button_row, text="Preview PDF", command=self.preview_pdf).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Save PDF", command=self.save_pdf).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Print", command=self.print_pdf).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Clear", command=self.clear_form).pack(side="left")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, foreground="#1f4f82").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(18, 0)
        )

    def collect_data(self) -> dict:
        data = {key: var.get() for key, var in self.vars.items()}

        required = [
            ("vendor_stk_no", "Vendor STK NO."),
            ("pack", "PACK"),
            ("units", "UNITS"),
            ("description", "DESCRIPTION"),
            ("color", "COLOR"),
            ("size", "SIZE"),
            ("gtin", "GTIN"),
        ]

        missing = [label for key, label in required if not data[key].strip()]
        if missing:
            raise ValueError("Please complete all fields: " + ", ".join(missing))

        normalize_gtin_for_ean13(data["gtin"])
        return data

    def generate_temp_pdf(self) -> str:
        data = self.collect_data()
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, PDF_FILENAME)
        builder = LabelPDFBuilder(pdf_path)
        builder.build(data)
        self.last_pdf_path = pdf_path
        self.status_var.set(f"PDF generated: {pdf_path}")
        return pdf_path

    def preview_pdf(self):
        try:
            pdf_path = self.generate_temp_pdf()
            os.startfile(pdf_path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.status_var.set("Error generating preview")

    def save_pdf(self):
        try:
            data = self.collect_data()
            filename = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', data['vendor_stk_no'].strip()) or 'carton_label'}.pdf"
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=filename,
                title="Save carton label PDF",
            )
            if not path:
                return

            builder = LabelPDFBuilder(path)
            builder.build(data)
            self.last_pdf_path = path
            self.status_var.set(f"Saved: {path}")
            messagebox.showinfo(APP_TITLE, f"Label saved successfully:\n{path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.status_var.set("Error saving PDF")

    def print_pdf(self):
        try:
            pdf_path = self.generate_temp_pdf()
            os.startfile(pdf_path, "print")
            self.status_var.set("Print command sent to Windows")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            self.status_var.set("Error printing PDF")

    def clear_form(self):
        for var in self.vars.values():
            var.set("")
        self.status_var.set("Form cleared")


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = CartonLabelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

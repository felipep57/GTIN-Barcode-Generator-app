import os
import re
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import createBarcodeDrawing
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


def gtin14_check_digit_ok(gtin14: str) -> bool:
    if not re.fullmatch(r"\d{14}", gtin14):
        return False

    digits = [int(d) for d in gtin14]
    check = digits[-1]
    body = digits[:-1]

    total = 0
    for idx, digit in enumerate(body):
        total += digit * (3 if idx % 2 == 0 else 1)

    calc = (10 - (total % 10)) % 10
    return calc == check


def normalize_gtin_for_itf14(gtin: str) -> str:
    raw = digits_only(gtin)

    if len(raw) == 14 and gtin14_check_digit_ok(raw):
        return raw

    raise ValueError(
        "GTIN must be a valid 14-digit GTIN for ITF-14."
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
        self.page_width = 6.0 * inch
        self.page_height = 4.0 * inch
        self.margin = 0.35 * inch
        self.label_x = self.margin
        self.label_y = self.margin
        self.label_w = self.page_width - (self.margin * 2)
        self.label_h = self.page_height - (self.margin * 2)

    def build(self, data: dict):
        c = canvas.Canvas(self.pdf_path, pagesize=(self.page_width, self.page_height))
        c.setTitle("Carton Label")

        page_w = self.page_width
        page_h = self.page_height

        def y_from_bottom_of_word(bottom_from_top: float, font_size: float) -> float:
            return page_h - bottom_from_top + (font_size * 0.20)

        c.setFillColor(black)

        # Top row headings (template-based coordinates)
        heading_size = 9.95
        heading_y = y_from_bottom_of_word(36.9, heading_size)
        c.setFont("Helvetica", heading_size)
        c.drawString(36.2, heading_y, "VENDOR STK NO.")
        c.drawString(324.4, heading_y, "PACK, UNITS")

        # Top row values (template-based coordinates)
        vendor = data["vendor_stk_no"].strip() or "-"
        pack_units = f"{data['pack'].strip()} {data['units'].strip()}".strip() or "-"

        vendor_size = fit_text(c, vendor, "Helvetica", 28, 20, 270)
        pack_size = fit_text(c, pack_units, "Helvetica", 28, 20, 80)
        top_value_baseline = y_from_bottom_of_word(71.5, 28.07)

        c.setFont("Helvetica", vendor_size)
        c.drawString(36.2, top_value_baseline, vendor)

        c.setFont("Helvetica", pack_size)
        c.drawRightString(404.9, top_value_baseline, pack_units)

        # Description section (template-based coordinates)
        desc_heading_size = 9.95
        desc_heading_y = y_from_bottom_of_word(83.4, desc_heading_size)
        c.setFont("Helvetica", desc_heading_size)
        c.drawCentredString(page_w / 2, desc_heading_y, "DESCRIPTION")

        description = data["description"].strip() or "-"
        desc_font = fit_text(c, description, "Helvetica-Bold", 18, 12, 360)
        desc_baseline = y_from_bottom_of_word(106.0, 18.11)
        c.setFont("Helvetica-Bold", desc_font)
        c.drawString(36.2, desc_baseline, description)

        # Color / size row (template-based coordinates)
        row_heading_size = 9.95
        row_heading_y = y_from_bottom_of_word(117.9, row_heading_size)
        c.setFont("Helvetica", row_heading_size)
        c.drawString(36.2, row_heading_y, "COLOR")
        c.drawString(324.4, row_heading_y, "SIZE, STYLE")

        color = data["color"].strip() or "-"
        size_style = data["size"].strip() or "-"

        color_font = fit_text(c, color, "Helvetica", 24, 16, 250)
        size_font = fit_text(c, size_style, "Helvetica", 24, 16, 80)
        row_value_baseline = y_from_bottom_of_word(147.4, 24.14)

        c.setFont("Helvetica", color_font)
        c.drawString(36.2, row_value_baseline, color)

        c.setFont("Helvetica", size_font)
        c.drawRightString(395.8, row_value_baseline, size_style)

        # Divider line (template-based coordinates)
        divider_y = page_h - 148.44
        c.setLineWidth(4.5)
        c.line(0, divider_y, page_w, divider_y)

        barcode_value = normalize_gtin_for_itf14(data["gtin"])
        barcode = createBarcodeDrawing("I2of5", value=barcode_value)
        b_width = barcode.width
        b_height = barcode.height

        # Barcode area from template object bounds
        target_x = 41.25
        target_y = 6.0
        target_w = 349.2
        target_h = 119.25

        scale_x = target_w / b_width
        scale_y = target_h / b_height
        scale = min(scale_x, scale_y)

        draw_x = target_x + (target_w - (b_width * scale)) / 2
        draw_y = target_y + (target_h - (b_height * scale)) / 2

        c.saveState()
        c.translate(draw_x, draw_y)
        c.scale(scale, scale)
        renderPDF.draw(barcode, c, 0, 0)
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
            "Barcode rule: enter a valid 14-digit GTIN for ITF-14.\n"
            "13-digit GTIN input is not accepted."
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

        normalize_gtin_for_itf14(data["gtin"])
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

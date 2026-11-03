import os
import uuid
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUTPUT_DIR = "generated_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACCENT = "E6394B"
LIGHT_ROW = "F7F7F9"
BORDER_COLOR = "D9D9DE"

THIN_BORDER = Border(
    left=Side(style="thin", color=BORDER_COLOR),
    right=Side(style="thin", color=BORDER_COLOR),
    top=Side(style="thin", color=BORDER_COLOR),
    bottom=Side(style="thin", color=BORDER_COLOR),
)

CURRENCY_HINTS = ("price", "cost", "value", "amount", "total", "revenue", "expense", "income", "salary", "budget")


def build_xlsx(sheet_name, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_name or "Sheet1")[:31]

    n_cols = max(len(headers), 1)

    # title block
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    title_cell = ws.cell(row=1, column=1, value=sheet_name or "Untitled Sheet")
    title_cell.font = Font(bold=True, size=14, color=ACCENT)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    date_cell = ws.cell(row=2, column=1, value=datetime.now().strftime("%B %d, %Y"))
    date_cell.font = Font(size=9, italic=True, color="777777")

    header_row = 4

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=ACCENT, end_color=ACCENT, fill_type="solid")
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = THIN_BORDER

    currency_cols = {
        col_idx for col_idx, h in enumerate(headers, 1)
        if any(hint in str(h).lower() for hint in CURRENCY_HINTS)
    }

    for r_offset, row in enumerate(rows):
        row_idx = header_row + 1 + r_offset
        row_fill = PatternFill(start_color=LIGHT_ROW, end_color=LIGHT_ROW, fill_type="solid") if r_offset % 2 == 1 else None

        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = THIN_BORDER
            if row_fill:
                cell.fill = row_fill
            if col_idx in currency_cols and isinstance(value, (int, float)):
                cell.number_format = '"$"#,##0.00'

    for col_idx in range(1, n_cols + 1):
        col_letter = get_column_letter(col_idx)
        max_len = len(str(headers[col_idx - 1])) if col_idx - 1 < len(headers) else 8
        for row in rows:
            if col_idx - 1 < len(row) and row[col_idx - 1] is not None:
                max_len = max(max_len, len(str(row[col_idx - 1])))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 45)

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(n_cols)}{header_row}"

    filename = f"{uuid.uuid4().hex}.xlsx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    wb.save(filepath)
    return filename
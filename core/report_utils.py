# core/report_utils.py
import io
import datetime as dt
from django.http import HttpResponse
from django.utils.timezone import make_aware
from django.db.models import Q
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def year_month_week_range(year=None, month=None, week=None):
    """
    Returns (start_datetime, end_datetime) or (None, None)
    - year only => whole year
    - year+month => whole month
    - year+week => ISO week range
    - year+month+week => week is applied after month filter normally (optional)
    """
    if not year:
        return None, None

    if year and week:
        # ISO week: Monday start
        # week 1..53
        d = dt.date.fromisocalendar(year, week, 1)
        start = dt.datetime.combine(d, dt.time.min)
        end = start + dt.timedelta(days=7)
        return make_aware(start), make_aware(end)

    if year and month:
        start = dt.datetime(year, month, 1)
        if month == 12:
            end = dt.datetime(year + 1, 1, 1)
        else:
            end = dt.datetime(year, month + 1, 1)
        return make_aware(start), make_aware(end)

    # year only
    start = make_aware(dt.datetime(year, 1, 1))
    end = make_aware(dt.datetime(year + 1, 1, 1))
    return start, end


def export_xlsx(filename: str, columns: list[str], rows: list[list]):
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    ws.append(columns)
    for r in rows:
        ws.append(r)

    buff = io.BytesIO()
    wb.save(buff)
    buff.seek(0)

    resp = HttpResponse(
        buff.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return resp


def export_pdf(filename: str, title: str, columns: list[str], rows: list[list]):
    buff = io.BytesIO()
    c = canvas.Canvas(buff, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, title)
    y -= 30

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, " | ".join(columns))
    y -= 18

    c.setFont("Helvetica", 9)
    for r in rows:
        line = " | ".join([str(x) if x is not None else "" for x in r])
        if y < 60:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 9)
        c.drawString(40, y, line[:150])  # keep line short
        y -= 14

    c.save()
    buff.seek(0)

    resp = HttpResponse(buff.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
    return resp

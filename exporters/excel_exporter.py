"""
GIKI Scheduler v2 - Timetable Exporters
========================================
Export to:
  - Excel (.xlsx) — full timetable grid, faculty-filtered, color-coded
  - PDF (text-based)
  - Text file

Can export all faculties or a specific faculty.
"""

from __future__ import annotations
import os
from core.models import Timetable, DayOfWeek


# Day order and display names
DAYS = [d for d in DayOfWeek]
DAY_NAMES = [d.value for d in DAYS]

# Official GIKI time slots in order
SLOT_TIMES = [
    ("0800", "8:00-8:50"),
    ("0900", "9:00-9:50"),
    ("1030", "10:30-11:20"),
    ("1130", "11:30-12:20"),
    ("1230", "12:30-1:20"),
    ("1430", "2:30-3:20"),
    ("1530", "3:30-4:20"),
    ("1630", "4:30-5:20"),
]

FRIDAY_SLOT_TIMES = [
    ("0800", "8:00-8:50"),
    ("0900", "9:00-9:50"),
    ("1000", "10:00-10:50"),
    ("1100", "11:00-11:50"),
    ("1200", "12:00-12:50"),
    ("1430", "2:30-3:20"),
    ("1530", "3:30-4:20"),
    ("1630", "4:30-5:20"),
]

FACULTY_COLORS = {
    "FCSE": "D6E4F0",
    "FEE":  "D5F5E3",
    "FME":  "FCF3CF",
    "FChE": "FAD7A0",
    "FMCE": "E8DAEF",
    "FCvE": "D1F2EB",
    "FBS":  "FDEBD0",
    "SMgS": "FDEDEC",
}


def _build_grid(timetable: Timetable, slots: dict, courses: dict,
                faculty_filter: str = None) -> dict:
    """
    Build a day x timeslot grid.
    Returns: {(day_name, time_key): [cell_text, ...]}
    """
    grid = {}

    for sess in timetable.sessions:
        if faculty_filter and sess.faculty != faculty_filter:
            continue

        slot = slots.get(sess.slot_id)
        if not slot:
            continue

        day = slot.day.value
        time_key = slot.start_str.replace(":", "")  # "0800"

        cell = f"{sess.course_code}\n{sess.section_uid.split('-')[-1]}\n{sess.room_id}"
        key = (day, time_key)
        grid.setdefault(key, []).append(cell)

    return grid


def export_excel(timetable: Timetable, slots: dict, courses: dict,
                  output_path: str, faculty_filter: str = None,
                  title: str = "GIKI University - Spring 2026 Timetable"):
    """
    Export timetable to Excel with colored cells by faculty.
    Mimics the official GIKI timetable format.
    """
    try:
        import xlsxwriter
    except ImportError:
        raise ImportError("xlsxwriter required: pip install xlsxwriter")

    workbook = xlsxwriter.Workbook(output_path)

    # ── Formats ──────────────────────────────────────────────────────
    title_fmt = workbook.add_format({
        'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#1F3864', 'font_color': 'white',
        'border': 1, 'text_wrap': True
    })
    header_fmt = workbook.add_format({
        'bold': True, 'font_size': 9, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#2E4E8C', 'font_color': 'white',
        'border': 1, 'text_wrap': True
    })
    day_fmt = workbook.add_format({
        'bold': True, 'font_size': 9, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#D6E4F0', 'border': 1, 'text_wrap': True
    })
    empty_fmt = workbook.add_format({
        'bg_color': '#FFFFFF', 'border': 1
    })

    # Faculty-specific formats
    fac_fmts = {}
    for fac, color in FACULTY_COLORS.items():
        fac_fmts[fac] = workbook.add_format({
            'font_size': 7, 'align': 'center', 'valign': 'vcenter',
            'bg_color': f'#{color}', 'border': 1, 'text_wrap': True
        })
    default_cell_fmt = workbook.add_format({
        'font_size': 7, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#F0F0F0', 'border': 1, 'text_wrap': True
    })

    # ── Build per-faculty sheets or one combined sheet ────────────────
    faculties_to_export = []
    if faculty_filter:
        faculties_to_export = [faculty_filter]
    else:
        # One sheet per faculty + one "All" sheet
        all_faculties = sorted(set(s.faculty for s in timetable.sessions if s.faculty))
        faculties_to_export = ["ALL"] + all_faculties

    for fac in faculties_to_export:
        filter_fac = None if fac == "ALL" else fac
        sheet_name = fac[:31]  # Excel limit
        ws = workbook.add_worksheet(sheet_name)

        # Title row
        ws.merge_range(0, 0, 1, 9, title, title_fmt)
        if filter_fac:
            ws.merge_range(2, 0, 2, 9, f"Faculty: {filter_fac}", header_fmt)
            data_start = 3
        else:
            data_start = 2

        # Set column widths
        ws.set_column(0, 0, 10)  # Day column
        ws.set_column(1, 8, 13)  # Time slot columns

        # Time slot headers
        ws.write(data_start, 0, "Day / Time", header_fmt)
        day_abbr = {
            DayOfWeek.MONDAY: "MON", DayOfWeek.TUESDAY: "TUE",
            DayOfWeek.WEDNESDAY: "WED", DayOfWeek.THURSDAY: "THU",
            DayOfWeek.FRIDAY: "FRI"
        }

        for col, (tkey, tlabel) in enumerate(SLOT_TIMES, 1):
            ws.write(data_start, col, tlabel, header_fmt)

        # Build grid for this faculty
        grid = _build_grid(timetable, slots, courses, filter_fac)

        # Fill rows
        for row_idx, day in enumerate(DAYS):
            row = data_start + 1 + row_idx
            ws.write(row, 0, day.value, day_fmt)
            ws.set_row(row, 45)

            slot_times = FRIDAY_SLOT_TIMES if day == DayOfWeek.FRIDAY else SLOT_TIMES

            for col, (tkey, _) in enumerate(slot_times, 1):
                key = (day.value, tkey)
                cells = grid.get(key, [])
                if cells:
                    # Find faculty for color
                    cell_sessions = [s for s in timetable.sessions
                                     if slots.get(s.slot_id)
                                     and slots[s.slot_id].day == day
                                     and slots[s.slot_id].start_str.replace(":", "") == tkey
                                     and (not filter_fac or s.faculty == filter_fac)]
                    if cell_sessions:
                        fac_code = cell_sessions[0].faculty
                        fmt = fac_fmts.get(fac_code, default_cell_fmt)
                    else:
                        fmt = default_cell_fmt
                    ws.write(row, col, "\n".join(cells), fmt)
                else:
                    ws.write(row, col, "", empty_fmt)

        # Legend
        legend_row = data_start + len(DAYS) + 2
        ws.write(legend_row, 0, "Faculty Legend:", header_fmt)
        for li, (fac_code, color) in enumerate(FACULTY_COLORS.items()):
            leg_fmt = workbook.add_format({'bg_color': f'#{color}', 'border': 1,
                                            'font_size': 8, 'bold': True})
            ws.write(legend_row + 1 + li // 4, (li % 4) * 2, fac_code, leg_fmt)
            ws.write(legend_row + 1 + li // 4, (li % 4) * 2 + 1,
                     {"FCSE":"CS/CE/AI/CY/DS/SE","FEE":"EE","FME":"ME",
                      "FChE":"CH","FMCE":"MM/MTE","FCvE":"CV",
                      "FBS":"MT/ES/PH","SMgS":"HM/MS/AF"}.get(fac_code,""),
                     workbook.add_format({'font_size': 7, 'border': 1}))

    workbook.close()
    return output_path


def export_text(timetable: Timetable, slots: dict,
                output_path: str, faculty_filter: str = None) -> str:
    """Export to plain text file."""
    lines = []
    lines.append("GHULAM ISHAQ KHAN INSTITUTE OF ENGINEERING SCIENCES AND TECHNOLOGY")
    lines.append("TIMETABLE - SPRING 2026")
    if faculty_filter:
        lines.append(f"Faculty: {faculty_filter}")
    lines.append("=" * 90)
    lines.append(f"{'Section':<20} {'Course':<10} {'Type':<8} {'Day':<12} {'Time':<14} {'Room':<14} {'Teacher'}")
    lines.append("-" * 90)

    day_order = {d: i for i, d in enumerate(DayOfWeek)}
    sessions = sorted(
        [s for s in timetable.sessions if not faculty_filter or s.faculty == faculty_filter],
        key=lambda s: (
            day_order.get(slots[s.slot_id].day if s.slot_id in slots else DayOfWeek.MONDAY, 0),
            slots[s.slot_id].start_min if s.slot_id in slots else 0,
        )
    )

    for s in sessions:
        slot = slots.get(s.slot_id)
        time_str = f"{slot.start_str}-{slot.end_str}" if slot else "?"
        day_str  = slot.day.value if slot else "?"
        stype    = "Lab" if s.session_type.value == "Lab" else "Lecture"
        lines.append(
            f"{s.section_uid:<20} {s.course_code:<10} {stype:<8} "
            f"{day_str:<12} {time_str:<14} {s.room_id:<14} {s.teacher_id}"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


def export_buildings_table_excel(output_path: str):
    """Export buildings and rooms reference table to Excel."""
    try:
        import xlsxwriter
    except ImportError:
        raise ImportError("xlsxwriter required")

    from config.buildings import get_all_rooms_table, BUILDINGS

    workbook = xlsxwriter.Workbook(output_path)

    # Buildings sheet
    ws_b = workbook.add_worksheet("Buildings")
    hdr = workbook.add_format({'bold': True, 'bg_color': '#1F3864', 'font_color': 'white',
                                'border': 1, 'font_size': 10})
    cell = workbook.add_format({'border': 1, 'font_size': 9, 'text_wrap': True})

    headers = ["Building ID", "Full Name", "Short Name", "Primary Faculties"]
    for c, h in enumerate(headers):
        ws_b.write(0, c, h, hdr)
    ws_b.set_column(0, 0, 12)
    ws_b.set_column(1, 1, 40)
    ws_b.set_column(2, 2, 15)
    ws_b.set_column(3, 3, 30)

    for r, (bid, bld) in enumerate(sorted(BUILDINGS.items()), 1):
        ws_b.write(r, 0, bid, cell)
        ws_b.write(r, 1, bld.name, cell)
        ws_b.write(r, 2, bld.short_name, cell)
        ws_b.write(r, 3, ", ".join(bld.faculty_home), cell)

    # Rooms sheet
    ws_r = workbook.add_worksheet("Rooms")
    r_headers = ["Room ID", "Building", "Capacity", "Type", "Priority Faculties", "Notes"]
    for c, h in enumerate(r_headers):
        ws_r.write(0, c, h, hdr)
    ws_r.set_column(0, 0, 14)
    ws_r.set_column(1, 1, 35)
    ws_r.set_column(2, 2, 10)
    ws_r.set_column(3, 3, 18)
    ws_r.set_column(4, 4, 25)
    ws_r.set_column(5, 5, 40)

    rows_data = get_all_rooms_table()
    for r, row in enumerate(rows_data, 1):
        # Color labs differently
        is_lab = "Lab" in row["type"]
        row_fmt = workbook.add_format({
            'border': 1, 'font_size': 8, 'text_wrap': True,
            'bg_color': '#FFF0E0' if is_lab else '#FFFFFF'
        })
        ws_r.write(r, 0, row["room_id"], row_fmt)
        ws_r.write(r, 1, row["building"], row_fmt)
        ws_r.write(r, 2, row["capacity"], row_fmt)
        ws_r.write(r, 3, row["type"], row_fmt)
        ws_r.write(r, 4, row["priority_for"], row_fmt)
        ws_r.write(r, 5, row["notes"], row_fmt)

    workbook.close()
    return output_path

"""
PDF Timetable Exporter
Exports: faculty building view OR section-specific timetable.
Uses reportlab.
"""
from __future__ import annotations
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from core.models import DayOfWeek, SessionType

DAYS = list(DayOfWeek)
NAVY  = colors.HexColor("#1F3864")
LIGHT = colors.HexColor("#D6E4F0")
WHITE = colors.white
GREY  = colors.HexColor("#F0F4FB")

FAC_COLORS = {
    "FCSE": colors.HexColor("#D6E4F0"),
    "FEE":  colors.HexColor("#D5F5E3"),
    "FME":  colors.HexColor("#FCF3CF"),
    "FChE": colors.HexColor("#FAD7A0"),
    "FMCE": colors.HexColor("#E8DAEF"),
    "FCvE": colors.HexColor("#D1F2EB"),
    "FBS":  colors.HexColor("#FDEBD0"),
    "SMgS": colors.HexColor("#FDEDEC"),
}


def _get_lecture_times(slots: dict) -> list:
    """Sorted unique (start_min) for lecture slots."""
    return sorted(set(s.start_min for s in slots.values() if s.duration == 50))


def _fmt_time(sm: int) -> str:
    h, m = divmod(sm, 60)
    eh, em = divmod(sm+50, 60)
    return f"{h:02d}:{m:02d}\n{eh:02d}:{em:02d}"


def export_faculty_pdf(timetable, slots: dict, sections: dict,
                        output_path: str, faculty_filter: str = None,
                        show_teacher: bool = True, title: str = None):
    """Export building/faculty timetable as PDF grid."""
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4),
                             leftMargin=1*cm, rightMargin=1*cm,
                             topMargin=1.5*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", fontSize=14, alignment=TA_CENTER,
                                  textColor=NAVY, fontName="Helvetica-Bold")
    cell_style = ParagraphStyle("cell", fontSize=6, alignment=TA_CENTER,
                                  fontName="Helvetica", leading=8)
    story = []

    heading = title or f"GIKI Timetable — {faculty_filter or 'All Faculties'}"
    story.append(Paragraph(heading, title_style))
    story.append(Spacer(1, 0.3*cm))

    time_mins = _get_lecture_times(slots)
    if not time_mins:
        return

    # Build cell map
    sessions = [s for s in timetable.sessions
                if not faculty_filter or s.faculty == faculty_filter]
    cell_map = {}
    for sess in sessions:
        sl = slots.get(sess.slot_id)
        if not sl or sl.duration != 50: continue
        key = (sl.day, sl.start_min)
        cell_map.setdefault(key, []).append(sess)

    # Build table data
    col_width = (27*cm) / (len(time_mins) + 1)
    header_row = ["Day / Time"] + [_fmt_time(sm) for sm in time_mins]
    data = [header_row]

    for day in DAYS:
        row = [day.value[:3]]
        for sm in time_mins:
            cell_sessions = cell_map.get((day, sm), [])
            if cell_sessions:
                lines = []
                for cs in cell_sessions[:3]:
                    sec = sections.get(cs.section_uid)
                    yr = f"Y{sec.batch_year}" if sec and sec.batch_year else ""
                    sid = cs.section_uid.split("-")[-1]
                    line = f"{cs.course_code}\n{sid}{yr}"
                    if show_teacher:
                        line += f"\n{cs.teacher_id[:14]}"
                    lines.append(line)
                if len(cell_sessions) > 3:
                    lines.append(f"+{len(cell_sessions)-3} more")
                row.append(Paragraph("\n---\n".join(lines), cell_style))
            else:
                row.append("")
        data.append(row)

    col_widths = [2.2*cm] + [col_width] * len(time_mins)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('TEXTCOLOR',  (0,0), (-1,0), WHITE),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 7),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [GREY, WHITE]),
        ('FONTSIZE',   (0,1), (-1,-1), 6),
        ('FONTNAME',   (0,1), (0,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (0,-1), LIGHT),
        ('ROWHEIGHT',  (0,1), (-1,-1), 1.2*cm),
    ])
    # Color faculty cells
    for ri, day in enumerate(DAYS, 1):
        for ci, sm in enumerate(time_mins, 1):
            cell_sessions = cell_map.get((day, sm), [])
            if cell_sessions:
                fac = cell_sessions[0].faculty
                bg = FAC_COLORS.get(fac, WHITE)
                style.add('BACKGROUND', (ci, ri), (ci, ri), bg)
    t.setStyle(style)
    story.append(t)
    doc.build(story)


def export_section_pdf(timetable, slots: dict, sections: dict, courses: dict,
                        output_path: str, section_uid: str, show_teacher: bool = True):
    """Export a single section's timetable as a clean PDF."""
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                             leftMargin=1.5*cm, rightMargin=1.5*cm,
                             topMargin=2*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("t", fontSize=14, alignment=TA_CENTER,
                               textColor=NAVY, fontName="Helvetica-Bold")
    sub_s = ParagraphStyle("s", fontSize=9, alignment=TA_CENTER,
                             fontName="Helvetica", textColor=colors.grey)
    cell_s = ParagraphStyle("c", fontSize=8, alignment=TA_CENTER,
                              fontName="Helvetica", leading=10)
    story = []

    sec = sections.get(section_uid)
    batch_label = {1:"Year 1 (Intake 2025)",2:"Year 2 (Intake 2024)",
                   3:"Year 3 (Intake 2023)",4:"Year 4 (Intake 2022)"}.get(
                    sec.batch_year if sec else 0, "")
    story.append(Paragraph(f"GIKI University — Section Timetable", title_s))
    story.append(Paragraph(f"Section: {section_uid}  |  {batch_label}  |  Faculty: {sec.faculty if sec else ''}", sub_s))
    story.append(Spacer(1, 0.5*cm))

    sess_list = timetable.get_sessions_by_section(section_uid)
    day_order = {d:i for i,d in enumerate(DAYS)}
    sess_list = sorted(sess_list, key=lambda s: (
        day_order.get(slots[s.slot_id].day if s.slot_id in slots else DayOfWeek.MONDAY, 0),
        slots[s.slot_id].start_min if s.slot_id in slots else 0))

    time_mins = _get_lecture_times(slots)
    cell_map = {}
    for sess in sess_list:
        sl = slots.get(sess.slot_id)
        if sl: cell_map[(sl.day, sl.start_min)] = sess

    col_width = 15*cm / (len(time_mins) + 1) if time_mins else 2*cm
    header_row = ["Day"] + [_fmt_time(sm) for sm in time_mins]
    data = [header_row]
    for day in DAYS:
        row = [day.value[:3]]
        for sm in time_mins:
            sess = cell_map.get((day, sm))
            if sess:
                sl = slots.get(sess.slot_id)
                crs = courses.get(sess.course_code)
                text = f"{sess.course_code}\n{sess.room_id}"
                if show_teacher:
                    text += f"\n{sess.teacher_id[:16]}"
                row.append(Paragraph(text, cell_s))
            else:
                row.append("")
        data.append(row)

    col_widths = [1.8*cm] + [col_width]*len(time_mins)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('TEXTCOLOR',  (0,0), (-1,0), WHITE),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 8),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [GREY, WHITE]),
        ('FONTSIZE',   (0,1), (-1,-1), 7),
        ('FONTNAME',   (0,1), (0,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (0,-1), LIGHT),
        ('ROWHEIGHT',  (0,1), (-1,-1), 1.4*cm),
    ]))
    story.append(t)

    # Session list below
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Session Details", ParagraphStyle("h",fontSize=10,
                             fontName="Helvetica-Bold",textColor=NAVY)))
    story.append(Spacer(1,0.2*cm))
    detail_data = [["Course","Type","Day","Time","Room","Teacher"]]
    for sess in sess_list:
        sl = slots.get(sess.slot_id)
        ts = f"{sl.start_str}-{sl.end_str}" if sl else "?"
        ds = sl.day.value if sl else "?"
        detail_data.append([sess.course_code, sess.session_type.value[:3],
                              ds, ts, sess.room_id, sess.teacher_id[:20]])
    dt = Table(detail_data, colWidths=[3*cm,1.5*cm,2.5*cm,2.5*cm,3*cm,5*cm])
    dt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[GREY,WHITE]),
    ]))
    story.append(dt)
    doc.build(story)

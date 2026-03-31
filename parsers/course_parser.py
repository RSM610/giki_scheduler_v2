"""
GIKI Scheduler v2 - Course List Parser
=======================================
Parses course lists from Excel (.xlsx), CSV (.csv), and PDF (.pdf) formats.
Handles all GIKI sheet formats observed in the provided spreadsheet.

Outputs a normalized list of CourseEntry objects.
"""

from __future__ import annotations
import re
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CourseEntry:
    """Normalized course entry from any input format."""
    course_code:  str
    title:        str
    credit_hours: int          # total contact hours (lectures only; labs counted separately)
    instructor:   str
    section:      str
    faculty:      str          # inferred from course code
    semester:     int = 0
    is_lab:       bool = False
    for_program:  str = ""     # "BME", "FCSE", etc.
    num_students: int = 30
    raw_ch:       str = ""     # original CH string (e.g. "1-3-2")

    @property
    def uid(self) -> str:
        return f"{self.course_code}-{self.section}"


def _clean(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _parse_credit_hours(ch_val) -> tuple[int, str]:
    """
    Parse credit hours from various formats:
      3       -> 3
      "3-0"   -> 3
      "1-3-2" -> 2 (last number = contact hours for scheduling)
      "2CH"   -> 2
      "3 CH"  -> 3
    Returns (int_hours, raw_string).
    """
    raw = _clean(ch_val)
    if not raw:
        return 2, raw
    # Remove non-numeric fluff
    raw_clean = raw.upper().replace("CH", "").strip()
    # Handle "L-T-P" format: take last non-zero field or sum
    parts = re.split(r'[-/]', raw_clean)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        try:
            ints = [int(p) for p in parts if p.isdigit()]
            if ints:
                return ints[0], raw  # first = lecture hours for scheduling
        except ValueError:
            pass
    try:
        return int(float(raw_clean.split()[0])), raw
    except (ValueError, IndexError):
        return 2, raw


def _infer_faculty(course_code: str) -> str:
    """Infer faculty from course code prefix."""
    code = course_code.strip().upper()
    mapping = [
        (("CS","CE","AI","CY","DS","SE","IF"), "FCSE"),
        (("EE",),                               "FEE"),
        (("ME",),                               "FME"),
        (("CH",),                               "FChE"),
        (("MM","CME","MTE"),                    "FMCE"),
        (("CV",),                               "FCvE"),
        (("MT","ES","PH"),                      "FBS"),
        (("HM","MS","AF","EM","SC"),             "SMgS"),
    ]
    for prefixes, faculty in mapping:
        for p in prefixes:
            if code.startswith(p):
                return faculty
    return "FCSE"


# ══════════════════════════════════════════════════════════════════════
# EXCEL PARSER
# ══════════════════════════════════════════════════════════════════════

def parse_excel(filepath: str) -> list[CourseEntry]:
    """
    Parse GIKI course list Excel file. Handles all sheet formats.
    Supports .xlsx, .xlsm, .xls, .ods.
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("openpyxl required: pip install openpyxl")

    entries = []
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".xls",):
        import pandas as pd
        xl = pd.ExcelFile(filepath, engine="xlrd")
        sheet_names = xl.sheet_names
    else:
        wb = load_workbook(filepath, read_only=True)
        sheet_names = wb.sheetnames

    for sheet_name in sheet_names:
        if ext in (".xls",):
            import pandas as pd
            df = pd.read_excel(filepath, sheet_name=sheet_name, engine="xlrd", header=None)
            rows = [tuple(row) for _, row in df.iterrows()]
        else:
            wb2 = load_workbook(filepath, read_only=True)
            ws = wb2[sheet_name]
            rows = [tuple(r) for r in ws.iter_rows(values_only=True)]

        sheet_entries = _parse_sheet_rows(rows, sheet_name)
        entries.extend(sheet_entries)

    return entries


def _parse_sheet_rows(rows: list, sheet_name: str) -> list[CourseEntry]:
    """Parse rows from one Excel sheet. Handles multiple column layouts."""
    entries = []
    header_row = None
    col_map = {}

    # Detect header row (first row with "Code" or "Course Code" or "Course#")
    for i, row in enumerate(rows):
        vals = [_clean(v).lower() for v in row]
        if any("code" in v for v in vals) or any("course#" in v for v in vals):
            header_row = i
            for j, v in enumerate(vals):
                if "code" in v:      col_map["code"] = j
                if "title" in v:     col_map["title"] = j
                if "ch" in v and "credit" not in v and "hours" not in v: col_map.get("ch") or col_map.update({"ch": j})
                if "credit" in v:    col_map["ch"] = j
                if "instructor" in v or "instr" in v: col_map["instructor"] = j
                if "section" in v:   col_map["section"] = j
                if "for" in v or "program" in v: col_map["for"] = j
                if "sem" in v:       col_map["sem"] = j
                if "exp" in v or "student" in v: col_map["students"] = j
            break

    if header_row is None:
        # Try direct parsing (SMGS format with S.No, Course Code, Course Title...)
        for i, row in enumerate(rows):
            vals = [_clean(v) for v in row]
            if len(vals) >= 4 and any(re.match(r'^[A-Z]{2,3}\d{3}', v) for v in vals):
                header_row = i - 1
                # Guess columns by position
                # Format: (None, S.No, Code, Title, CH, Section, Instructor, For)
                if len(row) >= 8:
                    col_map = {"code": 2, "title": 3, "ch": 4, "section": 5, "instructor": 6, "for": 7}
                break

    if not col_map:
        return entries

    data_start = (header_row or 0) + 1

    for row in rows[data_start:]:
        if len(row) < 3:
            continue
        vals = [_clean(v) for v in row]
        if not any(vals):
            continue

        code = vals[col_map.get("code", 2)] if col_map.get("code", 2) < len(vals) else ""
        if not code or not re.match(r'^[A-Z]{1,3}\s*\d', code.upper()):
            continue  # skip non-course rows

        code = re.sub(r'\s+', '', code).upper()  # normalize CS 112 -> CS112
        title = vals[col_map.get("title", 3)] if col_map.get("title", 3) < len(vals) else ""
        ch_raw = vals[col_map.get("ch", 4)] if col_map.get("ch", 4) < len(vals) else "2"
        section = vals[col_map.get("section", 5)] if col_map.get("section", 5) < len(vals) else "A"
        instructor = vals[col_map.get("instructor", 6)] if col_map.get("instructor", 6) < len(vals) else ""
        for_prog = vals[col_map.get("for", 7)] if col_map.get("for", 7) < len(vals) else ""

        ch, raw_ch = _parse_credit_hours(ch_raw)
        is_lab = bool(re.search(r'\bL\b|Lab$|-L$', code, re.I))
        faculty = _infer_faculty(code)

        # Parse num_students from "for" field if it contains numbers
        num_students = 30
        student_match = re.search(r'=\s*(\d+)', for_prog)
        if student_match:
            num_students = int(student_match.group(1))

        if not section or section in ("None", ""):
            section = "A"

        entries.append(CourseEntry(
            course_code  = code,
            title        = title,
            credit_hours = ch,
            instructor   = instructor,
            section      = str(section),
            faculty      = faculty,
            is_lab       = is_lab,
            for_program  = for_prog,
            num_students = num_students,
            raw_ch       = raw_ch,
        ))

    return entries


# ══════════════════════════════════════════════════════════════════════
# CSV PARSER
# ══════════════════════════════════════════════════════════════════════

def parse_csv(filepath: str) -> list[CourseEntry]:
    """
    Parse GIKI course list CSV.
    Expected columns (flexible order): code, title, ch, instructor, section, for/program
    """
    import csv
    entries = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_lower = {k.lower().strip(): v for k, v in row.items()}
            code = _clean(row_lower.get("code") or row_lower.get("course code") or row_lower.get("course_code", ""))
            if not code or not re.match(r'^[A-Z]{1,3}\s*\d', code.upper()):
                continue
            code = re.sub(r'\s+', '', code).upper()
            title = _clean(row_lower.get("title") or row_lower.get("course title", ""))
            ch_raw = _clean(row_lower.get("ch") or row_lower.get("credit hours") or row_lower.get("credit_hours", "2"))
            section = _clean(row_lower.get("section", "A"))
            instructor = _clean(row_lower.get("instructor", ""))
            for_prog = _clean(row_lower.get("for") or row_lower.get("program", ""))

            ch, raw_ch = _parse_credit_hours(ch_raw)
            is_lab = bool(re.search(r'\bL\b|Lab$|-L$', code, re.I))
            faculty = _infer_faculty(code)

            entries.append(CourseEntry(
                course_code  = code,
                title        = title,
                credit_hours = ch,
                instructor   = instructor,
                section      = section or "A",
                faculty      = faculty,
                is_lab       = is_lab,
                for_program  = for_prog,
                raw_ch       = raw_ch,
            ))
    return entries


# ══════════════════════════════════════════════════════════════════════
# PDF PARSER
# ══════════════════════════════════════════════════════════════════════

def parse_pdf(filepath: str) -> list[CourseEntry]:
    """
    Parse course list from PDF.
    Uses pypdf text extraction then regex to find course entries.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf required: pip install pypdf")

    reader = PdfReader(filepath)
    full_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    entries = []
    # Pattern: CODE  Title  CH  Section  Instructor
    # Flexible regex for GIKI-style course lists
    pattern = re.compile(
        r'([A-Z]{2,3}\s*\d{3}(?:[A-Z]|L)?)\s+'  # course code
        r'([A-Za-z][^\d]{5,60?}?)\s+'            # title
        r'(\d+(?:-\d+)*(?:\s*CH)?)\s+'           # credit hours
        r'([A-Z\d+]+)\s+'                         # section
        r'([A-Za-z][^\n]{3,50})',                  # instructor
        re.MULTILINE
    )

    for match in pattern.finditer(full_text):
        code = re.sub(r'\s+', '', match.group(1)).upper()
        title = match.group(2).strip()
        ch_raw = match.group(3).strip()
        section = match.group(4).strip()
        instructor = match.group(5).strip()

        ch, raw_ch = _parse_credit_hours(ch_raw)
        is_lab = bool(re.search(r'\bL\b|Lab$|-L$', code, re.I))
        faculty = _infer_faculty(code)

        entries.append(CourseEntry(
            course_code  = code,
            title        = title,
            credit_hours = ch,
            instructor   = instructor,
            section      = section,
            faculty      = faculty,
            is_lab       = is_lab,
            raw_ch       = raw_ch,
        ))

    return entries


# ══════════════════════════════════════════════════════════════════════
# UNIVERSAL PARSER
# ══════════════════════════════════════════════════════════════════════

def parse_course_list(filepath: str) -> list[CourseEntry]:
    """
    Auto-detect format and parse course list.
    Supports: .xlsx, .xlsm, .xls, .ods, .csv, .tsv, .pdf
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls", ".ods"):
        return parse_excel(filepath)
    elif ext in (".csv", ".tsv"):
        return parse_csv(filepath)
    elif ext == ".pdf":
        return parse_pdf(filepath)
    else:
        raise ValueError(f"Unsupported format: {ext}. Use .xlsx, .csv, or .pdf")


def summarize_courses(entries: list[CourseEntry]) -> dict:
    """Print summary of parsed courses."""
    from collections import Counter
    by_faculty = Counter(e.faculty for e in entries)
    by_code = Counter(e.course_code for e in entries)
    return {
        "total":      len(entries),
        "by_faculty": dict(by_faculty),
        "unique_codes": len(by_code),
        "labs":        sum(1 for e in entries if e.is_lab),
    }

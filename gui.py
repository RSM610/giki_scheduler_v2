"""
GIKI University Timetable Scheduler — Python GUI
=================================================
Run:  python gui.py

Requirements (if tkinter is missing):
    Windows:  tkinter is bundled with Python — reinstall Python and check "tcl/tk"
    Ubuntu:   sudo apt install python3-tk
    macOS:    brew install python-tk

This GUI is self-contained. Place it in the same folder as the
giki_scheduler_v2 package, or update SCHEDULER_PATH below.
"""

import os
import sys
import threading
import time
import json
import importlib.util

# ── Locate the scheduler package ──────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULER_PATH = SCRIPT_DIR  # gui.py is inside giki_scheduler_v2/
sys.path.insert(0, SCHEDULER_PATH)

# ── Tkinter import with helpful error ─────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    from tkinter.font import Font
except ModuleNotFoundError:
    print("\n" + "="*60)
    print("  tkinter not found.")
    print("  Ubuntu/Debian:  sudo apt install python3-tk")
    print("  Windows:        Reinstall Python, check 'tcl/tk' option")
    print("  macOS:          brew install python-tk")
    print("="*60 + "\n")
    sys.exit(1)

# ── Scheduler imports ──────────────────────────────────────────────────
from core.models import (
    Timetable, Section, Course, Teacher,
    SessionType, DayOfWeek
)
from core.scheduler import GIKIScheduler, ConstraintEngine
from data.slots import build_giki_slots
from config.buildings import ROOMS, BUILDINGS, add_room, add_building, remove_room
from parsers.course_parser import parse_course_list, summarize_courses
from exporters.excel_exporter import (
    export_excel, export_text, export_buildings_table_excel
)

# ══════════════════════════════════════════════════════════════════════
# COLOURS  (professional dark blue + warm white palette, no emojis)
# ══════════════════════════════════════════════════════════════════════

C = {
    "bg":          "#F4F6F9",
    "sidebar":     "#1F3864",
    "sidebar_hover":"#2E4E8C",
    "sidebar_active":"#4A7FCB",
    "accent":      "#2E4E8C",
    "accent2":     "#4A7FCB",
    "white":       "#FFFFFF",
    "text":        "#1A1A2E",
    "text_light":  "#666688",
    "border":      "#D0D8E8",
    "success":     "#1B5E20",
    "warning":     "#E65100",
    "error":       "#8B0000",
    "row_even":    "#F0F4FB",
    "row_odd":     "#FFFFFF",
    "header_bg":   "#1F3864",
    "header_fg":   "#FFFFFF",
    "btn":         "#2E4E8C",
    "btn_hover":   "#4A7FCB",
    "btn_danger":  "#8B0000",
    "btn_success": "#1B5E20",
    "input_bg":    "#FFFFFF",
    "input_border":"#B0BED0",
    "tag_fcse":    "#D6E4F0",
    "tag_fee":     "#D5F5E3",
    "tag_fme":     "#FCF3CF",
    "tag_smes":    "#FDEDEC",
    "tag_fbs":     "#FDEBD0",
    "tag_fche":    "#FAD7A0",
    "tag_fmce":    "#E8DAEF",
    "tag_fcve":    "#D1F2EB",
}

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else (
    "SF Pro Text" if sys.platform == "darwin" else "DejaVu Sans"
)

DATA_FILE = os.path.join(SCRIPT_DIR, "giki_scheduler_state.json")


# ══════════════════════════════════════════════════════════════════════
# APPLICATION STATE  (shared between all GUI panels)
# ══════════════════════════════════════════════════════════════════════

class AppState:
    def __init__(self):
        self.slots    = build_giki_slots()
        self.rooms    = ROOMS
        self.courses:  dict = {}
        self.teachers: dict = {}
        self.sections: dict = {}
        self.timetable = Timetable()

    def get_scheduler(self):
        return GIKIScheduler(
            self.timetable, self.slots, self.rooms,
            self.teachers, self.courses
        )

    def get_engine(self):
        return ConstraintEngine(
            self.timetable, self.slots, self.rooms,
            self.teachers, self.courses
        )

    def save(self):
        data = {
            "courses":  {k: {"code": v.course_code, "title": v.title,
                              "ch": v.credit_hours, "type": v.session_type.value,
                              "faculty": v.faculty, "lab_type": v.lab_type,
                              "restricted": [d.value for d in v.restricted_days]}
                         for k, v in self.courses.items()},
            "teachers": {k: {"id": v.teacher_id, "name": v.name,
                              "faculty": v.faculty,
                              "unavail": [d.value for d in v.unavailable_days]}
                         for k, v in self.teachers.items()},
            "sections": {k: {"sid": v.section_id, "code": v.course_code,
                              "tid": v.teacher_id, "batch": v.batch_year,
                              "faculty": v.faculty, "students": v.num_students,
                              "for": v.for_program}
                         for k, v in self.sections.items()},
            "sessions": [s.to_dict() for s in self.timetable.sessions],
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self):
        if not os.path.exists(DATA_FILE):
            return
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.get("courses", {}).items():
            restricted = [DayOfWeek(d) for d in v.get("restricted", [])]
            self.courses[k] = Course(
                v["code"], v["title"], v["ch"],
                SessionType(v["type"]), v.get("faculty", ""),
                restricted, v.get("lab_type", "")
            )
        for k, v in data.get("teachers", {}).items():
            unavail = [DayOfWeek(d) for d in v.get("unavail", [])]
            self.teachers[k] = Teacher(
                v["id"], v["name"], v.get("faculty", ""), unavail
            )
        for k, v in data.get("sections", {}).items():
            self.sections[k] = Section(
                v["sid"], v["code"], v["tid"], v["batch"],
                v.get("faculty", ""), v.get("students", 30), v.get("for", "")
            )
        from core.models import ScheduledSession
        for sd in data.get("sessions", []):
            sess = ScheduledSession(
                sd["section_uid"], sd["course_code"],
                SessionType(sd["session_type"]), sd["slot_id"],
                sd["room_id"], sd["teacher_id"], sd["batch_year"],
                sd.get("faculty", ""), sd.get("session_index", 1)
            )
            self.timetable.add_session(sess)


# ══════════════════════════════════════════════════════════════════════
# HELPER WIDGETS
# ══════════════════════════════════════════════════════════════════════

def make_btn(parent, text, command, color=None, width=18, font_size=9):
    bg = color or C["btn"]
    fg = C["white"]
    b = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=C["btn_hover"], activeforeground=fg,
        font=(FONT_FAMILY, font_size, "bold"),
        relief="flat", cursor="hand2", width=width,
        padx=10, pady=6, bd=0
    )
    b.bind("<Enter>", lambda e: b.config(bg=C["btn_hover"]))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def make_label(parent, text, size=9, bold=False, color=None):
    return tk.Label(
        parent, text=text,
        bg=parent.cget("bg"), fg=color or C["text"],
        font=(FONT_FAMILY, size, "bold" if bold else "normal")
    )


def make_entry(parent, width=30, textvariable=None):
    e = tk.Entry(
        parent, width=width,
        bg=C["input_bg"], fg=C["text"],
        insertbackground=C["text"],
        relief="solid", bd=1,
        highlightthickness=1,
        highlightbackground=C["input_border"],
        highlightcolor=C["accent"],
        font=(FONT_FAMILY, 9)
    )
    if textvariable:
        e.config(textvariable=textvariable)
    return e


def make_treeview(parent, columns, headings, col_widths=None, height=15):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("GIKI.Treeview",
                     background=C["white"], foreground=C["text"],
                     rowheight=24, fieldbackground=C["white"],
                     font=(FONT_FAMILY, 9),
                     bordercolor=C["border"], relief="flat")
    style.configure("GIKI.Treeview.Heading",
                     background=C["header_bg"], foreground=C["header_fg"],
                     font=(FONT_FAMILY, 9, "bold"), relief="flat")
    style.map("GIKI.Treeview",
              background=[("selected", C["accent2"])],
              foreground=[("selected", C["white"])])

    frame = tk.Frame(parent, bg=C["white"], bd=1, relief="solid",
                     highlightbackground=C["border"], highlightthickness=1)

    tree = ttk.Treeview(frame, columns=columns, show="headings",
                         height=height, style="GIKI.Treeview",
                         selectmode="browse")

    for col, heading in zip(columns, headings):
        width = 120
        if col_widths and col in col_widths:
            width = col_widths[col]
        tree.heading(col, text=heading, anchor="w")
        tree.column(col, width=width, minwidth=50, anchor="w")

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    # Alternate row colors
    tree.tag_configure("even", background=C["row_even"])
    tree.tag_configure("odd",  background=C["row_odd"])

    return frame, tree


def status_bar(parent):
    bar = tk.Label(
        parent, text="Ready", anchor="w",
        bg=C["sidebar"], fg=C["white"],
        font=(FONT_FAMILY, 8),
        padx=10, pady=4
    )
    return bar


# ══════════════════════════════════════════════════════════════════════
# PANELS
# ══════════════════════════════════════════════════════════════════════

class DashboardPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        # Title
        tk.Label(self, text="GIKI Timetable Scheduler",
                  bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 18, "bold")).pack(pady=(24, 4))
        tk.Label(self, text="Spring 2026  —  Faculty-aware scheduling",
                  bg=C["bg"], fg=C["text_light"],
                  font=(FONT_FAMILY, 10)).pack(pady=(0, 20))

        # Stats row
        stats_frame = tk.Frame(self, bg=C["bg"])
        stats_frame.pack(fill="x", padx=30, pady=10)

        self.stat_vars = {}
        stats = [
            ("Courses",  "courses",  C["accent"]),
            ("Teachers", "teachers", C["sidebar"]),
            ("Sections", "sections", "#1B5E20"),
            ("Sessions", "sessions", "#E65100"),
            ("Slots",    "slots",    "#4A235A"),
            ("Rooms",    "rooms",    "#1A237E"),
        ]
        for i, (label, key, color) in enumerate(stats):
            card = tk.Frame(stats_frame, bg=C["white"], bd=0,
                             highlightthickness=1,
                             highlightbackground=C["border"])
            card.grid(row=0, column=i, padx=6, pady=4, sticky="ew", ipadx=10, ipady=10)
            stats_frame.grid_columnconfigure(i, weight=1)

            var = tk.StringVar(value="0")
            self.stat_vars[key] = var
            tk.Label(card, textvariable=var, font=(FONT_FAMILY, 22, "bold"),
                      fg=color, bg=C["white"]).pack()
            tk.Label(card, text=label, font=(FONT_FAMILY, 8),
                      fg=C["text_light"], bg=C["white"]).pack()

        self.refresh_stats()

        # Quick action buttons
        tk.Label(self, text="Quick Actions",
                  bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 11, "bold")).pack(pady=(20, 8))

        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(pady=4)

        make_btn(btn_frame, "Import Course List",
                  self._import_file, width=20).grid(row=0, column=0, padx=8, pady=4)
        make_btn(btn_frame, "Schedule All",
                  self._schedule_all, color=C["btn_success"], width=20).grid(row=0, column=1, padx=8, pady=4)
        make_btn(btn_frame, "Validate Timetable",
                  self._validate, width=20).grid(row=0, column=2, padx=8, pady=4)
        make_btn(btn_frame, "Export to Excel",
                  self._export, width=20).grid(row=0, column=3, padx=8, pady=4)

        # Log area
        tk.Label(self, text="Activity Log",
                  bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 11, "bold")).pack(pady=(16, 4), anchor="w", padx=30)

        self.log = scrolledtext.ScrolledText(
            self, height=10, font=(FONT_FAMILY, 8),
            bg="#1A1A2E", fg="#A8D8EA",
            insertbackground="white", relief="flat",
            wrap="word", padx=10, pady=8
        )
        self.log.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        self._log("Dashboard loaded. Import a course list or use the sidebar to begin.")

    def _log(self, msg, level="info"):
        colors = {"info": "#A8D8EA", "success": "#A8E6CF",
                  "warning": "#FFD3A5", "error": "#FFAAA5"}
        self.log.config(state="normal")
        self.log.insert("end", f"  {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.on_status(msg)

    def refresh_stats(self):
        s = self.state
        self.stat_vars["courses"].set(str(len(s.courses)))
        self.stat_vars["teachers"].set(str(len(s.teachers)))
        self.stat_vars["sections"].set(str(len(s.sections)))
        self.stat_vars["sessions"].set(str(len(s.timetable.sessions)))
        self.stat_vars["slots"].set(str(len(s.slots)))
        self.stat_vars["rooms"].set(str(len(s.rooms)))

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="Select Course List",
            filetypes=[("Spreadsheet / PDF", "*.xlsx *.xls *.csv *.pdf *.ods"),
                       ("All files", "*.*")]
        )
        if not path:
            return
        self._log(f"Parsing {os.path.basename(path)}...")
        try:
            entries = parse_course_list(path)
            summary = summarize_courses(entries)
            self._import_entries(entries)
            self.state.save()
            self.refresh_stats()
            self._log(
                f"Imported {summary['total']} entries | "
                f"{summary['unique_codes']} courses | "
                f"{summary['labs']} labs | "
                f"{summary['by_faculty']}",
                "success"
            )
        except Exception as e:
            self._log(f"Import error: {e}", "error")
            messagebox.showerror("Import Error", str(e))

    def _import_entries(self, entries):
        import re
        s = self.state

        def infer_lab_type(code):
            c = code.upper()
            if c.startswith("CY"): return "cyber"
            if c.startswith("SE"): return "software"
            if c.startswith("MM"): return "composite"
            if c.startswith("CH"): return "chemistry"
            if c.startswith("PH"): return "physics"
            return "computer" if any(c.startswith(p) for p in ("CS","AI","DS","IF")) else ""

        def norm_tid(name):
            clean = re.sub(r'[^A-Za-z\s]', '', name).strip().split()
            if len(clean) >= 2:
                return f"T-{clean[-1][:8].upper()}-{clean[-2][:3].upper()}"
            return f"T-{name[:10].upper().replace(' ','')}"

        for e in entries:
            if e.course_code not in s.courses:
                st = SessionType.LAB if e.is_lab else SessionType.LECTURE
                s.courses[e.course_code] = Course(
                    e.course_code, e.title, e.credit_hours,
                    st, e.faculty, [], infer_lab_type(e.course_code)
                )
            if e.instructor:
                tid = norm_tid(e.instructor)
                if tid not in s.teachers:
                    s.teachers[tid] = Teacher(tid, e.instructor, e.faculty)
                sec = Section(str(e.section), e.course_code, tid,
                               0, e.faculty, e.num_students, e.for_program)
                if sec.uid not in s.sections:
                    s.sections[sec.uid] = sec

    def _schedule_all(self):
        if not self.state.sections:
            messagebox.showwarning("No Sections", "Import a course list first.")
            return
        self._log("Scheduling all sections...")

        def run():
            t0 = time.perf_counter()
            sched = self.state.get_scheduler()
            result = sched.schedule_all(list(self.state.sections.values()))
            elapsed = time.perf_counter() - t0
            placed = sum(len(r["scheduled"]) for r in result["results"].values())
            failed = sum(len(r["unscheduled"]) for r in result["results"].values())
            self.state.save()
            self.after(0, self.refresh_stats)
            self.after(0, lambda: self._log(
                f"Done in {elapsed*1000:.0f}ms — "
                f"{placed} sessions placed, {failed} unplaced", "success"
            ))
            for w in result["warnings"][:5]:
                self.after(0, lambda msg=w: self._log(f"Warning: {msg}", "warning"))

        threading.Thread(target=run, daemon=True).start()

    def _validate(self):
        engine = self.state.get_engine()
        rep = engine.validate()
        if not rep.has_conflict:
            self._log("Timetable valid — 0 conflicts.", "success")
            messagebox.showinfo("Validation", "Timetable is valid. No conflicts found.")
        else:
            self._log(f"{len(rep.conflicts)} conflict(s) detected.", "error")
            messagebox.showerror("Conflicts Found",
                                  "\n".join(rep.conflicts[:10]) +
                                  (f"\n...and {len(rep.conflicts)-10} more"
                                   if len(rep.conflicts) > 10 else ""))

    def _export(self):
        os.makedirs(os.path.join(SCRIPT_DIR, "exports"), exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Export Timetable",
            defaultextension=".xlsx",
            initialfile="GIKI_Timetable_Spring2026.xlsx",
            filetypes=[("Excel", "*.xlsx"), ("Text", "*.txt")]
        )
        if not path:
            return
        try:
            if path.endswith(".txt"):
                export_text(self.state.timetable, self.state.slots, path)
            else:
                export_excel(self.state.timetable, self.state.slots,
                              self.state.courses, path)
            self._log(f"Exported: {os.path.basename(path)}", "success")
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            self._log(f"Export error: {e}", "error")
            messagebox.showerror("Export Error", str(e))


class CoursesPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="Courses", bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(side="left")
        make_btn(hdr, "Add Course", self._add, width=14).pack(side="right", padx=4)
        make_btn(hdr, "Delete", self._delete, color=C["btn_danger"], width=10).pack(side="right", padx=4)
        make_btn(hdr, "Refresh", self._refresh, width=10).pack(side="right", padx=4)

        # Search
        sf = tk.Frame(self, bg=C["bg"])
        sf.pack(fill="x", padx=20, pady=4)
        tk.Label(sf, text="Search:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self._refresh())
        make_entry(sf, width=30, textvariable=self.search_var).pack(side="left")

        # Treeview
        cols = ("code", "title", "ch", "type", "faculty", "lab_type")
        heads = ("Code", "Title", "Credit Hours", "Type", "Faculty", "Lab Type")
        widths = {"code": 90, "title": 260, "ch": 90, "type": 90,
                   "faculty": 90, "lab_type": 100}
        frame, self.tree = make_treeview(
            self, cols, heads, widths, height=20
        )
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._refresh()

    def _refresh(self, *_):
        q = self.search_var.get().lower() if hasattr(self, "search_var") else ""
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, (k, c) in enumerate(sorted(self.state.courses.items())):
            if q and q not in k.lower() and q not in c.title.lower():
                continue
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                c.course_code, c.title, c.credit_hours,
                c.session_type.value, c.faculty, c.lab_type or ""
            ), tags=(tag,))

    def _add(self):
        _CourseDialog(self, self.state, self._refresh)

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a course to delete.")
            return
        code = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", f"Delete course '{code}'?"):
            self.state.courses.pop(code, None)
            self.state.save()
            self._refresh()
            self.on_status(f"Deleted course {code}")


class TeachersPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="Teachers", bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(side="left")
        make_btn(hdr, "Add Teacher", self._add, width=14).pack(side="right", padx=4)
        make_btn(hdr, "Delete", self._delete, color=C["btn_danger"], width=10).pack(side="right", padx=4)
        make_btn(hdr, "Refresh", self._refresh, width=10).pack(side="right", padx=4)

        cols = ("id", "name", "faculty", "unavail")
        heads = ("ID", "Name", "Faculty", "Unavailable Days")
        widths = {"id": 140, "name": 220, "faculty": 90, "unavail": 200}
        frame, self.tree = make_treeview(self, cols, heads, widths, height=22)
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._refresh()

    def _refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, (k, t) in enumerate(sorted(self.state.teachers.items())):
            tag = "even" if i % 2 == 0 else "odd"
            unavail = ", ".join(d.value for d in t.unavailable_days) or "None"
            self.tree.insert("", "end", values=(
                t.teacher_id, t.name, t.faculty, unavail
            ), tags=(tag,))

    def _add(self):
        _TeacherDialog(self, self.state, self._refresh)

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a teacher to delete.")
            return
        tid = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", f"Delete teacher '{tid}'?"):
            self.state.teachers.pop(tid, None)
            self.state.save()
            self._refresh()


class SectionsPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="Sections", bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(side="left")
        make_btn(hdr, "Add Section", self._add, width=14).pack(side="right", padx=4)
        make_btn(hdr, "Delete", self._delete, color=C["btn_danger"], width=10).pack(side="right", padx=4)
        make_btn(hdr, "Reschedule", self._reschedule, color=C["btn_success"], width=12).pack(side="right", padx=4)
        make_btn(hdr, "Refresh", self._refresh, width=10).pack(side="right", padx=4)

        # Faculty filter
        ff = tk.Frame(self, bg=C["bg"])
        ff.pack(fill="x", padx=20, pady=4)
        tk.Label(ff, text="Filter Faculty:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).pack(side="left", padx=(0, 6))
        self.filter_var = tk.StringVar(value="ALL")
        cb = ttk.Combobox(ff, textvariable=self.filter_var, width=12,
                           values=["ALL", "FCSE", "FEE", "FME", "FChE",
                                    "FMCE", "FCvE", "FBS", "SMgS"],
                           state="readonly", font=(FONT_FAMILY, 9))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        cols = ("uid", "course", "teacher", "batch", "faculty", "students")
        heads = ("Section UID", "Course", "Teacher", "Batch Year", "Faculty", "Students")
        widths = {"uid": 150, "course": 100, "teacher": 180,
                   "batch": 80, "faculty": 80, "students": 80}
        frame, self.tree = make_treeview(self, cols, heads, widths, height=20)
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._refresh()

    def _refresh(self):
        filt = self.filter_var.get() if hasattr(self, "filter_var") else "ALL"
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, (k, s) in enumerate(sorted(self.state.sections.items())):
            if filt != "ALL" and s.faculty != filt:
                continue
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                s.uid, s.course_code, s.teacher_id,
                s.batch_year or "-", s.faculty, s.num_students
            ), tags=(tag,))

    def _add(self):
        _SectionDialog(self, self.state, self._refresh)

    def _delete(self):
        sel = self.tree.selection()
        if not sel: return
        uid = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", f"Delete section '{uid}'?"):
            self.state.timetable.clear_section(uid)
            self.state.sections.pop(uid, None)
            self.state.save()
            self._refresh()

    def _reschedule(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a section to reschedule.")
            return
        uid = self.tree.item(sel[0])["values"][0]
        if uid not in self.state.sections:
            return
        sched = self.state.get_scheduler()
        result = sched.adjust_section(self.state.sections[uid])
        self.state.save()
        placed = len(result["scheduled"])
        self.on_status(f"Rescheduled {uid}: {placed} sessions placed")
        messagebox.showinfo("Rescheduled",
                             f"Section '{uid}': {placed} sessions placed.")


class SchedulePanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="Timetable", bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(side="left")

        # Controls
        ctrl = tk.Frame(self, bg=C["bg"])
        ctrl.pack(fill="x", padx=20, pady=6)

        tk.Label(ctrl, text="Filter:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).pack(side="left")
        self.filt_var = tk.StringVar(value="ALL")
        cb = ttk.Combobox(ctrl, textvariable=self.filt_var, width=10,
                           values=["ALL", "FCSE", "FEE", "FME", "FChE",
                                    "FMCE", "FCvE", "FBS", "SMgS"],
                           state="readonly", font=(FONT_FAMILY, 9))
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        tk.Label(ctrl, text="Section:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).pack(side="left", padx=(12, 4))
        self.sec_var = tk.StringVar()
        make_entry(ctrl, width=16, textvariable=self.sec_var).pack(side="left")
        make_btn(ctrl, "Filter", self._refresh, width=8).pack(side="left", padx=4)
        make_btn(ctrl, "Clear Filter", self._clear_filter, width=12).pack(side="left", padx=4)

        total_label = tk.Label(ctrl, bg=C["bg"], fg=C["text_light"],
                                 font=(FONT_FAMILY, 9))
        total_label.pack(side="right")
        self.total_label = total_label

        # Treeview
        cols = ("section", "course", "type", "day", "time", "room", "teacher", "faculty")
        heads = ("Section", "Course", "Type", "Day", "Time", "Room", "Teacher", "Faculty")
        widths = {"section": 140, "course": 90, "type": 70, "day": 100,
                   "time": 110, "room": 120, "teacher": 160, "faculty": 80}
        frame, self.tree = make_treeview(self, cols, heads, widths, height=24)
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._refresh()

    def _clear_filter(self):
        self.sec_var.set("")
        self.filt_var.set("ALL")
        self._refresh()

    def _refresh(self, *_):
        filt_fac = self.filt_var.get() if hasattr(self, "filt_var") else "ALL"
        filt_sec = self.sec_var.get().strip() if hasattr(self, "sec_var") else ""

        for row in self.tree.get_children():
            self.tree.delete(row)

        day_order = {d: i for i, d in enumerate(DayOfWeek)}
        sessions = self.state.timetable.sessions

        filtered = [
            s for s in sessions
            if (filt_fac == "ALL" or s.faculty == filt_fac)
            and (not filt_sec or filt_sec.lower() in s.section_uid.lower())
        ]
        filtered.sort(key=lambda s: (
            day_order.get(
                self.state.slots[s.slot_id].day
                if s.slot_id in self.state.slots else DayOfWeek.MONDAY, 0
            ),
            self.state.slots[s.slot_id].start_min
            if s.slot_id in self.state.slots else 0
        ))

        for i, s in enumerate(filtered):
            slot = self.state.slots.get(s.slot_id)
            time_str = f"{slot.start_str}-{slot.end_str}" if slot else "?"
            day_str  = slot.day.value if slot else "?"
            stype    = s.session_type.value
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                s.section_uid, s.course_code, stype,
                day_str, time_str, s.room_id,
                s.teacher_id, s.faculty
            ), tags=(tag,))

        if hasattr(self, "total_label"):
            self.total_label.config(text=f"{len(filtered)} sessions shown")


class ClashPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        tk.Label(self, text="Clash Check / Free Slot Finder",
                  bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(pady=(16, 8))

        form = tk.Frame(self, bg=C["white"], bd=1, relief="solid",
                         highlightbackground=C["border"], highlightthickness=1)
        form.pack(fill="x", padx=30, pady=8, ipady=12)

        fields = [
            ("Teacher ID:", "tid_var"),
            ("Section UID:", "uid_var"),
            ("Course Code:", "code_var"),
            ("Preferred Time (HH:MM):", "time_var"),
        ]
        for row, (lbl, var_name) in enumerate(fields):
            tk.Label(form, text=lbl, bg=C["white"], fg=C["text"],
                      font=(FONT_FAMILY, 9)).grid(row=row, column=0, sticky="e",
                                                    padx=(20, 8), pady=6)
            var = tk.StringVar()
            setattr(self, var_name, var)
            make_entry(form, width=24, textvariable=var).grid(
                row=row, column=1, sticky="w", padx=(0, 20), pady=6)

        # Session type
        tk.Label(form, text="Session Type:", bg=C["white"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).grid(row=4, column=0, sticky="e",
                                               padx=(20, 8), pady=6)
        self.stype_var = tk.StringVar(value="Lecture")
        ttk.Combobox(form, textvariable=self.stype_var,
                      values=["Lecture", "Lab"], state="readonly",
                      width=22, font=(FONT_FAMILY, 9)).grid(
            row=4, column=1, sticky="w", padx=(0, 20), pady=6)

        make_btn(form, "Find Free Slots", self._find,
                  color=C["btn_success"], width=20).grid(
            row=5, column=0, columnspan=2, pady=12)

        # Results
        tk.Label(self, text="Available Slots",
                  bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 11, "bold")).pack(pady=(12, 4), anchor="w", padx=30)

        cols = ("slot_id", "day", "time", "rooms")
        heads = ("Slot ID", "Day", "Time", "Available Rooms")
        widths = {"slot_id": 160, "day": 110, "time": 130, "rooms": 400}
        frame, self.tree = make_treeview(self, cols, heads, widths, height=14)
        frame.pack(fill="both", expand=True, padx=30, pady=8)

    def _find(self):
        tid   = self.tid_var.get().strip()
        uid   = self.uid_var.get().strip()
        code  = self.code_var.get().strip()
        stype = SessionType.LAB if self.stype_var.get() == "Lab" else SessionType.LECTURE
        pref  = self.time_var.get().strip()

        if not code:
            messagebox.showwarning("Missing", "Enter a course code.")
            return

        pref_min = None
        if pref:
            try:
                h, m = map(int, pref.split(":"))
                pref_min = h * 60 + m
            except ValueError:
                pass

        engine = self.state.get_engine()
        results = engine.find_free_slots(tid, uid, code, stype)

        if pref_min:
            results.sort(key=lambda x: abs(
                self.state.slots[x["slot_id"]].start_min - pref_min
                if x["slot_id"] in self.state.slots else 9999
            ))

        for row in self.tree.get_children():
            self.tree.delete(row)

        for i, r in enumerate(results):
            tag = "even" if i % 2 == 0 else "odd"
            rooms_str = ", ".join(r["rooms"][:4])
            self.tree.insert("", "end", values=(
                r["slot_id"], r["day"], r["time"], rooms_str
            ), tags=(tag,))

        self.on_status(f"Found {len(results)} free slots for {code}")


class RoomsPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="Buildings & Rooms", bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(side="left")
        make_btn(hdr, "Add Room", self._add_room, width=12).pack(side="right", padx=4)
        make_btn(hdr, "Remove Room", self._remove_room,
                  color=C["btn_danger"], width=12).pack(side="right", padx=4)
        make_btn(hdr, "Export Table", self._export_table, width=14).pack(side="right", padx=4)

        cols = ("room_id", "building", "capacity", "type", "priority", "notes")
        heads = ("Room ID", "Building", "Capacity", "Type", "Priority Faculties", "Notes")
        widths = {"room_id": 120, "building": 180, "capacity": 80,
                   "type": 120, "priority": 160, "notes": 280}
        frame, self.tree = make_treeview(self, cols, heads, widths, height=24)
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._refresh()

    def _refresh(self):
        from config.buildings import get_all_rooms_table
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = get_all_rooms_table()
        for i, r in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                r["room_id"], r["building"], r["capacity"],
                r["type"], r["priority_for"], r["notes"]
            ), tags=(tag,))

    def _add_room(self):
        _RoomDialog(self, self.state, self._refresh)

    def _remove_room(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a room to remove.")
            return
        rid = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", f"Remove room '{rid}'?"):
            remove_room(rid)
            self._refresh()
            self.on_status(f"Room '{rid}' removed")

    def _export_table(self):
        path = filedialog.asksaveasfilename(
            title="Export Buildings & Rooms",
            defaultextension=".xlsx",
            initialfile="GIKI_Buildings_Rooms.xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            export_buildings_table_excel(path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


class ExportPanel(tk.Frame):
    def __init__(self, parent, state: AppState, on_status):
        super().__init__(parent, bg=C["bg"])
        self.state = state
        self.on_status = on_status
        self._build()

    def _build(self):
        tk.Label(self, text="Export Timetable",
                  bg=C["bg"], fg=C["accent"],
                  font=(FONT_FAMILY, 14, "bold")).pack(pady=(16, 8))

        card = tk.Frame(self, bg=C["white"], bd=0,
                         highlightthickness=1, highlightbackground=C["border"])
        card.pack(fill="x", padx=30, pady=8, ipady=16, ipadx=20)

        # Faculty filter for export
        row0 = tk.Frame(card, bg=C["white"])
        row0.pack(fill="x", pady=8)
        tk.Label(row0, text="Faculty Filter:", bg=C["white"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).pack(side="left", padx=(0, 8))
        self.fac_var = tk.StringVar(value="ALL")
        ttk.Combobox(row0, textvariable=self.fac_var,
                      values=["ALL", "FCSE", "FEE", "FME", "FChE",
                               "FMCE", "FCvE", "FBS", "SMgS"],
                      state="readonly", width=14,
                      font=(FONT_FAMILY, 9)).pack(side="left")
        tk.Label(row0,
                  text="  (select ALL for one sheet per faculty + combined sheet)",
                  bg=C["white"], fg=C["text_light"],
                  font=(FONT_FAMILY, 8, "italic")).pack(side="left")

        exports = [
            ("Export to Excel (.xlsx)",
             "Faculty-color-coded grid, one sheet per faculty + ALL combined",
             C["btn_success"], self._export_excel),
            ("Export to Text (.txt)",
             "Plain text, sortable, easy to share",
             C["btn"], self._export_text),
            ("Export Buildings & Rooms Table",
             "Two-sheet Excel with all rooms and buildings",
             C["accent"], self._export_buildings),
        ]
        for lbl, desc, color, cmd in exports:
            row = tk.Frame(card, bg=C["white"])
            row.pack(fill="x", pady=8)
            make_btn(row, lbl, cmd, color=color, width=30).pack(side="left", padx=(0, 16))
            tk.Label(row, text=desc, bg=C["white"], fg=C["text_light"],
                      font=(FONT_FAMILY, 8, "italic")).pack(side="left")

    def _export_excel(self):
        fac = self.fac_var.get()
        path = filedialog.asksaveasfilename(
            title="Save Excel Timetable",
            defaultextension=".xlsx",
            initialfile=f"GIKI_Timetable_{fac}_Spring2026.xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            filt = None if fac == "ALL" else fac
            title = f"GIKI University — Timetable Spring 2026" + (f" — {fac}" if filt else "")
            export_excel(
                self.state.timetable, self.state.slots,
                self.state.courses, path,
                faculty_filter=filt, title=title
            )
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
            self.on_status(f"Exported: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_text(self):
        fac = self.fac_var.get()
        path = filedialog.asksaveasfilename(
            title="Save Text Timetable",
            defaultextension=".txt",
            initialfile="GIKI_Timetable_Spring2026.txt",
            filetypes=[("Text", "*.txt")]
        )
        if not path:
            return
        filt = None if fac == "ALL" else fac
        export_text(self.state.timetable, self.state.slots, path, faculty_filter=filt)
        messagebox.showinfo("Exported", f"Saved to:\n{path}")
        self.on_status(f"Text exported: {os.path.basename(path)}")

    def _export_buildings(self):
        path = filedialog.asksaveasfilename(
            title="Save Buildings & Rooms",
            defaultextension=".xlsx",
            initialfile="GIKI_Buildings_Rooms.xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            export_buildings_table_excel(path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


# ══════════════════════════════════════════════════════════════════════
# SIMPLE DIALOGS
# ══════════════════════════════════════════════════════════════════════

class _BaseDialog(tk.Toplevel):
    def __init__(self, parent, title, state, on_done):
        super().__init__(parent)
        self.state = state
        self.on_done = on_done
        self.title(title)
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._fields = {}
        self._build()
        self.wait_window()

    def _row(self, frame, label, var_name, row, default=""):
        tk.Label(frame, text=label, bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).grid(row=row, column=0, sticky="e",
                                               padx=(16, 8), pady=6)
        var = tk.StringVar(value=default)
        entry = make_entry(frame, width=28, textvariable=var)
        entry.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=6)
        self._fields[var_name] = var
        return var

    def _build(self):
        pass

    def _save(self):
        pass


class _CourseDialog(_BaseDialog):
    def __init__(self, parent, state, on_done):
        super().__init__(parent, "Add Course", state, on_done)

    def _build(self):
        f = tk.Frame(self, bg=C["bg"])
        f.pack(padx=20, pady=16)
        self._row(f, "Course Code:", "code", 0)
        self._row(f, "Title:", "title", 1)
        self._row(f, "Credit Hours:", "ch", 2, "3")
        self._row(f, "Faculty:", "faculty", 3, "FCSE")
        self._row(f, "Lab Type (optional):", "lab_type", 4)

        tk.Label(f, text="Session Type:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).grid(row=5, column=0, sticky="e",
                                               padx=(16, 8), pady=6)
        self._stype = tk.StringVar(value="Lecture")
        ttk.Combobox(f, textvariable=self._stype,
                      values=["Lecture", "Lab"], state="readonly",
                      width=26).grid(row=5, column=1, sticky="w", pady=6)

        make_btn(f, "Save", self._save, color=C["btn_success"], width=20).grid(
            row=6, column=0, columnspan=2, pady=12)

    def _save(self):
        code = self._fields["code"].get().strip().upper()
        if not code:
            messagebox.showwarning("Required", "Course code is required.", parent=self)
            return
        try:
            ch = int(self._fields["ch"].get().strip() or "2")
        except ValueError:
            ch = 2
        st = SessionType.LAB if self._stype.get() == "Lab" else SessionType.LECTURE
        self.state.courses[code] = Course(
            code, self._fields["title"].get().strip(), ch,
            st, self._fields["faculty"].get().strip(),
            [], self._fields["lab_type"].get().strip()
        )
        self.state.save()
        self.on_done()
        self.destroy()


class _TeacherDialog(_BaseDialog):
    def __init__(self, parent, state, on_done):
        super().__init__(parent, "Add Teacher", state, on_done)

    def _build(self):
        f = tk.Frame(self, bg=C["bg"])
        f.pack(padx=20, pady=16)
        self._row(f, "Teacher ID:", "tid", 0)
        self._row(f, "Full Name:", "name", 1)
        self._row(f, "Faculty:", "faculty", 2, "FCSE")
        self._row(f, "Unavailable Days (comma-sep):", "unavail", 3)
        tk.Label(f, text="e.g. Friday or Monday,Wednesday",
                  bg=C["bg"], fg=C["text_light"],
                  font=(FONT_FAMILY, 7, "italic")).grid(
            row=4, column=0, columnspan=2)
        make_btn(f, "Save", self._save, color=C["btn_success"], width=20).grid(
            row=5, column=0, columnspan=2, pady=12)

    def _save(self):
        tid = self._fields["tid"].get().strip()
        if not tid:
            messagebox.showwarning("Required", "Teacher ID required.", parent=self)
            return
        unavail_raw = self._fields["unavail"].get().strip()
        unavail = []
        for d in unavail_raw.split(","):
            d = d.strip().capitalize()
            try:
                unavail.append(DayOfWeek(d))
            except ValueError:
                pass
        self.state.teachers[tid] = Teacher(
            tid, self._fields["name"].get().strip(),
            self._fields["faculty"].get().strip(), unavail
        )
        self.state.save()
        self.on_done()
        self.destroy()


class _SectionDialog(_BaseDialog):
    def __init__(self, parent, state, on_done):
        super().__init__(parent, "Add Section", state, on_done)

    def _build(self):
        f = tk.Frame(self, bg=C["bg"])
        f.pack(padx=20, pady=16)
        self._row(f, "Course Code:", "code", 0)
        self._row(f, "Section ID (A/B/1/2):", "sid", 1, "A")
        self._row(f, "Teacher ID:", "tid", 2)
        self._row(f, "Batch Year:", "batch", 3, "2")
        self._row(f, "Faculty:", "faculty", 4, "FCSE")
        self._row(f, "Num Students:", "students", 5, "30")
        make_btn(f, "Save", self._save, color=C["btn_success"], width=20).grid(
            row=6, column=0, columnspan=2, pady=12)

    def _save(self):
        code = self._fields["code"].get().strip().upper()
        sid  = self._fields["sid"].get().strip()
        if not code or not sid:
            messagebox.showwarning("Required", "Course and section ID required.", parent=self)
            return
        try: batch = int(self._fields["batch"].get().strip() or "0")
        except: batch = 0
        try: students = int(self._fields["students"].get().strip() or "30")
        except: students = 30
        sec = Section(sid, code, self._fields["tid"].get().strip(),
                       batch, self._fields["faculty"].get().strip(), students)
        self.state.sections[sec.uid] = sec
        self.state.save()
        self.on_done()
        self.destroy()


class _RoomDialog(_BaseDialog):
    def __init__(self, parent, state, on_done):
        super().__init__(parent, "Add Room", state, on_done)

    def _build(self):
        f = tk.Frame(self, bg=C["bg"])
        f.pack(padx=20, pady=16)
        self._row(f, "Room ID:", "rid", 0)
        self._row(f, "Building ID:", "bid", 1)
        self._row(f, "Capacity:", "cap", 2, "60")
        self._row(f, "Priority Faculties (comma-sep):", "priority", 3)
        self._row(f, "Notes:", "notes", 4)

        tk.Label(f, text="Is Lab:", bg=C["bg"], fg=C["text"],
                  font=(FONT_FAMILY, 9)).grid(row=5, column=0, sticky="e",
                                               padx=(16, 8), pady=6)
        self._is_lab = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, variable=self._is_lab).grid(row=5, column=1, sticky="w")

        self._row(f, "Lab Type (if lab):", "lab_type", 6)

        make_btn(f, "Save", self._save, color=C["btn_success"], width=20).grid(
            row=7, column=0, columnspan=2, pady=12)

    def _save(self):
        rid = self._fields["rid"].get().strip()
        bid = self._fields["bid"].get().strip()
        if not rid or not bid:
            messagebox.showwarning("Required", "Room ID and Building ID required.", parent=self)
            return
        try: cap = int(self._fields["cap"].get().strip() or "60")
        except: cap = 60
        pf = [x.strip() for x in self._fields["priority"].get().split(",") if x.strip()]
        add_room(rid, bid, cap, self._is_lab.get(),
                  self._fields["lab_type"].get().strip() or None, pf,
                  self._fields["notes"].get().strip())
        self.on_done()
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
# MAIN APPLICATION WINDOW
# ══════════════════════════════════════════════════════════════════════

class GIKISchedulerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        try:
            self.state.load()
        except Exception:
            pass

        self.title("GIKI University Timetable Scheduler")
        self.geometry("1280x800")
        self.minsize(1100, 700)
        self.configure(bg=C["bg"])

        # Window icon (skip if unavailable)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._build_layout()
        self._active_panel = None
        self._nav_buttons  = {}
        self._show_panel("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        # ── Sidebar ──────────────────────────────────────────────────
        self.sidebar = tk.Frame(self, bg=C["sidebar"], width=200)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo area
        logo_frame = tk.Frame(self.sidebar, bg=C["sidebar"])
        logo_frame.pack(fill="x", pady=(20, 10))
        tk.Label(logo_frame, text="GIKI", bg=C["sidebar"], fg=C["white"],
                  font=(FONT_FAMILY, 18, "bold")).pack()
        tk.Label(logo_frame, text="Timetable Scheduler", bg=C["sidebar"], fg="#8AB4D8",
                  font=(FONT_FAMILY, 8)).pack()
        tk.Frame(logo_frame, bg="#2E4E8C", height=1).pack(fill="x", padx=16, pady=(8, 0))

        # Nav items
        nav_items = [
            ("dashboard",  "  Dashboard"),
            ("courses",    "  Courses"),
            ("teachers",   "  Teachers"),
            ("sections",   "  Sections"),
            ("schedule",   "  Timetable"),
            ("clash",      "  Clash Checker"),
            ("rooms",      "  Buildings & Rooms"),
            ("export",     "  Export"),
        ]
        self.nav_frame = tk.Frame(self.sidebar, bg=C["sidebar"])
        self.nav_frame.pack(fill="x", pady=(10, 0))

        for key, label in nav_items:
            btn = tk.Button(
                self.nav_frame, text=label, anchor="w",
                bg=C["sidebar"], fg=C["white"], relief="flat",
                font=(FONT_FAMILY, 10), cursor="hand2",
                activebackground=C["sidebar_hover"],
                activeforeground=C["white"],
                padx=16, pady=10, bd=0
            )
            btn.config(command=lambda k=key: self._show_panel(k))
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=C["sidebar_hover"])
                      if b.cget("bg") != C["sidebar_active"] else None)
            btn.bind("<Leave>", lambda e, b=btn, k2=key: b.config(
                bg=C["sidebar_active"] if self._active_panel == k2 else C["sidebar"]
            ))
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        # Version label at bottom
        tk.Label(self.sidebar, text="v2.0  Spring 2026",
                  bg=C["sidebar"], fg="#4A6E8C",
                  font=(FONT_FAMILY, 7)).pack(side="bottom", pady=10)

        # ── Main content area ─────────────────────────────────────────
        content_frame = tk.Frame(self, bg=C["bg"])
        content_frame.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(content_frame, bg=C["bg"])
        self.content.pack(fill="both", expand=True)

        # Status bar
        self.status = status_bar(content_frame)
        self.status.pack(fill="x", side="bottom")

        # Panel registry
        self._panels = {}

    def _show_panel(self, name: str):
        # Update nav highlight
        if self._active_panel and self._active_panel in self._nav_buttons:
            self._nav_buttons[self._active_panel].config(bg=C["sidebar"])
        self._active_panel = name
        if name in self._nav_buttons:
            self._nav_buttons[name].config(bg=C["sidebar_active"])

        # Create panel on first visit
        if name not in self._panels:
            panel_map = {
                "dashboard": DashboardPanel,
                "courses":   CoursesPanel,
                "teachers":  TeachersPanel,
                "sections":  SectionsPanel,
                "schedule":  SchedulePanel,
                "clash":     ClashPanel,
                "rooms":     RoomsPanel,
                "export":    ExportPanel,
            }
            cls = panel_map.get(name)
            if cls:
                p = cls(self.content, self.state, self._set_status)
                self._panels[name] = p

        # Hide all, show selected
        for p in self._panels.values():
            p.pack_forget()
        self._panels[name].pack(fill="both", expand=True)

        # Refresh panels that need it
        refresh_panels = {
            "schedule": "schedule",
            "sections": "sections",
            "courses":  "courses",
            "teachers": "teachers",
            "rooms":    "rooms",
        }
        panel = self._panels.get(name)
        if panel and hasattr(panel, "_refresh"):
            try:
                panel._refresh()
            except Exception:
                pass
        if name == "dashboard" and panel:
            panel.refresh_stats()

    def _set_status(self, msg: str):
        self.status.config(text=f"  {msg}")

    def _on_close(self):
        try:
            self.state.save()
        except Exception:
            pass
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = GIKISchedulerApp()
    app.mainloop()

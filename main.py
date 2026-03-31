"""
GIKI University Timetable Scheduler v2.0
=========================================
Run: python main.py

Features:
  - Parse courses from Excel / CSV / PDF
  - Faculty-aware room routing (CyberLab -> CyS first, etc.)
  - Variable credit hours (1, 2, 3, 4+)
  - Export full timetable or per-faculty timetable to Excel
  - Buildings and rooms reference table
  - Clash detection and free slot finder
"""

from __future__ import annotations
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.models import (
    Timetable, Section, Course, Teacher, TimeSlot, SessionType, DayOfWeek
)
from core.scheduler import GIKIScheduler, ConstraintEngine
from data.slots import build_giki_slots
from config.buildings import ROOMS, BUILDINGS
from parsers.course_parser import parse_course_list, summarize_courses, CourseEntry
from exporters.excel_exporter import (
    export_excel, export_text, export_buildings_table_excel
)

DIVIDER = "-" * 72
HDIVIDER = "=" * 72
DATA_FILE = "giki_scheduler_state.json"


# ══════════════════════════════════════════════════════════════════════
# APPLICATION STATE
# ══════════════════════════════════════════════════════════════════════

class AppState:
    def __init__(self):
        self.slots:    dict[str, TimeSlot] = build_giki_slots()
        self.rooms     = ROOMS
        self.courses:  dict[str, Course]   = {}
        self.teachers: dict[str, Teacher]  = {}
        self.sections: dict[str, Section]  = {}
        self.timetable = Timetable()

    def get_scheduler(self) -> GIKIScheduler:
        return GIKIScheduler(
            self.timetable, self.slots, self.rooms,
            self.teachers, self.courses
        )

    def get_engine(self) -> ConstraintEngine:
        return ConstraintEngine(
            self.timetable, self.slots, self.rooms,
            self.teachers, self.courses
        )

    def save(self, path: str = DATA_FILE):
        data = {
            "courses": {
                k: {"code": v.course_code, "title": v.title,
                    "ch": v.credit_hours, "type": v.session_type.value,
                    "faculty": v.faculty, "lab_type": v.lab_type,
                    "restricted": [d.value for d in v.restricted_days]}
                for k, v in self.courses.items()
            },
            "teachers": {
                k: {"id": v.teacher_id, "name": v.name, "faculty": v.faculty,
                    "unavail": [d.value for d in v.unavailable_days]}
                for k, v in self.teachers.items()
            },
            "sections": {
                k: {"sid": v.section_id, "code": v.course_code,
                    "tid": v.teacher_id, "batch": v.batch_year,
                    "faculty": v.faculty, "students": v.num_students,
                    "for": v.for_program}
                for k, v in self.sections.items()
            },
            "sessions": [s.to_dict() for s in self.timetable.sessions],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str = DATA_FILE):
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for k, v in data.get("courses", {}).items():
            restricted = [DayOfWeek(d) for d in v.get("restricted", [])]
            c = Course(v["code"], v["title"], v["ch"],
                       SessionType(v["type"]), v.get("faculty",""),
                       restricted, v.get("lab_type",""))
            self.courses[k] = c

        for k, v in data.get("teachers", {}).items():
            unavail = [DayOfWeek(d) for d in v.get("unavail", [])]
            t = Teacher(v["id"], v["name"], v.get("faculty",""), unavail)
            self.teachers[k] = t

        for k, v in data.get("sections", {}).items():
            s = Section(v["sid"], v["code"], v["tid"], v["batch"],
                        v.get("faculty",""), v.get("students", 30),
                        v.get("for",""))
            self.sections[k] = s

        from core.models import ScheduledSession
        for sd in data.get("sessions", []):
            sess = ScheduledSession(
                sd["section_uid"], sd["course_code"],
                SessionType(sd["session_type"]), sd["slot_id"],
                sd["room_id"], sd["teacher_id"], sd["batch_year"],
                sd.get("faculty",""), sd.get("session_index", 1)
            )
            self.timetable.add_session(sess)


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def clear(): os.system("cls" if os.name == "nt" else "clear")
def pause(): input("\nPress Enter to continue...")
def prompt(label, default=""): 
    v = input(f"  {label}{' ['+default+']' if default else ''}: ").strip()
    return v if v else default


# ══════════════════════════════════════════════════════════════════════
# IMPORT COURSES FROM FILE
# ══════════════════════════════════════════════════════════════════════

def import_courses_from_file(state: AppState):
    clear()
    print(HDIVIDER)
    print("  IMPORT COURSES FROM FILE")
    print(HDIVIDER)
    print("  Supports: .xlsx  .xls  .csv  .pdf")
    print()
    filepath = prompt("File path (drag and drop or type)")
    if not filepath or not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        pause(); return

    print(f"  Parsing '{os.path.basename(filepath)}'...")
    try:
        entries = parse_course_list(filepath)
        summary = summarize_courses(entries)
        print(f"  Parsed {summary['total']} entries | "
              f"{summary['unique_codes']} unique codes | "
              f"{summary['labs']} labs")
        print(f"  By faculty: {summary['by_faculty']}")
    except Exception as e:
        print(f"  Parse error: {e}")
        pause(); return

    if not entries:
        print("  No entries found.")
        pause(); return

    # Convert entries to courses, teachers, sections
    new_courses = 0
    new_teachers = 0
    new_sections = 0

    for entry in entries:
        # Add/update course
        if entry.course_code not in state.courses:
            lab_type = _infer_lab_type(entry.course_code)
            session_type = SessionType.LAB if entry.is_lab else SessionType.LECTURE
            state.courses[entry.course_code] = Course(
                entry.course_code, entry.title,
                entry.credit_hours, session_type,
                entry.faculty, [], lab_type
            )
            new_courses += 1

        # Add teacher if instructor provided
        teacher_id = None
        if entry.instructor:
            # Normalize teacher name to ID
            tid = _normalize_teacher_id(entry.instructor)
            if tid not in state.teachers:
                state.teachers[tid] = Teacher(tid, entry.instructor, entry.faculty)
                new_teachers += 1
            teacher_id = tid

        # Add section
        if teacher_id:
            sec = Section(
                str(entry.section), entry.course_code,
                teacher_id, 0, entry.faculty,
                entry.num_students, entry.for_program
            )
            uid = sec.uid
            if uid not in state.sections:
                state.sections[uid] = sec
                new_sections += 1

    state.save()
    print(f"\n  Added: {new_courses} courses, {new_teachers} teachers, {new_sections} sections")
    print(f"  Total state: {len(state.courses)} courses, {len(state.teachers)} teachers, "
          f"{len(state.sections)} sections")
    pause()


def _infer_lab_type(code: str) -> str:
    c = code.upper()
    if c.startswith("CY"): return "cyber"
    if c.startswith("SE"): return "software"
    if c.startswith("MM") or "MAT" in c: return "composite"
    if c.startswith("CH"): return "chemistry"
    if c.startswith("PH"): return "physics"
    if c.startswith("CS") or c.startswith("AI") or c.startswith("DS"): return "computer"
    return ""


def _normalize_teacher_id(name: str) -> str:
    """Convert name to a stable ID."""
    import re
    clean = re.sub(r'[^A-Za-z\s]', '', name).strip()
    parts = clean.split()
    if len(parts) >= 2:
        return f"T-{parts[-1][:8].upper()}-{parts[-2][:3].upper()}"
    return f"T-{clean[:12].upper().replace(' ', '')}"


# ══════════════════════════════════════════════════════════════════════
# SCHEDULING MENU
# ══════════════════════════════════════════════════════════════════════

def menu_schedule(state: AppState):
    while True:
        clear()
        print(HDIVIDER)
        print("  SCHEDULING")
        print(HDIVIDER)
        print(f"  Sections to schedule: {len(state.sections)}")
        print(f"  Sessions scheduled:   {len(state.timetable.sessions)}")
        print()
        print("  1. Schedule ALL sections (greedy, faculty-routed)")
        print("  2. Schedule specific section")
        print("  3. Adjust / re-schedule a section")
        print("  4. Add shared elective (multi-section)")
        print("  5. Validate timetable")
        print("  6. Clear timetable")
        print("  0. Back")
        choice = prompt("Choice")

        if choice == "1":
            clear(); print(HDIVIDER); print("  SCHEDULE ALL"); print(HDIVIDER)
            sched = state.get_scheduler()
            sections_list = list(state.sections.values())
            print(f"  Scheduling {len(sections_list)} sections...")
            t0 = time.perf_counter()
            result = sched.schedule_all(sections_list)
            elapsed = time.perf_counter() - t0
            placed = sum(len(r["scheduled"]) for r in result["results"].values())
            failed = sum(len(r["unscheduled"]) for r in result["results"].values())
            print(f"\n  Done in {elapsed*1000:.1f}ms")
            print(f"  Sessions placed: {placed}  |  Unplaced: {failed}")
            for w in result["warnings"][:10]:
                print(f"  ! {w}")
            state.save()
            pause()

        elif choice == "2":
            uid = prompt("Section UID (e.g. CS301-A)")
            if uid not in state.sections:
                print("  Section not found."); pause(); continue
            sched = state.get_scheduler()
            r = sched.schedule_section(state.sections[uid])
            print(f"  Placed: {len(r['scheduled'])}  Unplaced: {len(r['unscheduled'])}")
            for w in r["warnings"]: print(f"  ! {w}")
            state.save(); pause()

        elif choice == "3":
            uid = prompt("Section UID to adjust")
            if uid not in state.sections:
                print("  Section not found."); pause(); continue
            sched = state.get_scheduler()
            r = sched.adjust_section(state.sections[uid])
            print(f"  Re-scheduled: {len(r['scheduled'])} placed")
            state.save(); pause()

        elif choice == "4":
            code = prompt("Elective course code")
            raw = prompt("Section UIDs (comma-separated)")
            secs = [state.sections[u.strip()] for u in raw.split(",")
                    if u.strip() in state.sections]
            if not secs: print("  No valid sections."); pause(); continue
            sched = state.get_scheduler()
            r = sched.add_elective_for_sections(code, secs)
            print(f"  Placed: {len(r['scheduled'])} elective sessions")
            state.save(); pause()

        elif choice == "5":
            engine = state.get_engine()
            rep = engine.validate()
            if not rep:
                print("\n  Timetable is valid — 0 conflicts.")
            else:
                print(f"\n  {len(rep.conflicts)} conflict(s):")
                for c in rep.conflicts[:20]: print(f"  - {c}")
            pause()

        elif choice == "6":
            if prompt("Clear entire timetable? (y/n)", "n").lower() == "y":
                state.timetable = Timetable()
                state.save()
                print("  Timetable cleared.")
            pause()

        elif choice == "0":
            break


# ══════════════════════════════════════════════════════════════════════
# EXPORT MENU
# ══════════════════════════════════════════════════════════════════════

def menu_export(state: AppState):
    while True:
        clear()
        print(HDIVIDER)
        print("  EXPORT TIMETABLE")
        print(HDIVIDER)
        faculties = sorted(set(s.faculty for s in state.timetable.sessions if s.faculty))
        print(f"  Faculties with sessions: {', '.join(faculties) if faculties else 'None'}")
        print()
        print("  1. Export ALL faculties to Excel (one sheet per faculty + combined)")
        print("  2. Export specific faculty to Excel")
        print("  3. Export all to text file")
        print("  4. Export buildings and rooms reference table")
        print("  0. Back")
        choice = prompt("Choice")

        os.makedirs("exports", exist_ok=True)

        if choice == "1":
            path = "exports/GIKI_Timetable_All_Spring2026.xlsx"
            try:
                export_excel(state.timetable, state.slots, state.courses, path)
                print(f"  Exported to: {path}")
                # Copy to outputs for download
                import shutil
                shutil.copy(path, f"/mnt/user-data/outputs/{os.path.basename(path)}")
                print(f"  Ready for download.")
            except Exception as e:
                print(f"  Export error: {e}")
            pause()

        elif choice == "2":
            print(f"  Available: {', '.join(faculties)}")
            fac = prompt("Faculty code (e.g. FCSE, FEE, SMgS)")
            if fac not in faculties:
                print("  No sessions for that faculty."); pause(); continue
            path = f"exports/GIKI_Timetable_{fac}_Spring2026.xlsx"
            try:
                export_excel(state.timetable, state.slots, state.courses,
                             path, faculty_filter=fac,
                             title=f"GIKI Timetable Spring 2026 — {fac}")
                import shutil
                shutil.copy(path, f"/mnt/user-data/outputs/{os.path.basename(path)}")
                print(f"  Exported to: {path} — ready for download.")
            except Exception as e:
                print(f"  Export error: {e}")
            pause()

        elif choice == "3":
            path = "exports/GIKI_Timetable_Spring2026.txt"
            export_text(state.timetable, state.slots, path)
            import shutil
            shutil.copy(path, f"/mnt/user-data/outputs/{os.path.basename(path)}")
            print(f"  Exported: {path}")
            pause()

        elif choice == "4":
            path = "exports/GIKI_Buildings_Rooms.xlsx"
            try:
                export_buildings_table_excel(path)
                import shutil
                shutil.copy(path, f"/mnt/user-data/outputs/{os.path.basename(path)}")
                print(f"  Buildings & rooms table exported: {path}")
            except Exception as e:
                print(f"  Export error: {e}")
            pause()

        elif choice == "0":
            break


# ══════════════════════════════════════════════════════════════════════
# CLASH CHECK MENU
# ══════════════════════════════════════════════════════════════════════

def menu_clash(state: AppState):
    clear()
    print(HDIVIDER)
    print("  CLASH CHECK / FREE SLOT FINDER")
    print(HDIVIDER)
    tid    = prompt("Teacher ID")
    uid    = prompt("Section UID")
    code   = prompt("Course code")
    stype  = prompt("Session type: 1=Lecture  2=Lab", "1")
    pref_t = prompt("Preferred time HH:MM (blank to skip)")

    if code not in state.courses:
        print("  Course not found."); pause(); return

    session_type = SessionType.LAB if stype == "2" else SessionType.LECTURE
    pref_min = None
    if pref_t:
        try:
            h, m = map(int, pref_t.split(":"))
            pref_min = h * 60 + m
        except ValueError:
            pass

    engine = state.get_engine()
    results = engine.find_free_slots(tid, uid, code, session_type)
    if pref_min:
        results.sort(key=lambda x: abs(
            state.slots[x["slot_id"]].start_min - pref_min
            if x["slot_id"] in state.slots else 9999
        ))

    if not results:
        print("\n  No free slots found.")
    else:
        print(f"\n  Found {len(results)} free slot(s):\n")
        print(f"  {'Slot ID':<18} {'Day':<12} {'Time':<16} {'Rooms'}")
        print(DIVIDER)
        for r in results[:20]:
            rooms_str = ", ".join(r["rooms"][:3])
            print(f"  {r['slot_id']:<18} {r['day']:<12} {r['time']:<16} {rooms_str}")
    pause()


# ══════════════════════════════════════════════════════════════════════
# VIEW MENU
# ══════════════════════════════════════════════════════════════════════

def menu_view(state: AppState):
    while True:
        clear()
        print(HDIVIDER); print("  VIEW TIMETABLE"); print(HDIVIDER)
        total = len(state.timetable.sessions)
        print(f"  Total sessions: {total}")
        print()
        print("  1. View by faculty")
        print("  2. View by section")
        print("  3. View by teacher")
        print("  4. View by day")
        print("  0. Back")
        choice = prompt("Choice")

        if choice == "1":
            fac = prompt("Faculty code (e.g. FCSE, SMgS, ALL)")
            sessions = (state.timetable.sessions if fac.upper() == "ALL"
                        else state.timetable.get_sessions_by_faculty(fac))
            _print_sessions(sessions, state)
            pause()
        elif choice == "2":
            uid = prompt("Section UID (blank=all)")
            sessions = (state.timetable.get_sessions_by_section(uid)
                        if uid else state.timetable.sessions)
            _print_sessions(sessions, state)
            pause()
        elif choice == "3":
            tid = prompt("Teacher ID")
            sessions = state.timetable.get_sessions_by_teacher(tid)
            _print_sessions(sessions, state)
            pause()
        elif choice == "4":
            _print_day_view(state)
            pause()
        elif choice == "0":
            break


def _print_sessions(sessions, state: AppState):
    if not sessions:
        print("  No sessions found."); return
    day_order = {d: i for i, d in enumerate(DayOfWeek)}
    sessions = sorted(sessions, key=lambda s: (
        day_order.get(state.slots[s.slot_id].day, 9) if s.slot_id in state.slots else 9,
        state.slots[s.slot_id].start_min if s.slot_id in state.slots else 0,
    ))
    print(f"\n  {'Section':<18} {'Course':<10} {'Type':<8} {'Day':<12} {'Time':<14} {'Room':<14} {'Teacher'}")
    print(DIVIDER)
    for s in sessions:
        slot = state.slots.get(s.slot_id)
        t = f"{slot.start_str}-{slot.end_str}" if slot else "?"
        d = slot.day.value if slot else "?"
        tp = "Lab" if s.session_type.value == "Lab" else "Lec"
        print(f"  {s.section_uid:<18} {s.course_code:<10} {tp:<8} {d:<12} {t:<14} {s.room_id:<14} {s.teacher_id}")


def _print_day_view(state: AppState):
    for day in DayOfWeek:
        day_slots = sorted(
            [s for s in state.slots.values() if s.day == day],
            key=lambda x: x.start_min
        )
        print(f"\n  --- {day.value} ---")
        for slot in day_slots:
            sessions = state.timetable.get_sessions_by_slot(slot.slot_id)
            if sessions:
                for s in sessions:
                    print(f"    {slot.start_str}-{slot.end_str}  "
                          f"{s.section_uid:<18} {s.course_code:<10} {s.room_id:<14} {s.teacher_id}")


# ══════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════

def main():
    state = AppState()
    try:
        state.load()
    except Exception as e:
        pass  # First run

    while True:
        clear()
        print(HDIVIDER)
        print("  GIKI UNIVERSITY TIMETABLE SCHEDULER  v2.0")
        print("  Faculty-aware | Variable credit hours | Multi-format import")
        print(HDIVIDER)
        print(f"  Slots: {len(state.slots)}  Rooms: {len(state.rooms)}  "
              f"Courses: {len(state.courses)}  Teachers: {len(state.teachers)}  "
              f"Sections: {len(state.sections)}  Sessions: {len(state.timetable.sessions)}")
        print()
        print("  1. Import courses from file (Excel / CSV / PDF)")
        print("  2. Scheduling")
        print("  3. View timetable")
        print("  4. Export timetable")
        print("  5. Clash check / Free slot finder")
        print("  6. Manage buildings & rooms")
        print("  0. Exit")
        print()
        choice = prompt("Choice")

        if   choice == "1": import_courses_from_file(state)
        elif choice == "2": menu_schedule(state)
        elif choice == "3": menu_view(state)
        elif choice == "4": menu_export(state)
        elif choice == "5": menu_clash(state)
        elif choice == "6": menu_buildings(state)
        elif choice == "0":
            print("\n  Goodbye.\n"); sys.exit(0)


def menu_buildings(state: AppState):
    while True:
        clear()
        print(HDIVIDER); print("  BUILDINGS & ROOMS"); print(HDIVIDER)
        print(f"  Buildings: {len(BUILDINGS)}  Rooms: {len(state.rooms)}")
        print()
        print("  1. View all buildings")
        print("  2. View all rooms")
        print("  3. Add building")
        print("  4. Add room")
        print("  5. Remove room")
        print("  0. Back")
        choice = prompt("Choice")

        if choice == "1":
            print(f"\n  {'ID':<12} {'Short':<12} {'Primary Faculties':<30} Name")
            print(DIVIDER)
            for bid, b in sorted(BUILDINGS.items()):
                print(f"  {bid:<12} {b.short_name:<12} {', '.join(b.faculty_home):<30} {b.name}")
            pause()
        elif choice == "2":
            from config.buildings import get_all_rooms_table
            rows = get_all_rooms_table()
            print(f"\n  {'Room ID':<14} {'Building':<12} {'Cap':<6} {'Type':<18} {'Priority'}")
            print(DIVIDER)
            for r in rows:
                print(f"  {r['room_id']:<14} {r['short']:<12} {r['capacity']:<6} {r['type']:<18} {r['priority_for']}")
            pause()
        elif choice == "3":
            from config.buildings import add_building
            bid = prompt("Building ID"); name = prompt("Full name")
            sn  = prompt("Short name"); fac = prompt("Primary faculties (comma-separated)")
            add_building(bid, name, sn, [f.strip() for f in fac.split(",")])
            print(f"  Building '{bid}' added.")
            pause()
        elif choice == "4":
            from config.buildings import add_room
            rid = prompt("Room ID"); bid = prompt("Building ID")
            cap = prompt("Capacity", "60"); lab = prompt("Is lab? (y/n)", "n")
            lt  = prompt("Lab type if lab (cyber/software/composite/chemistry/physics/computer)", "")
            pf  = prompt("Priority faculties (comma-separated)")
            notes = prompt("Notes")
            add_room(rid, bid, int(cap), lab.lower()=="y", lt or None,
                     [f.strip() for f in pf.split(",") if f.strip()], notes)
            print(f"  Room '{rid}' added.")
            pause()
        elif choice == "5":
            from config.buildings import remove_room
            rid = prompt("Room ID to remove")
            remove_room(rid)
            print(f"  Room '{rid}' removed.")
            pause()
        elif choice == "0":
            break


if __name__ == "__main__":
    main()

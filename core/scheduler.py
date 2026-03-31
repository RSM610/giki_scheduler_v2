"""
GIKI Scheduler v2 - Greedy First-Fit with Faculty-Aware Room Routing
=====================================================================
Key addition over v1: faculty and lab-type routing.
CyberLab -> CyS courses first, then other FCSE.
Composite Lab -> FMCE courses only.
HM/MS courses -> Brabers first.
etc.
"""

from __future__ import annotations
from core.models import (
    Timetable, ScheduledSession, Section, Course,
    Teacher, TimeSlot, SessionType, DayOfWeek
)
from config.buildings import ROOMS, get_preferred_rooms, get_faculty_from_code


class ConflictReport:
    def __init__(self):
        self.has_conflict = False
        self.conflicts = []
        self.warnings = []

    def add(self, msg: str):
        self.has_conflict = True
        self.conflicts.append(msg)

    def __bool__(self):
        return self.has_conflict


class ConstraintEngine:
    """O(1) conflict checks using composite hash indexes."""

    def __init__(self, timetable, slots, rooms, teachers, courses):
        self.tt       = timetable
        self.slots    = slots
        self.rooms    = rooms
        self.teachers = teachers
        self.courses  = courses

    def check_all(self, section_uid, teacher_id, course_code,
                  slot_id, room_id, session_type, exclude=None) -> ConflictReport:
        r = ConflictReport()
        slot = self.slots.get(slot_id)
        if not slot:
            r.add(f"Slot '{slot_id}' not found"); return r

        course  = self.courses.get(course_code)
        teacher = self.teachers.get(teacher_id)

        # 1. Teacher day unavailability — O(1)
        if teacher and teacher.is_unavailable_on(slot.day):
            r.add(f"Teacher '{teacher_id}' unavailable on {slot.day.value}"); return r

        # 2. Teacher exact-slot conflict — O(1)
        if self.tt.is_teacher_booked_at(slot_id, teacher_id, exclude):
            r.add(f"Teacher '{teacher_id}' already in slot '{slot_id}'"); return r

        # 3. Room exact-slot conflict — O(1)
        if self.tt.is_room_booked_at(slot_id, room_id, exclude):
            r.add(f"Room '{room_id}' already booked in slot '{slot_id}'"); return r

        # 4. Section exact-slot conflict — O(1)
        if self.tt.is_section_booked_at(slot_id, section_uid, exclude):
            r.add(f"Section '{section_uid}' already has session in slot '{slot_id}'"); return r

        # 5. Course day restriction — O(1)
        if course and course.is_restricted_on(slot.day):
            r.add(f"Course '{course_code}' restricted on {slot.day.value}"); return r

        # 6. Room type match — O(1)
        room = self.rooms.get(room_id)
        if room:
            if session_type == SessionType.LAB and not room.is_lab:
                r.add(f"Room '{room_id}' is not a lab room"); return r
            if session_type == SessionType.LECTURE and room.is_lab:
                r.add(f"Room '{room_id}' is a lab room, need lecture room"); return r

        # 7. Overlapping slots (cross-duration: lab vs lecture) — O(k)
        for existing in self.tt.get_sessions_by_teacher(teacher_id):
            if existing is exclude: continue
            if existing.slot_id == slot_id: continue
            ex_slot = self.slots.get(existing.slot_id)
            if ex_slot and slot.conflicts_with(ex_slot):
                r.add(f"Teacher '{teacher_id}' time overlap at {slot} vs {ex_slot}"); return r

        return r

    def find_free_slots(self, teacher_id, section_uid, course_code,
                        session_type, preferred_rooms=None) -> list[dict]:
        """O(N*R) with O(1) per check."""
        course = self.courses.get(course_code)
        results = []

        day_order = {d: i for i, d in enumerate(DayOfWeek)}
        ordered_slots = sorted(
            self.slots.values(),
            key=lambda s: (day_order[s.day], s.start_min)
        )

        for slot in ordered_slots:
            # Duration must match session type
            expected_dur = (course.session_duration if course
                           else (180 if session_type == SessionType.LAB else 50))
            if slot.duration != expected_dur:
                continue

            free_rooms = []
            rooms_to_try = preferred_rooms or [r for r in self.rooms
                                                if not self.rooms[r].is_lab ==
                                                (session_type == SessionType.LAB)]

            for room_id in rooms_to_try:
                report = self.check_all(
                    section_uid, teacher_id, course_code,
                    slot.slot_id, room_id, session_type
                )
                if not report:
                    free_rooms.append(room_id)

            if free_rooms:
                results.append({
                    "slot_id": slot.slot_id,
                    "day": slot.day.value,
                    "time": f"{slot.start_str}-{slot.end_str}",
                    "rooms": free_rooms,
                })

        return results

    def validate(self) -> ConflictReport:
        """Full timetable validation. O(s^2) worst case."""
        r = ConflictReport()
        sessions = self.tt.sessions
        from collections import defaultdict
        by_slot = defaultdict(list)
        for s in sessions:
            by_slot[s.slot_id].append(s)

        for slot_id, group in by_slot.items():
            for i, a in enumerate(group):
                for b in group[i+1:]:
                    if a.teacher_id == b.teacher_id:
                        r.add(f"TEACHER CLASH: {a.teacher_id} in slot {slot_id}")
                    if a.room_id == b.room_id:
                        r.add(f"ROOM CLASH: {a.room_id} in slot {slot_id}")
                    if a.section_uid == b.section_uid:
                        r.add(f"SECTION CLASH: {a.section_uid} in slot {slot_id}")
        return r


class GIKIScheduler:
    """
    Greedy First-Fit scheduler with faculty-aware room routing.

    Room selection priority:
      1. Faculty's home building rooms (from FACULTY_ROUTING)
      2. Lab type matching (CyberLab for CY courses, etc.)
      3. Capacity check
      4. Fallback to any valid room
    """

    def __init__(self, timetable, slots, rooms, teachers, courses):
        self.tt       = timetable
        self.slots    = slots
        self.rooms    = rooms
        self.teachers = teachers
        self.courses  = courses
        self.engine   = ConstraintEngine(timetable, slots, rooms, teachers, courses)

        day_order = {d: i for i, d in enumerate(DayOfWeek)}
        self._sorted_slots = sorted(
            slots.values(),
            key=lambda s: (day_order[s.day], s.start_min)
        )

    def _get_candidate_rooms(self, course_code: str, session_type: SessionType,
                              num_students: int = 30) -> list[str]:
        """
        Returns ordered list of candidate room_ids for this course.
        Faculty routing + lab type matching + capacity filter.
        """
        course = self.courses.get(course_code)
        lab_type = course.lab_type if course else None

        preferred = get_preferred_rooms(
            course_code,
            is_lab=(session_type == SessionType.LAB),
            lab_type=lab_type,
            num_students=num_students,
        )

        # Filter: rooms must exist and match lab/lecture type
        is_lab = (session_type == SessionType.LAB)
        result = []
        for rid in preferred:
            room = self.rooms.get(rid)
            if room and room.is_lab == is_lab:
                result.append(rid)

        # Fallback: any room of correct type with enough capacity
        if not result:
            result = [rid for rid, room in self.rooms.items()
                      if room.is_lab == is_lab
                      and room.capacity >= max(1, num_students)]

        return result

    def schedule_section(self, section: Section,
                          preferred_days=None) -> dict:
        """
        Schedule all sessions for one section.
        Credit hours = number of sessions. Any value 1-4+.
        """
        course = self.courses.get(section.course_code)
        if not course:
            return {"scheduled": [], "unscheduled": [1],
                    "warnings": [f"Course '{section.course_code}' not found"]}

        num_sessions = course.weekly_sessions
        candidate_rooms = self._get_candidate_rooms(
            section.course_code, course.session_type, section.num_students
        )

        # Order slots by preferred days first
        if preferred_days:
            day_pref = {d: i for i, d in enumerate(preferred_days)}
            ordered = sorted(self._sorted_slots,
                key=lambda s: (day_pref.get(s.day, 99), s.start_min))
        else:
            ordered = self._sorted_slots

        scheduled, unscheduled = [], []

        for idx in range(1, num_sessions + 1):
            placed = False
            for slot in ordered:
                if placed: break
                if slot.duration != course.session_duration:
                    continue
                for room_id in candidate_rooms:
                    report = self.engine.check_all(
                        section.uid, section.teacher_id, section.course_code,
                        slot.slot_id, room_id, course.session_type
                    )
                    if not report:
                        sess = ScheduledSession(
                            section_uid   = section.uid,
                            course_code   = section.course_code,
                            session_type  = course.session_type,
                            slot_id       = slot.slot_id,
                            room_id       = room_id,
                            teacher_id    = section.teacher_id,
                            batch_year    = section.batch_year,
                            faculty       = section.faculty,
                            session_index = idx,
                        )
                        self.tt.add_session(sess)
                        scheduled.append(sess)
                        placed = True
                        break

            if not placed:
                unscheduled.append(idx)

        return {
            "scheduled":   scheduled,
            "unscheduled": unscheduled,
            "warnings": ([f"Could not place {len(unscheduled)} session(s) "
                          f"for '{section.uid}'"] if unscheduled else []),
        }

    def schedule_all(self, sections, preferred_days=None) -> dict:
        """MCV-ordered greedy scheduling of all sections."""
        # Most constrained first
        sorted_secs = sorted(
            sections,
            key=lambda s: (self.courses.get(s.course_code,
                           type('X', (), {'weekly_sessions': 0})()).weekly_sessions),
            reverse=True
        )
        all_results = {}
        warnings = []
        for sec in sorted_secs:
            r = self.schedule_section(sec, preferred_days)
            all_results[sec.uid] = r
            warnings.extend(r["warnings"])
        return {"results": all_results, "warnings": warnings}

    def adjust_section(self, section, preferred_days=None) -> dict:
        """Re-schedule a section. O(k) clear + O(h*N*R) reschedule."""
        self.tt.clear_section(section.uid)
        return self.schedule_section(section, preferred_days)

    def add_elective_for_sections(self, course_code, sections) -> dict:
        """Schedule a shared elective across multiple sections."""
        course = self.courses.get(course_code)
        if not course:
            return {"error": f"Course '{course_code}' not found"}

        candidate_rooms = self._get_candidate_rooms(
            course_code, course.session_type, 60
        )
        scheduled, unscheduled = [], []

        for idx in range(1, course.weekly_sessions + 1):
            placed = False
            for slot in self._sorted_slots:
                if placed: break
                if slot.duration != course.session_duration: continue

                all_clear = True
                for sec in sections:
                    r = self.engine.check_all(
                        sec.uid, sec.teacher_id, course_code,
                        slot.slot_id, candidate_rooms[0] if candidate_rooms else "",
                        course.session_type
                    )
                    if r:
                        all_clear = False
                        break

                if not all_clear: continue

                for room_id in candidate_rooms:
                    if self.tt.is_room_booked_at(slot.slot_id, room_id):
                        continue
                    for sec in sections:
                        sess = ScheduledSession(
                            section_uid=sec.uid, course_code=course_code,
                            session_type=course.session_type, slot_id=slot.slot_id,
                            room_id=room_id, teacher_id=sec.teacher_id,
                            batch_year=sec.batch_year, faculty=sec.faculty,
                            session_index=idx
                        )
                        self.tt.add_session(sess)
                        scheduled.append(sess)
                    placed = True
                    break

            if not placed:
                unscheduled.append(idx)

        return {"scheduled": scheduled, "unscheduled": unscheduled}

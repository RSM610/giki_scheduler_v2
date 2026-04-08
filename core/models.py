"""
GIKI Scheduler v2 - Core Models
================================
O(1) composite hash index for conflict detection.
Supports variable credit hours (1,2,3,4+), labs (3hr), lectures (50min).

Cohort isolation:
- A "cohort" is a group of students sharing the same curriculum stream:
  (batch_year, faculty, section_id).  No two courses from the same cohort
  may occupy the same timeslot.
- When for_program is set (e.g. "CY", "DS") a finer-grained check is also
  applied: (batch_year, for_program, section_id) → one course per slot.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DayOfWeek(Enum):
    MONDAY    = "Monday"
    TUESDAY   = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY  = "Thursday"
    FRIDAY    = "Friday"

    @classmethod
    def from_str(cls, s: str) -> "DayOfWeek":
        mapping = {"mon":"MONDAY","tue":"TUESDAY","wed":"WEDNESDAY",
                   "thu":"THURSDAY","fri":"FRIDAY"}
        return cls[mapping.get(s.lower()[:3], s.upper())]


class SessionType(Enum):
    LECTURE = "Lecture"   # 50 min
    LAB     = "Lab"       # 180 min (3 hr)


@dataclass
class TimeSlot:
    slot_id:   str
    day:       DayOfWeek
    start_min: int    # minutes from midnight
    duration:  int    # 50 or 180

    @property
    def end_min(self) -> int:
        return self.start_min + self.duration

    @property
    def start_str(self) -> str:
        h, m = divmod(self.start_min, 60)
        return f"{h:02d}:{m:02d}"

    @property
    def end_str(self) -> str:
        h, m = divmod(self.end_min, 60)
        return f"{h:02d}:{m:02d}"

    def conflicts_with(self, other: "TimeSlot") -> bool:
        """O(1): interval overlap test."""
        if self.day != other.day:
            return False
        return self.start_min < other.end_min and other.start_min < self.end_min

    def __repr__(self) -> str:
        return f"{self.day.value} {self.start_str}-{self.end_str}"


@dataclass
class Teacher:
    teacher_id:       str
    name:             str
    faculty:          str = ""
    unavailable_days: list = field(default_factory=list)
    _unavail_set:     frozenset = field(default_factory=frozenset, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_unavail_set', frozenset(self.unavailable_days))

    def is_unavailable_on(self, day: DayOfWeek) -> bool:
        return day in self._unavail_set


@dataclass
class Course:
    course_code:     str
    title:           str
    credit_hours:    int       # number of weekly sessions per section
    session_type:    SessionType = SessionType.LECTURE
    faculty:         str = ""
    restricted_days: list = field(default_factory=list)
    lab_type:        str = ""  # "cyber","software","composite","chemistry","computer"
    _restricted_set: frozenset = field(default_factory=frozenset, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_restricted_set', frozenset(self.restricted_days))

    def is_restricted_on(self, day: DayOfWeek) -> bool:
        return day in self._restricted_set

    @property
    def session_duration(self) -> int:
        return 180 if self.session_type == SessionType.LAB else 50

    @property
    def weekly_sessions(self) -> int:
        return self.credit_hours


@dataclass
class Section:
    section_id:   str
    course_code:  str
    teacher_id:   str
    batch_year:   int
    faculty:      str
    num_students: int = 30
    for_program:  str = ""

    @property
    def uid(self) -> str:
        return f"{self.course_code}-{self.section_id}"


@dataclass
class ScheduledSession:
    section_uid:   str
    course_code:   str
    session_type:  SessionType
    slot_id:       str
    room_id:       str
    teacher_id:    str
    batch_year:    int
    faculty:       str
    session_index: int = 1
    # section_id is the label part of section_uid (e.g. "A" from "CS201-A")
    section_id:    str = ""
    # for_program enables program-level clash checks (e.g. "CY", "DS")
    for_program:   str = ""

    def to_dict(self) -> dict:
        return {
            "section_uid":   self.section_uid,
            "course_code":   self.course_code,
            "session_type":  self.session_type.value,
            "slot_id":       self.slot_id,
            "room_id":       self.room_id,
            "teacher_id":    self.teacher_id,
            "batch_year":    self.batch_year,
            "faculty":       self.faculty,
            "session_index": self.session_index,
            "section_id":    self.section_id,
            "for_program":   self.for_program,
        }


class Timetable:
    """
    O(1) conflict detection via composite hash indexes.
    Three composite dicts for teacher/room/section slot occupancy.
    add_session: O(1) amortized. clear_section: O(k).

    Cohort isolation indexes:
      _dept_cohort_at_slot  : (slot_id, batch_year, faculty, section_id) → session
          Prevents two courses for the same department/semester/section cohort
          from sharing a timeslot (Requirement 1).
      _prog_cohort_at_slot  : (slot_id, batch_year, for_program, section_id) → session
          Finer-grained check for named programs (CY, DS, etc.) — Requirement 3.
    """

    def __init__(self):
        self.sessions: list[ScheduledSession] = []
        self._slot_index:    dict[str, list] = {}
        self._teacher_index: dict[str, list] = {}
        self._section_index: dict[str, list] = {}
        # Composite O(1) conflict indexes
        self._teacher_at_slot: dict[tuple, ScheduledSession] = {}
        self._room_at_slot:    dict[tuple, ScheduledSession] = {}
        self._section_at_slot: dict[tuple, ScheduledSession] = {}
        # Cohort isolation — Req 1 & 3
        self._dept_cohort_at_slot: dict[tuple, ScheduledSession] = {}
        self._prog_cohort_at_slot: dict[tuple, ScheduledSession] = {}
        
        # Cohort session indexes for overlap checking
        self._dept_cohort_index: dict[tuple, list] = {}
        self._prog_cohort_index: dict[tuple, list] = {}

    def _cohort_keys(self, s: ScheduledSession):
        """Return the (dept_key, prog_key) tuple for cohort index lookups."""
        dept_key = (s.slot_id, s.batch_year, s.faculty, s.section_id)
        prog_key = ((s.slot_id, s.batch_year, s.for_program, s.section_id)
                    if s.for_program else None)
        return dept_key, prog_key

    def add_session(self, s: ScheduledSession):
        self.sessions.append(s)
        self._slot_index.setdefault(s.slot_id, []).append(s)
        self._teacher_index.setdefault(s.teacher_id, []).append(s)
        self._section_index.setdefault(s.section_uid, []).append(s)
        self._teacher_at_slot[(s.slot_id, s.teacher_id)] = s
        self._room_at_slot[(s.slot_id, s.room_id)]       = s
        self._section_at_slot[(s.slot_id, s.section_uid)] = s
        # Cohort isolation
        dk, pk = self._cohort_keys(s)
        self._dept_cohort_at_slot[dk] = s
        if pk:
            self._prog_cohort_at_slot[pk] = s
            
        # Index for overlaps
        if s.batch_year and s.faculty and s.section_id:
            d_idx = (s.batch_year, s.faculty, s.section_id)
            self._dept_cohort_index.setdefault(d_idx, []).append(s)
        if s.batch_year and s.for_program and s.section_id:
            p_idx = (s.batch_year, s.for_program, s.section_id)
            self._prog_cohort_index.setdefault(p_idx, []).append(s)

    def remove_session(self, s: ScheduledSession):
        try: self.sessions.remove(s)
        except ValueError: pass
        self._teacher_at_slot.pop((s.slot_id, s.teacher_id), None)
        self._room_at_slot.pop((s.slot_id, s.room_id), None)
        self._section_at_slot.pop((s.slot_id, s.section_uid), None)
        # Cohort isolation
        dk, pk = self._cohort_keys(s)
        self._dept_cohort_at_slot.pop(dk, None)
        if pk:
            self._prog_cohort_at_slot.pop(pk, None)
            
        # Cohort index cleanup
        d_idx = (s.batch_year, s.faculty, s.section_id)
        if d_idx in self._dept_cohort_index:
            try: self._dept_cohort_index[d_idx].remove(s)
            except ValueError: pass
            if not self._dept_cohort_index[d_idx]:
                self._dept_cohort_index.pop(d_idx, None)
        
        if s.for_program:
            p_idx = (s.batch_year, s.for_program, s.section_id)
            if p_idx in self._prog_cohort_index:
                try: self._prog_cohort_index[p_idx].remove(s)
                except ValueError: pass
                if not self._prog_cohort_index[p_idx]:
                    self._prog_cohort_index.pop(p_idx, None)
        for bucket, key in [(self._slot_index, s.slot_id),
                             (self._teacher_index, s.teacher_id),
                             (self._section_index, s.section_uid)]:
            lst = bucket.get(key, [])
            try: lst.remove(s)
            except ValueError: pass
            if not lst: bucket.pop(key, None)

    def is_teacher_booked_at(self, slot_id: str, teacher_id: str,
                              exclude=None) -> bool:
        existing = self._teacher_at_slot.get((slot_id, teacher_id))
        if existing is None: return False
        if exclude is not None and existing is exclude: return False
        return True

    def is_room_booked_at(self, slot_id: str, room_id: str,
                           exclude=None) -> bool:
        existing = self._room_at_slot.get((slot_id, room_id))
        if existing is None: return False
        if exclude is not None and existing is exclude: return False
        return True

    def is_section_booked_at(self, slot_id: str, section_uid: str,
                              exclude=None) -> bool:
        existing = self._section_at_slot.get((slot_id, section_uid))
        if existing is None: return False
        if exclude is not None and existing is exclude: return False
        return True

    def is_dept_cohort_booked_at(self, slot_id: str, batch_year: int,
                                  faculty: str, section_id: str,
                                  exclude=None, slot_obj=None, all_slots=None) -> bool:
        """Req 1: prevent two courses for the same department/semester/section
        from occupying the same timeslot, including cross-duration overlaps."""
        if not batch_year or not faculty or not section_id:
            return False
            
        # Exact slot match
        existing = self._dept_cohort_at_slot.get((slot_id, batch_year, faculty, section_id))
        if existing is not None and existing is not exclude:
            return True
            
        # Cross-duration overlap check (e.g., lab overlaps with lecture)
        if slot_obj and all_slots:
            d_idx = (batch_year, faculty, section_id)
            for sess in self._dept_cohort_index.get(d_idx, []):
                if sess is exclude: continue
                if sess.slot_id == slot_id: continue
                ex_slot = all_slots.get(sess.slot_id)
                if ex_slot and slot_obj.conflicts_with(ex_slot):
                    return True
                    
        return False

    def is_prog_cohort_booked_at(self, slot_id: str, batch_year: int,
                                  for_program: str, section_id: str,
                                  exclude=None, slot_obj=None, all_slots=None) -> bool:
        """Req 3: prevent two courses for the same program cohort (e.g. CY, DS)
        from occupying the same timeslot, including cross-duration overlaps."""
        if not batch_year or not for_program or not section_id:
            return False
            
        existing = self._prog_cohort_at_slot.get((slot_id, batch_year, for_program, section_id))
        if existing is not None and existing is not exclude:
            return True
            
        if slot_obj and all_slots:
            p_idx = (batch_year, for_program, section_id)
            for sess in self._prog_cohort_index.get(p_idx, []):
                if sess is exclude: continue
                if sess.slot_id == slot_id: continue
                ex_slot = all_slots.get(sess.slot_id)
                if ex_slot and slot_obj.conflicts_with(ex_slot):
                    return True
                    
        return False

    def get_sessions_by_slot(self, slot_id: str) -> list:
        return self._slot_index.get(slot_id, [])

    def get_sessions_by_teacher(self, teacher_id: str) -> list:
        return self._teacher_index.get(teacher_id, [])

    def get_sessions_by_section(self, section_uid: str) -> list:
        return self._section_index.get(section_uid, [])

    def get_sessions_by_faculty(self, faculty: str) -> list:
        return [s for s in self.sessions if s.faculty == faculty]

    def clear_section(self, section_uid: str):
        for sess in list(self._section_index.get(section_uid, [])):
            self.remove_session(sess)

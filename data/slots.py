"""
GIKI Time Slots - Spring 2026
==============================
Derived from official timetable.
Mon-Thu: 8 slots (50min). Friday: shorter schedule.
Labs: 3-hour blocks (Cyber Lab has named slots 1 and 2).
"""

from core.models import TimeSlot, DayOfWeek


def build_giki_slots() -> dict[str, TimeSlot]:
    """Build official GIKI Spring 2026 time slots."""
    slots = {}

    # Mon-Thu lecture slots (50 min each)
    lecture_times = [
        (480, "0800"),   # 08:00-08:50
        (540, "0900"),   # 09:00-09:50
        (630, "1030"),   # 10:30-11:20
        (690, "1130"),   # 11:30-12:20
        (750, "1230"),   # 12:30-13:20
        (870, "1430"),   # 14:30-15:20
        (930, "1530"),   # 15:30-16:20
        (990, "1630"),   # 16:30-17:20
    ]

    # Friday lecture slots (different grid)
    friday_lecture_times = [
        (480, "0800"),   # 08:00-08:50
        (540, "0900"),   # 09:00-09:50
        (600, "1000"),   # 10:00-10:50
        (660, "1100"),   # 11:00-11:50
        (720, "1200"),   # 12:00-12:50
        (870, "1430"),   # 14:30-15:20
        (930, "1530"),   # 15:30-16:20
        (990, "1630"),   # 16:30-17:20
    ]

    days_mf = [
        (DayOfWeek.MONDAY,    "MON"),
        (DayOfWeek.TUESDAY,   "TUE"),
        (DayOfWeek.WEDNESDAY, "WED"),
        (DayOfWeek.THURSDAY,  "THU"),
    ]

    # Lecture slots Mon-Thu
    for day, abbr in days_mf:
        for start_min, time_str in lecture_times:
            slot_id = f"L-{abbr}-{time_str}"
            slots[slot_id] = TimeSlot(slot_id, day, start_min, 50)

    # Friday lecture slots
    for start_min, time_str in friday_lecture_times:
        slot_id = f"L-FRI-{time_str}"
        slots[slot_id] = TimeSlot(slot_id, DayOfWeek.FRIDAY, start_min, 50)

    # Lab slots (3 hour = 180 min) - two per day Mon-Thu
    lab_starts = [(480, "0800"), (660, "1100")]
    for day, abbr in days_mf:
        for i, (start_min, time_str) in enumerate(lab_starts, 1):
            slot_id = f"LAB-{abbr}-{i}"
            slots[slot_id] = TimeSlot(slot_id, day, start_min, 180)

    # Cyber Lab named slots (Thursday - matches existing timetable)
    slots["CYBER-THU-SLOT1"] = TimeSlot("CYBER-THU-SLOT1", DayOfWeek.THURSDAY, 870, 180)
    slots["CYBER-THU-SLOT2"] = TimeSlot("CYBER-THU-SLOT2", DayOfWeek.THURSDAY, 930, 50)  # second slot

    return slots


def get_slot_display(slot_id: str, slots: dict) -> str:
    """Human-readable slot string."""
    s = slots.get(slot_id)
    if not s:
        return slot_id
    return f"{s.day.value[:3]} {s.start_str}-{s.end_str}"

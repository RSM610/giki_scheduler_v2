"""
GIKI Time Slots
Lectures: 50 min. Labs: 180 min (3-hour blocks at standard period starts).

All five days share identical lecture start times so the timetable grid
has no overlapping time columns.

Lab slots start at 09:00.  Lab 09:00-12:00 ends exactly at 12:00
so it does not overlap the 12:00 lecture slot (strict-inequality overlap test).

Normal last slot : 16:30-17:20
Extended last slot: 19:30-20:20  (enabled via extended=True)
"""
from core.models import TimeSlot, DayOfWeek

# Lab block start times (minutes from midnight).
# Normal:   09:00 | 12:30 | 14:30
# Extended: adds   16:30 evening lab (16:30-19:30)
_LAB_STARTS          = [540, 750, 870]        # 09:00, 12:30, 14:30
_LAB_STARTS_EXTENDED = [540, 750, 870, 990]   # + 16:30-19:30 evening lab

def build_giki_slots(extended: bool = False) -> dict[str, TimeSlot]:
    slots: dict[str, TimeSlot] = {}

    # ── Unified lecture starts (same for all 5 days) ──────────────────────────
    # Normal  : 08:00 09:00 10:00 11:00 12:00 14:30 15:30 16:30
    # Extended: adds  17:30 18:30 19:30
    lecture_starts = [480, 540, 600, 660, 720, 870, 930, 990]
    extended_starts = [1050, 1110, 1170]   # 17:30, 18:30, 19:30

    all_days = [
        (DayOfWeek.MONDAY,    "MON"),
        (DayOfWeek.TUESDAY,   "TUE"),
        (DayOfWeek.WEDNESDAY, "WED"),
        (DayOfWeek.THURSDAY,  "THU"),
        (DayOfWeek.FRIDAY,    "FRI"),
    ]

    # ── Lecture slots ─────────────────────────────────────────────────────────
    for day, abbr in all_days:
        starts = lecture_starts + (extended_starts if extended else [])
        for sm in starts:
            h, m = divmod(sm, 60)
            sid = f"L-{abbr}-{h:02d}{m:02d}"
            slots[sid] = TimeSlot(sid, day, sm, 50)

    # ── Lab slots ─────────────────────────────────────────────────────────────
    lab_starts = _LAB_STARTS_EXTENDED if extended else _LAB_STARTS

    for day, abbr in all_days:
        for ls in lab_starts:
            h, m = divmod(ls, 60)
            sid = f"LAB-{abbr}-{h:02d}{m:02d}"
            slots[sid] = TimeSlot(sid, day, ls, 180)

    return slots


def get_all_lecture_slots_ordered(slots: dict) -> list:
    """Return lecture slots in day+time order for grid display."""
    day_order = {d: i for i, d in enumerate(DayOfWeek)}
    return sorted(
        [s for s in slots.values() if s.duration == 50],
        key=lambda s: (day_order[s.day], s.start_min)
    )
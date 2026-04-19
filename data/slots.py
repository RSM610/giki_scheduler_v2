"""
GIKI Time Slots
Lectures: 50 min. Labs: 180 min (3-hour blocks at standard period starts).

All five days share identical lecture start times so the timetable grid
has no overlapping time columns.

Lab slots start at 09:00.  Lab 09:00-12:00 ends exactly at 12:00
so it does not overlap the 12:00 lecture slot (strict-inequality overlap test).

Last slot: 16:30-17:20 (no slots after 17:30).
"""
from core.models import TimeSlot, DayOfWeek

# Lab block start times (minutes from midnight).
# 09:00-12:00 | 12:30-15:30 | 14:30-17:30
# (the last two overlap, but different sections can use either; the constraint
# engine prevents the same cohort from taking both on the same day.)
_LAB_STARTS = [540, 750, 870]                   # 09:00, 12:30, 14:30
_LAB_STARTS_EXTENDED = [540, 750, 870]          # same — no slots after 17:30

def build_giki_slots(extended: bool = False) -> dict[str, TimeSlot]:
    slots: dict[str, TimeSlot] = {}

    # ── Unified lecture starts (same for all 5 days) ──────────────────────────
    # 8 periods per day with 10-minute breaks between each.
    # No cross-day overlaps: every (start_min, duration) pair maps to exactly
    # one column in the timetable grid regardless of day.
    lecture_starts = [480, 540, 600, 660, 720, 870, 930, 990]
    # 08:00  09:00  10:00  11:00  12:00  14:30  15:30  16:30
    extended_starts = []   # no slots after 17:30

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

    # ── Lab slots: 3 per day at standard lecture-aligned start times ──────────
    lab_starts = _LAB_STARTS_EXTENDED if extended else _LAB_STARTS

    for day, abbr in all_days:
        for i, ls in enumerate(lab_starts):
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

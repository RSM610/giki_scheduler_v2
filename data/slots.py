"""
GIKI Time Slots
Lectures: 50 min. Labs: 180 min (3-hour blocks at standard period starts).

Lab slots are placed at the SAME start times as lectures (8:00, 12:30, 14:30)
so the timetable grid stays clean — lecture and lab share column headers.
The constraint engine prevents a cohort from having a lecture AND lab at the
same or overlapping time.

Default end: 17:30. Extended: 19:30 (7:30pm).
"""
from core.models import TimeSlot, DayOfWeek

# Lab block start times (minutes from midnight) — align with lecture starts so
# the grid header stays tidy.  These produce three non-overlapping lab columns:
#   08:00-11:00 | 12:30-15:30 | 14:30-17:30
# (the last two overlap, but different sections can use either; the constraint
# engine prevents the same cohort from taking both on the same day.)
_LAB_STARTS = [480, 750, 870]         # 08:00, 12:30, 14:30
_LAB_STARTS_EXTENDED = [480, 750, 870, 1020]   # + 17:00

def build_giki_slots(extended: bool = False) -> dict[str, TimeSlot]:
    slots: dict[str, TimeSlot] = {}

    # ── Lecture starts ────────────────────────────────────────────────────
    # Mon-Thu: 8 periods
    lecture_starts_mth = [480, 540, 630, 690, 750, 870, 930, 990]
    # Friday: different mid-morning grid
    lecture_starts_fri = [480, 540, 600, 660, 720, 870, 930, 990]
    # Optional evening extension
    extended_starts = [1050, 1110]   # 17:30, 18:30

    days_mth = [
        (DayOfWeek.MONDAY,    "MON"),
        (DayOfWeek.TUESDAY,   "TUE"),
        (DayOfWeek.WEDNESDAY, "WED"),
        (DayOfWeek.THURSDAY,  "THU"),
    ]

    # ── Mon–Thu lecture slots ─────────────────────────────────────────────
    for day, abbr in days_mth:
        starts = lecture_starts_mth + (extended_starts if extended else [])
        for sm in starts:
            h, m = divmod(sm, 60)
            sid = f"L-{abbr}-{h:02d}{m:02d}"
            slots[sid] = TimeSlot(sid, day, sm, 50)

    # ── Friday lecture slots ───────────────────────────────────────────────
    fri_starts = lecture_starts_fri + (extended_starts if extended else [])
    for sm in fri_starts:
        h, m = divmod(sm, 60)
        sid = f"L-FRI-{h:02d}{m:02d}"
        slots[sid] = TimeSlot(sid, DayOfWeek.FRIDAY, sm, 50)

    # ── Lab slots: 3 per day at standard lecture-aligned start times ───────
    # Using the same start-minute as a lecture means the grid shows adjacent
    # "08:00 Lec" / "08:00 Lab" columns — clean and predictable.
    lab_starts = _LAB_STARTS_EXTENDED if extended else _LAB_STARTS

    all_days = days_mth + [(DayOfWeek.FRIDAY, "FRI")]
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

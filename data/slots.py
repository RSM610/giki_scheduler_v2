"""
GIKI Time Slots
Lectures: 50 min. Labs: 180 min, can fall anywhere a 3-hr block fits.
Default end: 17:30. Extended: 19:30 (7:30pm).
"""
from core.models import TimeSlot, DayOfWeek

def build_giki_slots(extended: bool = False) -> dict[str, TimeSlot]:
    slots = {}
    # Mon-Thu: 8 lecture slots standard
    lecture_starts_mth = [480,540,630,690,750,870,930,990]  # 08,09,10:30,11:30,12:30,14:30,15:30,16:30
    # Friday: different grid
    lecture_starts_fri = [480,540,600,660,720,870,930,990]  # 08,09,10,11,12,14:30,15:30,16:30
    # Extended evening slots (optional)
    extended_starts = [1050, 1110]  # 17:30, 18:30

    days_mth = [(DayOfWeek.MONDAY,"MON"),(DayOfWeek.TUESDAY,"TUE"),
                (DayOfWeek.WEDNESDAY,"WED"),(DayOfWeek.THURSDAY,"THU")]

    for day, abbr in days_mth:
        starts = lecture_starts_mth + (extended_starts if extended else [])
        for sm in starts:
            h,m = divmod(sm,60)
            sid = f"L-{abbr}-{h:02d}{m:02d}"
            slots[sid] = TimeSlot(sid, day, sm, 50)
        # Lab slots: every 3-hr block that fits in the day (flexible)
        # 08:00-11:00, 09:00-12:00, 10:30-13:30, 11:30-14:30, 14:30-17:30
        lab_starts = [480,540,630,690,870]
        if extended:
            lab_starts += [930,990,1050]
        for i,ls in enumerate(lab_starts):
            sid = f"LAB-{abbr}-{i+1}"
            slots[sid] = TimeSlot(sid, day, ls, 180)

    # Friday
    fri_starts = lecture_starts_fri + (extended_starts if extended else [])
    for sm in fri_starts:
        h,m = divmod(sm,60)
        sid = f"L-FRI-{h:02d}{m:02d}"
        slots[sid] = TimeSlot(sid, DayOfWeek.FRIDAY, sm, 50)
    for i,ls in enumerate([480,540,600,660,870]):
        slots[f"LAB-FRI-{i+1}"] = TimeSlot(f"LAB-FRI-{i+1}", DayOfWeek.FRIDAY, ls, 180)

    return slots

def get_all_lecture_slots_ordered(slots: dict) -> list:
    """Return lecture slots in day+time order for grid display."""
    from core.models import DayOfWeek
    day_order = {d:i for i,d in enumerate(DayOfWeek)}
    return sorted(
        [s for s in slots.values() if s.duration==50],
        key=lambda s:(day_order[s.day], s.start_min)
    )

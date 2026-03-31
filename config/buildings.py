"""
GIKI Buildings and Rooms Configuration
=======================================
Scalable: add/remove buildings and rooms via config only.
Course codes determine faculty routing. Labs have priority queues.

Faculty codes (from course code prefix):
  CS, CE, AI, CY, DS, SE, IF  -> FCSE (Faculty of Computer Science & Engineering)
  EE                           -> FEE  (Faculty of Electrical Engineering)
  ME                           -> FME  (Faculty of Mechanical Engineering)
  CH                           -> FChE (Faculty of Chemical Engineering) / AcB
  MM, MTE, CME                 -> FMCE (Faculty of Materials & Chemical Engineering)
  CV                           -> FCvE (Faculty of Civil Engineering) / AcB
  MT, ES, PH                   -> FBS  (Faculty of Basic Sciences) - ES/FES building
  HM, MS, AF, EM, SC           -> SMgS (School of Mgmt Sciences) - Brabers
  MM                           -> FMCE

Building priority for each faculty:
  FCSE -> CS Block first, then AcB (Academic Block)
  FEE  -> EE Block first, then AcB
  FME  -> ME Block first
  FMCE -> MCE Block first, then AcB
  FCvE -> AcB first (CV rooms), then CS Block
  FBS  -> ES Block first, then EE Main, AcB
  SMgS -> Brabers (BB) first
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Room:
    """A schedulable room or lab."""
    room_id:     str
    building_id: str
    capacity:    int
    is_lab:      bool = False
    lab_type:    Optional[str] = None  # e.g. "cyber", "software", "composite", "chemistry", "physics", "computer"
    priority_faculty: list = field(default_factory=list)  # faculty codes with highest priority for this room
    notes:       str = ""


@dataclass
class Building:
    """A campus building."""
    building_id:  str
    name:         str
    short_name:   str
    faculty_home: list = field(default_factory=list)  # primary faculties
    rooms:        list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# GIKI BUILDINGS
# ══════════════════════════════════════════════════════════════════════

BUILDINGS = {
    "CS": Building(
        "CS", "CS/EE Block - FCSE/FEE Block",
        "CS Block",
        faculty_home=["FCSE", "FEE"],
        rooms=[]
    ),
    "AcB": Building(
        "AcB", "Academic Block",
        "AcB",
        faculty_home=["FCSE", "FEE", "FCvE", "FBS", "SMgS"],
        rooms=[]
    ),
    "BB": Building(
        "BB", "Brabers Building (School of Management Sciences)",
        "Brabers",
        faculty_home=["SMgS"],
        rooms=[]
    ),
    "ES": Building(
        "ES", "Engineering Sciences Block (FBS - Faculty of Basic Sciences)",
        "ES Block",
        faculty_home=["FBS"],
        rooms=[]
    ),
    "ME": Building(
        "ME", "Mechanical Engineering Block",
        "ME Block",
        faculty_home=["FME"],
        rooms=[]
    ),
    "MCE": Building(
        "MCE", "Materials & Chemical Engineering Block",
        "MCE Block",
        faculty_home=["FMCE", "FChE"],
        rooms=[]
    ),
    "CyberLab": Building(
        "CyberLab", "Cyber Security Lab (FCSE)",
        "CyberLab",
        faculty_home=["FCSE"],
        rooms=[]
    ),
    "SSDL": Building(
        "SSDL", "Systems and Software Development Lab (FCSE)",
        "SSDL",
        faculty_home=["FCSE"],
        rooms=[]
    ),
    "PCLab": Building(
        "PCLab", "PC Labs (General)",
        "PC Lab",
        faculty_home=["FCSE", "FEE"],
        rooms=[]
    ),
}


# ══════════════════════════════════════════════════════════════════════
# GIKI ROOMS - Derived from official timetable Spring 2026
# ══════════════════════════════════════════════════════════════════════

ROOMS = {
    # ── CS / EE Block Lecture Halls ──────────────────────────────────
    "CS-LH1":  Room("CS-LH1",  "CS", 80,  is_lab=False, priority_faculty=["FCSE","FEE"]),
    "CS-LH2":  Room("CS-LH2",  "CS", 80,  is_lab=False, priority_faculty=["FCSE","FEE"]),
    "CS-LH3":  Room("CS-LH3",  "CS", 80,  is_lab=False, priority_faculty=["FCSE","FEE"]),
    "EE-LH4":  Room("EE-LH4",  "CS", 80,  is_lab=False, priority_faculty=["FEE"]),
    "EE-LH5":  Room("EE-LH5",  "CS", 80,  is_lab=False, priority_faculty=["FEE"]),
    "EE-LH6":  Room("EE-LH6",  "CS", 80,  is_lab=False, priority_faculty=["FEE"]),
    "EE-Main": Room("EE-Main", "CS", 200, is_lab=False, priority_faculty=["FEE"]),
    "SE-Lab":  Room("SE-Lab",  "CS", 40,  is_lab=True,  lab_type="software",
                    priority_faculty=["FCSE"], notes="Software Engineering Lab"),

    # ── ES Block (FBS) ────────────────────────────────────────────────
    "ES-LH1":  Room("ES-LH1",  "ES", 60,  is_lab=False, priority_faculty=["FBS"]),
    "ES-LH2":  Room("ES-LH2",  "ES", 60,  is_lab=False, priority_faculty=["FBS"]),
    "ES-LH3":  Room("ES-LH3",  "ES", 60,  is_lab=False, priority_faculty=["FBS"]),
    "ES-Main": Room("ES-Main", "ES", 200, is_lab=False, priority_faculty=["FBS"]),
    "PH-Lab":  Room("PH-Lab",  "ES", 40,  is_lab=True,  lab_type="physics",
                    priority_faculty=["FBS"], notes="Physics Lab"),

    # ── Academic Block (AcB) ──────────────────────────────────────────
    "AcB-LH1":   Room("AcB-LH1",   "AcB", 60,  is_lab=False, priority_faculty=["FCvE"]),
    "AcB-LH2":   Room("AcB-LH2",   "AcB", 60,  is_lab=False, priority_faculty=["FCvE"]),
    "AcB-LH3":   Room("AcB-LH3",   "AcB", 60,  is_lab=False, priority_faculty=["FCvE"]),
    "AcB-LH4":   Room("AcB-LH4",   "AcB", 70,  is_lab=False, priority_faculty=["FCSE"]),
    "AcB-LH5":   Room("AcB-LH5",   "AcB", 70,  is_lab=False, priority_faculty=["FCSE"]),
    "AcB-LH6":   Room("AcB-LH6",   "AcB", 70,  is_lab=False, priority_faculty=["FCSE"]),
    "AcB-LH7":   Room("AcB-LH7",   "AcB", 60,  is_lab=False, priority_faculty=["FEE","FBS"]),
    "AcB-LH8":   Room("AcB-LH8",   "AcB", 70,  is_lab=False, priority_faculty=["FCSE"]),
    "AcB-LH9":   Room("AcB-LH9",   "AcB", 70,  is_lab=False, priority_faculty=["FCSE"],
                       notes="Used for CyS, CE courses"),
    "AcB-LH10":  Room("AcB-LH10",  "AcB", 60,  is_lab=False, priority_faculty=["FChE"]),
    "AcB-LH11":  Room("AcB-LH11",  "AcB", 60,  is_lab=False, priority_faculty=["FChE"]),
    "AcB-LH12":  Room("AcB-LH12",  "AcB", 60,  is_lab=False, priority_faculty=["FChE"]),
    "AcB-Main1": Room("AcB-Main1", "AcB", 200, is_lab=False, priority_faculty=["FCvE","FBS"]),
    "AcB-Main2": Room("AcB-Main2", "AcB", 250, is_lab=False, priority_faculty=["FCSE"]),
    "AcB-Main3": Room("AcB-Main3", "AcB", 200, is_lab=False, priority_faculty=["FChE"]),
    "PC-Lab-Old":  Room("PC-Lab-Old",  "PCLab", 40, is_lab=True, lab_type="computer",
                         priority_faculty=["SMgS","FBS"]),
    "PC-Lab-New":  Room("PC-Lab-New",  "PCLab", 40, is_lab=True, lab_type="computer",
                         priority_faculty=["SMgS","FBS"]),

    # ── Brabers / BB (SMgS) ───────────────────────────────────────────
    "BB-Main":  Room("BB-Main",  "BB", 200, is_lab=False, priority_faculty=["SMgS"]),
    "BB-LH2":   Room("BB-LH2",   "BB", 60,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-EH1":   Room("BB-EH1",   "BB", 60,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-EH2":   Room("BB-EH2",   "BB", 60,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-EH3":   Room("BB-EH3",   "BB", 60,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-EH4":   Room("BB-EH4",   "BB", 60,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-SemHall": Room("BB-SemHall","BB",100, is_lab=False, priority_faculty=["SMgS"]),
    "BB-WR1":   Room("BB-WR1",   "BB", 30,  is_lab=False, priority_faculty=["SMgS"]),
    "BB-WR2":   Room("BB-WR2",   "BB", 30,  is_lab=False, priority_faculty=["SMgS"]),

    # ── ME Block (FME) ────────────────────────────────────────────────
    "ME-LH1":   Room("ME-LH1",   "ME", 70,  is_lab=False, priority_faculty=["FME"]),
    "ME-LH2":   Room("ME-LH2",   "ME", 70,  is_lab=False, priority_faculty=["FME"]),
    "ME-LH3":   Room("ME-LH3",   "ME", 70,  is_lab=False, priority_faculty=["FME"]),
    "ME-Main":  Room("ME-Main",  "ME", 200, is_lab=False, priority_faculty=["FME"]),

    # ── MCE Block (FMCE / FChE) ───────────────────────────────────────
    "MCE-LH1":  Room("MCE-LH1",  "MCE", 60, is_lab=False, priority_faculty=["FMCE"]),
    "MCE-LH2":  Room("MCE-LH2",  "MCE", 60, is_lab=False, priority_faculty=["FMCE"]),
    "MCE-LH3":  Room("MCE-LH3",  "MCE", 60, is_lab=False, priority_faculty=["FMCE","FChE"]),
    "MCE-LH4":  Room("MCE-LH4",  "MCE", 60, is_lab=False, priority_faculty=["SMgS","FMCE"]),
    "MCE-Main": Room("MCE-Main", "MCE", 200,is_lab=False, priority_faculty=["FMCE","FChE"]),
    "Mat-Lab":  Room("Mat-Lab",  "MCE", 30, is_lab=True,  lab_type="composite",
                      priority_faculty=["FMCE"], notes="Materials / Composite Lab - FMCE priority"),

    # ── Dedicated Labs ────────────────────────────────────────────────
    "CyberLab-1": Room("CyberLab-1", "CyberLab", 30, is_lab=True, lab_type="cyber",
                        priority_faculty=["FCSE"],
                        notes="Cyber Security Lab Slot 1 - CyS courses highest priority, then FCSE"),
    "CyberLab-2": Room("CyberLab-2", "CyberLab", 30, is_lab=True, lab_type="cyber",
                        priority_faculty=["FCSE"],
                        notes="Cyber Security Lab Slot 2 - CyS courses highest priority, then FCSE"),
    "SSDL-1":   Room("SSDL-1",   "SSDL", 35, is_lab=True, lab_type="software",
                      priority_faculty=["FCSE"],
                      notes="Systems & Software Dev Lab - SE/CS priority"),
    "SSDL-2":   Room("SSDL-2",   "SSDL", 35, is_lab=True, lab_type="software",
                      priority_faculty=["FCSE"],
                      notes="Systems & Software Dev Lab - SE/CS priority"),
    "Chem-Lab": Room("Chem-Lab", "MCE", 25, is_lab=True, lab_type="chemistry",
                      priority_faculty=["FChE"],
                      notes="Chemistry lab - CH courses priority"),
    "AI-Lab":   Room("AI-Lab",   "AcB", 30, is_lab=True, lab_type="computer",
                      priority_faculty=["FCSE"],
                      notes="AI/DS lab in AcB"),
    "Incubator": Room("Incubator","AcB", 20, is_lab=True, lab_type="innovation",
                       priority_faculty=["FCSE"],
                       notes="Innovation & Makers Lab (IF102L)"),
}


# ══════════════════════════════════════════════════════════════════════
# FACULTY ROUTING — course code prefix → faculty → preferred buildings
# ══════════════════════════════════════════════════════════════════════

FACULTY_ROUTING = {
    # prefix : (faculty_code, preferred_room_ids_in_priority_order)
    "CS":  ("FCSE", ["CS-LH1","CS-LH2","CS-LH3","AcB-LH4","AcB-LH5","AcB-LH6","AcB-LH8","AcB-LH9","AcB-Main2"]),
    "CE":  ("FCSE", ["CS-LH1","CS-LH2","CS-LH3","AcB-LH4","AcB-LH5","AcB-LH6","AcB-LH9"]),
    "AI":  ("FCSE", ["AcB-LH4","AcB-LH5","AcB-LH6","AcB-LH8","CS-LH1","CS-LH2"]),
    "CY":  ("FCSE", ["AcB-LH9","AcB-LH8","AcB-LH4","CS-LH1"]),  # CyberLab for labs
    "DS":  ("FCSE", ["AcB-LH4","AcB-LH5","AcB-LH6","AcB-LH8","CS-LH1"]),
    "SE":  ("FCSE", ["AcB-LH4","AcB-LH5","AcB-LH6","CS-LH1","CS-LH2"]),
    "IF":  ("FCSE", ["AcB-Main2","AcB-Main1","Incubator"]),
    "EE":  ("FEE",  ["EE-LH4","EE-LH5","EE-LH6","EE-Main","AcB-LH7"]),
    "ME":  ("FME",  ["ME-LH1","ME-LH2","ME-LH3","ME-Main"]),
    "CH":  ("FChE", ["AcB-LH10","AcB-LH11","AcB-LH12","AcB-Main3","MCE-LH3"]),
    "MM":  ("FMCE", ["MCE-LH1","MCE-LH2","MCE-LH3","MCE-LH4","MCE-Main"]),
    "CV":  ("FCvE", ["AcB-LH1","AcB-LH2","AcB-LH3","AcB-Main1","AcB-LH4"]),
    "MT":  ("FBS",  ["ES-LH1","ES-LH2","ES-LH3","ES-Main","AcB-LH7","EE-Main"]),
    "ES":  ("FBS",  ["ES-LH1","ES-LH2","ES-LH3","ES-Main","AcB-LH7"]),
    "PH":  ("FBS",  ["ES-LH1","ES-LH2","ES-Main","MCE-Main"]),
    "HM":  ("SMgS", ["BB-Main","BB-LH2","BB-EH1","BB-EH2","BB-EH3","BB-EH4"]),
    "MS":  ("SMgS", ["BB-Main","BB-LH2","BB-EH1","BB-EH2","BB-EH3","BB-EH4","BB-SemHall"]),
    "AF":  ("SMgS", ["BB-SemHall","BB-WR1","BB-WR2","BB-Main"]),
    "EM":  ("SMgS", ["BB-SemHall","BB-WR1","BB-WR2","BB-Main"]),
    "SC":  ("SMgS", ["BB-SemHall","BB-WR1","BB-WR2"]),
}

# Lab type → lab rooms in priority order
LAB_ROUTING = {
    "cyber":      ["CyberLab-1", "CyberLab-2"],  # CyS courses first
    "software":   ["SSDL-1", "SSDL-2", "SE-Lab"],
    "composite":  ["Mat-Lab"],
    "chemistry":  ["Chem-Lab"],
    "physics":    ["PH-Lab"],
    "computer":   ["PC-Lab-New", "PC-Lab-Old", "AI-Lab"],
    "innovation": ["Incubator"],
    "materials":  ["Mat-Lab"],
}


def get_faculty_from_code(course_code: str) -> str:
    """Determine faculty from course code prefix. O(1) dict lookup."""
    if not course_code:
        return "FCSE"
    code = course_code.strip().upper()
    for prefix in sorted(FACULTY_ROUTING.keys(), key=len, reverse=True):
        if code.startswith(prefix):
            return FACULTY_ROUTING[prefix][0]
    return "FCSE"


def get_preferred_rooms(course_code: str, is_lab: bool = False,
                        lab_type: str = None, num_students: int = 30) -> list:
    """
    Return ordered list of preferred room_ids for this course.
    Lab courses get lab-specific routing. Faculty priority applied.
    """
    code = course_code.strip().upper()

    if is_lab and lab_type and lab_type in LAB_ROUTING:
        # Labs route to specific lab rooms first
        lab_rooms = LAB_ROUTING[lab_type]
        # Filter to rooms with sufficient capacity
        result = [r for r in lab_rooms if r in ROOMS and ROOMS[r].capacity >= max(1, num_students)]
        if result:
            return result

    # Lecture rooms: use faculty routing
    for prefix in sorted(FACULTY_ROUTING.keys(), key=len, reverse=True):
        if code.startswith(prefix):
            preferred = FACULTY_ROUTING[prefix][1]
            # Filter by capacity
            result = [r for r in preferred if r in ROOMS and ROOMS[r].capacity >= max(1, num_students)]
            if result:
                return result
            return preferred  # fallback: return all regardless of capacity

    # Default fallback
    return [r for r in ROOMS if not ROOMS[r].is_lab]


def add_building(building_id: str, name: str, short_name: str, faculty_home: list):
    """Add a new building to the system. O(1)."""
    BUILDINGS[building_id] = Building(building_id, name, short_name, faculty_home)


def add_room(room_id: str, building_id: str, capacity: int, is_lab: bool = False,
             lab_type: str = None, priority_faculty: list = None, notes: str = ""):
    """Add a new room to the system. O(1)."""
    ROOMS[room_id] = Room(
        room_id, building_id, capacity, is_lab,
        lab_type, priority_faculty or [], notes
    )


def remove_room(room_id: str):
    """Remove a room. O(1)."""
    ROOMS.pop(room_id, None)


def get_all_rooms_table() -> list[dict]:
    """Return structured table of all buildings and rooms. O(R)."""
    rows = []
    for rid, room in sorted(ROOMS.items()):
        building = BUILDINGS.get(room.building_id)
        rows.append({
            "room_id":     rid,
            "building":    building.name if building else room.building_id,
            "short":       building.short_name if building else room.building_id,
            "capacity":    room.capacity,
            "type":        f"Lab ({room.lab_type})" if room.is_lab else "Lecture",
            "priority_for": ", ".join(room.priority_faculty),
            "notes":       room.notes,
        })
    return rows

"""
GIKI Department / Sub-department configuration.
Faculties can have sub-departments (programs).
"""

# Faculty -> list of sub-departments/programs
FACULTY_PROGRAMS = {
    "FCSE": ["CS", "CE", "AI", "CY", "DS", "SE", "IF"],
    "FEE":  ["EEP", "EEC"],   # Power, Controls
    "FME":  [],
    "FChE": [],
    "FMCE": ["MTE", "CME"],   # Materials, Chemical-Materials
    "FCvE": [],
    "FBS":  [],
    "SMgS": ["MGS"],
}

# Program -> faculty mapping
PROGRAM_TO_FACULTY = {
    "CS":"FCSE","CE":"FCSE","AI":"FCSE","CY":"FCSE","DS":"FCSE","SE":"FCSE","IF":"FCSE",
    "EEP":"FEE","EEC":"FEE",
    "MTE":"FMCE","CME":"FMCE","MGS":"SMgS",
}

# Course code prefix -> sub-department
CODE_TO_PROGRAM = {
    "CS":"CS","CE":"CE","AI":"AI","CY":"CY","DS":"DS","SE":"SE","IF":"IF",
    "EE":"EE","ME":"ME","CH":"CH","MM":"MM","CV":"CV",
    "MT":"FBS","ES":"FBS","PH":"FBS",
    "HM":"SMgS","MS":"SMgS","AF":"SMgS","EM":"SMgS","SC":"SMgS",
}

# MLH / large halls that allow combined sections
LARGE_HALLS = [
    "CS-LH1","CS-LH2","CS-LH3",   # Main CS block lecture halls
    "EE-LH4","EE-LH5","EE-LH6",
    "AcB-Main1","AcB-Main2","AcB-Main3",
    "ES-Main","ME-Main","MCE-Main","BB-Main","EE-Main",
]

def get_program_from_code(course_code: str) -> str:
    """Return sub-department/program from course code prefix."""
    import re
    m = re.match(r'^([A-Z]+)', course_code.upper())
    if m:
        return CODE_TO_PROGRAM.get(m.group(1), "")
    return ""

def get_all_programs() -> list:
    """All programs across all faculties."""
    all_p = []
    for progs in FACULTY_PROGRAMS.values():
        all_p.extend(progs)
    return sorted(set(all_p))

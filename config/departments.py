"""
GIKI Department / Sub-department configuration.
Active programs: CS, AI, CE, CY, DS, SE (FCSE), EE (FEE), ES (FBS),
                 MGS (SMgS), ME (FME), MTE (FMCE), CVE (FCvE).
"""

# Faculty -> list of sub-departments/programs
FACULTY_PROGRAMS = {
    "FCSE": ["CS", "CE", "AI", "CY", "DS", "SE"],
    "FEE":  ["EE"],
    "FME":  ["ME"],
    "FMCE": ["MTE"],
    "FCvE": ["CVE"],
    "FBS":  ["ES"],
    "SMgS": ["MGS"],
}

# Program -> faculty mapping
PROGRAM_TO_FACULTY = {
    "CS":"FCSE","CE":"FCSE","AI":"FCSE","CY":"FCSE","DS":"FCSE","SE":"FCSE",
    "EE":"FEE",
    "ME":"FME",
    "MTE":"FMCE",
    "CVE":"FCvE",
    "ES":"FBS",
    "MGS":"SMgS",
}

# Course code prefix -> program/faculty label used in filtering
CODE_TO_PROGRAM = {
    "CS":"CS","CE":"CE","AI":"AI","CY":"CY","DS":"DS","SE":"SE",
    "EE":"EE",
    "ME":"ME",
    "MTE":"MTE",
    "CV":"CVE",
    "ES":"ES",
    "MS":"MGS","HM":"MGS","AF":"MGS","EM":"MGS","SC":"MGS",
}

# MLH / large halls that allow combined sections
LARGE_HALLS = [
    "CS-LH1","CS-LH2","CS-LH3",
    "EE-LH4","EE-LH5","EE-LH6",
    "AcB-Main1","AcB-Main2","AcB-Main3",
    "ES-Main","ME-Main","MCE-Main","BB-Main","EE-Main",
]

def get_program_from_code(course_code: str) -> str:
    """Return sub-department/program label from course code prefix."""
    import re
    # Check longer prefixes first so MTE matches before MT (not in list but future-proof)
    m = re.match(r'^([A-Z]+)', course_code.upper())
    if m:
        prefix = m.group(1)
        # Try full prefix then progressively shorter
        for length in range(len(prefix), 0, -1):
            val = CODE_TO_PROGRAM.get(prefix[:length])
            if val:
                return val
    return ""

def get_all_programs() -> list:
    """All programs across all faculties."""
    all_p = []
    for progs in FACULTY_PROGRAMS.values():
        all_p.extend(progs)
    return sorted(set(all_p))

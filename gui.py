"""
GIKI University Timetable Scheduler — GUI v2.2
python gui.py
Ubuntu: sudo apt install python3-tk
Windows: reinstall Python, check tcl/tk box
macOS: brew install python-tk
"""
import os,sys,threading,time,json,re,copy
SCRIPT_DIR=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,SCRIPT_DIR)
try:
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox,scrolledtext
except ModuleNotFoundError:
    print("tkinter missing. Ubuntu: sudo apt install python3-tk"); sys.exit(1)

from core.models import Timetable,Section,Course,Teacher,SessionType,DayOfWeek,ScheduledSession
from core.scheduler import GIKIScheduler,ConstraintEngine
from data.slots import build_giki_slots
from config.buildings import ROOMS,BUILDINGS,add_room,remove_room
from config.departments import FACULTY_PROGRAMS,LARGE_HALLS,get_program_from_code
from parsers.course_parser import parse_course_list,summarize_courses,normalize_teacher_name
from exporters.excel_exporter import export_excel,export_text,export_buildings_table_excel
try:
    from exporters.pdf_exporter import export_faculty_pdf,export_section_pdf
    PDF_OK=True
except ImportError:
    PDF_OK=False

C={"bg":"#F4F6F9","sidebar":"#1F3864","sidebar_hover":"#2E4E8C","sidebar_active":"#4A7FCB",
   "accent":"#2E4E8C","accent2":"#4A7FCB","white":"#FFFFFF","text":"#1A1A2E",
   "text_light":"#666688","border":"#D0D8E8","row_even":"#F0F4FB","row_odd":"#FFFFFF",
   "header_bg":"#1F3864","header_fg":"#FFFFFF","btn":"#2E4E8C","btn_hover":"#4A7FCB",
   "btn_danger":"#8B0000","btn_success":"#1B5E20","input_bg":"#FFFFFF","input_border":"#B0BED0",
   "slot_on":"#1B5E20","slot_off":"#CCCCCC"}
FF="Segoe UI" if sys.platform=="win32" else("SF Pro Text" if sys.platform=="darwin" else"DejaVu Sans")
DATA=os.path.join(SCRIPT_DIR,"giki_state.json")
BATCH_LABEL={1:"Year 1 (Intake 2025)",2:"Year 2 (Intake 2024)",
             3:"Year 3 (Intake 2023)",4:"Year 4 (Intake 2022)",0:"Year Unknown"}
YEAR_FILTERS=["ALL","Year 1 (Intake 2025)","Year 2 (Intake 2024)",
              "Year 3 (Intake 2023)","Year 4 (Intake 2022)"]
LECTURE_DURATION=50
LAB_DURATION=180
FAC_BG={"FCSE":"#D6E4F0","FEE":"#D5F5E3","FME":"#FCF3CF","FChE":"#FAD7A0",
        "FMCE":"#E8DAEF","FCvE":"#D1F2EB","FBS":"#FDEBD0","SMgS":"#FDEDEC"}

ALL_PROGRAMS=["ALL","FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS",
               "—","CS","CE","AI","CY","DS","SE","EE","ME","MTE","CVE","ES","MGS"]

def B(p,text,cmd,color=None,w=16,fs=9):
    bg=color or C["btn"]
    b=tk.Button(p,text=text,command=cmd,bg=bg,fg=C["white"],
                activebackground=C["btn_hover"],activeforeground=C["white"],
                font=(FF,fs,"bold"),relief="flat",cursor="hand2",width=w,padx=8,pady=5,bd=0)
    b.bind("<Enter>",lambda e:b.config(bg=C["btn_hover"]))
    b.bind("<Leave>",lambda e:b.config(bg=bg))
    return b

def E(p,w=28,var=None):
    e=tk.Entry(p,width=w,bg=C["input_bg"],fg=C["text"],insertbackground=C["text"],
               relief="solid",bd=1,highlightthickness=1,highlightbackground=C["input_border"],
               highlightcolor=C["accent"],font=(FF,9))
    if var: e.config(textvariable=var)
    return e

def L(p,text,size=9,bold=False,color=None,bg=None):
    return tk.Label(p,text=text,bg=bg or p.cget("bg"),fg=color or C["text"],
                    font=(FF,size,"bold" if bold else"normal"))

def CB(p,var,values,w=12):
    cb=ttk.Combobox(p,textvariable=var,values=values,state="readonly",width=w,font=(FF,9))
    return cb

def year_to_batch(label:str)->int:
    return {"Year 1":1,"Year 2":2,"Year 3":3,"Year 4":4}.get((label or "")[:6],0)

def slot_type_label(duration:int)->str:
    return "Lab" if duration==LAB_DURATION else "Lec"

def TV(p,cols,heads,widths=None,h=15):
    st=ttk.Style(); st.theme_use("clam")
    st.configure("G.Treeview",background=C["white"],foreground=C["text"],rowheight=24,
                 fieldbackground=C["white"],font=(FF,9),bordercolor=C["border"])
    st.configure("G.Treeview.Heading",background=C["header_bg"],foreground=C["header_fg"],
                 font=(FF,9,"bold"),relief="flat")
    st.map("G.Treeview",background=[("selected",C["accent2"])],foreground=[("selected",C["white"])])
    frame=tk.Frame(p,bg=C["white"],highlightbackground=C["border"],highlightthickness=1)
    tv=ttk.Treeview(frame,columns=cols,show="headings",height=h,style="G.Treeview",selectmode="browse")
    for col,head in zip(cols,heads):
        ww=(widths or {}).get(col,110)
        tv.heading(col,text=head,anchor="w"); tv.column(col,width=ww,minwidth=40,anchor="w")
    vsb=ttk.Scrollbar(frame,orient="vertical",command=tv.yview)
    hsb=ttk.Scrollbar(frame,orient="horizontal",command=tv.xview)
    tv.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
    tv.grid(row=0,column=0,sticky="nsew"); vsb.grid(row=0,column=1,sticky="ns")
    hsb.grid(row=1,column=0,sticky="ew")
    frame.grid_rowconfigure(0,weight=1); frame.grid_columnconfigure(0,weight=1)
    tv.tag_configure("even",background=C["row_even"]); tv.tag_configure("odd",background=C["row_odd"])
    return frame,tv

class AppState:
    def __init__(self):
        self.slots=build_giki_slots(extended=False); self.rooms=ROOMS
        self.courses={}; self.teachers={}; self.sections={}
        self.timetable=Timetable()
        self.enabled_slots=set(self.slots.keys())  # ALL enabled by default
        self.elective_section_uids=set()  # UIDs of sections imported as electives
    def get_scheduler(self):
        active={k:v for k,v in self.slots.items()
                if not self.enabled_slots or k in self.enabled_slots}
        return GIKIScheduler(self.timetable,active,self.rooms,self.teachers,self.courses)
    def get_engine(self):
        return ConstraintEngine(self.timetable,self.slots,self.rooms,self.teachers,self.courses)
    def reset_all(self):
        self.courses.clear(); self.teachers.clear(); self.sections.clear()
        self.timetable=Timetable(); self.enabled_slots=set(self.slots.keys())
        self.elective_section_uids.clear()
        if os.path.exists(DATA): os.remove(DATA)
    def advance_year(self):
        """September: all batches advance by 1, intake 2022 graduates, new Year 1 = 2026."""
        for uid,sec in list(self.sections.items()):
            if sec.batch_year==4:
                del self.sections[uid]
                self.elective_section_uids.discard(uid)  # graduated — remove elective tracking too
            elif sec.batch_year>0:
                sec.batch_year+=1
        self.save()
    def save(self):
        data={"courses":{k:{"code":v.course_code,"title":v.title,"ch":v.credit_hours,
                "type":v.session_type.value,"faculty":v.faculty,"lab_type":v.lab_type,
                "restricted":[d.value for d in v.restricted_days],"program":getattr(v,'program','')}
                for k,v in self.courses.items()},
              "teachers":{k:{"id":v.teacher_id,"name":v.name,"faculty":v.faculty,
                "unavail":[d.value for d in v.unavailable_days],
                "can_combined":getattr(v,'can_combined',False)} for k,v in self.teachers.items()},
              "sections":{k:{"sid":v.section_id,"code":v.course_code,"tid":v.teacher_id,
                "batch":v.batch_year,"faculty":v.faculty,"students":v.num_students,
                "for":v.for_program,"program":getattr(v,'program','')} for k,v in self.sections.items()},
              "sessions":[s.to_dict() for s in self.timetable.sessions],
              "enabled_slots":list(self.enabled_slots),
              "elective_uids":list(self.elective_section_uids)}
        with open(DATA,"w",encoding="utf-8") as f: json.dump(data,f,indent=2)
    def load(self):
        if not os.path.exists(DATA): return
        with open(DATA,"r",encoding="utf-8") as f: data=json.load(f)
        for k,v in data.get("courses",{}).items():
            c=Course(v["code"],v["title"],v["ch"],SessionType(v["type"]),
                v.get("faculty",""),[DayOfWeek(d) for d in v.get("restricted",[])],v.get("lab_type",""))
            c.program=v.get("program",""); self.courses[k]=c
        for k,v in data.get("teachers",{}).items():
            t=Teacher(v["id"],v["name"],v.get("faculty",""),
                [DayOfWeek(d) for d in v.get("unavail",[])])
            t.can_combined=v.get("can_combined",False); self.teachers[k]=t
        for k,v in data.get("sections",{}).items():
            s=Section(v["sid"],v["code"],v["tid"],v["batch"],
                v.get("faculty",""),v.get("students",30),v.get("for",""))
            s.program=v.get("program",""); self.sections[k]=s
        for sd in data.get("sessions",[]):
            self.timetable.add_session(ScheduledSession(
                sd["section_uid"],sd["course_code"],
                SessionType(sd["session_type"]),sd["slot_id"],sd["room_id"],sd["teacher_id"],
                sd["batch_year"],sd.get("faculty",""),sd.get("session_index",1),
                sd.get("section_id",""),sd.get("for_program",""),
            ))
        # Req 4: keep only slot IDs that exist in the current slot set.
        # Add any NEW slots (not present in saved state) as enabled by default so
        # the picker never shows "phantom disabled" slots the user can't toggle.
        all_slot_ids=set(self.slots.keys())
        saved_slots=set(data.get("enabled_slots",[]))
        if saved_slots:
            # Retain explicitly-enabled saved slots that still exist
            valid_saved=saved_slots & all_slot_ids
            # Any brand-new slot (not seen in saved state at all) → enable by default
            new_slots=all_slot_ids - saved_slots
            self.enabled_slots=valid_saved | new_slots
        else:
            self.enabled_slots=all_slot_ids
        # Restore elective tracking — keep only UIDs that still exist in sections
        saved_electives=set(data.get("elective_uids",[]))
        self.elective_section_uids=saved_electives & set(self.sections.keys())

# Allowed course-code prefixes — only courses whose code starts with one of
# these prefixes are imported.  Longer prefixes are checked first so "MTE"
# takes priority over any shorter match.
_ALLOWED_CODE_PREFIXES = tuple(sorted({
    "CS","AI","CE","CY","DS","SE",          # FCSE (IF removed)
    "EE",                                    # FEE
    "ES",                                    # FBS — Environmental Sciences only
    "ME",                                    # FME
    "MTE",                                   # FMCE — Materials only
    "CV",                                    # FCvE (Civil Engineering)
    "MS","HM","AF","EM","SC",               # SMgS — all Management Sciences
}, key=len, reverse=True))  # longer prefixes first

def _code_is_allowed(course_code: str) -> bool:
    code = course_code.upper()
    return any(code.startswith(p) for p in _ALLOWED_CODE_PREFIXES)

_VALID_PROGRAMS={"CS","CE","AI","CY","DS","SE","EE","ME","MTE","CVE","ES","MGS"}
_FACULTY_LEVEL_CODES={"FCSE","FEE","FME","FMCE","FCVE","FBS","SMGS"}

def _normalize_for_program(raw:str):
    """Return normalised program code, '' for faculty-wide/shared rows, None to drop."""
    if not raw: return ""
    prog=re.sub(r'=.*$','',str(raw)).strip().upper()
    if not prog: return ""
    if prog in _FACULTY_LEVEL_CODES: return ""  # faculty-wide → treat as shared
    _alias={"CYS":"CY","BCS":"CS","BAI":"AI","BCE":"CE","BDS":"DS","SWE":"SE"}
    prog=_alias.get(prog,prog)
    if prog in _VALID_PROGRAMS: return prog
    return None  # unrecognised value → drop the row

def _import_entries(entries,state):
    def lt(c):
        c=c.upper()
        if c.startswith("CY"): return"cyber"
        if c.startswith("SE"): return"software"
        if c.startswith("MTE"): return"composite"
        if c.startswith("CV"): return"composite"
        return"computer" if any(c.startswith(p) for p in("CS","AI","DS")) else""
    for e in entries:
        if not _code_is_allowed(e.course_code):
            continue
        for_prog=_normalize_for_program(e.for_program)
        if for_prog is None:
            continue  # unrecognised for_program (e.g. "FCSE", "All GIKI", "BME") → drop
        is_lab=e.is_lab or e.credit_hours==1
        if e.course_code not in state.courses:
            st=SessionType.LAB if is_lab else SessionType.LECTURE
            c=Course(e.course_code,e.title,e.credit_hours,st,e.faculty,[],lt(e.course_code))
            c.program=for_prog; state.courses[e.course_code]=c
        else:
            # Fix stale session_type: if the Excel identifies this as a lab but
            # the stored record says Lecture, correct it so weekly_sessions stays 1
            # and the lab is not over-scheduled (e.g. CS112L getting 5 sessions).
            existing=state.courses[e.course_code]
            if is_lab and existing.session_type==SessionType.LECTURE:
                existing.session_type=SessionType.LAB
        if not e.instructor: continue
        # Handle multi-teacher entries (e.g. "Mr. A, Mr. B, Ms. C")
        instructor_names=[n.strip() for n in e.instructor.split(",") if n.strip()]
        primary_tid=None
        for name in instructor_names:
            _,tid=normalize_teacher_name(name)
            if tid and tid not in state.teachers:
                t=Teacher(tid,name,e.faculty)
                t.can_combined=False; state.teachers[tid]=t
            if primary_tid is None: primary_tid=tid
        if not primary_tid: continue
        # Handle split sections A1/A2 etc — keep them as separate sections
        sec_names = [s.strip() for s in re.split(r'[,/]', str(e.section)) if s.strip()]
        if not sec_names:
            sec_names = ["A"]
        
        for s_name in sec_names:
            # Prevent duplicate lab problem if there are multiple entries for the same lab
            sec = Section(s_name, e.course_code, primary_tid, e.batch_year,
                          e.faculty, e.num_students, for_prog)
            sec.program = for_prog
            if sec.uid not in state.sections:
                state.sections[sec.uid] = sec

# Programs that receive exactly ONE mandatory 3-CH elective from Year 3 onwards
_ELECTIVE_PROGRAMS={"CS","CE","AI","CY","DS","SE","ME","EE","ES","ME","MGS","MTE","CVE"}
_MIN_ELECTIVE_BATCH=3  # semester 5+ = batch_year 3 (Year 3) and above

def _clean_prog_for_elective(raw):
    """Normalise a for_program value to a short program code (e.g. 'CY')."""
    if not raw: return ""
    prog=re.sub(r'=.*$','',str(raw)).strip().upper()
    # Map full-form names that appear in some Excel sheets
    _alias={"CYS":"CY","BCS":"CS","BAI":"AI","BCE":"CE","BDS":"DS","SWE":"SE","CME":"CME","MTE":"MTE"}
    return _alias.get(prog,prog)

def _elective_batch(e):
    """Return batch_year for an elective entry.
    The parser now maps all semesters (1-2=Y1, 3-4=Y2, 5-6=Y3, 7-8=Y4),
    so e.batch_year is already correct; this function is kept as a safety net."""
    if e.batch_year>=_MIN_ELECTIVE_BATCH:
        return e.batch_year
    # Fallback: re-derive from semester in case batch_year is 0
    sem=e.semester
    try:
        s=int(str(sem).strip())
        if s in(1,2): return 1
        if s in(3,4): return 2
        if s in(5,6): return 3
        if s in(7,8): return 4
    except: pass
    return e.batch_year

def _import_elective_entries(entries,state):
    """
    Import elective sections from a parsed course list.

    Rules enforced:
      • Only entries whose for_program is in _ELECTIVE_PROGRAMS are accepted.
      • batch_year must be >= 3 (3rd year / semester 5 onwards).
      • No limit on number of electives per program/year.
      • Credit hours are taken as-is from the Excel file.

    Returns (imported_count, warning_list).
    """
    def _lt(c):
        c=c.upper()
        if c.startswith("CY"): return"cyber"
        if c.startswith("SE"): return"software"
        if c.startswith("MM"): return"composite"
        if c.startswith("CH"): return"chemistry"
        if c.startswith("PH"): return"physics"
        return"computer" if any(c.startswith(p) for p in("CS","AI","DS","IF")) else""

    warnings=[]
    imported=0

    for e in entries:
        prog=_clean_prog_for_elective(e.for_program)
        batch=_elective_batch(e)

        if prog not in _ELECTIVE_PROGRAMS:
            warnings.append(
                f"Skipped {e.course_code} (sec {e.section}): "
                f"for_program='{prog}' not in elective programs {sorted(_ELECTIVE_PROGRAMS)}")
            continue

        if batch<_MIN_ELECTIVE_BATCH:
            warnings.append(
                f"Skipped {e.course_code}: Year {batch} is below 3rd year "
                f"(semester 5+ / Year 3+ required for electives)")
            continue

        if not e.instructor:
            warnings.append(f"Skipped {e.course_code}: no instructor assigned")
            continue

        is_lab=e.is_lab or e.credit_hours==1
        st=SessionType.LAB if is_lab else SessionType.LECTURE

        # Add course using actual credit hours from the file
        if e.course_code not in state.courses:
            c=Course(e.course_code,e.title,e.credit_hours,st,e.faculty,[],_lt(e.course_code))
            c.program=prog; state.courses[e.course_code]=c

        # Add teacher
        _,tid=normalize_teacher_name(e.instructor)
        if not tid:
            warnings.append(f"Skipped {e.course_code}: could not parse teacher '{e.instructor}'")
            continue
        if tid not in state.teachers:
            t=Teacher(tid,e.instructor,e.faculty); t.can_combined=False
            state.teachers[tid]=t

        # Section ID: use whatever the Excel gives; fall back to first char of program
        sec_names=[s.strip() for s in re.split(r'[,/]',str(e.section)) if s.strip()]
        s_name=sec_names[0] if sec_names else prog[0]

        sec=Section(s_name,e.course_code,tid,batch,e.faculty,e.num_students,prog)
        sec.program=prog

        if sec.uid not in state.sections:
            state.sections[sec.uid]=sec

        state.elective_section_uids.add(sec.uid)
        imported+=1

    return imported,warnings

# ─── Dashboard ────────────────────────────────────────────────────────
class DashboardPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        L(self,"GIKI Timetable Scheduler",18,True,C["accent"]).pack(pady=(20,4))
        L(self,"Spring 2026 — Faculty-aware scheduling",10,color=C["text_light"]).pack(pady=(0,14))
        sf=tk.Frame(self,bg=C["bg"]); sf.pack(fill="x",padx=30,pady=8)
        self.sv={}
        for i,(lab,key,col) in enumerate([("Courses","courses",C["accent"]),
            ("Teachers","teachers",C["sidebar"]),("Sections","sections","#1B5E20"),
            ("Sessions","sessions","#E65100"),("Rooms","rooms","#1A237E"),
            ("Enabled Slots","eslots","#4A235A")]):
            card=tk.Frame(sf,bg=C["white"],highlightthickness=1,highlightbackground=C["border"])
            card.grid(row=0,column=i,padx=5,pady=4,sticky="ew",ipadx=8,ipady=8)
            sf.grid_columnconfigure(i,weight=1)
            v=tk.StringVar(value="0"); self.sv[key]=v
            tk.Label(card,textvariable=v,font=(FF,20,"bold"),fg=col,bg=C["white"]).pack()
            tk.Label(card,text=lab,font=(FF,7),fg=C["text_light"],bg=C["white"]).pack()
        self.refresh_stats()
        bf=tk.Frame(self,bg=C["bg"]); bf.pack(pady=8)
        B(bf,"Import Course List",self._import,w=18).grid(row=0,column=0,padx=6,pady=4)
        B(bf,"Import Electives",self._import_electives,"#4A235A",18).grid(row=0,column=1,padx=6,pady=4)
        B(bf,"Schedule All",self._schedule_all,C["btn_success"],18).grid(row=0,column=2,padx=6,pady=4)
        B(bf,"Validate",self._validate,w=14).grid(row=0,column=3,padx=6,pady=4)
        B(bf,"Advance Year",self._advance_year,C["btn_hover"],14).grid(row=0,column=4,padx=6,pady=4)
        B(bf,"RESET ALL",self._reset,C["btn_danger"],12).grid(row=0,column=5,padx=6,pady=4)
        L(self,"Activity Log",11,True).pack(pady=(12,4),anchor="w",padx=30)
        self.log=scrolledtext.ScrolledText(self,height=14,font=(FF,8),bg="#1A1A2E",
            fg="#A8D8EA",insertbackground="white",relief="flat",wrap="word",padx=10,pady=8)
        self.log.pack(fill="both",expand=True,padx=30,pady=(0,16))
        self._log("Ready. Import a course list to begin.")
    def _log(self,msg,level="info"):
        self.log.config(state="normal"); self.log.insert("end",f"  {msg}\n")
        self.log.see("end"); self.log.config(state="disabled"); self.on_status(msg)
    def refresh_stats(self):
        s=self.state
        self.sv["courses"].set(str(len(s.courses))); self.sv["teachers"].set(str(len(s.teachers)))
        self.sv["sections"].set(str(len(s.sections))); self.sv["sessions"].set(str(len(s.timetable.sessions)))
        self.sv["rooms"].set(str(len(s.rooms)))
        n=len(s.enabled_slots) if s.enabled_slots else len(s.slots)
        self.sv["eslots"].set(str(n))
    def _import(self):
        path=filedialog.askopenfilename(title="Select Course List",
            filetypes=[("Excel/CSV/PDF","*.xlsx *.xls *.csv *.pdf *.ods"),("All","*.*")])
        if not path: return
        self._log(f"Parsing {os.path.basename(path)}...")
        try:
            entries=parse_course_list(path); s=summarize_courses(entries)
            _import_entries(entries,self.state); self.state.save(); self.refresh_stats()
            self._log(f"Imported {s['total']} entries | {s['unique_codes']} courses | {s['by_faculty']}","success")
        except Exception as e:
            self._log(f"Import error: {e}","error"); messagebox.showerror("Import Error",str(e))
    def _import_electives(self):
        path=filedialog.askopenfilename(title="Select Electives List (same Excel format as course list)",
            filetypes=[("Excel/CSV","*.xlsx *.xls *.csv *.ods"),("All","*.*")])
        if not path: return
        self._log(f"Parsing electives from {os.path.basename(path)}...")
        try:
            entries=parse_course_list(path)
            imported,warns=_import_elective_entries(entries,self.state)
            self.state.save(); self.refresh_stats()
            self._log(f"Electives imported: {imported} section(s) added","success")
            for w in warns[:8]: self._log(f"  {w}","warning")
            # Build summary per program/year for the info dialog
            prog_yr={}
            for uid in self.state.elective_section_uids:
                sec=self.state.sections.get(uid)
                if sec:
                    key=f"{_clean_prog_for_elective(sec.for_program)}/Year {sec.batch_year}"
                    prog_yr[key]=uid
            summary_lines=[f"  {k}: {v}" for k,v in sorted(prog_yr.items())]
            msg=(f"Imported {imported} elective section(s).\n\n"
                 f"Active electives ({len(prog_yr)}):\n"+"\n".join(summary_lines))
            if warns:
                msg+=f"\n\nWarnings ({len(warns)}):\n"+"\n".join(warns[:12])
                if len(warns)>12: msg+=f"\n...+{len(warns)-12} more"
            messagebox.showinfo("Electives Imported",msg)
        except Exception as e:
            self._log(f"Electives import error: {e}","error"); messagebox.showerror("Import Error",str(e))
    def _schedule_all(self):
        if not self.state.sections: messagebox.showwarning("No Sections","Import a course list first."); return
        self._log("Scheduling all sections...")
        def run():
            t0=time.perf_counter(); sched=self.state.get_scheduler()
            result=sched.schedule_all(list(self.state.sections.values()))
            elapsed=time.perf_counter()-t0
            placed=sum(len(r["scheduled"]) for r in result["results"].values())
            failed=sum(len(r["unscheduled"]) for r in result["results"].values())
            self.state.save(); self.after(0,self.refresh_stats)
            self.after(0,lambda:self._log(f"Done {elapsed*1000:.0f}ms — {placed} placed, {failed} unplaced","success"))
            for w in result["warnings"][:5]: self.after(0,lambda m=w:self._log(f"Warning: {m}","warning"))
        threading.Thread(target=run,daemon=True).start()
    def _validate(self):
        rep=self.state.get_engine().validate()
        if not rep.has_conflict:
            self._log("Timetable valid — 0 conflicts.","success"); messagebox.showinfo("Validation","No conflicts.")
        else:
            self._log(f"{len(rep.conflicts)} conflicts.","error")
            messagebox.showerror("Conflicts","\n".join(rep.conflicts[:10])+
                (f"\n...+{len(rep.conflicts)-10} more" if len(rep.conflicts)>10 else""))
    def _advance_year(self):
        if messagebox.askyesno("Advance Year",
            "Advance all batch years by 1?\nYear 4 (2022) will graduate.\nNew Year 1 will need to be imported."):
            self.state.advance_year(); self.refresh_stats()
            self._log("All batch years advanced. Year 4 sections removed (graduated).","success")
    def _reset(self):
        if messagebox.askyesno("Reset ALL","Delete ALL data?"):
            self.state.reset_all(); self.refresh_stats(); self._log("All data reset.","warning")

# ─── Slot Picker ──────────────────────────────────────────────────────
class SlotPickerPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status
        self._btns={}; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,4))
        L(hdr,"Slot Picker — Click to enable/disable time slots",14,True,C["accent"]).pack(side="left")
        B(hdr,"Enable All",self._enable_all,C["btn_success"],12).pack(side="right",padx=4)
        B(hdr,"Disable All",self._disable_all,C["btn_danger"],12).pack(side="right",padx=4)
        B(hdr,"Save",self._save,C["accent"],10).pack(side="right",padx=4)
        lf=tk.Frame(self,bg=C["bg"]); lf.pack(fill="x",padx=20,pady=4)
        for col,lab in [(C["slot_on"],"Enabled"),(C["slot_off"],"Disabled")]:
            tk.Frame(lf,bg=col,width=16,height=16).pack(side="left",padx=(0,4))
            L(lf,lab,8).pack(side="left",padx=(0,16))
        self.ext_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(lf,text="Extend to 7:30pm",variable=self.ext_var,
                         command=self._rebuild).pack(side="left",padx=8)
        outer=tk.Frame(self,bg=C["bg"]); outer.pack(fill="both",expand=True,padx=20,pady=8)
        self.canvas=tk.Canvas(outer,bg=C["white"],highlightthickness=0)
        vsb=ttk.Scrollbar(outer,orient="vertical",command=self.canvas.yview)
        hsb=ttk.Scrollbar(outer,orient="horizontal",command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        self.canvas.pack(side="left",fill="both",expand=True)
        self.gf=tk.Frame(self.canvas,bg=C["white"])
        self.canvas.create_window((0,0),window=self.gf,anchor="nw")
        self.gf.bind("<Configure>",lambda e:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._rebuild()
    def _rebuild(self):
        for w in self.gf.winfo_children(): w.destroy()
        self._btns.clear()
        # Remember which IDs were previously known (before extended-mode toggle)
        prev_ids=set(self.state.slots.keys())
        slots_all=build_giki_slots(extended=self.ext_var.get())
        new_ids=set(slots_all.keys())
        # Req 4: when rebuilding (e.g. extended toggle), synchronise enabled_slots:
        #   • brand-new slots (added by extending) → enable by default
        #   • removed slots (no longer exist) → remove from enabled_slots
        #   • existing slots → keep their current on/off state
        added=new_ids-prev_ids; removed=prev_ids-new_ids
        self.state.enabled_slots|=added          # new slots start enabled
        self.state.enabled_slots-=removed        # stale slots cleaned up
        if not self.state.enabled_slots:         # guard: at least open all
            self.state.enabled_slots=set(new_ids)
        self.state.slots=slots_all
        days=list(DayOfWeek)
        time_keys=sorted(set((s.start_min,s.duration) for s in slots_all.values()))
        hfmt=dict(bg=C["header_bg"],fg=C["white"],font=(FF,8,"bold"),relief="flat",padx=2,pady=5)
        tk.Label(self.gf,text="Time",width=14,**hfmt).grid(row=0,column=0,sticky="nsew",padx=1,pady=1)
        for ci,day in enumerate(days):
            tk.Label(self.gf,text=day.value[:3].upper(),width=16,**hfmt).grid(row=0,column=ci+1,sticky="nsew",padx=1,pady=1)
        for ri,(sm,dur) in enumerate(time_keys):
            h,m=divmod(sm,60); eh,em=divmod(sm+dur,60)
            tlab=f"{h:02d}:{m:02d}-{eh:02d}:{em:02d}"; ttype=" Lab" if dur==180 else" Lec"
            tk.Label(self.gf,text=tlab+ttype,bg=C["accent"],fg=C["white"],
                      font=(FF,7),width=16,anchor="w",padx=4,pady=4
                      ).grid(row=ri+1,column=0,sticky="nsew",padx=1,pady=1)
            for ci,day in enumerate(days):
                matching=[s for s in slots_all.values() if s.day==day and s.start_min==sm and s.duration==dur]
                if not matching:
                    tk.Label(self.gf,text="",bg="#E8E8E8",width=16).grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1); continue
                slot=matching[0]
                on=slot.slot_id in self.state.enabled_slots
                bg=C["slot_on"] if on else C["slot_off"]
                cb=tk.Button(self.gf,text=f"{h:02d}:{m:02d}\n({'Lab' if dur==180 else 'Lec'})",
                              bg=bg,fg=C["white"] if on else C["text"],font=(FF,7),
                              width=16,relief="flat",cursor="hand2",padx=2,pady=3)
                cb.config(command=lambda b=cb,sid=slot.slot_id:self._toggle(b,sid))
                cb.grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1)
                self._btns[slot.slot_id]=cb
    def _toggle(self,b,sid):
        if sid in self.state.enabled_slots:
            self.state.enabled_slots.discard(sid); b.config(bg=C["slot_off"],fg=C["text"])
        else:
            self.state.enabled_slots.add(sid); b.config(bg=C["slot_on"],fg=C["white"])
    def _enable_all(self):
        self.state.enabled_slots=set(self.state.slots.keys())
        for b in self._btns.values(): b.config(bg=C["slot_on"],fg=C["white"])
    def _disable_all(self):
        self.state.enabled_slots.clear()
        for b in self._btns.values(): b.config(bg=C["slot_off"],fg=C["text"])
    def _save(self):
        n=len(self.state.enabled_slots)
        self.state.save(); self.on_status(f"Saved — {n} slots enabled")
        messagebox.showinfo("Saved",f"{n} time slots enabled.")

# ─── Timetable Grid ───────────────────────────────────────────────────
class TimetableGridPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Timetable Grid",14,True,C["accent"]).pack(side="left")
        B(hdr,"Refresh",self._refresh,w=10).pack(side="right",padx=4)
        ctrl=tk.Frame(self,bg=C["bg"]); ctrl.pack(fill="x",padx=20,pady=4)
        L(ctrl,"View:",9).pack(side="left")
        self.fv=tk.StringVar(value="ALL")
        cb=CB(ctrl,self.fv,ALL_PROGRAMS,14); cb.pack(side="left",padx=6)
        cb.bind("<<ComboboxSelected>>",lambda e:self._refresh())
        L(ctrl,"Year:",9).pack(side="left",padx=(12,4))
        self.yv=tk.StringVar(value="ALL")
        yc=CB(ctrl,self.yv,YEAR_FILTERS,24); yc.pack(side="left",padx=4)
        yc.bind("<<ComboboxSelected>>",lambda e:self._refresh())
        # Teacher name toggle
        self.show_teacher=tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl,text="Show Teacher",variable=self.show_teacher,
                         command=self._refresh).pack(side="left",padx=8)
        self.count_lbl=L(ctrl,"0 sessions",8,color=C["text_light"]); self.count_lbl.pack(side="right")
        outer=tk.Frame(self,bg=C["bg"]); outer.pack(fill="both",expand=True,padx=20,pady=8)
        self.canvas=tk.Canvas(outer,bg=C["white"],highlightthickness=0)
        vsb=ttk.Scrollbar(outer,orient="vertical",command=self.canvas.yview)
        hsb=ttk.Scrollbar(outer,orient="horizontal",command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        self.canvas.pack(side="left",fill="both",expand=True)
        self.gf=tk.Frame(self.canvas,bg=C["white"])
        self.canvas.create_window((0,0),window=self.gf,anchor="nw")
        self.gf.bind("<Configure>",lambda e:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._refresh()
    def _filter_sessions(self):
        fac=self.fv.get() if hasattr(self,"fv") else"ALL"
        yr=self.yv.get() if hasattr(self,"yv") else"ALL"
        bf=year_to_batch(yr)
        sessions=self.state.timetable.sessions
        _FACULTIES={"FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"}
        if fac not in ("ALL","—"):
            if fac in _FACULTIES:
                sessions=[s for s in sessions if s.faculty==fac]
            else:
                # Program/sub-dept filter: only match explicit for_program or section.program.
                # No code-prefix fallback — that caused CS112L sections belonging to AI/CE/CY
                # students to appear in the CS program view.
                def matches(s):
                    if s.for_program==fac: return True
                    sec=self.state.sections.get(s.section_uid)
                    return bool(sec and getattr(sec,'program','')==fac)
                sessions=[s for s in sessions if matches(s)]
        if bf:
            sessions=[s for s in sessions if s.batch_year==bf]
        return sessions
    @staticmethod
    def _detect_conflict(cs):
        """Return True if the sessions represent a real cohort/room/teacher conflict."""
        for i,a in enumerate(cs):
            for b in cs[i+1:]:
                if a.room_id==b.room_id: return True
                if a.teacher_id==b.teacher_id: return True
                if a.section_uid==b.section_uid: return True
                # Dept cohort clash: same batch/faculty/section, different courses
                if (a.batch_year and a.batch_year==b.batch_year
                        and a.faculty==b.faculty
                        and a.section_id and a.section_id==b.section_id
                        and a.section_uid!=b.section_uid):
                    return True
                # Prog cohort clash: same batch/program, different courses
                if (a.for_program and a.for_program==b.for_program
                        and a.batch_year==b.batch_year
                        and a.section_uid!=b.section_uid):
                    return True
        return False

    def _refresh(self,*_):
        for w in self.gf.winfo_children(): w.destroy()
        sessions=self._filter_sessions()
        fac=self.fv.get() if hasattr(self,"fv") else"ALL"
        yr=self.yv.get() if hasattr(self,"yv") else"ALL"
        _BROAD_VIEWS={"ALL","—","FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"}
        is_prog_view=fac not in _BROAD_VIEWS
        bf_active=bool(year_to_batch(yr))
        days=list(DayOfWeek)
        time_keys=sorted(set((sl.start_min,sl.duration) for sl in self.state.slots.values()))
        if not time_keys: L(self.gf,"No slots available for display.",9).pack(pady=20); return
        cell_map={}
        for sess in sessions:
            sl=self.state.slots.get(sess.slot_id)
            if sl: cell_map.setdefault((sl.day,sl.start_min,sl.duration),[]).append(sess)
        hfmt=dict(bg=C["header_bg"],fg=C["white"],font=(FF,8,"bold"),relief="flat",padx=2,pady=5)
        tk.Label(self.gf,text="Day",width=8,**hfmt).grid(row=0,column=0,sticky="nsew",padx=1,pady=1)
        for ci,(sm,dur) in enumerate(time_keys):
            h,m=divmod(sm,60); eh,em=divmod(sm+dur,60)
            typ=slot_type_label(dur)
            tk.Label(self.gf,text=f"{h:02d}:{m:02d}\n{eh:02d}:{em:02d}\n{typ}",width=16,**hfmt
                      ).grid(row=0,column=ci+1,sticky="nsew",padx=1,pady=1)
        show_t=self.show_teacher.get() if hasattr(self,"show_teacher") else True
        for ri,day in enumerate(days):
            tk.Label(self.gf,text=day.value[:3],bg=C["accent"],fg=C["white"],
                      font=(FF,8,"bold"),width=8,anchor="center",padx=2,pady=4
                      ).grid(row=ri+1,column=0,sticky="nsew",padx=1,pady=1)
            for ci,(sm,dur) in enumerate(time_keys):
                cs=cell_map.get((day,sm,dur),[])
                if cs:
                    conflict=self._detect_conflict(cs) or (is_prog_view and bf_active and len(cs)>1)
                    if conflict:
                        # Real conflict: red cell with CLASH indicator
                        codes=", ".join(dict.fromkeys(x.course_code for x in cs))
                        clash_text=f"⚠ CLASH\n{codes[:20]}\n({len(cs)} sessions)"
                        tk.Label(self.gf,text=clash_text,bg="#C0392B",fg="#FFFFFF",
                                  font=(FF,6,"bold"),width=16,justify="center",
                                  relief="ridge",padx=1,pady=2
                                  ).grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1)
                    elif len(cs)==1:
                        x=cs[0]; line=f"{x.course_code}\n{x.room_id}"
                        if show_t: line+=f"\n{x.teacher_id[:12]}"
                        bg=FAC_BG.get(x.faculty,"#F0F0F0")
                        tk.Label(self.gf,text=line,bg=bg,fg=C["text"],
                                  font=(FF,6),width=16,justify="center",relief="ridge",padx=1,pady=2
                                  ).grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1)
                    else:
                        # Multiple valid parallel sessions — stack each one
                        inner=tk.Frame(self.gf,bg=C["border"],bd=1,relief="ridge")
                        inner.grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1)
                        cap=min(len(cs),4)
                        fs=5 if cap>2 else 6
                        for j,x in enumerate(cs[:cap]):
                            bg=FAC_BG.get(x.faculty,"#F0F0F0")
                            line=f"{x.course_code}\n{x.room_id}"
                            if show_t and cap<=2: line+=f"\n{x.teacher_id[:10]}"
                            tk.Label(inner,text=line,bg=bg,fg=C["text"],
                                      font=(FF,fs),width=16,justify="center",
                                      relief="flat",padx=1,pady=1).pack(fill="x")
                            if j<cap-1:
                                tk.Frame(inner,bg=C["border"],height=1).pack(fill="x")
                        if len(cs)>4:
                            tk.Label(inner,text=f"...+{len(cs)-4} more",
                                      bg="#E8E8E8",fg=C["text_light"],
                                      font=(FF,5),width=16,justify="center",
                                      padx=1,pady=1).pack(fill="x")
                else:
                    tk.Label(self.gf,text="",bg="#F8F9FA",width=16,relief="flat"
                              ).grid(row=ri+1,column=ci+1,sticky="nsew",padx=1,pady=1)
        self.count_lbl.config(text=f"{len(sessions)} sessions")

# ─── Section View Panel ───────────────────────────────────────────────
class SectionViewPanel(tk.Frame):
    """Section-wise timetable: select a specific section and see its full schedule."""
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Section Timetable View",14,True,C["accent"]).pack(side="left")
        B(hdr,"Print PDF",self._print_pdf,C["btn_success"],12).pack(side="right",padx=4)
        B(hdr,"Print Faculty PDF",self._print_fac_pdf,C["accent"],16).pack(side="right",padx=4)
        ctrl=tk.Frame(self,bg=C["bg"]); ctrl.pack(fill="x",padx=20,pady=4)
        L(ctrl,"Faculty/Program:",9).pack(side="left")
        self.fv=tk.StringVar(value="ALL")
        cb=CB(ctrl,self.fv,ALL_PROGRAMS,14); cb.pack(side="left",padx=6)
        cb.bind("<<ComboboxSelected>>",lambda e:self._load_sections())
        L(ctrl,"Year:",9).pack(side="left",padx=(12,4))
        self.yv=tk.StringVar(value="ALL")
        yc=CB(ctrl,self.yv,YEAR_FILTERS,24); yc.pack(side="left",padx=4)
        yc.bind("<<ComboboxSelected>>",lambda e:self._load_sections())
        L(ctrl,"Course with Section:",9).pack(side="left",padx=(12,4))
        self.sv=tk.StringVar()
        self.sec_cb=CB(ctrl,self.sv,[],24); self.sec_cb.pack(side="left",padx=4)
        self.sec_cb.bind("<<ComboboxSelected>>",lambda e:self._show_section())
        self.show_teacher=tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl,text="Show Teacher",variable=self.show_teacher,
                         command=self._show_section).pack(side="left",padx=8)
        # Grid canvas
        outer=tk.Frame(self,bg=C["bg"]); outer.pack(fill="both",expand=True,padx=20,pady=8)
        self.canvas=tk.Canvas(outer,bg=C["white"],highlightthickness=0)
        vsb=ttk.Scrollbar(outer,orient="vertical",command=self.canvas.yview)
        hsb=ttk.Scrollbar(outer,orient="horizontal",command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        self.canvas.pack(side="left",fill="both",expand=True)
        self.gf=tk.Frame(self.canvas,bg=C["white"])
        self.canvas.create_window((0,0),window=self.gf,anchor="nw")
        self.gf.bind("<Configure>",lambda e:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._load_sections()
    def _load_sections(self,*_):
        fac=self.fv.get()
        yr=self.yv.get() if hasattr(self,"yv") else"ALL"
        bf=year_to_batch(yr)
        _FACULTIES={"FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"}
        def matches(s):
            if fac=="ALL" or fac=="—": return True
            if fac in _FACULTIES: return s.faculty==fac
            return getattr(s,'program','')==fac
        uids=["ALL — Show All"]+[uid for uid,s in sorted(self.state.sections.items())
              if matches(s) and (not bf or s.batch_year==bf)]
        self.sec_cb["values"]=uids
        cur=self.sv.get()
        if cur not in uids:
            self.sv.set(uids[0] if uids else ""); self._show_section()
    def _show_section(self,*_):
        for w in self.gf.winfo_children(): w.destroy()
        uid=self.sv.get()
        if not uid: return

        # ── ALL mode: collect sessions for every visible section ──────
        is_all = uid.startswith("ALL")
        if is_all:
            fac=self.fv.get() if hasattr(self,"fv") else"ALL"
            yr=self.yv.get() if hasattr(self,"yv") else"ALL"
            bf=year_to_batch(yr)
            _FACULTIES={"FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"}
            def _matches(s):
                if fac in("ALL","—"): return True
                if fac in _FACULTIES: return s.faculty==fac
                return getattr(s,'program','')==fac
            visible_uids=[u for u,s in self.state.sections.items()
                          if _matches(s) and (not bf or s.batch_year==bf)]
            sess_list=[]
            for vu in visible_uids:
                sess_list.extend(self.state.timetable.get_sessions_by_section(vu))
            sec=None
            info_text=(f"All sections"
                       +(f" — {fac}" if fac not in("ALL","—") else"")
                       +(f" — {yr}" if yr!="ALL" else"")
                       +f"   ({len(visible_uids)} sections, {len(sess_list)} sessions)")
        else:
            sec=self.state.sections.get(uid)
            sess_list=self.state.timetable.get_sessions_by_section(uid)
            batch_label=BATCH_LABEL.get(sec.batch_year if sec else 0,"")
            info_text=f"Section: {uid}   Batch: {batch_label}   Faculty: {sec.faculty if sec else ''}"

        days=list(DayOfWeek)
        time_keys=sorted(set((sl.start_min,sl.duration) for sl in self.state.slots.values()))

        # Build cell map — support multiple sessions per cell in ALL mode
        cell_map={}
        for sess in sess_list:
            sl=self.state.slots.get(sess.slot_id)
            if sl: cell_map.setdefault((sl.day,sl.start_min,sl.duration),[]).append(sess)

        # Header info
        L(self.gf,info_text,9,bold=True,color=C["accent"],bg=C["white"]).grid(
            row=0,column=0,columnspan=len(time_keys)+1,sticky="w",padx=8,pady=6)
        hfmt=dict(bg=C["header_bg"],fg=C["white"],font=(FF,8,"bold"),relief="flat",padx=2,pady=5)
        tk.Label(self.gf,text="Day",width=8,**hfmt).grid(row=1,column=0,sticky="nsew",padx=1,pady=1)
        for ci,(sm,dur) in enumerate(time_keys):
            h,m=divmod(sm,60); eh,em=divmod(sm+dur,60)
            typ=slot_type_label(dur)
            tk.Label(self.gf,text=f"{h:02d}:{m:02d}\n{eh:02d}:{em:02d}\n{typ}",width=16,**hfmt
                      ).grid(row=1,column=ci+1,sticky="nsew",padx=1,pady=1)
        show_t=self.show_teacher.get()
        default_bg=FAC_BG.get(sec.faculty if sec else "FCSE","#D6E4F0")

        for ri,day in enumerate(days):
            tk.Label(self.gf,text=day.value[:3],bg=C["accent"],fg=C["white"],
                      font=(FF,8,"bold"),width=8,padx=2,pady=4
                      ).grid(row=ri+2,column=0,sticky="nsew",padx=1,pady=1)
            for ci,(sm,dur) in enumerate(time_keys):
                cell_sessions=cell_map.get((day,sm,dur),[])
                if not cell_sessions:
                    tk.Label(self.gf,text="",bg="#F8F9FA",width=16,relief="flat"
                              ).grid(row=ri+2,column=ci+1,sticky="nsew",padx=1,pady=1)
                elif len(cell_sessions)==1:
                    sess=cell_sessions[0]
                    bg_color=FAC_BG.get(sess.faculty,default_bg)
                    text=f"{sess.course_code}\n{sess.room_id}"
                    if show_t: text+=f"\n{sess.teacher_id[:14]}"
                    tk.Label(self.gf,text=text,bg=bg_color,fg=C["text"],
                              font=(FF,7),width=16,justify="center",relief="ridge",padx=1,pady=3
                              ).grid(row=ri+2,column=ci+1,sticky="nsew",padx=1,pady=1)
                else:
                    # Multiple sessions in this cell (ALL mode)
                    inner=tk.Frame(self.gf,bg=C["border"],bd=1,relief="ridge")
                    inner.grid(row=ri+2,column=ci+1,sticky="nsew",padx=1,pady=1)
                    cap=min(len(cell_sessions),4); fs=5 if cap>2 else 6
                    for j,x in enumerate(cell_sessions[:cap]):
                        bg=FAC_BG.get(x.faculty,"#F0F0F0")
                        line=f"{x.course_code}\n{x.room_id}"
                        if show_t and cap<=2: line+=f"\n{x.teacher_id[:10]}"
                        tk.Label(inner,text=line,bg=bg,fg=C["text"],
                                  font=(FF,fs),width=16,justify="center",
                                  relief="flat",padx=1,pady=1).pack(fill="x")
                        if j<cap-1:
                            tk.Frame(inner,bg=C["border"],height=1).pack(fill="x")
                    if len(cell_sessions)>4:
                        tk.Label(inner,text=f"...+{len(cell_sessions)-4} more",
                                  bg="#E8E8E8",fg=C["text_light"],
                                  font=(FF,5),width=16,justify="center",
                                  padx=1,pady=1).pack(fill="x")
    def _print_pdf(self):
        if not PDF_OK: messagebox.showerror("Missing","pip install reportlab"); return
        uid=self.sv.get()
        if not uid or uid.startswith("ALL"):
            messagebox.showwarning("No section","Select a specific section (not ALL) to print."); return
        path=filedialog.asksaveasfilename(title="Save Section PDF",
            defaultextension=".pdf",initialfile=f"Timetable_{uid}.pdf",
            filetypes=[("PDF","*.pdf")])
        if not path: return
        try:
            export_section_pdf(self.state.timetable,self.state.slots,
                                self.state.sections,self.state.courses,
                                path,uid,self.show_teacher.get())
            messagebox.showinfo("Exported",f"PDF saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))
    def _print_fac_pdf(self):
        if not PDF_OK: messagebox.showerror("Missing","pip install reportlab"); return
        fac=self.fv.get(); filt=None if fac in("ALL","—") else fac
        path=filedialog.asksaveasfilename(title="Save Faculty PDF",
            defaultextension=".pdf",initialfile=f"Timetable_{fac}.pdf",
            filetypes=[("PDF","*.pdf")])
        if not path: return
        try:
            export_faculty_pdf(self.state.timetable,self.state.slots,
                                self.state.sections,path,filt,
                                self.show_teacher.get(),f"GIKI Timetable — {fac}")
            messagebox.showinfo("Exported",f"PDF saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))
    def _refresh(self,*_): self._load_sections()

# ─── Courses ──────────────────────────────────────────────────────────
class CoursesPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Courses",14,True,C["accent"]).pack(side="left")
        B(hdr,"Add",self._add,w=8).pack(side="right",padx=3)
        B(hdr,"Edit",self._edit,w=8).pack(side="right",padx=3)
        B(hdr,"Delete",self._delete,C["btn_danger"],8).pack(side="right",padx=3)
        sf=tk.Frame(self,bg=C["bg"]); sf.pack(fill="x",padx=20,pady=4)
        L(sf,"Search:",9).pack(side="left",padx=(0,6))
        self.sv=tk.StringVar(); self.sv.trace("w",lambda *a:self._refresh())
        E(sf,30,self.sv).pack(side="left")
        cols=("code","title","ch","type","faculty","program","lab_type")
        heads=("Code","Title","Credit Hrs","Type","Faculty","Program","Lab Type")
        widths={"code":80,"title":240,"ch":70,"type":80,"faculty":70,"program":70,"lab_type":90}
        frame,self.tree=TV(self,cols,heads,widths,20)
        frame.pack(fill="both",expand=True,padx=20,pady=8)
        self.tree.bind("<Double-1>",lambda e:self._edit()); self._refresh()
    def _refresh(self,*_):
        q=self.sv.get().lower() if hasattr(self,"sv") else""
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,(k,c) in enumerate(sorted(self.state.courses.items())):
            if q and q not in k.lower() and q not in c.title.lower(): continue
            tag="even" if i%2==0 else"odd"
            self.tree.insert("","end",values=(c.course_code,c.title,c.credit_hours,
                c.session_type.value,c.faculty,getattr(c,'program',''),c.lab_type or""),tags=(tag,))
    def _add(self): _CourseDialog(self,self.state,self._refresh)
    def _edit(self):
        sel=self.tree.selection()
        if not sel: return
        code=self.tree.item(sel[0])["values"][0]
        _CourseDialog(self,self.state,self._refresh,existing=self.state.courses.get(code))
    def _delete(self):
        sel=self.tree.selection()
        if not sel: messagebox.showwarning("No selection","Select a course."); return
        code=self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm",f"Delete '{code}'?"):
            self.state.courses.pop(code,None); self.state.save(); self._refresh()

# ─── Teachers ─────────────────────────────────────────────────────────
class TeachersPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Teachers",14,True,C["accent"]).pack(side="left")
        B(hdr,"Add",self._add,w=8).pack(side="right",padx=3)
        B(hdr,"Edit",self._edit,w=8).pack(side="right",padx=3)
        B(hdr,"Delete",self._delete,C["btn_danger"],8).pack(side="right",padx=3)
        sf=tk.Frame(self,bg=C["bg"]); sf.pack(fill="x",padx=20,pady=4)
        L(sf,"Search:",9).pack(side="left",padx=(0,6))
        self.sv=tk.StringVar(); self.sv.trace("w",lambda *a:self._refresh())
        E(sf,30,self.sv).pack(side="left")
        cols=("id","name","faculty","combined","unavail")
        heads=("Teacher ID","Full Name","Faculty","Combined OK","Unavailable")
        widths={"id":170,"name":240,"faculty":70,"combined":90,"unavail":200}
        frame,self.tree=TV(self,cols,heads,widths,22)
        frame.pack(fill="both",expand=True,padx=20,pady=8)
        self.tree.bind("<Double-1>",lambda e:self._edit()); self._refresh()
    def _refresh(self,*_):
        q=self.sv.get().lower() if hasattr(self,"sv") else""
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,(k,t) in enumerate(sorted(self.state.teachers.items())):
            if q and q not in k.lower() and q not in t.name.lower(): continue
            tag="even" if i%2==0 else"odd"
            unavail=", ".join(d.value for d in t.unavailable_days) or"None"
            combined="Yes" if getattr(t,'can_combined',False) else"No"
            self.tree.insert("","end",values=(t.teacher_id,t.name,t.faculty,combined,unavail),tags=(tag,))
    def _add(self): _TeacherDialog(self,self.state,self._refresh)
    def _edit(self):
        sel=self.tree.selection()
        if not sel: return
        tid=self.tree.item(sel[0])["values"][0]
        _TeacherDialog(self,self.state,self._refresh,existing=self.state.teachers.get(tid))
    def _delete(self):
        sel=self.tree.selection()
        if not sel: return
        tid=self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm",f"Delete '{tid}'?"):
            self.state.teachers.pop(tid,None); self.state.save(); self._refresh()

# ─── Sections ─────────────────────────────────────────────────────────
class SectionsPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Sections",14,True,C["accent"]).pack(side="left")
        B(hdr,"Add",self._add,w=8).pack(side="right",padx=3)
        B(hdr,"Edit",self._edit,w=8).pack(side="right",padx=3)
        B(hdr,"Delete",self._delete,C["btn_danger"],8).pack(side="right",padx=3)
        B(hdr,"Reschedule",self._reschedule,C["btn_success"],12).pack(side="right",padx=3)
        ff=tk.Frame(self,bg=C["bg"]); ff.pack(fill="x",padx=20,pady=4)
        L(ff,"View:",9).pack(side="left")
        self.fv=tk.StringVar(value="ALL")
        cb=CB(ff,self.fv,ALL_PROGRAMS,14); cb.pack(side="left",padx=6)
        cb.bind("<<ComboboxSelected>>",lambda e:self._refresh())
        L(ff,"Year:",9).pack(side="left",padx=(12,4))
        self.yv=tk.StringVar(value="ALL")
        yc=CB(ff,self.yv,YEAR_FILTERS,24)
        yc.pack(side="left",padx=4); yc.bind("<<ComboboxSelected>>",lambda e:self._refresh())
        cols=("uid","sid","course","teacher","year","faculty","prog","students")
        heads=("Full UID","Sec ID","Course","Teacher","Batch Year","Faculty","Program","Students")
        widths={"uid":140,"sid":60,"course":80,"teacher":190,"year":160,"faculty":70,"prog":60,"students":70}
        frame,self.tree=TV(self,cols,heads,widths,20)
        frame.pack(fill="both",expand=True,padx=20,pady=8)
        self.tree.bind("<Double-1>",lambda e:self._edit()); self._refresh()
    def _refresh(self,*_):
        filt=self.fv.get() if hasattr(self,"fv") else"ALL"
        yr=self.yv.get() if hasattr(self,"yv") else"ALL"
        bf=year_to_batch(yr)
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,(k,s) in enumerate(sorted(self.state.sections.items())):
            if filt not in("ALL","—"):
                if filt in("FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"):
                    if s.faculty!=filt: continue
                else:
                    if s.program!=filt: continue
            if bf and s.batch_year!=bf: continue
            tag="even" if i%2==0 else"odd"
            bl=BATCH_LABEL.get(s.batch_year,f"Year {s.batch_year}")
            self.tree.insert("","end",values=(
                s.uid,s.section_id,s.course_code,s.teacher_id,
                bl,s.faculty,getattr(s,'program',''),s.num_students),tags=(tag,))
    def _add(self): _SectionDialog(self,self.state,self._refresh)
    def _edit(self):
        sel=self.tree.selection()
        if not sel: return
        uid=self.tree.item(sel[0])["values"][0]
        _SectionDialog(self,self.state,self._refresh,existing=self.state.sections.get(uid))
    def _delete(self):
        sel=self.tree.selection()
        if not sel: return
        uid=self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm",f"Delete '{uid}'?"):
            self.state.timetable.clear_section(uid); self.state.sections.pop(uid,None)
            self.state.save(); self._refresh()
    def _reschedule(self):
        sel=self.tree.selection()
        if not sel: messagebox.showwarning("No selection","Select a section."); return
        uid=self.tree.item(sel[0])["values"][0]
        if uid not in self.state.sections: return
        r=self.state.get_scheduler().adjust_section(self.state.sections[uid])
        self.state.save(); placed=len(r["scheduled"])
        self.on_status(f"Rescheduled {uid}: {placed} placed")
        messagebox.showinfo("Rescheduled",f"'{uid}': {placed} sessions placed.")

# ─── Electives ────────────────────────────────────────────────────────
class ElectivesPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        L(self,"Elective Scheduling",14,True,C["accent"]).pack(pady=(16,4))
        L(self,"Schedule electives taken by students from multiple sections / batch years.",
           9,color=C["text_light"]).pack(pady=(0,12))
        form=tk.Frame(self,bg=C["white"],highlightthickness=1,highlightbackground=C["border"])
        form.pack(fill="x",padx=30,pady=8,ipady=12)
        rows=[("Elective Course Code:","code_var"),
              ("Requesting Section UIDs (comma-sep):","secs_var"),
              ("Shared Teacher ID (optional):","teacher_var")]
        for ri,(lab,vn) in enumerate(rows):
            L(form,lab,9,bg=C["white"]).grid(row=ri,column=0,sticky="e",padx=(20,8),pady=6)
            var=tk.StringVar(); setattr(self,vn,var)
            w=48 if"Section"in lab else 30
            E(form,w,var).grid(row=ri,column=1,sticky="w",padx=(0,20),pady=6)
        L(form,"Credit Hours (override):",9,bg=C["white"]).grid(row=3,column=0,sticky="e",padx=(20,8),pady=6)
        self.ch_var=tk.StringVar()
        E(form,8,self.ch_var).grid(row=3,column=1,sticky="w",pady=6)
        L(form,"(leave blank to use course default)",8,color=C["text_light"],bg=C["white"]).grid(row=3,column=2,sticky="w")
        L(form,"Preferred Day:",9,bg=C["white"]).grid(row=4,column=0,sticky="e",padx=(20,8),pady=6)
        self.day_var=tk.StringVar(value="Any")
        CB(form,self.day_var,["Any","Monday","Tuesday","Wednesday","Thursday","Friday"],12
           ).grid(row=4,column=1,sticky="w",pady=6)
        B(form,"Schedule Elective",self._schedule,C["btn_success"],22).grid(row=5,column=0,columnspan=2,pady=12)
        L(self,"Results",11,True).pack(pady=(12,4),anchor="w",padx=30)
        cols=("section","course","day","time","room","teacher")
        heads=("Section","Course","Day","Time","Room","Teacher")
        widths={"section":150,"course":100,"day":100,"time":120,"room":130,"teacher":180}
        frame,self.tree=TV(self,cols,heads,widths,12)
        frame.pack(fill="both",expand=True,padx=30,pady=8)
    def _schedule(self):
        code=self.code_var.get().strip().upper()
        if not code: messagebox.showwarning("Missing","Enter a course code."); return
        if code not in self.state.courses:
            messagebox.showwarning("Not found",f"Course '{code}' not in courses."); return
        uids=[u.strip() for u in self.secs_var.get().split(",") if u.strip()]
        secs=[self.state.sections[u] for u in uids if u in self.state.sections]
        if not secs: messagebox.showwarning("Not found","No valid section UIDs found."); return
        # Override credit hours if specified
        ch_override=self.ch_var.get().strip()
        if ch_override:
            try:
                orig_ch=self.state.courses[code].credit_hours
                self.state.courses[code].credit_hours=int(ch_override)
            except: pass
        result=self.state.get_scheduler().add_elective_for_sections(code,secs)
        if ch_override:
            try: self.state.courses[code].credit_hours=orig_ch
            except: pass
        self.state.save()
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,sess in enumerate(result["scheduled"]):
            sl=self.state.slots.get(sess.slot_id)
            ts=f"{sl.start_str}-{sl.end_str}" if sl else"?"; ds=sl.day.value if sl else"?"
            tag="even" if i%2==0 else"odd"
            self.tree.insert("","end",values=(sess.section_uid,sess.course_code,ds,ts,
                sess.room_id,sess.teacher_id),tags=(tag,))
        placed=len(result["scheduled"])
        self.on_status(f"Elective {code}: {placed} sessions placed")

# ─── Clash ────────────────────────────────────────────────────────────
class ClashPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        L(self,"Clash Check / Free Slot Finder",14,True,C["accent"]).pack(pady=(16,8))
        form=tk.Frame(self,bg=C["white"],highlightthickness=1,highlightbackground=C["border"])
        form.pack(fill="x",padx=30,pady=8,ipady=12)
        for ri,(lab,vn) in enumerate([("Teacher ID:","tid_var"),("Section UID:","uid_var"),
            ("Course Code:","code_var"),("Preferred Time HH:MM:","time_var")]):
            L(form,lab,9,bg=C["white"]).grid(row=ri,column=0,sticky="e",padx=(20,8),pady=6)
            var=tk.StringVar(); setattr(self,vn,var)
            E(form,24,var).grid(row=ri,column=1,sticky="w",padx=(0,20),pady=6)
        L(form,"Session Type:",9,bg=C["white"]).grid(row=4,column=0,sticky="e",padx=(20,8),pady=6)
        self.sv=tk.StringVar(value="Lecture")
        CB(form,self.sv,["Lecture","Lab"],12).grid(row=4,column=1,sticky="w",pady=6)
        B(form,"Find Free Slots",self._find,C["btn_success"],20).grid(row=5,column=0,columnspan=2,pady=12)
        frame,self.tree=TV(self,("slot_id","day","time","rooms"),
            ("Slot ID","Day","Time","Available Rooms"),
            {"slot_id":160,"day":110,"time":130,"rooms":400},14)
        frame.pack(fill="both",expand=True,padx=30,pady=8)
    def _find(self):
        code=self.code_var.get().strip()
        if not code: messagebox.showwarning("Missing","Enter a course code."); return
        stype=SessionType.LAB if self.sv.get()=="Lab" else SessionType.LECTURE
        pref=self.time_var.get().strip(); pm=None
        if pref:
            try: h,m=map(int,pref.split(":")); pm=h*60+m
            except: pass
        results=self.state.get_engine().find_free_slots(
            self.tid_var.get().strip(),self.uid_var.get().strip(),code,stype)
        if pm: results.sort(key=lambda x:abs(
            self.state.slots[x["slot_id"]].start_min-pm if x["slot_id"] in self.state.slots else 9999))
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,r in enumerate(results):
            tag="even" if i%2==0 else"odd"
            self.tree.insert("","end",values=(r["slot_id"],r["day"],r["time"],
                ", ".join(r["rooms"][:5])),tags=(tag,))
        self.on_status(f"Found {len(results)} free slots for {code}")

# ─── Rooms ────────────────────────────────────────────────────────────
class RoomsPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        hdr=tk.Frame(self,bg=C["bg"]); hdr.pack(fill="x",padx=20,pady=(16,8))
        L(hdr,"Buildings & Rooms",14,True,C["accent"]).pack(side="left")
        B(hdr,"Add Room",self._add,w=10).pack(side="right",padx=3)
        B(hdr,"Edit Room",self._edit,w=10).pack(side="right",padx=3)
        B(hdr,"Remove",self._remove,C["btn_danger"],10).pack(side="right",padx=3)
        B(hdr,"Export Table",self._export,w=14).pack(side="right",padx=3)
        sf=tk.Frame(self,bg=C["bg"]); sf.pack(fill="x",padx=20,pady=4)
        L(sf,"Filter building:",9).pack(side="left")
        self.bv=tk.StringVar(value="ALL")
        bids=["ALL"]+sorted(BUILDINGS.keys())
        CB(sf,self.bv,bids,16).pack(side="left",padx=6)
        if hasattr(self,"bv"): pass
        cols=("room_id","building","capacity","type","priority","large_hall","notes")
        heads=("Room ID","Building","Cap","Type","Priority Faculties","Large Hall","Notes")
        widths={"room_id":120,"building":160,"capacity":50,"type":110,"priority":150,"large_hall":80,"notes":240}
        frame,self.tree=TV(self,cols,heads,widths,24)
        frame.pack(fill="both",expand=True,padx=20,pady=8)
        self.tree.bind("<Double-1>",lambda e:self._edit()); self._refresh()
    def _refresh(self,*_):
        from config.buildings import get_all_rooms_table
        filt=self.bv.get() if hasattr(self,"bv") else"ALL"
        for r in self.tree.get_children(): self.tree.delete(r)
        for i,r in enumerate(get_all_rooms_table()):
            if filt!="ALL" and r["short"]!=filt and r["room_id"].split("-")[0]!=filt: continue
            tag="even" if i%2==0 else"odd"
            is_large="Yes" if r["room_id"] in LARGE_HALLS else""
            self.tree.insert("","end",values=(r["room_id"],r["building"],r["capacity"],
                r["type"],r["priority_for"],is_large,r["notes"]),tags=(tag,))
    def _add(self): _RoomDialog(self,self.state,self._refresh)
    def _edit(self):
        sel=self.tree.selection()
        if not sel: return
        rid=self.tree.item(sel[0])["values"][0]
        room=self.state.rooms.get(rid)
        if room: _RoomDialog(self,self.state,self._refresh,existing=room)
    def _remove(self):
        sel=self.tree.selection()
        if not sel: return
        rid=self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm",f"Remove '{rid}'?"):
            remove_room(rid); self._refresh()
    def _export(self):
        path=filedialog.asksaveasfilename(title="Export",defaultextension=".xlsx",
            initialfile="GIKI_Buildings_Rooms.xlsx",filetypes=[("Excel","*.xlsx")])
        if not path: return
        try: export_buildings_table_excel(path); messagebox.showinfo("Exported",f"Saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))

# ─── Export ───────────────────────────────────────────────────────────
class ExportPanel(tk.Frame):
    def __init__(self,p,state,on_status):
        super().__init__(p,bg=C["bg"]); self.state=state; self.on_status=on_status; self._build()
    def _build(self):
        L(self,"Export Timetable",14,True,C["accent"]).pack(pady=(16,8))
        card=tk.Frame(self,bg=C["white"],highlightthickness=1,highlightbackground=C["border"])
        card.pack(fill="x",padx=30,pady=8,ipady=12,ipadx=16)
        r0=tk.Frame(card,bg=C["white"]); r0.pack(fill="x",pady=8)
        L(r0,"Faculty/Program:",9,bg=C["white"]).pack(side="left",padx=(0,8))
        self.fv=tk.StringVar(value="ALL")
        CB(r0,self.fv,ALL_PROGRAMS,16).pack(side="left")
        self.show_t=tk.BooleanVar(value=True)
        ttk.Checkbutton(r0,text="Include teacher names",variable=self.show_t).pack(side="left",padx=16)
        for lab,desc,col,cmd in [
            ("Export Excel","Color-coded grid, one sheet per faculty",C["btn_success"],self._excel),
            ("Export Text","Plain text",C["btn"],self._text),
            ("Export Faculty PDF","Landscape grid PDF",C["accent"],self._fac_pdf),
            ("Export Buildings & Rooms","Reference table",C["sidebar"],self._buildings),
        ]:
            row=tk.Frame(card,bg=C["white"]); row.pack(fill="x",pady=6)
            B(row,lab,cmd,color=col,w=26).pack(side="left",padx=(0,12))
            L(row,desc,8,color=C["text_light"],bg=C["white"]).pack(side="left")
    def _fac(self):
        fac=self.fv.get(); return None if fac in("ALL","—") else fac
    def _excel(self):
        fac=self.fv.get()
        path=filedialog.asksaveasfilename(title="Save Excel",defaultextension=".xlsx",
            initialfile=f"GIKI_Timetable_{fac}.xlsx",filetypes=[("Excel","*.xlsx")])
        if not path: return
        try:
            export_excel(self.state.timetable,self.state.slots,self.state.courses,path,
                          faculty_filter=self._fac(),title=f"GIKI Timetable — {fac}")
            messagebox.showinfo("Exported",f"Saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))
    def _text(self):
        fac=self.fv.get()
        path=filedialog.asksaveasfilename(title="Save Text",defaultextension=".txt",
            initialfile="GIKI_Timetable.txt",filetypes=[("Text","*.txt")])
        if not path: return
        export_text(self.state.timetable,self.state.slots,path,faculty_filter=self._fac())
        messagebox.showinfo("Exported",f"Saved:\n{path}")
    def _fac_pdf(self):
        if not PDF_OK: messagebox.showerror("Missing","pip install reportlab"); return
        fac=self.fv.get()
        path=filedialog.asksaveasfilename(title="Save PDF",defaultextension=".pdf",
            initialfile=f"GIKI_Timetable_{fac}.pdf",filetypes=[("PDF","*.pdf")])
        if not path: return
        try:
            export_faculty_pdf(self.state.timetable,self.state.slots,
                                self.state.sections,path,self._fac(),
                                self.show_t.get(),f"GIKI Timetable — {fac}")
            messagebox.showinfo("Exported",f"Saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))
    def _buildings(self):
        path=filedialog.asksaveasfilename(title="Save Buildings",defaultextension=".xlsx",
            initialfile="GIKI_Buildings_Rooms.xlsx",filetypes=[("Excel","*.xlsx")])
        if not path: return
        try: export_buildings_table_excel(path); messagebox.showinfo("Exported",f"Saved:\n{path}")
        except Exception as e: messagebox.showerror("Error",str(e))

# ─── Dialogs ──────────────────────────────────────────────────────────
class _BD(tk.Toplevel):
    def __init__(self,p,title,state,on_done):
        super().__init__(p); self.state=state; self.on_done=on_done
        self.title(title); self.configure(bg=C["bg"]); self.resizable(False,False)
        self.grab_set(); self._fields={}; self._build(); self.wait_window()
    def _row(self,f,label,vn,row,default=""):
        L(f,label,9).grid(row=row,column=0,sticky="e",padx=(16,8),pady=5)
        var=tk.StringVar(value=default)
        E(f,28,var).grid(row=row,column=1,sticky="w",padx=(0,16),pady=5)
        self._fields[vn]=var; return var
    def _build(self): pass
    def _save(self): pass

class _CourseDialog(_BD):
    def __init__(self,p,state,on_done,existing=None):
        self._ex=existing; super().__init__(p,"Edit Course" if existing else"Add Course",state,on_done)
    def _build(self):
        e=self._ex; f=tk.Frame(self,bg=C["bg"]); f.pack(padx=20,pady=16)
        self._row(f,"Course Code:","code",0,e.course_code if e else"")
        self._row(f,"Title:","title",1,e.title if e else"")
        self._row(f,"Credit Hours:","ch",2,str(e.credit_hours) if e else"3")
        L(f,"Faculty:",9).grid(row=3,column=0,sticky="e",padx=(16,8),pady=5)
        self._fac=tk.StringVar(value=e.faculty if e else"FCSE")
        CB(f,self._fac,["FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"],12
           ).grid(row=3,column=1,sticky="w",pady=5)
        L(f,"Program/Sub-dept:",9).grid(row=4,column=0,sticky="e",padx=(16,8),pady=5)
        self._prog=tk.StringVar(value=getattr(e,'program','') if e else"")
        CB(f,self._prog,["","CS","CE","AI","CY","DS","SE","EE","ME","MTE","CVE","ES","MGS"],12
           ).grid(row=4,column=1,sticky="w",pady=5)
        self._row(f,"Lab Type:","lab_type",5,e.lab_type if e else"")
        L(f,"Session Type:",9).grid(row=6,column=0,sticky="e",padx=(16,8),pady=5)
        self._st=tk.StringVar(value=e.session_type.value if e else"Lecture")
        CB(f,self._st,["Lecture","Lab"],12).grid(row=6,column=1,sticky="w",pady=5)
        B(f,"Save",self._save,C["btn_success"],20).grid(row=7,column=0,columnspan=2,pady=12)
    def _save(self):
        code=self._fields["code"].get().strip().upper()
        if not code: messagebox.showwarning("Required","Code required.",parent=self); return
        try: ch=int(self._fields["ch"].get().strip() or"2")
        except: ch=2
        st=SessionType.LAB if self._st.get()=="Lab" else SessionType.LECTURE
        c=Course(code,self._fields["title"].get().strip(),ch,st,self._fac.get(),[],
                  self._fields["lab_type"].get().strip())
        c.program=self._prog.get(); self.state.courses[code]=c
        self.state.save(); self.on_done(); self.destroy()

class _TeacherDialog(_BD):
    def __init__(self,p,state,on_done,existing=None):
        self._ex=existing; super().__init__(p,"Edit Teacher" if existing else"Add Teacher",state,on_done)
    def _build(self):
        e=self._ex; f=tk.Frame(self,bg=C["bg"]); f.pack(padx=20,pady=16)
        self._row(f,"Teacher ID:","tid",0,e.teacher_id if e else"")
        self._row(f,"Full Name:","name",1,e.name if e else"")
        L(f,"Faculty:",9).grid(row=2,column=0,sticky="e",padx=(16,8),pady=5)
        self._fac=tk.StringVar(value=e.faculty if e else"FCSE")
        CB(f,self._fac,["FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"],12
           ).grid(row=2,column=1,sticky="w",pady=5)
        ud=", ".join(d.value for d in e.unavailable_days) if e else""
        self._row(f,"Unavailable Days (e.g. Friday):","unavail",3,ud)
        L(f,"Can teach combined sections\n(MLH / large halls):",9).grid(
            row=4,column=0,sticky="e",padx=(16,8),pady=5)
        self._comb=tk.BooleanVar(value=getattr(e,'can_combined',False) if e else False)
        ttk.Checkbutton(f,variable=self._comb).grid(row=4,column=1,sticky="w")
        B(f,"Save",self._save,C["btn_success"],20).grid(row=5,column=0,columnspan=2,pady=12)
    def _save(self):
        tid=self._fields["tid"].get().strip()
        if not tid: messagebox.showwarning("Required","Teacher ID required.",parent=self); return
        unavail=[]
        for d in self._fields["unavail"].get().split(","):
            d=d.strip().capitalize()
            try: unavail.append(DayOfWeek(d))
            except: pass
        t=Teacher(tid,self._fields["name"].get().strip(),self._fac.get(),unavail)
        t.can_combined=self._comb.get(); self.state.teachers[tid]=t
        self.state.save(); self.on_done(); self.destroy()

class _SectionDialog(_BD):
    def __init__(self,p,state,on_done,existing=None):
        self._ex=existing; super().__init__(p,"Edit Section" if existing else"Add Section",state,on_done)
    def _build(self):
        e=self._ex; f=tk.Frame(self,bg=C["bg"]); f.pack(padx=20,pady=16)
        self._row(f,"Course Code:","code",0,e.course_code if e else"")
        self._row(f,"Section ID (A/B/G1/H2):","sid",1,e.section_id if e else"A")
        self._row(f,"Teacher ID:","tid",2,e.teacher_id if e else"")
        L(f,"Batch Year:",9).grid(row=3,column=0,sticky="e",padx=(16,8),pady=5)
        self._batch=tk.StringVar(value=str(e.batch_year) if e and e.batch_year else"0")
        CB(f,self._batch,["0 — Unknown","1 — Year 1 (Intake 2025)","2 — Year 2 (Intake 2024)",
                            "3 — Year 3 (Intake 2023)","4 — Year 4 (Intake 2022)"],26
           ).grid(row=3,column=1,sticky="w",pady=5)
        L(f,"Faculty:",9).grid(row=4,column=0,sticky="e",padx=(16,8),pady=5)
        self._fac=tk.StringVar(value=e.faculty if e else"FCSE")
        CB(f,self._fac,["FCSE","FEE","FME","FMCE","FCvE","FBS","SMgS"],12
           ).grid(row=4,column=1,sticky="w",pady=5)
        self._row(f,"Students:","students",5,str(e.num_students) if e else"30")
        L(f,"For Program(s):",9).grid(row=6,column=0,sticky="e",padx=(16,8),pady=5)
        self._prog_var=tk.StringVar(value=e.for_program if e else"")
        CB(f,self._prog_var,["","CS","CE","AI","CY","DS","SE","EE","ME","MTE","CVE","ES","MGS"],16
           ).grid(row=6,column=1,sticky="w",pady=5)
        B(f,"Save",self._save,C["btn_success"],20).grid(row=7,column=0,columnspan=2,pady=12)
    def _save(self):
        code=self._fields["code"].get().strip().upper()
        sid=self._fields["sid"].get().strip()
        if not code or not sid:
            messagebox.showwarning("Required","Course and Section ID required.",parent=self); return
        try: batch=int(self._batch.get().split("—")[0].strip())
        except: batch=0
        try: students=int(self._fields["students"].get().strip() or"30")
        except: students=30
        if self._ex: self.state.sections.pop(self._ex.uid,None)
        s=Section(sid,code,self._fields["tid"].get().strip(),batch,
                   self._fac.get(),students,self._prog_var.get())
        s.program=self._prog_var.get()
        self.state.sections[s.uid]=s
        self.state.save(); self.on_done(); self.destroy()

class _RoomDialog(_BD):
    def __init__(self,p,state,on_done,existing=None):
        self._ex=existing; super().__init__(p,"Edit Room" if existing else"Add Room",state,on_done)
    def _build(self):
        e=self._ex; f=tk.Frame(self,bg=C["bg"]); f.pack(padx=20,pady=16)
        self._row(f,"Room ID:","rid",0,e.room_id if e else"")
        L(f,"Building:",9).grid(row=1,column=0,sticky="e",padx=(16,8),pady=5)
        self._bid=tk.StringVar(value=e.building_id if e else list(BUILDINGS.keys())[0])
        CB(f,self._bid,sorted(BUILDINGS.keys()),16).grid(row=1,column=1,sticky="w",pady=5)
        self._row(f,"Capacity:","cap",2,str(e.capacity) if e else"60")
        self._row(f,"Priority Faculties (comma-sep):","priority",3,
                   ", ".join(e.priority_faculty) if e else"")
        self._row(f,"Notes:","notes",4,e.notes if e else"")
        L(f,"Is Lab:",9).grid(row=5,column=0,sticky="e",padx=(16,8),pady=5)
        self._il=tk.BooleanVar(value=e.is_lab if e else False)
        ttk.Checkbutton(f,variable=self._il).grid(row=5,column=1,sticky="w")
        self._row(f,"Lab Type:","lab_type",6,e.lab_type or"" if e else"")
        L(f,"Is Large Hall (combined):",9).grid(row=7,column=0,sticky="e",padx=(16,8),pady=5)
        self._large=tk.BooleanVar(value=(e.room_id in LARGE_HALLS) if e else False)
        ttk.Checkbutton(f,variable=self._large).grid(row=7,column=1,sticky="w")
        B(f,"Save",self._save,C["btn_success"],20).grid(row=8,column=0,columnspan=2,pady=12)
    def _save(self):
        rid=self._fields["rid"].get().strip(); bid=self._bid.get()
        if not rid or not bid:
            messagebox.showwarning("Required","Room ID and Building required.",parent=self); return
        try: cap=int(self._fields["cap"].get().strip() or"60")
        except: cap=60
        pf=[x.strip() for x in self._fields["priority"].get().split(",") if x.strip()]
        if self._ex and self._ex.room_id!=rid: remove_room(self._ex.room_id)
        add_room(rid,bid,cap,self._il.get(),self._fields["lab_type"].get().strip() or None,
                  pf,self._fields["notes"].get().strip())
        if self._large.get() and rid not in LARGE_HALLS:
            LARGE_HALLS.append(rid)
        elif not self._large.get() and rid in LARGE_HALLS:
            LARGE_HALLS.remove(rid)
        self.on_done(); self.destroy()

# ─── Main App ─────────────────────────────────────────────────────────
class GIKIApp(tk.Tk):
    def __init__(self):
        super().__init__(); self.state=AppState()
        try: self.state.load()
        except: pass
        self.title("GIKI University Timetable Scheduler v2.2")
        self.geometry("1300x840"); self.minsize(1100,700); self.configure(bg=C["bg"])
        try: self.iconbitmap(default="")
        except: pass
        self._active=None; self._nav={}; self._panels={}
        self._build(); self._show("dashboard")
        self.protocol("WM_DELETE_WINDOW",self._close)
    def _build(self):
        sb=tk.Frame(self,bg=C["sidebar"],width=210); sb.pack(side="left",fill="y"); sb.pack_propagate(False)
        lf=tk.Frame(sb,bg=C["sidebar"]); lf.pack(fill="x",pady=(20,8))
        tk.Label(lf,text="GIKI",bg=C["sidebar"],fg=C["white"],font=(FF,18,"bold")).pack()
        tk.Label(lf,text="Timetable Scheduler",bg=C["sidebar"],fg="#8AB4D8",font=(FF,8)).pack()
        tk.Frame(lf,bg="#2E4E8C",height=1).pack(fill="x",padx=16,pady=(8,0))
        nav=[("dashboard","  Dashboard"),("slot_picker","  Slot Picker"),
             ("courses","  Courses"),("teachers","  Teachers"),("sections","  Sections"),
             ("timetable_grid","  Timetable Grid"),("section_view","  Section View & Print"),
             ("electives","  Electives"),("clash","  Clash Checker"),
             ("rooms","  Buildings & Rooms"),("export","  Export")]
        nf=tk.Frame(sb,bg=C["sidebar"]); nf.pack(fill="x",pady=(8,0))
        for key,label in nav:
            b=tk.Button(nf,text=label,anchor="w",bg=C["sidebar"],fg=C["white"],relief="flat",
                         font=(FF,10),cursor="hand2",activebackground=C["sidebar_hover"],
                         activeforeground=C["white"],padx=16,pady=9,bd=0)
            b.config(command=lambda k=key:self._show(k))
            b.bind("<Enter>",lambda e,bt=b:bt.config(bg=C["sidebar_hover"])
                    if bt.cget("bg")!=C["sidebar_active"] else None)
            b.bind("<Leave>",lambda e,bt=b,k2=key:bt.config(
                bg=C["sidebar_active"] if self._active==k2 else C["sidebar"]))
            b.pack(fill="x"); self._nav[key]=b
        tk.Label(sb,text="v2.2",bg=C["sidebar"],fg="#4A6E8C",font=(FF,7)).pack(side="bottom",pady=8)
        cf=tk.Frame(self,bg=C["bg"]); cf.pack(side="left",fill="both",expand=True)
        self.content=tk.Frame(cf,bg=C["bg"]); self.content.pack(fill="both",expand=True)
        self.status_bar=tk.Label(cf,text="  Ready",anchor="w",bg=C["sidebar"],
            fg=C["white"],font=(FF,8),padx=10,pady=4); self.status_bar.pack(fill="x",side="bottom")
    def _show(self,name):
        if self._active and self._active in self._nav: self._nav[self._active].config(bg=C["sidebar"])
        self._active=name
        if name in self._nav: self._nav[name].config(bg=C["sidebar_active"])
        if name not in self._panels:
            cls={"dashboard":DashboardPanel,"slot_picker":SlotPickerPanel,
                 "courses":CoursesPanel,"teachers":TeachersPanel,"sections":SectionsPanel,
                 "timetable_grid":TimetableGridPanel,"section_view":SectionViewPanel,
                 "electives":ElectivesPanel,"clash":ClashPanel,
                 "rooms":RoomsPanel,"export":ExportPanel}.get(name)
            if cls: self._panels[name]=cls(self.content,self.state,self._status)
        for p in self._panels.values(): p.pack_forget()
        self._panels[name].pack(fill="both",expand=True)
        p=self._panels.get(name)
        if p and hasattr(p,"_refresh"):
            try: p._refresh()
            except: pass
        if name=="dashboard" and p: p.refresh_stats()
    def _status(self,msg): self.status_bar.config(text=f"  {msg}")
    def _close(self):
        try: self.state.save()
        except: pass
        self.destroy()

if __name__=="__main__":
    GIKIApp().mainloop()
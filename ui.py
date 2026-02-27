import streamlit as st
import pandas as pd
import json
from data.data_loader import DataLoader
from cpsat import CoursePlanner, PLAN_CONFIGS
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict
from slot_utils import analyse_semester_slots, SPECIAL_SLOTS
from infeasibility_diagnosis import diagnose_infeasibility_rich

st.set_page_config(
    page_title="AI Course Planner",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: bold; color: #1f77b4; text-align: center; margin-bottom: 2rem; }
    .sub-header  { font-size: 1.5rem; font-weight: bold; color: #ffffff; margin-top: 1.5rem; margin-bottom: 1rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 1rem; position: sticky; top: 0; z-index: 999; padding-bottom: 4px; }
    .stTabs [data-baseweb="tab"] { height: 3rem; padding: 0 2rem; font-size: 1rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────────────────
_defaults = {
    'loader': None, 'student': None, 'planner': None,
    'all_plans': None, 'selected_plan_type': None,
    'llm_weights': None, 'plan_explanation': None,
    'data_loaded': False, 'plans_solved': False, 'explanations_done': False,
    'customization_base_plan_type': None,
    'selected_for_review': {}, 'pinned_courses': {},
    'custom_plan': None, 'customization_warnings': [],
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

PLAN_ICONS = {'safe_graduation': '', 'interest_aligned': ''}


# ============================================================================
# SHARED DIAGNOSIS RENDERER
# ============================================================================

def render_diagnosis(diagnosis: dict, current_sem: int = None):
    """
    Renders a structured infeasibility diagnosis dict into rich Streamlit UI.
    Supports both the legacy dict shape and the new MIS-extended shape from
    diagnose_infeasibility_rich().
    """
    if not diagnosis:
        st.error("❌ No feasible plan found and no diagnosis was available.")
        return

    interacting = diagnosis.get("interacting", False)
    mis_list    = diagnosis.get("all_mis", [])

    if interacting:
        st.error(f"🎯 **Root cause (interacting constraints):** {diagnosis['root_cause']}")
    else:
        st.error(f"🎯 **Root cause:** {diagnosis['root_cause']}")

    if current_sem is not None:
        st.caption(
            f"ℹ️ **Note on slot conflicts:** Timetable slot conflicts are only enforced "
            f"for **Semester {current_sem}** (the current semester). "
            f"Future semester slot assignments are not yet known, so conflicts there are not checked."
        )

    if diagnosis.get("pre_solve_violations"):
        with st.expander(
            f"⚠️ Rule violations in your changes "
            f"({len(diagnosis['pre_solve_violations'])} issue(s)) — fix these first",
            expanded=True,
        ):
            st.markdown(
                "These are **direct rule violations** detected before the solver even runs. "
                "Fix them first."
            )
            for v in diagnosis["pre_solve_violations"]:
                st.markdown(f"- {v}")

    mis_summaries = diagnosis.get("mis_summaries", [])

    if mis_summaries:
        if len(mis_summaries) == 1:
            mis = mis_summaries[0]
            constraints = mis["constraints"]
            label = (
                f"🔩 {'Interacting constraints causing infeasibility' if len(constraints) > 1 else 'Constraint that failed'}: "
                f"**{mis['title']}**"
            )
            with st.expander(label, expanded=True):
                if len(constraints) > 1:
                    st.warning(
                        f"⚡ These **{len(constraints)} constraints interact** — removing just one of them "
                        f"would make the plan feasible, but **all must be addressed together**."
                    )
                st.markdown(mis["explanation"])
                if "slot_conflicts" in constraints and current_sem is not None:
                    st.warning(
                        f"Remember: slot conflicts are **only checked for Semester {current_sem}**."
                    )
        else:
            st.markdown(
                f"### ⚡ {len(mis_summaries)} independent infeasibility reasons found"
            )
            st.info(
                "Each reason below is **independent** — the plan would still be infeasible "
                "even if you fixed all other reasons except this one. "
                "**All must be resolved.**"
            )
            for idx, mis in enumerate(mis_summaries, 1):
                constraints = mis["constraints"]
                label = (
                    f"{'🔴' if len(constraints) > 1 else '🔶'} "
                    f"Reason {idx}: **{mis['title']}**"
                    + (f"  *(interacting: {len(constraints)} constraints)*" if len(constraints) > 1 else "")
                )
                with st.expander(label, expanded=(idx == 1)):
                    if len(constraints) > 1:
                        st.warning(
                            f"These {len(constraints)} constraints interact — "
                            "all must be addressed together to resolve this particular reason."
                        )
                    st.markdown(mis["explanation"])

    elif diagnosis.get("broken_constraint_layer") and not mis_summaries:
        with st.expander(
            f"🔩 Constraint that failed: **{diagnosis['broken_constraint_layer']}**",
            expanded=True,
        ):
            st.markdown("**What this constraint does:**")
            st.info(diagnosis["broken_constraint_detail"])
            if "Slot conflict" in diagnosis["broken_constraint_layer"] and current_sem is not None:
                st.warning(
                    f"Slot conflicts are **only checked for Semester {current_sem}**."
                )

    if diagnosis.get("credit_shortfalls"):
        with st.expander("📉 Graduation category credit shortfalls", expanded=True):
            st.markdown(
                "The following graduation categories **cannot be fully satisfied** "
                "with the courses currently in the eligible pool:"
            )
            for cat, needed, available in diagnosis["credit_shortfalls"]:
                deficit = needed - available
                st.markdown(
                    f"- **{cat}**: need **{needed}** more credits, "
                    f"only **{available}** available — shortfall of **{deficit}** credits"
                )

    if diagnosis.get("slot_conflicts"):
        with st.expander(
            f"🕐 Slot conflicts in Semester {current_sem} (current semester)",
            expanded=True,
        ):
            st.markdown(
                f"The following courses are pinned to **Semester {current_sem}** "
                f"but share timetable slots."
            )
            for msg in diagnosis["slot_conflicts"]:
                st.markdown(f"- {msg}")

    if diagnosis.get("theory_lab_issues"):
        with st.expander("🔬 Theory-lab pairing violations", expanded=True):
            st.markdown(
                "Theory courses and their lab components **must always be in the same semester**."
            )
            loader = st.session_state.loader
            for theory_cc, lab_cc, theory_sem, lab_sem in diagnosis["theory_lab_issues"]:
                ci_t   = loader.get_course_by_code(theory_cc) if loader else None
                ci_l   = loader.get_course_by_code(lab_cc) if loader else None
                t_name = ci_t['course_name'] if ci_t else theory_cc
                l_name = ci_l['course_name'] if ci_l else lab_cc
                if theory_sem is None and lab_sem is None:
                    # Case D/E: one half was removed entirely
                    st.markdown(
                        f"- **{t_name}** ({theory_cc}) and **{l_name}** ({lab_cc}) "
                        f"are a theory-lab pair — one was removed but the other was not. "
                        f"*(Remove both or keep both)*"
                    )
                else:
                    st.markdown(
                        f"- **{t_name}** ({theory_cc}) → Semester {theory_sem}  \n"
                        f"  **{l_name}** ({lab_cc}) → Semester {lab_sem}  \n"
                        f"  *(must be in the same semester)*"
                    )

    if diagnosis.get("year_level_issues"):
        with st.expander("📅 Year-level unlock violations", expanded=True):
            for cc, name, year_req, pinned_sem in diagnosis["year_level_issues"]:
                earliest = (year_req - 1) * 2 + 1
                st.markdown(
                    f"- **{name}** ({cc}): Year {year_req} course "
                    f"pinned to Semester {pinned_sem} (Year {(pinned_sem+1)//2}). "
                    f"Earliest valid semester: **Semester {earliest}**."
                )

    if diagnosis.get("mandatory_issues"):
        with st.expander("🔒 Mandatory course scheduling issues", expanded=True):
            for msg in diagnosis["mandatory_issues"]:
                st.markdown(f"- {msg}")

    st.info(f"💡 **How to fix:** {diagnosis['suggestion']}")

    layer_results = diagnosis.get("layer_results", [])
    if layer_results:
        with st.expander("🔍 Constraint layer test results (all layers)", expanded=True):
            st.markdown("Each layer below was tested independently with all previous constraints included (cumulative):")
            for name, ok in layer_results:
                icon = "✅" if ok else "❌"
                st.markdown(f"{icon} **{name}**")
            if all(ok for _, ok in layer_results):
                st.warning(
                    "⚠️ All individual layers are feasible — the infeasibility comes from "
                    "**two or more constraints interacting together**. "
                    "This typically means: slot conflicts + credit bounds, or mandatory courses + theory-lab pairing + available slots."
                )
    
    failing_pairs = diagnosis.get("failing_pairs", [])
    failing_triplets = diagnosis.get("failing_triplets", [])

    if failing_pairs or failing_triplets:
        with st.expander("⚡ Interacting constraint pairs/triplets (MIS)", expanded=True):
            if failing_pairs:
                st.markdown("**Failing pairs** — these two constraints together are infeasible:")
                for p in failing_pairs:
                    st.error(f"❌ **{p[0]}** × **{p[1]}**")
            if failing_triplets:
                st.markdown("**Failing triplets** — no pair fails alone, but these three together do:")
                for t in failing_triplets:
                    st.error(f"❌ **{t[0]}** × **{t[1]}** × **{t[2]}**")
        


# ── Help dialog ───────────────────────────────────────────────────────────────
@st.dialog("🎓 How to Use AI Course Planner", width="large")
def show_help_dialog():
    st.markdown("""
    ## Welcome to AI Course Planner!

    This app generates **two distinct course plans** for your remaining semesters:

    | Plan | Focus | Uses your preferences? |
    |------|-------|----------------------|
    | Safe Graduation | Graduate on time, low risk, manageable load | ❌ Fixed: low workload, easy difficulty |
    | Interest-Aligned | Courses you love, at your pace | ✅ Uses your workload & difficulty settings |

    ---

    ### Steps
    1. **Load Course Data** — sidebar
    2. **Load Student** — sidebar
    3. **Student Profile tab** — set interests, workload & difficulty *(Interest-Aligned only)*
    4. **Generate Plans tab** — click Generate
    5. **View Results tab** — compare, see difficulty banner, get AI explanation
    6. **Customize Plan tab** — fine-tune and regenerate
    """)
    if st.button("Got it 🚀", use_container_width=True, type="primary"):
        st.rerun()

if "help_shown" not in st.session_state:
    st.session_state.help_shown = False
    show_help_dialog()

_, col_help = st.columns([11, 1])
with col_help:
    if st.button("❓", help="How to use this app"):
        show_help_dialog()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎓 AI Course Planner")
    st.markdown("---")
    st.markdown("#### 📚 Data Management")

    if not st.session_state.data_loaded:
        if st.button("🔄 Load Course Data", use_container_width=True):
            with st.spinner("Loading course catalog..."):
                try:
                    loader = DataLoader()
                    loader.load_course_data()
                    st.session_state.loader = loader
                    st.session_state.data_loaded = True
                    st.success("✅ Course data loaded!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    else:
        st.success("✅ Course data loaded")
        st.markdown("#### 👤 Select Student")

        available_students = ["21BCE0001", "21BCE0055","21BCE0089","21BCE0134"]
        student_id = st.selectbox("Select Student ID", options=available_students, index=3)

        if st.button("🔍 Load Student", use_container_width=True):
            with st.spinner(f"Loading {student_id}..."):
                try:
                    student = st.session_state.loader.load_student(student_id)
                    st.session_state.student  = student
                    st.session_state.planner  = CoursePlanner(st.session_state.loader, 'gpt-4.1-mini')
                    st.session_state.all_plans = None
                    st.session_state.selected_plan_type = None
                    st.session_state.llm_weights = None
                    st.session_state.plan_explanation = None
                    st.session_state.customization_base_plan_type = None
                    st.session_state.selected_for_review = {}
                    st.session_state.pinned_courses = {}
                    st.session_state.custom_plan = None
                    st.session_state.customization_warnings = []
                    st.session_state.plans_solved = False
                    st.session_state.explanations_done = False
                    st.success(f"✅ Loaded {student.name}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

        if st.button("🗑️ Clear All Data", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.markdown("---")
    if st.session_state.loader and st.session_state.student:
        st.markdown("#### 📊 Quick Stats")
        student = st.session_state.student
        loader  = st.session_state.loader
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Courses", len(loader.courses_data))
            st.metric("Completed", len(student.completed_courses))
        with col2:
            st.metric("CGPA", f"{student.cgpa:.2f}")
            st.metric("Failed", len(student.failed_courses))
        total_earned = sum(loader.get_credits(c) for c in student.completed_courses)
        st.metric("Credits Earned", f"{total_earned}/160")


# ── Guard ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-header">AI-Powered Course Planner</p>', unsafe_allow_html=True)

if not st.session_state.data_loaded:
    st.info("👈 Click **Load Course Data** in the sidebar to begin.")
    st.stop()

if not st.session_state.student:
    st.info("👈 Select a Student ID and click **Load Student**.")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Student Profile", "Course Catalog", "System Constraints",
    "Generate Plans", "View Results", "Customize Plan"
])


# ============================================================================
# TAB 1 — STUDENT PROFILE
# ============================================================================
with tab1:
    student = st.session_state.student
    loader  = st.session_state.loader

    st.markdown('<p class="sub-header">Student Information</p>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Student ID", student.student_id)
    col2.metric("Name", student.name)
    col3.metric("Current Semester", f"Semester {student.current_semester}")
    col4.metric("CGPA", f"{student.cgpa:.2f}")

    st.markdown("---")
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<p class="sub-header">Academic Progress</p>', unsafe_allow_html=True)
        earned_by_category = defaultdict(int)
        for cc in student.completed_courses:
            course = loader.get_course_by_code(cc)
            if course:
                earned_by_category[course['course_type']] += loader.get_credits(cc)

        for category, requirements in loader.credit_requirements.items():
            required = requirements.get('required', 0)
            if required > 0:
                earned   = earned_by_category.get(category, 0)
                progress = min(100, (earned / required) * 100)
                st.write(f"**{category}**")
                st.progress(progress / 100, text=f"{earned:.0f} / {required:.0f} credits ({progress:.0f}%)")
                st.write("")

    with col2:
        st.markdown('<p class="sub-header">Credit Summary</p>', unsafe_allow_html=True)
        total_earned = sum(loader.get_credits(c) for c in student.completed_courses)
        fig = go.Figure(data=[go.Pie(
            labels=['Earned', 'Remaining'],
            values=[total_earned, 160 - total_earned],
            hole=.4, marker_colors=['#1f77b4', '#e0e0e0']
        )])
        fig.update_layout(showlegend=True, height=300, margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
        st.metric("Total Credits", f"{total_earned} / 160")

    st.markdown("---")
    st.markdown('<p class="sub-header">Semester-wise Performance</p>', unsafe_allow_html=True)
    semester_data = defaultdict(list)
    for record in student.course_records:
        semester_data[record.semester_taken].append(record)

    for sem in sorted(semester_data.keys()):
        with st.expander(f"📖 Semester {sem}", expanded=(sem == student.current_semester - 1)):
            sem_courses = semester_data[sem]
            c1, c2, c3 = st.columns(3)
            c1.metric("Courses", len(sem_courses))
            c2.metric("Credits", sum(r.credits for r in sem_courses))
            c3.metric("Failed", sum(1 for r in sem_courses if r.is_failed))
            df_sem = pd.DataFrame([{
                'Code': r.course_code, 'Name': r.course_name,
                'Credits': r.credits, 'Grade': r.grade,
                'Status': '❌ Failed' if r.is_failed else '✅ Passed'
            } for r in sem_courses])
            st.dataframe(df_sem, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown('<p class="sub-header">Preferences</p>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Interest Areas**")
        if hasattr(student, 'interest_areas') and isinstance(student.interest_areas, list):
            interests_text = st.text_area(
                "Edit your interests (one per line)",
                value="\n".join(student.interest_areas), height=150
            )
            if st.button("💾 Update Interests"):
                student.interest_areas = [i.strip() for i in interests_text.split('\n') if i.strip()]
                st.success("✅ Interests updated!")
        else:
            st.info("No interest areas defined")

    with col2:
        st.markdown("**Workload Preference**")
        st.caption("⚠️ Applies to **Interest-Aligned Plan** only. Safe Graduation always uses low workload.")
        workload_options = {
            'low':    '🟢 Low (16–18 credits/sem)',
            'medium': '🟡 Medium (19–22 credits/sem)',
            'high':   '🔴 High (23–25 credits/sem)',
        }
        current_wl = getattr(student, 'workload_preference', 'medium') or 'medium'
        selected_workload = st.selectbox(
            "Workload", options=list(workload_options.keys()),
            format_func=lambda x: workload_options[x],
            index=list(workload_options.keys()).index(current_wl)
        )
        if st.button("💾 Update Workload"):
            student.workload_preference = selected_workload
            st.success("✅ Workload preference updated!")

        st.markdown("**Course Difficulty Preference**")
        st.caption("⚠️ Applies to **Interest-Aligned Plan** only. Safe Graduation always targets easy–moderate difficulty.")
        difficulty_options = {
            'low':    '🟢 Easy (0–40 difficulty score)',
            'medium': '🟡 Moderate (31–64 difficulty score)',
            'high':   '🔴 Challenging (65–100 difficulty score)',
        }
        current_diff = getattr(student, 'difficulty_preference', 'medium') or 'medium'
        selected_difficulty = st.selectbox(
            "Difficulty", options=list(difficulty_options.keys()),
            format_func=lambda x: difficulty_options[x],
            index=list(difficulty_options.keys()).index(current_diff)
        )
        if st.button("💾 Update Difficulty"):
            student.difficulty_preference = selected_difficulty
            st.success("✅ Difficulty preference updated!")


# ============================================================================
# TAB 2 — COURSE CATALOG
# ============================================================================
with tab2:
    st.markdown('<p class="sub-header">Course Catalog</p>', unsafe_allow_html=True)
    loader = st.session_state.loader

    col1, col2, col3 = st.columns(3)
    mandatory_count = sum(1 for c in loader.courses_data if c.get('is_mandatory', False))
    col1.metric("Total Courses", len(loader.courses_data))
    col2.metric("Mandatory", mandatory_count)
    col3.metric("Electives", len(loader.courses_data) - mandatory_count)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_year = st.selectbox("Filter by Year", options=['All'] + [f"Year {i}" for i in range(1, 5)])
    with col2:
        course_types = ['All'] + sorted(set(c['course_type'] for c in loader.courses_data))
        filter_type = st.selectbox("Filter by Type", options=course_types)
    with col3:
        filter_mandatory = st.selectbox("Filter by Status", options=['All', 'Mandatory', 'Elective'])

    filtered = []
    for course in loader.courses_data:
        if filter_year != 'All' and course.get('year_offered', 1) != int(filter_year.split()[1]):
            continue
        if filter_type != 'All' and course['course_type'] != filter_type:
            continue
        if filter_mandatory == 'Mandatory' and not course.get('is_mandatory', False):
            continue
        if filter_mandatory == 'Elective' and course.get('is_mandatory', False):
            continue
        filtered.append(course)

    st.write(f"**Showing {len(filtered)} courses**")
    by_year = defaultdict(list)
    for c in filtered:
        by_year[c.get('year_offered', 1)].append(c)

    for year in sorted(by_year.keys()):
        with st.expander(f"📖 Year {year} — {len(by_year[year])} courses", expanded=(year == 1)):
            df = pd.DataFrame([{
                'Code': c['course_code'], 'Name': c['course_name'],
                'Credits': c['credits'], 'Type': c['course_type'],
                'Mandatory': '✅' if c.get('is_mandatory') else '❌',
                'Difficulty': f"{c.get('difficulty', 50)}%",
                'Pass Rate': f"{c.get('pass_rate', 0)*100:.0f}%",
                'Occupied Slots': ', '.join(c.get('slots', [])) or '—',
            } for c in by_year[year]])
            st.dataframe(df, use_container_width=True, hide_index=True, height=400)


# ============================================================================
# TAB 3 — SYSTEM CONSTRAINTS
# ============================================================================
with tab3:

    st.warning("""
⚠️ **PROTOTYPE NOTICE — Please Read Before Interpreting Results**

This is a **research prototype** built to demonstrate AI-powered course planning using constraint satisfaction.
All data used in this system is **dummy/synthetic data** created for demonstration purposes only.
""")

    with st.expander("📋 Full List of Prototype Assumptions", expanded=True):
        st.markdown("""
### Data Assumptions
| Item | Status | Details |
|------|--------|---------|
| Student records | 🟡 Dummy | 5 synthetic students with fabricated grades, CGPA, and course history |
| Course catalog | 🟡 Dummy | Courses modelled on a B.Tech CSE structure but with synthetic attributes |
| Credits per course | 🟡 Approximate | Assigned manually |
| Difficulty scores | 🟡 Synthetic | 0–100 scores assigned heuristically |
| Pass rates | 🟡 Synthetic | Fabricated values |
| Prerequisites | 🟡 Approximate | Modelled on common CSE curriculum logic |
| Interest areas | 🟡 Dummy | Hardcoded example strings |
| Workload preference | 🟡 Dummy | Default values set per student |

---

### Slot System Assumptions
A course occupies ALL of its listed slots every week — slots are not alternatives.
Two courses conflict if they share **any** slot. Slot conflicts are **only enforced for the current semester** because future semester timetables are not yet assigned.

---

### Constraint Assumptions
| Constraint | Assumption Made |
|------------|----------------|
| Credit bounds | 16–25 credits per semester |
| Slot conflicts | Enforced for **current semester only** (future slots unknown) |
| Theory-lab pairing | Theory and lab must be in the exact same semester |
| Project placement | Project-I → Semester 7, Project-II/Internship → Semester 8 |
| Year unlock | Course available from Year N → earliest Semester (2N-1) |
| Graduation credits | Fixed at 160 total |
| Max courses/semester | Capped at 12 |
| Failed course retake | Forced into the plan exactly once |
        """)

    st.markdown("---")
    st.markdown("### 🔒 Hard Constraints (Always Enforced)")
    hard = [
        ("Credit Bounds", "16 ≤ credits_per_semester ≤ 25"),
        ("Course Uniqueness", "Each course taken at most once"),
        ("Prerequisites", "Must complete prerequisites before a course"),
        ("Slot Conflicts", "No two courses sharing any timetable slot in the same semester — **current semester only**"),
        ("Theory-Lab Pairing", "Theory and lab taken in same semester"),
        ("Category Requirements", "Min credits per graduation category"),
        ("Project Constraints", "Project-I → Sem 7, Project-II → Sem 8"),
        ("Failed Course Retake", "Failed courses retaken exactly once"),
        ("Year Level Unlock", "Courses only available from their designated year"),
        ("Graduation Credits", "Total credits ≥ 160"),
        ("Max Courses/Sem", "At most 12 courses per semester"),
        ("Mandatory Completion", "All mandatory courses must be scheduled"),
    ]
    for name, formula in hard:
        st.markdown(f"**{name}** — `{formula}`")

    st.markdown("---")
    st.markdown("### Two Plans")
    col1, col2 = st.columns(2)
    with col1:
        st.success("""
**Safe Graduation Plan**
- Mandatory & failed → highest priority
- Workload → always **low** (hardcoded)
- Difficulty → always **easy** (hardcoded)
- Student preferences **ignored**
        """)
    with col2:
        st.info("""
**Interest-Aligned Plan**
- Mandatory & failed → equally high priority
- Workload → **your preference**
- Difficulty → **your preference**
- Interest → dominant weight
        """)

    st.markdown("---")
    st.markdown("### Objective Function")
    st.code("""
Maximize:
    w_mandatory × mandatory_score
  + w_unlock    × unlock_score
  + w_interest  × interest_score
  + w_failed    × failed_course_urgency
  + w_diversity × diversity_reward
  - w_workload  × workload_penalty
  - w_lateness  × lateness_penalty
  - w_difficulty× difficulty_penalty
  - w_freshness × freshness_penalty
  - w_credit_limit_exceed × credit_exceed
    """, language='python')


# ============================================================================
# TAB 4 — GENERATE PLANS
# ============================================================================
with tab4:
    student = st.session_state.student
    loader  = st.session_state.loader
    planner = st.session_state.planner

    st.markdown("### Your Current Settings")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Interest Areas:**")
        if hasattr(student, 'interest_areas') and isinstance(student.interest_areas, list):
            for interest in student.interest_areas:
                st.write(f"• {interest}")
        else:
            st.info("No interest areas defined")
    with col2:
        st.markdown("**Preferences** *(Interest-Aligned plan only)*")
        st.write(f"• Workload: **{getattr(student, 'workload_preference', 'medium') or 'medium'}**")
        st.write(f"• Difficulty: **{getattr(student, 'difficulty_preference', 'medium') or 'medium'}**")
        st.caption("Safe Graduation ignores these — always low workload + easy difficulty.")

    st.markdown("---")
    st.markdown("""
    ### Generate Plans

    Click below to generate **2 plans**:

    - **Safe Graduation** — fixed low workload, easy difficulty, prioritise on-time graduation
    - **Interest-Aligned** — your interests dominant, uses your workload & difficulty preferences
    """)

    if st.button("🚀 Generate My Plans", type="primary", use_container_width=True):
        st.session_state.plans_solved = False
        st.session_state.all_plans = None
        st.session_state.selected_plan_type = None

        progress_bar = st.progress(0, text="Starting...")
        planner.set_ui_logger(lambda msg: print(msg))

        try:
            progress_bar.progress(5, text="Reviewing your course history...")
            remaining_semesters = list(range(student.current_semester, 9))
            eligible_courses, failed_courses = planner.get_eligible_and_failed_courses(student)
            current_sem = student.current_semester

            progress_bar.progress(20, text="AI matching courses to your interests...")
            llm_weights = planner.get_course_interest_weights_from_llm(student, eligible_courses)
            if llm_weights:
                st.session_state.llm_weights = llm_weights

            all_plans = {}
            failed_diagnoses = {}
            total_plans = len(PLAN_CONFIGS)

            for idx, (plan_type, config) in enumerate(PLAN_CONFIGS.items(), 1):
                pct_start = 20 + (idx - 1) * (70 // total_plans)
                pct_end   = 20 + idx * (70 // total_plans)
                icon      = PLAN_ICONS.get(plan_type, '')
                progress_bar.progress(pct_start, text=f"Building {icon} {config['name']} ({idx}/{total_plans})...")

                plan, diagnosis = planner.generate_single_plan(
                    student, eligible_courses, remaining_semesters,
                    failed_courses, llm_weights,
                    weights=config['weights'],
                    plan_type=plan_type,
                )

                if plan and any(plan.values()):
                    all_plans[plan_type] = {'config': config, 'plan': plan, 'explanation': None}
                    progress_bar.progress(pct_end, text=f"{icon} {config['name']} — done ✅")
                else:
                    if diagnosis is None:
                        with st.spinner(f"Diagnosing why {config['name']} failed..."):
                            diagnosis = diagnose_infeasibility_rich(
                                planner, student, eligible_courses, failed_courses,
                                remaining_semesters,
                                avoided_list=[], pinned_courses={},
                                is_customization=False,
                            )
                    failed_diagnoses[plan_type] = (config, diagnosis)
                    progress_bar.progress(pct_end, text=f"{icon} {config['name']} — ❌ no solution")

            progress_bar.progress(100, text="Done!")
            st.session_state.all_plans = all_plans
            st.session_state.plans_solved = True

            if all_plans:
                st.success(f"✅ {len(all_plans)} plan(s) generated successfully. Go to **View Results** to explore them.")
            else:
                st.warning("⚠️ No feasible plans could be generated.")

            for plan_type, (config, diagnosis) in failed_diagnoses.items():
                icon = PLAN_ICONS.get(plan_type, '')
                st.markdown("---")
                st.markdown(f"### ❌ {icon} {config['name']} — Generation Failed")
                st.markdown(
                    f"The solver could not find a valid plan for **{config['name']}**. "
                    f"This is typically a data or constraint conflict, not a user error."
                )
                render_diagnosis(diagnosis, current_sem=current_sem)

        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Error: {e}")
            with st.expander("Details"):
                st.exception(e)


# ============================================================================
# TAB 5 — VIEW RESULTS
# ============================================================================
with tab5:
    if not st.session_state.all_plans:
        st.info("Generate plans first — go to the **Generate Plans** tab.")
        st.stop()

    all_plans = st.session_state.all_plans
    student   = st.session_state.student
    loader    = st.session_state.loader
    planner   = st.session_state.planner

    st.markdown("### Select a Plan to Explore")
    plan_types = list(all_plans.keys())
    cols = st.columns(len(plan_types))

    for col, pt in zip(cols, plan_types):
        with col:
            pd_data   = all_plans[pt]
            config    = pd_data['config']
            plan      = pd_data['plan']
            total_c   = sum(len(v) for v in plan.values())
            total_cr  = sum(sum(loader.get_credits(c) for c in v) for v in plan.values())
            icon      = PLAN_ICONS.get(pt, '')
            uses_pref = config.get('use_student_preferences', True)

            st.markdown(f"### {icon} {config['name']}")
            st.write(config['description'])

            if uses_pref:
                wl   = getattr(student, 'workload_preference', 'medium') or 'medium'
                diff = getattr(student, 'difficulty_preference', 'medium') or 'medium'
                st.caption(f"Using your preferences → workload: {wl}, difficulty: {diff}")
            else:
                hw = config.get('hardcoded_workload', 'medium')
                hd = config.get('hardcoded_difficulty', 'low')
                st.caption(f"Fixed → workload: {hw}, difficulty: {hd} (ignores your preferences)")

            c1, c2 = st.columns(2)
            c1.metric("Courses", total_c)
            c2.metric("Credits", total_cr)

            if st.button(f"Select {icon}", key=f"sel_{pt}", use_container_width=True):
                st.session_state.selected_plan_type = pt
                st.session_state.customization_base_plan_type = pt
                st.session_state.selected_for_review = {}
                st.session_state.pinned_courses = {}
                st.session_state.custom_plan = None
                st.session_state.customization_warnings = []
                st.rerun()

    if not st.session_state.selected_plan_type:
        st.markdown("---")
        st.markdown("### 📊 Plan Comparison")
        comp = []
        for pt, pd_data in all_plans.items():
            config = pd_data['config']
            plan   = pd_data['plan']
            tc  = sum(len(v) for v in plan.values())
            tcr = sum(sum(loader.get_credits(c) for c in v) for v in plan.values())
            man = sum(1 for v in plan.values() for c in v if loader.get_course_by_code(c).get('is_mandatory', False))
            comp.append({
                'Plan': f"{PLAN_ICONS.get(pt,'')} {config['name']}",
                'Courses': tc, 'Credits': tcr,
                'Mandatory': man, 'Electives': tc - man
            })
        st.dataframe(pd.DataFrame(comp), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 📅 Semester Comparison")
        all_sems = sorted(set(s for pd_data in all_plans.values() for s in pd_data['plan']))
        for sem in all_sems:
            st.markdown(f"#### Semester {sem}")
            sem_cols = st.columns(len(plan_types))
            for col, pt in zip(sem_cols, plan_types):
                with col:
                    courses = all_plans[pt]['plan'].get(sem, [])
                    icon    = PLAN_ICONS.get(pt, '')
                    st.markdown(f"**{icon} {all_plans[pt]['config']['name']}**")
                    if courses:
                        cr = sum(loader.get_credits(c) for c in courses)
                        st.write(f"{len(courses)} courses, {cr} credits")
                        for cc in courses:
                            ci = loader.get_course_by_code(cc)
                            st.write(f"• {ci['course_name'] if ci else cc} ({cc})")
                    else:
                        st.write("No courses")
            st.markdown("---")
        st.stop()

    selected_pt   = st.session_state.selected_plan_type
    selected_data = all_plans[selected_pt]
    config        = selected_data['config']
    plan          = selected_data['plan']
    explanation   = selected_data.get('explanation')
    icon          = PLAN_ICONS.get(selected_pt, '')

    st.markdown("---")
    st.markdown(f"## {icon} {config['name']}")

    diff_ranges = {'low': (0, 40), 'medium': (31, 64), 'high': (65, 100)}
    uses_pref   = config.get('use_student_preferences', True)
    if uses_pref:
        active_diff = getattr(student, 'difficulty_preference', 'medium') or 'medium'
        pref_note   = f"your preference: **{active_diff}**"
    else:
        active_diff = config.get('hardcoded_difficulty', 'low')
        pref_note   = f"hardcoded for safe graduation: **{active_diff}** *(ignores your preference)*"

    lo, hi = diff_ranges[active_diff]
    all_plan_courses = [c for v in plan.values() for c in v]
    if all_plan_courses:
        avg_diff  = sum(loader.get_course_by_code(c).get('difficulty', 50) for c in all_plan_courses) / len(all_plan_courses)
        on_target = lo <= avg_diff <= hi
        status    = "✅ within target range" if on_target else "⚠️ outside target range — mandatory courses shift the average"
        # st.info(
        #     f"**Difficulty target ({pref_note}): {active_diff.capitalize()} ({lo}–{hi})** "
        #     f"&nbsp;·&nbsp; Plan average: **{avg_diff:.0f}** &nbsp; {status}"
        # )

    st.markdown("#### Semester-by-Semester Plan")
    for sem in sorted(plan.keys()):
        if not plan[sem]:
            continue
        courses     = plan[sem]
        sem_credits = sum(loader.get_credits(c) for c in courses)
        with st.expander(f"Semester {sem} — {len(courses)} courses, {sem_credits} credits", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Courses", len(courses))
            c2.metric("Credits", sem_credits)
            c3.metric("Mandatory", sum(1 for c in courses if loader.get_course_by_code(c).get('is_mandatory', False)))
            rows = []
            for cc in courses:
                ci = loader.get_course_by_code(cc)
                if ci:
                    rows.append({
                        'Code': cc, 'Name': ci['course_name'],
                        'Credits': loader.get_credits(cc), 'Type': ci['course_type'],
                        'Mandatory': '✅' if ci.get('is_mandatory') else '❌',
                        'Difficulty': f"{ci.get('difficulty', 50)}%",
                        'Pass Rate': f"{ci.get('pass_rate', 0)*100:.0f}%",
                        'Occupied Slots': ', '.join(ci.get('slots', [])) or '—',
                    })
            df_plan = pd.DataFrame(rows)
            st.dataframe(df_plan, use_container_width=True, hide_index=True)

            if sem == student.current_semester:
                from slot_utils import analyse_semester_slots, SPECIAL_SLOTS

                slot_options = {
                    cc: (loader.get_course_by_code(cc) or {}).get('slots', [])
                    for cc in courses
                }
                result = analyse_semester_slots(courses, slot_options)

                st.markdown("---")
                st.markdown("##### 🕐 Slot Registration Guide")
                st.caption(
                    "For each course, **safe slots** are ones you can register in without "
                    "causing a timetable clash with any other recommended course this semester. "
                    "**Unsafe slots** would make it impossible to assign the rest conflict-free. "
                    "Register tight courses first."
                )

                if result["feasible"]:
                    st.success(
                        "✅ A conflict-free slot assignment exists for all courses this semester."
                    )
                else:
                    st.error(
                        "❌ **No valid slot assignment exists.** Some courses share all their "
                        "possible slots — you may need to swap one course out."
                    )

                if result["tight_courses"]:
                    tight_msgs = []
                    for cc in result["tight_courses"]:
                        ci = loader.get_course_by_code(cc)
                        safe_r = [s for s in result["safe_slots"].get(cc, []) if s not in SPECIAL_SLOTS]
                        tight_msgs.append(
                            f"**{ci['course_name'] if ci else cc}** — only safe slot: "
                            f"`{safe_r[0] if safe_r else 'none'}`"
                        )
                    st.warning(
                        "⚠️ **Register these courses first** (very limited slot choices):\n\n" +
                        "\n".join(f"- {m}" for m in tight_msgs)
                    )

                with st.expander("🔍 Safe & unsafe slots per course", expanded=True):
                    slot_rows = []
                    for cc in courses:
                        ci = loader.get_course_by_code(cc)
                        name = ci['course_name'] if ci else cc
                        all_opts   = slot_options.get(cc, [])
                        safe_r     = [s for s in result["safe_slots"].get(cc, []) if s not in SPECIAL_SLOTS]
                        unsafe_r   = result["unsafe_slots"].get(cc, [])
                        special    = [s for s in all_opts if s in SPECIAL_SLOTS]
                        is_tight   = cc in result["tight_courses"]

                        example_slot = (result["example_assignment"] or {}).get(cc, "—")

                        slot_rows.append({
                            "Course":        f"{'⚠️ ' if is_tight else ''}{name} ({cc})",
                            "Example Slot":  example_slot if example_slot else "—",
                            "✅ Safe Slots":  ", ".join(safe_r) if safe_r else ("special only" if special else "none"),
                            "🚫 Avoid":       ", ".join(unsafe_r) if unsafe_r else "—",
                            "Special Slots": ", ".join(special) if special else "—",
                        })

                    st.dataframe(pd.DataFrame(slot_rows), use_container_width=True, hide_index=True)
                    st.caption(
                        "**Example Slot** = one valid assignment (not the only option). "
                        "Any combination from Safe Slots column works as long as no two courses share the same slot."
                    )

            else:
                st.caption(
                    "ℹ️ Slot assignments for future semesters are not shown — "
                    "timetables are not yet finalized for upcoming terms."
                )

    st.markdown("---")
    st.markdown("#### 📊 Analysis")
    col1, col2 = st.columns(2)
    with col1:
        sem_cr_data = [
            {'Semester': f"Sem {s}", 'Credits': sum(loader.get_credits(c) for c in plan[s])}
            for s in sorted(plan) if plan[s]
        ]
        fig1 = px.bar(pd.DataFrame(sem_cr_data), x='Semester', y='Credits',
                      title='Credits per Semester', color='Credits', color_continuous_scale='Blues')
        fig1.add_hline(y=16, line_dash="dash", line_color="red", annotation_text="Min (16)")
        fig1.add_hline(y=25, line_dash="dash", line_color="red", annotation_text="Max (25)")
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        type_counts = defaultdict(int)
        for v in plan.values():
            for c in v:
                ci = loader.get_course_by_code(c)
                if ci:
                    type_counts[ci['course_type']] += 1
        fig2 = px.pie(
            pd.DataFrame([{'Type': k, 'Count': v} for k, v in type_counts.items()]),
            values='Count', names='Type', title='Course Type Distribution'
        )
        st.plotly_chart(fig2, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        diff_data = [
            {'Semester': f"Sem {s}",
             'Avg Difficulty': sum(loader.get_course_by_code(c).get('difficulty', 50) for c in plan[s]) / len(plan[s])}
            for s in sorted(plan) if plan[s]
        ]
        fig3 = px.line(pd.DataFrame(diff_data), x='Semester', y='Avg Difficulty',
                       title='Average Difficulty per Semester', markers=True)
        fig3.add_hrect(y0=lo, y1=hi, fillcolor="green", opacity=0.08,
                       annotation_text=f"Target ({active_diff})", annotation_position="top left")
        fig3.update_yaxes(range=[0, 100])
        st.plotly_chart(fig3, use_container_width=True)

    with col2:
        pass_data = [
            {'Semester': f"Sem {s}",
             'Avg Pass Rate': sum(loader.get_course_by_code(c).get('pass_rate', 0.8)*100 for c in plan[s]) / len(plan[s])}
            for s in sorted(plan) if plan[s]
        ]
        fig4 = px.line(pd.DataFrame(pass_data), x='Semester', y='Avg Pass Rate',
                       title='Average Pass Rate per Semester', markers=True,
                       color_discrete_sequence=['green'])
        fig4.update_yaxes(range=[0, 100])
        st.plotly_chart(fig4, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🤖 AI Interest Analysis")
    llm_weights = st.session_state.llm_weights

    if llm_weights and llm_weights.courses:
        planned_codes = {c for v in plan.values() for c in v}
        weight_data = []
        for cw in llm_weights.courses:
            ci = loader.get_course_by_code(cw.code)
            if ci:
                weight_data.append({
                    'Course Code': cw.code, 'Course Name': cw.name,
                    'Interest Weight': cw.weight, 'Type': ci.get('course_type', 'Unknown'),
                    'In Plan': '✅' if cw.code in planned_codes else '❌',
                    'AI Reasoning': cw.reason
                })
        weight_data.sort(key=lambda x: x['Interest Weight'], reverse=True)
        df_w = pd.DataFrame(weight_data)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("High Interest (≥0.8)", len([w for w in weight_data if w['Interest Weight'] >= 0.8]))
        c2.metric("Medium (0.5–0.8)",     len([w for w in weight_data if 0.5 <= w['Interest Weight'] < 0.8]))
        c3.metric("Low (<0.5)",           len([w for w in weight_data if w['Interest Weight'] < 0.5]))
        c4.metric("In Plan",              len([w for w in weight_data if w['In Plan'] == '✅']))

        wt1, wt2, wt3 = st.tabs(["All Courses", "High Interest", "In Your Plan"])
        with wt1:
            st.dataframe(df_w.style.format({'Interest Weight': '{:.2f}'}),
                         use_container_width=True, hide_index=True, height=400)
        with wt2:
            for _, row in df_w[df_w['Interest Weight'] >= 0.8].iterrows():
                with st.expander(f"⭐ {row['Course Code']}: {row['Course Name']} ({row['Interest Weight']:.2f})"):
                    c1, c2 = st.columns([1, 3])
                    c1.metric("Weight", f"{row['Interest Weight']:.2f}")
                    c1.write(f"**In Plan:** {row['In Plan']}")
                    c2.info(row['AI Reasoning'])
        with wt3:
            plan_df = df_w[df_w['In Plan'] == '✅']
            if len(plan_df):
                st.metric("Avg Interest Weight (planned)", f"{plan_df['Interest Weight'].mean():.2f}")
                for sem in sorted(plan.keys()):
                    if not plan[sem]:
                        continue
                    sem_w = plan_df[plan_df['Course Code'].isin(plan[sem])]
                    if len(sem_w):
                        with st.expander(f"Semester {sem}"):
                            st.metric("Avg Weight", f"{sem_w['Interest Weight'].mean():.2f}")
                            for _, row in sem_w.iterrows():
                                badge = "🟢" if row['Interest Weight'] >= 0.8 else ("🟡" if row['Interest Weight'] >= 0.5 else "🔴")
                                st.markdown(f"**{row['Course Code']}: {row['Course Name']}** {badge} {row['Interest Weight']:.2f}")
                                st.caption(row['AI Reasoning'])
                                st.markdown("---")
    else:
        st.info("No LLM weight data. Generate plans to see AI interest analysis.")

    st.markdown("---")
    st.markdown("#### 📖 AI Plan Explanation")
    if explanation:
        with st.expander("📋 Overall Summary", expanded=True):
            st.write(explanation.overall_plan_summary)
            st.markdown("---")
            st.write(explanation.graduation_path)

        for sem_exp in explanation.semesters:
            with st.expander(f"Semester {sem_exp.semester}", expanded=(sem_exp.semester == student.current_semester)):
                c1, c2 = st.columns(2)
                c1.info(sem_exp.overall_strategy)
                c2.info(sem_exp.workload_reasoning)
                st.markdown("---")
                for ce in sem_exp.courses:
                    st.markdown(f"**{ce.code}: {ce.name}**")
                    t1, t2, t3, t4, t5 = st.tabs(["Why Selected","Why This Semester","Prerequisites","Interest","Strategic Value"])
                    t1.write(ce.why_selected)
                    t2.write(ce.why_this_semester)
                    t3.write(ce.prerequisites_context)
                    t4.write(ce.interest_alignment)
                    t5.write(ce.strategic_value)
                    st.markdown("---")

        exp_dict = {
            "plan_type": selected_pt,
            "overall_plan_summary": explanation.overall_plan_summary,
            "graduation_path": explanation.graduation_path,
            "semesters": [{
                "semester": s.semester, "strategy": s.overall_strategy,
                "courses": [{"code": c.code, "name": c.name, "why_selected": c.why_selected} for c in s.courses]
            } for s in explanation.semesters]
        }
        st.download_button("📄 Download Explanation (JSON)",
                           data=json.dumps(exp_dict, indent=2),
                           file_name=f"explanation_{selected_pt}_{student.student_id}.json",
                           mime="application/json")
    else:
        st.info("AI explanation not yet generated.")
        if st.button("Generate AI Explanation"):
            with st.spinner("Generating — ~30 seconds..."):
                try:
                    generated = planner.generate_explanation_for_plan(student, plan, st.session_state.llm_weights)
                    st.session_state.all_plans[selected_pt]['explanation'] = generated
                    st.rerun()
                except Exception as e:
                    st.warning(f"Could not generate: {e}")

    st.markdown("---")
    st.markdown("#### 💾 Export Plan")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("📄 JSON",
                           data=json.dumps({'plan_type': selected_pt, 'student': student.student_id, 'plan': plan}, indent=2),
                           file_name=f"plan_{selected_pt}_{student.student_id}.json",
                           mime="application/json", use_container_width=True)
    with c2:
        rows = []
        for sem, courses in plan.items():
            for cc in courses:
                ci = loader.get_course_by_code(cc)
                if ci:
                    rows.append({'Semester': sem, 'Code': cc, 'Name': ci['course_name'],
                                 'Credits': loader.get_credits(cc), 'Type': ci['course_type'],
                                 'Mandatory': 'Yes' if ci.get('is_mandatory') else 'No'})
        st.download_button("📊 CSV", data=pd.DataFrame(rows).to_csv(index=False),
                           file_name=f"plan_{selected_pt}_{student.student_id}.csv",
                           mime="text/csv", use_container_width=True)


# ============================================================================
# TAB 6 — CUSTOMIZE PLAN
# ============================================================================
with tab6:
    if not st.session_state.all_plans:
        st.info("Generate plans first — go to the **Generate Plans** tab.")
        st.stop()

    all_plans = st.session_state.all_plans
    student   = st.session_state.student
    loader    = st.session_state.loader
    planner   = st.session_state.planner
    current_sem = student.current_semester

    plan_options = {pt: f"{PLAN_ICONS.get(pt,'')} {all_plans[pt]['config']['name']}" for pt in all_plans}

    available_plan_types = list(plan_options.keys())
    if st.session_state.customization_base_plan_type not in available_plan_types:
        st.session_state.customization_base_plan_type = (
            st.session_state.selected_plan_type
            if st.session_state.selected_plan_type in available_plan_types
            else available_plan_types[0]
        )
        st.session_state.selected_for_review   = {}
        st.session_state.pinned_courses         = {}
        st.session_state.custom_plan            = None
        st.session_state.customization_warnings = []

    selected_index = available_plan_types.index(st.session_state.customization_base_plan_type)
    chosen_plan_type = st.selectbox(
        "Customize which plan:",
        options=available_plan_types,
        index=selected_index,
        format_func=lambda pt: plan_options[pt],
    )

    if chosen_plan_type != st.session_state.customization_base_plan_type:
        st.session_state.customization_base_plan_type = chosen_plan_type
        st.session_state.selected_for_review   = {}
        st.session_state.pinned_courses         = {}
        st.session_state.custom_plan            = None
        st.session_state.customization_warnings = []
        st.rerun()

    base_plan_type = st.session_state.customization_base_plan_type

    base_plan         = all_plans[base_plan_type]['plan']
    all_planned_codes = {c for v in base_plan.values() for c in v}
    completed_set     = set(student.completed_courses)
    addable = [
        cc for cc in loader.get_all_course_codes()
        if cc not in all_planned_codes and cc not in completed_set
        and all(p in completed_set for p in loader.get_prerequisites(cc))
    ]

    def compute_warnings(removed_codes, all_planned_codes):
        warnings = []
        for cc in removed_codes:
            deps = [c for c in all_planned_codes if cc in loader.get_prerequisites(c) and c not in removed_codes]
            if deps:
                ci = loader.get_course_by_code(cc)
                dep_names = [loader.get_course_by_code(d)['course_name'] if loader.get_course_by_code(d) else d for d in deps]
                warnings.append(f"**{ci['course_name'] if ci else cc}** is a prerequisite for {', '.join(dep_names)}.")
        return warnings

    def _on_checkbox_change(cc, sem):
        chk_key = f"chk_{sem}_{cc}"
        val = st.session_state.get(chk_key, True)
        if not val:
            st.session_state.selected_for_review[cc] = 'avoid'
        else:
            st.session_state.selected_for_review.pop(cc, None)
        st.session_state.custom_plan = None

    def _on_move_change(cc, sem):
        move_key = f"move_{sem}_{cc}"
        val = st.session_state.get(move_key, "Keep in place")
        if val != "Keep in place":
            target_sem = int(val.split("Semester ")[1])
            st.session_state.selected_for_review[cc] = 'rearrange'
            st.session_state.pinned_courses[cc] = target_sem
        else:
            st.session_state.selected_for_review.pop(cc, None)
            st.session_state.pinned_courses.pop(cc, None)
        st.session_state.custom_plan = None

    for _sem, _courses in base_plan.items():
        for _cc in _courses:
            _ci = loader.get_course_by_code(_cc)
            if not _ci:
                continue
            _is_locked = _ci.get('is_mandatory', False) or _cc in (student.failed_courses or [])

            if not _is_locked:
                _chk_key = f"chk_{_sem}_{_cc}"
                _currently_removed = st.session_state.selected_for_review.get(_cc) == 'avoid'
                st.session_state[_chk_key] = not _currently_removed

            _move_key = f"move_{_sem}_{_cc}"
            if (st.session_state.selected_for_review.get(_cc) == 'rearrange'
                    and _cc in st.session_state.pinned_courses):
                _remaining = [s for s in range(student.current_semester, 9) if s != _sem]
                _desired = f"Move to Semester {st.session_state.pinned_courses[_cc]}"
                st.session_state[_move_key] = _desired if _desired in [f"Move to Semester {s}" for s in _remaining] else "Keep in place"
            else:
                st.session_state[_move_key] = "Keep in place"

    st.markdown("---")
    col_plan, col_summary = st.columns([2, 1])

    with col_plan:
        st.markdown("#### Your Plan — make changes below")
        st.caption("Uncheck to remove a non-mandatory course. Use the dropdown to reschedule any course. Use the expander to add courses.")

        for sem in sorted(base_plan.keys()):
            if not base_plan.get(sem):
                continue
            sem_credits = sum(loader.get_credits(c) for c in base_plan[sem])
            slot_note   = " *(slot conflicts enforced here)*" if sem == current_sem else " *(future — slots not enforced)*"
            st.markdown(f"**Semester {sem}**{slot_note} · {len(base_plan[sem])} courses, {sem_credits} credits")
            st.divider()

            for cc in base_plan[sem]:
                ci = loader.get_course_by_code(cc)
                if not ci:
                    continue

                is_mandatory   = ci.get('is_mandatory', False)
                is_failed      = cc in (student.failed_courses or [])
                removal_locked = is_mandatory or is_failed
                currently_removed = st.session_state.selected_for_review.get(cc) == 'avoid'
                currently_kept    = not currently_removed

                row = st.columns([0.05, 0.5, 0.3, 0.15])

                with row[0]:
                    chk_key = f"chk_{sem}_{cc}"
                    if not removal_locked:
                        st.checkbox(
                            "", key=chk_key,
                            disabled=False,
                            on_change=_on_checkbox_change, args=(cc, sem),
                            label_visibility="collapsed"
                        )
                    else:
                        st.checkbox(
                            "", value=True,
                            disabled=True,
                            key=f"chk_locked_{sem}_{cc}",
                            label_visibility="collapsed"
                        )

                with row[1]:
                    lock_icon = " 🔒" if removal_locked else ""
                    st.markdown(
                        f"**{ci['course_name']}**{lock_icon}  \n"
                        f"<small style='color:#666'>{cc} · {ci.get('course_type','')} · {loader.get_credits(cc)} cr</small>",
                        unsafe_allow_html=True
                    )

                with row[2]:
                    if currently_kept:
                        remaining_sems_list = [s for s in range(student.current_semester, 9) if s != sem]
                        move_options = ["Keep in place"] + [f"Move to Semester {s}" for s in remaining_sems_list]
                        move_key = f"move_{sem}_{cc}"
                        st.selectbox(
                            "", options=move_options,
                            key=move_key,
                            on_change=_on_move_change, args=(cc, sem),
                            label_visibility="collapsed"
                        )

                with row[3]:
                    if is_mandatory:
                        st.caption("Required")
                    elif is_failed:
                        st.caption("Retake")

            already_pinned_to_sem = [
                cc for cc, ps in st.session_state.pinned_courses.items()
                if ps == sem and cc not in all_planned_codes
            ]
            with st.expander(f"+ Add a course to Semester {sem}"):
                if addable:
                    to_add = st.multiselect(
                        "Select courses:",
                        options=sorted(addable),
                        default=[c for c in already_pinned_to_sem if c in sorted(addable)],
                        format_func=lambda c: f"{loader.get_course_by_code(c)['course_name']} ({c})" if loader.get_course_by_code(c) else c,
                        key=f"add_to_{sem}"
                    )
                    for old_cc in list(st.session_state.pinned_courses.keys()):
                        if (st.session_state.pinned_courses[old_cc] == sem
                                and old_cc not in all_planned_codes and old_cc not in to_add):
                            st.session_state.pinned_courses.pop(old_cc, None)
                            st.session_state.custom_plan = None
                    for new_cc in to_add:
                        if new_cc not in st.session_state.pinned_courses:
                            ci_new   = loader.get_course_by_code(new_cc)
                            year_off = ci_new.get('year_offered', 1) if ci_new else 1
                            if (sem + 1) // 2 < year_off:
                                st.warning(f"⚠️ {new_cc} is Year {year_off} — Semester {sem} is Year {(sem+1)//2}.")
                            else:
                                st.session_state.pinned_courses[new_cc] = sem
                                st.session_state.custom_plan = None
                else:
                    st.caption("No additional eligible courses.")
            st.write("")

    with col_summary:
        st.markdown("#### Your Changes")
        st.divider()

        rearranged_list = [c for c, a in st.session_state.selected_for_review.items() if a == 'rearrange']
        avoided_list    = [c for c, a in st.session_state.selected_for_review.items() if a == 'avoid']
        added_list      = {cc: ps for cc, ps in st.session_state.pinned_courses.items() if cc not in all_planned_codes}
        has_changes     = bool(rearranged_list or avoided_list or added_list)

        if not has_changes:
            st.caption("No changes yet.")
        else:
            if avoided_list:
                st.markdown("**Removing:**")
                for cc in avoided_list:
                    ci = loader.get_course_by_code(cc)
                    st.markdown(f"✗ {ci['course_name'] if ci else cc}")
            if rearranged_list:
                st.markdown("**Moving:**")
                for cc in rearranged_list:
                    ci = loader.get_course_by_code(cc)
                    st.markdown(f"↕ {ci['course_name'] if ci else cc} → Sem {st.session_state.pinned_courses.get(cc,'?')}")
            if added_list:
                st.markdown("**Adding:**")
                for cc, ps in added_list.items():
                    ci = loader.get_course_by_code(cc)
                    st.markdown(f"＋ {ci['course_name'] if ci else cc} (Sem {ps})")

        warnings = compute_warnings(set(avoided_list), all_planned_codes)
        if warnings:
            st.divider()
            for w in warnings:
                st.warning(w)

        st.divider()
        regen_clicked = st.button("↺ Regenerate Plan", type="primary",
                                   use_container_width=True, disabled=not has_changes)
        if has_changes:
            if st.button("Reset All Changes", use_container_width=True):
                st.session_state.selected_for_review   = {}
                st.session_state.pinned_courses         = {}
                st.session_state.custom_plan            = None
                st.session_state.customization_warnings = []
                st.rerun()

    # ── Regenerate ────────────────────────────────────────────────────────────
    if regen_clicked:
        with st.spinner("Recalculating your plan..."):
            try:
                from ortools.sat.python import cp_model as _cp

                remaining_sems   = list(range(student.current_semester, 9))
                eligible_courses, failed_courses = planner.get_eligible_and_failed_courses(student)
                completed_set_regen = set(student.completed_courses)

                # ── FIX (Bug 1, Step 1): Remove courses from adjusted first ──
                adjusted = [c for c in eligible_courses if c not in avoided_list]

                # ── FIX (Bug 1, Step 2): Enforce theory-lab pair integrity ────
                # If one half of a theory-lab pair was removed (via avoided_list),
                # remove the other half too so the solver never sees an orphaned pair.
                adjusted, auto_removed_pairs = planner.enforce_theory_lab_pair_integrity(
                    adjusted, completed_set_regen
                )

                # Warn the user about auto-removed orphaned halves
                warnings_out = []
                for removed_cc, partner_cc in auto_removed_pairs.items():
                    ci_r = loader.get_course_by_code(removed_cc)
                    ci_p = loader.get_course_by_code(partner_cc)
                    r_name = ci_r['course_name'] if ci_r else removed_cc
                    p_name = ci_p['course_name'] if ci_p else partner_cc
                    warnings_out.append(
                        f"⚠️ **{r_name}** was also removed because its theory-lab partner "
                        f"**{p_name}** was removed. Theory and lab must always go together."
                    )

                # ── Build original-semester map for pinned/rearranged logic ───
                # FIX (Bug 2): Use the actual original semester, not always cur_sem
                original_sem_map = {c: s for s, clist in base_plan.items() for c in clist}

                # Add in regen_clicked, after building `adjusted`, before cp = _cp.CpModel()
                print("=== REGEN DEBUG ===")
                print(f"remaining_sems: {remaining_sems}")
                print(f"adjusted count: {len(adjusted)}")
                print(f"pinned_courses: {st.session_state.pinned_courses}")
                print(f"rearranged_list: {rearranged_list}")

                # Simulate what each semester looks like after pins
                from collections import defaultdict
                sim = defaultdict(list)
                for s, clist in base_plan.items():
                    for c in clist:
                        target = st.session_state.pinned_courses.get(c, s)
                        if c not in avoided_list:
                            sim[target].append(c)
                # Add newly pinned courses not in base_plan
                for c, s in st.session_state.pinned_courses.items():
                    if c not in {cc for clist in base_plan.values() for cc in clist}:
                        sim[s].append(c)

                for s in sorted(sim.keys()):
                    cr = sum(loader.get_credits(c) for c in sim[s])
                    print(f"  Sem {s}: {len(sim[s])} courses, {cr} credits — {sim[s]}")

                # Check graduation requirements
                earned = round(sum(loader.get_credits(c) for c in student.completed_courses))
                pool_cr = sum(loader.get_credits(c) for c in adjusted)
                print(f"Credits earned: {earned}, pool: {pool_cr}, total: {earned + pool_cr}, needed: 160")

                from collections import defaultdict as dd
                cat_earned = dd(int)
                for c in student.completed_courses:
                    ci = loader.get_course_by_code(c)
                    if ci:
                        cat_earned[ci['course_type']] += loader.get_credits(c)
                cat_pool = dd(int)
                for c in adjusted:
                    ci = loader.get_course_by_code(c)
                    if ci:
                        cat_pool[ci['course_type']] += loader.get_credits(c)
                print("Category check:")
                for cat, req in loader.credit_requirements.items():
                    needed = req.get('required', 0)
                    have = cat_earned.get(cat, 0)
                    pool = cat_pool.get(cat, 0)
                    if cat == 'Combined Elective':
                        pool = sum(cat_pool[t] for t in ['Discipline Elective','Open Elective','Multidisciplinary Elective'])
                    status = "✅" if have >= needed or have + pool >= needed else "❌"
                    print(f"  {status} {cat}: earned={have}, pool={pool}, needed={needed}, gap={max(0,needed-have)}")

                cp = _cp.CpModel()
                x  = planner._create_variables(cp, adjusted, remaining_sems)
                planner.add_hard_constraints(cp, x, student, adjusted, failed_courses, remaining_sems)

                # FIX (Bug 2): Block the course's ACTUAL original semester, not cur_sem
                for cc in rearranged_list:
                    orig_sem = original_sem_map.get(cc)
                    if orig_sem and cc in adjusted and (cc, orig_sem) in x:
                        cp.add(x[cc, orig_sem] == 0)

                for cc, ps in st.session_state.pinned_courses.items():
                    if cc not in adjusted:
                        warnings_out.append(f"⚠️ {cc} could not be pinned — not eligible.")
                        continue
                    if (cc, ps) in x:
                        cp.add(x[cc, ps] == 1)
                    else:
                        warnings_out.append(f"⚠️ {cc} — Semester {ps} not valid.")

                st.session_state.customization_warnings = warnings_out

                base_config = all_plans[base_plan_type]['config']

                wp  = planner.add_workload_balance_soft_constraint(cp, x, student, adjusted, remaining_sems, base_plan_type)
                dr  = planner.add_diversity_reward_soft_constraint(cp, x, adjusted, remaining_sems)
                cl  = planner.add_total_credit_limit_exceeding_penalty(cp, x, student, adjusted, remaining_sems)
                dp  = planner.add_difficulty_balance_soft_constraint(cp, x, student, adjusted, remaining_sems, base_plan_type)
                fp  = planner.add_prerequisite_freshness_soft_constraint(cp, x, student, adjusted, remaining_sems)
                ciw = planner.add_course_interest_soft_constraint(adjusted, st.session_state.llm_weights)

                planner.set_objective(
                    cp, x, student, adjusted, remaining_sems,
                    failed_courses, wp, ciw, base_config['weights'],
                    dr, cl, dp, fp
                )

                solver = _cp.CpSolver()
                solver.parameters.max_time_in_seconds = 30.0
                solver.parameters.random_seed = 42
                solver.parameters.num_search_workers = 1

                # Add right before status = solver.Solve(cp)
                # Test full hard constraints + pins together (no soft, no objective)
                test_hard = _cp.CpModel()
                test_x_hard = planner._create_variables(test_hard, adjusted, remaining_sems)
                planner.add_hard_constraints(test_hard, test_x_hard, student, adjusted, failed_courses, remaining_sems)
                for cc in rearranged_list:
                    orig_sem = original_sem_map.get(cc)
                    if orig_sem and cc in adjusted and (cc, orig_sem) in test_x_hard:
                        test_hard.add(test_x_hard[cc, orig_sem] == 0)
                for cc, ps in st.session_state.pinned_courses.items():
                    if cc in adjusted and (cc, ps) in test_x_hard:
                        test_hard.add(test_x_hard[cc, ps] == 1)
                test_s_hard = _cp.CpSolver()
                test_s_hard.parameters.max_time_in_seconds = 10.0
                test_s_hard.parameters.num_search_workers = 1
                print(f"TEST (ALL hard + pins): {test_s_hard.StatusName(test_s_hard.Solve(test_hard))}")

                # Now test adding each soft constraint on top
                for soft_name, soft_fn in [
                    ("workload", lambda m,x: planner.add_workload_balance_soft_constraint(m, x, student, adjusted, remaining_sems, base_plan_type)),
                    ("diversity", lambda m,x: planner.add_diversity_reward_soft_constraint(m, x, adjusted, remaining_sems)),
                    ("credit_limit", lambda m,x: planner.add_total_credit_limit_exceeding_penalty(m, x, student, adjusted, remaining_sems)),
                    ("difficulty", lambda m,x: planner.add_difficulty_balance_soft_constraint(m, x, student, adjusted, remaining_sems, base_plan_type)),
                    ("freshness", lambda m,x: planner.add_prerequisite_freshness_soft_constraint(m, x, student, adjusted, remaining_sems)),
                ]:
                    test_soft = _cp.CpModel()
                    test_x_soft = planner._create_variables(test_soft, adjusted, remaining_sems)
                    planner.add_hard_constraints(test_soft, test_x_soft, student, adjusted, failed_courses, remaining_sems)
                    for cc in rearranged_list:
                        orig_sem = original_sem_map.get(cc)
                        if orig_sem and cc in adjusted and (cc, orig_sem) in test_x_soft:
                            test_soft.add(test_x_soft[cc, orig_sem] == 0)
                    for cc, ps in st.session_state.pinned_courses.items():
                        if cc in adjusted and (cc, ps) in test_x_soft:
                            test_soft.add(test_x_soft[cc, ps] == 1)
                    soft_fn(test_soft, test_x_soft)
                    test_s_soft = _cp.CpSolver()
                    test_s_soft.parameters.max_time_in_seconds = 10.0
                    test_s_soft.parameters.num_search_workers = 1
                    print(f"TEST (hard + pins + {soft_name}): {test_s_soft.StatusName(test_s_soft.Solve(test_soft))}")

                status = solver.Solve(cp)

                if status in (_cp.OPTIMAL, _cp.FEASIBLE):
                    st.session_state.custom_plan = planner.get_solution(solver, x, adjusted, remaining_sems)
                    st.rerun()
                else:
                    st.error("❌ No valid plan found with your customizations.")
                    st.markdown("---")
                    st.markdown("#### 🔍 Why Did This Fail?")

                    with st.spinner("Identifying the exact constraint(s) causing infeasibility..."):
                        # ── FIX (Bug 3): Pass `adjusted` (avoided-filtered) NOT
                        # `eligible_courses` (full list) so layered solver checks
                        # reflect the exact same pool the regen solver used.
                        diagnosis = planner.diagnose_infeasibility_core(
                            student,
                            adjusted,           # ← FIX: was eligible_courses
                            failed_courses,
                            remaining_sems,
                            avoided_list=avoided_list,
                            pinned_courses=st.session_state.pinned_courses,
                            rearranged_list=rearranged_list,
                            is_customization=True,
                            base_plan=base_plan,
                        )

                    render_diagnosis(diagnosis, current_sem=current_sem)

            except Exception as e:
                st.error(f"Error: {e}")
                with st.expander("Details"):
                    st.exception(e)

    st.markdown("---")

    # ── Custom plan result ────────────────────────────────────────────────────
    if st.session_state.custom_plan:
        st.markdown("### Your Customized Plan")
        for w in st.session_state.customization_warnings:
            st.warning(w)

        original_flat = {c: s for s, v in base_plan.items() for c in v}
        custom_flat   = {c: s for s, v in st.session_state.custom_plan.items() for c in v}
        added_in      = set(custom_flat) - set(original_flat)
        removed_in    = set(original_flat) - set(custom_flat)
        moved_in      = {c for c in (set(custom_flat) & set(original_flat)) if custom_flat[c] != original_flat[c]}

        c1, c2, c3, c4 = st.columns(4)
        orig_c  = sum(len(v) for v in base_plan.values())
        cust_c  = sum(len(v) for v in st.session_state.custom_plan.values())
        orig_cr = sum(loader.get_credits(c) for v in base_plan.values() for c in v)
        cust_cr = sum(loader.get_credits(c) for v in st.session_state.custom_plan.values() for c in v)
        c1.metric("Courses", cust_c, delta=cust_c - orig_c)
        c2.metric("Credits", cust_cr, delta=cust_cr - orig_cr)
        c3.metric("Moved",   len(moved_in))
        c4.metric("Removed", len(removed_in))

        if added_in:
            st.success(f"Added: {', '.join(loader.get_course_by_code(c)['course_name'] if loader.get_course_by_code(c) else c for c in sorted(added_in))}")
        if removed_in:
            st.warning(f"Removed: {', '.join(loader.get_course_by_code(c)['course_name'] if loader.get_course_by_code(c) else c for c in sorted(removed_in))}")
        if moved_in:
            parts = [f"{loader.get_course_by_code(c)['course_name'] if loader.get_course_by_code(c) else c} (Sem {original_flat[c]} → Sem {custom_flat[c]})" for c in moved_in]
            st.info(f"Rescheduled: {', '.join(parts)}")

        for sem in sorted(st.session_state.custom_plan.keys()):
            if not st.session_state.custom_plan[sem]:
                continue
            courses = st.session_state.custom_plan[sem]
            sem_cr  = sum(loader.get_credits(c) for c in courses)
            slot_note = " *(slot conflicts enforced)*" if sem == current_sem else " *(future — slots not enforced)*"
            with st.expander(f"Semester {sem}{slot_note} — {len(courses)} courses, {sem_cr} credits", expanded=True):
                rows = []
                for cc in courses:
                    ci = loader.get_course_by_code(cc)
                    if not ci:
                        continue
                    if cc in added_in:
                        change = "🆕 Added"
                    elif cc in moved_in and custom_flat.get(cc) == sem:
                        change = f"↕️ Moved from Sem {original_flat.get(cc,'?')}"
                    else:
                        change = "✅ Unchanged"
                    rows.append({
                        'Name': ci['course_name'], 'Code': cc,
                        'Credits': loader.get_credits(cc), 'Type': ci['course_type'],
                        'Mandatory': '✅' if ci.get('is_mandatory') else '—',
                        'Occupied Slots': ', '.join(ci.get('slots', [])) or '—',
                        'Change': change
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            export_rows = []
            for sem, courses in st.session_state.custom_plan.items():
                for cc in courses:
                    ci = loader.get_course_by_code(cc)
                    if ci:
                        export_rows.append({
                            'Semester': sem, 'Code': cc, 'Name': ci['course_name'],
                            'Credits': loader.get_credits(cc), 'Type': ci['course_type'],
                            'Mandatory': 'Yes' if ci.get('is_mandatory') else 'No'
                        })
            st.download_button("Download Customized Plan (CSV)",
                               data=pd.DataFrame(export_rows).to_csv(index=False),
                               file_name=f"custom_{student.student_id}.csv",
                               mime="text/csv", use_container_width=True)
        with c2:
            if st.button("Reset All Changes", use_container_width=True, key="reset_bottom"):
                st.session_state.selected_for_review   = {}
                st.session_state.pinned_courses         = {}
                st.session_state.custom_plan            = None
                st.session_state.customization_warnings = []
                st.rerun()
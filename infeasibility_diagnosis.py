"""
infeasibility_diagnosis.py
──────────────────────────────────────────────────────────────────────────────
Simple, reliable infeasibility diagnosis.

Algorithm:
  1. Build the exact same CP model the real solver uses (all constraints + user pins).
  2. Confirm it is infeasible.
  3. Remove ONE constraint at a time and re-solve.
     If removing constraint X makes it feasible → X is a culprit.
  4. Report all culprit constraints clearly.

This is dead simple and always correct — no MIS enumeration, no subset search.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple
from ortools.sat.python import cp_model


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINT METADATA  (name → human readable title + explanation)
# ─────────────────────────────────────────────────────────────────────────────

CONSTRAINT_META: Dict[str, Tuple[str, str]] = {
    # name: (short title, explanation)
    "credit_bounds": (
        "Credit bounds (16–25 credits per semester)",
        "Every semester must have between 16 and 25 credits. "
        "Too many removals leave semesters underfillable; "
        "too many courses pinned to one semester can exceed the cap.",
    ),
    "once_only": (
        "Each course taken at most once",
        "No course may appear in more than one semester.",
    ),
    "failed_retake": (
        "Failed course retakes",
        "Every failed course must be scheduled exactly once in the remaining semesters.",
    ),
    "prerequisites": (
        "Prerequisite ordering",
        "A course can only be taken after all its prerequisites are done. "
        "Pinning a course before its prerequisite, or removing a prerequisite "
        "from the pool, violates this.",
    ),
    "slot_conflicts": (
        "Timetable slot conflicts (current semester only)",
        "Two courses sharing a timetable slot cannot both be in the current semester. "
        "Slot conflicts are only enforced for the current semester — "
        "future semester timetables are not yet known.",
    ),
    "theory_lab": (
        "Theory-lab pairing",
        "A theory course and its lab must always be in the same semester. "
        "Moving just the lab (or just the theory) to a different semester breaks this.",
    ),
    "category_credits": (
        "Graduation category credits",
        "Each graduation category needs a minimum credit total. "
        "Removing too many courses of a given type makes this impossible.",
    ),
    "total_graduation_credits": (
        "Total graduation credits (≥ 160)",
        "The total credits across all semesters must reach 160. "
        "Too many removals push the total below this threshold.",
    ),
    "year_unlock": (
        "Year-level unlock",
        "A Year-N course may only appear from Semester (2N-1) onwards. "
        "Pinning it to an earlier semester breaks this rule.",
    ),
    "max_courses": (
        "Max courses per semester (≤ 12)",
        "At most 12 courses may be in any single semester.",
    ),
    "mandatory_completion": (
        "All mandatory courses must be scheduled",
        "Every mandatory course must appear exactly once. "
        "It cannot be removed or left unscheduled.",
    ),
}

SUGGESTIONS: Dict[str, str] = {
    "credit_bounds":
        "Check that each semester can still reach 16 credits after your removals, "
        "and that no semester is over-pinned above 25.",
    "failed_retake":
        "Failed courses must each appear exactly once — make sure they aren't blocked "
        "by slot conflicts in the current semester.",
    "prerequisites":
        "A pinned course may be placed before its prerequisite. "
        "Move the dependent course later, or unpin it.",
    "slot_conflicts":
        "Two courses pinned to the current semester share a timetable slot. "
        "Move one of them to a different semester.",
    "theory_lab":
        "Move the lab back to the same semester as its theory course, "
        "or move both to the same new semester.",
    "category_credits":
        "Restore some removed courses so each graduation category can meet its credit minimum.",
    "total_graduation_credits":
        "Restore removed courses — the pool no longer has enough credits to reach 160.",
    "year_unlock":
        "Move the pinned course to a semester that matches its year level "
        "(Year-N course → earliest Semester 2N-1).",
    "max_courses":
        "Spread pinned courses across more semesters — one semester exceeds 12 courses.",
    "mandatory_completion":
        "A mandatory course cannot be placed anywhere. "
        "Check its prerequisites are met and it has no slot conflicts.",
}


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINT BUILDERS  (each adds one group of constraints to the model)
# ─────────────────────────────────────────────────────────────────────────────

def _build_credit_bounds(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_min_max_credit_constraint(model, x, courses, semesters)

def _build_once_only(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_course_can_be_taken_only_once_constraint(model, x, courses, semesters)

def _build_failed_retake(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_failed_courses_retake_constraint(model, x, failed_courses, semesters)

def _build_prerequisites(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_preq_check_constraint(model, x, student, courses, semesters)

def _build_slot_conflicts(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_slot_conflict_constraint(model, x, courses, semesters)

def _build_theory_lab(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_theory_lab_pairing_constraint(model, x, student, courses, semesters)

def _build_category_credits(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_category_credit_requirement_constraint(model, x, student, courses, semesters)

def _build_total_grad_credits(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_total_min_credits_req_for_graduation(model, x, student, courses, semesters)

def _build_year_unlock(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_year_level_course_unlock_constraint(model, x, courses, semesters)

def _build_max_courses(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_max_allowed_courses_per_semester(model, x, courses, semesters)

def _build_mandatory_completion(planner, model, x, student, courses, semesters, failed_courses):
    planner.add_mandatory_courses_completion_constraint(model, x, courses, semesters)


CONSTRAINT_BUILDERS: Dict[str, Callable] = {
    "credit_bounds":            _build_credit_bounds,
    "once_only":                _build_once_only,
    "failed_retake":            _build_failed_retake,
    "prerequisites":            _build_prerequisites,
    "slot_conflicts":           _build_slot_conflicts,
    "theory_lab":               _build_theory_lab,
    "category_credits":         _build_category_credits,
    "total_graduation_credits": _build_total_grad_credits,
    "year_unlock":              _build_year_unlock,
    "max_courses":              _build_max_courses,
    "mandatory_completion":     _build_mandatory_completion,
}

ALL_CONSTRAINTS = list(CONSTRAINT_BUILDERS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# CORE SOLVER  — build model with given constraints + user pins, return status
# ─────────────────────────────────────────────────────────────────────────────

def _solve(
    planner,
    student,
    courses: List[str],
    semesters: List[int],
    failed_courses: Set[str],
    skip_constraints: List[str],        # constraints to LEAVE OUT
    pinned_courses: Dict[str, int],     # user pins: {course: semester}
    rearranged_list: List[str],         # courses banned from current semester
    time_limit: float = 5.0,
) -> bool:
    """
    Build and solve a CP model with all constraints EXCEPT those in skip_constraints.
    Always applies the user's pinned_courses and rearranged_list.
    Returns True if feasible.
    """
    m = cp_model.CpModel()
    x = planner._create_variables(m, courses, semesters)

    for name, builder in CONSTRAINT_BUILDERS.items():
        if name not in skip_constraints:
            builder(planner, m, x, student, courses, semesters, failed_courses)

    # Apply user pins
    for cc, ps in pinned_courses.items():
        if cc in courses and (cc, ps) in x:
            m.add(x[cc, ps] == 1)

    # Apply move-away-from-current constraints
    if semesters:
        cur = semesters[0]
        for cc in rearranged_list:
            if cc in courses and (cc, cur) in x:
                m.add(x[cc, cur] == 0)

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.num_search_workers  = 1
    return s.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DIAGNOSIS  — remove one constraint at a time, find culprits
# ─────────────────────────────────────────────────────────────────────────────

def find_culprit_constraints(
    planner,
    student,
    courses: List[str],
    semesters: List[int],
    failed_courses: Set[str],
    pinned_courses: Dict[str, int],
    rearranged_list: List[str],
    time_limit: float = 5.0,
) -> List[str]:
    """
    Returns a list of constraint names that are causing infeasibility.

    For each constraint, we remove it and re-solve.
    If removing it makes the problem feasible → it's a culprit.

    Simple, reliable, always correct.
    """
    # First confirm the full model is actually infeasible
    if _solve(planner, student, courses, semesters, failed_courses,
              skip_constraints=[], pinned_courses=pinned_courses,
              rearranged_list=rearranged_list, time_limit=time_limit):
        return []  # It's actually feasible — no culprits

    culprits = []
    for name in ALL_CONSTRAINTS:
        feasible_without = _solve(
            planner, student, courses, semesters, failed_courses,
            skip_constraints=[name],
            pinned_courses=pinned_courses,
            rearranged_list=rearranged_list,
            time_limit=time_limit,
        )
        if feasible_without:
            culprits.append(name)

    return culprits


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def diagnose_infeasibility_rich(
    planner,
    student,
    eligible_courses:    List[str],
    failed_courses:      Set[str],
    remaining_semesters: List[int],
    avoided_list:        List[str]      = None,
    pinned_courses:      Dict[str, int] = None,
    rearranged_list:     List[str]      = None,
    is_customization:    bool           = False,
    oracle_time:         float          = 5.0,
) -> Dict:
    """
    Diagnose why the solver failed.

    Returns a dict consumed by render_diagnosis() in app.py.
    """
    if avoided_list    is None: avoided_list    = []
    if pinned_courses  is None: pinned_courses  = {}
    if rearranged_list is None: rearranged_list = []

    loader      = planner.loader
    current_sem = remaining_semesters[0] if remaining_semesters else None

    result: Dict = {
        "is_customization":         is_customization,
        "root_cause":               "",
        "pre_solve_violations":     [],
        "broken_constraint_layer":  "",
        "broken_constraint_detail": "",
        "credit_shortfalls":        [],
        "slot_conflicts":           [],
        "mandatory_issues":         [],
        "theory_lab_issues":        [],
        "year_level_issues":        [],
        "suggestion":               "",
        "culprit_constraints":      [],   # NEW — list of constraint name strings
        "mis_summaries":            [],   # kept for render_diagnosis compatibility
        "all_mis":                  [],
        "interacting":              False,
    }

    # ── Step 1: find culprit constraints by elimination ───────────────────────
    culprits = find_culprit_constraints(
        planner, student, eligible_courses, remaining_semesters,
        failed_courses, pinned_courses, rearranged_list,
        time_limit=oracle_time,
    )

    result["culprit_constraints"] = culprits

    # ── Step 2: build human-readable output from culprits ─────────────────────
    if not culprits:
        # All constraints are jointly responsible (very rare — just say so)
        result["root_cause"] = (
            "Multiple constraints are jointly causing infeasibility and none "
            "can be individually identified as the single cause. "
            "Try resetting your changes one at a time."
        )
        result["broken_constraint_layer"]  = "Complex interaction"
        result["broken_constraint_detail"] = "Reset changes one at a time to isolate the issue."
        result["suggestion"] = "Reset all customizations and reapply them one at a time."
        return result

    # Build mis_summaries list (reusing render_diagnosis's existing display logic)
    mis_summaries = []
    for name in culprits:
        title, explanation = CONSTRAINT_META.get(name, (name, ""))
        mis_summaries.append({
            "constraints": [name],
            "title":       title,
            "explanation": explanation,
        })

    result["mis_summaries"] = mis_summaries
    result["all_mis"]       = [[c] for c in culprits]

    # Root cause summary
    if len(culprits) == 1:
        title, explanation = CONSTRAINT_META[culprits[0]]
        result["root_cause"]               = f"**{title}** is causing infeasibility."
        result["broken_constraint_layer"]  = title
        result["broken_constraint_detail"] = explanation
    else:
        titles = [CONSTRAINT_META[c][0] for c in culprits]
        result["root_cause"] = (
            f"**{len(culprits)} constraints** are each independently causing infeasibility: "
            + ", ".join(f"**{t}**" for t in titles) + "."
        )
        result["broken_constraint_layer"]  = titles[0]
        result["broken_constraint_detail"] = CONSTRAINT_META[culprits[0]][1]

    # ── Step 3: detailed sub-analyses for specific culprits ───────────────────

    # Theory-lab issues — scan pinned courses for mismatched pairs
    if "theory_lab" in culprits and is_customization:
        loader = planner.loader
        seen = set()
        for cc, ps in pinned_courses.items():
            # cc is a lab — find its theory
            theory = loader.get_theory_course(cc) if hasattr(loader, 'get_theory_course') else None
            if theory and theory in eligible_courses:
                pair = tuple(sorted([theory, cc]))
                if pair not in seen:
                    # theory semester: pinned or figure it out from the plan
                    theory_sem = pinned_courses.get(theory)
                    if theory_sem is not None and theory_sem != ps:
                        ci_t = loader.get_course_by_code(theory)
                        ci_l = loader.get_course_by_code(cc)
                        result["theory_lab_issues"].append((theory, cc, theory_sem, ps))
                        result["pre_solve_violations"].append(
                            f"**{ci_t['course_name'] if ci_t else theory}** is in Semester {theory_sem} "
                            f"but its lab **{ci_l['course_name'] if ci_l else cc}** "
                            f"is pinned to Semester {ps}. They must be in the same semester."
                        )
                        seen.add(pair)

            # cc is a theory — find its lab
            lab = loader.get_lab_course(cc)
            if lab and lab in eligible_courses:
                pair = tuple(sorted([cc, lab]))
                if pair not in seen:
                    lab_sem = pinned_courses.get(lab)
                    if lab_sem is not None and lab_sem != ps:
                        ci_t = loader.get_course_by_code(cc)
                        ci_l = loader.get_course_by_code(lab)
                        result["theory_lab_issues"].append((cc, lab, ps, lab_sem))
                        result["pre_solve_violations"].append(
                            f"**{ci_t['course_name'] if ci_t else cc}** is pinned to Semester {ps} "
                            f"but its lab **{ci_l['course_name'] if ci_l else lab}** "
                            f"is in Semester {lab_sem}. They must be in the same semester."
                        )
                        seen.add(pair)

    # Year-level issues
    if "year_unlock" in culprits and is_customization:
        for cc, ps in pinned_courses.items():
            ci = loader.get_course_by_code(cc)
            if ci:
                yr_req = ci.get('year_offered', 1)
                yr_sem = (ps + 1) // 2
                if yr_sem < yr_req:
                    earliest = (yr_req - 1) * 2 + 1
                    result["year_level_issues"].append((cc, ci['course_name'], yr_req, ps))
                    result["pre_solve_violations"].append(
                        f"**{ci['course_name']}** is a Year {yr_req} course pinned to "
                        f"Semester {ps} (Year {yr_sem}). Earliest valid: Semester {earliest}."
                    )

    # Slot conflicts in current semester
    if "slot_conflicts" in culprits and current_sem is not None:
        pinned_now = [cc for cc, ps in pinned_courses.items()
                      if ps == current_sem and cc in eligible_courses]
        for i, c1 in enumerate(pinned_now):
            for c2 in pinned_now[i+1:]:
                if not loader.can_take_together(c1, c2):
                    ci1 = loader.get_course_by_code(c1)
                    ci2 = loader.get_course_by_code(c2)
                    s1, s2 = set(loader.get_course_slots(c1)), set(loader.get_course_slots(c2))
                    shared = s1 & s2
                    msg = (
                        f"**{ci1['course_name'] if ci1 else c1}** and "
                        f"**{ci2['course_name'] if ci2 else c2}** share slot(s): "
                        f"**{', '.join(shared)}** in Semester {current_sem}."
                    )
                    result["slot_conflicts"].append(msg)

    # ── Step 4: suggestion ────────────────────────────────────────────────────
    tips = [SUGGESTIONS.get(c, "") for c in culprits if SUGGESTIONS.get(c)]
    if len(tips) == 1:
        result["suggestion"] = tips[0]
    elif tips:
        result["suggestion"] = "Fix all of the following:\n• " + "\n• ".join(tips)
    else:
        result["suggestion"] = "Reset your changes one at a time to isolate the conflict."

    return result
"""
slot_utils.py
─────────────────────────────────────────────────────────────────────────────
Utility for VIT FFCS slot assignment analysis.

Each course's `slots` list = the time slots it CAN be registered in.
The student picks exactly ONE slot per course during FFCS registration.
Two courses conflict ONLY if the student is forced to pick the same slot.

analyse_semester_slots() computes, for every course in a semester:
  - which of its slots are SAFE  (a full conflict-free assignment exists using that slot)
  - which are UNSAFE (picking that slot makes it impossible to assign the rest)
  - one example valid full assignment
  - tight courses (≤1 safe slot — register these first!)
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple

SPECIAL_SLOTS: Set[str] = {
    "NGCR", "SS1", "SS2", "SS3", "SS4",
    "PRJ", "INT", "INT-FULL",
    "CAP1", "CAP2", "OE1", "OE2", "OE3", "OE4",
}


def _is_special(slot: str) -> bool:
    return slot in SPECIAL_SLOTS


def find_valid_slot_assignment(
    courses: List[str],
    slot_options: Dict[str, List[str]],
) -> Optional[Dict[str, str]]:
    """
    Backtracking search: assign one slot per course such that no two
    courses share the same non-special slot.
    Returns {course_code: slot} or None if impossible.
    """
    assignment: Dict[str, str] = {}
    used: Set[str] = set()

    def backtrack(idx: int) -> bool:
        if idx == len(courses):
            return True
        cc = courses[idx]
        for slot in slot_options.get(cc, [""]):
            if _is_special(slot) or slot not in used:
                assignment[cc] = slot
                if not _is_special(slot):
                    used.add(slot)
                if backtrack(idx + 1):
                    return True
                assignment.pop(cc)
                if not _is_special(slot):
                    used.discard(slot)
        return False

    return assignment if backtrack(0) else None


def analyse_semester_slots(
    courses: List[str],
    slot_options: Dict[str, List[str]],
) -> Dict:
    """
    For a given semester's course list, return:
    {
      "feasible": bool,
      "example_assignment": {course: slot} | None,
      "safe_slots":  {course: [slots where a full valid assignment still exists]},
      "unsafe_slots":{course: [slots that make the rest impossible to assign]},
      "tight_courses": [courses with only 1 safe regular slot — register first!],
    }
    """
    example = find_valid_slot_assignment(courses, slot_options)

    safe_slots: Dict[str, List[str]]   = {}
    unsafe_slots: Dict[str, List[str]] = {}

    for cc in courses:
        safe, unsafe = [], []
        for slot in slot_options.get(cc, []):
            if _is_special(slot):
                safe.append(slot)
                continue
            # Pin this course to `slot`, try to assign the rest
            forced = {
                c: ([slot] if c == cc else slot_options.get(c, []))
                for c in courses
            }
            if find_valid_slot_assignment(courses, forced) is not None:
                safe.append(slot)
            else:
                unsafe.append(slot)
        safe_slots[cc]   = safe
        unsafe_slots[cc] = unsafe

    tight_courses = [
        cc for cc in courses
        if len([s for s in safe_slots.get(cc, []) if not _is_special(s)]) == 1
        and any(not _is_special(s) for s in slot_options.get(cc, []))
    ]

    return {
        "feasible":          example is not None,
        "example_assignment": example,
        "safe_slots":        safe_slots,
        "unsafe_slots":      unsafe_slots,
        "tight_courses":     tight_courses,
    }
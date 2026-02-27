"""
Comprehensive Data Loader for VIT FFCS Course Recommendation System
Provides all necessary data access methods for CP-SAT solver
"""

import json
import os
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field

# File paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_FILE = os.path.join(CURRENT_DIR, "courses.json")
STUDENTS_DIR = os.path.join(CURRENT_DIR, "students")


# ============================================================================
# VIT GRADE SCHEMA  (Single source of truth)
# ============================================================================

GRADE_POINTS_MAP: Dict[str, int] = {
    'S': 10, 'A': 9, 'B': 8, 'C': 7, 'D': 6, 'E': 5, 'F': 0, 'P': 0,
}
PASSING_GRADES: Set[str] = {'S', 'A', 'B', 'C', 'D', 'E', 'P'}
CGPA_GRADES: Set[str] = {'S', 'A', 'B', 'C', 'D', 'E', 'F'}
VALID_GRADES: Set[str] = set(GRADE_POINTS_MAP.keys())


# ============================================================================
# ACADEMIC PERFORMANCE HELPER
# ============================================================================

def compute_academic_performance(
    course_records: List['CourseRecord'],
) -> Tuple[Dict[int, float], float]:
    by_semester: Dict[int, List['CourseRecord']] = defaultdict(list)
    for r in course_records:
        by_semester[r.semester_taken].append(r)

    sgpa_by_semester: Dict[int, float] = {}
    for sem in sorted(by_semester.keys()):
        total_cp = 0.0
        total_cr = 0.0
        for r in by_semester[sem]:
            if r.grade not in CGPA_GRADES:
                continue
            total_cp += r.grade_points * r.credits
            total_cr += r.credits
        sgpa_by_semester[sem] = round(total_cp / total_cr, 2) if total_cr > 0 else 0.0

    latest: Dict[str, 'CourseRecord'] = {}
    for sem in sorted(by_semester.keys()):
        for r in by_semester[sem]:
            if r.grade not in CGPA_GRADES:
                continue
            latest[r.course_code] = r

    total_cp = sum(r.grade_points * r.credits for r in latest.values())
    total_cr = sum(r.credits for r in latest.values())
    cgpa = round(total_cp / total_cr, 2) if total_cr > 0 else 0.0

    return sgpa_by_semester, cgpa


# ============================================================================
# DATA LOADER CLASS
# ============================================================================

class DataLoader:
    """
    Comprehensive data loader providing all methods needed for CP-SAT solver.
    """

    def __init__(self):
        self.courses_data: List[Dict] = []
        self.course_code_to_id: Dict[str, int] = {}
        self.course_id_to_code: Dict[int, str] = {}
        self.course_code_dict: Dict[str, Dict] = {}
        self.course_id_dict: Dict[int, Dict] = {}
        self.course_prereqs: Dict[str, List[str]] = defaultdict(list)
        self.course_unlocks: Dict[str, List[str]] = defaultdict(list)
        self.courses_by_type: Dict[str, List[str]] = defaultdict(list)
        self.mandatory_courses: List[str] = []
        self.elective_courses: List[str] = []
        self.slot_to_courses: Dict[str, List[str]] = defaultdict(list)
        self.course_to_slots: Dict[str, List[str]] = {}
        self.slot_conflicts: Dict[str, Set[str]] = {}
        self.courses_by_year: Dict[int, List[str]] = defaultdict(list)
        self.theory_to_lab: Dict[str, str] = {}
        self.lab_to_theory: Dict[str, str] = {}
        self.difficulty_map: Dict[str, int] = {}
        self.pass_rate_map: Dict[str, float] = {}
        self.credit_map: Dict[str, int] = {}
        self.credit_requirements: Dict = {}
        self.students: Dict[str, 'StudentProfile'] = {}
        self.current_student: Optional['StudentProfile'] = None

    # ============================================================================
    # CORE LOADING METHODS
    # ============================================================================

    def load_course_data(self) -> None:
        if not os.path.exists(COURSES_FILE):
            raise FileNotFoundError(f"Course data file not found: {COURSES_FILE}")

        with open(COURSES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.courses_data = data.get('courses', [])
        self.credit_requirements = data.get('credit_requirements', {})

        self._build_course_indices()
        self._build_prerequisite_maps()
        self._build_category_maps()
        self._build_slot_maps()
        self._build_year_maps()
        self._build_lab_relationships()
        self._build_metadata_maps()
        self._detect_slot_conflicts()

        print(f"✅ Loaded {len(self.courses_data)} courses")
        print(f"   - Mandatory : {len(self.mandatory_courses)}")
        print(f"   - Electives : {len(self.elective_courses)}")
        print(f"   - Unique slots : {len(self.slot_to_courses)}")

    def load_student(self, student_id: str) -> 'StudentProfile':
        student_file = os.path.join(STUDENTS_DIR, f"{student_id}.json")

        if not os.path.exists(student_file):
            raise FileNotFoundError(f"Student file not found: {student_file}")

        with open(student_file, 'r', encoding='utf-8') as f:
            student_data = json.load(f)

        student = StudentProfile.from_dict(student_data)

        stored_cgpa = student_data.get('cgpa', 0.0)
        calculated_cgpa = student.recalculate_cgpa()
        if abs(calculated_cgpa - stored_cgpa) > 0.05:
            print(
                f"   ⚠️  CGPA mismatch for {student_id}: "
                f"stored={stored_cgpa:.2f}, calculated={calculated_cgpa:.2f}. "
                f"Using calculated value."
            )

        self.students[student_id] = student
        self.current_student = student

        print(f"✅ Loaded student : {student.name} (ID: {student.student_id})")
        print(f"   - Current    : Semester {student.current_semester}, Year {student.current_year}")
        print(f"   - Completed  : {len(student.completed_courses)} courses")
        print(f"   - Failed     : {len(student.failed_courses)} courses")
        print(f"   - CGPA       : {student.cgpa:.2f}")

        return student

    # ============================================================================
    # INTERNAL INDEX BUILDING METHODS
    # ============================================================================

    def _build_course_indices(self):
        for course in self.courses_data:
            course_id   = course['id']
            course_code = course['course_code']
            self.course_code_to_id[course_code] = course_id
            self.course_id_to_code[course_id]   = course_code
            self.course_code_dict[course_code]  = course
            self.course_id_dict[course_id]      = course

    def _build_prerequisite_maps(self):
        for course in self.courses_data:
            course_code = course['course_code']
            self.course_prereqs[course_code] = course.get('prerequisites', [])

        for course_code, prereqs in self.course_prereqs.items():
            for prereq in prereqs:
                self.course_unlocks[prereq].append(course_code)

    def _build_category_maps(self):
        for course in self.courses_data:
            course_code  = course['course_code']
            course_type  = course['course_type']
            is_mandatory = course['is_mandatory']
            self.courses_by_type[course_type].append(course_code)
            if is_mandatory:
                self.mandatory_courses.append(course_code)
            else:
                self.elective_courses.append(course_code)

    def _build_slot_maps(self):
        for course in self.courses_data:
            course_code = course['course_code']
            slots = course.get('slots', [])
            self.course_to_slots[course_code] = slots
            for slot in slots:
                self.slot_to_courses[slot].append(course_code)

    def _build_year_maps(self):
        for course in self.courses_data:
            course_code = course['course_code']
            year = course.get('year_offered', 1)
            self.courses_by_year[year].append(course_code)

    def _build_lab_relationships(self):
        for course in self.courses_data:
            course_code = course['course_code']
            if course.get('has_lab'):
                lab_code = course.get('lab_course_code')
                if lab_code:
                    self.theory_to_lab[course_code] = lab_code
            if course.get('is_lab'):
                theory_code = course.get('theory_course_code')
                if theory_code:
                    self.lab_to_theory[course_code] = theory_code

    def _build_metadata_maps(self):
        for course in self.courses_data:
            course_code = course['course_code']
            self.difficulty_map[course_code]  = course.get('difficulty', 50)
            self.pass_rate_map[course_code]   = course.get('pass_rate', 0.8)
            self.credit_map[course_code]      = course.get('credits', 3)

    def _detect_slot_conflicts(self):
        for slot, courses in self.slot_to_courses.items():
            self.slot_conflicts[slot] = set(courses)

    # ============================================================================
    # COURSE QUERY METHODS
    # ============================================================================

    def get_course_by_code(self, course_code: str) -> Optional[Dict]:
        return self.course_code_dict.get(course_code)

    def get_course_by_id(self, course_id: int) -> Optional[Dict]:
        return self.course_id_dict.get(course_id)

    def get_all_course_codes(self) -> List[str]:
        return list(self.course_code_dict.keys())

    def get_all_course_ids(self) -> List[int]:
        return list(self.course_id_dict.keys())

    def get_course_id(self, course_code: str) -> Optional[int]:
        return self.course_code_to_id.get(course_code)

    def get_course_code(self, course_id: int) -> Optional[str]:
        return self.course_id_to_code.get(course_id)

    # ============================================================================
    # PREREQUISITE & DEPENDENCY METHODS
    # ============================================================================

    def get_prerequisites(self, course_code: str) -> List[str]:
        return self.course_prereqs.get(course_code, [])

    def get_unlocked_courses(self, course_code: str) -> List[str]:
        return self.course_unlocks.get(course_code, [])

    def has_prerequisites_met(self, course_code: str, completed_courses: Set[str]) -> bool:
        return all(p in completed_courses for p in self.get_prerequisites(course_code))

    def get_all_prerequisites_recursive(self, course_code: str) -> Set[str]:
        all_prereqs: Set[str] = set()
        to_process = [course_code]
        while to_process:
            current = to_process.pop()
            for prereq in self.get_prerequisites(current):
                if prereq not in all_prereqs:
                    all_prereqs.add(prereq)
                    to_process.append(prereq)
        return all_prereqs

    # ============================================================================
    # CATEGORY & TYPE METHODS
    # ============================================================================

    def get_courses_by_type(self, course_type: str) -> List[str]:
        return self.courses_by_type.get(course_type, [])

    def get_mandatory_courses(self) -> List[str]:
        return self.mandatory_courses

    def get_elective_courses(self) -> List[str]:
        return self.elective_courses

    def is_mandatory(self, course_code: str) -> bool:
        course = self.get_course_by_code(course_code)
        return course.get('is_mandatory', False) if course else False

    def is_elective(self, course_code: str) -> bool:
        return not self.is_mandatory(course_code)

    # ============================================================================
    # SLOT & SCHEDULING METHODS
    # ============================================================================

    def get_course_slots(self, course_code: str) -> List[str]:
        return self.course_to_slots.get(course_code, [])

    def get_courses_in_slot(self, slot: str) -> List[str]:
        return self.slot_to_courses.get(slot, [])

    def do_slots_conflict(self, slot1: str, slot2: str) -> bool:
        """
        In VIT FFCS, two slots conflict only when they are identical.
        Special administrative slots never conflict with anything.
        """
        if not slot1 or not slot2:
            return False
        special_slots = {
            'NGCR', 'SS1', 'SS2', 'SS3', 'SS4',
            'PRJ', 'INT', 'INT-FULL',
            'CAP1', 'CAP2', 'OE1', 'OE2', 'OE3', 'OE4',
        }
        if slot1 in special_slots or slot2 in special_slots:
            return False
        return slot1 == slot2

    def get_conflicting_courses(self, course_code: str, semester_courses: List[str]) -> List[str]:
        conflicting: List[str] = []
        course_slots = set(self.get_course_slots(course_code))
        for other in semester_courses:
            if other == course_code:
                continue
            for s1 in course_slots:
                for s2 in self.get_course_slots(other):
                    if self.do_slots_conflict(s1, s2):
                        conflicting.append(other)
                        break
        return conflicting

    def can_take_together(self, course1: str, course2: str) -> bool:
        """
        Return True if course1 and course2 can coexist in the same semester
        without a guaranteed slot conflict.

        In VIT FFCS, each course's slots list represents the time slots it
        CAN be registered in (student picks exactly one). Two courses conflict
        only if their slot option sets share a common regular slot — because
        the student could end up forced into that slot for both.

        Conservative rule:
          - If the two courses share ANY common regular slot, they cannot be
            safely placed together. This is the safest assumption for a planner
            that does not model explicit slot selection variables.
          - Special slots (NGCR, SS*, PRJ, INT, CAP*, OE*) never conflict.
          - If either course has no slot data, assume no conflict.
        """
        special_slots = {
            'NGCR', 'SS1', 'SS2', 'SS3', 'SS4',
            'PRJ', 'INT', 'INT-FULL',
            'CAP1', 'CAP2', 'OE1', 'OE2', 'OE3', 'OE4',
        }
        slots1 = self.get_course_slots(course1)
        slots2 = self.get_course_slots(course2)

        if not slots1 or not slots2:
            return True   # no slot info → assume no conflict

        regular1 = set(s for s in slots1 if s not in special_slots)
        regular2 = set(s for s in slots2 if s not in special_slots)

        if not regular1 or not regular2:
            return True   # only special slots → never conflict

        # Conflict if they share any regular slot option
        return len(regular1 & regular2) == 0

    # ============================================================================
    # CREDIT & DIFFICULTY METHODS
    # ============================================================================

    def get_credits(self, course_code: str) -> int:
        return self.credit_map.get(course_code, 0)

    def get_difficulty(self, course_code: str) -> int:
        return self.difficulty_map.get(course_code, 50)

    def get_pass_rate(self, course_code: str) -> float:
        return self.pass_rate_map.get(course_code, 0.8)

    def calculate_total_credits(self, course_codes: List[str]) -> int:
        return sum(self.get_credits(c) for c in course_codes)

    def calculate_average_difficulty(self, course_codes: List[str]) -> float:
        if not course_codes:
            return 0.0
        return sum(self.get_difficulty(c) for c in course_codes) / len(course_codes)

    def calculate_semester_difficulty(self, course_codes: List[str]) -> float:
        if not course_codes:
            return 0.0
        total_diff = sum(self.get_difficulty(c) * self.get_credits(c) for c in course_codes)
        total_cr   = self.calculate_total_credits(course_codes)
        return total_diff / total_cr if total_cr > 0 else 0.0

    # ============================================================================
    # LAB RELATIONSHIP METHODS
    # ============================================================================

    def has_lab(self, course_code: str) -> bool:
        return course_code in self.theory_to_lab

    def get_lab_course(self, theory_code: str) -> Optional[str]:
        return self.theory_to_lab.get(theory_code)

    def get_theory_course(self, lab_code: str) -> Optional[str]:
        return self.lab_to_theory.get(lab_code)

    def must_take_together(self, course1: str, course2: str) -> bool:
        return (
            self.theory_to_lab.get(course1) == course2
            or self.theory_to_lab.get(course2) == course1
        )

    # ============================================================================
    # STUDENT-SPECIFIC METHODS
    # ============================================================================

    def get_eligible_courses(self, student: 'StudentProfile' = None) -> List[str]:
        if student is None:
            student = self.current_student
        if student is None:
            raise ValueError("No student loaded")

        completed = set(student.completed_courses)
        eligible: List[str] = []

        for course_code in self.get_all_course_codes():
            if course_code in completed:
                continue
            course = self.get_course_by_code(course_code)
            if course is None:
                continue
            year_ok = course.get('year_offered', 1) <= student.current_year
            if self.has_prerequisites_met(course_code, completed) and year_ok:
                eligible.append(course_code)

        for fc in student.failed_courses:
            if fc not in eligible:
                eligible.append(fc)

        return eligible

    def get_remaining_mandatory_courses(self, student: 'StudentProfile' = None) -> List[str]:
        if student is None:
            student = self.current_student
        completed = set(student.completed_courses)
        return [c for c in self.mandatory_courses if c not in completed]

    def get_remaining_credits_by_type(self, student: 'StudentProfile' = None) -> Dict[str, int]:
        if student is None:
            student = self.current_student

        completed = set(student.completed_courses)
        earned_credits: Dict[str, int] = defaultdict(int)

        for course_code in completed:
            course = self.get_course_by_code(course_code)
            if course:
                earned_credits[course['course_type']] += self.get_credits(course_code)

        remaining: Dict[str, int] = {}
        for category, requirements in self.credit_requirements.items():
            required = requirements.get('required', 0)
            remaining[category] = max(0, required - earned_credits.get(category, 0))

        return remaining

    def get_courses_matching_interests(
        self,
        student: 'StudentProfile' = None,
        min_rating: int = 4,
    ) -> List[str]:
        if student is None:
            student = self.current_student

        matching: List[str] = []
        high_interest_tags = student.get_high_interest_areas(min_rating)

        for course_code in self.get_all_course_codes():
            course = self.get_course_by_code(course_code)
            if course:
                course_name_lower = course['course_name'].lower()
                for tag in high_interest_tags:
                    if tag.lower() in course_name_lower:
                        matching.append(course_code)
                        break

        return matching

    # ============================================================================
    # VALIDATION METHODS
    # ============================================================================

    def validate_semester_plan(self, course_codes: List[str]) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        total_credits = self.calculate_total_credits(course_codes)
        if total_credits < 16:
            errors.append(f"Too few credits: {total_credits} (minimum 16)")
        if total_credits > 27:
            errors.append(f"Too many credits: {total_credits} (maximum 27)")

        for i, course1 in enumerate(course_codes):
            for course2 in course_codes[i + 1:]:
                if not self.can_take_together(course1, course2):
                    errors.append(f"Slot conflict: {course1} and {course2}")

        for course in course_codes:
            if self.has_lab(course):
                lab = self.get_lab_course(course)
                if lab not in course_codes:
                    errors.append(f"Missing lab companion: {course} requires {lab}")

        return len(errors) == 0, errors

    def validate_full_path(
        self,
        semesters: List[List[str]],
        student: 'StudentProfile' = None,
    ) -> Tuple[bool, List[str]]:
        if student is None:
            student = self.current_student

        errors: List[str] = []
        completed = set(student.completed_courses)

        for sem_idx, semester_courses in enumerate(semesters, start=student.current_semester):
            _, sem_errors = self.validate_semester_plan(semester_courses)
            for err in sem_errors:
                errors.append(f"Semester {sem_idx}: {err}")

            for course in semester_courses:
                if not self.has_prerequisites_met(course, completed):
                    missing = [p for p in self.get_prerequisites(course) if p not in completed]
                    errors.append(
                        f"Semester {sem_idx}: {course} missing prerequisites: {missing}"
                    )

            completed.update(semester_courses)

        remaining_mandatory = [c for c in self.mandatory_courses if c not in completed]
        if remaining_mandatory:
            errors.append(f"Missing mandatory courses: {remaining_mandatory}")

        return len(errors) == 0, errors

    # ============================================================================
    # STATISTICS & REPORTING
    # ============================================================================

    def get_statistics(self) -> Dict:
        return {
            'total_courses'    : len(self.courses_data),
            'mandatory_courses': len(self.mandatory_courses),
            'elective_courses' : len(self.elective_courses),
            'unique_slots'     : len(self.slot_to_courses),
            'course_types'     : {ct: len(cs) for ct, cs in self.courses_by_type.items()},
            'avg_difficulty'   : (
                sum(self.difficulty_map.values()) / len(self.difficulty_map)
                if self.difficulty_map else 0
            ),
            'avg_credits'      : (
                sum(self.credit_map.values()) / len(self.credit_map)
                if self.credit_map else 0
            ),
        }

    def export_debug_info(self, output_file: str = 'debug_data.json') -> None:
        debug_data = {
            'courses'     : self.courses_data,
            'prerequisites': dict(self.course_prereqs),
            'unlocks'     : dict(self.course_unlocks),
            'slots'       : dict(self.slot_to_courses),
            'statistics'  : self.get_statistics(),
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, indent=2)
        print(f"✅ Debug data exported to {output_file}")


# ============================================================================
# STUDENT DATA STRUCTURES
# ============================================================================

@dataclass
class CourseRecord:
    course_code   : str
    course_name   : str
    credits       : float
    grade         : str
    semester_taken: int
    grade_points  : int  = 0
    credit_points : int  = 0
    is_failed     : bool = False
    note          : Optional[str] = None

    def __post_init__(self):
        g = self.grade.strip().upper()
        if g not in VALID_GRADES:
            raise ValueError(
                f"Invalid grade '{self.grade}' for {self.course_code}. "
                f"Accepted values: {sorted(VALID_GRADES)}"
            )
        self.grade        = g
        self.grade_points = GRADE_POINTS_MAP[g]
        self.credit_points = int(self.grade_points * self.credits)
        self.is_failed    = (g == 'F')

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StudentProfile:
    student_id : str
    name       : str
    email      : str
    program    : str
    current_year    : int
    current_semester: int
    cgpa            : float
    completed_courses: List[str]
    failed_courses   : List[str]
    course_records   : List[CourseRecord]
    interest_areas: List[str]
    preferred_credits_per_semester: int
    max_credits_per_semester      : int
    preferred_difficulty_level    : str
    has_backlogs  : bool
    avoid_courses : List[str]
    past_performance_trend: str
    risk_tolerance     : str
    workload_preference: str
    difficulty_preference: str
    prioritize_gpa     : bool
    prioritize_learning: bool
    semester_summary: List[Dict] = field(default_factory=list)

    def recalculate_cgpa(self) -> float:
        _, cgpa = compute_academic_performance(self.course_records)
        self.cgpa = cgpa
        return cgpa

    def get_sgpa_by_semester(self) -> Dict[int, float]:
        sgpa_map, _ = compute_academic_performance(self.course_records)
        return sgpa_map

    def get_grade_points_for_grade(self, grade: str) -> int:
        g = grade.strip().upper()
        if g not in GRADE_POINTS_MAP:
            raise ValueError(f"Unrecognised grade: '{grade}'")
        return GRADE_POINTS_MAP[g]

    def get_remaining_semesters(self) -> int:
        return max(0, 8 - self.current_semester + 1)

    def get_high_interest_areas(self, min_rating: int = 4) -> List[str]:
        if isinstance(self.interest_areas, dict):
            return [area for area, rating in self.interest_areas.items() if rating >= min_rating]
        return list(self.interest_areas)

    def get_completed_set(self) -> Set[str]:
        return set(self.completed_courses)

    def has_completed(self, course_code: str) -> bool:
        return course_code in self.completed_courses

    def has_failed_course(self, course_code: str) -> bool:
        return course_code in self.failed_courses

    def has_failed(self, course_code: str) -> bool:
        return self.has_failed_course(course_code)

    def get_grade_for_course(self, course_code: str) -> Optional[str]:
        result = None
        for record in self.course_records:
            if record.course_code == course_code:
                result = record.grade
        return result

    def get_record_for_course(self, course_code: str) -> Optional['CourseRecord']:
        result = None
        for record in self.course_records:
            if record.course_code == course_code:
                result = record
        return result

    def get_all_records_for_course(self, course_code: str) -> List['CourseRecord']:
        return [r for r in self.course_records if r.course_code == course_code]

    def to_dict(self) -> Dict:
        data = asdict(self)
        data['course_records'] = [r.to_dict() for r in self.course_records]
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'StudentProfile':
        _COURSE_RECORD_FIELDS = {
            'course_code', 'course_name', 'credits', 'grade',
            'semester_taken', 'grade_points', 'credit_points',
            'is_failed', 'note',
        }
        raw_records = data.get('course_records', [])
        course_records: List[CourseRecord] = []
        for record in raw_records:
            filtered = {k: v for k, v in record.items() if k in _COURSE_RECORD_FIELDS}
            course_records.append(CourseRecord(**filtered))

        clean = dict(data)
        clean['course_records'] = course_records
        clean.setdefault('semester_summary', [])
        return cls(**clean)


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    loader = DataLoader()

    try:
        loader.load_course_data()
        print("\n" + "=" * 80)
        print("COURSE DATA LOADED SUCCESSFULLY")
        print("=" * 80)

        stats = loader.get_statistics()
        print(f"\n📊 Course Statistics:")
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"\n  {key}:")
                for k, v in value.items():
                    print(f"    - {k}: {v}")
            else:
                print(f"  - {key}: {value}")

        test_course = "BCSE202L"
        if loader.get_course_by_code(test_course):
            print(f"\n📚 Sample Course : {test_course}")
            print(f"  - Credits        : {loader.get_credits(test_course)}")
            print(f"  - Difficulty     : {loader.get_difficulty(test_course)}")
            print(f"  - Prerequisites  : {loader.get_prerequisites(test_course)}")
            print(f"  - Unlocks        : {loader.get_unlocked_courses(test_course)}")
            print(f"  - Slots          : {loader.get_course_slots(test_course)}")

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
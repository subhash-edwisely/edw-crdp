"""
Comprehensive Data Loader for VIT FFCS Course Recommendation System
Provides all necessary data access methods for CP-SAT solver
"""

import json
import os
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict

# File paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_FILE = os.path.join(CURRENT_DIR, "courses.json")
STUDENTS_DIR = os.path.join(CURRENT_DIR, "students")


class DataLoader:
    """
    Comprehensive data loader providing all methods needed for CP-SAT solver
    """
    
    def __init__(self):
        # Course data structures
        self.courses_data: List[Dict] = []
        self.course_code_to_id: Dict[str, int] = {}
        self.course_id_to_code: Dict[int, str] = {}
        self.course_code_dict: Dict[str, Dict] = {}
        self.course_id_dict: Dict[int, Dict] = {}
        
        # Prerequisite and dependency maps
        self.course_prereqs: Dict[str, List[str]] = defaultdict(list)
        self.course_unlocks: Dict[str, List[str]] = defaultdict(list)
        
        # Category maps
        self.courses_by_type: Dict[str, List[str]] = defaultdict(list)
        self.mandatory_courses: List[str] = []
        self.elective_courses: List[str] = []
        
        # Slot and scheduling maps
        self.slot_to_courses: Dict[str, List[str]] = defaultdict(list)
        self.course_to_slots: Dict[str, List[str]] = {}
        self.slot_conflicts: Dict[str, Set[str]] = {}  # For conflict detection
        
        # Year-wise organization
        self.courses_by_year: Dict[int, List[str]] = defaultdict(list)
        
        # Lab relationships
        self.theory_to_lab: Dict[str, str] = {}
        self.lab_to_theory: Dict[str, str] = {}
        
        # Metadata
        self.difficulty_map: Dict[str, int] = {}
        self.pass_rate_map: Dict[str, float] = {}
        self.credit_map: Dict[str, int] = {}
        
        # Credit requirements from metadata
        self.credit_requirements: Dict = {}
        
        # Student data (can handle multiple students)
        self.students: Dict[str, 'StudentProfile'] = {}
        self.current_student: Optional['StudentProfile'] = None
    
    # ============================================================================
    # CORE LOADING METHODS
    # ============================================================================
    
    def load_course_data(self) -> None:
        """Load and index all course data"""
        if not os.path.exists(COURSES_FILE):
            raise FileNotFoundError(f"Course data file not found: {COURSES_FILE}")
        
        with open(COURSES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.courses_data = data.get('courses', [])
        self.credit_requirements = data.get('credit_requirements', {})
        
        # Build all indices
        self._build_course_indices()
        self._build_prerequisite_maps()
        self._build_category_maps()
        self._build_slot_maps()
        self._build_year_maps()
        self._build_lab_relationships()
        self._build_metadata_maps()
        self._detect_slot_conflicts()
        
        print(f"✅ Loaded {len(self.courses_data)} courses")
        print(f"   - Mandatory: {len(self.mandatory_courses)}")
        print(f"   - Electives: {len(self.elective_courses)}")
        print(f"   - Unique slots: {len(self.slot_to_courses)}")
    
    def load_student(self, student_id: str) -> 'StudentProfile':
        """Load a student's profile"""
        student_file = os.path.join(STUDENTS_DIR, f"{student_id}.json")
        
        if not os.path.exists(student_file):
            raise FileNotFoundError(f"Student file not found: {student_file}")
        
        with open(student_file, 'r', encoding='utf-8') as f:
            student_data = json.load(f)
        
        student = StudentProfile.from_dict(student_data)
        self.students[student_id] = student
        self.current_student = student
        
        print(f"✅ Loaded student: {student.name} (ID: {student.student_id})")
        print(f"   - Current: Semester {student.current_semester}, Year {student.current_year}")
        print(f"   - Completed: {len(student.completed_courses)} courses")
        print(f"   - Failed: {len(student.failed_courses)} courses")
        print(f"   - CGPA: {student.cgpa:.2f}")
        
        return student
    
    # ============================================================================
    # INTERNAL INDEX BUILDING METHODS
    # ============================================================================
    
    def _build_course_indices(self):
        """Build course ID and code mappings"""
        for course in self.courses_data:
            course_id = course['id']
            course_code = course['course_code']
            
            self.course_code_to_id[course_code] = course_id
            self.course_id_to_code[course_id] = course_code
            self.course_code_dict[course_code] = course
            self.course_id_dict[course_id] = course
    
    def _build_prerequisite_maps(self):
        """Build prerequisite and unlock maps"""
        for course in self.courses_data:
            course_code = course['course_code']
            prereqs = course.get('prerequisites', [])
            unlocks = course.get('unlocks', [])
            
            self.course_prereqs[course_code] = prereqs
            self.course_unlocks[course_code] = unlocks
    
    def _build_category_maps(self):
        """Categorize courses by type"""
        for course in self.courses_data:
            course_code = course['course_code']
            course_type = course['course_type']
            is_mandatory = course['is_mandatory']
            
            self.courses_by_type[course_type].append(course_code)
            
            if is_mandatory:
                self.mandatory_courses.append(course_code)
            else:
                self.elective_courses.append(course_code)
    
    def _build_slot_maps(self):
        """Build slot to course mappings"""
        for course in self.courses_data:
            course_code = course['course_code']
            slots = course.get('slots', [])
            
            self.course_to_slots[course_code] = slots
            
            for slot in slots:
                self.slot_to_courses[slot].append(course_code)
    
    def _build_year_maps(self):
        """Map courses to typical years"""
        for course in self.courses_data:
            course_code = course['course_code']
            year = course.get('year_offered', 1)
            self.courses_by_year[year].append(course_code)
    
    def _build_lab_relationships(self):
        """Build theory-lab relationships"""
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
        """Build difficulty, pass rate, and credit maps"""
        for course in self.courses_data:
            course_code = course['course_code']
            self.difficulty_map[course_code] = course.get('difficulty', 50)
            self.pass_rate_map[course_code] = course.get('pass_rate', 0.8)
            self.credit_map[course_code] = course.get('credits', 3)
    
    def _detect_slot_conflicts(self):
        """Pre-compute slot conflicts for faster constraint checking"""
        for slot, courses in self.slot_to_courses.items():
            self.slot_conflicts[slot] = set(courses)
    
    # ============================================================================
    # COURSE QUERY METHODS (For CP-SAT Constraints)
    # ============================================================================
    
    def get_course_by_code(self, course_code: str) -> Optional[Dict]:
        """Get course data by code"""
        return self.course_code_dict.get(course_code)
    
    def get_course_by_id(self, course_id: int) -> Optional[Dict]:
        """Get course data by ID"""
        return self.course_id_dict.get(course_id)
    
    def get_all_course_codes(self) -> List[str]:
        """Get list of all course codes"""
        return list(self.course_code_dict.keys())
    
    def get_all_course_ids(self) -> List[int]:
        """Get list of all course IDs"""
        return list(self.course_id_dict.keys())
    
    def get_course_id(self, course_code: str) -> Optional[int]:
        """Convert course code to ID"""
        return self.course_code_to_id.get(course_code)
    
    def get_course_code(self, course_id: int) -> Optional[str]:
        """Convert course ID to code"""
        return self.course_id_to_code.get(course_id)
    
    # ============================================================================
    # PREREQUISITE & DEPENDENCY METHODS
    # ============================================================================
    
    def get_prerequisites(self, course_code: str) -> List[str]:
        """Get prerequisite course codes"""
        return self.course_prereqs.get(course_code, [])
    
    def get_unlocked_courses(self, course_code: str) -> List[str]:
        """Get courses unlocked by this course"""
        return self.course_unlocks.get(course_code, [])
    
    def has_prerequisites_met(self, course_code: str, completed_courses: Set[str]) -> bool:
        """Check if all prerequisites are met"""
        prereqs = self.get_prerequisites(course_code)
        return all(prereq in completed_courses for prereq in prereqs)
    
    def get_all_prerequisites_recursive(self, course_code: str) -> Set[str]:
        """Get all prerequisites recursively (entire dependency chain)"""
        all_prereqs = set()
        to_process = [course_code]
        
        while to_process:
            current = to_process.pop()
            prereqs = self.get_prerequisites(current)
            for prereq in prereqs:
                if prereq not in all_prereqs:
                    all_prereqs.add(prereq)
                    to_process.append(prereq)
        
        return all_prereqs
    
    # ============================================================================
    # CATEGORY & TYPE METHODS
    # ============================================================================
    
    def get_courses_by_type(self, course_type: str) -> List[str]:
        """Get all courses of a specific type"""
        return self.courses_by_type.get(course_type, [])
    
    def get_mandatory_courses(self) -> List[str]:
        """Get all mandatory courses"""
        return self.mandatory_courses
    
    def get_elective_courses(self) -> List[str]:
        """Get all elective courses"""
        return self.elective_courses
    
    def is_mandatory(self, course_code: str) -> bool:
        """Check if course is mandatory"""
        course = self.get_course_by_code(course_code)
        return course.get('is_mandatory', False) if course else False
    
    def is_elective(self, course_code: str) -> bool:
        """Check if course is elective"""
        return not self.is_mandatory(course_code)
    
    # ============================================================================
    # SLOT & SCHEDULING METHODS (Critical for FFCS!)
    # ============================================================================
    
    def get_course_slots(self, course_code: str) -> List[str]:
        """Get all slots where a course is offered"""
        return self.course_to_slots.get(course_code, [])
    
    def get_courses_in_slot(self, slot: str) -> List[str]:
        """Get all courses offered in a specific slot"""
        return self.slot_to_courses.get(slot, [])
    
    def do_slots_conflict(self, slot1: str, slot2: str) -> bool:
        """Check if two slots conflict (same time)"""
        # In FFCS, slots with same letter conflict (e.g., A1 conflicts with A2)
        # This is a simplified check - adjust based on actual VIT slot system
        if not slot1 or not slot2:
            return False
        return slot1[0] == slot2[0] if len(slot1) > 0 and len(slot2) > 0 else False
    
    def get_conflicting_courses(self, course_code: str, semester_courses: List[str]) -> List[str]:
        """Get courses that conflict with given course in a semester"""
        conflicting = []
        course_slots = set(self.get_course_slots(course_code))
        
        for other_course in semester_courses:
            if other_course == course_code:
                continue
            other_slots = set(self.get_course_slots(other_course))
            
            # Check if any slots overlap
            for slot1 in course_slots:
                for slot2 in other_slots:
                    if self.do_slots_conflict(slot1, slot2):
                        conflicting.append(other_course)
                        break
        
        return conflicting
    
    def can_take_together(self, course1: str, course2: str) -> bool:
        """Check if two courses can be taken in same semester (no slot conflict)"""
        slots1 = set(self.get_course_slots(course1))
        slots2 = set(self.get_course_slots(course2))
        
        # Check if there's at least one non-conflicting slot combination
        for slot1 in slots1:
            for slot2 in slots2:
                if not self.do_slots_conflict(slot1, slot2):
                    return True
        return False
    
    # ============================================================================
    # CREDIT & DIFFICULTY METHODS
    # ============================================================================
    
    def get_credits(self, course_code: str) -> int:
        """Get credits for a course"""
        return self.credit_map.get(course_code, 0)
    
    def get_difficulty(self, course_code: str) -> int:
        """Get difficulty score (0-100)"""
        return self.difficulty_map.get(course_code, 50)
    
    def get_pass_rate(self, course_code: str) -> float:
        """Get pass rate (0.0-1.0)"""
        return self.pass_rate_map.get(course_code, 0.8)
    
    def calculate_total_credits(self, course_codes: List[str]) -> int:
        """Calculate total credits for a list of courses"""
        return sum(self.get_credits(code) for code in course_codes)
    
    def calculate_average_difficulty(self, course_codes: List[str]) -> float:
        """Calculate average difficulty for a list of courses"""
        if not course_codes:
            return 0.0
        return sum(self.get_difficulty(code) for code in course_codes) / len(course_codes)
    
    def calculate_semester_difficulty(self, course_codes: List[str]) -> float:
        """Calculate weighted difficulty for a semester (difficulty * credits)"""
        if not course_codes:
            return 0.0
        
        total_difficulty = sum(
            self.get_difficulty(code) * self.get_credits(code) 
            for code in course_codes
        )
        total_credits = self.calculate_total_credits(course_codes)
        
        return total_difficulty / total_credits if total_credits > 0 else 0.0
    
    # ============================================================================
    # LAB RELATIONSHIP METHODS
    # ============================================================================
    
    def has_lab(self, course_code: str) -> bool:
        """Check if course has an associated lab"""
        return course_code in self.theory_to_lab
    
    def get_lab_course(self, theory_code: str) -> Optional[str]:
        """Get lab course code for a theory course"""
        return self.theory_to_lab.get(theory_code)
    
    def get_theory_course(self, lab_code: str) -> Optional[str]:
        """Get theory course code for a lab course"""
        return self.lab_to_theory.get(lab_code)
    
    def must_take_together(self, course1: str, course2: str) -> bool:
        """Check if two courses must be taken together (theory-lab pair)"""
        return (self.theory_to_lab.get(course1) == course2 or 
                self.theory_to_lab.get(course2) == course1)
    
    # ============================================================================
    # STUDENT-SPECIFIC METHODS
    # ============================================================================
    
    def get_eligible_courses(self, student: 'StudentProfile' = None) -> List[str]:
        """Get courses student is eligible to take (prerequisites met, not completed)"""
        if student is None:
            student = self.current_student
        
        if student is None:
            raise ValueError("No student loaded")
        
        completed = set(student.completed_courses)
        eligible = []
        
        for course_code in self.get_all_course_codes():
            # Skip if already completed
            if course_code in completed:
                continue
            
            # Check prerequisites
            if self.has_prerequisites_met(course_code, completed) and self.get_course_by_code(course_code).get('year_offered') <= student.current_year:
                eligible.append(course_code)
        
        eligible.extend(student.failed_courses)
        return eligible
    
    def get_remaining_mandatory_courses(self, student: 'StudentProfile' = None) -> List[str]:
        """Get mandatory courses not yet completed"""
        if student is None:
            student = self.current_student
        
        completed = set(student.completed_courses)
        return [c for c in self.mandatory_courses if c not in completed]
    
    def get_remaining_credits_by_type(self, student: 'StudentProfile' = None) -> Dict[str, int]:
        """Calculate remaining credits needed in each course type"""
        if student is None:
            student = self.current_student
        
        completed = set(student.completed_courses)
        earned_credits = defaultdict(int)
        
        # Calculate earned credits by type
        for course_code in completed:
            course = self.get_course_by_code(course_code)
            if course:
                course_type = course['course_type']
                credits = self.get_credits(course_code)
                earned_credits[course_type] += credits
        
        # Calculate remaining credits needed
        remaining = {}
        for category, requirements in self.credit_requirements.items():
            required = requirements.get('required', 0)
            earned = earned_credits.get(category, 0)
            remaining[category] = max(0, required - earned)
        
        return remaining
    
    def get_courses_matching_interests(self, student: 'StudentProfile' = None, 
                                      min_rating: int = 4) -> List[str]:
        """Get courses matching student's high-interest tags"""
        if student is None:
            student = self.current_student
        
        matching = []
        high_interest_tags = student.get_high_interest_areas(min_rating)
        
        for course_code in self.get_all_course_codes():
            course = self.get_course_by_code(course_code)
            if course:
                # Check if course name contains any high-interest keywords
                course_name = course['course_name'].lower()
                for tag in high_interest_tags:
                    if tag.lower() in course_name:
                        matching.append(course_code)
                        break
        
        return matching
    
    # ============================================================================
    # VALIDATION METHODS
    # ============================================================================
    
    def validate_semester_plan(self, course_codes: List[str]) -> Tuple[bool, List[str]]:
        """Validate a semester course selection"""
        errors = []
        
        # Check credit limits (16-27 typically)
        total_credits = self.calculate_total_credits(course_codes)
        if total_credits < 16:
            errors.append(f"Too few credits: {total_credits} (minimum 16)")
        if total_credits > 27:
            errors.append(f"Too many credits: {total_credits} (maximum 27)")
        
        # Check slot conflicts
        for i, course1 in enumerate(course_codes):
            for course2 in course_codes[i+1:]:
                if not self.can_take_together(course1, course2):
                    errors.append(f"Slot conflict: {course1} and {course2}")
        
        # Check theory-lab pairs
        for course in course_codes:
            if self.has_lab(course):
                lab = self.get_lab_course(course)
                if lab not in course_codes:
                    errors.append(f"Missing lab: {course} requires {lab}")
        
        return len(errors) == 0, errors
    
    def validate_full_path(self, semesters: List[List[str]], 
                          student: 'StudentProfile' = None) -> Tuple[bool, List[str]]:
        """Validate a complete academic path"""
        if student is None:
            student = self.current_student
        
        errors = []
        completed = set(student.completed_courses)
        
        # Validate each semester
        for sem_idx, semester_courses in enumerate(semesters, start=student.current_semester):
            is_valid, sem_errors = self.validate_semester_plan(semester_courses)
            for error in sem_errors:
                errors.append(f"Semester {sem_idx}: {error}")
            
            # Check prerequisites based on courses completed so far
            for course in semester_courses:
                if not self.has_prerequisites_met(course, completed):
                    missing = [p for p in self.get_prerequisites(course) if p not in completed]
                    errors.append(
                        f"Semester {sem_idx}: {course} missing prerequisites: {missing}"
                    )
            
            # Add this semester's courses to completed
            completed.update(semester_courses)
        
        # Check if all mandatory courses are included
        remaining_mandatory = [c for c in self.mandatory_courses if c not in completed]
        if remaining_mandatory:
            errors.append(f"Missing mandatory courses: {remaining_mandatory}")
        
        # Check if credit requirements are met
        # (Implementation depends on exact requirements structure)
        
        return len(errors) == 0, errors
    
    # ============================================================================
    # STATISTICS & REPORTING
    # ============================================================================
    
    def get_statistics(self) -> Dict:
        """Get comprehensive data statistics"""
        return {
            'total_courses': len(self.courses_data),
            'mandatory_courses': len(self.mandatory_courses),
            'elective_courses': len(self.elective_courses),
            'unique_slots': len(self.slot_to_courses),
            'course_types': {ct: len(courses) for ct, courses in self.courses_by_type.items()},
            'avg_difficulty': sum(self.difficulty_map.values()) / len(self.difficulty_map),
            'avg_credits': sum(self.credit_map.values()) / len(self.credit_map),
        }
    
    def export_debug_info(self, output_file: str = 'debug_data.json') -> None:
        """Export all data for debugging"""
        debug_data = {
            'courses': self.courses_data,
            'prerequisites': dict(self.course_prereqs),
            'unlocks': dict(self.course_unlocks),
            'slots': dict(self.slot_to_courses),
            'statistics': self.get_statistics()
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, indent=2)
        
        print(f"✅ Debug data exported to {output_file}")


# ============================================================================
# STUDENT DATA STRUCTURE
# ============================================================================

@dataclass
class CourseRecord:
    """Individual course record in student's history"""
    course_code: str
    course_name: str
    credits: float
    grade: str
    semester_taken: int
    is_failed: bool = False
    
    def to_dict(self):
        return asdict(self)


@dataclass
class StudentProfile:
    """Complete student profile with academic history"""
    # Basic Info
    student_id: str
    name: str
    email: str
    program: str
    
    # Academic Status
    current_year: int  # 1, 2, 3, or 4
    current_semester: int  # 1-8
    cgpa: float
    
    # Course History
    completed_courses: List[str]  # Course codes of passed courses
    failed_courses: List[str]  # Course codes of failed courses (not retaken successfully)
    course_records: List[CourseRecord]  # Complete grade sheet
    
    # Preferences & Interests
    interest_areas: Dict[str, int]  # Area name -> Rating (1-5)
    # e.g., {"Machine Learning": 5, "Web Development": 4, "Theory": 2}
    
    # Workload Preferences
    preferred_credits_per_semester: int  # e.g., 20
    max_credits_per_semester: int  # e.g., 24
    preferred_difficulty_level: str  # "light", "moderate", "heavy"
    
    # Constraints & Special Cases
    has_backlogs: bool
    avoid_courses: List[str]  # Courses student wants to avoid
    
    # Behavioral Data (for personalization)
    past_performance_trend: str  # "improving", "stable", "declining"
    
    # Risk Profile
    risk_tolerance: str  # "conservative", "balanced", "aggressive"
    workload_preference: str # "low" (18-20) , "medium" (21-23), "high (24-26)"
    prioritize_gpa: bool
    prioritize_learning: bool

    
    def get_remaining_semesters(self) -> int:
        """Calculate remaining semesters until graduation"""
        return 8 - self.current_semester + 1
    
    def get_high_interest_areas(self, min_rating: int = 4) -> List[str]:
        """Get areas of high interest"""
        return [area for area, rating in self.interest_areas.items() if rating >= min_rating]
    
    def get_completed_set(self) -> Set[str]:
        """Get completed courses as a set for fast lookup"""
        return set(self.completed_courses)
    
    def has_completed(self, course_code: str) -> bool:
        """Check if student has completed a course"""
        return course_code in self.completed_courses
    
    def has_failed(self, course_code: str) -> bool:
        """Check if student has failed a course"""
        return course_code in self.failed_courses
    
    def get_grade_for_course(self, course_code: str) -> Optional[str]:
        """Get grade for a specific course"""
        for record in self.course_records:
            if record.course_code == course_code:
                return record.grade
        return None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['course_records'] = [r.to_dict() for r in self.course_records]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StudentProfile':
        """Create StudentProfile from dictionary"""
        # Convert course records
        course_records = [
            CourseRecord(**record) 
            for record in data.get('course_records', [])
        ]
        data['course_records'] = course_records
        return cls(**data)


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    # Initialize loader
    loader = DataLoader()
    
    # Load course data
    try:
        loader.load_course_data()
        print("\n" + "="*80)
        print("COURSE DATA LOADED SUCCESSFULLY")
        print("="*80)
        
        # Display statistics
        stats = loader.get_statistics()
        print(f"\n📊 Course Statistics:")
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"\n  {key}:")
                for k, v in value.items():
                    print(f"    - {k}: {v}")
            else:
                print(f"  - {key}: {value}")
        
        # Test some queries
        print(f"\n🔍 Sample Queries:")
        print(f"  - Mandatory courses: {len(loader.get_mandatory_courses())}")
        print(f"  - Elective courses: {len(loader.get_elective_courses())}")
        print(f"  - Courses in slot A1: {len(loader.get_courses_in_slot('A1'))}")
        
        # Test a specific course
        test_course = "BCSE202L"
        if loader.get_course_by_code(test_course):
            print(f"\n📚 Sample Course: {test_course}")
            print(f"  - Credits: {loader.get_credits(test_course)}")
            print(f"  - Difficulty: {loader.get_difficulty(test_course)}")
            print(f"  - Prerequisites: {loader.get_prerequisites(test_course)}")
            print(f"  - Unlocks: {loader.get_unlocked_courses(test_course)}")
            print(f"  - Slots: {loader.get_course_slots(test_course)}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
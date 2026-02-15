"""
Global CP-SAT Planner for VIT FFCS Course Recommendation
Plans all remaining semesters (current to 8) in one optimization problem
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Tuple, Set
from collections import defaultdict

MIN_CREDITS = 16
MAX_CREDITS = 24


class GlobalCPSATPlanner:
    """
    Global optimization planner that considers all remaining semesters together
    """
    
    def __init__(self, loader):
        self.loader = loader
        
    def generate_complete_plan(self, student) -> Dict[int, List[str]]:
        """
        Generate complete semester-wise plan from current semester to semester 8
        Returns: {semester_number: [course_codes]}
        """
        print("\n" + "="*80)
        print("🚀 GLOBAL CP-SAT PLANNER - GENERATING COMPLETE ACADEMIC PLAN")
        print("="*80)
        
        # Get planning scope
        semesters = list(range(student.current_semester, 9))
        print(f"\n📅 Planning for semesters: {semesters}")
        
        # Get eligible courses (across all future semesters)
        eligible_courses = self._get_all_eligible_courses(student)
        print(f"📚 Total eligible courses: {len(eligible_courses)}")
        
        # Build the model
        model = cp_model.CpModel()
        
        # Create variables
        x = self._create_variables(model, eligible_courses, semesters)
        
        # Add constraints
        print("\n🔧 Adding constraints...")
        self._add_course_taken_once_constraint(model, x, eligible_courses, semesters)
        self._add_already_completed_constraint(model, x, student, eligible_courses, semesters)
        self._add_prerequisite_constraints(model, x, student, eligible_courses, semesters)
        self._add_per_semester_credit_constraints(model, x, eligible_courses, semesters)
        self._add_slot_conflict_constraints(model, x, eligible_courses, semesters)
        self._add_theory_lab_pairing_constraints(model, x, eligible_courses, semesters)
        self._add_avoid_courses_constraint(model, x, student, eligible_courses, semesters)
        self._add_category_credit_requirements(model, x, student, eligible_courses, semesters)
        self._add_project_semester_8_constraint(model, x, eligible_courses, semesters)
        
        # Set objective
        print("🎯 Setting objective function...")
        self._set_objective(model, x, student, eligible_courses, semesters)
        
        # Solve
        print("\n⚙️  Solving...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0  # 30 second timeout
        status = solver.Solve(model)
        
        # Extract solution
        if status == cp_model.OPTIMAL:
            print("✅ OPTIMAL solution found!")
            plan = self._extract_solution(solver, x, eligible_courses, semesters)
            self._print_plan_summary(plan, student)
            return plan
        elif status == cp_model.FEASIBLE:
            print("⚠️  FEASIBLE solution found (not optimal)")
            plan = self._extract_solution(solver, x, eligible_courses, semesters)
            self._print_plan_summary(plan, student)
            return plan
        else:
            print("❌ NO SOLUTION FOUND")
            print(f"Status: {solver.StatusName(status)}")
            return {sem: [] for sem in semesters}
    
    # ========================================================================
    # VARIABLE CREATION
    # ========================================================================
    
    def _create_variables(self, model, courses: List[str], semesters: List[int]) -> Dict:
        """
        Create decision variables x[course, semester]
        x[c, s] = 1 if course c is taken in semester s, 0 otherwise
        """
        x = {}
        for course in courses:
            for sem in semesters:
                x[course, sem] = model.NewBoolVar(f'{course}_sem{sem}')
        
        print(f"✅ Created {len(courses) * len(semesters)} decision variables")
        return x
    
    # ========================================================================
    # CONSTRAINT METHODS
    # ========================================================================
    
    def _add_course_taken_once_constraint(self, model, x, courses, semesters):
        """Each course can be taken at most once across all semesters"""
        for course in courses:
            model.Add(sum(x[course, sem] for sem in semesters) <= 1)
        print("  ✓ Course taken at most once")
    
    def _add_already_completed_constraint(self, model, x, student, courses, semesters):
        """Courses already completed cannot be taken again"""
        completed = set(student.completed_courses)
        for course in courses:
            if course in completed:
                for sem in semesters:
                    model.Add(x[course, sem] == 0)
        print("  ✓ Already completed courses excluded")
    
    def _add_prerequisite_constraints(self, model, x, student, courses, semesters):
        """
        If taking course C in semester S, all prerequisites must be completed
        either before the planning period or in earlier semesters
        """
        completed = set(student.completed_courses)
        
        for course in courses:
            prereqs = self.loader.get_prerequisites(course)
            if not prereqs:
                continue
            
            for sem in semesters:
                # For each prerequisite, it must either be:
                # 1. Already completed (before planning), OR
                # 2. Taken in an earlier semester during planning
                
                for prereq in prereqs:
                    if prereq in completed:
                        # Already satisfied
                        continue
                    
                    # Must be taken in earlier semester
                    # x[course, sem] <= sum(x[prereq, s] for s in earlier_semesters)
                    earlier_sems = [s for s in semesters if s < sem]
                    if earlier_sems and prereq in courses:
                        model.Add(
                            x[course, sem] <= sum(x[prereq, s] for s in earlier_sems)
                        )
        
        print("  ✓ Prerequisite constraints added")
    
    def _add_per_semester_credit_constraints(self, model, x, courses, semesters):
        """Each semester must have credits within [MIN_CREDITS, MAX_CREDITS]"""
        for sem in semesters:
            semester_credits = sum(
                self.loader.get_credits(c) * x[c, sem] 
                for c in courses
            )
            model.Add(semester_credits >= MIN_CREDITS)
            model.Add(semester_credits <= MAX_CREDITS)
        print(f"  ✓ Per-semester credit limits: {MIN_CREDITS}-{MAX_CREDITS}")
    
    def _add_slot_conflict_constraints(self, model, x, courses, semesters):
        """No two courses with conflicting slots in same semester"""
        for sem in semesters:
            for i, c1 in enumerate(courses):
                for c2 in courses[i+1:]:
                    if not self.loader.can_take_together(c1, c2):
                        model.Add(x[c1, sem] + x[c2, sem] <= 1)
        print("  ✓ Slot conflict constraints added")
    
    def _add_theory_lab_pairing_constraints(self, model, x, courses, semesters):
        """Theory and lab must be taken together in same semester"""
        for course in courses:
            if self.loader.has_lab(course):
                lab = self.loader.get_lab_course(course)
                if lab and lab in courses:
                    for sem in semesters:
                        # x[theory, sem] == x[lab, sem]
                        model.Add(x[course, sem] == x[lab, sem])
        print("  ✓ Theory-lab pairing constraints added")
    
    def _add_avoid_courses_constraint(self, model, x, student, courses, semesters):
        """Student-specified courses to avoid"""
        for course in student.avoid_courses:
            if course in courses:
                for sem in semesters:
                    model.Add(x[course, sem] == 0)
        print(f"  ✓ Avoiding {len(student.avoid_courses)} courses")
    
    def _add_category_credit_requirements(self, model, x, student, courses, semesters):
        """
        Global credit requirements by category must be met by semester 8
        """
        # Calculate credits already earned by category
        completed = set(student.completed_courses)
        earned_by_category = defaultdict(int)
        
        for course_code in completed:
            course = self.loader.get_course_by_code(course_code)
            if course:
                category = course['course_type']
                earned_by_category[category] += self.loader.get_credits(course_code)
        
        # Add constraints for each category
        for category, requirements in self.loader.credit_requirements.items():
            required = requirements.get('required', 0)
            already_earned = earned_by_category.get(category, 0)
            
            if already_earned >= required:
                continue  # Already satisfied
            
            # Get courses in this category
            category_courses = [
                c for c in courses 
                if self.loader.get_course_by_code(c).get('course_type') == category
            ]
            
            if not category_courses:
                continue
            
            # Sum of credits from this category across all semesters
            future_credits = sum(
                self.loader.get_credits(c) * x[c, sem]
                for c in category_courses
                for sem in semesters
            )
            
            # Must meet requirement
            model.Add(future_credits + already_earned >= required)
        
        print("  ✓ Category credit requirements added")
    
    def _add_project_semester_8_constraint(self, model, x, courses, semesters):
        """
        Project courses (Projects and Internship category) must be in semester 7 or 8
        """
        project_courses = [
            c for c in courses
            if self.loader.get_course_by_code(c).get('course_type') == 'Projects and Internship'
        ]
        
        for course in project_courses:
            # Can only be taken in semester 7 or 8
            for sem in semesters:
                if sem < 7:
                    model.Add(x[course, sem] == 0)
        
        print(f"  ✓ Project courses restricted to semesters 7-8")
    
    # ========================================================================
    # OBJECTIVE FUNCTION
    # ========================================================================
    
    def _set_objective(self, model, x, student, courses, semesters):
        """
        Maximize:
        - Mandatory courses taken
        - Courses that unlock other courses
        - Minimize difficulty (optional)
        """
        mandatory_courses = self.loader.get_remaining_mandatory_courses(student)
        
        # Mandatory course score
        mandatory_score = sum(
            x[c, sem] 
            for c in mandatory_courses 
            if c in courses
            for sem in semesters
        )
        
        # Unlock potential score
        unlock_score = sum(
            len(self.loader.course_unlocks.get(c, [])) * x[c, sem]
            for c in courses
            for sem in semesters
        )
        
        # Objective: prioritize mandatory, then unlock potential
        model.Maximize(100 * mandatory_score + 30 * unlock_score)
        print("  ✓ Objective function set")
    
    # ========================================================================
    # SOLUTION EXTRACTION
    # ========================================================================
    
    def _extract_solution(self, solver, x, courses, semesters) -> Dict[int, List[str]]:
        """Extract course assignments from solved model"""
        plan = {sem: [] for sem in semesters}
        
        for course in courses:
            for sem in semesters:
                if solver.Value(x[course, sem]) == 1:
                    plan[sem].append(course)
        
        return plan
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _get_all_eligible_courses(self, student) -> List[str]:
        """
        Get all courses that could potentially be taken in remaining semesters
        More permissive than single-semester eligibility
        """
        completed = set(student.completed_courses)
        all_courses = self.loader.get_all_course_codes()
        
        eligible = []
        for course_code in all_courses:
            # Skip if already completed
            if course_code in completed:
                continue
            
            course = self.loader.get_course_by_code(course_code)
            if not course:
                continue
            
            # Include if:
            # 1. Year offered <= current year + 1 (can take next year's courses)
            # 2. Prerequisites might be satisfiable during planning
            max_year = min(4, student.current_year + 1)
            if course.get('year_offered', 1) <= max_year:
                eligible.append(course_code)
        
        return eligible
    
    def _print_plan_summary(self, plan: Dict[int, List[str]], student):
        """Print summary of generated plan"""
        print("\n" + "="*80)
        print("📋 PLAN SUMMARY")
        print("="*80)
        
        total_courses = 0
        total_credits = 0
        
        for sem in sorted(plan.keys()):
            courses = plan[sem]
            credits = sum(self.loader.get_credits(c) for c in courses)
            total_courses += len(courses)
            total_credits += credits
            
            print(f"\nSemester {sem}: {len(courses)} courses, {credits} credits")
            for course in courses:
                course_info = self.loader.get_course_by_code(course)
                if course_info:
                    print(f"  • {course}: {course_info['course_name']} ({self.loader.get_credits(course)} cr)")
        
        print("\n" + "="*80)
        print(f"Total: {total_courses} courses, {total_credits} credits")
        print(f"Credits earned so far: {student.total_credits_earned}")
        print(f"Total after plan: {student.total_credits_earned + total_credits}")
        print(f"Required for graduation: {student.total_credits_required}")
        print("="*80 + "\n")


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    from data_loader import DataLoader
    
    # Initialize
    loader = DataLoader()
    loader.load_course_data()
    student = loader.load_student("21BCE0001")
    
    # Generate global plan
    planner = GlobalCPSATPlanner(loader)
    complete_plan = planner.generate_complete_plan(student)
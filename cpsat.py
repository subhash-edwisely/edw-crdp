from ortools.sat.python import cp_model
from typing import List
from collections import defaultdict
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel, Field

load_dotenv()

MIN_CREDITS = 16
MAX_CREDITS = 25
TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE = 160
TOTAL_SEMS = 8
MAX_ALLOWED_COURSES_PER_SEM = 12
RANGES = {
    "low": (MIN_CREDITS, MIN_CREDITS+2),
    "medium": (MIN_CREDITS+3, MAX_CREDITS-3),
    "high": (MAX_CREDITS-2 , MAX_CREDITS)
}
PLAN_CONFIGS = {
    'balanced': {
        'name': 'Balanced Plan',
        'description': 'A well-rounded approach balancing requirements, interests, and workload',
        'weights': {
            'mandatory': 100,
            'unlock': 30,
            'interest': 30,
            'workload': 60,
            'failed': 200,
        },
    },
    
    'interest_aligned': {
        'name': 'Interest-Aligned Plan',
        'description': 'Prioritize courses matching your passions and career goals',
        'weights': {
            'mandatory': 60,
            'unlock': 30,
            'interest': 150,
            'workload': 30,
            'failed': 200
        },
    }
}



class WeightReasoning(BaseModel):
    code: str
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    reason: str

class WeightsList(BaseModel):
    courses: List[WeightReasoning]

class CourseExplanation(BaseModel):
    code: str
    name: str
    semester: int
    why_selected: str
    why_this_semester: str
    prerequisites_context: str
    interest_alignment: str
    strategic_value: str

class SemesterExplanation(BaseModel):
    semester: int
    overall_strategy: str
    workload_reasoning: str
    courses: List[CourseExplanation]

class PlanExplanation(BaseModel):
    overall_plan_summary: str
    graduation_path: str
    semesters: List[SemesterExplanation]


class CoursePlanner:
    def __init__(self, loader, model='gpt-4.1-mini'):
        self.loader = loader
        self.client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.model = model
        self.last_llm_weights = None
        self.last_plan_explanation = None

    def set_ui_logger(self, callback):
        """Streamlit passes a callback here to receive selected logs"""
        self._ui_log_callback = callback

    def _ui_log(self, message):
        """Only these messages will show in Streamlit UI"""
        if self._ui_log_callback:
            self._ui_log_callback(message)
        print(message)  # still prints to console too

    def generate_single_plan(self, student, eligible_courses, remaining_semesters, failed_courses, llm_weights, weights):
        
        self._ui_log("🔧 Building constraint model...")
        model = cp_model.CpModel()
        x = self._create_variables(model, eligible_courses, remaining_semesters)
        self.add_hard_constraints(model, x, student, eligible_courses, failed_courses, remaining_semesters)
        workload_penalties = self.add_workload_balance_soft_constraint(model, x, student, eligible_courses, remaining_semesters)
        
        print("\n" + "="*80)
        print("🔍 LLM CALL RESULT CHECK")
        print("="*80)
        print(f"llm_weights type: {type(llm_weights)}")
        print(f"llm_weights is None: {llm_weights is None}")
        if llm_weights:
            print(f"llm_weights has 'courses': {'courses' in llm_weights}")
            if 'courses' in llm_weights:
                print(f"Number of courses: {len(llm_weights['courses'])}")
        else:
            print("⚠️ WARNING: llm_weights is None! LLM call failed or returned None")
        print("="*80 + "\n")
        
        # Store LLM weights for UI access
        self.last_llm_weights = llm_weights
        
        print(f"✅ Stored to self.last_llm_weights: {self.last_llm_weights is not None}")
        course_interest_weights_dict = self.add_course_interest_soft_constraint(eligible_courses, llm_weights)
        self.set_objective(model, x, student, eligible_courses, remaining_semesters, failed_courses, workload_penalties, course_interest_weights_dict, weights)
        
        # print("\n=== CONSTRAINT DEBUG ===")

        # # Check mandatory courses
        # mandatory_remaining = [c for c in self.loader.get_remaining_mandatory_courses(student) if c in eligible_courses]
        # mandatory_credits_total = sum(self.loader.get_credits(c) for c in mandatory_remaining)
        # print(f"Mandatory courses remaining: {len(mandatory_remaining)}")
        # print(f"Mandatory credits: {mandatory_credits_total}")

        # # Check if all mandatory can fit in 4 semesters
        # print(f"Max credits per semester: {MAX_CREDITS}")
        # print(f"Total max credits in 4 sems: {MAX_CREDITS * 4} = {25 * 4} = 100")
        # print(f"Can fit mandatory? {mandatory_credits_total <= 100}")

        # # Check Combined Elective specifically
        # de_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Discipline Elective']
        # oe_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Open Elective']
        # me_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Multidisciplinary Elective']

        # combined_available = sum(self.loader.get_credits(c) for c in de_courses + oe_courses + me_courses)
        # print(f"\nCombined Elective available: {combined_available} credits")
        # print(f"Combined Elective needed: 30 credits")
        # print(f"Can meet? {combined_available >= 30}")

        # # Check Non-graded
        # ng_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Non-graded Core Requirement']
        # ng_available = sum(self.loader.get_credits(c) for c in ng_courses)
        # print(f"\nNon-graded available: {ng_available} credits")
        # print(f"Non-graded needed: 11 credits")
        # print(f"Can meet? {ng_available >= 11}")

        # print("\n" + "="*50)

        # print("\n=== SEMESTER 5 DETAILED DEBUG ===")
        # failed_course = 'BMAT201L'
        # failed_slots = self.loader.get_course_by_code(failed_course).get('slots', [])
        # print(f"Failed course: {failed_course}")
        # print(f"Failed course slots: {failed_slots}")
        # print(f"Failed course credits: {self.loader.get_credits(failed_course)}")

        # # Find courses available for sem 5
        # sem5_eligible = []
        # for course in eligible_courses:
        #     if course == failed_course:
        #         continue
            
        #     course_info = self.loader.get_course_by_code(course)
            
        #     # Check year unlock
        #     year_offered = course_info.get('year_offered', 4)
        #     if year_offered > 3:  # Sem 5 is year 3
        #         continue
            
        #     # Check prerequisites
        #     preqs = self.loader.get_prerequisites(course)
        #     preqs_met = all(p in student.completed_courses for p in preqs)
        #     if not preqs_met:
        #         continue
            
        #     # Check slot conflict with failed course
        #     course_slots = course_info.get('slots', [])
        #     has_conflict = any(slot in failed_slots for slot in course_slots)
            
        #     sem5_eligible.append({
        #         'code': course,
        #         'credits': self.loader.get_credits(course),
        #         'slots': course_slots,
        #         'conflicts_with_failed': has_conflict,
        #         'type': course_info.get('course_type')
        #     })

        # print(f"\nCourses available for Sem 5: {len(sem5_eligible)}")
        # print(f"Courses WITHOUT slot conflict: {len([c for c in sem5_eligible if not c['conflicts_with_failed']])}")

        # # Check if we can meet 17 credits
        # non_conflict_credits = sum(c['credits'] for c in sem5_eligible if not c['conflicts_with_failed'])
        # print(f"\nTotal credits available (no conflict): {non_conflict_credits}")
        # print(f"Need (including failed course): 17 credits")
        # print(f"Need (excluding failed course 4 cr): 13 credits")
        # print(f"Can meet minimum? {non_conflict_credits >= 13}")

        # # Show some available courses
        # print("\nSample available courses (no conflict with failed):")
        # for c in sem5_eligible[:10]:
        #     if not c['conflicts_with_failed']:
        #         print(f"  {c['code']}: {c['credits']}cr, {c['type']}, slots: {c['slots']}")


        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        solver.parameters.random_seed = 42
        solver.parameters.num_search_workers = 1
    
        # 3. Disable any parallel features
        solver.parameters.interleave_search = False
        solver.parameters.share_objective_bounds = False
        solver.parameters.share_level_zero_bounds = False
        
        # 4. Use deterministic search strategy
        solver.parameters.search_branching = cp_model.FIXED_SEARCH
        solver.parameters.linearization_level = 2


        # solver.parameters.log_search_progress = True

        self._ui_log("⚡ Running CP-SAT solver...")
        status = solver.Solve(model)

        # for constraint in model.Proto().constraints:
            # print('constraints : ', constraint)
        
        # solver.parameters.cp_model_presolve = True
        # solver.parameters.find_multiple_cores = True 


        if status == cp_model.OPTIMAL:
            self._ui_log("✅ Found optimal solution!")
            plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
            self.print_plan(plan, student)

            # Generate explanations after successful plan generation
            print("\n" + "="*80)
            print("🤖 GENERATING PLAN EXPLANATIONS")
            print("="*80)
            self._ui_log("🤖 Generating plan explanation with AI...")
            plan_explanation = self.generate_plan_explanation(student, plan, llm_weights, course_interest_weights_dict)
            self.last_plan_explanation = plan_explanation
            print("✅ Explanations generated successfully")
            self._ui_log("✅ Plan explanation ready!")

            return plan, plan_explanation
        elif status == cp_model.FEASIBLE:
            print('Found feasible solution')
            self._ui_log("✅ Found feasible solution!")
            plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
            self.print_plan(plan, student)
            
            # Generate explanations after successful plan generation
            print("\n" + "="*80)
            print("🤖 GENERATING PLAN EXPLANATIONS")
            print("="*80)
            self._ui_log("🤖 Generating plan explanation with AI...")
            plan_explanation = self.generate_plan_explanation(student, plan, llm_weights, course_interest_weights_dict)
            self.last_plan_explanation = plan_explanation
            print("✅ Explanations generated successfully")
            self._ui_log("✅ Plan explanation ready!")
            
            return plan, plan_explanation
        else:
            print('No solution found')
            self._ui_log("❌ No solution found — diagnosing issue...")
            print('Status :', solver.StatusName(status))
            reasons = self.diagnose_infeasibility(student, eligible_courses, failed_courses, remaining_semesters)
            print("🔍 Infeasibility reasons:")
            for r in reasons:
                print(f"  ❌ {r}")
            return {sem: [] for sem in remaining_semesters}, None


        # print("\n=== CATEGORY REQUIREMENT DETAILED ANALYSIS ===")

        # completed = set(student.completed_courses)
        # earned_by_category = defaultdict(int)

        # for course_code in completed:
        #     course = self.loader.get_course_by_code(course_code)
        #     if course:
        #         category = course['course_type']
        #         earned_by_category[category] += self.loader.get_credits(course_code)

        # print("\nCredits earned by category:")
        # for cat, creds in earned_by_category.items():
        #     print(f"  {cat}: {creds} credits")

        # print("\nChecking each category requirement:")
        # for category, requirements in self.loader.credit_requirements.items():
        #     required = requirements.get('required', 0)
        #     already_earned = earned_by_category.get(category, 0)
            
        #     if already_earned >= required:
        #         print(f"\n✓ {category}: SATISFIED ({already_earned}/{required})")
        #         continue
            
        #     print(f"\n⚠ {category}: Need {required - already_earned} more credits ({already_earned}/{required})")
            
        #     # Find available courses for this category
        #     if category == 'Combined Elective':
        #         category_courses = [
        #             c for c in eligible_courses  
        #             if self.loader.get_course_by_code(c).get('course_type', '') in
        #             ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
        #         ]
        #     else:
        #         category_courses = [
        #             c for c in eligible_courses 
        #             if self.loader.get_course_by_code(c).get('course_type', '') == category
        #         ]
            
        #     total_available = sum(self.loader.get_credits(c) for c in category_courses)
        #     can_satisfy = (total_available + already_earned) >= required
            
        #     print(f"  Available courses: {len(category_courses)}")
        #     print(f"  Available credits: {total_available}")
        #     print(f"  Total (earned + available): {already_earned + total_available}")
        #     print(f"  Can satisfy? {can_satisfy}")
            
        #     if not can_satisfy:
        #         print(f"  ❌ IMPOSSIBLE TO SATISFY!")
        #         print(f"     Need: {required}")
        #         print(f"     Have: {already_earned}")
        #         print(f"     Can get: {total_available}")
        #         print(f"     Shortage: {required - (already_earned + total_available)}")
            
        #     # Show which courses are available
        #     if len(category_courses) > 0:
        #         print(f"  Sample courses:")
        #         for c in category_courses[:5]:
        #             print(f"    - {c}: {self.loader.get_credits(c)}cr")

        # # Call debug instead of solving
        # self.debug_constraints(student, eligible_courses, failed_courses, remaining_semesters)
        # return {sem: [] for sem in remaining_semesters}

    
    def generate_complete_plan(self, student):
        print("\n" + "="*80)
        print("🎓 GENERATING MULTIPLE COURSE PLANS")
        print("="*80)

        remaining_semesters = list(range(student.current_semester, 9))
        print("Generating recommendations for semesters:", remaining_semesters)

        eligible_courses, failed_courses = self.get_eligible_and_failed_courses(student)
        
        # DEBUG: Print counts
        print(f"\n=== DEBUG ===")
        print(f"Eligible courses: {len(eligible_courses)}")
        print(f"Failed courses: {len(failed_courses)}")
        
        # Check remaining requirements
        remaining = self.loader.get_remaining_credits_by_type(student)
        print(f"\nRemaining credits needed:")
        for cat, creds in remaining.items():
            print(f"  {cat}: {creds} credits")
        
        # Check if enough courses available
        total_needed = sum(remaining.values())
        total_available = sum(self.loader.get_credits(c) for c in eligible_courses)
        print(f"\nTotal credits needed: {total_needed}")
        print(f"Total credits available: {total_available}")
        # print("="*80)
        # print('COMPLETE PLAN')
        # print("="*80)

        # remaining_semesters = list(range(student.current_semester, 9))
        # print("Generating recommendations for semesters:", remaining_semesters)

        # eligible_courses, failed_courses = self.get_eligible_and_failed_courses(student)
        
        llm_weights = self.get_course_interest_weights_from_llm(student, eligible_courses)

        results = {}
        
        # Generate each plan type
        for plan_type, config in PLAN_CONFIGS.items():
            plan, explanation = self.generate_single_plan(
                student,
                eligible_courses,
                remaining_semesters,
                failed_courses,
                llm_weights,
                weights=config['weights'],
            )
            
            if plan and any(plan.values()) and explanation:
                
                results[plan_type] = {
                    'config': config,
                    'plan': plan,
                    'explanation': explanation,
                }
                
                print(f"\n✅ {config['name']} completed:")

            else:
                print(f"\n❌ {config['name']} failed to generate")
        
        print("\n" + "="*80)
        print(f"✅ Generated {len(results)}/2 plans successfully")
        print("="*80 + "\n")
        
        return results


    def get_eligible_and_failed_courses(self, student):
        completed = set(student.completed_courses)
        failed = set(student.failed_courses)
        all_courses = self.loader.get_all_course_codes()

        eligible = []
        for course_code in all_courses:
            if course_code in completed:
                continue

            eligible.append(course_code)
        
        return eligible, failed

    def _create_variables(self, model, eligible_courses, semesters):
        x = {}
        for course in eligible_courses:
            for sem in semesters:
                x[course, sem] = model.new_bool_var(f'{course}_semester{sem}')
        
        return x
    
    def add_course_can_be_taken_only_once_constraint(self, model, x, courses, semesters):
        for course in courses:
            model.add(sum(x[course, sem] for sem in semesters) <= 1)
    
    def add_course_already_completed_constraint(self, model, x, student, courses, semesters):
        completed = set(student.completed_courses)
        for course in courses:
            if course in completed:
                for sem in semesters:
                    model.add(x[course, sem] == 0)
    
    def add_preq_check_constraint(self, model, x, student, courses, semesters):
        completed = set(student.completed_courses)

        for course in courses:
            preqs = self.loader.get_prerequisites(course)
            if not preqs:
                continue

            for sem in semesters:
                for preq in preqs:
                    if preq in completed:
                        continue

                    if preq not in courses:
                        print('Prerequisite not in completed and also it is not in eligible course pool')   
                        model.add(1 == 0)
                        continue
                    
                    past_sems = [s for s in semesters if s < sem]

                    if not past_sems:
                        model.add(x[course, sem] == 0)

                    if past_sems and preq in courses:

                        # a constraint telling the solver to only consider the current course in this current sem only if its preq are satisfied in previous sems
                        model.add(
                            x[course, sem] <= sum(x[preq, s] for s in past_sems)
                        )
    
    def add_min_max_credit_constraint(self, model, x, courses, semesters):

        for sem in semesters:
            sem_creds = sum(
                self.loader.get_credits(c) * x[c, sem]
                for c in courses
            )

            model.add(sem_creds >= MIN_CREDITS)
            model.add(sem_creds <= MAX_CREDITS)

    def add_slot_conflict_constraint(self, model, x, courses, semesters):
        for sem in semesters:
            for i, c1 in enumerate(courses):
                for c2 in courses[i+1: ]:
                    if not self.loader.can_take_together(c1, c2):
                        model.add(x[c1, sem] + x[c2, sem] <= 1)
            
            break

    def add_theory_lab_pairing_constraint(self, model, x, student, courses, semesters):
        completed = set(student.completed_courses)
        for course in courses:
            if self.loader.get_lab_course(course):
                lab = self.loader.get_lab_course(course)
                if lab and lab in courses and lab not in completed:
                    for sem in semesters:
                        model.add(x[course, sem] == x[lab, sem])
    
    def add_category_credit_requirement_constraint(self, model, x, student, courses, semesters):
        completed = set(student.completed_courses)
        earned_by_category = defaultdict(int)

        for course_code in completed:
            course = self.loader.get_course_by_code(course_code)
            if course:
                category = course['course_type']
                earned_by_category[category] += self.loader.get_credits(course_code)

        for category, requirements in self.loader.credit_requirements.items():
            required = requirements.get('required', 0)
            already_earned = earned_by_category.get(category, 0)

            if already_earned >= required:
                continue
        
            category_courses = [c for c in courses if self.loader.get_course_by_code(c).get('course_type', '') == category]
            if category == 'Combined Elective':
                category_courses = [
                    c for c in courses  
                    if self.loader.get_course_by_code(c).get('course_type', '') in
                    ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
                ]

            if not category_courses:
                print(f"Cannot meet {category} requirement!")
                print(f"Required: {required}, Earned: {already_earned}, Shortage: {required - already_earned}")
                model.add(1 == 0)
                continue
        
            future_credits = sum(
                self.loader.get_credits(c) * x[c, sem]
                for c in category_courses
                for sem in semesters
            )

            model.add(future_credits + already_earned >= required)

    def add_project_constraint(self, model, x, courses, semesters):
        project_courses = [
            c for c in courses
            if self.loader.get_course_by_code(c).get('course_type') == 'Projects and Internship'
        ]

        project1 = 'BCSE497J'
        project2 = 'BCSE498J'
        internship = 'BCSE499J'
        for course in project_courses:
            for sem in semesters:
                if(course == project1):
                    if(sem == 7):
                        model.add(x[course, sem] == 1)
                    else:
                        model.add(x[course, sem] == 0)
                
                elif(course == project2 or course == internship):
                    if(sem == 8):
                        model.add(x[course, sem] == 1)
                    else:
                        model.add(x[course, sem] == 0)
                
                else:
                    if(sem < 7):
                        model.add(x[course, sem] == 0)
    
    def add_failed_courses_retake_constraint(self, model, x, failed_courses, semesters):
        for c in failed_courses:
            model.add(sum(x[c, s] for s in semesters) == 1)

    def add_total_min_credits_req_for_graduation(self, model, x, student, courses, semesters):
        completed = student.completed_courses
        credits_earned_so_far = round(sum([self.loader.get_credits(c) for c in completed]))
        min_credits_required = TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE - credits_earned_so_far
        # print('eyuyuyuyuyu : ', TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE, credits_earned_so_far, min_credits_required, [self.loader.get_credits(c) for c in completed])
        model.add(
            sum(
                self.loader.get_credits(c) * x[c, s]
                for c in courses
                for s in semesters
            ) >= min_credits_required
        )

    def add_year_level_course_unlock_constraint(self, model, x, courses, semesters):
        for course in courses:
            course_unlock_year = self.loader.get_course_by_code(course).get('year_offered', 4)
            for sem in semesters:
                year = (sem+1)//2
                if(year < course_unlock_year):
                    model.add(x[course, sem] == 0)

    def add_max_allowed_courses_per_semester(self, model, x, courses, semesters):
        for sem in semesters:
            model.add(
                sum(x[c, sem] for c in courses) <= MAX_ALLOWED_COURSES_PER_SEM
            )

    def add_hard_constraints(self, model, x, student, eligible_courses, failed_courses, remaining_semesters):
        self.add_course_already_completed_constraint(model, x, student, eligible_courses, remaining_semesters)
        self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
        self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
        self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
        self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
        self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
        self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
        self.add_theory_lab_pairing_constraint(model, x, student, eligible_courses, remaining_semesters)  
        self.add_failed_courses_retake_constraint(model, x, failed_courses, remaining_semesters)
        self.add_total_min_credits_req_for_graduation(model, x, student, eligible_courses, remaining_semesters)
        self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
        self.add_max_allowed_courses_per_semester(model, x, eligible_courses, remaining_semesters)


    def add_workload_balance_soft_constraint(self, model, x, student, courses, semesters):
        workload_preference = student.workload_preference or 'medium'
        penalty_vars = []
        ranges = RANGES

        current_semester = semesters[0]
        future_semesters = semesters[1: ] if len(semesters) > 1 else []

        current_sem_preference = ranges[workload_preference]
        min_target, max_target = current_sem_preference
        current_sem_credits = sum([self.loader.get_credits(c) * x[c, current_semester] for c in courses])

        # will penalize if credits are below the min_target
        under_penalty = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{current_semester}')
        model.add(under_penalty >= min_target - current_sem_credits)

        # will penalize if credits are above the max_target
        over_penalty = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{current_semester}')
        model.add(over_penalty >= current_sem_credits - max_target)

        penalty_vars.extend([under_penalty, over_penalty])

        # we consider balanced workload for future sems
        for sem in future_semesters:
            sem_credits = sum([self.loader.get_credits(c) * x[c, sem] for c in courses])
            min_target, max_target = ranges['medium']

            under_penalty = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{sem}')
            model.add(under_penalty >= min_target - sem_credits)

            over_penalty = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{sem}')
            model.add(over_penalty >= sem_credits - max_target)

            penalty_vars.extend([under_penalty, over_penalty])
        

        return penalty_vars
    
    
    def get_course_interest_weights_from_llm(self, student, courses):
        
        # Build compact course list
        course_list = []
        for course_code in courses:
            course_info = self.loader.get_course_by_code(course_code)
            course_list.append({
                "code": course_code,
                "name": course_info['course_name'],
                "type": course_info.get('course_type', 'Unknown')
            })

        # print('coruse list : ', course_list)
        self._ui_log(f"🤖 AI analyzing {len(course_list)} courses against your interests and grade history...")
        
        prompt = f"""You are an academic advisor analyzing course-interest alignment.

            TASK:
            Rate how well each course matches the student's stated interests.

            STUDENT INTERESTS:
            {json.dumps(student.interest_areas, indent=2)}

            COURSES TO RATE:
            {json.dumps(course_list, indent=2)}

            RATING GUIDELINES:

            Score 0.9 - 1.0: Perfect Match
            - Course title/content directly mentions student's core interests
            - Example: Student likes "Machine Learning" → Course is "Machine Learning Fundamentals"

            Score 0.7 - 0.8: Strong Match
            - Course closely related to interests
            - Example: Student likes "AI" → Course is "Neural Networks" or "Computer Vision"

            Score 0.5 - 0.6: Moderate Match
            - Course somewhat related or complementary
            - Example: Student likes "Web Development" → Course is "Database Systems"

            Score 0.3 - 0.4: Weak Match
            - Course tangentially related or prerequisite to interests
            - Example: Student likes "Cybersecurity" → Course is "Operating Systems"

            Score 0.0 - 0.2: No Match
            - Course unrelated to stated interests
            - Example: Student likes "Software Engineering" → Course is "Analog Electronics"

            CRITICAL RULES:
            1. Base scores ONLY on interest alignment, nothing else
            2. Ignore student's CGPA, year, or past performance
            3. Ignore course difficulty or workload
            4. Ignore graduation requirements (mandatory/elective status)
            5. Focus purely on: Does this course topic match what the student is interested in?

            OUTPUT FORMAT (strict JSON):
            {{
            "courses": {{
                {{
                "code": "BCSE306L",
                "name": "Artificial Intelligence",
                "weight": 0.95,
                "reason": "Directly matches core AI interest"
                }},
                {{
                "code": "BCSE301L",
                "name": "Software Engineering",
                "weight": 0.60,
                "reason": "Related to software development interest"
                }}
            }}
            }}

            Rate ALL {len(course_list)} courses. Return ONLY valid JSON, no additional text."""

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": """You are an expert academic advisor specializing in course-interest matching.

                            Your ONLY job: Determine how well each course aligns with student's stated interests.

                            You MUST:
                            - Rate based purely on interest-topic alignment
                            - Provide specific, concrete reasons
                            - Be consistent in your scoring
                            - Return valid JSON only

                            You MUST NOT:
                            - Consider student's grades or performance
                            - Consider course difficulty
                            - Consider graduation requirements
                            - Make assumptions beyond the interest areas provided
                            - Hallucinate course content not in the course name/type"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                text_format=WeightsList,
            )
            
            parsed_output = response.output_parsed
            self._ui_log(f"✅ AI analysis complete — {len(parsed_output.courses)} courses weighted")
            return parsed_output
            
        except json.JSONDecodeError as e:
            print(f"✗ Error parsing LLM response: {e}")
            return None
        
        except Exception as e:
            print(f"✗ Error in LLM call: {e}")
            return None

    def add_course_interest_soft_constraint(self, courses, llm_weights):
        print(llm_weights)
        weights_dict = dict()
        if llm_weights and llm_weights.courses:
            for course_weight in llm_weights.courses:
                weights_dict[course_weight.code] = (course_weight.weight, course_weight.name, course_weight.reason)
        
        print('Totla courses weighted : ', len(weights_dict))

        for course in courses:
            weighted_courses = set(weights_dict.keys())
            if course not in weighted_courses:
                weights_dict[course] = (0.5, self.loader.get_course_by_code(course).get('course_name'), 'Default value set')
                print('Using default weight for course : ', course)
        
        return weights_dict


    def set_objective(self, model, x, student, courses, semesters, failed_courses, workload_penalties, course_interest_weights_dict, weights):
        mandatory_courses = self.loader.get_remaining_mandatory_courses(student)
        mandatory_score = sum(
            x[c, s] * (TOTAL_SEMS - s + 1)
            for c in mandatory_courses if c in courses for s in semesters
        )

        unlock_score = sum(
            len(self.loader.course_unlocks.get(c, [])) * x[c, s] * (TOTAL_SEMS - s + 1)
            for c in courses for s in semesters
        )

        print('WORKLOAD PENALTIES : ', workload_penalties)
        worload_penalty_total = sum(workload_penalties)

        interest_score = sum(
            int(course_interest_weights_dict.get(c, (0.5, self.loader.get_course_by_code(c).get('course_name'), 'Default value set'))[0] * 100) * x[c, s] * (TOTAL_SEMS - s + 1)
            for c in courses
            for s in semesters
        )


        failed_course_urgency_score = sum(
            (TOTAL_SEMS - s + 1) * x[c, s]
            for c in failed_courses if c in courses
            for s in semesters
        )



        w_mandatory = weights.get('mandatory', 100)
        w_unlock = weights.get('unlock', 30)
        w_interest = weights.get('interest', 30)
        w_workload = weights.get('workload', 60)
        w_failed = weights.get('failed', 200)


        model.maximize(
            w_mandatory * mandatory_score 
            + 
            w_unlock * unlock_score
            +
            w_interest * interest_score
            +
            w_failed * failed_course_urgency_score
            -
            w_workload * worload_penalty_total
        )
    
    def get_solution(self, solver, x, courses, semesters):
        plan = {sem: [] for sem in semesters}

        for course in courses:
            for sem in semesters:
                if solver.Value(x[course, sem]) == 1:
                    plan[sem].append(course)
        
        return plan

    def print_plan(self, plan, student):
        print("\n" + "="*80)
        print("📋 PLAN SUMMARY")
        print("="*80)
        
        completed = student.completed_courses
        credits_earned_so_far = round(sum([self.loader.get_credits(c) for c in completed]))

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
        print(f"Credits earned so far: {credits_earned_so_far}")
        print(f"Total after plan: {credits_earned_so_far + total_credits}")
        print(f"Required for graduation: {TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE}")
        print("="*80 + "\n")



    
    # def debug_constraints(self, student, eligible_courses, failed_courses, remaining_semesters):
    #     """Test each constraint individually to find which makes the problem infeasible"""
        
    #     print("\n" + "="*80)
    #     print("CONSTRAINT DEBUGGING - Testing each constraint individually")
    #     print("="*80)
        
    #     # Test 1: Bare minimum - just credit bounds
    #     print("\n[TEST 1] Only credit bounds (17-25)")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 2: Add once-only constraint
    #     print("\n[TEST 2] + Course taken only once")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 3: Add failed course constraint
    #     print("\n[TEST 3] + Failed course must be retaken")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 4: Add slot conflicts
    #     print("\n[TEST 4] + Slot conflicts (sem 5 only)")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 5: Add theory-lab pairing
    #     print("\n[TEST 5] + Theory-lab pairing")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 6: Add prerequisites
    #     print("\n[TEST 6] + Prerequisites")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 7: Add project constraints
    #     print("\n[TEST 7] + Project constraints")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 8: Add year unlock
    #     print("\n[TEST 8] + Year unlock")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 9: Add category requirements
    #     print("\n[TEST 9] + Category credit requirements")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     # Test 10: Add total credits requirement
    #     print("\n[TEST 10] + Total credits for graduation")
    #     model = cp_model.CpModel()
    #     x = self._create_variables(model, eligible_courses, remaining_semesters)
    #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
    #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
    #     self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
    #     self.add_total_min_credits_req_for_graduation(model, x, student, eligible_courses, remaining_semesters)
    #     solver = cp_model.CpSolver()
    #     solver.parameters.max_time_in_seconds = 5.0
    #     status = solver.Solve(model)
    #     print(f"Result: {solver.StatusName(status)}")
        
    #     print("\n" + "="*80)


    def generate_plan_explanation(self, student, plan, llm_weights, course_interest_weights_dict):
        """
        Generate comprehensive explanations for why each course was selected 
        and why it was placed in a specific semester using LLM.
        """

        self._ui_log("📝 Generating personalized course explanations...")
        
        # Prepare context data
        student_context = {
            "name": student.name,
            "student_id": student.student_id,
            "current_semester": student.current_semester,
            "cgpa": student.cgpa,
            "interest_areas": student.interest_areas if hasattr(student, 'interest_areas') else [],
            "workload_preference": student.workload_preference or "medium",
            "completed_courses_count": len(student.completed_courses),
            "failed_courses": student.failed_courses
        }
        
        # Prepare plan data with rich context
        plan_data = []
        for sem in sorted(plan.keys()):
            if not plan[sem]:
                continue
                
            sem_courses = []
            sem_credits = 0
            
            for course_code in plan[sem]:
                course_info = self.loader.get_course_by_code(course_code)
                if not course_info:
                    continue
                    
                credits = self.loader.get_credits(course_code)
                sem_credits += credits
                
                # Get prerequisites
                prereqs = self.loader.get_prerequisites(course_code)
                prereq_names = []
                for p in prereqs:
                    p_info = self.loader.get_course_by_code(p)
                    if p_info:
                        prereq_names.append(f"{p} ({p_info['course_name']})")
                
                # Get courses this unlocks
                unlocks = self.loader.course_unlocks.get(course_code, [])
                unlock_names = []
                for u in unlocks:
                    u_info = self.loader.get_course_by_code(u)
                    if u_info:
                        unlock_names.append(f"{u} ({u_info['course_name']})")
                
                # Get interest weight
                interest_weight_info = course_interest_weights_dict.get(
                    course_code, 
                    (0.5, course_info.get('course_name'), 'Not weighted')
                )
                
                sem_courses.append({
                    "code": course_code,
                    "name": course_info['course_name'],
                    "credits": credits,
                    "type": course_info.get('course_type', 'Unknown'),
                    "is_mandatory": course_info.get('is_mandatory', False),
                    "is_failed_retake": course_code in student.failed_courses,
                    "difficulty": course_info.get('difficulty', 50),
                    "pass_rate": course_info.get('pass_rate', 0.8),
                    "prerequisites": prereq_names,
                    "unlocks": unlock_names,
                    "interest_weight": interest_weight_info[0],
                    "interest_reason": interest_weight_info[2],
                    "slots": course_info.get('slots', [])
                })
            
            plan_data.append({
                "semester": sem,
                "total_credits": sem_credits,
                "course_count": len(sem_courses),
                "courses": sem_courses
            })
        
        # Get remaining requirements
        remaining_requirements = self.loader.get_remaining_credits_by_type(student)
        
        # Build the prompt
        prompt = f"""You are an expert academic advisor with deep knowledge of curriculum planning, 
            course prerequisites, and student success strategies. 

            TASK:
            Generate a comprehensive, personalized explanation for this student's course plan. 
            Explain WHY each course was selected and WHY it was placed in its specific semester.

            STUDENT PROFILE:
            {json.dumps(student_context, indent=2)}

            REMAINING REQUIREMENTS:
            {json.dumps(remaining_requirements, indent=2)}

            GENERATED COURSE PLAN:
            {json.dumps(plan_data, indent=2)}

            EXPLANATION REQUIREMENTS:

            For the OVERALL PLAN:
            1. Summarize the strategic approach to graduation (2-3 sentences)
            2. Explain how this plan addresses the student's interests and workload preference
            3. Highlight the graduation path trajectory (e.g., "Front-loads mandatory courses, saves electives for later")

            For EACH SEMESTER:
            1. Overall semester strategy (1-2 sentences explaining the focus/theme)
            2. Workload reasoning (why this specific credit load makes sense)

            For EACH COURSE in EACH SEMESTER:
            1. **Why Selected**: 
            - Is it mandatory for graduation? 
            - Does it align with student interests (reference the interest_weight)?
            - Is it a failed course that must be retaken?
            - Does it satisfy a specific requirement category?

            2. **Why This Semester**:
            - Are prerequisites satisfied by this point?
            - Does it unlock important future courses (mention which ones)?
            - Does it fit the student's current workload preference?
            - Are there slot/scheduling constraints?
            - Is this the earliest possible semester for this course?

            3. **Prerequisites Context**:
            - List which prerequisites were already completed or will be completed
            - Explain why the student is ready for this course now

            4. **Interest Alignment**:
            - Reference the interest_weight score
            - Explain how this course connects to student's stated interests
            - Use the interest_reason from the weight analysis

            5. **Strategic Value**:
            - What future courses does this unlock?
            - How does this contribute to graduation requirements?
            - Does this help maintain GPA or reduce risk?

            IMPORTANT INSTRUCTIONS:
            - Be specific and reference actual data (course codes, prerequisites, interest weights)
            - Explain cause-and-effect relationships (e.g., "Taking BCSE203P in Sem 5 unlocks BCSE306L in Sem 6")
            - Acknowledge trade-offs when they exist (e.g., "Slightly higher workload to complete mandatory courses early")
            - Use natural, conversational language - avoid robotic or repetitive phrasing
            - Focus on PERSONALIZATION - this should feel tailored to this specific student
            - For failed courses, be encouraging and explain the retake strategy
            - Mention workload distribution across semesters

            OUTPUT FORMAT:
            Return a structured JSON matching the PlanExplanation schema with:
            - overall_plan_summary: string (2-3 paragraphs)
            - graduation_path: string (1-2 paragraphs)
            - semesters: array of SemesterExplanation objects
            - Each with: semester, overall_strategy, workload_reasoning, courses array
            - courses array contains CourseExplanation objects with all required fields

            Example structure:
            {{
            "overall_plan_summary": "Your course plan strategically balances...",
            "graduation_path": "You're on track to graduate with...",
            "semesters": [
                {{
                "semester": 5,
                "overall_strategy": "This semester focuses on...",
                "workload_reasoning": "With 20 credits, this aligns with your medium workload preference...",
                "courses": [
                    {{
                    "code": "BCSE306L",
                    "name": "Artificial Intelligence",
                    "semester": 5,
                    "why_selected": "This mandatory core course directly aligns with your strong interest in AI (interest weight: 0.95). It's essential for your degree and matches your passion.",
                    "why_this_semester": "This is the earliest semester you can take this course after completing prerequisite BCSE203P in Sem 4. Taking it now unlocks advanced AI electives like Machine Learning (BCSE410L) in future semesters.",
                    "prerequisites_context": "You've already completed the required prerequisites: BCSE203P (Data Structures) in Sem 4, which gave you the algorithmic foundation needed.",
                    "interest_alignment": "With an interest weight of 0.95, this is one of your highest-rated courses. It directly addresses your stated interest in 'AI and machine learning applications'.",
                    "strategic_value": "This course unlocks 3 advanced electives: BCSE410L (Machine Learning), BCSE412L (Deep Learning), and BCSE415L (Computer Vision). Completing it now maximizes your options for specialized courses in later semesters."
                    }}
                ]
                }}
            ]
            }}

            Generate thorough, personalized explanations that will help the student understand and feel confident about their course plan."""

        try:
            print("🤖 Calling LLM for plan explanation...")
            
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": """You are an expert academic advisor who excels at explaining complex course planning decisions.

                        Your explanations should be:
                        - SPECIFIC: Reference actual course codes, prerequisites, and data
                        - PERSONALIZED: Connect to the student's interests and situation
                        - STRATEGIC: Explain the long-term thinking behind decisions
                        - ENCOURAGING: Positive and supportive tone
                        - CLEAR: Avoid jargon, use natural language
                        - ACTIONABLE: Help students understand what to do and why

                        You MUST:
                        - Explain every course selection decision
                        - Connect courses to student's interests using the interest_weight data
                        - Explain prerequisite chains and course unlocking
                        - Justify semester placement based on constraints
                        - Address workload distribution
                        - Be specific about graduation requirements being met

                        You MUST NOT:
                        - Give generic explanations that could apply to anyone
                        - Ignore the interest_weight and interest_reason data provided
                        - Make assumptions not supported by the data
                        - Be overly technical or use unexplained acronyms
                        - Provide incomplete explanations for any course"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                text_format=PlanExplanation,
            )
            
            explanation = response.output_parsed
            
            self._ui_log(f"✅ Explanations ready for {len(explanation.semesters)} semesters")
            print(f"✅ Generated explanations for {len(explanation.semesters)} semesters")
            for sem_exp in explanation.semesters:
                print(f"   Semester {sem_exp.semester}: {len(sem_exp.courses)} courses explained")
            
            print("Explanation : ", explanation)
            
            return explanation
            
        except json.JSONDecodeError as e:
            print(f"✗ Error parsing LLM explanation response: {e}")
            return None
        
        except Exception as e:
            print(f"✗ Error in LLM explanation call: {e}")
            import traceback
            traceback.print_exc()
            return None





    def diagnose_infeasibility(self, student, eligible_courses, failed_courses, remaining_semesters):
        """Run constraint isolation to identify what's causing infeasibility"""
        
        reasons = []
        
        def quick_solve(add_constraints_fn):
            m = cp_model.CpModel()
            x = self._create_variables(m, eligible_courses, remaining_semesters)
            add_constraints_fn(m, x)
            s = cp_model.CpSolver()
            s.parameters.max_time_in_seconds = 5.0
            return s.Solve(m) in [cp_model.OPTIMAL, cp_model.FEASIBLE]

        # Check 1: Credits alone
        if not quick_solve(lambda m, x: self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters)):
            reasons.append("Not enough courses available to meet minimum credit requirements per semester")
            return reasons

        # Check 2: + Failed courses retake
        def check2(m, x):
            self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters)
            self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters)
            self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters)
        if not quick_solve(check2):
            reasons.append(f"Failed courses {list(failed_courses)} cannot be accommodated within credit limits")
            return reasons

        # Check 3: + Prerequisites
        def check3(m, x):
            check2(m, x)
            self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters)
        if not quick_solve(check3):
            reasons.append("Prerequisite chain constraints make scheduling impossible — possible failed course whose prereq is also failed")
            return reasons

        # Check 4: + Category requirements
        def check4(m, x):
            check3(m, x)
            self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters)
        if not quick_solve(check4):
            reasons.append("Category credit requirements cannot be satisfied with available courses in remaining semesters")
            return reasons

        # Check 5: + Graduation credits
        def check5(m, x):
            check4(m, x)
            self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters)
        if not quick_solve(check5):
            reasons.append("Total credits required for graduation cannot be achieved in remaining semesters")
            return reasons

        reasons.append("Combination of all constraints together is infeasible — likely slot conflicts or theory-lab pairing conflicts")
        return reasons






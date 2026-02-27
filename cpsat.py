# from ortools.sat.python import cp_model
# from typing import List
# from collections import defaultdict
# from openai import OpenAI
# from dotenv import load_dotenv
# import os
# import json
# from pydantic import BaseModel, Field

# load_dotenv()

# MIN_CREDITS = 16
# MAX_CREDITS = 25
# TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE = 160
# TOTAL_SEMS = 8
# MAX_ALLOWED_COURSES_PER_SEM = 12
# RANGES = {
#     "low": (MIN_CREDITS, MIN_CREDITS+2),
#     "medium": (MIN_CREDITS+3, MAX_CREDITS-3),
#     "high": (MAX_CREDITS-2 , MAX_CREDITS)
# }
# PLAN_CONFIGS = {
#     'balanced': {
#         'name': 'Balanced Plan',
#         'description': 'A well-rounded approach balancing requirements, interests, and workload',
#         'weights': {
#             'mandatory': 100,
#             'failed': 200,
#             'lateness': 100,
#             'unlock': 100,
#             'diversity': 30,
#             'interest': 50,
#             'workload': 100,
#             'credit_limit_exceed': 30
#         },
#     },
    
#     'interest_aligned': {
#         'name': 'Interest-Aligned Plan',
#         'description': 'Prioritize courses matching your passions and career goals',
#         'weights': {
#             'mandatory': 1,
#             'failed': 1,
#             'lateness': 1,
#             'unlock': 1,
#             'diversity': 1,
#             'interest': 1,
#             'workload': 1,
#             'credit_limit_exceed': 30
#         },
#     }
# }
# INTEREST_SCALE = 100
# NORM_SCALE = 100



# class WeightReasoning(BaseModel):
#     code: str
#     name: str
#     weight: float = Field(ge=0.0, le=1.0)
#     reason: str

# class WeightsList(BaseModel):
#     courses: List[WeightReasoning]

# class CourseExplanation(BaseModel):
#     code: str
#     name: str
#     semester: int
#     why_selected: str
#     why_this_semester: str
#     prerequisites_context: str
#     interest_alignment: str
#     strategic_value: str

# class SemesterExplanation(BaseModel):
#     semester: int
#     overall_strategy: str
#     workload_reasoning: str
#     courses: List[CourseExplanation]

# class PlanExplanation(BaseModel):
#     overall_plan_summary: str
#     graduation_path: str
#     semesters: List[SemesterExplanation]


# class CoursePlanner:
#     def __init__(self, loader, model='gpt-4.1-mini'):
#         self.loader = loader
#         self.client = OpenAI(
#             api_key=os.getenv('OPENAI_API_KEY')
#         )
#         self.model = model
#         self.last_llm_weights = None
#         self.last_plan_explanation = None
#         self.unlock_chain_sizes = self.precompute_unlock_chain_sizes()
#         print(f'Precomputed chain sizes for {len(self.unlock_chain_sizes)} courses. The are {self.unlock_chain_sizes}')

#         self._ui_log_callback = None

#     def set_ui_logger(self, callback):
#         """Streamlit passes a callback here to receive selected logs"""
#         self._ui_log_callback = callback

#     def _ui_log(self, message):
#         """Only these messages will show in Streamlit UI"""
#         if self._ui_log_callback:
#             self._ui_log_callback(message)
#         else:
#             print(message)  # still prints to console too


#     def precompute_unlock_chain_sizes(self):
#         chain_sizes = {}
#         all_courses = self.loader.get_all_course_codes()

#         def count_downstream(course_code, visited):
#             if(course_code in visited):
#                 return set()
#             visited.add(course_code)
            
#             direct_unlocks = set(self.loader.course_unlocks.get(course_code, []))
#             all_downstream = set(direct_unlocks)

#             for c in direct_unlocks:
#                 all_downstream |= count_downstream(c, visited.copy())
            
#             return all_downstream
        

#         for course in all_courses:
#             downstream_courses = count_downstream(course, set())
#             chain_sizes[course] = len(downstream_courses)
        
#         return chain_sizes
    

#     def generate_single_plan(self, student, eligible_courses, remaining_semesters, failed_courses, llm_weights, weights):
        
#         self._ui_log("🔧 Building constraint model...")
#         model = cp_model.CpModel()
#         x = self._create_variables(model, eligible_courses, remaining_semesters)
#         self.add_hard_constraints(model, x, student, eligible_courses, failed_courses, remaining_semesters)
#         workload_penalties = self.add_workload_balance_soft_constraint(model, x, student, eligible_courses, remaining_semesters)
#         diversity_rewards = self.add_diversity_reward_soft_constraint(model, x, eligible_courses, remaining_semesters)
#         credit_limit_exceeding = self.add_total_credit_limit_exceeding_penalty(model, x, student, eligible_courses, remaining_semesters)
        
#         print("\n" + "="*80)
#         print("🔍 LLM CALL RESULT CHECK")
#         print("="*80)
#         print(f"llm_weights type: {type(llm_weights)}")
#         print(f"llm_weights is None: {llm_weights is None}")
#         if llm_weights:
#             print(f"llm_weights has 'courses': {'courses' in llm_weights}")
#             if 'courses' in llm_weights:
#                 print(f"Number of courses: {len(llm_weights['courses'])}")
#         else:
#             print("⚠️ WARNING: llm_weights is None! LLM call failed or returned None")
#         print("="*80 + "\n")
        
#         # Store LLM weights for UI access
#         self.last_llm_weights = llm_weights
        
#         print(f"✅ Stored to self.last_llm_weights: {self.last_llm_weights is not None}")
#         course_interest_weights_dict = self.add_course_interest_soft_constraint(eligible_courses, llm_weights)
#         self.set_objective(model, x, student, eligible_courses, remaining_semesters, failed_courses, workload_penalties, course_interest_weights_dict, weights, diversity_rewards, credit_limit_exceeding)
        
#         # print("\n=== CONSTRAINT DEBUG ===")

#         # # Check mandatory courses
#         # mandatory_remaining = [c for c in self.loader.get_remaining_mandatory_courses(student) if c in eligible_courses]
#         # mandatory_credits_total = sum(self.loader.get_credits(c) for c in mandatory_remaining)
#         # print(f"Mandatory courses remaining: {len(mandatory_remaining)}")
#         # print(f"Mandatory credits: {mandatory_credits_total}")

#         # # Check if all mandatory can fit in 4 semesters
#         # print(f"Max credits per semester: {MAX_CREDITS}")
#         # print(f"Total max credits in 4 sems: {MAX_CREDITS * 4} = {25 * 4} = 100")
#         # print(f"Can fit mandatory? {mandatory_credits_total <= 100}")

#         # # Check Combined Elective specifically
#         # de_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Discipline Elective']
#         # oe_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Open Elective']
#         # me_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Multidisciplinary Elective']

#         # combined_available = sum(self.loader.get_credits(c) for c in de_courses + oe_courses + me_courses)
#         # print(f"\nCombined Elective available: {combined_available} credits")
#         # print(f"Combined Elective needed: 30 credits")
#         # print(f"Can meet? {combined_available >= 30}")

#         # # Check Non-graded
#         # ng_courses = [c for c in eligible_courses if self.loader.get_course_by_code(c).get('course_type') == 'Non-graded Core Requirement']
#         # ng_available = sum(self.loader.get_credits(c) for c in ng_courses)
#         # print(f"\nNon-graded available: {ng_available} credits")
#         # print(f"Non-graded needed: 11 credits")
#         # print(f"Can meet? {ng_available >= 11}")

#         # print("\n" + "="*50)

#         # print("\n=== SEMESTER 5 DETAILED DEBUG ===")
#         # failed_course = 'BMAT201L'
#         # failed_slots = self.loader.get_course_by_code(failed_course).get('slots', [])
#         # print(f"Failed course: {failed_course}")
#         # print(f"Failed course slots: {failed_slots}")
#         # print(f"Failed course credits: {self.loader.get_credits(failed_course)}")

#         # # Find courses available for sem 5
#         # sem5_eligible = []
#         # for course in eligible_courses:
#         #     if course == failed_course:
#         #         continue
            
#         #     course_info = self.loader.get_course_by_code(course)
            
#         #     # Check year unlock
#         #     year_offered = course_info.get('year_offered', 4)
#         #     if year_offered > 3:  # Sem 5 is year 3
#         #         continue
            
#         #     # Check prerequisites
#         #     preqs = self.loader.get_prerequisites(course)
#         #     preqs_met = all(p in student.completed_courses for p in preqs)
#         #     if not preqs_met:
#         #         continue
            
#         #     # Check slot conflict with failed course
#         #     course_slots = course_info.get('slots', [])
#         #     has_conflict = any(slot in failed_slots for slot in course_slots)
            
#         #     sem5_eligible.append({
#         #         'code': course,
#         #         'credits': self.loader.get_credits(course),
#         #         'slots': course_slots,
#         #         'conflicts_with_failed': has_conflict,
#         #         'type': course_info.get('course_type')
#         #     })

#         # print(f"\nCourses available for Sem 5: {len(sem5_eligible)}")
#         # print(f"Courses WITHOUT slot conflict: {len([c for c in sem5_eligible if not c['conflicts_with_failed']])}")

#         # # Check if we can meet 17 credits
#         # non_conflict_credits = sum(c['credits'] for c in sem5_eligible if not c['conflicts_with_failed'])
#         # print(f"\nTotal credits available (no conflict): {non_conflict_credits}")
#         # print(f"Need (including failed course): 17 credits")
#         # print(f"Need (excluding failed course 4 cr): 13 credits")
#         # print(f"Can meet minimum? {non_conflict_credits >= 13}")

#         # # Show some available courses
#         # print("\nSample available courses (no conflict with failed):")
#         # for c in sem5_eligible[:10]:
#         #     if not c['conflicts_with_failed']:
#         #         print(f"  {c['code']}: {c['credits']}cr, {c['type']}, slots: {c['slots']}")


#         solver = cp_model.CpSolver()
#         solver.parameters.max_time_in_seconds = 30.0
#         solver.parameters.random_seed = 42
#         solver.parameters.num_search_workers = 8
    
#         # # 3. Disable any parallel features
#         # solver.parameters.interleave_search = False
#         # solver.parameters.share_objective_bounds = False
#         # solver.parameters.share_level_zero_bounds = False
        
#         # # 4. Use deterministic search strategy
#         # solver.parameters.search_branching = cp_model.FIXED_SEARCH
#         # solver.parameters.linearization_level = 2


#         # solver.parameters.log_search_progress = True

#         self._ui_log("⚡ Running CP-SAT solver...")
#         status = solver.Solve(model)

#         # for constraint in model.Proto().constraints:
#             # print('constraints : ', constraint)
        
#         # solver.parameters.cp_model_presolve = True
#         # solver.parameters.find_multiple_cores = True 


#         if status == cp_model.OPTIMAL:
#             self._ui_log("✅ Found optimal solution!")
#             plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
#             self.print_plan(plan, student)

#             # Generate explanations after successful plan generation
#             print("\n" + "="*80)
#             print("🤖 GENERATING PLAN EXPLANATIONS")
#             print("="*80)
#             self._ui_log("🤖 Generating plan explanation with AI...")
#             plan_explanation = self.generate_plan_explanation(student, plan, llm_weights, course_interest_weights_dict)
#             self.last_plan_explanation = plan_explanation
#             print("✅ Explanations generated successfully")
#             self._ui_log("✅ Plan explanation ready!")

#             return plan, plan_explanation
#         elif status == cp_model.FEASIBLE:
#             print('Found feasible solution')
#             self._ui_log("✅ Found feasible solution!")
#             plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
#             self.print_plan(plan, student)
            
#             # Generate explanations after successful plan generation
#             print("\n" + "="*80)
#             print("🤖 GENERATING PLAN EXPLANATIONS")
#             print("="*80)
#             self._ui_log("🤖 Generating plan explanation with AI...")
#             plan_explanation = self.generate_plan_explanation(student, plan, llm_weights, course_interest_weights_dict)
#             self.last_plan_explanation = plan_explanation
#             print("✅ Explanations generated successfully")
#             self._ui_log("✅ Plan explanation ready!")
            
#             return plan, plan_explanation
#         else:
#             print('No solution found')
#             self._ui_log("❌ No solution found — diagnosing issue...")
#             print('Status :', solver.StatusName(status))
#             reasons = self.diagnose_infeasibility(student, eligible_courses, failed_courses, remaining_semesters)
#             print("🔍 Infeasibility reasons:")
#             for r in reasons:
#                 print(f"  ❌ {r}")
#             return {sem: [] for sem in remaining_semesters}, None


#         # print("\n=== CATEGORY REQUIREMENT DETAILED ANALYSIS ===")

#         # completed = set(student.completed_courses)
#         # earned_by_category = defaultdict(int)

#         # for course_code in completed:
#         #     course = self.loader.get_course_by_code(course_code)
#         #     if course:
#         #         category = course['course_type']
#         #         earned_by_category[category] += self.loader.get_credits(course_code)

#         # print("\nCredits earned by category:")
#         # for cat, creds in earned_by_category.items():
#         #     print(f"  {cat}: {creds} credits")

#         # print("\nChecking each category requirement:")
#         # for category, requirements in self.loader.credit_requirements.items():
#         #     required = requirements.get('required', 0)
#         #     already_earned = earned_by_category.get(category, 0)
            
#         #     if already_earned >= required:
#         #         print(f"\n✓ {category}: SATISFIED ({already_earned}/{required})")
#         #         continue
            
#         #     print(f"\n⚠ {category}: Need {required - already_earned} more credits ({already_earned}/{required})")
            
#         #     # Find available courses for this category
#         #     if category == 'Combined Elective':
#         #         category_courses = [
#         #             c for c in eligible_courses  
#         #             if self.loader.get_course_by_code(c).get('course_type', '') in
#         #             ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
#         #         ]
#         #     else:
#         #         category_courses = [
#         #             c for c in eligible_courses 
#         #             if self.loader.get_course_by_code(c).get('course_type', '') == category
#         #         ]
            
#         #     total_available = sum(self.loader.get_credits(c) for c in category_courses)
#         #     can_satisfy = (total_available + already_earned) >= required
            
#         #     print(f"  Available courses: {len(category_courses)}")
#         #     print(f"  Available credits: {total_available}")
#         #     print(f"  Total (earned + available): {already_earned + total_available}")
#         #     print(f"  Can satisfy? {can_satisfy}")
            
#         #     if not can_satisfy:
#         #         print(f"  ❌ IMPOSSIBLE TO SATISFY!")
#         #         print(f"     Need: {required}")
#         #         print(f"     Have: {already_earned}")
#         #         print(f"     Can get: {total_available}")
#         #         print(f"     Shortage: {required - (already_earned + total_available)}")
            
#         #     # Show which courses are available
#         #     if len(category_courses) > 0:
#         #         print(f"  Sample courses:")
#         #         for c in category_courses[:5]:
#         #             print(f"    - {c}: {self.loader.get_credits(c)}cr")

#         # # Call debug instead of solving
#         # self.debug_constraints(student, eligible_courses, failed_courses, remaining_semesters)
#         # return {sem: [] for sem in remaining_semesters}

    
#     def generate_complete_plan(self, student):
#         print("\n" + "="*80)
#         print("🎓 GENERATING MULTIPLE COURSE PLANS")
#         print("="*80)

#         remaining_semesters = list(range(student.current_semester, 9))
#         print("Generating recommendations for semesters:", remaining_semesters)

#         eligible_courses, failed_courses = self.get_eligible_and_failed_courses(student)
        
#         # DEBUG: Print counts
#         print(f"\n=== DEBUG ===")
#         print(f"Eligible courses: {len(eligible_courses)}")
#         print(f"Failed courses: {len(failed_courses)}")
        
#         # Check remaining requirements
#         remaining = self.loader.get_remaining_credits_by_type(student)
#         print(f"\nRemaining credits needed:")
#         for cat, creds in remaining.items():
#             print(f"  {cat}: {creds} credits")
        
#         # Check if enough courses available
#         total_needed = sum(remaining.values())
#         total_available = sum(self.loader.get_credits(c) for c in eligible_courses)
#         print(f"\nTotal credits needed: {total_needed}")
#         print(f"Total credits available: {total_available}")
#         # print("="*80)
#         # print('COMPLETE PLAN')
#         # print("="*80)

#         # remaining_semesters = list(range(student.current_semester, 9))
#         # print("Generating recommendations for semesters:", remaining_semesters)

#         # eligible_courses, failed_courses = self.get_eligible_and_failed_courses(student)
        
#         llm_weights = self.get_course_interest_weights_from_llm(student, eligible_courses)

#         results = {}
        
#         # Generate each plan type
#         for plan_type, config in PLAN_CONFIGS.items():
#             plan, explanation = self.generate_single_plan(
#                 student,
#                 eligible_courses,
#                 remaining_semesters,
#                 failed_courses,
#                 llm_weights,
#                 weights=config['weights'],
#             )
            
#             if plan and any(plan.values()) and explanation:
                
#                 results[plan_type] = {
#                     'config': config,
#                     'plan': plan,
#                     'explanation': explanation,
#                 }
                
#                 print(f"\n✅ {config['name']} completed:")

#             else:
#                 print(f"\n❌ {config['name']} failed to generate")
        
#         print("\n" + "="*80)
#         print(f"✅ Generated {len(results)}/2 plans successfully")
#         print("="*80 + "\n")
        
#         return results


#     def get_eligible_and_failed_courses(self, student):
#         completed = set(student.completed_courses)
#         failed = set(student.failed_courses)
#         all_courses = self.loader.get_all_course_codes()

#         eligible = []
#         for course_code in all_courses:
#             if course_code in completed:
#                 continue

#             eligible.append(course_code)
        
#         return eligible, failed

#     def _create_variables(self, model, eligible_courses, semesters):
#         x = {}
#         for course in eligible_courses:
#             for sem in semesters:
#                 x[course, sem] = model.new_bool_var(f'{course}_semester{sem}')
        
#         return x
    
#     def add_course_can_be_taken_only_once_constraint(self, model, x, courses, semesters):
#         for course in courses:
#             model.add(sum(x[course, sem] for sem in semesters) <= 1)
    
#     def add_course_already_completed_constraint(self, model, x, student, courses, semesters):
#         completed = set(student.completed_courses)
#         for course in courses:
#             if course in completed:
#                 for sem in semesters:
#                     model.add(x[course, sem] == 0)
    
#     def add_preq_check_constraint(self, model, x, student, courses, semesters):
#         completed = set(student.completed_courses)

#         for course in courses:
#             preqs = self.loader.get_prerequisites(course)
#             if not preqs:
#                 continue

#             for sem in semesters:
#                 for preq in preqs:
#                     if preq in completed:
#                         continue

#                     if preq not in courses:
#                         print('Prerequisite not in completed and also it is not in eligible course pool')   
#                         model.add(1 == 0)
#                         continue
                    
#                     past_sems = [s for s in semesters if s < sem]

#                     if not past_sems:
#                         model.add(x[course, sem] == 0)

#                     if past_sems and preq in courses:

#                         # a constraint telling the solver to only consider the current course in this current sem only if its preq are satisfied in previous sems
#                         model.add(
#                             x[course, sem] <= sum(x[preq, s] for s in past_sems)
#                         )
    
#     def add_min_max_credit_constraint(self, model, x, courses, semesters):

#         for sem in semesters:
#             sem_creds = sum(
#                 self.loader.get_credits(c) * x[c, sem]
#                 for c in courses
#             )

#             model.add(sem_creds >= MIN_CREDITS)
#             model.add(sem_creds <= MAX_CREDITS)

#     def add_slot_conflict_constraint(self, model, x, courses, semesters):
#         for sem in semesters:
#             for i, c1 in enumerate(courses):
#                 for c2 in courses[i+1: ]:
#                     if not self.loader.can_take_together(c1, c2):
#                         model.add(x[c1, sem] + x[c2, sem] <= 1)
            
#             break

#     def add_theory_lab_pairing_constraint(self, model, x, student, courses, semesters):
#         completed = set(student.completed_courses)
#         for course in courses:
#             if self.loader.get_lab_course(course):
#                 lab = self.loader.get_lab_course(course)
#                 if lab and lab in courses and lab not in completed:
#                     for sem in semesters:
#                         model.add(x[course, sem] == x[lab, sem])
    
#     def add_category_credit_requirement_constraint(self, model, x, student, courses, semesters):
#         completed = set(student.completed_courses)
#         earned_by_category = defaultdict(int)

#         for course_code in completed:
#             course = self.loader.get_course_by_code(course_code)
#             if course:
#                 category = course['course_type']
#                 earned_by_category[category] += self.loader.get_credits(course_code)

#         for category, requirements in self.loader.credit_requirements.items():
#             required = requirements.get('required', 0)
#             already_earned = earned_by_category.get(category, 0)

#             if already_earned >= required:
#                 continue
        
#             category_courses = [c for c in courses if self.loader.get_course_by_code(c).get('course_type', '') == category]
#             if category == 'Combined Elective':
#                 category_courses = [
#                     c for c in courses  
#                     if self.loader.get_course_by_code(c).get('course_type', '') in
#                     ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
#                 ]

#             if not category_courses:
#                 print(f"Cannot meet {category} requirement!")
#                 print(f"Required: {required}, Earned: {already_earned}, Shortage: {required - already_earned}")
#                 model.add(1 == 0)
#                 continue
        
#             future_credits = sum(
#                 self.loader.get_credits(c) * x[c, sem]
#                 for c in category_courses
#                 for sem in semesters
#             )

#             model.add(future_credits + already_earned >= required)

#     def add_project_constraint(self, model, x, courses, semesters):
#         project_courses = [
#             c for c in courses
#             if self.loader.get_course_by_code(c).get('course_type') == 'Projects and Internship'
#         ]

#         project1 = 'BCSE497J'
#         project2 = 'BCSE498J'
#         internship = 'BCSE499J'
#         for course in project_courses:
#             for sem in semesters:
#                 if(course == project1):
#                     if(sem == 7):
#                         model.add(x[course, sem] == 1)
#                     else:
#                         model.add(x[course, sem] == 0)
                
#                 elif(course == project2 or course == internship):
#                     if(sem == 8):
#                         model.add(x[course, sem] == 1)
#                     else:
#                         model.add(x[course, sem] == 0)
                
#                 else:
#                     if(sem < 7):
#                         model.add(x[course, sem] == 0)
    
#     def add_failed_courses_retake_constraint(self, model, x, failed_courses, semesters):
#         for c in failed_courses:
#             model.add(sum(x[c, s] for s in semesters) == 1)

#     def add_mandatory_courses_completion_constraint(self, model, x, courses, semesters):
#         for c in courses:
#            if self.loader.get_course_by_code(c).get('is_mandatory', False):
#                model.add(sum(x[c, s] for s in semesters) == 1)

#     def add_total_min_credits_req_for_graduation(self, model, x, student, courses, semesters):
#         completed = student.completed_courses
#         credits_earned_so_far = round(sum([self.loader.get_credits(c) for c in completed]))
#         min_credits_required = TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE - credits_earned_so_far
#         # print('eyuyuyuyuyu : ', TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE, credits_earned_so_far, min_credits_required, [self.loader.get_credits(c) for c in completed])
#         model.add(
#             sum(
#                 self.loader.get_credits(c) * x[c, s]
#                 for c in courses
#                 for s in semesters
#             ) >= min_credits_required
#         )

#     def add_year_level_course_unlock_constraint(self, model, x, courses, semesters):
#         for course in courses:
#             course_unlock_year = self.loader.get_course_by_code(course).get('year_offered', 4)
#             for sem in semesters:
#                 year = (sem+1)//2
#                 if(year < course_unlock_year):
#                     model.add(x[course, sem] == 0)

#     def add_max_allowed_courses_per_semester(self, model, x, courses, semesters):
#         for sem in semesters:
#             model.add(
#                 sum(x[c, sem] for c in courses) <= MAX_ALLOWED_COURSES_PER_SEM
#             )

#     def add_hard_constraints(self, model, x, student, eligible_courses, failed_courses, remaining_semesters):
#         self.add_course_already_completed_constraint(model, x, student, eligible_courses, remaining_semesters)
#         self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
#         self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#         self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#         self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#         self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
#         self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#         self.add_theory_lab_pairing_constraint(model, x, student, eligible_courses, remaining_semesters)  
#         self.add_failed_courses_retake_constraint(model, x, failed_courses, remaining_semesters)
#         self.add_total_min_credits_req_for_graduation(model, x, student, eligible_courses, remaining_semesters)
#         self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
#         self.add_max_allowed_courses_per_semester(model, x, eligible_courses, remaining_semesters)
#         self.add_mandatory_courses_completion_constraint(model, x, eligible_courses, remaining_semesters)


#     def add_workload_balance_soft_constraint(self, model, x, student, courses, semesters):
#         workload_preference = student.workload_preference or 'medium'
#         penalty_vars = []
#         ranges = RANGES

#         current_semester = semesters[0]
#         future_semesters = semesters[1: ] if len(semesters) > 1 else []

#         current_sem_preference = ranges[workload_preference]
#         min_target, max_target = current_sem_preference
#         current_sem_credits = sum([self.loader.get_credits(c) * x[c, current_semester] for c in courses])

#         # will penalize if credits are below the min_target
#         under_penalty = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{current_semester}')
#         model.add(under_penalty >= min_target - current_sem_credits)

#         # will penalize if credits are above the max_target
#         over_penalty = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{current_semester}')
#         model.add(over_penalty >= current_sem_credits - max_target)

#         penalty_vars.extend([under_penalty, over_penalty])

#         # we consider balanced workload for future sems
#         for sem in future_semesters:
#             sem_credits = sum([self.loader.get_credits(c) * x[c, sem] for c in courses])
#             min_target, max_target = ranges['medium']

#             under_penalty = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{sem}')
#             model.add(under_penalty >= min_target - sem_credits)

#             over_penalty = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{sem}')
#             model.add(over_penalty >= sem_credits - max_target)

#             penalty_vars.extend([under_penalty, over_penalty])
        

#         return penalty_vars
    

#     def add_difficulty_balance_soft_constraint(self, model, x, student, courses, semesters):
#         difficulty_preference = 'medium'

    
#     def add_total_credit_limit_exceeding_penalty(self, model, x, student, courses, semesters):
#         completed_courses = set(student.completed_courses)

#         credits_earned_so_far = round(sum(self.loader.get_credits(c) for c in completed_courses))
#         SUFFFICIENT_TOTAL = TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE - credits_earned_so_far

#         total_future_credits = sum(
#             self.loader.get_credits(c) * x[c, s]
#             for c in courses
#             for s in semesters
#         )


#         MAX_POSSIBLE_CREDITS_TO_EARN = MAX_CREDITS * TOTAL_SEMS
#         credit_exceed = model.new_int_var(0, MAX_POSSIBLE_CREDITS_TO_EARN, 'total_credit_exceed')
#         model.add(credit_exceed >= (credits_earned_so_far + total_future_credits) - TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE)

#         return [credit_exceed]


    
#     def get_course_interest_weights_from_llm(self, student, courses):
        
#         # Build compact course list
#         course_list = []
#         for course_code in courses:
#             course_info = self.loader.get_course_by_code(course_code)
#             course_list.append({
#                 "code": course_code,
#                 "name": course_info['course_name'],
#                 "type": course_info.get('course_type', 'Unknown')
#             })

#         # print('coruse list : ', course_list)
#         self._ui_log(f"🤖 AI analyzing {len(course_list)} courses against your interests and grade history...")
        
#         prompt = f"""You are an academic advisor analyzing course-interest alignment.

#             TASK:
#             Rate how well each course matches the student's stated interests.

#             STUDENT INTERESTS:
#             {json.dumps(student.interest_areas, indent=2)}

#             COURSES TO RATE:
#             {json.dumps(course_list, indent=2)}

#             RATING GUIDELINES:

#             Score 0.9 - 1.0: Perfect Match
#             - Course title/content directly mentions student's core interests
#             - Example: Student likes "Machine Learning" → Course is "Machine Learning Fundamentals"

#             Score 0.7 - 0.8: Strong Match
#             - Course closely related to interests
#             - Example: Student likes "AI" → Course is "Neural Networks" or "Computer Vision"

#             Score 0.5 - 0.6: Moderate Match
#             - Course somewhat related or complementary
#             - Example: Student likes "Web Development" → Course is "Database Systems"

#             Score 0.3 - 0.4: Weak Match
#             - Course tangentially related or prerequisite to interests
#             - Example: Student likes "Cybersecurity" → Course is "Operating Systems"

#             Score 0.0 - 0.2: No Match
#             - Course unrelated to stated interests
#             - Example: Student likes "Software Engineering" → Course is "Analog Electronics"

#             CRITICAL RULES:
#             1. Base scores ONLY on interest alignment, nothing else
#             2. Ignore student's CGPA, year, or past performance
#             3. Ignore course difficulty or workload
#             4. Ignore graduation requirements (mandatory/elective status)
#             5. Focus purely on: Does this course topic match what the student is interested in?

#             OUTPUT FORMAT (strict JSON):
#             {{
#             "courses": {{
#                 {{
#                 "code": "BCSE306L",
#                 "name": "Artificial Intelligence",
#                 "weight": 0.95,
#                 "reason": "Directly matches core AI interest"
#                 }},
#                 {{
#                 "code": "BCSE301L",
#                 "name": "Software Engineering",
#                 "weight": 0.60,
#                 "reason": "Related to software development interest"
#                 }}
#             }}
#             }}

#             Rate ALL {len(course_list)} courses. Return ONLY valid JSON, no additional text."""

#         try:
#             response = self.client.responses.parse(
#                 model=self.model,
#                 input=[
#                     {
#                         "role": "system",
#                         "content": """You are an expert academic advisor specializing in course-interest matching.

#                             Your ONLY job: Determine how well each course aligns with student's stated interests.

#                             You MUST:
#                             - Rate based purely on interest-topic alignment
#                             - Provide specific, concrete reasons
#                             - Be consistent in your scoring
#                             - Return valid JSON only

#                             You MUST NOT:
#                             - Consider student's grades or performance
#                             - Consider course difficulty
#                             - Consider graduation requirements
#                             - Make assumptions beyond the interest areas provided
#                             - Hallucinate course content not in the course name/type"""
#                     },
#                     {
#                         "role": "user",
#                         "content": prompt
#                     }
#                 ],
#                 text_format=WeightsList,
#             )
            
#             parsed_output = response.output_parsed
#             self._ui_log(f"✅ AI analysis complete — {len(parsed_output.courses)} courses weighted")
#             return parsed_output
            
#         except json.JSONDecodeError as e:
#             print(f"✗ Error parsing LLM response: {e}")
#             return None
        
#         except Exception as e:
#             print(f"✗ Error in LLM call: {e}")
#             return None

#     def add_course_interest_soft_constraint(self, courses, llm_weights):
#         print(llm_weights)
#         weights_dict = dict()
#         if llm_weights and llm_weights.courses:
#             for course_weight in llm_weights.courses:
#                 weights_dict[course_weight.code] = (course_weight.weight, course_weight.name, course_weight.reason)
        
#         print('Totla courses weighted : ', len(weights_dict))

#         for course in courses:
#             weighted_courses = set(weights_dict.keys())
#             if course not in weighted_courses:
#                 weights_dict[course] = (0.5, self.loader.get_course_by_code(course).get('course_name'), 'Default value set')
#                 print('Using default weight for course : ', course)
        
#         return weights_dict


#     def add_lateness_penalty(self, course_code, sem):
#         course_info = self.loader.get_course_by_code(course_code)
#         year_offered = course_info.get('year_offered', 1)

#         better_complete_before_sem = (year_offered + 1) * 2
#         if(sem <= better_complete_before_sem):
#             return 0
        
#         sems_late = sem - better_complete_before_sem
#         is_mandatory = course_info.get('is_mandatory', False)

#         unlock_chain_size = 1
#         if(self.unlock_chain_sizes.get(course_code) != None):
#             unlock_chain_size = self.unlock_chain_sizes[course_code] + 1

#         return sems_late * (2 if is_mandatory else 1) * unlock_chain_size


#     def add_diversity_reward_soft_constraint(self, model, x, courses, semesters):
#         CATEGORIES_TO_BALANCE = {
#             'Discipline Elective',
#             'Open Elective',
#             'Non-graded Core Requirements'
#         }

#         reward_vars = []

#         for sem in semesters[::-1]:
#             for cat in CATEGORIES_TO_BALANCE:
#                 category_courses = [c for c in courses if self.loader.get_course_by_code(c).get('course_type', '') == cat]
#                 if not category_courses:
#                     continue

#                 present = model.new_bool_var(f'{cat}_present_sem{sem}')
#                 model.add(sum(x[c, sem] for c in category_courses) >= present)
#                 model.add(present <= sum(x[c, sem] for c in category_courses))

#                 reward_vars.append(present)
        
#         return reward_vars


#     def set_objective(self, model, x, student, courses, semesters, failed_courses, workload_penalties, course_interest_weights_dict, weights, diversity_rewards, credit_limit_exceeding):        
#         w_mandatory = weights.get('mandatory', 100)
#         w_unlock = weights.get('unlock', 30)
#         w_interest = weights.get('interest', 30)
#         w_workload = weights.get('workload', 60)
#         w_failed = weights.get('failed', 200)
#         w_lateness = weights.get('lateness', 75)
#         w_diversity = weights.get('diversity', 30)
#         w_credit_limit_exceed = weights.get('credit_limit_exceed', 30)


#         mandatory_courses = self.loader.get_remaining_mandatory_courses(student)
#         mandatory_score = sum(
#             x[c, s] * (TOTAL_SEMS - s + 1)
#             for c in mandatory_courses if c in courses for s in semesters
#         )

#         unlock_score = sum(
#             len(self.loader.course_unlocks.get(c, [])) * x[c, s] * (TOTAL_SEMS - s + 1)
#             for c in courses for s in semesters
#         )

#         print('WORKLOAD PENALTIES : ', workload_penalties)
#         workload_penalty_total = sum(workload_penalties)


#         interest_score = sum(
#             int(round(course_interest_weights_dict.get(c, (0.5, self.loader.get_course_by_code(c).get('course_name'), 'Default value set'))[0] * INTEREST_SCALE)) * x[c, s] * (TOTAL_SEMS - s + 1)
#             for c in courses
#             for s in semesters
#         )


#         failed_course_urgency_score = sum(
#             (TOTAL_SEMS - s + 1) * x[c, s]
#             for c in failed_courses if c in courses
#             for s in semesters
#         )


#         lateness_penalty_total = sum(
#             self.add_lateness_penalty(c, s) * x[c, s]
#             for c in courses
#             for s in semesters
#         )

        
#         diversity_reward_total = sum(diversity_rewards)


#         credit_limit_exceed_penalty = sum(credit_limit_exceeding)


#         # preq_taken_semester = 1
#         # preq_non_freshness_penalty_total = sum(
#         #     x[c, s] * (s - preq_taken_semester)
#         #     for c in courses
#         #     for s in semesters
#         #     for preq in self.loader.get_prerequisites(c)
#         # )


#         model.maximize(
#             w_mandatory * mandatory_score 
#             + 
#             w_unlock * unlock_score
#             +
#             w_interest * interest_score
#             +
#             w_failed * failed_course_urgency_score
#             +
#             w_diversity * diversity_reward_total
#             -
#             w_workload * workload_penalty_total
#             -
#             w_lateness * lateness_penalty_total
#             -
#             w_credit_limit_exceed * credit_limit_exceed_penalty
#         )
    
#     def get_solution(self, solver, x, courses, semesters):
#         plan = {sem: [] for sem in semesters}

#         for course in courses:
#             for sem in semesters:
#                 if solver.Value(x[course, sem]) == 1:
#                     plan[sem].append(course)
        
#         return plan

#     def print_plan(self, plan, student):
#         print("\n" + "="*80)
#         print("📋 PLAN SUMMARY")
#         print("="*80)
        
#         completed = student.completed_courses
#         credits_earned_so_far = round(sum([self.loader.get_credits(c) for c in completed]))

#         total_courses = 0
#         total_credits = 0
        
#         for sem in sorted(plan.keys()):
#             courses = plan[sem]
#             credits = sum(self.loader.get_credits(c) for c in courses)
#             total_courses += len(courses)
#             total_credits += credits
            
#             print(f"\nSemester {sem}: {len(courses)} courses, {credits} credits")
#             for course in courses:
#                 course_info = self.loader.get_course_by_code(course)
#                 if course_info:
#                     print(f"  • {course}: {course_info['course_name']} ({self.loader.get_credits(course)} cr)")
        
#         print("\n" + "="*80)
#         print(f"Total: {total_courses} courses, {total_credits} credits")
#         print(f"Credits earned so far: {credits_earned_so_far}")
#         print(f"Total after plan: {credits_earned_so_far + total_credits}")
#         print(f"Required for graduation: {TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE}")
#         print("="*80 + "\n")



    
#     # def debug_constraints(self, student, eligible_courses, failed_courses, remaining_semesters):
#     #     """Test each constraint individually to find which makes the problem infeasible"""
        
#     #     print("\n" + "="*80)
#     #     print("CONSTRAINT DEBUGGING - Testing each constraint individually")
#     #     print("="*80)
        
#     #     # Test 1: Bare minimum - just credit bounds
#     #     print("\n[TEST 1] Only credit bounds (17-25)")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 2: Add once-only constraint
#     #     print("\n[TEST 2] + Course taken only once")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 3: Add failed course constraint
#     #     print("\n[TEST 3] + Failed course must be retaken")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 4: Add slot conflicts
#     #     print("\n[TEST 4] + Slot conflicts (sem 5 only)")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 5: Add theory-lab pairing
#     #     print("\n[TEST 5] + Theory-lab pairing")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 6: Add prerequisites
#     #     print("\n[TEST 6] + Prerequisites")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 7: Add project constraints
#     #     print("\n[TEST 7] + Project constraints")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 8: Add year unlock
#     #     print("\n[TEST 8] + Year unlock")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 9: Add category requirements
#     #     print("\n[TEST 9] + Category credit requirements")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     # Test 10: Add total credits requirement
#     #     print("\n[TEST 10] + Total credits for graduation")
#     #     model = cp_model.CpModel()
#     #     x = self._create_variables(model, eligible_courses, remaining_semesters)
#     #     self.add_min_max_credit_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_course_can_be_taken_only_once_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_failed_courses_immediate_retake_constraint(model, x, failed_courses, remaining_semesters)
#     #     self.add_slot_conflict_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_theory_lab_pairing_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_preq_check_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     self.add_project_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_year_level_course_unlock_constraint(model, x, eligible_courses, remaining_semesters)
#     #     self.add_category_credit_requirement_constraint(model, x, student, eligible_courses, remaining_semesters)
#     #     self.add_total_min_credits_req_for_graduation(model, x, student, eligible_courses, remaining_semesters)
#     #     solver = cp_model.CpSolver()
#     #     solver.parameters.max_time_in_seconds = 5.0
#     #     status = solver.Solve(model)
#     #     print(f"Result: {solver.StatusName(status)}")
        
#     #     print("\n" + "="*80)


#     def generate_plan_explanation(self, student, plan, llm_weights, course_interest_weights_dict):
#         """
#         Generate comprehensive explanations for why each course was selected 
#         and why it was placed in a specific semester using LLM.
#         """

#         self._ui_log("📝 Generating personalized course explanations...")
        
#         # Prepare context data
#         student_context = {
#             "name": student.name,
#             "student_id": student.student_id,
#             "current_semester": student.current_semester,
#             "cgpa": student.cgpa,
#             "interest_areas": student.interest_areas if hasattr(student, 'interest_areas') else [],
#             "workload_preference": student.workload_preference or "medium",
#             "completed_courses_count": len(student.completed_courses),
#             "failed_courses": student.failed_courses
#         }
        
#         # Prepare plan data with rich context
#         plan_data = []
#         for sem in sorted(plan.keys()):
#             if not plan[sem]:
#                 continue
                
#             sem_courses = []
#             sem_credits = 0
            
#             for course_code in plan[sem]:
#                 course_info = self.loader.get_course_by_code(course_code)
#                 if not course_info:
#                     continue
                    
#                 credits = self.loader.get_credits(course_code)
#                 sem_credits += credits
                
#                 # Get prerequisites
#                 prereqs = self.loader.get_prerequisites(course_code)
#                 prereq_names = []
#                 for p in prereqs:
#                     p_info = self.loader.get_course_by_code(p)
#                     if p_info:
#                         prereq_names.append(f"{p} ({p_info['course_name']})")
                
#                 # Get courses this unlocks
#                 unlocks = self.loader.course_unlocks.get(course_code, [])
#                 unlock_names = []
#                 for u in unlocks:
#                     u_info = self.loader.get_course_by_code(u)
#                     if u_info:
#                         unlock_names.append(f"{u} ({u_info['course_name']})")
                
#                 # Get interest weight
#                 interest_weight_info = course_interest_weights_dict.get(
#                     course_code, 
#                     (0.5, course_info.get('course_name'), 'Not weighted')
#                 )
                
#                 sem_courses.append({
#                     "code": course_code,
#                     "name": course_info['course_name'],
#                     "credits": credits,
#                     "type": course_info.get('course_type', 'Unknown'),
#                     "is_mandatory": course_info.get('is_mandatory', False),
#                     "is_failed_retake": course_code in student.failed_courses,
#                     "difficulty": course_info.get('difficulty', 50),
#                     "pass_rate": course_info.get('pass_rate', 0.8),
#                     "prerequisites": prereq_names,
#                     "unlocks": unlock_names,
#                     "interest_weight": interest_weight_info[0],
#                     "interest_reason": interest_weight_info[2],
#                     "slots": course_info.get('slots', [])
#                 })
            
#             plan_data.append({
#                 "semester": sem,
#                 "total_credits": sem_credits,
#                 "course_count": len(sem_courses),
#                 "courses": sem_courses
#             })
        
#         # Get remaining requirements
#         remaining_requirements = self.loader.get_remaining_credits_by_type(student)
        
#         # Build the prompt
#         prompt = f"""You are an expert academic advisor with deep knowledge of curriculum planning, 
#             course prerequisites, and student success strategies. 

#             TASK:
#             Generate a comprehensive, personalized explanation for this student's course plan. 
#             Explain WHY each course was selected and WHY it was placed in its specific semester.

#             STUDENT PROFILE:
#             {json.dumps(student_context, indent=2)}

#             REMAINING REQUIREMENTS:
#             {json.dumps(remaining_requirements, indent=2)}

#             GENERATED COURSE PLAN:
#             {json.dumps(plan_data, indent=2)}

#             EXPLANATION REQUIREMENTS:

#             For the OVERALL PLAN:
#             1. Summarize the strategic approach to graduation (2-3 sentences)
#             2. Explain how this plan addresses the student's interests and workload preference
#             3. Highlight the graduation path trajectory (e.g., "Front-loads mandatory courses, saves electives for later")

#             For EACH SEMESTER:
#             1. Overall semester strategy (1-2 sentences explaining the focus/theme)
#             2. Workload reasoning (why this specific credit load makes sense)

#             For EACH COURSE in EACH SEMESTER:
#             1. **Why Selected**: 
#             - Is it mandatory for graduation? 
#             - Does it align with student interests (reference the interest_weight)?
#             - Is it a failed course that must be retaken?
#             - Does it satisfy a specific requirement category?

#             2. **Why This Semester**:
#             - Are prerequisites satisfied by this point?
#             - Does it unlock important future courses (mention which ones)?
#             - Does it fit the student's current workload preference?
#             - Are there slot/scheduling constraints?
#             - Is this the earliest possible semester for this course?

#             3. **Prerequisites Context**:
#             - List which prerequisites were already completed or will be completed
#             - Explain why the student is ready for this course now

#             4. **Interest Alignment**:
#             - Reference the interest_weight score
#             - Explain how this course connects to student's stated interests
#             - Use the interest_reason from the weight analysis

#             5. **Strategic Value**:
#             - What future courses does this unlock?
#             - How does this contribute to graduation requirements?
#             - Does this help maintain GPA or reduce risk?

#             IMPORTANT INSTRUCTIONS:
#             - Be specific and reference actual data (course codes, prerequisites, interest weights)
#             - Explain cause-and-effect relationships (e.g., "Taking BCSE203P in Sem 5 unlocks BCSE306L in Sem 6")
#             - Acknowledge trade-offs when they exist (e.g., "Slightly higher workload to complete mandatory courses early")
#             - Use natural, conversational language - avoid robotic or repetitive phrasing
#             - Focus on PERSONALIZATION - this should feel tailored to this specific student
#             - For failed courses, be encouraging and explain the retake strategy
#             - Mention workload distribution across semesters

#             OUTPUT FORMAT:
#             Return a structured JSON matching the PlanExplanation schema with:
#             - overall_plan_summary: string (2-3 paragraphs)
#             - graduation_path: string (1-2 paragraphs)
#             - semesters: array of SemesterExplanation objects
#             - Each with: semester, overall_strategy, workload_reasoning, courses array
#             - courses array contains CourseExplanation objects with all required fields

#             Example structure:
#             {{
#             "overall_plan_summary": "Your course plan strategically balances...",
#             "graduation_path": "You're on track to graduate with...",
#             "semesters": [
#                 {{
#                 "semester": 5,
#                 "overall_strategy": "This semester focuses on...",
#                 "workload_reasoning": "With 20 credits, this aligns with your medium workload preference...",
#                 "courses": [
#                     {{
#                     "code": "BCSE306L",
#                     "name": "Artificial Intelligence",
#                     "semester": 5,
#                     "why_selected": "This mandatory core course directly aligns with your strong interest in AI (interest weight: 0.95). It's essential for your degree and matches your passion.",
#                     "why_this_semester": "This is the earliest semester you can take this course after completing prerequisite BCSE203P in Sem 4. Taking it now unlocks advanced AI electives like Machine Learning (BCSE410L) in future semesters.",
#                     "prerequisites_context": "You've already completed the required prerequisites: BCSE203P (Data Structures) in Sem 4, which gave you the algorithmic foundation needed.",
#                     "interest_alignment": "With an interest weight of 0.95, this is one of your highest-rated courses. It directly addresses your stated interest in 'AI and machine learning applications'.",
#                     "strategic_value": "This course unlocks 3 advanced electives: BCSE410L (Machine Learning), BCSE412L (Deep Learning), and BCSE415L (Computer Vision). Completing it now maximizes your options for specialized courses in later semesters."
#                     }}
#                 ]
#                 }}
#             ]
#             }}

#             Generate thorough, personalized explanations that will help the student understand and feel confident about their course plan."""

#         try:
#             print("🤖 Calling LLM for plan explanation...")
            
#             response = self.client.responses.parse(
#                 model=self.model,
#                 input=[
#                     {
#                         "role": "system",
#                         "content": """You are an expert academic advisor who excels at explaining complex course planning decisions.

#                         Your explanations should be:
#                         - SPECIFIC: Reference actual course codes, prerequisites, and data
#                         - PERSONALIZED: Connect to the student's interests and situation
#                         - STRATEGIC: Explain the long-term thinking behind decisions
#                         - ENCOURAGING: Positive and supportive tone
#                         - CLEAR: Avoid jargon, use natural language
#                         - ACTIONABLE: Help students understand what to do and why

#                         You MUST:
#                         - Explain every course selection decision
#                         - Connect courses to student's interests using the interest_weight data
#                         - Explain prerequisite chains and course unlocking
#                         - Justify semester placement based on constraints
#                         - Address workload distribution
#                         - Be specific about graduation requirements being met

#                         You MUST NOT:
#                         - Give generic explanations that could apply to anyone
#                         - Ignore the interest_weight and interest_reason data provided
#                         - Make assumptions not supported by the data
#                         - Be overly technical or use unexplained acronyms
#                         - Provide incomplete explanations for any course"""
#                     },
#                     {
#                         "role": "user",
#                         "content": prompt
#                     }
#                 ],
#                 text_format=PlanExplanation,
#             )
            
#             explanation = response.output_parsed
            
#             self._ui_log(f"✅ Explanations ready for {len(explanation.semesters)} semesters")
#             print(f"✅ Generated explanations for {len(explanation.semesters)} semesters")
#             for sem_exp in explanation.semesters:
#                 print(f"   Semester {sem_exp.semester}: {len(sem_exp.courses)} courses explained")
            
#             print("Explanation : ", explanation)
            
#             return explanation
            
#         except json.JSONDecodeError as e:
#             print(f"✗ Error parsing LLM explanation response: {e}")
#             return None
        
#         except Exception as e:
#             print(f"✗ Error in LLM explanation call: {e}")
#             import traceback
#             traceback.print_exc()
#             return None





#     def diagnose_infeasibility(self, student, eligible_courses, failed_courses, remaining_semesters):
#         """Run constraint isolation to identify what's causing infeasibility"""
        
#         reasons = []
        
#         def quick_solve(add_constraints_fn):
#             m = cp_model.CpModel()
#             x = self._create_variables(m, eligible_courses, remaining_semesters)
#             add_constraints_fn(m, x)
#             s = cp_model.CpSolver()
#             s.parameters.max_time_in_seconds = 5.0
#             return s.Solve(m) in [cp_model.OPTIMAL, cp_model.FEASIBLE]

#         # Check 1: Credits alone
#         if not quick_solve(lambda m, x: self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters)):
#             reasons.append("Not enough courses available to meet minimum credit requirements per semester")
#             return reasons

#         # Check 2: + Failed courses retake
#         def check2(m, x):
#             self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters)
#             self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters)
#             self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters)
#         if not quick_solve(check2):
#             reasons.append(f"Failed courses {list(failed_courses)} cannot be accommodated within credit limits")
#             return reasons

#         # Check 3: + Prerequisites
#         def check3(m, x):
#             check2(m, x)
#             self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters)
#         if not quick_solve(check3):
#             reasons.append("Prerequisite chain constraints make scheduling impossible — possible failed course whose prereq is also failed")
#             return reasons

#         # Check 4: + Category requirements
#         def check4(m, x):
#             check3(m, x)
#             self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters)
#         if not quick_solve(check4):
#             reasons.append("Category credit requirements cannot be satisfied with available courses in remaining semesters")
#             return reasons

#         # Check 5: + Graduation credits
#         def check5(m, x):
#             check4(m, x)
#             self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters)
#         if not quick_solve(check5):
#             reasons.append("Total credits required for graduation cannot be achieved in remaining semesters")
#             return reasons

#         reasons.append("Combination of all constraints together is infeasible — likely slot conflicts or theory-lab pairing conflicts")
#         return reasons




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
DIFFICULTY_RANGES = {
    "low":    (0,  40),
    "medium": (31, 64),
    "high":   (65, 100)
}
PLAN_CONFIGS = {
    'safe_graduation': {
        'name': 'Safe Graduation Plan',
        'description': 'Graduate on time with manageable workload and easy-moderate difficulty. Ignores personal workload/difficulty preferences — optimized for safety.',
        'use_student_preferences': False,
        'hardcoded_workload': 'low',
        'hardcoded_difficulty': 'low',
        'weights': {
            'mandatory': 250,
            'failed': 250,
            'lateness': 200,
            'unlock': 100,
            'diversity': 20,
            'interest': 20,
            'workload': 150,
            'credit_limit_exceed': 100,
            'difficulty': 100,
            'freshness': 40,
        },
    },

    'interest_aligned': {
        'name': 'Interest-Aligned Plan',
        'description': 'Prioritize courses matching your passions. Uses your workload and difficulty preferences. Graduation is still guaranteed.',
        'use_student_preferences': True,
        'weights': {
            'mandatory': 250,
            'failed': 250,
            'lateness': 100,
            'unlock': 60,
            'diversity': 50,
            'interest': 400,
            'workload': 75,
            'credit_limit_exceed': 75,
            'difficulty': 30,
            'freshness': 40,
        },
    }
}
INTEREST_SCALE = 100
NORM_SCALE = 100


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
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = model
        self.last_llm_weights = None
        self.last_plan_explanation = None
        self.unlock_chain_sizes = self.precompute_unlock_chain_sizes()
        print(f'Precomputed chain sizes for {len(self.unlock_chain_sizes)} courses.')
        self._ui_log_callback = None

    def set_ui_logger(self, callback):
        self._ui_log_callback = callback

    def _ui_log(self, message):
        if self._ui_log_callback:
            self._ui_log_callback(message)
        else:
            print(message)

    # ─────────────────────────────────────────────────────────────────────────
    # Precompute unlock chains
    # ─────────────────────────────────────────────────────────────────────────
    def precompute_unlock_chain_sizes(self):
        chain_sizes = {}
        all_courses = self.loader.get_all_course_codes()

        def count_downstream(course_code, visited):
            if course_code in visited:
                return set()
            visited.add(course_code)
            direct_unlocks = set(self.loader.course_unlocks.get(course_code, []))
            all_downstream = set(direct_unlocks)
            for c in direct_unlocks:
                all_downstream |= count_downstream(c, visited.copy())
            return all_downstream

        for course in all_courses:
            downstream_courses = count_downstream(course, set())
            chain_sizes[course] = len(downstream_courses)

        return chain_sizes

    # ─────────────────────────────────────────────────────────────────────────
    # Theory-lab pair integrity helper
    # ─────────────────────────────────────────────────────────────────────────
    def enforce_theory_lab_pair_integrity(self, course_list, completed_set):
        """
        FIX (Bug 1): Ensures theory-lab pairs are always both present or both absent
        in the course list. If one half is missing (removed by user), removes the other
        half too so the solver never sees an orphaned lab or theory course.

        Returns the cleaned list and a dict of pairs that were auto-removed:
          { removed_code: partner_code }
        """
        course_set = set(course_list)
        auto_removed = {}  # removed_code -> partner_code

        for cc in list(course_list):
            if cc not in course_set:
                continue  # already removed in this pass

            # Check theory -> lab direction
            lab = self.loader.get_lab_course(cc)
            if lab and lab not in completed_set:
                if lab not in course_set:
                    # Lab is missing; remove theory too
                    course_set.discard(cc)
                    auto_removed[cc] = lab

            # Check lab -> theory direction (need inverse lookup)
            theory = self.loader.get_theory_course(cc) if hasattr(self.loader, 'get_theory_course') else None
            if theory and theory not in completed_set:
                if theory not in course_set:
                    # Theory is missing; remove lab too
                    course_set.discard(cc)
                    auto_removed[cc] = theory

        cleaned = [c for c in course_list if c in course_set]
        return cleaned, auto_removed

    # ─────────────────────────────────────────────────────────────────────────
    # Plan generation
    # ─────────────────────────────────────────────────────────────────────────
    def generate_single_plan(self, student, eligible_courses, remaining_semesters, failed_courses, llm_weights, weights, plan_type='interest_aligned'):
        self._ui_log("🔧 Building constraint model...")
        model = cp_model.CpModel()
        x = self._create_variables(model, eligible_courses, remaining_semesters)
        self.add_hard_constraints(model, x, student, eligible_courses, failed_courses, remaining_semesters)
        workload_penalties     = self.add_workload_balance_soft_constraint(model, x, student, eligible_courses, remaining_semesters, plan_type)
        diversity_rewards      = self.add_diversity_reward_soft_constraint(model, x, eligible_courses, remaining_semesters)
        credit_limit_exceeding = self.add_total_credit_limit_exceeding_penalty(model, x, student, eligible_courses, remaining_semesters)
        difficulty_penalties   = self.add_difficulty_balance_soft_constraint(model, x, student, eligible_courses, remaining_semesters, plan_type)
        freshness_penalties    = self.add_prerequisite_freshness_soft_constraint(model, x, student, eligible_courses, remaining_semesters)

        self.last_llm_weights = llm_weights
        course_interest_weights_dict = self.add_course_interest_soft_constraint(eligible_courses, llm_weights)
        self.set_objective(
            model, x, student, eligible_courses, remaining_semesters,
            failed_courses, workload_penalties, course_interest_weights_dict,
            weights, diversity_rewards, credit_limit_exceeding, difficulty_penalties,
            freshness_penalties
        )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        solver.parameters.random_seed = 42
        solver.parameters.num_search_workers = 1

        self._ui_log("⚡ Running CP-SAT solver...")
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL:
            self._ui_log("✅ Found optimal solution!")
            plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
            self.print_plan(plan, student)
            self._last_course_interest_weights_dict = course_interest_weights_dict
            return plan, None
        elif status == cp_model.FEASIBLE:
            self._ui_log("✅ Found feasible solution!")
            plan = self.get_solution(solver, x, eligible_courses, remaining_semesters)
            self.print_plan(plan, student)
            self._last_course_interest_weights_dict = course_interest_weights_dict
            return plan, None
        else:
            self._ui_log("❌ No solution found — diagnosing issue...")
            print('Status :', solver.StatusName(status))
            diagnosis = self.diagnose_infeasibility_core(
                student, eligible_courses, failed_courses, remaining_semesters,
                avoided_list=[], pinned_courses={},
                is_customization=False,
            )
            return {sem: [] for sem in remaining_semesters}, diagnosis

    def generate_explanation_for_plan(self, student, plan, llm_weights):
        course_interest_weights_dict = getattr(self, '_last_course_interest_weights_dict', {})
        explanation = self.generate_plan_explanation(student, plan, llm_weights, course_interest_weights_dict)
        self.last_plan_explanation = explanation
        return explanation

    def generate_complete_plan(self, student):
        print("\n" + "="*80)
        print("🎓 GENERATING MULTIPLE COURSE PLANS")
        print("="*80)

        remaining_semesters = list(range(student.current_semester, 9))
        eligible_courses, failed_courses = self.get_eligible_and_failed_courses(student)

        remaining = self.loader.get_remaining_credits_by_type(student)
        total_needed     = sum(remaining.values())
        total_available  = sum(self.loader.get_credits(c) for c in eligible_courses)
        print(f"\nTotal credits needed: {total_needed}")
        print(f"Total credits available: {total_available}")

        llm_weights = self.get_course_interest_weights_from_llm(student, eligible_courses)
        results = {}

        for plan_type, config in PLAN_CONFIGS.items():
            plan, diagnosis = self.generate_single_plan(
                student, eligible_courses, remaining_semesters,
                failed_courses, llm_weights, weights=config['weights'],
                plan_type=plan_type,
            )
            if plan and any(plan.values()):
                results[plan_type] = {
                    'config': config,
                    'plan': plan,
                    'explanation': None,
                    'diagnosis': None,
                }
            else:
                results[plan_type] = {
                    'config': config,
                    'plan': {},
                    'explanation': None,
                    'diagnosis': diagnosis,
                }

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Eligible / failed courses
    # ─────────────────────────────────────────────────────────────────────────
    def get_eligible_and_failed_courses(self, student):
        completed = set(student.completed_courses)
        all_courses = self.loader.get_all_course_codes()
        eligible = [cc for cc in all_courses if cc not in completed]
        failed   = set(student.failed_courses)
        return eligible, failed

    # ─────────────────────────────────────────────────────────────────────────
    # Variable creation
    # ─────────────────────────────────────────────────────────────────────────
    def _create_variables(self, model, eligible_courses, semesters):
        x = {}
        for course in eligible_courses:
            for sem in semesters:
                x[course, sem] = model.new_bool_var(f'{course}_semester{sem}')
        return x

    # ─────────────────────────────────────────────────────────────────────────
    # Hard constraints
    # ─────────────────────────────────────────────────────────────────────────
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
                        print('Prerequisite not in completed and also not in eligible course pool')
                        model.add(1 == 0)
                        continue
                    past_sems = [s for s in semesters if s < sem]
                    if not past_sems:
                        model.add(x[course, sem] == 0)
                    if past_sems and preq in courses:
                        model.add(x[course, sem] <= sum(x[preq, s] for s in past_sems))

    def add_min_max_credit_constraint(self, model, x, courses, semesters):
        for sem in semesters:
            sem_creds = sum(self.loader.get_credits(c) * x[c, sem] for c in courses)
            model.add(sem_creds >= MIN_CREDITS)
            model.add(sem_creds <= MAX_CREDITS)

    def add_slot_conflict_constraint(self, model, x, courses, semesters):
        # Slot conflicts only enforced for the CURRENT (first) semester.
        # Future semester slots are unknown at planning time.
        for sem in semesters:
            for i, c1 in enumerate(courses):
                for c2 in courses[i+1:]:
                    if not self.loader.can_take_together(c1, c2):
                        model.add(x[c1, sem] + x[c2, sem] <= 1)
            break  # only current semester

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
            required       = requirements.get('required', 0)
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
        project1   = 'BCSE497J'
        project2   = 'BCSE498J'
        internship = 'BCSE499J'
        for course in project_courses:
            for sem in semesters:
                if course == project1:
                    model.add(x[course, sem] == (1 if sem == 7 else 0))
                elif course == project2 or course == internship:
                    model.add(x[course, sem] == (1 if sem == 8 else 0))
                else:
                    if sem < 7:
                        model.add(x[course, sem] == 0)

    def add_failed_courses_retake_constraint(self, model, x, failed_courses, semesters):
        for c in failed_courses:
            model.add(sum(x[c, s] for s in semesters) == 1)

    def add_mandatory_courses_completion_constraint(self, model, x, courses, semesters):
        for c in courses:
            if self.loader.get_course_by_code(c).get('is_mandatory', False):
                model.add(sum(x[c, s] for s in semesters) == 1)

    def add_total_min_credits_req_for_graduation(self, model, x, student, courses, semesters):
        completed = student.completed_courses
        credits_earned_so_far = round(sum(self.loader.get_credits(c) for c in completed))
        min_credits_required  = TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE - credits_earned_so_far
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
                year = (sem + 1) // 2
                if year < course_unlock_year:
                    model.add(x[course, sem] == 0)

    def add_max_allowed_courses_per_semester(self, model, x, courses, semesters):
        for sem in semesters:
            model.add(sum(x[c, sem] for c in courses) <= MAX_ALLOWED_COURSES_PER_SEM)

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
        self.add_mandatory_courses_completion_constraint(model, x, eligible_courses, remaining_semesters)

    # ─────────────────────────────────────────────────────────────────────────
    # Soft constraints
    # ─────────────────────────────────────────────────────────────────────────
    def add_workload_balance_soft_constraint(self, model, x, student, courses, semesters, plan_type='interest_aligned'):
        config = PLAN_CONFIGS.get(plan_type, {})
        if config.get('use_student_preferences', True):
            workload_preference = getattr(student, 'workload_preference', 'medium') or 'medium'
        else:
            workload_preference = config.get('hardcoded_workload', 'medium')
        penalty_vars = []
        ranges = RANGES

        current_semester  = semesters[0]
        future_semesters  = semesters[1:] if len(semesters) > 1 else []

        min_target, max_target = ranges[workload_preference]
        current_sem_credits = sum(self.loader.get_credits(c) * x[c, current_semester] for c in courses)

        under_penalty = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{current_semester}')
        model.add(under_penalty >= min_target - current_sem_credits)

        over_penalty = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{current_semester}')
        model.add(over_penalty >= current_sem_credits - max_target)

        penalty_vars.extend([under_penalty, over_penalty])

        for sem in future_semesters:
            sem_credits = sum(self.loader.get_credits(c) * x[c, sem] for c in courses)
            min_t, max_t = ranges['medium']

            u_pen = model.new_int_var(0, MIN_CREDITS, f'under_penalty_sem{sem}')
            model.add(u_pen >= min_t - sem_credits)

            o_pen = model.new_int_var(0, MAX_CREDITS, f'over_penalty_sem{sem}')
            model.add(o_pen >= sem_credits - max_t)

            penalty_vars.extend([u_pen, o_pen])

        return penalty_vars

    def add_difficulty_balance_soft_constraint(self, model, x, student, courses, semesters, plan_type='interest_aligned'):
        config = PLAN_CONFIGS.get(plan_type, {})
        if config.get('use_student_preferences', True):
            difficulty_preference = getattr(student, 'difficulty_preference', 'medium') or 'medium'
        else:
            difficulty_preference = config.get('hardcoded_difficulty', 'low')
        min_diff, max_diff = DIFFICULTY_RANGES[difficulty_preference]
        min_target = min_diff * 10
        max_target = max_diff * 10

        MAX_PENALTY = MAX_ALLOWED_COURSES_PER_SEM * 1000
        penalty_vars = []

        for sem in semesters:
            sem_difficulty_sum = sum(
                int(self.loader.get_course_by_code(c).get('difficulty', 50) * 10) * x[c, sem]
                for c in courses
            )
            num_courses = sum(x[c, sem] for c in courses)

            under_penalty = model.new_int_var(0, MAX_PENALTY, f'diff_under_penalty_sem{sem}')
            over_penalty  = model.new_int_var(0, MAX_PENALTY, f'diff_over_penalty_sem{sem}')

            model.add(under_penalty >= min_target * num_courses - sem_difficulty_sum)
            model.add(over_penalty  >= sem_difficulty_sum - max_target * num_courses)

            penalty_vars.extend([under_penalty, over_penalty])

        return penalty_vars

    def add_prerequisite_freshness_soft_constraint(self, model, x, student, courses, semesters):
        completed_set = set(student.completed_courses)
        courses_set   = set(courses)

        completed_sem_map: dict = {}
        for r in student.course_records:
            if not r.is_failed:
                completed_sem_map[r.course_code] = r.semester_taken

        min_sem = min(semesters)
        max_sem = max(semesters)

        history_min = min(completed_sem_map.values()) if completed_sem_map else min_sem - 1
        prereq_lower_bound = min(history_min, min_sem - 1)

        penalty_vars = []

        for course in courses:
            prereqs = self.loader.get_prerequisites(course)
            if not prereqs:
                continue

            completed_prereqs = [p for p in prereqs if p in completed_set]
            future_prereqs    = [p for p in prereqs if p in courses_set and p not in completed_set]

            if not completed_prereqs and not future_prereqs:
                continue

            latest_prereq_sem = model.new_int_var(
                prereq_lower_bound, max_sem, f'latest_prereq_sem_{course}'
            )

            for prereq in completed_prereqs:
                actual_sem = completed_sem_map.get(prereq)
                if actual_sem is not None:
                    model.add(latest_prereq_sem >= actual_sem)

            for prereq in future_prereqs:
                prereq_sem_var = model.new_int_var(
                    min_sem - 1, max_sem, f'prereq_sem_{prereq}_for_{course}'
                )
                is_scheduled = model.new_bool_var(f'prereq_scheduled_{prereq}_for_{course}')
                model.add(sum(x[prereq, s] for s in semesters) >= is_scheduled)
                model.add(is_scheduled >= sum(x[prereq, s] for s in semesters))

                scheduled_sem_expr = sum(s * x[prereq, s] for s in semesters)
                model.add(prereq_sem_var == scheduled_sem_expr).only_enforce_if(is_scheduled)
                model.add(prereq_sem_var == min_sem - 1).only_enforce_if(is_scheduled.Not())
                model.add(latest_prereq_sem >= prereq_sem_var)

            course_sem_var = model.new_int_var(min_sem, max_sem, f'course_sem_{course}')
            course_is_scheduled = model.new_bool_var(f'course_scheduled_{course}')
            model.add(sum(x[course, s] for s in semesters) >= course_is_scheduled)
            model.add(course_is_scheduled >= sum(x[course, s] for s in semesters))

            course_sem_expr = sum(s * x[course, s] for s in semesters)
            model.add(course_sem_var == course_sem_expr).only_enforce_if(course_is_scheduled)
            model.add(course_sem_var == min_sem).only_enforce_if(course_is_scheduled.Not())

            max_possible_gap = max_sem - prereq_lower_bound
            gap_var = model.new_int_var(-max_possible_gap, max_possible_gap, f'freshness_gap_{course}')
            model.add(gap_var == course_sem_var - latest_prereq_sem)

            freshness_penalty = model.new_int_var(0, max_possible_gap, f'freshness_penalty_{course}')
            model.add(freshness_penalty >= gap_var - 1)
            model.add(freshness_penalty >= 0)
            penalty_vars.append(freshness_penalty)

        print(f"📐 Freshness constraint: tracking {len(penalty_vars)} courses with prerequisites")
        return penalty_vars

    def add_total_credit_limit_exceeding_penalty(self, model, x, student, courses, semesters):
        completed_courses     = set(student.completed_courses)
        credits_earned_so_far = round(sum(self.loader.get_credits(c) for c in completed_courses))

        total_future_credits = sum(
            self.loader.get_credits(c) * x[c, s]
            for c in courses
            for s in semesters
        )

        MAX_POSSIBLE_CREDITS_TO_EARN = MAX_CREDITS * TOTAL_SEMS
        credit_exceed = model.new_int_var(0, MAX_POSSIBLE_CREDITS_TO_EARN, 'total_credit_exceed')
        model.add(credit_exceed >= (credits_earned_so_far + total_future_credits) - TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE)

        return [credit_exceed]

    def add_diversity_reward_soft_constraint(self, model, x, courses, semesters):
        CATEGORIES_TO_BALANCE = {
            'Discipline Elective',
            'Open Elective',
            'Non-graded Core Requirements'
        }
        reward_vars = []
        for sem in semesters[::-1]:
            for cat in CATEGORIES_TO_BALANCE:
                category_courses = [c for c in courses if self.loader.get_course_by_code(c).get('course_type', '') == cat]
                if not category_courses:
                    continue
                present = model.new_bool_var(f'{cat}_present_sem{sem}')
                model.add(sum(x[c, sem] for c in category_courses) >= present)
                model.add(present <= sum(x[c, sem] for c in category_courses))
                reward_vars.append(present)
        return reward_vars

    # ─────────────────────────────────────────────────────────────────────────
    # LLM interest weights
    # ─────────────────────────────────────────────────────────────────────────
    def get_course_interest_weights_from_llm(self, student, courses):
        course_list = []
        for course_code in courses:
            course_info = self.loader.get_course_by_code(course_code)
            course_list.append({
                "code": course_code,
                "name": course_info['course_name'],
                "type": course_info.get('course_type', 'Unknown')
            })

        self._ui_log(f"🤖 AI analyzing {len(course_list)} courses against your interests...")

        prompt = f"""You are an academic advisor analyzing course-interest alignment.

TASK:
Rate how well each course matches the student's stated interests.

STUDENT INTERESTS:
{json.dumps(student.interest_areas, indent=2)}

COURSES TO RATE:
{json.dumps(course_list, indent=2)}

RATING GUIDELINES:
Score 0.9 - 1.0: Perfect Match - Course directly mentions student's core interests
Score 0.7 - 0.8: Strong Match - Course closely related to interests
Score 0.5 - 0.6: Moderate Match - Course somewhat related or complementary
Score 0.3 - 0.4: Weak Match - Course tangentially related
Score 0.0 - 0.2: No Match - Course unrelated to stated interests

CRITICAL RULES:
1. Base scores ONLY on interest alignment, nothing else
2. Ignore student's CGPA, year, or past performance
3. Ignore course difficulty or workload
4. Ignore graduation requirements

OUTPUT FORMAT (strict JSON):
{{
  "courses": [
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
  ]
}}

Rate ALL {len(course_list)} courses. Return ONLY valid JSON, no additional text."""

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": "You are an expert academic advisor specializing in course-interest matching. Return valid JSON only."
                    },
                    {"role": "user", "content": prompt}
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
        weights_dict = {}
        if llm_weights and llm_weights.courses:
            for cw in llm_weights.courses:
                weights_dict[cw.code] = (cw.weight, cw.name, cw.reason)

        for course in courses:
            if course not in weights_dict:
                ci = self.loader.get_course_by_code(course)
                weights_dict[course] = (0.5, ci.get('course_name') if ci else course, 'Default value set')

        return weights_dict

    # ─────────────────────────────────────────────────────────────────────────
    # Lateness penalty helper
    # ─────────────────────────────────────────────────────────────────────────
    def add_lateness_penalty(self, course_code, sem):
        course_info = self.loader.get_course_by_code(course_code)
        year_offered = course_info.get('year_offered', 1)
        better_complete_before_sem = (year_offered + 1) * 2
        if sem <= better_complete_before_sem:
            return 0
        sems_late    = sem - better_complete_before_sem
        is_mandatory = course_info.get('is_mandatory', False)
        unlock_chain_size = (self.unlock_chain_sizes.get(course_code) or 0) + 1
        return sems_late * (2 if is_mandatory else 1) * unlock_chain_size

    # ─────────────────────────────────────────────────────────────────────────
    # Objective
    # ─────────────────────────────────────────────────────────────────────────
    def set_objective(self, model, x, student, courses, semesters, failed_courses,
                      workload_penalties, course_interest_weights_dict, weights,
                      diversity_rewards, credit_limit_exceeding, difficulty_penalties,
                      freshness_penalties):

        w_mandatory           = weights.get('mandatory', 100)
        w_unlock              = weights.get('unlock', 30)
        w_interest            = weights.get('interest', 30)
        w_workload            = weights.get('workload', 60)
        w_failed              = weights.get('failed', 200)
        w_lateness            = weights.get('lateness', 75)
        w_diversity           = weights.get('diversity', 30)
        w_credit_limit_exceed = weights.get('credit_limit_exceed', 30)
        w_difficulty          = weights.get('difficulty', 30)
        w_freshness           = weights.get('freshness', 40)

        mandatory_courses = self.loader.get_remaining_mandatory_courses(student)
        mandatory_score = sum(
            x[c, s] * (TOTAL_SEMS - s + 1)
            for c in mandatory_courses if c in courses
            for s in semesters
        )

        unlock_score = sum(
            len(self.loader.course_unlocks.get(c, [])) * x[c, s] * (TOTAL_SEMS - s + 1)
            for c in courses for s in semesters
        )

        workload_penalty_total = sum(workload_penalties)

        interest_score = sum(
            int(round(
                course_interest_weights_dict.get(
                    c, (0.5, self.loader.get_course_by_code(c).get('course_name'), 'Default')
                )[0] * INTEREST_SCALE
            )) * x[c, s] * (TOTAL_SEMS - s + 1)
            for c in courses
            for s in semesters
        )

        failed_course_urgency_score = sum(
            (TOTAL_SEMS - s + 1) * x[c, s]
            for c in failed_courses if c in courses
            for s in semesters
        )

        lateness_penalty_total = sum(
            self.add_lateness_penalty(c, s) * x[c, s]
            for c in courses
            for s in semesters
        )

        diversity_reward_total      = sum(diversity_rewards)
        credit_limit_exceed_penalty = sum(credit_limit_exceeding)
        difficulty_penalty_total    = sum(difficulty_penalties)
        freshness_penalty_total     = sum(freshness_penalties)
        total_courses_taken = sum(x[c, s] for c in courses for s in semesters)

        model.maximize(
            w_mandatory   * mandatory_score
            + w_unlock    * unlock_score
            + w_interest  * interest_score
            + w_failed    * failed_course_urgency_score
            + w_diversity * diversity_reward_total
            - w_workload  * workload_penalty_total
            - w_lateness  * lateness_penalty_total
            - w_credit_limit_exceed * credit_limit_exceed_penalty
            - w_difficulty * difficulty_penalty_total
            - w_freshness  * freshness_penalty_total
            - 1 * total_courses_taken
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Solution extraction & display
    # ─────────────────────────────────────────────────────────────────────────
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
        credits_earned_so_far = round(sum(self.loader.get_credits(c) for c in completed))
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

    # ─────────────────────────────────────────────────────────────────────────
    # LLM plan explanation
    # ─────────────────────────────────────────────────────────────────────────
    def generate_plan_explanation(self, student, plan, llm_weights, course_interest_weights_dict):
        self._ui_log("📝 Generating personalized course explanations...")

        student_context = {
            "name":                    student.name,
            "student_id":              student.student_id,
            "current_semester":        student.current_semester,
            "cgpa":                    student.cgpa,
            "interest_areas":          student.interest_areas if hasattr(student, 'interest_areas') else [],
            "workload_preference":     student.workload_preference or "medium",
            "difficulty_preference":   getattr(student, 'difficulty_preference', 'medium'),
            "completed_courses_count": len(student.completed_courses),
            "failed_courses":          student.failed_courses
        }

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
                prereqs = self.loader.get_prerequisites(course_code)
                prereq_names = []
                for p in prereqs:
                    p_info = self.loader.get_course_by_code(p)
                    if p_info:
                        prereq_names.append(f"{p} ({p_info['course_name']})")
                unlocks = self.loader.course_unlocks.get(course_code, [])
                unlock_names = []
                for u in unlocks:
                    u_info = self.loader.get_course_by_code(u)
                    if u_info:
                        unlock_names.append(f"{u} ({u_info['course_name']})")
                interest_weight_info = course_interest_weights_dict.get(
                    course_code, (0.5, course_info.get('course_name'), 'Not weighted')
                )
                sem_courses.append({
                    "code":             course_code,
                    "name":             course_info['course_name'],
                    "credits":          credits,
                    "type":             course_info.get('course_type', 'Unknown'),
                    "is_mandatory":     course_info.get('is_mandatory', False),
                    "is_failed_retake": course_code in student.failed_courses,
                    "difficulty":       course_info.get('difficulty', 50),
                    "pass_rate":        course_info.get('pass_rate', 0.8),
                    "prerequisites":    prereq_names,
                    "unlocks":          unlock_names,
                    "interest_weight":  interest_weight_info[0],
                    "interest_reason":  interest_weight_info[2],
                    "slots":            course_info.get('slots', [])
                })
            plan_data.append({
                "semester":      sem,
                "total_credits": sem_credits,
                "course_count":  len(sem_courses),
                "courses":       sem_courses
            })

        remaining_requirements = self.loader.get_remaining_credits_by_type(student)

        prompt = f"""You are an expert academic advisor. Generate comprehensive, personalized explanations
for this student's course plan.

STUDENT PROFILE:
{json.dumps(student_context, indent=2)}

REMAINING REQUIREMENTS:
{json.dumps(remaining_requirements, indent=2)}

GENERATED COURSE PLAN:
{json.dumps(plan_data, indent=2)}

Return a structured JSON matching the PlanExplanation schema:
- overall_plan_summary: string (2-3 paragraphs)
- graduation_path: string (1-2 paragraphs)
- semesters: array of SemesterExplanation objects, each with semester, overall_strategy, workload_reasoning, courses
- courses: array of CourseExplanation objects with code, name, semester, why_selected, why_this_semester, prerequisites_context, interest_alignment, strategic_value

Be specific, personalized, and reference actual course codes and interest weights."""

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": "You are an expert academic advisor. Explain course plans clearly and specifically."
                    },
                    {"role": "user", "content": prompt}
                ],
                text_format=PlanExplanation,
            )
            explanation = response.output_parsed
            self._ui_log(f"✅ Explanations ready for {len(explanation.semesters)} semesters")
            return explanation
        except json.JSONDecodeError as e:
            print(f"✗ Error parsing LLM explanation response: {e}")
            return None
        except Exception as e:
            print(f"✗ Error in LLM explanation call: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # UNIFIED INFEASIBILITY DIAGNOSIS
    # ─────────────────────────────────────────────────────────────────────────
    def diagnose_infeasibility_core(
        self,
        student,
        eligible_courses,
        failed_courses,
        remaining_semesters,
        avoided_list=None,
        pinned_courses=None,
        rearranged_list=None,
        is_customization=False,
        base_plan=None,
    ):
        """
        Unified infeasibility diagnosis used by both generate_single_plan and
        the customization flow in app.py.

        FIX (Bug 3): The layered solver checks now use `eligible_courses` as passed in.
        The caller (regen_clicked in app.py) must pass `adjusted` (avoided-filtered list),
        NOT the full `eligible_courses`, so the solver layers reflect the real regen state.

        When is_customization=False: pre-solve violation checks are skipped.
        When is_customization=True: full pre-solve checks run first.

        NOTE: Slot conflicts are ONLY checked for the current (first) semester
        because future semester timetables are not yet assigned.
        """
        if avoided_list is None:
            avoided_list = []
        if pinned_courses is None:
            pinned_courses = {}
        if rearranged_list is None:
            rearranged_list = []

        loader        = self.loader
        completed_set = set(student.completed_courses)
        current_sem   = remaining_semesters[0] if remaining_semesters else None

        result = {
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
            "suggestion":               "Review the details below and undo the changes causing the conflict.",
        }

        # ── PRE-SOLVE CHECKS (customization only) ────────────────────────────
        if is_customization:
            avoided_set        = set(avoided_list)
            eligible_set       = set(eligible_courses)
            base_course_to_sem = {}
            if base_plan is not None:
                base_course_to_sem = {c: s for s, clist in base_plan.items() for c in clist}

            print("=== DIAGNOSIS DEBUG ===")
            print(f"is_customization: {is_customization}")
            print(f"avoided_list: {avoided_list}")
            print(f"pinned_courses: {pinned_courses}")
            print(f"eligible_courses count: {len(eligible_courses)}")
            print(f"base_plan is None: {base_plan is None}")

            # ── CHECK 1: Prerequisite broken by removal ───────────────────────
            for cc in avoided_list:
                ci   = loader.get_course_by_code(cc)
                name = ci['course_name'] if ci else cc
                dependents = [
                    c for c in eligible_set
                    if cc in loader.get_prerequisites(c) and c not in avoided_set
                ]
                if dependents:
                    dep_names = [
                        f"**{loader.get_course_by_code(d)['course_name']}** ({d})"
                        if loader.get_course_by_code(d) else d
                        for d in dependents
                    ]
                    result["pre_solve_violations"].append(
                        f"Removing **{name}** ({cc}) breaks the prerequisite for: "
                        f"{', '.join(dep_names)}. "
                        f"Either keep **{name}** or also remove those dependent courses."
                    )

            # ── CHECK 2: Mandatory course being removed ───────────────────────
            for cc in avoided_list:
                ci = loader.get_course_by_code(cc)
                if ci and ci.get('is_mandatory', False):
                    result["pre_solve_violations"].append(
                        f"**{ci['course_name']}** ({cc}) is a **mandatory** course and cannot "
                        f"be removed from the plan. All mandatory courses must be completed."
                    )
                    result["mandatory_issues"].append(
                        f"**{ci['course_name']}** ({cc}) is mandatory and was removed."
                    )

            # ── CHECK 3: Failed course being removed ──────────────────────────
            failed_set = set(failed_courses)
            for cc in avoided_list:
                if cc in failed_set:
                    ci   = loader.get_course_by_code(cc)
                    name = ci['course_name'] if ci else cc
                    result["pre_solve_violations"].append(
                        f"**{name}** ({cc}) is a **failed course** that must be retaken. "
                        f"It cannot be removed from the plan."
                    )

            # ── CHECK 4: Year-level unlock violated by pin ────────────────────
            for cc, ps in pinned_courses.items():
                ci = loader.get_course_by_code(cc)
                if ci:
                    year_required      = ci.get('year_offered', 1)
                    year_of_sem        = (ps + 1) // 2
                    earliest_valid_sem = (year_required - 1) * 2 + 1
                    if year_of_sem < year_required:
                        result["pre_solve_violations"].append(
                            f"**{ci['course_name']}** ({cc}) is a Year {year_required} course "
                            f"but you pinned it to Semester {ps} (Year {year_of_sem}). "
                            f"Earliest valid semester is **Semester {earliest_valid_sem}**."
                        )
                        result["year_level_issues"].append(
                            (cc, ci['course_name'], year_required, ps)
                        )

            # ── CHECK 5: Project courses pinned to wrong semester ─────────────
            PROJECT1    = 'BCSE497J'
            PROJECT2    = 'BCSE498J'
            INTERNSHIP  = 'BCSE499J'
            for cc, ps in pinned_courses.items():
                ci = loader.get_course_by_code(cc)
                if not ci:
                    continue
                if cc == PROJECT1 and ps != 7:
                    result["pre_solve_violations"].append(
                        f"**{ci['course_name']}** ({cc}) (Project-I) must be in "
                        f"**Semester 7** — it cannot be moved to Semester {ps}."
                    )
                elif cc in (PROJECT2, INTERNSHIP) and ps != 8:
                    result["pre_solve_violations"].append(
                        f"**{ci['course_name']}** ({cc}) must be in "
                        f"**Semester 8** — it cannot be moved to Semester {ps}."
                    )
                elif ci.get('course_type') == 'Projects and Internship' and cc not in (PROJECT1, PROJECT2, INTERNSHIP) and ps < 7:
                    result["pre_solve_violations"].append(
                        f"**{ci['course_name']}** ({cc}) is a project course and "
                        f"cannot be placed before Semester 7."
                    )

            # ── CHECK 6: Theory-lab pair separation ───────────────────────────
            # FIX (Bug 4): Added Cases D and E — one half removed from the pool
            already_reported = set()

            # Case D: theory removed, lab still present in eligible pool
            for cc in avoided_list:
                lab = loader.get_lab_course(cc)
                if lab and lab in eligible_set and lab not in avoided_set:
                    pair_key = tuple(sorted([cc, lab]))
                    if pair_key not in already_reported:
                        ci_t   = loader.get_course_by_code(cc)
                        ci_l   = loader.get_course_by_code(lab)
                        t_name = ci_t['course_name'] if ci_t else cc
                        l_name = ci_l['course_name'] if ci_l else lab
                        result["pre_solve_violations"].append(
                            f"**{t_name}** ({cc}) was removed but its paired lab "
                            f"**{l_name}** ({lab}) is still in the plan. "
                            f"Theory and lab must always be **removed or kept together**. "
                            f"Please also remove **{l_name}** or restore **{t_name}**."
                        )
                        result["theory_lab_issues"].append((cc, lab, None, None))
                        already_reported.add(pair_key)

            # Case E: lab removed, theory still present in eligible pool
            # Requires inverse lookup: get_theory_course (lab -> theory)
            if hasattr(loader, 'get_theory_course'):
                for cc in avoided_list:
                    theory = loader.get_theory_course(cc)
                    if theory and theory in eligible_set and theory not in avoided_set:
                        pair_key = tuple(sorted([cc, theory]))
                        if pair_key not in already_reported:
                            ci_t   = loader.get_course_by_code(theory)
                            ci_l   = loader.get_course_by_code(cc)
                            t_name = ci_t['course_name'] if ci_t else theory
                            l_name = ci_l['course_name'] if ci_l else cc
                            result["pre_solve_violations"].append(
                                f"**{l_name}** ({cc}) (lab) was removed but its theory course "
                                f"**{t_name}** ({theory}) is still in the plan. "
                                f"Theory and lab must always be **removed or kept together**. "
                                f"Please also remove **{t_name}** or restore **{l_name}**."
                            )
                            result["theory_lab_issues"].append((theory, cc, None, None))
                            already_reported.add(pair_key)

            # Cases A/B/C: pinning separates a pair
            for cc, ps in pinned_courses.items():
                # Case B & A (cc is a lab)
                theory = loader.get_theory_course(cc) if hasattr(loader, 'get_theory_course') else None
                if theory and theory in eligible_set:
                    pair_key = tuple(sorted([cc, theory]))
                    if pair_key not in already_reported:
                        ci_t   = loader.get_course_by_code(theory)
                        ci_l   = loader.get_course_by_code(cc)
                        t_name = ci_t['course_name'] if ci_t else theory
                        l_name = ci_l['course_name'] if ci_l else cc

                        theory_sem = pinned_courses.get(theory)
                        if theory_sem is not None and theory_sem != ps:
                            result["pre_solve_violations"].append(
                                f"**{l_name}** (lab) is pinned to Semester {ps} but its theory "
                                f"**{t_name}** is pinned to Semester {theory_sem}. "
                                f"Theory and lab **must be in the same semester**."
                            )
                            result["theory_lab_issues"].append((theory, cc, theory_sem, ps))
                            already_reported.add(pair_key)
                        elif theory_sem is None and base_plan is not None:
                            base_theory_sem = base_course_to_sem.get(theory)
                            if base_theory_sem is not None and base_theory_sem != ps:
                                result["pre_solve_violations"].append(
                                    f"**{l_name}** (lab) is moved to Semester {ps} but its theory "
                                    f"**{t_name}** is still in Semester {base_theory_sem}. "
                                    f"Theory and lab **must always be in the same semester** — "
                                    f"move **{t_name}** to Semester {ps} as well, or move both back."
                                )
                                result["theory_lab_issues"].append((theory, cc, base_theory_sem, ps))
                                already_reported.add(pair_key)

                # Case C & A (cc is a theory)
                lab = loader.get_lab_course(cc)
                if lab and lab in eligible_set:
                    pair_key = tuple(sorted([cc, lab]))
                    if pair_key not in already_reported:
                        ci_t   = loader.get_course_by_code(cc)
                        ci_l   = loader.get_course_by_code(lab)
                        t_name = ci_t['course_name'] if ci_t else cc
                        l_name = ci_l['course_name'] if ci_l else lab

                        lab_sem = pinned_courses.get(lab)
                        if lab_sem is not None and lab_sem != ps:
                            result["pre_solve_violations"].append(
                                f"**{t_name}** (theory) is pinned to Semester {ps} but its lab "
                                f"**{l_name}** is pinned to Semester {lab_sem}. "
                                f"Theory and lab **must be in the same semester**."
                            )
                            result["theory_lab_issues"].append((cc, lab, ps, lab_sem))
                            already_reported.add(pair_key)
                        elif lab_sem is None and base_plan is not None:
                            base_lab_sem = base_course_to_sem.get(lab)
                            if base_lab_sem is not None and base_lab_sem != ps:
                                result["pre_solve_violations"].append(
                                    f"**{t_name}** (theory) is moved to Semester {ps} but its lab "
                                    f"**{l_name}** is still in Semester {base_lab_sem}. "
                                    f"Theory and lab **must always be in the same semester** — "
                                    f"move **{l_name}** to Semester {ps} as well, or move both back."
                                )
                                result["theory_lab_issues"].append((cc, lab, ps, base_lab_sem))
                                already_reported.add(pair_key)

            # ── CHECK 7: Slot conflicts in current semester (all effective courses) ─
            if current_sem is not None:
                # Courses originally in current sem that are staying (not removed, not moved away)
                originally_staying = [
                    cc for cc in (base_plan or {}).get(current_sem, [])
                    if cc not in avoided_list
                    and pinned_courses.get(cc, current_sem) == current_sem
                ]
                # Courses from other sems being moved INTO current sem
                moved_in = [
                    cc for cc, ps in pinned_courses.items()
                    if ps == current_sem
                    and cc not in (base_plan or {}).get(current_sem, [])
                    and cc in eligible_set
                ]

                effective = originally_staying + moved_in

                for i, c1 in enumerate(effective):
                    for c2 in effective[i+1:]:
                        if not loader.can_take_together(c1, c2):
                            ci1    = loader.get_course_by_code(c1)
                            ci2    = loader.get_course_by_code(c2)
                            slots1 = ci1.get('slots', []) if ci1 else []
                            slots2 = ci2.get('slots', []) if ci2 else []
                            shared = set(slots1) & set(slots2)
                            c1_label = 'moved in' if c1 in moved_in else f'already in Sem {current_sem}'
                            c2_label = 'moved in' if c2 in moved_in else f'already in Sem {current_sem}'
                            msg = (
                                f"**{ci1['course_name'] if ci1 else c1}** ({c1_label}) and "
                                f"**{ci2['course_name'] if ci2 else c2}** ({c2_label}) "
                                f"share timetable slot(s): **{', '.join(shared)}** "
                                f"in Semester {current_sem}."
                            )
                            result["slot_conflicts"].append(msg)
                            result["pre_solve_violations"].append(
                                f"Slot conflict in Semester {current_sem}: " + msg +
                                f" Move one of them to a different semester."
                            )

            # ── CHECK 8: Credit bounds — semester over/underflow ──────────────
            if base_plan is not None:
                sim_credits = {}
                for s in remaining_semesters:
                    sim_credits[s] = sum(loader.get_credits(c) for c in base_plan.get(s, []))
                for cc, target_sem in pinned_courses.items():
                    original_sem = base_course_to_sem.get(cc)
                    cr = loader.get_credits(cc)
                    if original_sem is not None and original_sem != target_sem:
                        sim_credits[original_sem] = sim_credits.get(original_sem, 0) - cr
                        sim_credits[target_sem]   = sim_credits.get(target_sem, 0) + cr
                    elif original_sem is None:
                        sim_credits[target_sem] = sim_credits.get(target_sem, 0) + cr
                for cc in avoided_list:
                    original_sem = base_course_to_sem.get(cc)
                    if original_sem is not None:
                        sim_credits[original_sem] = sim_credits.get(original_sem, 0) - loader.get_credits(cc)

                remaining_set = set(remaining_semesters)
                for s, cr_total in sim_credits.items():
                    if s not in remaining_set:
                        continue
                    if cr_total < MIN_CREDITS:
                        culprits = [
                            cc for cc, ts in pinned_courses.items()
                            if base_course_to_sem.get(cc) == s and ts != s
                        ] + [
                            cc for cc in avoided_list
                            if base_course_to_sem.get(cc) == s
                        ]
                        culprit_names = [
                            f"**{loader.get_course_by_code(c)['course_name'] if loader.get_course_by_code(c) else c}**"
                            for c in culprits
                        ]
                        msg = (
                            f"Semester {s} would only have **{cr_total} credits** after your "
                            f"changes (minimum required is **{MIN_CREDITS}**). "
                        )
                        if culprit_names:
                            msg += (
                                f"Moving/removing {', '.join(culprit_names)} leaves this semester "
                                f"underfilled. Move other courses into Semester {s}, or move "
                                f"these courses back."
                            )
                        result["pre_solve_violations"].append(msg)

                    if cr_total > MAX_CREDITS:
                        culprits = [
                            cc for cc, ts in pinned_courses.items()
                            if ts == s and base_course_to_sem.get(cc) != s
                        ]
                        culprit_names = [
                            f"**{loader.get_course_by_code(c)['course_name'] if loader.get_course_by_code(c) else c}**"
                            for c in culprits
                        ]
                        msg = (
                            f"Semester {s} would have **{cr_total} credits** after your "
                            f"changes (maximum allowed is **{MAX_CREDITS}**). "
                        )
                        if culprit_names:
                            msg += (
                                f"Moving {', '.join(culprit_names)} into this semester causes "
                                f"overflow. Spread them across other semesters."
                            )
                        result["pre_solve_violations"].append(msg)

            # ── CHECK 9: Max courses per semester ─────────────────────────────
            if base_plan is not None:
                sim_counts = {
                    s: len(clist) for s, clist in base_plan.items()
                }
                for cc, target_sem in pinned_courses.items():
                    original_sem = base_course_to_sem.get(cc)
                    if original_sem is not None and original_sem != target_sem:
                        sim_counts[original_sem] = sim_counts.get(original_sem, 0) - 1
                        sim_counts[target_sem]   = sim_counts.get(target_sem, 0) + 1
                    elif original_sem is None:
                        sim_counts[target_sem] = sim_counts.get(target_sem, 0) + 1
                for cc in avoided_list:
                    original_sem = base_course_to_sem.get(cc)
                    if original_sem is not None:
                        sim_counts[original_sem] = sim_counts.get(original_sem, 0) - 1

                for s, count in sim_counts.items():
                    if s not in remaining_set:
                        continue
                    if count > MAX_ALLOWED_COURSES_PER_SEM:
                        excess = count - MAX_ALLOWED_COURSES_PER_SEM
                        result["pre_solve_violations"].append(
                            f"Semester {s} would have **{count} courses** after your changes "
                            f"(maximum allowed is **{MAX_ALLOWED_COURSES_PER_SEM}**). "
                            f"Move at least **{excess}** course(s) to another semester."
                        )

            # ── CHECK 10: Category credit requirements ────────────────────────
            earned_by_cat = defaultdict(int)
            for c in completed_set:
                ci = loader.get_course_by_code(c)
                if ci:
                    earned_by_cat[ci['course_type']] += loader.get_credits(c)

            for category, requirements in loader.credit_requirements.items():
                required       = requirements.get('required', 0)
                already_earned = earned_by_cat.get(category, 0)
                if already_earned >= required:
                    continue

                if category == 'Combined Elective':
                    cat_courses = [
                        c for c in eligible_courses
                        if loader.get_course_by_code(c) and
                        loader.get_course_by_code(c).get('course_type', '') in
                        ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
                    ]
                else:
                    cat_courses = [
                        c for c in eligible_courses
                        if loader.get_course_by_code(c) and
                        loader.get_course_by_code(c).get('course_type', '') == category
                    ]

                available  = sum(loader.get_credits(c) for c in cat_courses)
                still_need = required - already_earned
                if available < still_need:
                    shortfall = still_need - available
                    result["pre_solve_violations"].append(
                        f"**Graduation category '{category}'** cannot be satisfied. "
                        f"You need **{still_need} more credits** in this category but only "
                        f"**{available} credits** worth of eligible courses remain. "
                        f"Shortfall: **{shortfall} credits**. Restore some removed courses "
                        f"from this category."
                    )
                    result["credit_shortfalls"].append((category, still_need, available))

            # ── CHECK 11: Total graduation credits ────────────────────────────
            credits_earned = round(sum(loader.get_credits(c) for c in completed_set))
            total_available = sum(loader.get_credits(c) for c in eligible_courses)
            if credits_earned + total_available < TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE:
                shortfall = TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE - credits_earned - total_available
                result["pre_solve_violations"].append(
                    f"**Total graduation credits cannot be reached.** "
                    f"You have earned {credits_earned} credits and only {total_available} more "
                    f"are available in the current pool — total {credits_earned + total_available}, "
                    f"but **{TOTAL_MIN_CREDITS_FOR_GRAD_FROM_SEM_ONE} are required**. "
                    f"Restore at least **{shortfall} credits** worth of removed courses."
                )

            # ── CHECK 12: Prerequisite ordering for pinned courses ────────────
            for cc, ps in pinned_courses.items():
                if cc in avoided_set:
                    continue
                ci   = loader.get_course_by_code(cc)
                name = ci['course_name'] if ci else cc
                preqs = loader.get_prerequisites(cc)
                for preq in preqs:
                    if preq in completed_set:
                        continue
                    if preq in avoided_set:
                        result["pre_solve_violations"].append(
                            f"**{name}** ({cc}) is pinned to Semester {ps} but its prerequisite "
                            f"**{loader.get_course_by_code(preq)['course_name'] if loader.get_course_by_code(preq) else preq}** "
                            f"({preq}) has been removed. Restore the prerequisite or unpin {cc}."
                        )
                        continue
                    preq_pinned_sem = pinned_courses.get(preq)
                    if preq_pinned_sem is not None and preq_pinned_sem >= ps:
                        ci_preq = loader.get_course_by_code(preq)
                        result["pre_solve_violations"].append(
                            f"**{name}** ({cc}) is pinned to Semester {ps} but its prerequisite "
                            f"**{ci_preq['course_name'] if ci_preq else preq}** ({preq}) is pinned "
                            f"to Semester {preq_pinned_sem} — prerequisites must come **before** "
                            f"the course that needs them."
                        )

            # ── CHECK 13: Duplicate pins ──────────────────────────────────────
            seen_pins = {}
            for cc, ps in pinned_courses.items():
                if cc in seen_pins:
                    ci   = loader.get_course_by_code(cc)
                    name = ci['course_name'] if ci else cc
                    result["pre_solve_violations"].append(
                        f"**{name}** ({cc}) appears to be pinned to multiple semesters "
                        f"({seen_pins[cc]} and {ps}). Each course can only appear once."
                    )
                seen_pins[cc] = ps

            print(f"pre_solve_violations count: {len(result['pre_solve_violations'])}")
            for v in result['pre_solve_violations']:
                print(f"  VIOLATION: {v}")

        # ── LAYERED SOLVER CHECKS ─────────────────────────────────────────────
        # NOTE (Bug 3 fix): `eligible_courses` here is whatever the caller passed in.
        # For customization failures, the caller (app.py regen_clicked) must pass
        # `adjusted` (avoided-filtered), not the full eligible list.
        def try_solve(build_fn, time_limit=5.0):
            m = cp_model.CpModel()
            x = self._create_variables(m, eligible_courses, remaining_semesters)
            build_fn(m, x)
            for cc, ps in pinned_courses.items():
                if cc in eligible_courses and (cc, ps) in x:
                    m.add(x[cc, ps] == 1)
            if rearranged_list and remaining_semesters:
                # FIX (Bug 2): block the course's ORIGINAL semester, not always current_sem
                orig_map = {}
                if base_plan is not None:
                    orig_map = {c: s for s, clist in base_plan.items() for c in clist}
                for cc in rearranged_list:
                    orig_sem = orig_map.get(cc)
                    if orig_sem and cc in eligible_courses and (cc, orig_sem) in x:
                        m.add(x[cc, orig_sem] == 0)
            s = cp_model.CpSolver()
            s.parameters.max_time_in_seconds = time_limit
            s.parameters.num_search_workers  = 1
            return s.Solve(m) in [cp_model.OPTIMAL, cp_model.FEASIBLE]

        layers = [
            (
                "Credit bounds (16–25 credits per semester)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters)
                ),
                (
                    "After the current course pool is considered, it is impossible to fill "
                    "every remaining semester with between 16 and 25 credits. "
                    "This usually means too many courses were removed (not enough to hit 16), "
                    "or mandatory/pinned courses alone exceed 25 credits in some semester."
                ),
            ),
            (
                "Each course taken at most once + failed course retakes",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                ),
                (
                    f"Failed courses that must be retaken ({', '.join(failed_courses) if failed_courses else 'none'}) "
                    f"cannot be fit into the remaining semesters while staying within the 16–25 credit "
                    f"per semester bounds."
                ),
            ),
            (
                "Prerequisites",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                ),
                (
                    "Prerequisite ordering constraints conflict with the available semesters. "
                    "A course is required before its prerequisite can be completed in time."
                ),
            ),
            (
                "Slot conflicts (current semester only — future slots are unknown)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                ),
                (
                    f"Slot conflicts in Semester {current_sem} (the current semester) make it impossible "
                    f"to assemble a valid schedule. Slot conflicts are only enforced for the current "
                    f"semester because timetable slots for future semesters are not yet assigned."
                ),
            ),
            (
                "Theory-lab course pairing",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                ),
                (
                    "A theory course and its paired lab component cannot be scheduled in the same "
                    "semester. They are always required to be taken together."
                ),
            ),
            (
                "Graduation category credit requirements",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                ),
                (
                    "One or more graduation credit category requirements cannot be met with the "
                    "remaining eligible courses."
                ),
            ),
            (
                "Total graduation credits (≥ 160 credits overall)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters),
                ),
                (
                    "Even taking every remaining eligible course, the total credit count falls "
                    "below the 160 credits required for graduation."
                ),
            ),
            (
                "Year-level course unlock (courses only available from their designated year)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters),
                    self.add_year_level_course_unlock_constraint(m, x, eligible_courses, remaining_semesters),
                ),
                (
                    "A course has been pinned to a semester that is earlier than its designated year level."
                ),
            ),
            (
                "Maximum courses per semester (≤ 12 courses)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters),
                    self.add_year_level_course_unlock_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_max_allowed_courses_per_semester(m, x, eligible_courses, remaining_semesters),
                ),
                (
                    "Too many courses have been pinned into a single semester, exceeding the "
                    "maximum of 12 courses per semester."
                ),
            ),
            (
                "Mandatory course completion (all mandatory courses must be scheduled)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters),
                    self.add_year_level_course_unlock_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_max_allowed_courses_per_semester(m, x, eligible_courses, remaining_semesters),
                    self.add_mandatory_courses_completion_constraint(m, x, eligible_courses, remaining_semesters),
                ),
                
                (
                    "One or more mandatory courses cannot be scheduled in the remaining semesters "
                    "even after considering all other constraints."
                ),
            ),
            (
                "Project course placement (Project-I → Sem 7, Project-II/Internship → Sem 8)",
                lambda m, x: (
                    self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                    self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                    self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                    self.add_project_constraint(m, x, eligible_courses, remaining_semesters),
                ),
                (
                    "Project-I (BCSE497J) must be in Semester 7 and Project-II/Internship (BCSE498J/BCSE499J) "
                    "must be in Semester 8. If these are in the eligible pool but the remaining semesters "
                    "don't include 7 or 8, the plan becomes infeasible."
                ),
            ),
        ]

        # ── Run layered checks ─────────────────────────────────────────────────────
        broken_layer_name   = ""
        broken_layer_detail = ""
        layer_results = []  # NEW: track all results

        if not result["pre_solve_violations"]:
            for layer_name, build_fn, detail in layers:
                feasible = try_solve(build_fn)
                layer_results.append((layer_name, feasible))
                print(f"  Layer '{layer_name}': {'✅ FEASIBLE' if feasible else '❌ INFEASIBLE'}")
                if not feasible:
                    broken_layer_name   = layer_name
                    broken_layer_detail = detail
                    break

        result["broken_constraint_layer"]  = broken_layer_name
        result["broken_constraint_detail"] = broken_layer_detail
        result["layer_results"] = layer_results  # NEW: store for UI

        # ── Credit shortfall analysis ─────────────────────────────────────────
        earned_by_category = defaultdict(int)
        for cc in completed_set:
            ci = loader.get_course_by_code(cc)
            if ci:
                earned_by_category[ci['course_type']] += loader.get_credits(cc)

        for category, requirements in loader.credit_requirements.items():
            required       = requirements.get('required', 0)
            already_earned = earned_by_category.get(category, 0)
            if already_earned >= required:
                continue

            if category == 'Combined Elective':
                cat_courses = [
                    c for c in eligible_courses
                    if loader.get_course_by_code(c) and
                    loader.get_course_by_code(c).get('course_type', '') in
                    ['Discipline Elective', 'Open Elective', 'Multidisciplinary Elective']
                ]
            else:
                cat_courses = [
                    c for c in eligible_courses
                    if loader.get_course_by_code(c) and
                    loader.get_course_by_code(c).get('course_type', '') == category
                ]

            available    = sum(loader.get_credits(c) for c in cat_courses)
            still_needed = required - already_earned
            if available < still_needed:
                result["credit_shortfalls"].append((category, still_needed, available))

        # ── Mandatory course individual checks ────────────────────────────────
        mandatory_in_pool = [
            c for c in eligible_courses
            if loader.get_course_by_code(c) and loader.get_course_by_code(c).get('is_mandatory', False)
        ]
        for mc in mandatory_in_pool:
            preqs = loader.get_prerequisites(mc)
            unmet = [p for p in preqs if p not in completed_set and p not in eligible_courses]
            ci    = loader.get_course_by_code(mc)
            name  = ci['course_name'] if ci else mc
            if unmet:
                result["mandatory_issues"].append(
                    f"**{name}** ({mc}) is mandatory but its prerequisite(s) "
                    f"{', '.join(unmet)} are neither completed nor in the eligible course pool."
                )

        # ── Root cause summary ────────────────────────────────────────────────
        if result["pre_solve_violations"]:
            n = len(result["pre_solve_violations"])
            result["root_cause"] = (
                f"{n} direct rule violation{'s' if n > 1 else ''} detected in your changes "
                f"— fix these first before the solver can attempt a solution."
            )
        elif broken_layer_name:
            result["root_cause"] = f"Constraint layer **'{broken_layer_name}'** cannot be satisfied."
        elif result["slot_conflicts"]:
            result["root_cause"] = f"Slot conflict(s) between courses pinned to Semester {current_sem}."
        else:
            # NEW: All individual layers passed — it's an interaction
            passed_layers = [name for name, ok in layer_results if ok]
            result["root_cause"] = (
                "**Interacting constraints** — all individual constraint layers pass on their own, "
                "but together they are infeasible. This is a combinatorial conflict. "
                f"All {len(passed_layers)} layers passed individually."
            )
            result["interacting"] = True
            result["layer_results"] = layer_results

        # ── Actionable suggestion ─────────────────────────────────────────────
        if result["pre_solve_violations"]:
            violations_text = " ".join(result["pre_solve_violations"]).lower()
            if result["theory_lab_issues"] and any(
                t[2] is None for t in result["theory_lab_issues"]
            ):
                result["suggestion"] = (
                    "Restore the removed theory or lab course — theory and lab must "
                    "always be kept or removed together."
                )
            elif "credits" in violations_text and ("only have" in violations_text or "would have" in violations_text):
                result["suggestion"] = (
                    "Your course moves have caused one or more semesters to go outside the "
                    "16–25 credit range. Move courses back to balance the credit load."
                )
            elif "prerequisite" in violations_text:
                result["suggestion"] = (
                    "Restore the course(s) whose removal broke prerequisite chains, "
                    "or also remove all courses that depend on them."
                )
            elif result["year_level_issues"]:
                result["suggestion"] = (
                    "Move the pinned course(s) to a later semester that matches their year level."
                )
            elif result["theory_lab_issues"]:
                result["suggestion"] = (
                    "Make sure the theory course and its lab are pinned to the same semester, "
                    "or unpin one of them and let the solver decide."
                )
            elif result["slot_conflicts"]:
                result["suggestion"] = (
                    f"Unpin at least one of the conflicting courses from Semester {current_sem}."
                )
            else:
                result["suggestion"] = "Undo the most recent change and try a smaller adjustment."
        elif "Credit bounds" in broken_layer_name:
            result["suggestion"] = (
                "Restore some of the courses you removed — there are not enough courses "
                "left to fill each semester with the required 16–25 credits."
            )
        elif "failed course" in broken_layer_name.lower():
            result["suggestion"] = (
                "Failed courses must be retaken exactly once. Check that failed course slots "
                "do not conflict with too many other courses in the current semester."
            )
        elif "Prerequisite" in broken_layer_name:
            result["suggestion"] = (
                "Check if any pinned semesters place a course before its prerequisite can be completed."
            )
        elif "Slot conflict" in broken_layer_name:
            result["suggestion"] = (
                f"Two or more courses that must be in Semester {current_sem} share a timetable slot."
            )
        elif "Theory-lab" in broken_layer_name:
            result["suggestion"] = (
                "A theory course and its lab have been separated. "
                "Pin both to the same semester or unpin both."
            )
        elif "Category" in broken_layer_name:
            if result["credit_shortfalls"]:
                cats = [s[0] for s in result["credit_shortfalls"]]
                result["suggestion"] = (
                    f"Restore courses from these categories: {', '.join(cats)}."
                )
            else:
                result["suggestion"] = (
                    "Restore some elective courses — graduation category credit requirements "
                    "cannot be met with the current course pool."
                )
        elif "graduation credits" in broken_layer_name.lower():
            credits_earned  = round(sum(loader.get_credits(c) for c in completed_set))
            total_available = sum(loader.get_credits(c) for c in eligible_courses)
            shortage        = 160 - credits_earned - total_available
            result["suggestion"] = (
                f"You need at least {shortage} more credits worth of courses restored."
            )
        elif "Year-level" in broken_layer_name:
            result["suggestion"] = (
                "Move pinned courses to semesters that match their year level."
            )
        elif "Maximum courses" in broken_layer_name:
            result["suggestion"] = (
                "You have pinned more than 12 courses into one semester. "
                "Unpin some and spread them across other semesters."
            )
        elif "Mandatory" in broken_layer_name:
            result["suggestion"] = (
                "One or more mandatory courses cannot be placed anywhere. "
                "Check if their prerequisites are satisfied."
            )
        else:
            result["suggestion"] = (
                "Try resetting all customizations and reapplying them one at a time."
            )

        
        wearable = 'BCSE315L'
        wi = loader.get_course_by_code(wearable)
        w_slots = wi.get('slots', []) if wi else []
        print(f"DEBUG Wearable slots: {w_slots}")
        for cc in (base_plan or {}).get(current_sem, []):
            ci = loader.get_course_by_code(cc)
            s = ci.get('slots', []) if ci else []
            shared = set(w_slots) & set(s)
            print(f"  vs {cc}: slots={s}, shared={shared}")

        # ── MIS Detection: test pairs when all individual layers pass ──────────────
        if all(ok for _, ok in layer_results) and not result["pre_solve_violations"]:
            print("All individual layers feasible — testing pairwise interactions...")
            
            failing_pairs = []
            failing_triplets = []
            
            # Test every pair of constraint-adding functions
            # We need the raw functions, so restructure layers into (name, fn, detail) tuples
            # and test combinations
            
            constraint_fns = {
                "Credit bounds":           lambda m, x: self.add_min_max_credit_constraint(m, x, eligible_courses, remaining_semesters),
                "Course uniqueness":       lambda m, x: self.add_course_can_be_taken_only_once_constraint(m, x, eligible_courses, remaining_semesters),
                "Failed retakes":          lambda m, x: self.add_failed_courses_retake_constraint(m, x, failed_courses, remaining_semesters),
                "Prerequisites":           lambda m, x: self.add_preq_check_constraint(m, x, student, eligible_courses, remaining_semesters),
                "Slot conflicts":          lambda m, x: self.add_slot_conflict_constraint(m, x, eligible_courses, remaining_semesters),
                "Theory-lab pairing":      lambda m, x: self.add_theory_lab_pairing_constraint(m, x, student, eligible_courses, remaining_semesters),
                "Project placement":       lambda m, x: self.add_project_constraint(m, x, eligible_courses, remaining_semesters),
                "Category requirements":   lambda m, x: self.add_category_credit_requirement_constraint(m, x, student, eligible_courses, remaining_semesters),
                "Graduation credits":      lambda m, x: self.add_total_min_credits_req_for_graduation(m, x, student, eligible_courses, remaining_semesters),
                "Year-level unlock":       lambda m, x: self.add_year_level_course_unlock_constraint(m, x, eligible_courses, remaining_semesters),
                "Max courses/sem":         lambda m, x: self.add_max_allowed_courses_per_semester(m, x, eligible_courses, remaining_semesters),
                "Mandatory completion":    lambda m, x: self.add_mandatory_courses_completion_constraint(m, x, eligible_courses, remaining_semesters),
            }
            
            def try_solve_fns(fns_to_apply, time_limit=5.0):
                m = cp_model.CpModel()
                x = self._create_variables(m, eligible_courses, remaining_semesters)
                for fn in fns_to_apply:
                    fn(m, x)
                # apply pins/rearrangements too
                for cc, ps in pinned_courses.items():
                    if cc in eligible_courses and (cc, ps) in x:
                        m.add(x[cc, ps] == 1)
                if rearranged_list and remaining_semesters and base_plan is not None:
                    orig_map = {c: s for s, clist in base_plan.items() for c in clist}
                    for cc in rearranged_list:
                        orig_sem = orig_map.get(cc)
                        if orig_sem and cc in eligible_courses and (cc, orig_sem) in x:
                            m.add(x[cc, orig_sem] == 0)
                s = cp_model.CpSolver()
                s.parameters.max_time_in_seconds = time_limit
                s.parameters.num_search_workers = 1
                return s.Solve(m) in [cp_model.OPTIMAL, cp_model.FEASIBLE]
            
            names = list(constraint_fns.keys())
            fns   = list(constraint_fns.values())
            
            # ── Pairwise test ──────────────────────────────────────────────────────
            print("Testing pairs...")
            for i in range(len(names)):
                for j in range(i+1, len(names)):
                    feasible = try_solve_fns([fns[i], fns[j]])
                    if not feasible:
                        pair = (names[i], names[j])
                        failing_pairs.append(pair)
                        print(f"  ❌ PAIR FAILS: {names[i]} + {names[j]}")
            
            # ── Triplet test (only for pairs that individually passed but pair fails) ──
            # Only run triplets if no failing pairs found (true 3-way interaction)
            if not failing_pairs:
                print("No failing pairs — testing triplets...")
                for i in range(len(names)):
                    for j in range(i+1, len(names)):
                        for k in range(j+1, len(names)):
                            feasible = try_solve_fns([fns[i], fns[j], fns[k]])
                            if not feasible:
                                triplet = (names[i], names[j], names[k])
                                failing_triplets.append(triplet)
                                print(f"  ❌ TRIPLET FAILS: {names[i]} + {names[j]} + {names[k]}")
            
            result["failing_pairs"]    = failing_pairs
            result["failing_triplets"] = failing_triplets
            result["interacting"]      = True
            
            # Build human-readable MIS summaries
            mis_summaries = []
            for pair in failing_pairs:
                mis_summaries.append({
                    "title":       f"{pair[0]}  ×  {pair[1]}",
                    "constraints": list(pair),
                    "explanation": (
                        f"**{pair[0]}** and **{pair[1]}** are individually satisfiable, "
                        f"but **cannot be satisfied at the same time** given your current course pool "
                        f"and semester constraints. Removing or relaxing either one would make the "
                        f"plan feasible."
                    )
                })
            for triplet in failing_triplets:
                mis_summaries.append({
                    "title":       f"{triplet[0]}  ×  {triplet[1]}  ×  {triplet[2]}",
                    "constraints": list(triplet),
                    "explanation": (
                        f"These three constraints together cause infeasibility: "
                        f"**{triplet[0]}**, **{triplet[1]}**, and **{triplet[2]}**. "
                        f"No pair among them fails alone — all three must interact to create the conflict."
                    )
                })
            
            result["mis_summaries"] = mis_summaries
            
            if mis_summaries:
                names_str = " and ".join(
                    f"**{m['title']}**" for m in mis_summaries
                )
                result["root_cause"] = (
                    f"Interacting constraints found: {names_str}. "
                    f"These constraints are individually feasible but conflict together."
                )
            else:
                result["root_cause"] = (
                    "Infeasibility requires more than 3 constraints interacting — "
                    "extremely rare. Try resetting all customizations."
                )

        
        return result

    # Keep old name as alias for backward compatibility
    def diagnose_customization_infeasibility(
        self, student, adjusted_courses, failed_courses,
        remaining_sems, avoided_list, pinned_courses, loader
    ):
        return self.diagnose_infeasibility_core(
            student, adjusted_courses, failed_courses, remaining_sems,
            avoided_list=avoided_list, pinned_courses=pinned_courses,
            is_customization=True,
        )
import streamlit as st
import pandas as pd
import json
from data.data_loader import DataLoader
from cpsat import CoursePlanner, PLAN_CONFIGS
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict

# Page configuration
st.set_page_config(
    page_title="AI Course Planner",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .constraint-box {
        background-color: #e8f4f8;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #17a2b8;
    }
    .course-card {
        background-color: #ffffff;
        padding: 0.8rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        border: 1px solid #dee2e6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #28a745;
    }
    .warning-message {
        background-color: #fff3cd;
        color: #856404;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ffc107;
    }
    .info-box {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #17a2b8;
        margin-bottom: 1rem;
    }
    .plan-card {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 2px solid #dee2e6;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 1.5rem;
    }
    .plan-card.selected {
        border-color: #28a745;
        background-color: #f8fff9;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        padding: 0 2rem;
        font-size: 1rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'loader' not in st.session_state:
    st.session_state.loader = None
if 'student' not in st.session_state:
    st.session_state.student = None
if 'planner' not in st.session_state:
    st.session_state.planner = None
if 'all_plans' not in st.session_state:
    st.session_state.all_plans = None
if 'selected_plan_type' not in st.session_state:
    st.session_state.selected_plan_type = None
if 'llm_weights' not in st.session_state:
    st.session_state.llm_weights = None
if 'plan_explanation' not in st.session_state:
    st.session_state.plan_explanation = None
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

# Sidebar
with st.sidebar:
    st.markdown("### 🎓 AI Course Planner")
    st.markdown("---")
    
    # Load data section
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
                    st.error(f"❌ Error loading data: {str(e)}")
    else:
        st.success("✅ Course data loaded")
        
        # Student selection with dropdown
        st.markdown("#### 👤 Select Student")
        
        # Dropdown for predefined student IDs
        available_students = [
            "21BCE0001",
            "21BCE0042", 
            "21BCE0089",
            "21BCE0134"
        ]
        
        student_id = st.selectbox(
            "Select Student ID",
            options=available_students,
            index=3,  # Default to 21BCE0134
            help="Choose a student profile to load"
        )
        
        if st.button("🔍 Load Student", use_container_width=True):
            with st.spinner(f"Loading student {student_id}..."):
                try:
                    student = st.session_state.loader.load_student(student_id)
                    st.session_state.student = student
                    
                    # Initialize planner
                    st.session_state.planner = CoursePlanner(
                        st.session_state.loader,
                        'gpt-4.1-mini'
                    )
                    
                    # Clear previous plans
                    st.session_state.all_plans = None
                    st.session_state.selected_plan_type = None
                    st.session_state.llm_weights = None
                    st.session_state.plan_explanation = None
                    
                    st.success(f"✅ Loaded {student.name}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error loading student: {str(e)}")
        
        # Clear data button
        if st.button("🗑️ Clear All Data", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    st.markdown("---")
    
    # Quick stats
    if st.session_state.loader and st.session_state.student:
        st.markdown("#### 📊 Quick Stats")
        student = st.session_state.student
        loader = st.session_state.loader
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Courses", len(loader.courses_data))
            st.metric("Completed", len(student.completed_courses))
        with col2:
            st.metric("CGPA", f"{student.cgpa:.2f}")
            st.metric("Failed", len(student.failed_courses))
        
        # Credits info
        total_earned = sum([loader.get_credits(c) for c in student.completed_courses])
        st.metric("Credits Earned", f"{total_earned}/160")
        
        # Progress bar
        progress = (total_earned / 160) * 100
        st.progress(progress / 100)
        st.caption(f"{progress:.1f}% Complete")

# Main content
st.markdown('<p class="main-header">🎓 AI-Powered Course Planner</p>', unsafe_allow_html=True)

if not st.session_state.data_loaded:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("""
    ### 👋 Welcome to AI Course Planner!
    
    This intelligent system helps you plan your academic journey by:
    - 📊 Analyzing your academic progress
    - 🎯 Matching courses with your interests using AI
    - ⚡ Optimizing your schedule with constraint programming
    - 📈 Ensuring you meet all graduation requirements
    
    **Get Started:**
    👈 Click "Load Course Data" in the sidebar to begin!
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

if not st.session_state.student:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("""
    ### 📚 Course Data Loaded!
    
    Now let's load your student profile.
    
    👈 Select a Student ID from the dropdown in the sidebar and click "Load Student"
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# Create tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "👤 Student Profile",
    "📚 Course Catalog",
    "⚙️ Constraints & Objectives",
    "🎯 Generate Plans",
    "📊 Results & Analysis"
])

# ============================================================================
# TAB 1: STUDENT PROFILE
# ============================================================================
with tab1:
    student = st.session_state.student
    loader = st.session_state.loader
    
    st.markdown('<p class="sub-header">Student Information</p>', unsafe_allow_html=True)
    
    # Basic info cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Student ID", student.student_id)
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Name", student.name)
        st.markdown('</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Current Semester", f"Semester {student.current_semester}")
        st.markdown('</div>', unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("CGPA", f"{student.cgpa:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Academic progress
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown('<p class="sub-header">📈 Academic Progress</p>', unsafe_allow_html=True)
        
        # Calculate credits by category
        earned_by_category = defaultdict(int)
        for course_code in student.completed_courses:
            course = loader.get_course_by_code(course_code)
            if course:
                category = course['course_type']
                earned_by_category[category] += loader.get_credits(course_code)
        
        # Create progress bars
        progress_data = []
        for category, requirements in loader.credit_requirements.items():
            required = requirements.get('required', 0)
            if required > 0:
                earned = earned_by_category.get(category, 0)
                progress_data.append({
                    'Category': category,
                    'Earned': earned,
                    'Required': required,
                    'Progress': min(100, (earned / required) * 100) if required > 0 else 0
                })
        
        df_progress = pd.DataFrame(progress_data)
        
        # Display progress bars
        for _, row in df_progress.iterrows():
            st.write(f"**{row['Category']}**")
            progress_text = f"{row['Earned']:.0f} / {row['Required']:.0f} credits ({row['Progress']:.0f}%)"
            st.progress(row['Progress'] / 100, text=progress_text)
            st.write("")
    
    with col2:
        st.markdown('<p class="sub-header">📊 Credit Summary</p>', unsafe_allow_html=True)
        
        total_earned = sum([loader.get_credits(c) for c in student.completed_courses])
        total_required = 160
        
        # Pie chart
        fig = go.Figure(data=[go.Pie(
            labels=['Earned', 'Remaining'],
            values=[total_earned, total_required - total_earned],
            hole=.4,
            marker_colors=['#1f77b4', '#e0e0e0']
        )])
        fig.update_layout(
            showlegend=True,
            height=300,
            margin=dict(t=30, b=0, l=0, r=0)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.metric("Total Credits", f"{total_earned} / {total_required}")
    
    st.markdown("---")
    
    # Semester-wise grades
    st.markdown('<p class="sub-header">📝 Semester-wise Performance</p>', unsafe_allow_html=True)
    
    # Group courses by semester
    semester_data = defaultdict(list)
    for record in student.course_records:
        semester_data[record.semester_taken].append(record)
    
    # Create DataFrame for each semester
    for sem in sorted(semester_data.keys()):
        with st.expander(f"📖 Semester {sem}", expanded=(sem == student.current_semester - 1)):
            sem_courses = semester_data[sem]
            
            df_sem = pd.DataFrame([
                {
                    'Course Code': r.course_code,
                    'Course Name': r.course_name,
                    'Credits': r.credits,
                    'Grade': r.grade,
                    'Status': '❌ Failed' if r.is_failed else '✅ Passed'
                }
                for r in sem_courses
            ])
            
            # Calculate semester stats
            sem_credits = sum([r.credits for r in sem_courses])
            sem_courses_count = len(sem_courses)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Courses", sem_courses_count)
            with col2:
                st.metric("Credits", sem_credits)
            with col3:
                failed_count = sum([1 for r in sem_courses if r.is_failed])
                st.metric("Failed", failed_count)
            
            st.dataframe(
                df_sem,
                use_container_width=True,
                hide_index=True
            )
    
    st.markdown("---")
    
    # Student preferences
    st.markdown('<p class="sub-header">⚙️ Preferences</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Interest Areas**")
        if hasattr(student, 'interest_areas') and isinstance(student.interest_areas, list):
            interests_text = st.text_area(
                "Edit your interests (one per line)",
                value="\n".join(student.interest_areas),
                height=150,
                help="Enter your areas of interest, one per line"
            )
            
            if st.button("💾 Update Interests"):
                student.interest_areas = [i.strip() for i in interests_text.split('\n') if i.strip()]
                st.success("✅ Interests updated!")
        else:
            st.info("No interest areas defined for this student")
    
    with col2:
        st.markdown("**Workload Preference**")
        workload_options = {
            'low': '🟢 Low (16-18 credits)',
            'medium': '🟡 Medium (19-22 credits)',
            'high': '🔴 High (23-25 credits)'
        }
        
        current_pref = student.workload_preference or 'low'
        selected_workload = st.selectbox(
            "Select your preferred workload",
            options=list(workload_options.keys()),
            format_func=lambda x: workload_options[x],
            index=list(workload_options.keys()).index(current_pref)
        )
        
        if st.button("💾 Update Workload"):
            student.workload_preference = selected_workload
            st.success("✅ Workload preference updated!")
        
        # st.markdown("**Other Preferences**")
        # st.info(f"🎯 Priority: {'GPA' if student.prioritize_gpa else 'Learning'}")
        # st.info(f"⚠️ Risk Tolerance: {student.risk_tolerance}")

# ============================================================================
# TAB 2: COURSE CATALOG
# ============================================================================
with tab2:
    st.markdown('<p class="sub-header">📚 Course Catalog</p>', unsafe_allow_html=True)
    
    loader = st.session_state.loader
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Courses", len(loader.courses_data))
    with col2:
        mandatory_count = sum(1 for c in loader.courses_data if c.get('is_mandatory', False))
        st.metric("Mandatory", mandatory_count)
    with col3:
        elective_count = len(loader.courses_data) - mandatory_count
        st.metric("Electives", elective_count)
    with col4:
        unique_slots = len(set(slot for c in loader.courses_data for slot in c.get('slots', [])))
        st.metric("Unique Slots", unique_slots)
    
    st.markdown("---")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_year = st.selectbox(
            "Filter by Year",
            options=['All'] + [f"Year {i}" for i in range(1, 5)],
            index=0
        )
    with col2:
        course_types = ['All'] + sorted(list(set([c['course_type'] for c in loader.courses_data])))
        filter_type = st.selectbox(
            "Filter by Type",
            options=course_types,
            index=0
        )
    with col3:
        filter_mandatory = st.selectbox(
            "Filter by Status",
            options=['All', 'Mandatory', 'Elective'],
            index=0
        )
    
    # Apply filters
    filtered_courses = []
    for course in loader.courses_data:
        # Year filter
        if filter_year != 'All':
            year_num = int(filter_year.split()[1])
            if course.get('year_offered', 1) != year_num:
                continue
        
        # Type filter
        if filter_type != 'All' and course['course_type'] != filter_type:
            continue
        
        # Mandatory filter
        if filter_mandatory == 'Mandatory' and not course.get('is_mandatory', False):
            continue
        if filter_mandatory == 'Elective' and course.get('is_mandatory', False):
            continue
        
        filtered_courses.append(course)
    
    st.write(f"**Showing {len(filtered_courses)} courses**")
    
    # Group by year
    courses_by_year = defaultdict(list)
    for course in filtered_courses:
        year = course.get('year_offered', 1)
        courses_by_year[year].append(course)
    
    # Display courses year by year
    for year in sorted(courses_by_year.keys()):
        with st.expander(f"📖 Year {year} - {len(courses_by_year[year])} courses", expanded=(year == 1)):
            courses = courses_by_year[year]
            
            # Create DataFrame
            df_courses = pd.DataFrame([
                {
                    'Code': c['course_code'],
                    'Name': c['course_name'],
                    'Credits': c['credits'],
                    'Type': c['course_type'],
                    'L-T-P-J': f"{c.get('L', 0)}-{c.get('T', 0)}-{c.get('P', 0)}-{c.get('J', 0)}",
                    'Mandatory': '✅' if c.get('is_mandatory', False) else '❌',
                    'Has Lab': '🧪' if c.get('has_lab', False) else '',
                    'Difficulty': f"{c.get('difficulty', 50)}%",
                    'Pass Rate': f"{c.get('pass_rate', 0) * 100:.0f}%"
                }
                for c in courses
            ])
            
            st.dataframe(
                df_courses,
                use_container_width=True,
                hide_index=True,
                height=400
            )

# ============================================================================
# TAB 3: CONSTRAINTS & OBJECTIVES
# ============================================================================
with tab3:
    st.markdown('<p class="sub-header">⚙️ Optimization Constraints & Objectives</p>', unsafe_allow_html=True)
    
    st.markdown("""
    Our course planner uses **Constraint Programming** with **Google OR-Tools CP-SAT Solver** 
    to find the optimal course schedule that satisfies all requirements while maximizing your preferences.
    """)
    
    st.markdown("---")
    
    # Hard Constraints
    st.markdown("### 🔒 Hard Constraints (Must Satisfy)")
    st.markdown("These are non-negotiable rules that every valid schedule must follow:")
    
    constraints = [
        {
            "name": "Credit Bounds",
            "description": "Each semester must have between 16-25 credits",
            "formula": "16 ≤ credits_per_semester ≤ 25",
            "rationale": "University policy requires minimum credits for full-time status and maximum to prevent overload"
        },
        {
            "name": "Course Uniqueness",
            "description": "Each course can be taken at most once across all semesters",
            "formula": "Σ(course_taken_in_sem_i) ≤ 1 for all semesters",
            "rationale": "Prevents duplicate course enrollment"
        },
        {
            "name": "Completed Courses",
            "description": "Already completed courses cannot be taken again",
            "formula": "course_taken = 0 if course in completed_courses",
            "rationale": "You don't retake passed courses"
        },
        {
            "name": "Prerequisites",
            "description": "A course can only be taken if all its prerequisites are completed",
            "formula": "take_course_i in sem_j ⟹ all prerequisites taken in sem < j",
            "rationale": "Ensures proper knowledge progression"
        },
        {
            "name": "Slot Conflicts",
            "description": "Courses with overlapping time slots cannot be taken together",
            "formula": "course_A + course_B ≤ 1 if slots overlap in same semester",
            "rationale": "You can't be in two places at once"
        },
        {
            "name": "Theory-Lab Pairing",
            "description": "Theory courses and their lab components must be taken together",
            "formula": "take_theory in sem_i ⟺ take_lab in sem_i",
            "rationale": "Labs complement theoretical knowledge"
        },
        {
            "name": "Category Requirements",
            "description": "Must complete minimum credits in each category (Foundation, Core, Elective, etc.)",
            "formula": "Σ(credits_in_category) + earned ≥ required_for_category",
            "rationale": "Degree requirements mandate balanced education"
        },
        {
            "name": "Project Constraints",
            "description": "Project courses must be taken in specific semesters (Project-I in sem 7, Project-II in sem 8)",
            "formula": "BCSE497J must be in semester 7; BCSE498J/BCSE499J must be in semester 8",
            "rationale": "Capstone projects require prior coursework"
        },
        {
            "name": "Failed Course Retake",
            "description": "Failed courses must be retaken exactly once across remaining semesters",
            "formula": "Σ(failed_course_in_remaining_sems) = 1",
            "rationale": "Must clear failed courses for graduation — urgency handled via objective function to schedule as early as constraints allow"
        },
        {
            "name": "Year Level Unlocking",
            "description": "Courses can only be taken in or after their designated year",
            "formula": "take_course = 0 if current_year < course_year_offered",
            "rationale": "Advanced courses require foundational knowledge"
        },
        {
            "name": "Total Credits for Graduation",
            "description": "Must complete at least 160 total credits",
            "formula": "credits_earned + Σ(future_credits) ≥ 160",
            "rationale": "University graduation requirement"
        },
        {
            "name": "Maximum Courses per Semester",
            "description": "Cannot take more than 12 courses in a single semester",
            "formula": "Σ(courses_in_semester) ≤ 12",
            "rationale": "Prevents unrealistic course loads"
        }
    ]
    
    for i, constraint in enumerate(constraints, 1):
        with st.container():
            st.markdown(f'<div class="constraint-box">', unsafe_allow_html=True)
            st.markdown(f"**{i}. {constraint['name']}**")
            st.write(f"📝 {constraint['description']}")
            st.code(constraint['formula'], language='python')
            st.info(f"💡 Why: {constraint['rationale']}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Soft Constraints
    st.markdown("### 🎯 Soft Constraints (Preferences)")
    st.markdown("These are optimized to give you the best possible schedule:")
    
    soft_constraints = [
        {
            "name": "Workload Balance",
            "description": "Distribute credits according to your workload preference",
            "weight": "60",
            "formula": "Minimize: Σ(penalty for deviating from target credits)",
            "details": "Low: 16-18 credits, Medium: 19-22 credits, High: 23-25 credits per semester"
        },
        {
            "name": "Course Interest Alignment",
            "description": "Prioritize courses matching your interests using LLM-based scoring",
            "weight": "30-120 (varies by plan)",
            "formula": "Maximize: Σ(interest_weight × course_taken × semester_priority)",
            "details": "AI analyzes course content vs. your interests and assigns 0-1 weights"
        },
        {
            "name": "Early Mandatory Completion",
            "description": "Complete mandatory courses earlier to avoid bottlenecks",
            "weight": "60-100 (varies by plan)",
            "formula": "Maximize: Σ(mandatory_course × (9 - semester))",
            "details": "Earlier semesters get higher priority for mandatory courses"
        },
        {
            "name": "Prerequisite Unlocking",
            "description": "Prioritize courses that unlock many other courses",
            "weight": "30-40 (varies by plan)",
            "formula": "Maximize: Σ(num_courses_unlocked × course_taken × semester_priority)",
            "details": "Taking prerequisite courses early opens up more options later"
        }
    ]
    
    for i, sc in enumerate(soft_constraints, 1):
        with st.container():
            st.markdown(f'<div class="constraint-box">', unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{i}. {sc['name']}**")
                st.write(f"📝 {sc['description']}")
            with col2:
                st.metric("Weight", sc['weight'])
            st.code(sc['formula'], language='python')
            st.info(f"💡 {sc['details']}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Plan Types - DYNAMIC
    num_plans = len(PLAN_CONFIGS)
    st.markdown(f"### 🎯 {num_plans} Optimization Strategies")
    st.markdown(f"The planner generates {num_plans} different plans, each optimized for a different priority:")
    
    for plan_type, config in PLAN_CONFIGS.items():
        with st.container():
            st.markdown(f'<div class="constraint-box">', unsafe_allow_html=True)
            
            # Determine emoji based on plan type
            if 'balanced' in plan_type:
                emoji = "⚖️"
            elif 'graduation' in plan_type:
                emoji = "🎓"
            else:
                emoji = "❤️"
            
            st.markdown(f"### {emoji} {config['name']}")
            st.write(f"**Description:** {config['description']}")
            
            weights = config['weights']
            # Display weights
            st.code(f"""Weights Configuration:
                - Mandatory Score Weight:     {weights['mandatory']}
                - Unlock Score Weight:        {weights['unlock']}
                - Interest Score Weight:      {weights['interest']}
                - Workload Penalty Weight:    {weights['workload']}
                - Failed Course Urgency Weight: {weights.get('failed', 200)}""", language='text')
            
            # Explanation of what this means
            if 'balanced' in plan_type:
                st.success("✨ Best for: Students who want a steady, sustainable path to graduation with balanced priorities")
            elif 'graduation' in plan_type:
                st.success("✨ Best for: Students prioritizing timely graduation and efficient requirement completion")
            else:
                st.success("✨ Best for: Students who want to explore their interests deeply and align with career goals")
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Objective Function
    st.markdown("### 🎯 Objective Function")
    st.markdown("""
    The solver **maximizes** this combined objective (weights vary by plan type):
    """)
    
    # Build dynamic weight examples from actual configs
    weight_examples = []
    for plan_type, config in PLAN_CONFIGS.items():
        w = config['weights']
        weight_examples.append(f"    {config['name']:20s} w_mandatory={w['mandatory']}, w_unlock={w['unlock']}, w_interest={w['interest']}, w_workload={w['workload']}, w_failed={w['failed']}")
    
    st.code(f"""
Maximize:
    w_mandatory × (mandatory_score)      # Complete mandatory courses early
  + w_unlock × (unlock_score)            # Take prerequisite courses early
  + w_interest × (interest_score)        # Align with your interests
  + w_failed × (failed_course_urgency_score)    # Retake failed courses ASAP
  - w_workload × (workload_penalty)      # Balance workload per preference

Where:
    mandatory_score = Σ(mandatory_course × (9 - semester))
    unlock_score = Σ(num_unlocked_courses × course_taken × (9 - semester))
    interest_score = Σ(LLM_weight × course_taken × (9 - semester))
    failed_course_urgency_score = Σ(failed_course * (8 - semester + 1))
    workload_penalty = Σ(deviation from target credits per semester)
    
    
Weights vary by plan type:
{chr(10).join(weight_examples)}
    """, language='python')
    
    st.success("""
    **Result**: The solver finds schedules that:
    - ✅ Satisfy ALL hard constraints (graduation requirements)
    - 🎯 Maximize your preferences based on plan type
    - ⚡ Unlock future courses efficiently
    - 🤖 Use AI to match courses with your interests
    """)

# ============================================================================
# TAB 4: GENERATE PLANS
# ============================================================================
with tab4:
    st.markdown('<p class="sub-header">🎯 Generate Course Plans</p>', unsafe_allow_html=True)
    
    student = st.session_state.student
    loader = st.session_state.loader
    planner = st.session_state.planner
    
    # Summary before generation
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        remaining_courses = len([c for c in loader.get_all_course_codes() if c not in student.completed_courses])
        st.metric("Remaining Courses", remaining_courses)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        remaining_credits = loader.get_remaining_credits_by_type(student)
        total_remaining = sum(remaining_credits.values())
        st.metric("Remaining Credits", total_remaining)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        remaining_sems = 9 - student.current_semester
        st.metric("Remaining Semesters", remaining_sems)
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Show current preferences
    st.markdown("### 📋 Current Preferences")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Interest Areas:**")
        if hasattr(student, 'interest_areas') and isinstance(student.interest_areas, list):
            for interest in student.interest_areas:
                st.write(f"• {interest}")
        else:
            st.info("No interest areas defined")
    
    with col2:
        st.markdown("**Settings:**")
        st.write(f"• Workload: **{student.workload_preference or 'medium'}**")
        st.write(f"• Priority: **{'GPA' if student.prioritize_gpa else 'Learning'}**")
        st.write(f"• Risk Tolerance: **{student.risk_tolerance}**")
    
    st.markdown("---")
    
    # Information box - DYNAMIC
    num_plans = len(PLAN_CONFIGS)
    
    # Build plan list with emojis
    plan_list_items = []
    for plan_type, config in PLAN_CONFIGS.items():
        if 'balanced' in plan_type:
            emoji = "⚖️"
        elif 'graduation' in plan_type:
            emoji = "🎓"
        else:
            emoji = "❤️"
        plan_list_items.append(f"- {emoji} **{config['name']}**: {config['description']}")
    
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    plan_bullets = "\n".join(plan_list_items)
    st.markdown(f"""
    ### 🚀 Generate Multiple Plans
    
    Click the button below to generate **{num_plans} different course plans**, each optimized for a different strategy:
    
{plan_bullets}
    
    The AI will analyze all courses against your interests and the optimizer will create the best schedules!
    
    **This process takes 1-2 minutes** as it:
    1. Analyzes your interests with AI (GPT-4)
    2. Builds constraint satisfaction problems
    3. Solves {num_plans} optimization problems
    4. Generates detailed explanations for each plan
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Generate button
    if st.button(f"🚀 Generate All {num_plans} Plans", type="primary", use_container_width=True):
        progress_bar = st.progress(0, text="🔄 Starting optimization...")
        
        # Live log area
        st.markdown("### 📡 Live Progress")
        log_placeholder = st.empty()
        log_lines = []

        def ui_logger(message):
            log_lines.append(message)
            # Show last 8 lines so it scrolls naturally
            log_placeholder.code("\n".join(log_lines[-8:]), language=None)

        # Attach logger to planner
        planner.set_ui_logger(ui_logger)

        try:
            progress_bar.progress(5, text="📚 Analyzing eligible courses...")
            ui_logger("📚 Loading eligible courses...")
            
            remaining_semesters = list(range(student.current_semester, 9))
            eligible_courses, failed_courses = planner.get_eligible_and_failed_courses(student)
            ui_logger(f"✅ Found {len(eligible_courses)} eligible courses, {len(failed_courses)} failed courses to retake")

            progress_bar.progress(15, text="🤖 Generating AI interest weights...")
            llm_weights = planner.get_course_interest_weights_from_llm(student, eligible_courses)

            if llm_weights:
                st.session_state.llm_weights = llm_weights
                progress_bar.progress(30, text="✅ Interest weights generated!")

            all_plans = {}
            total_plans = len(PLAN_CONFIGS)

            for idx, (plan_type, config) in enumerate(PLAN_CONFIGS.items(), 1):
                start_progress = 30 + (idx - 1) * (60 // total_plans)
                end_progress = 30 + idx * (60 // total_plans)

                if 'balanced' in plan_type:
                    emoji = "⚖️"
                elif 'graduation' in plan_type:
                    emoji = "🎓"
                else:
                    emoji = "❤️"

                progress_bar.progress(start_progress, text=f"{emoji} Generating {config['name']}...")
                ui_logger(f"\n{'='*40}")
                ui_logger(f"{emoji} Starting: {config['name']}")
                ui_logger(f"{'='*40}")

                plan, explanation = planner.generate_single_plan(
                    student, eligible_courses, remaining_semesters,
                    failed_courses, llm_weights, weights=config['weights']
                )

                if plan and any(plan.values()):
                    total_courses = sum(len(c) for c in plan.values())
                    total_credits = sum(sum(loader.get_credits(c) for c in courses) for courses in plan.values())
                    ui_logger(f"✅ {config['name']} complete — {total_courses} courses, {total_credits} credits")
                    progress_bar.progress(end_progress, text=f"✅ {config['name']} done!")
                    all_plans[plan_type] = {'config': config, 'plan': plan, 'explanation': explanation}

            progress_bar.progress(100, text="✅ All plans generated!")
            ui_logger("\n🎉 All plans generated successfully!")
            st.session_state.all_plans = all_plans

            # ... rest of success/failure handling
            
            # Success message
            if all_plans and len(all_plans) > 0:
                st.balloons()
                st.markdown('<div class="success-message">', unsafe_allow_html=True)
                st.markdown(f"### ✅ Successfully Generated {len(all_plans)} Plans!")
                st.markdown("Navigate to the **Results & Analysis** tab to explore and compare your personalized course plans.")
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Quick preview
                st.markdown("### 📊 Quick Preview")
                
                for plan_type, plan_data in all_plans.items():
                    config = plan_data['config']
                    plan = plan_data['plan']
                    
                    total_courses = sum(len(courses) for courses in plan.values())
                    total_credits = sum(sum(loader.get_credits(c) for c in courses) for courses in plan.values())
                    
                    # Determine emoji
                    if 'balanced' in plan_type:
                        emoji = "⚖️"
                    elif 'graduation' in plan_type:
                        emoji = "🎓"
                    else:
                        emoji = "❤️"
                    
                    with st.expander(f"{emoji} {config['name']} - {total_courses} courses, {total_credits} credits"):
                        st.write(f"**Description:** {config['description']}")
                        
                        for sem in sorted(plan.keys()):
                            if plan[sem]:
                                sem_credits = sum(loader.get_credits(c) for c in plan[sem])
                                st.write(f"- Semester {sem}: {len(plan[sem])} courses, {sem_credits} credits")
            else:
                st.markdown('<div class="warning-message">', unsafe_allow_html=True)
                st.markdown("### ⚠️ No Feasible Plans Found")
                st.markdown("The constraints might be too restrictive. Try adjusting your preferences or check your completed courses.")
                st.markdown('</div>', unsafe_allow_html=True)

                # Run diagnosis and show reasons
                with st.spinner("🔍 Diagnosing the issue..."):
                    reasons = planner.diagnose_infeasibility(
                        student,
                        eligible_courses,
                        failed_courses,
                        remaining_semesters
                    )
                
                for reason in reasons:
                    st.error(f"❌ {reason}")
                
                st.info("💡 **Suggestions:** Contact your academic advisor or review your failed courses and prerequisite chains.")
                        

        except Exception as e:
            progress_bar.empty()
            # status_placeholder.empty()
            st.error(f"❌ Error generating plans: {str(e)}")
            with st.expander("🔍 View Error Details"):
                st.exception(e)

# ============================================================================
# TAB 5: RESULTS & ANALYSIS (continues in next file due to length)
# ============================================================================
# [TAB 5 code continues - it's very long, so I'll provide it in a separate response if needed]
# The TAB 5 code remains the same as your original - it already dynamically handles any number of plans

# ============================================================================
# TAB 5: RESULTS & ANALYSIS
# ============================================================================
with tab5:
    st.markdown('<p class="sub-header">📊 Results & Analysis</p>', unsafe_allow_html=True)
    
    if not st.session_state.all_plans:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("""
        ### 🎯 No Plans Generated Yet
        
        Please go to the **Generate Plans** tab to create your personalized course schedules.
        """)
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()
    
    all_plans = st.session_state.all_plans
    student = st.session_state.student
    loader = st.session_state.loader
    
    # Plan Selection
    st.markdown("### 🎯 Select a Plan to Explore")
    
    # Create columns for plan cards
    plan_types = list(all_plans.keys())
    cols = st.columns(len(plan_types))
    
    for idx, (col, plan_type) in enumerate(zip(cols, plan_types)):
        with col:
            plan_data = all_plans[plan_type]
            config = plan_data['config']
            plan = plan_data['plan']
            
            total_courses = sum(len(courses) for courses in plan.values())
            total_credits = sum(sum(loader.get_credits(c) for c in courses) for courses in plan.values())
            
            # Determine emoji based on plan type
            if 'balanced' in plan_type:
                emoji = "⚖️"
            elif 'graduation' in plan_type:
                emoji = "🎓"
            else:
                emoji = "❤️"
            
            # Create card
            is_selected = st.session_state.selected_plan_type == plan_type
            card_class = "plan-card selected" if is_selected else "plan-card"
            
            st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
            st.markdown(f"### {emoji} {config['name']}")
            st.write(config['description'])
            st.metric("Total Courses", total_courses)
            st.metric("Total Credits", total_credits)
            
            if st.button(f"Select This Plan", key=f"select_{plan_type}", use_container_width=True):
                st.session_state.selected_plan_type = plan_type
                st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    # If no plan selected yet, show comparison
    if not st.session_state.selected_plan_type:
        st.markdown("---")
        st.info("👆 Select a plan above to see detailed analysis, or scroll down to compare all plans side-by-side.")
        
        # Comparison view
        st.markdown("### 📊 Plan Comparison")
        
        comparison_data = []
        for plan_type, plan_data in all_plans.items():
            config = plan_data['config']
            plan = plan_data['plan']
            
            total_courses = sum(len(courses) for courses in plan.values())
            total_credits = sum(sum(loader.get_credits(c) for c in courses) for courses in plan.values())
            
            # Count mandatory vs elective
            mandatory_count = 0
            elective_count = 0
            for courses in plan.values():
                for c in courses:
                    course_info = loader.get_course_by_code(c)
                    if course_info and course_info.get('is_mandatory', False):
                        mandatory_count += 1
                    else:
                        elective_count += 1
            
            comparison_data.append({
                'Plan': config['name'],
                'Total Courses': total_courses,
                'Total Credits': total_credits,
                'Mandatory': mandatory_count,
                'Electives': elective_count
            })
        
        df_comparison = pd.DataFrame(comparison_data)
        st.dataframe(df_comparison, use_container_width=True, hide_index=True)
        
        # Side-by-side semester comparison
        st.markdown("---")
        st.markdown("### 📅 Semester-by-Semester Comparison")
        
        # Get all semesters across all plans
        all_semesters = set()
        for plan_data in all_plans.values():
            all_semesters.update(plan_data['plan'].keys())
        
        for sem in sorted(all_semesters):
            st.markdown(f"#### Semester {sem}")
            
            sem_cols = st.columns(len(plan_types))
            for col, plan_type in zip(sem_cols, plan_types):
                with col:
                    plan_data = all_plans[plan_type]
                    config = plan_data['config']
                    plan = plan_data['plan']
                    
                    if sem in plan and plan[sem]:
                        courses = plan[sem]
                        sem_credits = sum(loader.get_credits(c) for c in courses)
                        
                        st.markdown(f"**{config['name']}**")
                        st.write(f"{len(courses)} courses, {sem_credits} credits")
                        
                        for course_code in courses:
                            course_info = loader.get_course_by_code(course_code)
                            if course_info:
                                st.write(f"• {course_code}")
                    else:
                        st.markdown(f"**{config['name']}**")
                        st.write("No courses")
            
            st.markdown("---")
        
        st.stop()
    
    # Show detailed analysis for selected plan
    selected_plan_type = st.session_state.selected_plan_type
    selected_plan_data = all_plans[selected_plan_type]
    config = selected_plan_data['config']
    plan = selected_plan_data['plan']
    explanation = selected_plan_data.get('explanation', None)
    
    st.markdown("---")
    st.markdown(f"### 📋 Detailed Analysis: {config['name']}")
    
    # Check if plan has courses
    if not any(len(courses) > 0 for courses in plan.values()):
        st.warning("⚠️ No courses were scheduled for this plan.")
        
        with st.spinner("🔍 Diagnosing the issue..."):
            eligible_courses, failed_courses = planner.get_eligible_and_failed_courses(student)
            remaining_semesters = list(range(student.current_semester, 9))
            reasons = planner.diagnose_infeasibility(
                student,
                eligible_courses,
                failed_courses,
                remaining_semesters
            )
        
        for reason in reasons:
            st.error(f"❌ {reason}")
        
        st.info("💡 **Suggestions:** Contact your academic advisor or review your failed courses and prerequisite chains.")
        st.stop()
    
    # Summary metrics
    st.markdown("#### 📈 Plan Summary")
    
    total_courses = sum(len(courses) for courses in plan.values())
    total_credits = sum(sum(loader.get_credits(c) for c in courses) for courses in plan.values())
    completed_credits = sum([loader.get_credits(c) for c in student.completed_courses])
    final_credits = completed_credits + total_credits
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Planned Courses", total_courses)
    with col2:
        st.metric("Planned Credits", total_credits)
    with col3:
        st.metric("Total After Plan", final_credits)
    with col4:
        progress = (final_credits / 160) * 100
        st.metric("Progress", f"{progress:.1f}%")
    
    st.markdown("---")
    
    # Semester-by-semester plan
    st.markdown("#### 📅 Semester-by-Semester Plan")
    
    for sem in sorted(plan.keys()):
        if not plan[sem]:
            continue
            
        courses = plan[sem]
        sem_credits = sum(loader.get_credits(c) for c in courses)
        
        with st.expander(f"📖 Semester {sem} - {len(courses)} courses, {sem_credits} credits", expanded=True):
            # Semester metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Courses", len(courses))
            with col2:
                st.metric("Credits", sem_credits)
            with col3:
                # Count mandatory vs elective
                mandatory_count = sum(1 for c in courses if loader.get_course_by_code(c).get('is_mandatory', False))
                st.metric("Mandatory", mandatory_count)
            
            # Course details
            course_data = []
            for course_code in courses:
                course_info = loader.get_course_by_code(course_code)
                if course_info:
                    course_data.append({
                        'Code': course_code,
                        'Name': course_info['course_name'],
                        'Credits': loader.get_credits(course_code),
                        'Type': course_info['course_type'],
                        'Mandatory': '✅' if course_info.get('is_mandatory', False) else '❌',
                        'Difficulty': f"{course_info.get('difficulty', 50)}%",
                        'Pass Rate': f"{course_info.get('pass_rate', 0) * 100:.0f}%",
                        'Slots': ', '.join(course_info.get('slots', []))
                    })
            
            df_sem = pd.DataFrame(course_data)
            st.dataframe(df_sem, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Credit distribution
    st.markdown("#### 📊 Credit Distribution Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Credits per semester bar chart
        sem_credits_data = []
        for sem in sorted(plan.keys()):
            if plan[sem]:
                credits = sum(loader.get_credits(c) for c in plan[sem])
                sem_credits_data.append({'Semester': f"Sem {sem}", 'Credits': credits})
        
        df_sem_credits = pd.DataFrame(sem_credits_data)
        fig1 = px.bar(
            df_sem_credits,
            x='Semester',
            y='Credits',
            title='Credits per Semester',
            color='Credits',
            color_continuous_scale='Blues'
        )
        fig1.add_hline(y=16, line_dash="dash", line_color="red", annotation_text="Min (16)")
        fig1.add_hline(y=25, line_dash="dash", line_color="red", annotation_text="Max (25)")
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # Course type distribution
        type_counts = defaultdict(int)
        for courses in plan.values():
            for c in courses:
                course_info = loader.get_course_by_code(c)
                if course_info:
                    type_counts[course_info['course_type']] += 1
        
        df_types = pd.DataFrame([
            {'Type': k, 'Count': v}
            for k, v in type_counts.items()
        ])
        
        fig2 = px.pie(
            df_types,
            values='Count',
            names='Type',
            title='Course Type Distribution'
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("---")
    
    # Difficulty and workload analysis
    st.markdown("#### 📈 Difficulty & Workload Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Average difficulty per semester
        diff_data = []
        for sem in sorted(plan.keys()):
            if plan[sem]:
                difficulties = [loader.get_course_by_code(c).get('difficulty', 50) for c in plan[sem]]
                avg_diff = sum(difficulties) / len(difficulties) if difficulties else 0
                diff_data.append({'Semester': f"Sem {sem}", 'Avg Difficulty': avg_diff})
        
        df_diff = pd.DataFrame(diff_data)
        fig3 = px.line(
            df_diff,
            x='Semester',
            y='Avg Difficulty',
            title='Average Course Difficulty per Semester',
            markers=True
        )
        fig3.update_yaxes(range=[0, 100])
        st.plotly_chart(fig3, use_container_width=True)
    
    with col2:
        # Pass rate analysis
        pass_rate_data = []
        for sem in sorted(plan.keys()):
            if plan[sem]:
                pass_rates = [loader.get_course_by_code(c).get('pass_rate', 0.8) * 100 for c in plan[sem]]
                avg_pass = sum(pass_rates) / len(pass_rates) if pass_rates else 0
                pass_rate_data.append({'Semester': f"Sem {sem}", 'Avg Pass Rate': avg_pass})
        
        df_pass = pd.DataFrame(pass_rate_data)
        fig4 = px.line(
            df_pass,
            x='Semester',
            y='Avg Pass Rate',
            title='Average Pass Rate per Semester',
            markers=True,
            color_discrete_sequence=['green']
        )
        fig4.update_yaxes(range=[0, 100])
        st.plotly_chart(fig4, use_container_width=True)
    
    st.markdown("---")
    
    # LLM Weights and Interest Analysis
    st.markdown("#### 🤖 AI Interest Analysis")
    st.markdown("""
    Our AI analyzed each course against your stated interests and assigned weights (0.0 to 1.0) 
    indicating how well each course aligns with what you're interested in.
    """)
    
    # Get LLM weights from session state (shared across all plans)
    llm_weights = st.session_state.llm_weights
    
    if llm_weights and llm_weights.courses:
        # Create a comprehensive DataFrame with all courses
        weight_data = []
        
        # Create a dict for quick lookup
        weight_dict = {cw.code: cw for cw in llm_weights.courses}
        
        # Get all courses from the plan
        planned_courses = set()
        for courses in plan.values():
            planned_courses.update(courses)
        
        # Add all weighted courses
        for course_weight in llm_weights.courses:
            course_info = loader.get_course_by_code(course_weight.code)
            if course_info:
                in_plan = course_weight.code in planned_courses
                weight_data.append({
                    'Course Code': course_weight.code,
                    'Course Name': course_weight.name,
                    'Interest Weight': course_weight.weight,
                    'Type': course_info.get('course_type', 'Unknown'),
                    'In Plan': '✅' if in_plan else '❌',
                    'AI Reasoning': course_weight.reason
                })
        
        # Sort by weight (highest first)
        weight_data.sort(key=lambda x: x['Interest Weight'], reverse=True)
        df_weights = pd.DataFrame(weight_data)
        
        # Display summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            high_interest = len([w for w in weight_data if w['Interest Weight'] >= 0.8])
            st.metric("High Interest (≥0.8)", high_interest)
        with col2:
            medium_interest = len([w for w in weight_data if 0.5 <= w['Interest Weight'] < 0.8])
            st.metric("Medium Interest (0.5-0.8)", medium_interest)
        with col3:
            low_interest = len([w for w in weight_data if w['Interest Weight'] < 0.5])
            st.metric("Low Interest (<0.5)", low_interest)
        with col4:
            in_plan_count = len([w for w in weight_data if w['In Plan'] == '✅'])
            st.metric("Courses in Plan", in_plan_count)
        
        st.markdown("---")
        
        # Tabs for different views
        weight_tab1, weight_tab2, weight_tab3 = st.tabs([
            "📊 All Courses",
            "⭐ High Interest Courses",
            "📋 Courses in Your Plan"
        ])
        
        with weight_tab1:
            st.markdown("**All Courses Analyzed by AI**")
            st.markdown("*Sorted by interest weight (highest to lowest)*")
            
            # Color-code by weight
            def color_weight(val):
                if val >= 0.8:
                    return 'background-color: #d4edda'  # Green
                elif val >= 0.5:
                    return 'background-color: #fff3cd'  # Yellow
                else:
                    return 'background-color: #f8d7da'  # Red
            
            styled_df = df_weights.style.applymap(
                color_weight,
                subset=['Interest Weight']
            ).format({'Interest Weight': '{:.2f}'})
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
            
            # Download button for weights
            weights_csv = df_weights.to_csv(index=False)
            st.download_button(
                label="📥 Download Interest Analysis (CSV)",
                data=weights_csv,
                file_name=f"interest_weights_{student.student_id}.csv",
                mime="text/csv"
            )
        
        with weight_tab2:
            st.markdown("**High Interest Courses (Weight ≥ 0.8)**")
            st.markdown("*These courses strongly align with your interests*")
            
            high_interest_df = df_weights[df_weights['Interest Weight'] >= 0.8].copy()
            
            if len(high_interest_df) > 0:
                # Show detailed cards for high interest courses
                for idx, row in high_interest_df.iterrows():
                    with st.expander(f"⭐ {row['Course Code']}: {row['Course Name']} (Weight: {row['Interest Weight']:.2f})"):
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.metric("Weight", f"{row['Interest Weight']:.2f}")
                            st.write(f"**Type:** {row['Type']}")
                            st.write(f"**Status:** {row['In Plan']}")
                        with col2:
                            st.markdown("**🤖 AI Reasoning:**")
                            st.info(row['AI Reasoning'])
            else:
                st.info("No courses with weight ≥ 0.8 found. Consider broadening your interest areas.")
        
        with weight_tab3:
            st.markdown("**Courses Selected for Your Plan**")
            st.markdown("*Showing AI analysis for courses in your generated plan*")
            
            plan_courses_df = df_weights[df_weights['In Plan'] == '✅'].copy()
            
            if len(plan_courses_df) > 0:
                # Calculate average weight of planned courses
                avg_weight = plan_courses_df['Interest Weight'].mean()
                st.metric("Average Interest Weight of Planned Courses", f"{avg_weight:.2f}")
                
                st.markdown("---")
                
                # Group by semester
                for sem in sorted(plan.keys()):
                    if not plan[sem]:
                        continue
                    
                    sem_courses = plan[sem]
                    sem_weights = plan_courses_df[plan_courses_df['Course Code'].isin(sem_courses)]
                    
                    if len(sem_weights) > 0:
                        with st.expander(f"📖 Semester {sem} - Interest Analysis"):
                            sem_avg = sem_weights['Interest Weight'].mean()
                            st.metric(f"Average Interest Weight - Semester {sem}", f"{sem_avg:.2f}")
                            
                            for _, row in sem_weights.iterrows():
                                st.markdown(f"**{row['Course Code']}: {row['Course Name']}**")
                                col1, col2 = st.columns([1, 4])
                                with col1:
                                    # Color-code the weight badge
                                    if row['Interest Weight'] >= 0.8:
                                        badge_color = "🟢"
                                    elif row['Interest Weight'] >= 0.5:
                                        badge_color = "🟡"
                                    else:
                                        badge_color = "🔴"
                                    st.write(f"{badge_color} **Weight: {row['Interest Weight']:.2f}**")
                                with col2:
                                    st.markdown(f"*{row['AI Reasoning']}*")
                                st.markdown("---")
            else:
                st.warning("No courses in plan have weight data.")
        
        st.markdown("---")
        
        # Distribution visualization
        st.markdown("#### 📊 Interest Weight Distribution")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Histogram of weights
            fig_hist = px.histogram(
                df_weights,
                x='Interest Weight',
                nbins=20,
                title='Distribution of Interest Weights',
                labels={'Interest Weight': 'Interest Weight', 'count': 'Number of Courses'},
                color_discrete_sequence=['#1f77b4']
            )
            fig_hist.add_vline(x=0.8, line_dash="dash", line_color="green", annotation_text="High")
            fig_hist.add_vline(x=0.5, line_dash="dash", line_color="orange", annotation_text="Medium")
            st.plotly_chart(fig_hist, use_container_width=True)
        
        with col2:
            # Weight by course type
            type_weights = df_weights.groupby('Type')['Interest Weight'].mean().reset_index()
            type_weights = type_weights.sort_values('Interest Weight', ascending=False)
            
            fig_type = px.bar(
                type_weights,
                x='Type',
                y='Interest Weight',
                title='Average Interest Weight by Course Type',
                color='Interest Weight',
                color_continuous_scale='RdYlGn',
                labels={'Interest Weight': 'Avg Weight'}
            )
            fig_type.update_xaxes(tickangle=45)
            st.plotly_chart(fig_type, use_container_width=True)
    
    else:
        st.info("No LLM weight data available. Generate plans to see AI interest analysis.")
    
    st.markdown("---")
    
    # PLAN EXPLANATION SECTION
    if explanation:
        st.markdown("#### 📖 Detailed Plan Explanation")
        st.markdown("""
        Our AI advisor has analyzed your course plan and generated personalized explanations 
        for why each course was selected and placed in its specific semester.
        """)
        
        # Overall Summary Section
        with st.expander("📋 Overall Plan Summary & Strategy", expanded=True):
            st.markdown("##### 🎯 Your Personalized Plan")
            st.write(explanation.overall_plan_summary)
            
            st.markdown("---")
            
            st.markdown("##### 🎓 Graduation Path")
            st.write(explanation.graduation_path)
        
        st.markdown("---")
        
        # Semester-by-Semester Explanations
        st.markdown("##### 📅 Semester-by-Semester Breakdown")
        
        for sem_explanation in explanation.semesters:
            semester_num = sem_explanation.semester
            
            with st.expander(
                f"📖 Semester {semester_num} - Strategy & Course Explanations",
                expanded=(semester_num == student.current_semester)
            ):
                # Semester Overview
                st.markdown(f"**Semester {semester_num} Overview**")
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.markdown("**📊 Semester Strategy**")
                    st.info(sem_explanation.overall_strategy)
                
                with col2:
                    st.markdown("**⚖️ Workload Reasoning**")
                    st.info(sem_explanation.workload_reasoning)
                
                st.markdown("---")
                
                # Course-by-Course Explanations
                st.markdown(f"**Course Explanations ({len(sem_explanation.courses)} courses)**")
                
                for course_exp in sem_explanation.courses:
                    # Course header
                    st.markdown(f"**{course_exp.code}: {course_exp.name}**")
                    
                    # Create tabs for different explanation aspects
                    exp_tab1, exp_tab2, exp_tab3, exp_tab4, exp_tab5 = st.tabs([
                        "📌 Why Selected",
                        "📅 Why This Semester",
                        "🔗 Prerequisites",
                        "💡 Interest Alignment",
                        "🎯 Strategic Value"
                    ])
                    
                    with exp_tab1:
                        st.markdown("**Why this course was chosen for you:**")
                        st.write(course_exp.why_selected)
                    
                    with exp_tab2:
                        st.markdown("**Why it was placed in this specific semester:**")
                        st.write(course_exp.why_this_semester)
                    
                    with exp_tab3:
                        st.markdown("**Prerequisites and readiness:**")
                        st.write(course_exp.prerequisites_context)
                    
                    with exp_tab4:
                        st.markdown("**How this course aligns with your interests:**")
                        st.write(course_exp.interest_alignment)
                    
                    with exp_tab5:
                        st.markdown("**Strategic importance for your degree:**")
                        st.write(course_exp.strategic_value)
                    
                    st.markdown("---")
        
        # Export explanations
        st.markdown("#### 💾 Export Explanation")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Export as JSON
            explanation_dict = {
                "plan_type": selected_plan_type,
                "config": config,
                "overall_plan_summary": explanation.overall_plan_summary,
                "graduation_path": explanation.graduation_path,
                "semesters": [
                    {
                        "semester": sem.semester,
                        "overall_strategy": sem.overall_strategy,
                        "workload_reasoning": sem.workload_reasoning,
                        "courses": [
                            {
                                "code": c.code,
                                "name": c.name,
                                "semester": c.semester,
                                "why_selected": c.why_selected,
                                "why_this_semester": c.why_this_semester,
                                "prerequisites_context": c.prerequisites_context,
                                "interest_alignment": c.interest_alignment,
                                "strategic_value": c.strategic_value
                            }
                            for c in sem.courses
                        ]
                    }
                    for sem in explanation.semesters
                ]
            }
            
            explanation_json = json.dumps(explanation_dict, indent=2)
            st.download_button(
                label="📄 Download Explanation (JSON)",
                data=explanation_json,
                file_name=f"plan_explanation_{selected_plan_type}_{student.student_id}.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col2:
            # Export as readable text
            text_explanation = f"""
COURSE PLAN EXPLANATION
Student: {student.name} ({student.student_id})
Plan Type: {config['name']}
Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}

{'='*80}
OVERALL PLAN SUMMARY
{'='*80}
{explanation.overall_plan_summary}

{'='*80}
GRADUATION PATH
{'='*80}
{explanation.graduation_path}

{'='*80}
SEMESTER-BY-SEMESTER BREAKDOWN
{'='*80}
"""
            
            for sem_exp in explanation.semesters:
                text_explanation += f"""
{'-'*80}
SEMESTER {sem_exp.semester}
{'-'*80}

STRATEGY: {sem_exp.overall_strategy}

WORKLOAD: {sem_exp.workload_reasoning}

COURSES:
"""
                for course_exp in sem_exp.courses:
                    text_explanation += f"""
  [{course_exp.code}] {course_exp.name}
  
  WHY SELECTED:
  {course_exp.why_selected}
  
  WHY THIS SEMESTER:
  {course_exp.why_this_semester}
  
  PREREQUISITES:
  {course_exp.prerequisites_context}
  
  INTEREST ALIGNMENT:
  {course_exp.interest_alignment}
  
  STRATEGIC VALUE:
  {course_exp.strategic_value}
  
  {'-'*40}
"""
            
            st.download_button(
                label="📝 Download Explanation (Text)",
                data=text_explanation,
                file_name=f"plan_explanation_{selected_plan_type}_{student.student_id}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    else:
        st.warning("""
        ⚠️ **Plan explanations not available**
        
        Explanations are generated when you create a course plan. 
        Go to the **Generate Plans** tab to create your personalized course schedules.
        
        Note: Explanation generation requires the LLM to analyze the entire plan, 
        which happens automatically after plan generation completes.
        """)
    
    st.markdown("---")
    
    # Download options
    st.markdown("#### 💾 Export Plan Data")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export as JSON
        export_data = {
            'plan_type': selected_plan_type,
            'config': config,
            'plan': plan,
            'student_id': student.student_id,
            'student_name': student.name,
            'generated_at': pd.Timestamp.now().isoformat()
        }
        plan_json = json.dumps(export_data, indent=2)
        st.download_button(
            label="📄 Download as JSON",
            data=plan_json,
            file_name=f"course_plan_{selected_plan_type}_{student.student_id}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        # Export as CSV
        csv_data = []
        for sem, courses in plan.items():
            for course_code in courses:
                course_info = loader.get_course_by_code(course_code)
                if course_info:
                    csv_data.append({
                        'Semester': sem,
                        'Course Code': course_code,
                        'Course Name': course_info['course_name'],
                        'Credits': loader.get_credits(course_code),
                        'Type': course_info['course_type'],
                        'Mandatory': 'Yes' if course_info.get('is_mandatory', False) else 'No'
                    })
        
        df_csv = pd.DataFrame(csv_data)
        csv = df_csv.to_csv(index=False)
        st.download_button(
            label="📊 Download as CSV",
            data=csv,
            file_name=f"course_plan_{selected_plan_type}_{student.student_id}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col3:
        # Print view
        if st.button("🖨️ Print View", use_container_width=True):
            st.info("Use your browser's print function (Ctrl+P / Cmd+P) to print this page.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🎓 AI Course Planner v2.0 | Powered by Google OR-Tools & GPT-4</p>
    <p>Built with ❤️ using Streamlit</p>
</div>
""", unsafe_allow_html=True)
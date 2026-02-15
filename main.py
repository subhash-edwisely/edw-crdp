from data.data_loader import DataLoader
from cpsat import CoursePlanner

loader = DataLoader()
loader.load_course_data()
student = loader.load_student('21BCE0134')

planner = CoursePlanner(loader, 'gpt-4.1-mini')
complete_plan = planner.generate_complete_plan(student)
    

import random
import statistics
from collections import defaultdict
from django.db.models import Count
from django.utils import timezone
from .models import Student, Course, Lab, Assignment, TeachingPreference, SpecialRequest, AllocationWeights

def allocation_algorithm(clear_existing=False):
    """
    Main allocation algorithm function
    
    Parameters:
    - clear_existing: Boolean to determine if existing assignments should be cleared
    
    Returns:
    - Dictionary with statistics and allocation results
    - Raises ValueError with error message if no eligible students
    """
    # Start with getting allocation weights
    weights = AllocationWeights.get_weights()
    
    # Clear existing assignments if requested
    if clear_existing:
        Assignment.objects.all().delete()
        Lab.objects.all().update(assigned=False)
    
    # Group ALL labs by course+group
    all_labs = Lab.objects.all()
    lab_groups = group_labs_by_course_and_group(all_labs)
    
    # Get all students eligible for allocation (gs_duty=True)
    eligible_students = list(Student.objects.filter(gs_duty=True))
    
    # If no eligible students, raise error
    if not eligible_students:
        raise ValueError("No eligible students for allocation (all have gs_duty=False)")
    
    # Initialize student assignments and load tracking
    student_assignments = {}
    students_with_capacity = []
    
    for student in eligible_students:
        # Initialize student entry
        student_assignments[student] = {
            'assigned_groups': [],
            'current_load': 0
        }
        
        # Get existing assignments for this student
        existing_assignments = Assignment.objects.filter(student=student).select_related('course_lab')
        
        # Map existing assignments to lab_groups
        for assignment in existing_assignments:
            lab = assignment.course_lab
            group_key = (lab.code, lab.group)
            
            # Find and remove from lab_groups if present
            if group_key in lab_groups:
                student_assignments[student]['assigned_groups'].append(lab_groups[group_key])
                student_assignments[student]['current_load'] += 1
                del lab_groups[group_key]
        
        # Check if student still has capacity
        if student_assignments[student]['current_load'] < student.lab_load:
            students_with_capacity.append(student)
        else:
            del student_assignments[student]
    
    # If no students with capacity, raise error
    if not students_with_capacity:
        raise ValueError("No students with remaining lab load capacity")
    
    # Sort students by priority (availability constraints, then higher remaining lab_load)
    students_with_capacity.sort(key=lambda s: (
        -1 if SpecialRequest.objects.filter(student=s, availability_approved=True).exists() else 0,
        -(s.lab_load - student_assignments[s]['current_load'])  # Higher remaining capacity first
    ))
    
    # Initialize best solution
    best_solution = {
        'assignments': [],
        'penalty_score': float('inf')
    }
    
    # Convert student_assignments to the format expected by other functions
    base_student_assignments = {
        student: data['assigned_groups'] 
        for student, data in student_assignments.items()
    }
    
    # Run permutations
    for _ in range(weights.permutation_count):
        # Create working copies for this permutation
        working_lab_groups = lab_groups.copy()
        current_assignments = defaultdict(list)
        
        # Start with existing assignments
        for student, assigned in base_student_assignments.items():
            current_assignments[student].extend(assigned)
        
        # First, handle course lock requests
        handle_course_lock_requests(working_lab_groups, current_assignments, students_with_capacity)
        
        # Then do greedy allocation for remaining labs
        greedy_allocation(working_lab_groups, current_assignments, students_with_capacity)
        
        # Flatten assignments for calculating penalty
        flat_assignments = []
        for student, assigned_labs in current_assignments.items():
            for lab_group in assigned_labs:
                for lab in lab_group:
                    flat_assignments.append((student, lab))
        
        # Calculate penalty score
        penalty_score = calculate_penalty_score(flat_assignments, current_assignments, students_with_capacity, weights)
        
        # Update best solution if current solution is better
        if penalty_score < best_solution['penalty_score']:
            best_solution = {
                'assignments': flat_assignments,
                'penalty_score': penalty_score
            }
        
        # Shuffle labs for next iteration
        keys = list(lab_groups.keys())
        random.shuffle(keys)
        lab_groups = {key: lab_groups[key] for key in keys}
    
    # Save best solution to database (only new assignments)
    existing_assignment_ids = set(Assignment.objects.values_list('id', flat=True))
    new_assignments = [
        (student, lab) for student, lab in best_solution['assignments']
        if not Assignment.objects.filter(student=student, course_lab=lab).exists()
    ]
    save_assignments(new_assignments)
    
    # Calculate statistics
    stats = calculate_statistics()
    stats['penalty_score'] = round(best_solution['penalty_score'], 1)
    
    return stats

def group_labs_by_course_and_group(labs):
    """Group labs by course+group to ensure all sessions of the same lab are assigned together"""
    lab_groups = defaultdict(list)
    for lab in labs:
        key = (lab.code, lab.group)
        lab_groups[key].append(lab)
    return lab_groups

def handle_course_lock_requests(available_labs, student_assignments, students):
    """Handle students with course lock requests first"""
    course_locks = SpecialRequest.objects.filter(course_lock_approved=True)
    
    for lock in course_locks:
        student = lock.student
        if student not in students:
            continue
        
        course = lock.course_lock
        labs_to_assign = lock.lab_groups_locked
        
        # Get all labs for this course
        course_labs = [(key, labs) for key, labs in available_labs.items() if key[0] == course]
        
        # First, try to assign odd/even week pairs
        odd_even_pairs = find_odd_even_pairs(course_labs)
        
        for pair in odd_even_pairs:
            if labs_to_assign <= 1:
                break
                
            # Check if this assignment would violate constraints
            if not violates_constraints(student, pair[0][1], student_assignments):
                student_assignments[student].append(pair[0][1])
                del available_labs[pair[0][0]]
                
                if not violates_constraints(student, pair[1][1], student_assignments):
                    student_assignments[student].append(pair[1][1])
                    del available_labs[pair[1][0]]
                    labs_to_assign -= 2
                else:
                    # If we can't assign the second lab in the pair, put the first one back
                    available_labs[pair[0][0]] = student_assignments[student].pop()
        
        # Then, try to assign remaining labs
        if labs_to_assign > 0:
            for key, labs in list(course_labs):
                if key in available_labs:
                    if not violates_constraints(student, labs, student_assignments):
                        student_assignments[student].append(labs)
                        del available_labs[key]
                        labs_to_assign -= 1

def greedy_allocation(available_labs, student_assignments, students):
    """Greedy allocation algorithm for remaining labs"""
    for student in students:
        if student_at_max_load(student, student_assignments):
            continue
        
        # Track which courses the student has already been assigned
        assigned_courses = set(lab.code for lab_group in student_assignments[student] for lab in lab_group)
        
        # First, try to assign labs from courses the student is already teaching
        for course in assigned_courses:
            if student_at_max_load(student, student_assignments):
                break
                
            # Try to assign odd/even week pairs first
            course_labs = [(key, labs) for key, labs in available_labs.items() if key[0] == course]
            odd_even_pairs = find_odd_even_pairs(course_labs)
            
            for pair in odd_even_pairs:
                if (student.lab_load - len(student_assignments[student])) <= 1 : # Cannot assign pairs if left only 1 more lab_load to fulfil
                    break
                    
                if not violates_constraints(student, pair[0][1], student_assignments):
                    student_assignments[student].append(pair[0][1])
                    del available_labs[pair[0][0]]
                    
                    if not violates_constraints(student, pair[1][1], student_assignments):
                        student_assignments[student].append(pair[1][1])
                        del available_labs[pair[1][0]]
                    else:
                        # If we can't assign the second lab in the pair, put the first one back
                        available_labs[pair[0][0]] = student_assignments[student].pop()
            
            # Then assign remaining labs from this course
            for key, labs in list(course_labs):
                if key in available_labs and not student_at_max_load(student, student_assignments):
                    if not violates_constraints(student, labs, student_assignments):
                        student_assignments[student].append(labs)
                        del available_labs[key]
        
        # Then, try to assign labs based on preferences
        for ranking in range(1, 9):  # Preference rankings 1-8
            if student_at_max_load(student, student_assignments):
                break
                
            # Get all preferences with this ranking
            current_prefs = TeachingPreference.objects.filter(student=student, ranking=ranking)
            
            # If we have multiple courses at the same ranking, prioritize past assignments
            if len(current_prefs) > 1:
                # Sort preferences by whether the course is in past_assignments
                current_prefs = sorted(current_prefs, 
                                    key=lambda p: p.course in student.past_assignments.all(), 
                                    reverse=True)  # True values first
            
            for pref in current_prefs:
                if student_at_max_load(student, student_assignments):
                    break
                    
                course = pref.course
                
                # Try to assign odd/even week pairs first
                course_labs = [(key, labs) for key, labs in available_labs.items() if key[0] == course]
                odd_even_pairs = find_odd_even_pairs(course_labs)
                
                for pair in odd_even_pairs:
                    if (student.lab_load - len(student_assignments[student])) <= 1:
                        break
                        
                    if not violates_constraints(student, pair[0][1], student_assignments):
                        student_assignments[student].append(pair[0][1])
                        del available_labs[pair[0][0]]
                        
                        if not violates_constraints(student, pair[1][1], student_assignments):
                            student_assignments[student].append(pair[1][1])
                            del available_labs[pair[1][0]]
                        else:
                            # If we can't assign the second lab in the pair, put the first one back
                            available_labs[pair[0][0]] = student_assignments[student].pop()
                
                # Then assign remaining labs from this course
                for key, labs in list(course_labs):
                    if key in available_labs and not student_at_max_load(student, student_assignments):
                        if not violates_constraints(student, labs, student_assignments):
                            student_assignments[student].append(labs)
                            del available_labs[key]
        
        # Finally, try to assign any remaining labs
        if not student_at_max_load(student, student_assignments):
            for key, labs in list(available_labs.items()):
                if not violates_constraints(student, labs, student_assignments):
                    student_assignments[student].append(labs)
                    del available_labs[key]

def find_odd_even_pairs(course_labs):
    """Find odd/even week pairs among lab groups"""
    pairs = []
    odd_labs = []
    even_labs = []
    
    # Group labs by odd/even weeks
    for key, labs in course_labs:
        # Skip if labs is empty
        if not labs:
            continue
            
        # Get the teaching weeks for the first lab in the group
        teaching_weeks = labs[0].teaching_week
        
        # Check if all weeks are odd or all are even
        if all(week % 2 == 1 for week in teaching_weeks): # if all odd
            odd_labs.append((key, labs))
        elif all(week % 2 == 0 for week in teaching_weeks): # if all even
            even_labs.append((key, labs))
    
    # Find potential pairs based on day and time
    for odd_key, odd_lab_group in odd_labs:
        for even_key, even_lab_group in even_labs:
            # Check if they have the same day and time
            if (odd_lab_group[0].day == even_lab_group[0].day and 
                odd_lab_group[0].time == even_lab_group[0].time):
                pairs.append(((odd_key, odd_lab_group), (even_key, even_lab_group)))
                break
    
    return pairs

def student_at_max_load(student, student_assignments):
    """Check if a student has reached their maximum lab load"""
    return len(student_assignments[student]) >= student.lab_load



def violates_constraints(student, labs, student_assignments):
    """Check if assigning these labs would violate any constraints"""
    # Check if the student has any special requests
    try:
        special_request = SpecialRequest.objects.get(student=student, availability_approved=True)
        has_special_request = True
    except SpecialRequest.DoesNotExist:
        has_special_request = False
    
    # If assigning this lab would exceed the student's lab_load
    if len(student_assignments[student]) + len(labs) > student.lab_load:
        return True
    
    # Check for time clashes
    for lab in labs:
        lab_start, lab_end = parse_time(lab.time)
        
        for assigned_lab_group in student_assignments[student]:
            for assigned_lab in assigned_lab_group:
                # Check if same day
                if lab.day == assigned_lab.day:
                    # Parse assigned lab times
                    assigned_start, assigned_end = parse_time(assigned_lab.time)
                    
                    # Check if time periods overlap
                    # This is true if either lab starts during the other lab
                    # or if one lab completely contains the other
                    if (lab_start < assigned_end and lab_end > assigned_start):
                        # Check if teaching weeks overlap
                        if any(week in assigned_lab.teaching_week for week in lab.teaching_week):
                            return True
    
    # Check for max teaching days constraint
    if has_special_request:
        current_days = set(assigned_lab.day for assigned_lab_group in student_assignments[student] for assigned_lab in assigned_lab_group)
        # Use the first lab in the list, same pattern as your for loop
        first_lab = next(iter(labs), None)  # Safely get the first item or None
        if first_lab and first_lab.day not in current_days and len(current_days) >= special_request.max_teaching_days:
            return True
        
    # Check for unavailable slots
    if has_special_request and special_request.unavailable_slots:
        # Again, use the first lab in the list
        first_lab = next(iter(labs), None)
        if first_lab:  # Check if we have a lab
            lab_start, _ = parse_time(first_lab.time)
            
            for unavailable_slot in special_request.unavailable_slots:
                day, time_slot = unavailable_slot.split('-')
                
                if first_lab.day == day:
                    if time_slot == "AM" and lab_start[0] < 12:
                        return True
                    elif time_slot == "PM" and lab_start[0] >= 12:
                        return True
    
    return False

def calculate_penalty_score(assignments, student_assignments, students, weights):
    """Calculate the penalty score for the current allocation"""
    penalty = 0
    
    # Penalty for odd/even week pairs assigned to different students
    odd_even_pair_penalty = calculate_odd_even_pair_penalty(assignments)
    penalty += odd_even_pair_penalty * weights.odd_even_pair_weight
    
    # Penalty for course variety
    course_variety_penalty = calculate_course_variety_penalty(student_assignments)
    penalty += course_variety_penalty * weights.course_variety_weight
    
    # Penalty for preference ranking
    preference_penalty = calculate_preference_penalty(student_assignments)
    penalty += preference_penalty * weights.preference_weight
    
    # Penalty for workload distribution
    workload_penalty = calculate_workload_penalty(student_assignments, students)
    penalty += workload_penalty * weights.workload_distribution_weight

    # Bonus for utilizing past assignments (subtract from penalty)
    past_assignments_bonus = calculate_past_assignments_bonus(student_assignments)
    penalty -= past_assignments_bonus * weights.past_assignments_weight
    
    return penalty

def calculate_odd_even_pair_penalty(assignments):
    """Calculate penalty for odd/even week pairs assigned to different students"""
    penalty = 0
    lab_assignments = defaultdict(dict)
    
    # Group assignments by day and time
    for student, lab in assignments:
        key = (lab.day, lab.time)
        lab_key = (lab.code, lab.group)
        lab_assignments[key][lab_key] = student
    
    # Check for odd/even week pairs assigned to different students
    for (day, time), labs in lab_assignments.items():
        for lab1_key, student1 in labs.items():
            for lab2_key, student2 in labs.items():
                if lab1_key != lab2_key and student1 != student2:
                    # Check if they form an odd/even pair
                    lab1 = Lab.objects.filter(code=lab1_key[0], group=lab1_key[1], day=day, time=time).first()
                    lab2 = Lab.objects.filter(code=lab2_key[0], group=lab2_key[1], day=day, time=time).first()
                    
                    if lab1 and lab2:
                        # Check if one is all odd and one is all even
                        weeks1 = lab1.teaching_week
                        weeks2 = lab2.teaching_week
                        
                        if (all(week % 2 == 1 for week in weeks1) and all(week % 2 == 0 for week in weeks2)) or \
                           (all(week % 2 == 0 for week in weeks1) and all(week % 2 == 1 for week in weeks2)):
                            penalty += 1
    
    return penalty

def calculate_course_variety_penalty(student_assignments):
    """Calculate penalty for course variety"""
    penalty = 0
    
    for student, assignments in student_assignments.items():
        if not assignments:
            continue
        
        # Count number of unique courses
        unique_courses = set(lab.code for lab_group in assignments for lab in lab_group)
        
        # Add penalty for each additional course beyond the first one
        penalty += len(unique_courses) - 1
    
    return penalty

def calculate_preference_penalty(student_assignments):
    """Calculate penalty for preference ranking"""
    penalty = 0
    
    for student, assignments in student_assignments.items():
        if not assignments:
            continue
        
        # Get student's preferences
        preferences = {pref.course: pref.ranking for pref in TeachingPreference.objects.filter(student=student)}
        
        # Count unique courses
        unique_courses = set(lab.code for lab_group in assignments for lab in lab_group)
        
        # Calculate penalty based on preference ranking
        for course in unique_courses:
            if course in preferences:
                # Penalty is based on ranking (1 is best, 8 is worst)
                penalty += preferences[course] - 1
            else:
                # Double penalty for courses not in preferences
                penalty += 16  # 2 * (8 - 0)
    
    return penalty

def calculate_workload_penalty(student_assignments, students):
    """Calculate penalty for workload distribution"""
    workload_ratios = []
    
    for student in students:   
        # Calculate total workload
        total_workload = 0
        for lab_group in student_assignments[student]:
            for lab in lab_group:
                course = lab.code
                total_workload += course.hours * course.weeks
        
        # Calculate ratio of workload to lab_load
        ratio = total_workload / student.lab_load
        workload_ratios.append(ratio)
    
    # Calculate standard deviation of workload ratios
    if workload_ratios:
        return statistics.stdev(workload_ratios) if len(workload_ratios) > 1 else 0
    else:
        return 0

def calculate_past_assignments_bonus(student_assignments):
    """Calculate bonus (negative penalty) for utilizing past teaching experience"""
    bonus = 0
    
    for student, assignments in student_assignments.items():
        if not assignments:
            continue
        
        # Get student's past assignments
        past_courses = set(course.code for course in student.past_assignments.all())
        
        # Count unique courses in current assignment
        current_courses = set(lab.code.code for lab_group in assignments for lab in lab_group)
        
        # Calculate number of past courses that were assigned
        matched_courses = past_courses.intersection(current_courses)
        
        # Add bonus for each matched course (negative penalty)
        bonus += len(matched_courses)
    
    return bonus

def save_assignments(assignments):
    """Save the best solution to the database"""
    # Create Assignment objects
    for student, lab in assignments:
        Assignment.objects.create(
            course_lab=lab,
            student=student,
            created_at=timezone.now()
        )
        
        # Update Lab.assigned
        lab.assigned = True
        lab.save()

def calculate_statistics():
    """Calculate statistics for the allocation dashboard"""
    stats = {}
    
    # Total number of students who have met their lab load
    total_students = Student.objects.filter(gs_duty=True).count()
    students_with_assignments = Assignment.objects.values('student').annotate(
        count=Count('student')
    ).filter(count__gt=0).count()
    
    stats['students_assigned'] = students_with_assignments
    stats['total_students'] = total_students
    
    # Number of courses
    stats['total_courses'] = Course.objects.count()
    
    # Number of labs and percentage assigned
    total_labs = Lab.objects.values('code', 'group').distinct().count()
    assigned_labs = Lab.objects.filter(assigned=True).values('code', 'group').distinct().count()
    
    stats['total_labs'] = total_labs
    stats['assigned_labs'] = assigned_labs
    stats['assignment_percentage'] = round((assigned_labs / total_labs * 100), 1) if total_labs > 0 else 0
    
    return stats

def validate_group_assignment(student, labs):
    """Validate an assignment for a group of labs"""
    if not labs:
        return False, "No labs provided"
    
    # Check if the student is already at max load
    # Exclude any labs from this group that may already be assigned to the student
    lab_ids = [lab.id for lab in labs]
    current_assignments = Assignment.objects.filter(student=student).exclude(course_lab_id__in=lab_ids)
    
    # If we're assigning a new group, add 1 to the count
    if current_assignments.count() >= student.lab_load:
        return False, "Student is already at maximum lab load"
    
    # Check for time clashes with other assignments
    for lab in labs:
        lab_day = lab.day
        lab_start, lab_end = parse_time(lab.time)
        
        for assignment in current_assignments:
            assigned_lab = assignment.course_lab
            
            # Check if same day
            if assigned_lab.day == lab_day:
                # Parse time strings
                assigned_start, assigned_end = parse_time(assigned_lab.time)
                
                # Check if time periods overlap
                if (lab_start < assigned_end and lab_end > assigned_start):
                    # Check if teaching weeks overlap
                    if any(week in assigned_lab.teaching_week for week in lab.teaching_week):
                        weeks_str = ', '.join(map(str, assigned_lab.teaching_week))
                        return False, (
                            f"Time clash with existing assignment on {lab_day} {assigned_lab.time} "
                            f"(Teaching Wk: {weeks_str})"
                        )
    
    # Check for special request constraints
    try:
        special_request = SpecialRequest.objects.get(student=student, availability_approved=True)
        
        # Get current teaching days (excluding this group)
        current_days = set(assignment.course_lab.day for assignment in current_assignments)
        
        # Get the unique days in the new lab group
        new_days = set(lab.day for lab in labs)
        
        # Check for any new teaching days that would exceed the limit
        new_teaching_days = [day for day in new_days if day not in current_days]
        if new_teaching_days and len(current_days) + len(new_teaching_days) > special_request.max_teaching_days:
            return False, f"Exceeds maximum teaching days ({special_request.max_teaching_days})"
        
        # Check for unavailable slots
        if special_request.unavailable_slots:
            for lab in labs:
                lab_start, _ = parse_time(lab.time)
                time_slot = "AM" if lab_start[0] < 12 else "PM"
                slot = f"{lab.day}-{time_slot}"
                
                if slot in special_request.unavailable_slots:
                    return False, f"Assigned during unavailable time slot ({slot})"
            
    except SpecialRequest.DoesNotExist:
        pass
    
    return True, "Allocation is valid"

def parse_time(time_str):
    """Parse a time string in format 'hhmm-hhmm' to start and end times (hours and minutes)"""
    start_str, end_str = time_str.split('-')
    
    start_hour = int(start_str[:2])
    start_minute = int(start_str[2:])
    
    end_hour = int(end_str[:2])
    end_minute = int(end_str[2:])
    
    # Return as tuples of (hour, minute) for easier comparison
    return (start_hour, start_minute), (end_hour, end_minute)
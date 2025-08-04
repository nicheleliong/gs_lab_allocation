from django.contrib.auth.models import Group
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.core.mail import send_mail, EmailMessage
from collections import defaultdict
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from django.http import HttpResponse
from .forms import *
from .models import Student, Course, SpecialRequest, TeachingPreference, Lab, Assignment, AllocationWeights
from .allocation_algorithm import (
    allocation_algorithm, 
    validate_group_assignment,
    calculate_penalty_score
    )
import random, string, pandas as pd, re, csv, io


# Authorisation functions
def is_admin(user):
    return user.groups.filter(name='Admin').exists()

def is_student(user):
    return user.groups.filter(name='Student').exists()

def role_restricted(role_check):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if role_check(request.user):
                return view_func(request, *args, **kwargs)
            return redirect('unauthorized')  # Redirect to a custom error page
        return wrapper
    return decorator

# Helper functions
def generate_random_password(length=8):
    """Generate a random password of the given length."""
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choice(characters) for i in range(length))
    return password

def parse_teaching_weeks(remark):
    # Default weeks 1 to 13 if remark is empty or None
    if not remark or not isinstance(remark, str) or remark.strip() == "":
        return list(range(1, 14))  

    # Make remark lowercase for easier parsing
    remark = remark.lower()

    # Try to find patterns like wk2-13, teaching wk2-13, 2-13, etc.
    teaching_week_pattern = r'(?:teaching\s*)?wk?([\d,-]+)'
    match = re.search(teaching_week_pattern, remark)

    # If no pattern matched, return default weeks
    if not match:
        return list(range(1, 14))  

    weeks_str = match.group(1)
    weeks = set()

    # Split by comma to handle lists like "1,3,5"
    for part in weeks_str.split(','):
        part = part.strip()
        if '-' in part:
            # Handle ranges like "2-13"
            start, end = map(int, part.split('-'))
            weeks.update(range(start, end + 1))
        else:
            # Handle individual weeks like "1"
            weeks.add(int(part))

    return sorted(weeks)


# Custom Error Page
def unauthorized(request):
    return render(request, 'unauthorized.html')

# home view
def home(request):
    # Handle login POST request
    if request.method == 'POST' and 'username' in request.POST:
        username = request.POST['username']
        password = request.POST['password']
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "You Have Been Logged In!")
            return redirect('home')
        else:
            messages.error(request, "There Was An Error Logging In.")
            return redirect('home')
    
    # If user is logged in, show dashboard
    if request.user.is_authenticated:
        context = {}
        try:
            if request.user.is_staff or request.user.is_superuser:  # Admin
                context['steps'] = [
                    ("1. Set Up Courses & Labs", "view_courses", 
                     "Add courses and their lab sessions"),
                    ("2. Manage Student Accounts", "view_students", 
                     "Register or delete student accounts"),
                    ("3. Review Special Requests", "view_special_requests", 
                     "Approve/reject student requests"),
                    ("4. Allocate Labs", "allocation_dashboard", 
                     "Allocate labs automatically or manually")
                ]
                context['is_admin'] = True
            else:  # Student
                context['steps'] = [
                    ("1. Complete Your Profile", "profile", 
                     "Change your password and set up your profile"),
                    ("2. Submit Semester Info", "semester_info", 
                     "Declare your desired lab load and other information"),
                    ("3. Indicate Preferences", "teaching_preference", 
                     "Rank your preferred courses to teach"),
                    ("4. Submit Special Requests", "special_request", 
                     "Request specific accommodations if needed"),
                    ("5. View Allocations", "view_allocations", 
                     "Check your assigned labs when available")
                ]
                context['is_admin'] = False
        except Exception as e:
            messages.error(request, f"Error loading dashboard: {str(e)}")
        
        return render(request, 'home.html', context)
    
    # If not logged in, show login page
    return render(request, 'home.html')

def logout_user(request):
    logout(request)
    messages.success(request, "You Have Been Logged Out.")
    return redirect('home')

def logout_user(request):
    logout(request)
    messages.success(request, "You Have Been Logged Out.")
    return redirect('home')

@login_required
@role_restricted(is_admin)
def view_students(request):
    students = Student.objects.all()
    
    return render(request, 'admin/view_students.html',{'students':students})

def delete_student(request, pk):
    if request.user.is_authenticated:
        delete_it = Student.objects.get(user_id=pk)
        delete_it.delete()
        messages.success(request, "Student Record deleted successfully.")
        return redirect('view_students')
    else:
        messages.success(request, "You must be logged in to do that.")
        return redirect('view_students')

    
def register_student(request):
    #when user has clicked "Submit"
    if request.method == 'POST':
        form = AdminRegisterStudentForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # user random-generated password
            password = generate_random_password() 
            user.set_password(password)
            user.save() # save to database

            # Assign user to "Student" group
            student_group, created = Group.objects.get_or_create(name="Student")  # Ensures group exists
            user.groups.add(student_group)  # Add user to group

            # Create the Student instance with default values for non-mandatory fields
            student = Student.objects.create(
                user = user,
                name = user.get_full_name(),
                email = user.email,
                supervisor = "Not Set",
                bachelor_degree = "Not Set",
                matriculation_date = "Not Set",
            )

            # Send email to student
            subject = 'Account Created on Teaching Allocation Portal'
            message = f"""Dear {user.first_name} {user.last_name},

An account has been created for you on the Teaching Allocation Portal. 
Please use the link below to complete setting up your account:
http://127.0.0.1:8000/

Your username is: {user.username}
Your autogenerated password is: {password}
Please log in to change your password and complete your profile information within the next 14 days.

Best regards,
Teaching Allocation Portal Team
"""
            from_email = 'gsallocationfyp@gmail.com'  # Replace with your actual email
            send_mail(subject, message, from_email, [user.email])

            if user:
                messages.success(request, """Student successfully registered. 
                An email has been sent out to the student to notify them to setup their account.""")
            return redirect('home')
    else:
        form = AdminRegisterStudentForm()   
    return render(request, 'admin/register_student.html', {'form':form})

@login_required
@role_restricted(is_student)
def profile(request):
    """Displays the profile with an edit button."""
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        messages.error(request, "Student record not found.")
        return redirect("home")

    return render(request, "student/profile.html", {"student": student})

@login_required
@role_restricted(is_student)
def edit_profile(request):
    student = Student.objects.get(user=request.user)

    # Replace "Not Set" with empty string for form initialization
    if student.supervisor == "Not Set":
        student.supervisor = ""
    if student.bachelor_degree == "Not Set":
        student.bachelor_degree = ""
    if student.matriculation_date == "Not Set":
        student.matriculation_date = ""

    password_form = PasswordChangeForm(request.user)
    profile_form = StudentProfileForm(instance=student)
    user_form = UserProfileForm(instance=request.user)
    
    if request.method == "POST":
        if "change_password" in request.POST:
             password_form = PasswordChangeForm(request.user, request.POST)
             if password_form.is_valid():
                 user = password_form.save()
                 update_session_auth_hash(request, user)
                 messages.success(request, "Your password was updated successfully!")
                 return redirect("edit_profile")
        elif "update_profile" in request.POST:
            profile_form = StudentProfileForm(request.POST, instance=student)
            user_form = UserProfileForm(request.POST, instance=request.user)

            # Validate both forms
            if user_form.is_valid() and profile_form.is_valid():
                user = user_form.save()
                student = profile_form.save(commit=False)
                student.name = user.get_full_name()  # Update the name from User model
                student.save()
                messages.success(request, "Profile updated successfully!")
                return redirect("edit_profile")
    else:
        # Initial form load
        profile_form = StudentProfileForm(instance=student)
        user_form = UserProfileForm(instance=request.user)

    return render(request, "student/edit_profile.html", {
        "password_form": password_form,
        "profile_form": profile_form,
        "user_form": user_form,
    })

@login_required
@role_restricted(is_admin)
def view_courses(request):
    courses = Course.objects.all()

    return render(request, 'admin/view_courses.html', {'courses': courses})

@login_required
@role_restricted(is_admin)
def add_course(request):
    if request.method == "POST":
        form = AddCourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "New course has been added successfully.")
            return redirect('view_courses')  # Redirect to the course list page
    else:
        form = AddCourseForm()

    return render(request, 'admin/add_course.html', {'form': form})

@login_required
@role_restricted(is_admin)
def course(request, new_code):
    if request.user.is_authenticated:
        #look up records
        course = Course.objects.get(new_code=new_code)
        # Filter groups where course_id matches course.code
        labs = Lab.objects.filter(code=course.code)
        return render(request, 'admin/course.html', {'course': course, 'labs': labs})
    else:
        messages.success(request, "You must be logged in to view that page.")
        return redirect('home')

@login_required
@role_restricted(is_admin)
def delete_course(request, new_code):
    if request.user.is_authenticated:
        delete_it = Course.objects.get(new_code=new_code)
        delete_it.delete()
        messages.success(request, f"Course {new_code} deleted successfully.")
        return redirect('view_courses')
    else:
        messages.success(request, "You must be logged in to do that.")
        return redirect('home')

@login_required
@role_restricted(is_admin)
def edit_course(request, new_code):
    if not request.user.is_authenticated:
        messages.success(request, "You must be logged in.")
        return redirect('home')
    
    current_course = Course.objects.get(new_code=new_code)
    lab_qs = Lab.objects.filter(code=current_course)
    
    if request.method == 'POST':
        form = AddCourseForm(request.POST, instance=current_course)
        lab_formset = LabFormSet(request.POST, queryset=lab_qs)
        
        # Check if both form and formset are valid
        if form.is_valid() and lab_formset.is_valid():
            form.save()
            lab_formset.save()

            # Get the manual override if provided
            manual_grp_count = form.cleaned_data.get('manual_grp_count')

            if manual_grp_count is not None:
                # Use the manual override
                current_course.grp_count = manual_grp_count
            else:
                # Auto-calculate from unique lab groups
                unique_groups_count = Lab.objects.filter(code=current_course).values('group').distinct().count()
                current_course.grp_count = unique_groups_count

            current_course.save()

            messages.success(request, "Course and lab details have been updated.")
            return redirect('view_courses')
        else:
            # One or both forms have errors
            if not form.is_valid():
                messages.error(request, f"Course form errors: {form.errors}")
    
            if not lab_formset.is_valid():
                for i, form_errors in enumerate(lab_formset.errors):
                    if form_errors:
                        messages.error(request, f"Lab {i+1} errors: {form_errors}")
    else:
        form = AddCourseForm(instance=current_course)
        lab_formset = LabFormSet(queryset=lab_qs)
    
    context = {
        'form': form,
        'lab_formset': lab_formset,
        'current_course': current_course,
    }
    
    return render(request, 'admin/edit_course.html', context)

@login_required
@role_restricted(is_student)
def semester_info(request):
    student = Student.objects.get(user=request.user)
    courses = Course.objects.all() 

    if request.method == "POST":
        form = SemesterInformationForm(request.POST, instance=student)
        if form.is_valid():
            gs_duty = form.cleaned_data['gs_duty'] == 'True'
            if not gs_duty:
                student.lab_load = 0

            form.save()

            # Handle selected past assignments (ManyToMany)
            selected_courses = request.POST.getlist('previous_courses')  # List of course IDs as strings
            student.past_assignments.set(selected_courses)  # Assign many-to-many relationships

            messages.success(request, "Semester Information has been saved.")

            if not gs_duty:
                return redirect('home')  # If GS Duty False, exit process
            return redirect('teaching_preference')  # Proceed to teaching preference
    else:
        form = SemesterInformationForm(instance=student)

    return render(request, 'student/semester_info.html', {'form': form, 'courses': courses})

@login_required
@role_restricted(is_student)
def special_request(request):
    student = Student.objects.get(user=request.user)
    courses = Course.objects.all()

    am_slots = ["Mon-AM", "Tue-AM", "Wed-AM", "Thu-AM", "Fri-AM"]
    pm_slots = ["Mon-PM", "Tue-PM", "Wed-PM", "Thu-PM", "Fri-PM"]

    # Get existing request, keep only the latest one
    existing_request = SpecialRequest.objects.filter(student=student).first()

    selected_slots = existing_request.unavailable_slots if existing_request else []

    if request.method == 'POST':
        form = SpecialRequestForm(request.POST, instance=existing_request)

        if form.is_valid():
            unavailable_slots = request.POST.getlist('unavailable_slots')
            
            # Create instance but don't save yet
            special_request = form.save(commit=False)
            special_request.student = student
            special_request.unavailable_slots = unavailable_slots  # Assuming ArrayField
            special_request.reviewed_at = None  # Reset review status
            special_request.course_lock_approved = False  # Reset approval flags
            special_request.availability_approved = False

            # Check if course_lock is empty
            if not form.cleaned_data.get('course_lock'):
                special_request.course_lock = None
                special_request.lab_groups_locked = 0
                special_request.faculty_contact = ""

            # Save now
            special_request.save()

            messages.success(request, "Special Requests have been submitted.")
            return redirect('home')

    else:
        form = SpecialRequestForm(instance=existing_request)

    # Set the max attribute to the student's lab_load
    form.fields['lab_groups_locked'].widget.attrs['max'] = student.lab_load
    
    context = {
        'form': form,
        'courses': courses,
        "am_slots": am_slots,
        "pm_slots": pm_slots,
        'selected_slots': selected_slots,
    }
    return render(request, 'student/special_request.html', context)

@login_required
@role_restricted(is_student)
def teaching_preference(request):
    student = Student.objects.get(user=request.user)

    if request.method == 'POST':
        form = TeachingPreferenceForm(request.POST, student=student)
        if form.is_valid():
            preferences = []
            ranking_counts = {}
            year_counts = {1: 0, 2: 0, 3: 0}

            # Collect and validate preferences
            for field_name, value in form.cleaned_data.items():
                if value:  # If the student has ranked this course
                    course = form.fields[field_name].course
                    year = form.fields[field_name].year

                    # Track how many courses picked for each year
                    year_counts[year] += 1

                    # Track how many times each ranking number is used
                    ranking_counts[value] = ranking_counts.get(value, 0) + 1

                    # Prepare TeachingPreference object (without saving yet)
                    preferences.append(TeachingPreference(
                        student=student,
                        course=course,
                        ranking=value,
                        year=course.year  # Copy over year from Course model
                    ))

            # Validation checks
            error = False
            for year, count in year_counts.items():
                if count < 3:
                    messages.error(request, f"You must rank at least 3 courses for Year {year}.")
                    error = True

            for rank, count in ranking_counts.items():
                if count > 2:
                    messages.error(request, f"You cannot assign ranking {rank} to more than 2 courses.")
                    error = True

            if error:
                return render(request, 'student/teaching_preference.html', {'form': form})

            # Delete old preferences and save new ones
            TeachingPreference.objects.filter(student=student).delete()
            TeachingPreference.objects.bulk_create(preferences)
            messages.success(request, "Your preferences have been saved successfully.")
            return redirect('home') 

    else:
        form = TeachingPreferenceForm(student=student)

    return render(request, 'student/teaching_preference.html', {'form': form}) 

@login_required
@role_restricted(is_admin)
def add_labs(request):
    if request.method == "POST":
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            labs = []
            file = request.FILES["file"]
 
            try:
                xlsx = pd.ExcelFile(file)
                processed_courses = set()
                 
                for sheet_name in xlsx.sheet_names:
                    # Attempt to find corresponding Course
                    course = Course.objects.filter(new_code=sheet_name).first()
                    if not course:
                        messages.error(request, f"No matching course found for sheet: {sheet_name}")
                        continue
 
                    df = pd.read_excel(xlsx, sheet_name=sheet_name)
                     
                    # Ensure required columns exist
                    required_columns = {"TYPE", "GROUP", "TIME", "VENUE", "REMARK"}
                    missing_columns = required_columns - set(df.columns)
                    if missing_columns:
                        messages.error(request, f"Missing required columns in sheet: {sheet_name}. Missing columns: {', '.join(missing_columns)}")
                        continue
 
                    # Filter rows where TYPE == "LAB"
                    df_lab = df[df["TYPE"].str.upper() == "LAB"]
                     
                    for _, row in df_lab.iterrows():
                        teaching_weeks = parse_teaching_weeks(row["REMARK"]) if pd.notna(row["REMARK"]) else []
                         
                        labs.append(Lab(
                            code=course,
                            group=row["GROUP"],
                            day=row["DAY"],
                            time=row["TIME"],
                            venue=row["VENUE"],
                            teaching_week=teaching_weeks
                        ))
 
                    processed_courses.add(sheet_name)
 
                # Delete old lab information and save new ones
                for course in Course.objects.filter(new_code__in=xlsx.sheet_names):
                    Lab.objects.filter(code=course).delete()
                Lab.objects.bulk_create(labs)

                # Update Course.grp_count
                for course in Course.objects.filter(new_code__in=processed_courses):
                    unique_groups_count = Lab.objects.filter(code=course).values('group').distinct().count()
                    course.grp_count = unique_groups_count
                    course.save()
                 
                course_list = ', '.join(sorted(processed_courses))
                messages.success(request, f"Successfully inserted {len(labs)} LAB records for {len(processed_courses)} courses: {course_list}")
                return redirect('view_courses')
 
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")
                return redirect("add_labs")
    else:
        form = FileUploadForm()
     
    return render(request, "admin/add_labs.html", {'form': form})

@login_required
@role_restricted(is_admin)
def view_special_requests(request):
    # Get all special requests with student info
    special_requests = SpecialRequest.objects.all().select_related('student', 'course_lock')
    
    context = {
        'special_requests': special_requests,
    }
    return render(request, 'admin/view_special_requests.html', context)

@login_required
@role_restricted(is_admin)
def review_special_request(request, request_id):
    special_request = get_object_or_404(SpecialRequest, id=request_id)
    student = special_request.student
    
    am_slots = ["Mon-AM", "Tue-AM", "Wed-AM", "Thu-AM", "Fri-AM"]
    pm_slots = ["Mon-PM", "Tue-PM", "Wed-PM", "Thu-PM", "Fri-PM"]
    
    if request.method == 'POST':
        form = AdminSpecialRequestForm(request.POST, instance=special_request)
        if form.is_valid():
            # Save the form and update the review timestamp
            updated_request = form.save(commit=False)
            updated_request.reviewed_at = timezone.now()
            updated_request.save()
            
            # Check if any part was disapproved
            email_sent = False
            rejected_parts = []
            if updated_request.course_lock and not updated_request.course_lock_approved:
                rejected_parts.append("Course Lock Request")
            if (updated_request.unavailable_slots or updated_request.max_teaching_days < 5) and not updated_request.availability_approved:
                rejected_parts.append("Availability Request")

            if rejected_parts:
                # Construct the email
                subject = f"Special Request #{updated_request.id} Review Outcome"
                
                # List of items they requested
                course_lock_info = f"Course Lock Requested: {updated_request.course_lock.code}" if updated_request.course_lock else "No Course Lock Requested"
                availability_info = f"Unavailable Slots: {', '.join(updated_request.unavailable_slots) if updated_request.unavailable_slots else 'None'}\nMax Teaching Days: {updated_request.max_teaching_days if updated_request.max_teaching_days else 'Not specified'}"

                # Rejected parts summary
                rejected_summary = "Unfortunately, the following part(s) of your special request have been rejected: " + ", ".join(rejected_parts) + "."

                # Optional admin comments
                admin_comments = f"\n\nComments from Admin:\n{updated_request.admin_comments}" if updated_request.admin_comments else ""

                # Advice on next steps
                next_steps = (
                    "\n\nIf you wish to have the disapproved part(s) reviewed again, please resubmit the Special Request form with better justification or different entries."
                    "\n\nNote: If you submitted both Course Lock and Availability requests but only one was approved, "
                    "you may choose not to pursue the other disapproved part. The approved request will still be taken into account."
                    "\nHowever, if you decide to resubmit, you must fill out both parts of the Special Request form again, "
                    "including the part that was previously approved, as the entire request will be re-evaluated."
                )

                message = (
                    f"Dear {student.name},\n\n"
                    f"Your Special Request (ID: {updated_request.id}) has been reviewed.\n\n"
                    f"{course_lock_info}\n"
                    f"{availability_info}\n\n"
                    f"{rejected_summary}"
                    f"{admin_comments}"
                    f"{next_steps}\n\n"
                    f"Best regards,\nTeaching Allocation Portal Team"
                )

                # Send the email
                from_email = 'gsallocationfyp@gmail.com'  # Replace with your actual email
                send_mail(subject, message, from_email, [student.email])
                email_sent = True

            # Messages depending on whether email was sent
            if email_sent:
                messages.success(request, f"Special request for {student.user.username} has been reviewed. An email has been sent to notify the student to resubmit due to disapproval of some parts.")
            else:
                messages.success(request, f"Special request for {student.user.username} has been reviewed.")

            return redirect('view_special_requests')
    else:
        form = AdminSpecialRequestForm(instance=special_request)
    
    context = {
        'form': form,
        'special_request': special_request,
        'student': student,
        'am_slots': am_slots,
        'pm_slots': pm_slots,
    }
    return render(request, 'admin/review_special_request.html', context)

@login_required
@role_restricted(is_admin)
def allocation_dashboard(request):
    """
    Main view for the allocation dashboard
    """
    # Get allocation weights
    weights = AllocationWeights.get_weights()

    # Get penalty score from session or calculate current one
    penalty_score = request.session.pop('penalty_score', None)
    if penalty_score is None and Assignment.objects.exists():
        try:
            penalty_score = calculate_current_penalty_score(weights)
        except Exception as e:
            penalty_score = 0
            messages.error(request, f"Could not calculate penalty score: {str(e)}")

    # Handle form submissions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_weights':
            # Update allocation weights
            weights.odd_even_pair_weight = int(request.POST.get('odd_even_pair_weight', 40))
            weights.course_variety_weight = int(request.POST.get('course_variety_weight', 30))
            weights.past_assignments_weight = int(request.POST.get('past_assignments_weight', 20))
            weights.preference_weight = int(request.POST.get('preference_weight', 25))
            weights.workload_distribution_weight = int(request.POST.get('workload_distribution_weight', 15))
            weights.permutation_count = int(request.POST.get('permutation_count', 30))
            weights.save()
            messages.success(request, "Allocation weights updated successfully")

            # Recalculate penalty score with new weights
            try:
                penalty_score = calculate_current_penalty_score(weights)
            except Exception as e:
                messages.error(request, f"Could not recalculate penalty score: {str(e)}")
            
        elif action == 'auto_allocate':
            # Run auto allocation
            clear_existing = request.POST.get('clear_existing') == 'true'
            try:
                allocation_stats = allocation_algorithm(clear_existing=clear_existing)
                penalty_score = allocation_stats['penalty_score']  # Extract penalty_score
                messages.success(request, f"Automatic allocation completed with penalty score: {penalty_score}")
                request.session['penalty_score'] = penalty_score
            except ValueError as e:
                # Catch the ValueError and display it as an error message
                messages.error(request, str(e))
                return redirect('allocation_dashboard')
            
        elif action == 'clear_assignments':
            # Clear all assignments
            Assignment.objects.all().delete()
            Lab.objects.all().update(assigned=False)
            messages.success(request, "All assignments cleared")
            penalty_score = 0  # Reset penalty score 
            
        return redirect('allocation_dashboard')
    
    # Calculate statistics
    stats = calculate_dashboard_statistics()
    
    # Get student assignments for table
    students = Student.objects.filter(gs_duty=True).order_by('name')
    student_assignments = []
    
    for student in students:
        assignments = Assignment.objects.filter(student=student).select_related('course_lab', 'course_lab__code')
        total_workload = sum(a.course_lab.code.hours * a.course_lab.code.weeks for a in assignments)
        
        # Count distinct course code + lab group combinations
        assigned_labs_count = assignments.annotate(
            course_group=Concat(
                F('course_lab__code__code'),  # Course code
                Value('-'),  # Separator
                F('course_lab__group')  # Lab group
            )
        ).values('course_group').distinct().count()
        
        student_assignments.append({
            'student': student,
            'assigned_labs': assigned_labs_count,
            'lab_load': student.lab_load,
            'total_workload': total_workload,
            'assignments': assignments
        })
    
    # Get course assignments for table
    courses = Course.objects.all().order_by('code')
    course_assignments = []
    
    for course in courses:
        labs = Lab.objects.filter(code=course).select_related('code')
        grouped_labs = {}
        
        for lab in labs:
            key = lab.group
            if key not in grouped_labs:
                grouped_labs[key] = {
                    'group': lab.group,
                    'day': lab.day,
                    'time': lab.time,
                    'venue': lab.venue,
                    'teaching_weeks': lab.teaching_week,
                    'assigned': lab.assigned,
                    'student': None
                }
                
                # Find student if assigned
                if lab.assigned:
                    assignment = Assignment.objects.filter(course_lab=lab).first()
                    if assignment:
                        grouped_labs[key]['student'] = assignment.student
        
        course_assignments.append({
            'course': course,
            'total': course.grp_count,
            'labs': grouped_labs.values()
        })
    
    # Paginate tables
    paginator_students = Paginator(student_assignments, 10)
    paginator_courses = Paginator(course_assignments, 10)
    
    student_page = request.GET.get('student_page', 1)
    course_page = request.GET.get('course_page', 1)
    
    student_page_obj = paginator_students.get_page(student_page)
    course_page_obj = paginator_courses.get_page(course_page)
    
    # Prepare context
    context = {
        'stats': stats,
        'penalty_score': penalty_score,
        'weights': weights,
        'student_assignments': student_page_obj,
        'course_assignments': course_page_obj,
        'active_tab': request.GET.get('tab', 'student')
    }
    
    return render(request, 'admin/allocation_dashboard.html', context)

@login_required
@role_restricted(is_admin)
def edit_allocation(request):
    courses = Course.objects.all()
    selected_course = None
    grouped_assignments = []
    eligible_students = Student.objects.filter(gs_duty=True)
    
    if 'course' in request.GET:
        course_code = request.GET.get('course')
        try:
            selected_course = Course.objects.get(pk=course_code)
            
            # Get all labs for this course
            labs = Lab.objects.filter(code=selected_course)
            
            # Group labs by lab group
            lab_groups = {}
            for lab in labs:
                if lab.group not in lab_groups:
                    lab_groups[lab.group] = []
                lab_groups[lab.group].append(lab)
            
            # For each lab group, create an assignment entry
            for group_name, group_labs in lab_groups.items():
                # Check if any lab in this group is assigned
                assigned_lab = next((lab for lab in group_labs if lab.assigned), None)
                
                if assigned_lab:
                    # If a lab in this group is assigned, get its assignment
                    try:
                        assignment = Assignment.objects.get(course_lab=assigned_lab)
                    except Assignment.DoesNotExist:
                        assignment = None
                else:
                    assignment = None
                
                # Group labs by time slots
                time_slots = {}
                for lab in group_labs:
                    if lab.time not in time_slots:
                        time_slots[lab.time] = {
                            'day': lab.day,
                            'venue': lab.venue,
                            'teaching_weeks': []
                        }
                    time_slots[lab.time]['teaching_weeks'].extend(lab.teaching_week)
                
                # Sort time slots
                sorted_time_slots = []
                for time, info in time_slots.items():
                    info['time'] = time
                    info['teaching_weeks'] = sorted(set(info['teaching_weeks']))
                    sorted_time_slots.append(info)
                
                # Create a group entry with all relevant information
                group_entry = {
                    'group': group_name,
                    'time_slots': sorted_time_slots,
                    'labs': group_labs,
                    'assignment': assignment,
                    'student': assignment.student if assignment else None,
                    'first_lab_id': group_labs[0].id
                }
                
                grouped_assignments.append(group_entry)
                
        except Course.DoesNotExist:
            pass
    
    context = {
        'courses': courses,
        'selected_course': selected_course,
        'grouped_assignments': grouped_assignments,
        'eligible_students': eligible_students
    }
    
    return render(request, 'admin/edit_allocation.html', context)

@login_required
@role_restricted(is_admin)
def save_assignments(request):
    if request.method == 'POST':
        course_code = request.POST.get('course_code')
        try:
            course = Course.objects.get(pk=course_code)
            all_labs = Lab.objects.filter(code=course)
            
            # Track if we made any changes
            changes_made = False
            error_occurred = False
            
            # Group labs by lab group
            lab_groups = {}
            for lab in all_labs:
                if lab.group not in lab_groups:
                    lab_groups[lab.group] = []
                lab_groups[lab.group].append(lab)
            
            # Process each lab group
            for group_name, group_labs in lab_groups.items():
                representative_lab = group_labs[0]
                student_id = request.POST.get(f'student_{representative_lab.id}')
                delete = request.POST.get(f'delete_{representative_lab.id}')
                
                # Handle deletion for the entire group
                if delete:
                    for lab in group_labs:
                        Assignment.objects.filter(course_lab=lab).delete()
                        lab.assigned = False
                        lab.save()
                    changes_made = True
                    continue
                
                # Handle assignment changes
                if student_id:
                    try:
                        student = Student.objects.get(user_id=student_id)
                        is_valid, error_message = validate_group_assignment(student, group_labs)
                        
                        if is_valid:
                            for lab in group_labs:
                                try:
                                    assignment = Assignment.objects.get(course_lab=lab)
                                    if assignment.student != student:
                                        assignment.student = student
                                        assignment.save()
                                        changes_made = True
                                except Assignment.DoesNotExist:
                                    Assignment.objects.create(course_lab=lab, student=student)
                                    changes_made = True
                                
                                lab.assigned = True
                                lab.save()
                        else:
                            messages.error(request, f"Cannot assign {student.name} to group {group_name}: {error_message}")
                            error_occurred = True
                    except Student.DoesNotExist:
                        for lab in group_labs:
                            Assignment.objects.filter(course_lab=lab).delete()
                            lab.assigned = False
                            lab.save()
                        changes_made = True
                else:
                    # No student selected - remove assignments
                    for lab in group_labs:
                        Assignment.objects.filter(course_lab=lab).delete()
                        lab.assigned = False
                        lab.save()
                    changes_made = True
            
            # Only show success message if changes were made and no errors occurred
            if changes_made and not error_occurred:
                messages.success(request, f"Assignments for {course.code} updated successfully")
            
        except Course.DoesNotExist:
            messages.error(request, "Invalid course code")
        
        return redirect('allocation_dashboard')
    
    return redirect('edit_allocation')


def calculate_dashboard_statistics():
    """Calculate statistics for the allocation dashboard"""
    stats = {}
    
    # Total number of students who have met their lab load
    total_students = Student.objects.filter(gs_duty=True).count()
    
    # Students who have met their lab load
    students_with_lab_load_met = 0
    for student in Student.objects.filter(gs_duty=True):
        assigned_labs = Assignment.objects.filter(student=student).count()
        if assigned_labs >= student.lab_load:
            students_with_lab_load_met += 1
    
    stats['students_with_lab_load_met'] = students_with_lab_load_met
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

def export_allocations(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="allocations.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Course Code', 'Course Name', 'Lab Category', 'Lab Hours', 'Lab Weeks', 
        'Lab Group', 'Lab Day', 'Lab Time', 'Lab Venue', 'Lab Teaching Week', 'Student Assigned'
    ])

    # Get all courses
    courses = Course.objects.all().order_by('code')

    for course in courses:
        labs = Lab.objects.filter(code=course).select_related('code')
        for lab in labs:
            assignment = Assignment.objects.filter(course_lab=lab).first()
            student_assigned = assignment.student.name if assignment else "Not Assigned"

            writer.writerow([
                course.code,
                course.title,
                course.lab_cat,
                course.hours,
                course.weeks,
                lab.group,
                lab.day,
                lab.time,
                lab.venue,
                ', '.join(map(str, lab.teaching_week)),
                student_assigned
            ])

    return response

@login_required
@role_restricted(is_student)
def view_allocations(request):
    # Get the logged-in student
    student = Student.objects.get(user=request.user)

    # Get the logged-in student's assignments
    assignments = Assignment.objects.filter(student__user=request.user)

    # Get all student assignments (for the "All Student Assignments" tab)
    all_students = Student.objects.all()
    all_assignments = []

    for s in all_students:
        student_assignments = Assignment.objects.filter(student=s)
        if student_assignments.exists():
            all_assignments.append({
                'student': s,
                'assignments': student_assignments,
            })

    context = {
        'student': student,
        'assignments': assignments,
        'all_assignments': all_assignments,
    }

    return render(request, 'student/view_allocations.html', context)

@login_required
@role_restricted(is_student)
def contact_student(request):
    if request.method == 'POST':
        form = ContactStudentForm(request.POST)
        if form.is_valid():
            # Get the recipient and message
            recipient = form.cleaned_data['recipient']
            message = form.cleaned_data['message']

            # Include the logged-in student's email in the message
            full_message = f"""Dear {recipient.name}

You have received a message from {request.user.student.name} ({request.user.email}).

Message from {request.user.student.name}:
{message}

You can access the Teaching Allocation Portal here:
http://127.0.0.1:8000/

Best regards,
Teaching Allocation Portal Team
"""

            # Send the email
            send_mail(
                subject=f"Teaching Allocation Portal: Message from {request.user.student.name}",
                message=full_message,
                from_email='gsallocationfyp@gmail.com',  # Use a generic "no-reply" email
                recipient_list=[recipient.email],  # Send to the selected student's email
            )

            messages.success(request, "Your message has been sent successfully.")
            return redirect('view_allocations')
    else:
        form = ContactStudentForm()

    return render(request, 'student/contact_student.html', {'form': form})

@login_required
@role_restricted(is_admin)
def confirm_and_notify_students(request):
    """
    Confirm allocations and notify students via email with CSV attachment
    """
    if request.method != 'POST':
        return redirect('allocation_dashboard')
        
    # Get all students with gs_duty=True
    students = Student.objects.filter(gs_duty=True)
    
    # Get unique email addresses to avoid duplicate emails
    unique_emails = set(student.email for student in students if student.email)
    
    if not unique_emails:
        messages.error(request, "No student emails found to notify")
        return redirect('allocation_dashboard')
    
    # Create CSV file in memory
    csv_file = io.StringIO()
    writer = csv.writer(csv_file)
    writer.writerow([
        'Course Code', 'Course Name', 'Lab Category', 'Lab Hours', 'Lab Weeks', 
        'Lab Group', 'Lab Day', 'Lab Time', 'Lab Venue', 'Lab Teaching Week', 'Student Assigned'
    ])

    # Get all courses
    courses = Course.objects.all().order_by('code')

    for course in courses:
        labs = Lab.objects.filter(code=course).select_related('code')
        for lab in labs:
            assignment = Assignment.objects.filter(course_lab=lab).first()
            student_assigned = assignment.student.name if assignment else "Not Assigned"

            writer.writerow([
                course.code,
                course.title,
                course.lab_cat,
                course.hours,
                course.weeks,
                lab.group,
                lab.day,
                lab.time,
                lab.venue,
                ', '.join(map(str, lab.teaching_week)),
                student_assigned
            ])
    
    # Prepare email content
    subject = "Lab Allocation Results"
    message = """Dear Student,

The lab allocations for this semester have been confirmed and are now available in the Teaching Allocation Portal.

You can access your allocations by logging into the portal at http://127.0.0.1:8000/. A complete list of all allocations is attached to this email for your reference.

Please review your assignments and let us know if you have any questions.

Best regards,
Teaching Allocation Portal Team
"""

    # Send email with attachment
    try:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email='gsallocationfyp@gmail.com',
            to=list(unique_emails),  # Send to unique emails only
        )
        
        # Add the CSV file as an attachment
        csv_file.seek(0)
        email.attach('allocations.csv', csv_file.getvalue(), 'text/csv')
        
        # Send the email
        email.send()
        
        messages.success(request, f"Allocation notifications sent to {len(unique_emails)} unique email addresses")
    except Exception as e:
        messages.error(request, f"Error sending emails: {str(e)}")
    
    return redirect('allocation_dashboard')

@login_required
@role_restricted(is_admin)
def semester_reset(request):
    students = Student.objects.all()
    
    if request.method == 'POST':
        # Check which form was submitted based on the button clicked
        if 'send_all' in request.POST:
            # Send email to all students
            subject = request.POST.get('subject')
            message = request.POST.get('message')
            
            if subject and message:
                recipient_list = [student.email for student in students]
                
                # Send the email to all students
                send_mail(
                    subject=subject,
                    message=message,
                    from_email='gsallocationfyp@gmail.com',
                    recipient_list=recipient_list,
                    fail_silently=False,
                )
                
                messages.success(request, f"Email sent successfully to {len(recipient_list)} students.")
                return redirect('admin_communications')
            else:
                messages.error(request, "Subject and message are required.")
                
        elif 'send_selected' in request.POST:
            # Send email to selected students
            subject = request.POST.get('subject')
            message = request.POST.get('message')
            selected_students = request.POST.getlist('selected_students')
            
            if subject and message and selected_students:
                recipient_list = []
                for selected in selected_students:
                    try:
                        student = Student.objects.get(user__username=selected)
                        recipient_list.append(student.email)
                    except Student.DoesNotExist:
                        pass
                
                if recipient_list:
                    # Send the email to selected students
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email='gsallocationfyp@gmail.com',
                        recipient_list=recipient_list,
                        fail_silently=False,
                    )
                    
                    messages.success(request, f"Email sent successfully to {len(recipient_list)} selected students.")
                else:
                    messages.error(request, "No valid student emails found.")
                return redirect('semester_reset')
            else:
                messages.error(request, "Subject, message, and at least one student selection are required.")
                
        elif 'reset_database' in request.POST:
            # Clear database tables
            confirmation = request.POST.get('confirmation')
            
            if confirmation == 'CONFIRM':
                # Delete records from the specified models
                SpecialRequest.objects.all().delete()
                TeachingPreference.objects.all().delete()
                Assignment.objects.all().delete()
                
                # Clear past assignments from all students
                for student in students:
                    student.past_assignments.clear()
                
                messages.success(request, "Database has been reset successfully. All records have been cleared.")
                return redirect('semester_reset')
            else:
                messages.error(request, "You must type 'CONFIRM' to reset the database.")
    
    return render(request, 'admin/semester_reset.html', {'students': students})

def calculate_current_penalty_score(weights):
    """Calculate penalty score for current assignments"""
    assignments = Assignment.objects.select_related('student', 'course_lab').all()
    
    if not assignments.exists():
        return 0
    
    student_assignments = defaultdict(list)
    flat_assignments = []
    
    # Get all students with assignments
    assigned_students = set()
    for assignment in assignments:
        student = assignment.student
        lab = assignment.course_lab
        group_key = (lab.code, lab.group)
        
        flat_assignments.append((student, lab))
        assigned_students.add(student)
        
        if not any(group_key == (lg[0].code, lg[0].group) for lg in student_assignments[student]):
            group_labs = Lab.objects.filter(code=lab.code, group=lab.group)
            student_assignments[student].append(list(group_labs))
    
    # Only use students who actually have assignments
    students = list(assigned_students)
    
    try:
        penalty_score = calculate_penalty_score(
            flat_assignments,
            dict(student_assignments),
            students,
            weights
        )
    except Exception:
        penalty_score = 0
    
    return round(penalty_score, 1)
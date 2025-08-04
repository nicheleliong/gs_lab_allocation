from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django import forms
from .models import Student, Course, SpecialRequest, TeachingPreference, Lab, AllocationWeights
from django.forms import ModelForm, CheckboxSelectMultiple, modelformset_factory
import re

class AdminRegisterStudentForm(forms.ModelForm):
    email = forms.EmailField(label="",widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Email Address'}))
    first_name = forms.CharField(label="",max_length=100, widget=forms.TextInput(attrs={'class':'form-control','placeholder':'First Name'}))
    last_name = forms.CharField(label="",max_length=100, widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Last Name'}))
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']  # Include only the fields you need
    
    # Custom save method to set the password automatically
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user
    
    #constructor method used to initalise AdminRegisterStudentForm  
    def __init__(self, *args, **kwargs):
        #calls the parent class's constructor (forms.ModelForm)
        #to ensure all inherited functionality is intialised correctly
        super(AdminRegisterStudentForm, self).__init__(*args, **kwargs)

        self.fields['username'].widget.attrs['class']='form-control'
        self.fields['username'].widget.attrs['placeholder']='Username'
        self.fields['username'].label=''
        self.fields['username'].help_text='<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.</small></span>'


# create Add Student Form
class AddStudentForm(forms.ModelForm):
    name = forms.CharField(required=True, widget=forms.widgets.TextInput(attrs={"placeholder": "Name", "class":"form-control"}),label="")
    email = forms.CharField(required=True, widget=forms.widgets.TextInput(attrs={"placeholder": "Email", "class":"form-control"}),label="")
    supervisor = forms.CharField(required=True, widget=forms.widgets.TextInput(attrs={"placeholder": "CCDS PhD Supervisor", "class":"form-control"}),label="")
    bachelor_degree = forms.CharField(required=True, widget=forms.widgets.TextInput(attrs={"placeholder": "Bachelor Degree", "class":"form-control"}),label="")
    matriculation_date = forms.CharField(required=True, widget=forms.widgets.TextInput(attrs={"placeholder": "Matriculation Date", "class":"form-control"}),label="")
    
    class Meta:
        model = Student
        exclude = ("user",)

class UserProfileForm(forms.ModelForm):
    """Form for updating user details."""
    username = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username'
        })
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    
    
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

# for setup_profile and edit_profile
class StudentProfileForm(forms.ModelForm):
    supervisor = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter supervisor name'
        })
    )
    
    bachelor_degree = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter name of bachelor degree earned'
        })
    )
    
    matriculation_date = forms.CharField(
        validators=[RegexValidator(
            regex=r'^(0[1-9]|1[0-2])/\d{4}$', 
            message='Matriculation date must be in MM/YYYY format (valid months: 01-12)'
        )],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'MM/YYYY',
            'pattern': '(0[1-9]|1[0-2])/\d{4}'
        })
    )


    class Meta:
        model = Student  # Make sure this is correctly set
        fields = ['supervisor', 'bachelor_degree', 'matriculation_date']

    def clean_matriculation_date(self):
        date_str = self.cleaned_data.get('matriculation_date')
        
        try:
            # Convert string to datetime object
            from datetime import datetime
            datetime.strptime(date_str, '%m/%Y')
            return date_str
        except (ValueError, TypeError):
            raise forms.ValidationError("Invalid date format. Use MM/YYYY.")

class AddCourseForm(forms.ModelForm):
    lab_cat_choices = (
        ('C', 'C'),
        ('D', 'D'),
    )

    code = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter the Course Code'
        })
    )
    title = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter the Course Title'
        })
    )
    year = forms.IntegerField(
        required=True,
        widget=forms.NumberInput(attrs={  # Changed from IntegerField to NumberInput
            'class': 'form-control',
            'placeholder': 'Enter the Year',  # Fixed placeholder
            'min': '1', 
            'max': '3'
        })
    )
    lab_cat = forms.ChoiceField(
        required=True,
        choices=lab_cat_choices,  # Changed from 'choice' to 'choices'
        widget=forms.Select(attrs={  # Changed from ChoiceField to Select
            'class': 'form-control',
            'placeholder': 'Enter the Lab Category',
            'choices': lab_cat_choices
        })
    )
    hours = forms.IntegerField(
        required=True,
        widget=forms.NumberInput(attrs={  # Changed from IntegerField to NumberInput
            'class': 'form-control',
            'placeholder': 'Enter the Number of Hours per Lab',
            'min': '1'
        })
    )
    weeks = forms.IntegerField(  # Fixed typo: NumbeIntegerFieldrInput
        required=True,
        widget=forms.NumberInput(attrs={  # Changed from IntegerField to NumberInput
            'class': 'form-control',
            'placeholder': 'Enter the Number of Weeks',
            'min': '1', 
            'max': '13'
        })
    )
    # Optional manual override for grp_count
    manual_grp_count = forms.IntegerField(
        required=False, 
        min_value=0, 
        label='Manual Group Count (optional)',
        help_text='Leave blank to auto-calculate from labs. Fill in to override.'
    )

    class Meta:
        model = Course
        fields = ['code', 'title', 'year', 'lab_cat', 'hours', 'weeks']

class SemesterInformationForm(forms.ModelForm):
    gs_duty = forms.ChoiceField(
        choices=[(True, 'Yes'), (False, 'No')],
        widget=forms.RadioSelect,
        label='Graduate Student Duty (GS Duty)'
    )
    lab_load = forms.IntegerField(label='Preferred Lab Load', required=False, min_value=0)
    past_assignments = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Previous Course Assignments'
    )

    class Meta:
        model = Student
        fields = ['gs_duty', 'lab_load', 'past_assignments']

class SpecialRequestForm(ModelForm):
    course_lock = forms.ModelChoiceField(
        queryset=Course.objects.all(),
        required=False,
        empty_label="Not Applicable",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    lab_groups_locked = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '1', 
            'max': '{{ student.lab_load }}',
        })
    )
    faculty_contact = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        })
    )
    max_teaching_days = forms.IntegerField(  
        required=False,
        initial=5,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '1', 
            'max': '5',
        })
    )

    justification = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control'
        }),
        required=False, 
    )
    
    class Meta:
        model = SpecialRequest
        fields = ['course_lock', 'lab_groups_locked', 'faculty_contact', 'max_teaching_days', 'justification']
        exclude = ['unavailable_slots', 'student']
    
    def clean(self):
        cleaned_data = super().clean()
        course_lock = cleaned_data.get('course_lock')
        lab_groups_locked = cleaned_data.get('lab_groups_locked')
        faculty_contact = cleaned_data.get('faculty_contact')
        max_teaching_days = cleaned_data.get('max_teaching_days', 5)
        justification = cleaned_data.get('justification')

        # Capture POSTed unavailable_slots via self.data (since it's handled outside model form)
        unavailable_slots = self.data.getlist('unavailable_slots')

        # Validation: If more than 8 unavailable slots selected
        if len(unavailable_slots) > 8:
            raise forms.ValidationError("You can only select up to 8 unavailable slots.")
        
        # Validation: If unavailable slots selected or max teaching days < 5, require justification
        if unavailable_slots or (max_teaching_days and int(max_teaching_days) < 5):
            if not justification:
                self.add_error('justification', 'Justification is required when constraints are applied.')

        # Validation: If course_lock is selected, lab_groups_locked and faculty_contact must be filled
        if course_lock:
            if not lab_groups_locked:
                self.add_error('lab_groups_locked', 'Required when a course is selected')
            if not faculty_contact:
                self.add_error('faculty_contact', 'Required when a course is selected')
        return cleaned_data

class TeachingPreferenceForm(forms.Form):
    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
        self.student = student

        # Fetch courses grouped by year
        courses_by_year = {
            1: Course.objects.filter(year=1),
            2: Course.objects.filter(year=2),
            3: Course.objects.filter(year=3),
        }

        # Dynamically create an integer field for each course
        for year, courses in courses_by_year.items():
            for course in courses:
                field_name = f"course_{course.new_code}"
                self.fields[field_name] = forms.IntegerField(
                    label=f"{course.code} - {course.title}",
                    required=False,  # Allow blank for courses the student doesn't want to rank
                    min_value=1,
                    max_value=8,
                    widget=forms.NumberInput(attrs={
                        'placeholder': 'Ranking',
                        'class': 'form-control w-80',
                    })
                )
                # Store metadata on the field itself to help later
                self.fields[field_name].course = course
                self.fields[field_name].year = year

class FileUploadForm(forms.Form):
    file = forms.FileField(label="Upload Excel File")

# Form for editing a single Lab
class LabForm(forms.ModelForm):
    day_choices = (
         ('MON', 'MON'),
         ('TUE', 'TUE'),
         ('WED', 'WED'),
         ('THU', 'THU'),
         ('FRI', 'FRI'),
     )
    group = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        })
    )
    day = forms.ChoiceField(
        required=True,
        choices=day_choices,  # Changed from 'choice' to 'choices'
        widget=forms.Select(attrs={  # Changed from ChoiceField to Select
            'class': 'form-control',
            'choices': day_choices
        })
    )
    venue = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        })
    )
    time = forms.CharField(
        validators=[RegexValidator(
            regex=r'^\d{4}-\d{4}$',
            message='Time must be in the format: e.g. 1430-1520, 1100-1250'
        )],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 1430-1620',
            'pattern': r'\d{4}-\d{4}' 
        })
    )
    teaching_week = forms.CharField(
        validators=[RegexValidator(
            regex=r'^(\d+(,\s*\d+)*)?$', 
        )],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'pattern': r'(\d+(,\s*\d+)*)?' 
        })
    )

    class Meta:
        model = Lab
        fields = ['group', 'day', 'time', 'venue', 'teaching_week']
    
    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        if instance and instance.teaching_week:
            # Convert list to comma-separated string for the initial display
            initial = kwargs.get('initial', {})
            initial['teaching_week'] = ', '.join(map(str, instance.teaching_week))
            kwargs['initial'] = initial
        super(LabForm, self).__init__(*args, **kwargs)
    
    def clean_teaching_week(self):
        data = self.cleaned_data.get('teaching_week', '')
        print(f"Cleaning teaching_week: {data}")  # Debug print
        
        if not data:
            return list(range(1, 14))
        
        try:
            # Split by commas and convert to integers
            week_list = [int(i.strip()) for i in data.split(',') if i.strip()]
            print(f"Converted to: {week_list}")  # Debug print
            return week_list
        except ValueError:
            print("ValueError in clean_teaching_week")  # Debug print
            raise forms.ValidationError('Please enter valid integers separated by commas (e.g. 1, 2, 3).')

# FormSet for multiple Labs tied to a Course
LabFormSet = modelformset_factory(Lab, form=LabForm, extra=0, can_delete=True) 

class AdminSpecialRequestForm(forms.ModelForm):
    course_lock_approved = forms.BooleanField(required=False, label="Approve Course Lock")
    availability_approved = forms.BooleanField(required=False, label="Approve Time Constraints")
    admin_comments = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'form-control',
            'placeholder': 'Optional comments for the student'
        }),
        required=False
    )
    
    class Meta:
        model = SpecialRequest
        fields = ['course_lock_approved', 'availability_approved', 'admin_comments']

class AllocationWeightsForm(forms.ModelForm):
    odd_even_pair_weight = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )
    course_variety_weight = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )
    past_assignments_weight = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )
    preference_weight = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )
    workload_distribution_weight = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )
    permutation_count = forms.IntegerField( 
        required=False,
        widget=forms.NumberInput(attrs={ 
            'class': 'form-control',
            'min': '10', 
        })
    )

    
    class Meta:
        model = AllocationWeights
        fields = ['odd_even_pair_weight', 'course_variety_weight', 'past_assignments_weight', 
                  'preference_weight', 'workload_distribution_weight', 'permutation_count']
        widgets = {
            'odd_even_pair_weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'course_variety_weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'past_assignments_weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'preference_weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'workload_distribution_weight': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class ManualAssignmentForm(forms.Form):
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(gs_duty=True),
        required=True,
        empty_label="Select a student"
    )
    lab = forms.ModelChoiceField(
        queryset=Lab.objects.filter(assigned=False),
        required=True,
        empty_label="Select a lab group"
    )

class CourseSelectionForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.all(),
        required=False,
        empty_label="-- Select a course --"
    )

class ContactStudentForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=Student.objects.all(), 
        label="Select Student",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}), 
        label="Message"
    )

class AdminEmailForm(forms.Form):
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Subject"
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
        label="Message"
    )
    selected_students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control selectpicker', 'data-live-search': 'true'}),
        required=False,
        label="Select Students"
    )
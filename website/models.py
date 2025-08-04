from django.db import models
from django.contrib.auth.models import User
import re

class Course(models.Model):
    code = models.CharField(max_length=50, primary_key=True)  # Explicit PK
    new_code = models.CharField(max_length=50, editable=False, blank=True)  # Auto-generated field
    title = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    lab_cat = models.CharField(max_length=1)
    hours = models.PositiveSmallIntegerField()
    weeks = models.PositiveSmallIntegerField()
    grp_count = models.PositiveSmallIntegerField(null=True)

    def save(self, *args, **kwargs):
        # Auto-generate new_code from the part before the '/'
        self.new_code = re.split(r'/', self.code)[0] if '/' in self.code else self.code
        super().save(*args, **kwargs)  # Call the original save method

    def __str__(self):
        return f"{self.code} {self.title}"


# Lab Model
class Lab(models.Model):
    code = models.ForeignKey(Course, on_delete=models.CASCADE)  # FK to Course
    group = models.CharField(max_length=10)
    day = models.CharField(max_length=3)
    time = models.CharField(max_length=9)
    venue = models.CharField(max_length=10)
    teaching_week = models.JSONField(default=list)  # Stores list of weeks (1-13)
    assigned = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code', 'group','day','time','venue'], name='unique_lab_entry')
        ]

    def __str__(self):
        return f"{self.code.code}-{self.group}"

# Student Model
class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)  # PK linked to User
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()  # add in unique=True when deploy
    supervisor = models.CharField(max_length=100, blank=True, default="Not Set")
    bachelor_degree = models.CharField(max_length=100, blank=True, default="Not Set")
    matriculation_date = models.CharField(max_length=7, blank=True, default="Not Set")
    gs_duty = models.BooleanField(default=True)
    lab_load = models.PositiveSmallIntegerField(default=4)  # Remove max_length (not valid for IntegerField)
    past_assignments = models.ManyToManyField(Course, blank=True)  # Allows multiple courses
 
    def __str__(self):
        return f"{self.name} ({self.matriculation_date})"

# Course Lock + Day Availability & Constraints
class SpecialRequest(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, unique=True)
    course_lock = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    lab_groups_locked = models.PositiveSmallIntegerField(default=0, blank=True) # Number of lab groups agreed to take
    faculty_contact = models.CharField(max_length=100, blank=True) # Store faculty member's name
    unavailable_slots = models.JSONField(default=list, blank=True)  # Store Day + AM/PM blackout
    max_teaching_days = models.PositiveSmallIntegerField(default=5, blank=True)
    justification = models.TextField(blank=True)
    course_lock_approved = models.BooleanField(default=False)
    availability_approved = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True) # Track when the Admin reviewed request
    admin_comments = models.TextField(blank=True) # Admin feedback if disapproved request

class TeachingPreference(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    ranking = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student} preference for {self.course} (Rank {self.ranking})"

# Assignment Model
class Assignment(models.Model):
    course_lab = models.ForeignKey(Lab, on_delete=models.CASCADE)  # Links to a specific course's lab
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True)  # Student who was assigned
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course_lab} Assigned to {self.student.name if self.student else 'Unassigned'}"

class AllocationWeights(models.Model):
    """
    Stores weights for the allocation algorithm's constraints
    """
    odd_even_pair_weight = models.IntegerField(default=40, 
        help_text="Weight for assigning odd/even week pairs to the same student")
    course_variety_weight = models.IntegerField(default=30, 
        help_text="Weight for minimizing variety of courses assigned to each student")
    past_assignments_weight = models.IntegerField(default=15, 
        help_text="Weight for assigning courses a student has taught before")
    preference_weight = models.IntegerField(default=25, 
        help_text="Weight for student preferences")
    workload_distribution_weight = models.IntegerField(default=20, 
        help_text="Weight for fair workload distribution")
    permutation_count = models.IntegerField(default=30, 
        help_text="Number of permutations to run for the allocation algorithm")

    @classmethod
    def get_weights(cls):
        """Get the current weights, creating default if none exist"""
        weights, created = cls.objects.get_or_create(pk=1)
        return weights
from django.contrib import admin
from .models import Student, Course, Lab, Assignment, SpecialRequest, TeachingPreference

# Register your models here.
admin.site.register(Student)
admin.site.register(Course)
admin.site.register(Lab)
admin.site.register(Assignment)
admin.site.register(SpecialRequest)
admin.site.register(TeachingPreference)
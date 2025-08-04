from django.urls import path
from . import views

urlpatterns = [
    path('',views.home, name='home'),
    path('unauthorized/',views.unauthorized, name='unauthorized'),
    path('logout/', views.logout_user, name='logout'),

    # Admin URLs
    path('view_students/',views.view_students, name='view_students'), 
    path('register_student/',views.register_student, name='register_student'),
    path('delete_student/<int:pk>', views.delete_student, name='delete_student'),
    path('view_courses/',views.view_courses, name='view_courses'), 
    path('course/<str:new_code>',views.course, name='course'), 
    path('edit_course/<str:new_code>/',views.edit_course, name='edit_course'),
    path('delete_course/<str:new_code>/',views.delete_course, name='delete_course'), 
    path('add_course/',views.add_course, name='add_course'), 
    path('add_labs/',views.add_labs, name='add_labs'), 
    path('view_special_requests/', views.view_special_requests, name='view_special_requests'),
    path('review_special_request/<int:request_id>/', views.review_special_request, name='review_special_request'),
    path('allocation_dashboard/',views.allocation_dashboard, name='allocation_dashboard'),
    path('export-allocations/', views.export_allocations, name='export_allocations'),
    path('edit_allocation/',views.edit_allocation, name='edit_allocation'),
    path('save_assignments/',views.save_assignments, name='save_assignments'),
    path('confirm_and_notify_students/',views.confirm_and_notify_students, name='confirm_and_notify_students'),
    path('semester_reset/',views.semester_reset, name='semester_reset'),
    

    # Student URLs
    path('profile/',views.profile, name='profile'),
    path('edit_profile',views.edit_profile, name='edit_profile'),
    path('semester_info/',views.semester_info, name='semester_info'),
    path('special_request/',views.special_request, name='special_request'),
    path('teaching_preference/',views.teaching_preference, name='teaching_preference'),
    path('view_allocations/',views.view_allocations, name='view_allocations'),
    path('contact_student/',views.contact_student, name='contact_student'),
]
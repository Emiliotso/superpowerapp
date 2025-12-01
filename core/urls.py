from django.urls import path
from . import views

urlpatterns = [
    path('feedback/<uuid:uuid>/', views.survey_view, name='survey_view'),
    
    # Analysis & Chat
    path('profile/analyze/', views.profile_analysis_view, name='profile_analysis'),
    path('profile/chat/', views.chat_view, name='chat_view'),
    
    # Dashboard & Auth
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('invite/', views.add_invite_view, name='add_invite'),
    path('signup/', views.signup_view, name='signup'),
]
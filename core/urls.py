from django.urls import path
from . import views

urlpatterns = [
    path('feedback/<uuid:uuid>/', views.survey_view, name='survey_view'),
    path('feedback/<uuid:uuid>/submit/', views.survey_feedback_view, name='survey_feedback'),
    path('feedback/<uuid:uuid>/alternative/', views.get_alternative_question, name='get_alternative_question'),
    path('public/<uuid:uuid>/', views.public_survey_view, name='public_survey'),
    
    # Analysis & Chat
    path('profile/analyze/', views.profile_analysis_view, name='profile_analysis'),
    path('profile/chat/', views.chat_view, name='chat_view'),
    
    # Dashboard & Auth
    path('', views.landing_view, name='landing'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('stats/', views.stats_view, name='stats'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('invite/', views.add_invite_view, name='add_invite'),
    path('invite/delete/<uuid:uuid>/', views.delete_invite_view, name='delete_invite'),
    # path('signup/', views.signup_view, name='signup'), # Handled by allauth
]
from django.urls import path
from . import views

urlpatterns = [
    path('feedback/<uuid:uuid>/', views.survey_view, name='survey_view'),
    path('public/<uuid:uuid>/', views.public_survey_view, name='public_survey'),
    
    # Analysis & Chat
    path('profile/analyze/', views.profile_analysis_view, name='profile_analysis'),
    path('profile/chat/', views.chat_view, name='chat_view'),
    
    # Dashboard & Auth
    path('', views.landing_view, name='landing'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('invite/', views.add_invite_view, name='add_invite'),
    path('invite/delete/<uuid:uuid>/', views.delete_invite_view, name='delete_invite'),
    # path('signup/', views.signup_view, name='signup'), # Handled by allauth
]
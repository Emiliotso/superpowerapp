from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Survey
import google.generativeai as genai
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
import json

# PASTE YOUR GOOGLE KEY HERE
GOOGLE_API_KEY = "AIzaSyA44_vEHOMlzZdErpMajfs2SJNh5Oq1-fM"

def survey_view(request, uuid):
    # 1. Find the specific invitation
    survey = get_object_or_404(Survey, uuid=uuid)

    # 2. If POST, save answers
    if request.method == 'POST':
        survey.relationship_context = request.POST.get('relationship', '')
        survey.foxhole_answer = request.POST.get('foxhole', '')
        survey.magic_answer = request.POST.get('magic', '')
        survey.shadow_answer = request.POST.get('shadow', '')
        survey.is_completed = True
        survey.save()
        return render(request, 'thank_you.html')

    # 3. If GET, show the form (only if not completed)
    if survey.is_completed:
         return render(request, 'thank_you.html')
         
    return render(request, 'survey_form.html', {'survey': survey})

# --- NEW GEMINI FUNCTION ---
    return render(request, 'results.html', {'survey': survey})

@login_required
def profile_analysis_view(request):
    # 1. Gather ALL completed surveys for this user
    completed_surveys = Survey.objects.filter(user=request.user, is_completed=True)
    
    if not completed_surveys:
        return redirect('dashboard')
        
    # Aggregate text from the 3 specific questions
    text_data = ""
    
    # Add User Context
    profile = request.user.profile
    text_data += f"\n--- USER CONTEXT ---\n"
    text_data += f"Role: {profile.current_role}\n"
    text_data += f"Responsibilities: {profile.responsibilities}\n"
    text_data += f"Goal: {profile.career_goal}\n"
    text_data += f"Family: {profile.family_context}\n"
    text_data += f"Values: {profile.core_values}\n"
    text_data += f"Stress Response: {profile.stress_response}\n"
    
    for s in completed_surveys:
        text_data += f"\n--- Feedback from {s.respondent_name} ---\n"
        text_data += f"Context: {s.relationship_context}\n"
        text_data += f"Greatest Strength (Foxhole): {s.foxhole_answer}\n"
        text_data += f"Growth Area (Magic Wand): {s.magic_answer}\n"
        text_data += f"Stress Behavior (Shadow): {s.shadow_answer}\n"

    # 2. Configure Gemini
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')

    # 3. Create the Prompt
    prompt = f"""
    You are an expert executive coach. Read the following feedback about a user from multiple people and multiple contexts.
    
    FEEDBACK:
    {text_data}
    
    TASK:
    Synthesize all the feedback into a single, cohesive GLOBAL profile.
    
    1. **The Core Superpower**: Identify the single greatest strength that appears consistently across all feedback.
    2. **Enneagram Analysis**: Analyze their likely Enneagram type based on the *collective* behaviors described.
    3. **Actionable Advice**: Provide one piece of deep, actionable advice based on the synthesized feedback.
    
    Keep the tone encouraging, deep, and holistic.
    """

    # 4. Ask Gemini
    try:
        response = model.generate_content(prompt)
        # 5. Save to Profile
        profile = request.user.profile
        profile.ai_summary = response.text
        profile.save()
    except Exception as e:
        print(f"Gemini Error: {e}")
        # Ideally handle error gracefully
        pass

    return redirect('dashboard')

@login_required
def chat_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            
            # 1. Gather Context (All completed surveys)
            completed_surveys = Survey.objects.filter(user=request.user, is_completed=True)
            context_data = ""
            
            # Add User Context (Onboarding)
            profile = request.user.profile
            context_data += f"\n--- USER CONTEXT ---\n"
            context_data += f"Role: {profile.current_role}\n"
            context_data += f"Responsibilities: {profile.responsibilities}\n"
            context_data += f"Goal: {profile.career_goal}\n"
            context_data += f"Family: {profile.family_context}\n"
            context_data += f"Values: {profile.core_values}\n"
            context_data += f"Stress Response: {profile.stress_response}\n"

            for s in completed_surveys:
                context_data += f"\n--- Feedback (Anonymous) ---\n"
                context_data += f"Context: {s.relationship_context}\n"
                context_data += f"Strength: {s.foxhole_answer}\n"
                context_data += f"Growth: {s.magic_answer}\n"
                context_data += f"Stress: {s.shadow_answer}\n"

            # 2. Configure Gemini
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # 3. Construct Prompt with Privacy Rules
            prompt = f"""
            You are a confidential executive coach. You have access to the following 360-degree feedback about the user.
            
            FEEDBACK DATA:
            {context_data}
            
            USER QUESTION: "{user_message}"
            
            CRITICAL RULES:
            1. **CONFIDENTIALITY**: NEVER reveal the identity of the person who gave specific feedback. Use phrases like "One colleague mentioned..." or "Feedback suggests...".
            2. **SYNTHESIS**: Aggregate the insights. Don't just quote.
            3. **TONE**: Professional, encouraging, and growth-oriented.
            
            Answer the user's question based on the data.
            """
            
            response = model.generate_content(prompt)
            return JsonResponse({'reply': response.text})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Invalid request'}, status=400)

# --- DASHBOARD & AUTH ---

@login_required
def dashboard_view(request):
    # Check Onboarding
    if not request.user.profile.onboarding_completed:
        return redirect('onboarding')

    # Show only the logged-in user's surveys (invitations)
    surveys = Survey.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'dashboard.html', {'surveys': surveys, 'profile': request.user.profile})

@login_required
def onboarding_view(request):
    if request.method == 'POST':
        profile = request.user.profile
        profile.current_role = request.POST.get('role', '')
        profile.responsibilities = request.POST.get('responsibilities', '')
        profile.career_goal = request.POST.get('goal', '')
        profile.family_context = request.POST.get('family', '')
        profile.core_values = request.POST.get('values', '')
        profile.stress_response = request.POST.get('stress', '')
        profile.onboarding_completed = True
        profile.save()
        return redirect('dashboard')
    return render(request, 'onboarding.html')

@login_required
def add_invite_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone', '')
        
        # Create the invitation
        survey = Survey.objects.create(
            user=request.user,
            respondent_name=name,
            respondent_email=email,
            respondent_phone=phone
        )
        
        # Generate Link
        link = request.build_absolute_uri(reverse('survey_view', args=[survey.uuid]))
        
        # Send Email
        try:
            send_mail(
                subject=f"Feedback Request from {request.user.username}",
                message=f"Hi {name},\n\n{request.user.username} would value your feedback.\n\nPlease click here: {link}",
                from_email="noreply@superpower.app",
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email Error: {e}")
            # We still redirect to dashboard, but the error is logged.
            # In a real app, we might show a message to the user.
        
        return redirect('dashboard')
    return render(request, 'invite.html')

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('onboarding')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})
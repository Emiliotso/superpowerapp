from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .models import Survey, Profile, SurveyFeedback
import google.generativeai as genai
import os
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse, JsonResponse
import threading
import json

# API Key managed via environment variables


def survey_view(request, uuid):
    # 1. Find the specific invitation
    survey = get_object_or_404(Survey, uuid=uuid)

    # 2. If POST, save answers
    if request.method == 'POST':
        survey.relationship_context = request.POST.get('relationship', '')
        survey.energy_audit_answer = request.POST.get('energy_audit', '')
        survey.stress_profile_answer = request.POST.get('stress_profile', '')
        survey.glass_ceiling_answer = request.POST.get('glass_ceiling', '')
        survey.future_self_answer = request.POST.get('future_self', '')
        survey.is_completed = True
        survey.save()
        survey.is_completed = True
        survey.save()
        return render(request, 'thank_you.html', {'survey_uuid': survey.uuid})

    # 3. If GET, show the form (only if not completed)
    if survey.is_completed:
         return render(request, 'thank_you.html', {'survey_uuid': survey.uuid})
         
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
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)
    text_data += f"\n--- USER CONTEXT ---\n"
    text_data += f"Role: {profile.current_role}\n"
    text_data += f"Responsibilities: {profile.responsibilities}\n"
    text_data += f"Family: {profile.family_context}\n"
    text_data += f"Values: {profile.core_values}\n"
    
    text_data += f"\n--- 10-YEAR VISION ---\n"
    text_data += f"Perfect Tuesday (2035): {profile.vision_perfect_tuesday}\n"
    text_data += f"Toast Test: {profile.vision_toast_test}\n"
    text_data += f"Anti-Vision: {profile.vision_anti_vision}\n"
    
    text_data += f"\n--- INTERNAL OPERATING SYSTEM ---\n"
    text_data += f"Stress Response: {profile.stress_response}\n"
    text_data += f"The Anchor: {profile.internal_anchor}\n"
    
    for s in completed_surveys:
        text_data += f"\n--- Feedback from {s.respondent_name} ---\n"
        text_data += f"Context: {s.relationship_context}\n"
        text_data += f"Energy Audit: {s.energy_audit_answer}\n"
        text_data += f"Stress Profile: {s.stress_profile_answer}\n"
        text_data += f"Glass Ceiling: {s.glass_ceiling_answer}\n"
        text_data += f"Future Self: {s.future_self_answer}\n"

    # 2. Configure Gemini
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        from django.contrib import messages
        messages.error(request, "Configuration Error: No Google API Key found. Please add GOOGLE_API_KEY to your environment variables.")
        return redirect('dashboard')
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-pro')

    # 3. Create the Prompt
    prompt = f"""
    Role: You are an expert developmental psychologist and executive coach, fluent in the Enneagram, Internal Family Systems (IFS), The 6 Types of Working Genius, and Vertical Leadership Development.
    
    Input Data: You will receive 360-feedback from peers AND the user's own "10-Year Vision" from their onboarding.
    
    FEEDBACK DATA:
    {text_data}
    
    Objective: Synthesize the inputs into a high-impact "User Manual" for the subject. Do not summarize; interpret the data to reveal their operating system. Use "Radical Candor"—be direct, kind, and psychologically deep.
    
    Output Format:
    
    Section 1: Who You Are (The Operating System)
    * Core Motivation: Identify their likely Enneagram Type based on their stressors and desires.
    * Zone of Genius: Contrast where they have *competence* vs. where they actually get *energy* (Working Genius).
    
    Section 2: The Gap (Intent vs. Impact)
    * The Protectors (IFS): explicitly name the "Characters" that show up when they are stressed (e.g., "The Steamroller," "The Ghost," "The Martyr") and explain the specific cost of these behaviors on their relationships.
    * The Blind Spot: Highlight the specific behavior (Vertical Development edge) that threatens to sabotage their 10-Year Vision.
    
    Section 3: The North Star
    * Compare their *Self-Reported Vision* with *Peer Feedback*. Are they aligned? Is the user under-selling or over-selling themselves?
    * Paint a vivid picture of them operating at the "Self-Transforming" level of maturity.
    
    Section 4: The Manual (The Path Forward)
    * The Daily Practice: One specific micro-habit to integrate their Shadow/Protectors (e.g., "The 5-Minute Pause," "Solicited Criticism").
    * The Media Stack:
        * Read: 1 specific book (with a 1-sentence "why").
        * Watch: 1 movie or show that mirrors their specific character arc.
        * Listen: 1 specific podcast episode.
    * The Experience:
        * General: A specific type of activity to break their pattern (e.g., Improv, Jiu-Jitsu, Silent Retreat).
        * Local: If the user's location is known, suggest a specific local venue/vendor. If unknown, suggest how to find the best local option.
    """

    # 4. Ask Gemini
    try:
        print(f"DEBUG: Attempting to generate profile for {request.user.email}")
        response = model.generate_content(prompt)
        print("DEBUG: Gemini response received.")
        
        # 5. Save to Profile
        profile = request.user.profile
        profile.ai_summary = response.text
        profile.save()
        
        from django.contrib import messages
        messages.success(request, "Leadership Profile generated successfully!")
        
    except Exception as e:
        print(f"CRITICAL GEMINI ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Debug: List available models to see what the key can access
        debug_info = ""
        try:
            available = [m.name for m in genai.list_models()]
            debug_info = f" | Visible Models: {available}"
        except Exception as x:
            debug_info = f" | Could not list models: {x}"
        
        from django.contrib import messages
        messages.error(request, f"Analysis Failed: {str(e)}{debug_info}")
        # Don't just pass, we want to know.
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
            try:
                profile = request.user.profile
            except Profile.DoesNotExist:
                profile = Profile.objects.create(user=request.user)
            context_data += f"\n--- USER CONTEXT ---\n"
            context_data += f"Role: {profile.current_role}\n"
            context_data += f"Responsibilities: {profile.responsibilities}\n"
            context_data += f"Family: {profile.family_context}\n"
            context_data += f"Values: {profile.core_values}\n"
            
            context_data += f"\n--- 10-YEAR VISION ---\n"
            context_data += f"Perfect Tuesday (2035): {profile.vision_perfect_tuesday}\n"
            context_data += f"Toast Test: {profile.vision_toast_test}\n"
            context_data += f"Anti-Vision: {profile.vision_anti_vision}\n"
            
            context_data += f"\n--- INTERNAL OPERATING SYSTEM ---\n"
            context_data += f"Stress Response: {profile.stress_response}\n"
            context_data += f"The Anchor: {profile.internal_anchor}\n"

            for s in completed_surveys:
                context_data += f"\n--- Feedback (Anonymous) ---\n"
                context_data += f"Context: {s.relationship_context}\n"
                context_data += f"Energy: {s.energy_audit_answer}\n"
                context_data += f"Stress: {s.stress_profile_answer}\n"
                context_data += f"Glass Ceiling: {s.glass_ceiling_answer}\n"
                context_data += f"Future Self: {s.future_self_answer}\n"

            # 2. Configure Gemini
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                return JsonResponse({'reply': "System Error: Google API Key not configured."})

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-pro')
            
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

from django.http import HttpResponse

@login_required
def dashboard_view(request):
    try:
        # Ensure Profile exists
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user)

        # Check Onboarding
        if not profile.onboarding_completed:
            return redirect('onboarding')

        # Show only the logged-in user's surveys (invitations)
        surveys = Survey.objects.filter(user=request.user).order_by('-created_at')
        return render(request, 'dashboard.html', {'surveys': surveys, 'profile': profile})
    except Exception as e:
        import traceback
        return HttpResponse(f"<h1>Debug Error</h1><pre>{traceback.format_exc()}</pre>", status=500)

@login_required
def onboarding_view(request):
    try:
        # Ensure Profile exists
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user)

        if request.method == 'POST':
            profile.current_role = request.POST.get('role', '')
            profile.responsibilities = request.POST.get('responsibilities', '')
            profile.family_context = request.POST.get('family', '')
            profile.core_values = request.POST.get('values', '')
            
            # New Vision Fields
            profile.vision_perfect_tuesday = request.POST.get('vision_perfect_tuesday', '')
            profile.vision_toast_test = request.POST.get('vision_toast_test', '')
            profile.vision_anti_vision = request.POST.get('vision_anti_vision', '')
            
            # Internal OS
            profile.stress_response = request.POST.get('stress', '')
            profile.internal_anchor = request.POST.get('internal_anchor', '')
            
            profile.onboarding_completed = True
            profile.save()
            print(f"DEBUG: Onboarding saved for {request.user.username}. Completed: {profile.onboarding_completed}")
            return redirect('dashboard')
        return render(request, 'onboarding.html')
    except Exception as e:
        import traceback
        return HttpResponse(f"<h1>Debug Error</h1><pre>{traceback.format_exc()}</pre>", status=500)

@login_required
def add_invite_view(request):
    try:
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
            
            # Send Email in Background Thread
            import threading
            def send_email_thread(subject, message, from_email, recipient_list):
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=from_email,
                        recipient_list=recipient_list,
                        fail_silently=False,
                    )
                    print(f"Email sent successfully to {recipient_list}")
                except Exception as e:
                    print(f"Email Error (Background): {e}")

            email_thread = threading.Thread(
                target=send_email_thread,
                args=(
                    f"Feedback Request from {request.user.username}",
                    f"Hi {name},\n\n{request.user.username} would value your feedback.\n\nPlease click here: {link}",
                    settings.DEFAULT_FROM_EMAIL,
                    [email]
                )
            )
            email_thread.start()
            # print("Email sending temporarily disabled for debugging.")
            
            return redirect('dashboard')
        return render(request, 'invite.html')
    except Exception as e:
        import traceback
        return HttpResponse(f"<h1>Debug Error</h1><pre>{traceback.format_exc()}</pre>", status=500)

@login_required
def delete_invite_view(request, uuid):
    survey = get_object_or_404(Survey, uuid=uuid, user=request.user)
    if request.method == 'POST':
        survey.delete()
    return redirect('dashboard')

def public_survey_view(request, uuid):
    # 1. Find the user who owns this public link
    profile = get_object_or_404(Profile, public_link_uuid=uuid)
    user = profile.user
    
    if request.method == 'POST':
        # 2. Create a new Survey object for this respondent
        name = request.POST.get('name')
        email = request.POST.get('email')
        
        survey = Survey.objects.create(
            user=user,
            respondent_name=name,
            respondent_email=email,
            is_completed=False # They still need to fill it out
        )
        
        # 3. Redirect them to the actual survey form
        return redirect('survey_view', uuid=survey.uuid)
        
    return render(request, 'public_invite.html', {'user': user})

def custom_500(request):
    import traceback
    return HttpResponse(f"<h1>Server Error (500)</h1><pre>{traceback.format_exc()}</pre>", status=500)

def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')

def survey_feedback_view(request, uuid):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            survey = get_object_or_404(Survey, uuid=uuid)
            
            # Create or update feedback
            feedback, created = SurveyFeedback.objects.get_or_create(survey=survey)
            feedback.sentiment = data.get('sentiment', '')
            if data.get('comment'):
                feedback.comment = data.get('comment', '')
            feedback.save()
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def stats_view(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
        
    # Aggregate counts
    from django.db.models import Count
    total_feedback = SurveyFeedback.objects.count()
    
    # Get counts per sentiment
    counts = SurveyFeedback.objects.values('sentiment').annotate(count=Count('sentiment'))
    sentiment_counts = {item['sentiment']: item['count'] for item in counts}
    
    # Get recent feedback
    recent_feedback = SurveyFeedback.objects.order_by('-created_at')[:50]
    
    return render(request, 'stats.html', {
        'total_feedback': total_feedback,
        'sentiment_counts': sentiment_counts,
        'recent_feedback': recent_feedback
    })

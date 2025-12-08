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
        survey.relationship_type = request.POST.get('relationship', '') # Correct field
        # We can store the text description if 'Other' or just rely on the type.
        # But wait, relationship_context was the old field. Let's start using relationship_type primarily.
        
        survey.energy_audit_answer = request.POST.get('energy_audit', '')
        survey.stress_profile_answer = request.POST.get('stress_profile', '')
        survey.glass_ceiling_answer = request.POST.get('glass_ceiling', '')
        survey.future_self_answer = request.POST.get('future_self', '')
        survey.final_thoughts = request.POST.get('final_thoughts', '')
        survey.is_completed = True
        survey.save()
        return render(request, 'thank_you.html', {'survey_uuid': survey.uuid})

    # 3. If GET, show the form (only if not completed)
    if survey.is_completed:
         return render(request, 'thank_you.html', {'survey_uuid': survey.uuid})
         
    return render(request, 'survey_form.html', {'survey': survey})

# --- NEW GEMINI FUNCTION ---
@login_required
def get_alternative_question(request, uuid):
    if request.method != 'POST':
         return JsonResponse({'error': 'Invalid request method'}, status=400)
         
    try:
        data = json.loads(request.body)
        question_type = data.get('question_type')
        relationship = data.get('relationship', 'acquaintance')
        
        survey = get_object_or_404(Survey, uuid=uuid)
        target_user = survey.user
        
        # Configure Gemini
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return JsonResponse({'error': 'API Key missing'}, status=500)
            
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Context for the specific question types to help AI generate a good alternative
        context_map = {
            'energy_audit': f"The original question asked about 'flow state' and competence vs genius.",
            'stress_profile': f"The original question asked about their 'stress character' or shadow side.",
            'glass_ceiling': f"The original question asked about a 'hard truth' or behavior limiting their potential.",
            'future_self': f"The original question asked to imagine them 3 years from now as a leader."
        }
        
        specific_context = context_map.get(question_type, "General leadership feedback.")
        
        prompt = f"""
        Objective: Generate a SINGLE, simple, open-ended interview question for a respondent who knows the subject as a "{relationship}".
        
        Constraint: The respondent clicked "I'm not sure" on a deep psychological question about "{question_type}".
        Context of original question: {specific_context}
        
        Task: Create a softer, broader, easier-to-answer alternative question that still gets at the same underlying insight but requires less specific observation.
        
        Example for 'Stress': 
        - Hard: "Who do they turn into when threatened?"
        - Easy: "When things get difficult at work, how do you typically see them react?"

        Output ONLY the text of the new question. No quotes, no intro.
        """
        
        response = model.generate_content(prompt)
        return JsonResponse({'question': response.text.strip()})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def run_ai_analysis(profile_id, prompt, api_key):
    import time
    try:
        # Re-fetch profile to avoid stale data (and ensure thread-safety)
        from .models import Profile
        profile = Profile.objects.get(id=profile_id)
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Stream response (standard practice for long gens)
        response_stream = model.generate_content(prompt, stream=True)
        
        full_text = ""
        for chunk in response_stream:
            if chunk.text:
                full_text += chunk.text
        
        profile.ai_summary = full_text
        profile.save()
        print(f"BACKGROUND DEBUG: Analysis saved for Profile {profile_id}")
        
    except Exception as e:
        print(f"BACKGROUND ERROR: {e}")
        try:
             from .models import Profile
             profile = Profile.objects.get(id=profile_id)
             profile.ai_summary = f"Error during analysis: {str(e)}. Please try again."
             profile.save()
        except:
            pass

@login_required
def profile_analysis_view(request):
    # 1. Gather ALL completed surveys for this user
    completed_surveys = Survey.objects.filter(user=request.user, is_completed=True)
    
    if not completed_surveys:
        return redirect('dashboard')
        
    # Aggregate text
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)

    text_data = ""
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

    # Check API Key
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        from django.contrib import messages
        messages.error(request, "Configuration Error: No Google API Key found.")
        return redirect('dashboard')

    # Construct Prompt
    prompt = f"""
    Role: You are an expert developmental psychologist and executive coach, fluent in the Enneagram, Internal Family Systems (IFS), The 6 Types of Working Genius, and Vertical Leadership Development.
    
    Input Data: You will receive 360-feedback from peers AND the user's own "10-Year Vision" from their onboarding.
    
    FEEDBACK DATA:
    {text_data}
    
    Objective: Synthesize the inputs into a high-impact "User Manual" for the subject. Do not summarize; interpret the data to reveal their operating system. Use "Radical Candor"—be direct, kind, and psychologically deep.
    
    Output Format:
    
    Return pure HTML code (no markdown backticks, no markdown syntax like **, #). structure it as follows:

    <div class="report-section">
        <h3>Section 1: Who You Are (The Operating System)</h3>
        <p><strong>Core Motivation:</strong> [Enneagram Insight]</p>
        <p><strong>Zone of Genius:</strong> [Working Genius Insight]</p>
    </div>

    <div class="report-section">
        <h3>Section 2: The Gap (Intent vs. Impact)</h3>
        <p><strong>The Protectors (IFS):</strong></p>
        <ul>
            <li>[Character Name]: [Description of behavior and cost]</li>
        </ul>
        <p><strong>The Blind Spot:</strong> [Vertical Development Insight]</p>
    </div>

    <div class="report-section">
        <h3>Section 3: The North Star</h3>
        <p>[Comparison of Self-Report vs Peer Feedback]</p>
        <p><strong>Vision of Maturity:</strong> [Description of them at Self-Transforming level]</p>
    </div>

    <div class="report-section">
        <h3>Section 4: The Manual (The Path Forward)</h3>
        <p><strong>The Daily Practice:</strong> [Specific Micro-habit]</p>
        
        <p><strong>The Media Stack:</strong></p>
        <ul>
            <li><strong>Read:</strong> [Book Title] - [Why]</li>
            <li><strong>Watch:</strong> [Movie/Show] - [Why]</li>
            <li><strong>Listen:</strong> [Podcast Episode] - [Why]</li>
        </ul>

        <p><strong>The Experience:</strong></p>
        <ul>
            <li>[Activity Recommendation]</li>
        </ul>
    </div>
    """

    # Set Status Marker
    profile.ai_summary = "__ANALYZING__"
    profile.save()

    # Launch Background Thread
    import threading
    t = threading.Thread(target=run_ai_analysis, args=(profile.id, prompt, api_key))
    t.start()
    
    from django.contrib import messages
    messages.success(request, "Analysis started! This may take 30-60 seconds. We'll update this page when it's ready.")

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
            model = genai.GenerativeModel('gemini-2.5-flash')
            
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

@login_required(login_url=None) # Actually this view is public, so login_required might be wrong if used as a decorator on the view itself without @login_required? 
# Wait, public_survey_view is for the public. It should NOT have @login_required.
# Let's check imports. public_survey_view does not have @login_required decorator in previous code.
# But I am replacing lines 411-431.

@login_required(login_url=None) # Keep or remove based on previous state, but fixing the logic below is key.
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

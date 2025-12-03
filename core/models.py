from django.db import models
from django.conf import settings
import uuid

class Survey(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='surveys')
    
    # Respondent Info
    respondent_name = models.CharField(max_length=255)
    respondent_email = models.EmailField()
    respondent_phone = models.CharField(max_length=50, blank=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Answers
    relationship_context = models.TextField(blank=True, verbose_name="How do you know them?")
    
    # 1. The Energy Audit
    energy_audit_answer = models.TextField(blank=True, verbose_name="The Energy Audit")
    
    # 2. The Stress Profile
    stress_profile_answer = models.TextField(blank=True, verbose_name="The Stress Profile")
    
    # 3. The Glass Ceiling
    glass_ceiling_answer = models.TextField(blank=True, verbose_name="The Glass Ceiling")
    
    # 4. The Future Self
    future_self_answer = models.TextField(blank=True, verbose_name="The Future Self")

    def __str__(self):
        return f"Invite to {self.respondent_name} ({self.user.username})"

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    ai_summary = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    # Onboarding / User Context
    onboarding_completed = models.BooleanField(default=False)
    
    # Part 1: Context
    current_role = models.CharField(max_length=255, blank=True)
    responsibilities = models.TextField(blank=True)
    family_context = models.TextField(blank=True)
    core_values = models.TextField(blank=True)
    
    # Part 2: 10-Year Vision
    vision_perfect_tuesday = models.TextField(blank=True, verbose_name="The Perfect Tuesday in 2035")
    vision_toast_test = models.TextField(blank=True, verbose_name="The Toast Test")
    vision_anti_vision = models.TextField(blank=True, verbose_name="The Anti-Vision")

    # Part 3: Internal Operating System
    stress_response = models.TextField(blank=True, verbose_name="Pressure Reflex")
    internal_anchor = models.TextField(blank=True, verbose_name="The Anchor")
    
    # Deprecated / Replaced (Keep for now or remove if fresh start? User just wiped DB so we can keep or repurpose)
    career_goal = models.TextField(blank=True) # Can be deprecated or kept as summary

    def __str__(self):
        return f"Profile for {self.user.username}"

# Signal to create Profile automatically when User is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
import uuid
from django.db import models
from django.conf import settings


class ChatSession(models.Model):
    """
    A single conversation. Tenant-scoped via `company`.
    `company=None` means system-level (RonoSystems public site).
    """
    SCOPE_CHOICES = [
        ('system', 'System'),
        ('company', 'Company'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='ai_chat_sessions',
        help_text='Null = system-level chat (public site).',
    )
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='system')
    business_type_slug = models.CharField(max_length=50, blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ai_chat_sessions',
    )
    session_key = models.CharField(max_length=64, blank=True, db_index=True)

    title = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['company', 'user']),
            models.Index(fields=['session_key']),
        ]


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('system', 'System'),
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('tool', 'Tool'),
    ]

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    tool_name = models.CharField(max_length=100, blank=True)
    tool_payload = models.JSONField(null=True, blank=True)
    tokens_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class ChatFeedback(models.Model):
    """Thumbs up/down on assistant replies — useful for tuning prompts."""
    message = models.OneToOneField(
        ChatMessage, on_delete=models.CASCADE, related_name='feedback'
    )
    rating = models.SmallIntegerField(choices=[(1, 'Up'), (-1, 'Down')])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
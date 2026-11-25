import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Thin wrapper over your configured provider (Groq by default).
    Returns a dict: {'content': str, 'tool_calls': list, 'tokens': int}
    """

    def __init__(self):
        self.provider = settings.AI_PROVIDER
        if self.provider == 'groq':
            from groq import Groq
            self.client = Groq(api_key=settings.GROQ_API_KEY)
            self.model = settings.GROQ_MODEL
        elif self.provider == 'openai':
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = settings.OPENAI_MODEL
        else:
            raise ValueError(f"Unsupported AI_PROVIDER: {self.provider}")

    def chat(self, messages, tools=None, temperature=0.4):
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        if tools:
            kwargs['tools'] = tools
            kwargs['tool_choice'] = 'auto'

        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            logger.exception("LLM call failed")
            return {'content': "Sorry, I hit a snag. Please try again.",
                    'tool_calls': [], 'tokens': 0}

        choice = resp.choices[0].message
        return {
            'content': choice.content or '',
            'tool_calls': getattr(choice, 'tool_calls', []) or [],
            'tokens': resp.usage.total_tokens if resp.usage else 0,
        }
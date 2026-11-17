import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render, get_object_or_404
from django.utils.text import Truncator

from .models import ChatSession, ChatMessage
from .services.llm_client import LLMClient
from .services.context_builder import build_context
from .services.tools import build_tool_schemas, dispatch_tool


MAX_HISTORY = 20  # messages kept in the prompt context


def chatbot_page(request):
    """Renders the floating chat widget / dedicated page."""
    ctx = build_context(request)
    session = _get_or_create_session(request, ctx)
    return render(request, 'ai_chatbot/chat.html', {
        'session': session,
        'scope': ctx['scope'],
        'business_type_slug': ctx['business_type_slug'],
    })


@require_POST
def send_message(request):
    """POST {message: str} → {reply: str, session_id: uuid}"""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_text = (payload.get('message') or '').strip()
    if not user_text:
        return JsonResponse({'error': 'Empty message'}, status=400)

    ctx = build_context(request)
    session = _get_or_create_session(request, ctx)

    # Persist the user message
    ChatMessage.objects.create(session=session, role='user', content=user_text)

    # Build message history for the LLM
    history = list(
        session.messages.order_by('-created_at')[:MAX_HISTORY]
    )[::-1]

    messages = [{'role': 'system', 'content': ctx['system_prompt']}]
    for m in history:
        if m.role in ('user', 'assistant'):
            messages.append({'role': m.role, 'content': m.content})

    client = LLMClient()
    tools = build_tool_schemas(ctx['tool_whitelist'])

    # Agent loop: keep calling until no more tool calls
    total_tokens = 0
    for _ in range(4):  # max 4 tool rounds — prevents runaway
        result = client.chat(messages, tools=tools or None)
        total_tokens += result['tokens']

        if not result['tool_calls']:
            # Final text answer
            assistant_text = result['content'] or "I'm not sure how to answer that."
            ChatMessage.objects.create(
                session=session, role='assistant',
                content=assistant_text, tokens_used=total_tokens,
            )
            return JsonResponse({
                'reply': assistant_text,
                'session_id': str(session.id),
            })

        # Append assistant's tool-call turn
        messages.append({
            'role': 'assistant',
            'content': result['content'] or '',
            'tool_calls': [
                {
                    'id': tc.id,
                    'type': 'function',
                    'function': {
                        'name': tc.function.name,
                        'arguments': tc.function.arguments,
                    },
                } for tc in result['tool_calls']
            ],
        })

        # Execute each tool and append its result
        for tc in result['tool_calls']:
            try:
                args = json.loads(tc.function.arguments or '{}')
            except json.JSONDecodeError:
                args = {}
            tool_result = dispatch_tool(
                tc.function.name, args,
                company=ctx['company'], user=request.user,
            )
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.id,
                'content': json.dumps(tool_result, default=str),
            })

    # Safety fallback if the loop exhausted
    fallback = "I'm having trouble answering that — please rephrase or contact support."
    ChatMessage.objects.create(session=session, role='assistant', content=fallback)
    return JsonResponse({'reply': fallback, 'session_id': str(session.id)})


# --- helpers ----------------------------------------------------------------
def _get_or_create_session(request, ctx):
    if not request.session.session_key:
        request.session.create()
    sk = request.session.session_key

    session, _ = ChatSession.objects.get_or_create(
        session_key=sk,
        company=ctx['company'],
        user=request.user if request.user.is_authenticated else None,
        defaults={
            'scope': ctx['scope'],
            'business_type_slug': ctx['business_type_slug'],
            'is_active': True,
        },
    )
    return session
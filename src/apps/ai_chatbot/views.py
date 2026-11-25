import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import render

from .models import ChatSession, ChatMessage
from .services.llm_client import LLMClient
from .services.context_builder import build_context
from .services.tools import build_tool_schemas, dispatch_tool

MAX_HISTORY = 20

def chatbot_page(request):
    ctx = build_context(request)
    session = _get_or_create_session(request, ctx)
    return render(request, 'ai_chatbot/chat.html', {
        'session': session,
        'scope': ctx['scope'],
        'business_type_slug': ctx['business_type_slug'],
    })


@require_POST
def send_message(request):
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_text = (payload.get('message') or '').strip()
    current_domain = payload.get('current_domain', '').strip()

    if not user_text:
        return JsonResponse({'error': 'Empty message'}, status=400)

    ctx = build_context(request)
    session = _get_or_create_session(request, ctx)
    company = ctx['company']

    # Persist the user message
    ChatMessage.objects.create(session=session, role='user', content=user_text)

    # Build message history
    history = list(session.messages.order_by('-created_at')[:MAX_HISTORY])[::-1]
    messages = [{'role': 'system', 'content': ctx['system_prompt']}]

    # -----------------------------------------------------------------
    # DOMAIN INJECTION
    # -----------------------------------------------------------------
    if current_domain:
        messages[0]['content'] += (
            f"\n\nIMPORTANT CONTEXT: The current website domain is {current_domain}. "
            f"When you use the `get_system_url` tool, you MUST format the final link as an absolute URL: "
            f"{current_domain}[URL_PATH]."
        )

    # -----------------------------------------------------------------
    # DYNAMIC BRANCH INJECTION (PROACTIVE DB CHECK)
    # -----------------------------------------------------------------
    # If the user mentions "branch", "location", "store", etc., 
    # fetch the DB right now and inject it as a system fact.
    branch_keywords = ['branch', 'branches', 'location', 'locations', 'nairobi', 'eldoret', 'store', 'shop']
    if any(kw in user_text.lower() for kw in branch_keywords) and company:
        from apps.companies.models import Branch
        branches = Branch.objects.filter(company=company, is_active=True)
        
        if branches.exists():
            branch_data = "SYSTEM DIRECTIVE: The user asked about branches. Here are the branches from the database. Quote this exact data:\n"
            for b in branches:
                main_tag = " (MAIN)" if getattr(b, 'is_main_branch', False) else ""
                branch_data += f"- {b.name}{main_tag} | Location: {getattr(b, 'location', 'N/A')} | Phone: {getattr(b, 'phone', 'N/A')}\n"
            
            # Inject this as a system message right before the user's prompt
            messages.append({'role': 'system', 'content': branch_data})
    
    # -----------------------------------------------------------------

    for m in history:
        if m.role in ('user', 'assistant'):
            messages.append({'role': m.role, 'content': m.content})

    client = LLMClient()
    tools = build_tool_schemas(ctx['tool_whitelist'])

    total_tokens = 0
    for _ in range(4):
        result = client.chat(messages, tools=tools or None)
        total_tokens += result['tokens']

        if not result['tool_calls']:
            assistant_text = result['content'] or "I'm not sure how to answer that."
            ChatMessage.objects.create(
                session=session, role='assistant',
                content=assistant_text, tokens_used=total_tokens,
            )
            return JsonResponse({'reply': assistant_text, 'session_id': str(session.id)})

        messages.append({
            'role': 'assistant',
            'content': result['content'] or '',
            'tool_calls': [
                {
                    'id': tc.id,
                    'type': 'function',
                    'function': {'name': tc.function.name, 'arguments': tc.function.arguments},
                } for tc in result['tool_calls']
            ],
        })

        for tc in result['tool_calls']:
            try:
                args = json.loads(tc.function.arguments or '{}')
            except json.JSONDecodeError:
                args = {}
            tool_result = dispatch_tool(tc.function.name, args, company=company, user=request.user)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.id,
                'content': json.dumps(tool_result, default=str),
            })

    fallback = "I'm having trouble answering that — please rephrase."
    ChatMessage.objects.create(session=session, role='assistant', content=fallback)
    return JsonResponse({'reply': fallback, 'session_id': str(session.id)})


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
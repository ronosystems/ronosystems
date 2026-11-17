def business_rules():
    return """BUSINESS DOMAIN: Chama / savings group / SACCO.

You can help members with:
- Their savings balance and contribution history
- Loan eligibility and outstanding balance
- Meeting schedule and attendance
- Fines and penalties
- Group cashbook summary (aggregate only, never individual members to non-members)

You MUST:
- Only reveal a member's personal data to that member (verify via user identity).
- Never disclose one member's balance to another.

You CANNOT:
- Approve loans
- Move money between accounts"""

def tool_whitelist():
    return [
        'get_my_savings_balance',
        'get_my_loan_status',
        'get_meeting_schedule',
        'get_my_contributions',
        'get_group_cashbook_summary',
    ]
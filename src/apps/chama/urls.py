from django.urls import path
from . import views
from . import members_views
from . import internal_loans_views
from . import external_loans_views

app_name = 'chama'


urlpatterns = [
    # ============================================================
    # DASHBOARD
    # ============================================================
    path('', views.dashboard, name='dashboard'),

    # ============================================================
    # MEMBER SECTION — delegated to members_views
    # ============================================================
    # Membership Types
    path('membership-types/', members_views.membership_type_list, name='membership_type_list'),
    path('membership-types/create/', members_views.membership_type_create, name='membership_type_create'),
    path('membership-types/<int:pk>/edit/', members_views.membership_type_edit, name='membership_type_edit'),
    path('membership-types/<int:pk>/delete/', members_views.membership_type_delete, name='membership_type_delete'),
       
    # Members
    path('members/', members_views.member_list, name='member_list'),
    path('members/create/', members_views.member_create, name='member_create'),
    path('members/<int:pk>/', members_views.member_detail, name='member_detail'),
    path('members/<int:pk>/edit/', members_views.member_edit, name='member_edit'),
    path('members/<int:pk>/delete/', members_views.member_delete, name='member_delete'),
    path('members/<int:pk>/toggle-status/', members_views.member_toggle_status, name='member_toggle_status'),


    # Registration
    path('registrations/', members_views.registration_list, name='registration_list'),
    path('registrations/<int:pk>/approve/', members_views.registration_approve, name='registration_approve'),
    path('registrations/<int:pk>/reject/', members_views.registration_reject, name='registration_reject'),

    # Member Loan History / Limit (AJAX)
    path('members/<int:member_pk>/loan-history/', members_views.member_loan_history, name='member_loan_history'),
    path('members/<int:member_pk>/loan-limit/', members_views.member_loan_limit_adjust, name='member_loan_limit_adjust'),

    # ============================================================
    # COMMITTEES
    # ============================================================
    path('committees/', views.committee_list, name='committee_list'),
    path('committees/create/', views.committee_create, name='committee_create'),
    path('committees/<int:pk>/', views.committee_detail, name='committee_detail'),
    path('committees/<int:pk>/members/add/', views.committee_member_add, name='committee_member_add'),
    path('committees/<int:pk>/members/<int:member_pk>/remove/', views.committee_member_remove, name='committee_member_remove'),

    # ============================================================
    # PROJECTS / MEETINGS / ATTENDANCE / ANNOUNCEMENTS
    # ============================================================
    path('projects/', views.project_list, name='project_list'),
    path('projects/create/', views.project_create, name='project_create'),

    path('meetings/', views.meeting_list, name='meeting_list'),
    path('meetings/create/', views.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/', views.meeting_detail, name='meeting_detail'),
    path('meetings/<int:pk>/edit/', views.meeting_edit, name='meeting_edit'),

    path('attendance/', views.attendance_list, name='attendance_list'),
    path('meetings/<int:meeting_pk>/attendance/create/', views.attendance_create, name='attendance_create'),

    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/create/', views.announcement_create, name='announcement_create'),

    # ============================================================
    # CONTRIBUTIONS
    # ============================================================
    path('contributions/', views.contribution_list, name='contribution_list'),
    path('contributions/create/', views.contribution_create, name='contribution_create'),
    path('contributions/<int:pk>/edit/', views.contribution_edit, name='contribution_edit'),
    path('contributions/<int:pk>/delete/', views.contribution_delete, name='contribution_delete'),
    path('contributions/pay/', views.contribution_pay, name='contribution_pay'),
    path('contributions/pay/self/', views.contribution_pay_self_service, name='contribution_pay_self_service'),

    # ============================================================
    # SAVINGS
    # ============================================================
    path('savings/', views.savings_list, name='savings_list'),
    path('savings/create/', views.savings_create, name='savings_create'),
    path('savings/<int:pk>/edit/', views.savings_edit, name='savings_edit'),
    path('savings/<int:pk>/delete/', views.savings_delete, name='savings_delete'),

    # ============================================================
    # FINES
    # ============================================================
    path('fines/', views.fine_list, name='fine_list'),
    path('fines/create/', views.fine_create, name='fine_create'),
    path('fines/<int:pk>/edit/', views.fine_edit, name='fine_edit'),
    path('fines/<int:pk>/delete/', views.fine_delete, name='fine_delete'),
    path('fines/<int:pk>/pay/', views.fine_pay, name='fine_pay'),

    # ============================================================
    # LOAN TYPES (internal module)
    # ============================================================
    path('loan-types/', internal_loans_views.loan_type_list, name='loan_type_list'),
    path('loan-types/create/', internal_loans_views.loan_type_create, name='loan_type_create'),
    path('loan-types/<int:pk>/edit/', internal_loans_views.loan_type_edit, name='loan_type_edit'),
    path('loan-types/<int:pk>/delete/', internal_loans_views.loan_type_delete, name='loan_type_delete'),

    # ============================================================
    # INTERNAL LOANS
    # ============================================================
    path('loans/', internal_loans_views.loan_list, name='loan_list'),
    path('loans/create/', internal_loans_views.loan_create, name='loan_create'),
    path('loans/<int:pk>/', internal_loans_views.loan_detail, name='loan_detail'),
    path('loans/<int:pk>/edit/', internal_loans_views.loan_edit, name='loan_edit'),
    path('loans/<int:pk>/delete/', internal_loans_views.loan_delete, name='loan_delete'),
    path('loans/<int:pk>/approve/', internal_loans_views.loan_approve, name='loan_approve'),
    path('loans/<int:pk>/reject/', internal_loans_views.loan_reject, name='loan_reject'),
    path('loans/<int:pk>/disburse/', internal_loans_views.loan_disburse, name='loan_disburse'),
    path('loan-limits/', internal_loans_views.internal_loan_limits, name='internal_loan_limits'),
    path('internal-borrowers/', internal_loans_views.member_loan_list, name='member_loan_list'),

    # ============================================================
    # INTERNAL LOAN REPAYMENTS
    # ============================================================
    path('loans/<int:pk>/repayment/create/', internal_loans_views.loan_repayment_create, name='loan_repayment_create'),
    path('loans/<int:loan_pk>/repayment/pay/', internal_loans_views.loan_repayment_pay, name='loan_repayment_pay'),
    path('loan-repayments/', internal_loans_views.loan_repayment_list, name='loan_repayment_list'),
    
    # ============================================================
    # GUESTS — CRUD
    # ============================================================
    path('guests/', external_loans_views.guest_list, name='guest_list'),
    path('guests/create/', external_loans_views.guest_create, name='guest_create'),
    path('guests/<int:pk>/', external_loans_views.guest_detail, name='guest_detail'),
    path('guests/<int:pk>/edit/', external_loans_views.guest_edit, name='guest_edit'),
    path('guests/<int:pk>/delete/', external_loans_views.guest_delete, name='guest_delete'),

    # ============================================================
    # EXTERNAL LOANS — CRUD
    # ============================================================
    path('external-loans/', external_loans_views.external_loan_list, name='external_loan_list'),
    path('external-loans/<int:pk>/', external_loans_views.external_loan_detail, name='external_loan_detail'),
    path('external-loans/<int:pk>/edit/', external_loans_views.loan_edit_external, name='loan_edit_external'),
    path('external-loans/<int:pk>/delete/', external_loans_views.loan_delete_external, name='loan_delete_external'),
    path('external-loans/<int:pk>/approve/', external_loans_views.loan_approve_external, name='loan_approve_external'),
    path('external-loans/<int:pk>/reject/', external_loans_views.loan_reject_external, name='loan_reject_external'),
    path('external-loans/<int:pk>/disburse/', external_loans_views.loan_disburse_external, name='loan_disburse_external'),
    path('external-loans/guests/<int:guest_pk>/create/', external_loans_views.loan_create_external, name='loan_create_external'),
    path('external-loans/limits/', external_loans_views.external_loan_limits, name='external_loan_limits'),

    # ============================================================
    # EXTERNAL LOAN REPAYMENTS
    # ============================================================
    path('external-loans/<int:loan_pk>/repayment/create/', external_loans_views.external_loan_repayment_create, name='external_loan_repayment_create'),
    path('external-loans/<int:loan_pk>/repayment/pay/', external_loans_views.external_loan_repayment_pay, name='external_loan_repayment_pay'),
    path('external-loan-repayments/', external_loans_views.external_loan_repayment_list, name='external_loan_repayment_list'),

    # ============================================================
    # ACCOUNTS & TRANSACTIONS
    # ============================================================
    path('accounts/', views.account_list, name='account_list'),
    path('accounts/create/', views.account_create, name='account_create'),
    path('accounts/<int:pk>/edit/', views.account_edit, name='account_edit'),
    path('accounts/<int:pk>/delete/', views.account_delete, name='account_delete'),
    path('accounts/transfer/', views.account_transfer, name='account_transfer'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('expenses/', views.expense_list, name='expense_list'),

    # ============================================================
    # TREASURY — TRANSACTIONS
    # ============================================================
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:pk>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),

    # ============================================================
    # TREASURY — EXPENSES
    # ============================================================
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
]
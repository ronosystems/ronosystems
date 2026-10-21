from django.urls import path

from . import views

app_name = 'chama'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Members
    path('members/', views.member_list, name='member_list'),
    path('members/create/', views.member_create, name='member_create'),
    path('members/<int:pk>/edit/', views.member_edit, name='member_edit'),
    path('members/<int:pk>/', views.member_detail, name='member_detail'),
    path('membership-types/', views.membership_type_list, name='membership_type_list'),
    path('membership-types/create/', views.membership_type_create, name='membership_type_create'),
    path('membership-types/<int:pk>/edit/', views.membership_type_edit, name='membership_type_edit'),
    path('membership-types/<int:pk>/delete/', views.membership_type_delete, name='membership_type_delete'),
    path('membership-types/', views.membership_type_list, name='membership_type_list'),
    path('registrations/', views.registration_list, name='registration_list'),
    path('registrations/', views.registration_list, name='registration_list'),
    path('registrations/<int:pk>/approve/', views.registration_approve, name='registration_approve'),
    path('registrations/<int:pk>/reject/', views.registration_reject, name='registration_reject'),

    # Savings
    path('savings/', views.savings_list, name='savings_list'),
    path('savings/create/', views.savings_create, name='savings_create'),
    path('savings/<int:pk>/edit/', views.savings_edit, name='savings_edit'),
    path('savings/<int:pk>/delete/', views.savings_delete, name='savings_delete'),

    # Contributions
    path('contributions/', views.contribution_list, name='contribution_list'),
    path('contributions/<int:pk>/pay/', views.contribution_pay, name='contribution_pay'),
    path('contributions/create/', views.contribution_create, name='contribution_create'),
    path('contributions/<int:pk>/edit/', views.contribution_edit, name='contribution_edit'),
    path('contributions/<int:pk>/delete/', views.contribution_delete, name='contribution_delete'),

    # Fines
    path('fines/', views.fine_list, name='fine_list'),
    path('fines/<int:pk>/pay/', views.fine_pay, name='fine_pay'),
    path('fines/create/', views.fine_create, name='fine_create'),
    path('fines/<int:pk>/edit/', views.fine_edit, name='fine_edit'),
    path('fines/<int:pk>/delete/', views.fine_delete, name='fine_delete'),

    # Loan Types
    path('loan-types/', views.loan_type_list, name='loan_type_list'),
    path('loan-types/create/', views.loan_type_create, name='loan_type_create'),
    path('loan-types/<int:pk>/edit/', views.loan_type_edit, name='loan_type_edit'),
    path('loan-types/<int:pk>/delete/', views.loan_type_delete, name='loan_type_delete'),

    # Loans
    path('loans/', views.loan_list, name='loan_list'),
    path('loans/create/', views.loan_create, name='loan_create'),
    path('loans/<int:pk>/', views.loan_detail, name='loan_detail'),
    path('loans/<int:pk>/edit/', views.loan_edit, name='loan_edit'),
    path('loans/<int:pk>/delete/', views.loan_delete, name='loan_delete'),
    path('loans/<int:pk>/approve/', views.loan_approve, name='loan_approve'),
    path('loans/<int:pk>/reject/', views.loan_reject, name='loan_reject'),
    path('loans/<int:pk>/disburse/', views.loan_disburse, name='loan_disburse'),
    path('loans/<int:loan_pk>/pay/', views.loan_repayment_pay, name='loan_repayment_pay'),

    # Loan Repayments
    path('loan-repayments/', views.loan_repayment_list, name='loan_repayment_list'),
    path('loans/<int:loan_pk>/repay/', views.loan_repayment_create, name='loan_repayment_create'),

    # Transactions
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.transaction_create, name='transaction_create'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.expense_create, name='expense_create'),

    # Accounts
    path('accounts/', views.account_list, name='account_list'),
    path('accounts/create/', views.account_create, name='account_create'),

    # Projects
    path('projects/', views.project_list, name='project_list'),
    path('projects/create/', views.project_create, name='project_create'),

    # Meetings
    path('meetings/', views.meeting_list, name='meeting_list'),
    path('meetings/create/', views.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/', views.meeting_detail, name='meeting_detail'),
    path('meetings/<int:pk>/edit/', views.meeting_edit, name='meeting_edit'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('meetings/<int:meeting_pk>/attendance/create/', views.attendance_create, name='attendance_create'),

    # Announcements
    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/create/', views.announcement_create, name='announcement_create'),


    # Roles
    path('roles/', views.role_list, name='role_list'),

    # Committees
    path('committees/', views.committee_list, name='committee_list'),
    path('committees/create/', views.committee_create, name='committee_create'),
    path('committees/<int:pk>/', views.committee_detail, name='committee_detail'),
    path('committees/<int:pk>/members/add/', views.committee_member_add, name='committee_member_add'),
    path('committees/<int:pk>/members/<int:member_pk>/remove/', views.committee_member_remove, name='committee_member_remove'),

    # Reports
    path('reports/', views.reports, name='reports'),
]
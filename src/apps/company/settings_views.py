from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings as django_settings
from django.http import JsonResponse
import os
import json

from apps.companies.models import Company

@login_required
def settings_dashboard(request):
    """Company settings dashboard"""
    company = request.user.company
    
    # Get current settings
    settings_data = get_company_settings(company)
    
    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
    }
    return render(request, 'company/settings/dashboard.html', context)

@login_required
def settings_company(request):
    """Company settings - update company info and logo"""
    company = request.user.company
    
    if request.method == 'POST':
        try:
            # Update company info
            company_name = request.POST.get('company_name')
            company_email = request.POST.get('company_email')
            company_phone = request.POST.get('company_phone')
            company_address = request.POST.get('company_address')
            
            if company_name:
                company.name = company_name
            if company_email:
                company.email = company_email
            if company_phone:
                company.phone = company_phone
            if company_address:
                company.address = company_address
            
            # Handle logo upload
            if request.FILES.get('company_logo'):
                logo = request.FILES['company_logo']
                # Validate file type
                valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg']
                ext = os.path.splitext(logo.name)[1].lower()
                if ext in valid_extensions:
                    # Delete old logo if exists
                    if company.logo:
                        old_logo_path = os.path.join(django_settings.MEDIA_ROOT, str(company.logo))
                        if os.path.exists(old_logo_path):
                            os.remove(old_logo_path)
                    
                    # Save new logo
                    company.logo = logo
                else:
                    messages.error(request, 'Invalid file format. Please upload JPG, PNG, GIF, or SVG.')
                    return redirect('company-settings-company')
            
            # Handle logo removal
            if request.POST.get('remove_logo') == 'true':
                if company.logo:
                    old_logo_path = os.path.join(django_settings.MEDIA_ROOT, str(company.logo))
                    if os.path.exists(old_logo_path):
                        os.remove(old_logo_path)
                    company.logo = None
                    company.save()
                    messages.success(request, 'Company logo removed successfully!')
                    return redirect('company-settings-company')
            
            company.save()
            
            # Save settings to JSON
            save_company_settings(company, request.POST)
            
            messages.success(request, 'Company settings updated successfully!')
            return redirect('company-settings-company')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    settings_data = get_company_settings(company)
    
    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'company',
    }
    return render(request, 'company/settings/company.html', context)

@login_required
def settings_payment(request):
    """Payment settings"""
    company = request.user.company
    
    if request.method == 'POST':
        try:
            # Save payment settings
            payment_settings = {
                'currency': request.POST.get('currency', 'KES'),
                'currency_symbol': request.POST.get('currency_symbol', 'KSh'),
                'decimal_places': int(request.POST.get('decimal_places', 2)),
                'payment_methods': request.POST.getlist('payment_methods'),
                'enable_discount': request.POST.get('enable_discount') == 'on',
                'enable_tax': request.POST.get('enable_tax') == 'on',
                'default_tax_rate': float(request.POST.get('default_tax_rate', 0)),
                'enable_partial_payment': request.POST.get('enable_partial_payment') == 'on',
                'enable_credit': request.POST.get('enable_credit') == 'on',
                'credit_limit': float(request.POST.get('credit_limit', 0)),
                'payment_terms': int(request.POST.get('payment_terms', 30)),
                'enable_mpesa': request.POST.get('enable_mpesa') == 'on',
                'mpesa_paybill': request.POST.get('mpesa_paybill', ''),
                'mpesa_till': request.POST.get('mpesa_till', ''),
                'enable_bank': request.POST.get('enable_bank') == 'on',
                'bank_name': request.POST.get('bank_name', ''),
                'bank_account': request.POST.get('bank_account', ''),
                'bank_branch': request.POST.get('bank_branch', ''),
            }
            
            save_company_settings(company, payment_settings, 'payment')
            messages.success(request, 'Payment settings updated successfully!')
            return redirect('company-settings-payment')
            
        except Exception as e:
            messages.error(request, f'Error updating payment settings: {str(e)}')
    
    settings_data = get_company_settings(company)
    
    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'payment',
        'payment_methods_choices': [
            ('cash', 'Cash'),
            ('m-pesa', 'M-Pesa'),
            ('bank', 'Bank Transfer'),
            ('card', 'Card'),
            ('credit', 'Credit'),
        ],
    }
    return render(request, 'company/settings/payment.html', context)

@login_required
def settings_receipt(request):
    """Receipt settings"""
    company = request.user.company
    
    if request.method == 'POST':
        try:
            # Save receipt settings
            receipt_settings = {
                'receipt_header': request.POST.get('receipt_header', ''),
                'receipt_footer': request.POST.get('receipt_footer', ''),
                'receipt_format': request.POST.get('receipt_format', 'standard'),
                'show_logo': request.POST.get('show_logo') == 'on',
                'show_company_details': request.POST.get('show_company_details') == 'on',
                'show_customer_details': request.POST.get('show_customer_details') == 'on',
                'show_items': request.POST.get('show_items') == 'on',
                'show_totals': request.POST.get('show_totals') == 'on',
                'show_payment': request.POST.get('show_payment') == 'on',
                'show_signature': request.POST.get('show_signature') == 'on',
                'receipt_title': request.POST.get('receipt_title', 'RECEIPT'),
                'thank_you_message': request.POST.get('thank_you_message', 'Thank you for your business!'),
                'include_barcode': request.POST.get('include_barcode') == 'on',
                'print_copies': int(request.POST.get('print_copies', 1)),
                'auto_print': request.POST.get('auto_print') == 'on',
                'receipt_font_size': request.POST.get('receipt_font_size', '14'),
                'receipt_width': request.POST.get('receipt_width', '80'),
                'custom_css': request.POST.get('custom_css', ''),
            }
            
            save_company_settings(company, receipt_settings, 'receipt')
            messages.success(request, 'Receipt settings updated successfully!')
            return redirect('company-settings-receipt')
            
        except Exception as e:
            messages.error(request, f'Error updating receipt settings: {str(e)}')
    
    settings_data = get_company_settings(company)
    
    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'receipt',
        'receipt_formats': [
            ('standard', 'Standard'),
            ('mini', 'Mini Receipt'),
            ('detailed', 'Detailed'),
            ('invoice', 'Invoice Style'),
        ],
    }
    return render(request, 'company/settings/receipt.html', context)

@login_required
def settings_preview_receipt(request):
    """Preview receipt"""
    company = request.user.company
    settings_data = get_company_settings(company)
    
    # Sample receipt data
    receipt_data = {
        'receipt_number': 'RCP-2026-0001',
        'date': '2026-08-27 14:30',
        'customer': 'John Doe',
        'customer_phone': '+254712345678',
        'items': [
            {'name': 'Samsung Galaxy S24', 'qty': 1, 'price': 65000, 'total': 65000},
            {'name': 'Phone Case', 'qty': 2, 'price': 500, 'total': 1000},
            {'name': 'Screen Protector', 'qty': 1, 'price': 300, 'total': 300},
        ],
        'subtotal': 66300,
        'discount': 0,
        'tax': 0,
        'total': 66300,
        'payment_method': 'M-Pesa',
        'payment_status': 'Paid',
        'cashier': 'Admin',
    }
    
    context = {
        'company': company,
        'settings': settings_data,
        'receipt': receipt_data,
    }
    return render(request, 'company/settings/receipt_preview.html', context)

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_company_settings(company):
    """Get company settings from JSON or defaults"""
    default_settings = {
        'company': {
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
        },
        'payment': {
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
            'payment_methods': ['cash', 'm-pesa'],
            'enable_discount': True,
            'enable_tax': False,
            'default_tax_rate': 0,
            'enable_partial_payment': False,
            'enable_credit': False,
            'credit_limit': 0,
            'payment_terms': 30,
            'enable_mpesa': True,
            'mpesa_paybill': '',
            'mpesa_till': '',
            'enable_bank': False,
            'bank_name': '',
            'bank_account': '',
            'bank_branch': '',
        },
        'receipt': {
            'receipt_header': '',
            'receipt_footer': '',
            'receipt_format': 'standard',
            'show_logo': True,
            'show_company_details': True,
            'show_customer_details': True,
            'show_items': True,
            'show_totals': True,
            'show_payment': True,
            'show_signature': True,
            'receipt_title': 'RECEIPT',
            'thank_you_message': 'Thank you for your business!',
            'include_barcode': False,
            'print_copies': 1,
            'auto_print': False,
            'receipt_font_size': '14',
            'receipt_width': '80',
            'custom_css': '',
        }
    }
    
    try:
        if company.company_settings:  # Use company_settings instead of settings
            saved_settings = json.loads(company.company_settings)
            # Merge with defaults
            for section in default_settings:
                if section in saved_settings:
                    default_settings[section].update(saved_settings[section])
    except:
        pass
    
    return default_settings

def save_company_settings(company, settings_data, section=None):
    """Save company settings to JSON"""
    try:
        # Get existing settings
        existing = {}
        if company.company_settings:  # Use company_settings instead of settings
            existing = json.loads(company.company_settings)
        
        if section:
            # Update specific section
            existing[section] = settings_data
        else:
            # Update general company settings
            if 'company' not in existing:
                existing['company'] = {}
            existing['company'].update(settings_data)
        
        company.company_settings = json.dumps(existing)  # Use company_settings
        company.save()
    except Exception as e:
        raise e
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth import logout, get_user_model, update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse_lazy
from django.conf import settings
from decimal import Decimal  # 👈 IMPORTED HERE
from apps.companies.models import Company
from apps.chama.models import Loan, LoanType, Guest 
from .models import Customer
import time
import cloudinary
import cloudinary.uploader

# Initialize User model
User = get_user_model()


def _cloudinary_configure():
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def coming_soon(request, page_name):
    """A generic placeholder page for features that are not yet built."""
    title = page_name.replace('_', ' ').title()
    return render(request, 'customers/coming_soon.html', {'page_title': title})


def customer_register(request):
    company_id = request.GET.get('company_id')
    if not company_id:
        messages.error(request, "Invalid company registration link.")
        return redirect('home')
        
    company = get_object_or_404(Company, id=company_id, is_active=True)

    referer = request.META.get('HTTP_REFERER', '')
    join_action = "join the Chama" if '/chama/' in referer else "start shopping"

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        pin = request.POST.get('pin', '').strip()
        confirm_pin = request.POST.get('confirm_pin', '').strip()

        if not full_name or not phone_number or not pin:
            messages.error(request, "Name, Phone Number, and PIN are required.")
        elif len(pin) < 4 or len(pin) > 10:
            messages.error(request, "PIN must be between 4 and 10 digits.")
        elif pin != confirm_pin:
            messages.error(request, "PINs do not match.")
        else:
            try:
                with transaction.atomic():
                    user, user_created = User.objects.get_or_create(
                        username=phone_number,
                        defaults={
                            'email': email,
                            'first_name': full_name.split()[0] if full_name else '',
                            'role': 'customer',
                        }
                    )

                    if user_created:
                        user.set_password(pin)
                        user.save()

                    customer, created = Customer.objects.get_or_create(
                        company=company,
                        phone_number=phone_number,
                        defaults={
                            'full_name': full_name,
                            'email': email,
                            'user': user
                        }
                    )
                    
                    if not created:
                        messages.warning(request, f"You are already registered with {company.display_name}.")
                    else:
                        messages.success(
                            request, 
                            f"Welcome {full_name}! You can now log in using your Phone Number ({phone_number}) and your PIN."
                        )
                    
                    return redirect('customers:login')
                    
            except Exception as e:
                messages.error(request, f"Registration failed: {str(e)}")

    return render(request, 'customers/customer_register.html', {
        'company': company,
        'join_action': join_action
    })


def registration_success(request, public_id):
    """A simple thank you page after registration."""
    customer = get_object_or_404(Customer, public_id=public_id)
    return render(request, 'customers/registration_success.html', {'customer': customer})


class CustomerLoginView(LoginView):
    template_name = 'customers/customer_login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('customers:dashboard') 


def customer_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('customers:login')


@login_required(login_url='customers:login')
def customer_profile(request):
    try:
        customer = request.user.customer_profile
    except AttributeError:
        messages.error(request, "You do not have a customer profile set up.")
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_details':
            customer.full_name = request.POST.get('full_name', customer.full_name)
            customer.national_id = request.POST.get('national_id', customer.national_id)
            customer.phone_number = request.POST.get('phone_number', customer.phone_number)
            customer.email = request.POST.get('email', customer.email)
            customer.location = request.POST.get('location', customer.location)
            
            customer.next_of_kin_name = request.POST.get('next_of_kin_name', customer.next_of_kin_name)
            customer.next_of_kin_phone = request.POST.get('next_of_kin_phone', customer.next_of_kin_phone)
            
            customer.save()
            messages.success(request, "Profile details updated successfully!")
            return redirect('customers:profile')
            
        elif action == 'upload_kyc':
            _cloudinary_configure()
            timestamp = int(time.time())
            
            def upload_file(file_key, field_name, is_pdf=False):
                file_obj = request.FILES.get(file_key)
                if file_obj:
                    public_id = f"profiles/customer_{customer.id}_{field_name}_{timestamp}"
                    res_type = 'raw' if is_pdf else 'image'
                    result = cloudinary.uploader.upload(file_obj, public_id=public_id, resource_type=res_type)
                    setattr(customer, field_name, result.get('public_id'))

            upload_file('id_front', 'id_front')
            upload_file('id_back', 'id_back')
            upload_file('good_conduct', 'good_conduct', is_pdf=True)
            upload_file('kra_pin', 'kra_pin', is_pdf=True)
            upload_file('cv', 'cv', is_pdf=True)

            customer.save()
            messages.success(request, "KYC documents uploaded successfully!")
            return redirect('customers:profile')

    return render(request, 'customers/profile.html', {'customer': customer})


@login_required(login_url='customers:login')
def customer_dashboard(request):
    try:
        customer = request.user.customer_profile
    except AttributeError:
        messages.error(request, "You do not have a customer profile set up.")
        return redirect('home')

    if request.method == 'POST' and 'update_photo' in request.POST:
        profile_pic = request.FILES.get('profile_photo')
        
        if profile_pic:
            old_key = ''
            if customer.profile_photo:
                old_key = getattr(customer.profile_photo, 'name', '') or str(customer.profile_photo)
                old_key = old_key.strip().lstrip('/')
            
            try:
                _cloudinary_configure()
                public_id = f"profiles/customer_{customer.id}_{int(time.time())}"
                result = cloudinary.uploader.upload(
                    profile_pic,
                    public_id=public_id,
                    overwrite=False,
                    resource_type='image',
                )
                new_key = result.get('public_id') or public_id
            except Exception as e:
                messages.error(request, f'Upload failed: {e}')
                return redirect('customers:dashboard')

            customer.profile_photo = new_key
            customer.save()

            if old_key and old_key != new_key:
                try:
                    _cloudinary_configure()
                    cloudinary.uploader.destroy(old_key)
                except Exception:
                    pass

            messages.success(request, 'Profile photo updated successfully!')
            return redirect('customers:dashboard')
        else:
            messages.error(request, "No image selected.")

    return render(request, 'customers/dashboard.html', {
        'customer': customer,
    })


@login_required(login_url='customers:login')
def customer_settings(request):
    try:
        customer = request.user.customer_profile
    except AttributeError:
        messages.error(request, "You do not have a customer profile set up.")
        return redirect('customers:login')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'change_password':
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Your PIN/Password has been updated successfully!")
                return redirect('customers:settings')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{error}")

        elif action == 'update_info':
            phone = request.POST.get('phone_number', '').strip()
            email = request.POST.get('email', '').strip()
            
            if phone:
                customer.phone_number = phone
                customer.user.username = phone
            if email:
                customer.email = email
                customer.user.email = email
            
            customer.save()
            customer.user.save()
            messages.success(request, "Contact information updated successfully!")
            return redirect('customers:settings')

        elif action == 'delete_account':
            user = request.user
            user.delete()
            messages.success(request, "Your account has been deleted permanently.")
            return redirect('home')

    password_form = PasswordChangeForm(request.user)

    return render(request, 'customers/settings.html', {
        'customer': customer,
        'password_form': password_form,
    })

@login_required(login_url='customers:login')
def customer_loan_create(request):
    """Customer Self-Service Loan Application"""
    try:
        customer = request.user.customer_profile
    except AttributeError:
        messages.error(request, "You do not have a customer profile set up.")
        return redirect('home')

    if customer.custom_loan_limit <= 0:
        messages.warning(request, "You need an approved loan limit before you can apply for a loan.")
        return redirect('customers:dashboard')

    # ✅ NEW: Block new applications while one is pending
    pending_loan = Loan.objects.filter(
        company=customer.company,
        guest__national_id=customer.national_id or customer.phone_number,
        status='pending',
    ).first()

    if pending_loan:
        messages.warning(
            request,
            "You already have a loan application pending approval. "
            "Please wait for it to be reviewed before applying again."
        )
        return redirect('customers:dashboard')

    if request.method == 'POST':
        loan_type_id = request.POST.get('loan_type')
        amount = request.POST.get('amount')
        term = request.POST.get('term_months')
        purpose = request.POST.get('purpose')

        try:
            loan_type = LoanType.objects.get(pk=loan_type_id, company=customer.company)
            amount_dec = Decimal(str(amount))

            if amount_dec > customer.custom_loan_limit:
                messages.error(request, f"Amount exceeds your approved limit of KES {customer.custom_loan_limit}.")
            else:
                guest, created = Guest.objects.get_or_create(
                    company=customer.company,
                    national_id=customer.national_id or customer.phone_number,
                    defaults={
                        'full_name': customer.full_name,
                        'phone': customer.phone_number,
                        'email': customer.email,
                    }
                )

                # ✅ Double-check inside transaction (race condition safety)
                with transaction.atomic():
                    already_pending = Loan.objects.filter(
                        company=customer.company,
                        guest=guest,
                        status='pending',
                    ).exists()

                    if already_pending:
                        messages.warning(request, "A pending loan application already exists.")
                        return redirect('customers:dashboard')

                    Loan.objects.create(
                        company=customer.company,
                        loan_category='external',
                        guest=guest,
                        loan_type=loan_type,
                        principal=amount_dec,
                        interest_rate=loan_type.interest_rate,
                        term_months=term,
                        purpose=purpose,
                        status='pending',
                    )

                messages.success(request, "Your loan application has been submitted and is pending approval.")
                return redirect('customers:dashboard')
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    loan_types = LoanType.objects.filter(company=customer.company, is_active=True)

    return render(request, 'customers/loan_create.html', {
        'customer': customer,
        'loan_types': loan_types,
        'latest_loan': latest_loan, 
    })
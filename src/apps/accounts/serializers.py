# apps/users/serializers.py

import uuid
from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User

User = get_user_model()


# ============================================================
# DISPLAY / READ SERIALIZERS
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    role_flags = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
    active_membership = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'role_display', 'role_flags',
            'company', 'company_name', 'branch', 'branch_name',
            'phone', 'staff_id', 'department', 'position', 'hire_date',
            'is_verified', 'two_factor_enabled',
            'profile_picture', 'profile_picture_url', 'address', 'is_active',
            'created_at', 'updated_at', 'active_membership',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'is_verified', 'two_factor_enabled', 'active_membership',
        ]

    def get_full_name(self, obj):
        return obj.full_name

    def get_role_display(self, obj):
        return obj.get_role_display()

    def get_company_name(self, obj):
        return obj.company.name if obj.company else None

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else None

    def get_profile_picture_url(self, obj):
        return obj.profile_picture_url

    def get_active_membership(self, obj):
        """The membership used to authenticate this session, if any."""
        m = getattr(obj, 'active_membership', None)
        if not m:
            return None
        return {
            'id': m.id,
            'company_id': m.company_id,
            'company_name': m.company.name if m.company else None,
            'company_subdomain': getattr(m.company, 'subdomain', None) if m.company else None,
            'role': m.role,
            'role_display': m.get_role_display(),
            'branch_id': m.branch_id,
            'branch_name': m.branch.name if m.branch else None,
            'company_username': m.company_username,
            'is_primary': m.is_primary,
        }

    def get_role_flags(self, obj):
        flags = getattr(obj, 'role_flags', None)
        if flags:
            return flags

        return {
            # Platform
            'is_super_admin': obj.role == 'super_admin',
            'is_site_manager': obj.role == 'site_manager',
            'is_company_admin': obj.role == 'company_admin',
            'is_company_manager': obj.role == 'company_manager',
            'is_company_cashier': obj.role == 'company_cashier',
            'is_stock_controller': obj.role == 'stock_controller',
            'is_company_agent': obj.role == 'company_agent',
            'is_mpesa_agent': obj.role == 'mpesa_agent',
            'is_company_technician': obj.role == 'company_technician',
            'is_customer_care': obj.role == 'customer_care',
            'is_company_staff': obj.role == 'company_staff',
            'is_guest': obj.role == 'guest',
            # Chama
            'is_chairperson': obj.role == 'chairperson',
            'is_vice_chairperson': obj.role == 'vice_chairperson',
            'is_secretary': obj.role == 'secretary',
            'is_vice_secretary': obj.role == 'vice_secretary',
            'is_treasurer': obj.role == 'treasurer',
            'is_loan_officer': obj.role == 'loan_officer',
            'is_coopted_member': obj.role == 'coopted_member',
            'is_member': obj.role == 'member',
        }


# ============================================================
# MEMBERSHIP SERIALIZERS  (per-company login profiles)
# ============================================================

class MembershipSerializer(serializers.ModelSerializer):
    company_name = serializers.SerializerMethodField()
    company_subdomain = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()

    class Meta:
        from apps.accounts.models import Membership
        model = Membership
        fields = [
            'id', 'company', 'company_name', 'company_subdomain',
            'branch', 'branch_name', 'role', 'role_display',
            'company_username', 'is_active', 'is_primary',
            'created_at',
        ]
        read_only_fields = ['id', 'company_username', 'created_at']

    def get_company_name(self, obj):
        return obj.company.name if obj.company else None

    def get_company_subdomain(self, obj):
        return getattr(obj.company, 'subdomain', None) if obj.company else None

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else None

    def get_role_display(self, obj):
        return obj.get_role_display()


# ============================================================
# UPDATE
# ============================================================

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone',
            'address', 'profile_picture', 'branch',
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Email already exists")
        return value


# ============================================================
# REGISTRATION
# ============================================================

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    company_name = serializers.CharField(write_only=True, required=True, max_length=200)
    business_type = serializers.CharField(write_only=True, required=True, max_length=100)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'confirm_password',
            'first_name', 'last_name', 'role', 'phone',
            'company_name', 'business_type',
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords don't match"})
        try:
            validate_password(attrs['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        from apps.companies.business_types import (
            BusinessTypeEnum, BUSINESS_TYPE_SLUGS,
        )
        raw = (attrs.get('business_type') or '').strip()
        slug_to_name = {v: k for k, v in BUSINESS_TYPE_SLUGS.items()}
        resolved_name = slug_to_name.get(raw.lower()) or slug_to_name.get(raw)
        if not resolved_name:
            for name in BusinessTypeEnum.get_all_names():
                if name.lower() == raw.lower():
                    resolved_name = name
                    break
        if not resolved_name or not BusinessTypeEnum.validate_name(resolved_name):
            raise serializers.ValidationError({
                "business_type": f"Invalid business type. Choose one of: {', '.join(BusinessTypeEnum.get_all_names())}"
            })
        attrs['_business_type_name'] = resolved_name
        attrs['role'] = 'company_admin'
        return attrs

    def create(self, validated_data):
        from django.db import transaction
        from apps.companies.models import Company, BusinessType
        from apps.accounts.models import Membership

        company_name = validated_data.pop('company_name')
        validated_data.pop('business_type')
        business_name = validated_data.pop('_business_type_name')
        validated_data.pop('confirm_password')

        with transaction.atomic():
            validated_data['is_active'] = True
            validated_data['role'] = 'company_admin'
            user = User.objects.create_user(**validated_data)

            try:
                business_type_obj = BusinessType.objects.get(name=business_name)
            except BusinessType.DoesNotExist:
                business_type_obj = BusinessType(name=business_name, is_active=True)
                business_type_obj.save()

            company = Company.objects.create(
                name=company_name,
                business_type=business_type_obj,
                registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
                address='Not provided',
                city='Eldoret',
                state='Uasin Gishu',
                country='Kenya',
                postal_code='30100',
                email=user.email,
                phone=getattr(user, 'phone', '') or '',
                status='active',
                is_active=True,
                created_by=user,
            )

            # Link user -> company (global, backward compat)
            user.company = company
            user.role = 'company_admin'
            user.save()

            # Create the PRIMARY membership for this company profile.
            # Set the SAME password so the owner can log in via
            # company_username OR email from day one.
            membership = Membership(
                user=user,
                company=company,
                role='company_admin',
                is_primary=True,
                is_active=True,
            )
            membership.set_password(validated_data.get('password') or '')
            membership.save()

        return user


# ============================================================
# LOGIN  (multi-tenant, per-company login)
# ============================================================

class LoginSerializer(serializers.Serializer):
    """
    Accepts ANY of:
      - company_username  (e.g. FEK74039837)
      - email
      - phone
      - global username

    Plus password. Delegates to authenticate(request=...) so the
    MembershipBackend can pick the right membership for the current tenant.
    """
    username = serializers.CharField(
        required=True,
        help_text="Company username, email, phone, or global username.",
    )
    password = serializers.CharField(
        required=True, style={'input_type': 'password'}, write_only=True,
    )

    def validate(self, attrs):
        identifier = (attrs.get('username') or '').strip()
        password = attrs.get('password') or ''

        if not identifier or not password:
            raise serializers.ValidationError(
                {"error": "Username and password are required"}
            )

        request = self.context.get('request')

        # IMPORTANT: pass request so MembershipBackend can filter by tenant
        user = authenticate(
            request=request,
            username=identifier,
            password=password,
        )

        if not user:
            raise serializers.ValidationError(
                {"error": "Invalid login credentials"}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"error": "Account is deactivated"}
            )

        attrs['user'] = user
        return attrs


# ============================================================
# ROLE / COMPANY UPDATES (admin)
# ============================================================

class UserRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)


class UserCompanyUpdateSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(required=True)
    role = serializers.ChoiceField(
        choices=[
            (value, label)
            for value, label in User.ROLE_CHOICES
            if value not in ('super_admin', 'guest')
        ],
        required=False,
    )


# ============================================================
# PASSWORD
# ============================================================

class UserPasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "Passwords don't match"})

        try:
            validate_password(attrs['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        return attrs


class UserPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist")
        return value
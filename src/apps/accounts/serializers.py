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

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'role_display', 'role_flags',
            'company', 'company_name', 'branch', 'branch_name',
            'phone', 'staff_id', 'department', 'position', 'hire_date',
            'is_verified', 'two_factor_enabled',
            'profile_picture', 'profile_picture_url', 'address', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified', 'two_factor_enabled']

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

    def get_role_flags(self, obj):
        """
        Return the model's role_flags dict if present.
        Falls back to a manually-built dict so the serializer never breaks
        if the model property is removed or renamed.
        """
        flags = getattr(obj, 'role_flags', None)
        if flags:
            return flags

        # Fallback — includes both platform and Chama roles
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

        # --- Validate business_type: kubali slug ("epa-shop") au jina ("EPA Shop") ---
        from apps.companies.business_types import (
            BusinessTypeEnum, BUSINESS_TYPE_SLUGS,
        )
        raw = (attrs.get('business_type') or '').strip()
        # BUSINESS_TYPE_SLUGS = {"EPA Shop": "epa-shop", ...} -> reverse it
        slug_to_name = {v: k for k, v in BUSINESS_TYPE_SLUGS.items()}
        # Jaribu kama ni slug kwanza, kisha kama ni jina
        resolved_name = slug_to_name.get(raw.lower()) or slug_to_name.get(raw)
        if not resolved_name:
            # Labda user alituma jina lenyewe
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

        company_name = validated_data.pop('company_name')
        validated_data.pop('business_type')
        business_name = validated_data.pop('_business_type_name')
        validated_data.pop('confirm_password')

        with transaction.atomic():
            # 1. User - ACTIVE mara moja
            validated_data['is_active'] = True
            validated_data['role'] = 'company_admin'
            user = User.objects.create_user(**validated_data)

            # 2. BusinessType - lazima iwe kwenye choices, usi-create ya ovyo
            try:
                business_type_obj = BusinessType.objects.get(name=business_name)
            except BusinessType.DoesNotExist:
                business_type_obj = BusinessType(name=business_name, is_active=True)
                business_type_obj.save()  # clean() ita-validate kupitia Enum

            # 3. Company - jaza fields zote required
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

            # 4. Unganisha user -> company
            user.company = company
            user.role = 'company_admin'
            user.is_active = True
            user.save()

        return user

        
# ============================================================
# LOGIN
# ============================================================

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

            if not user:
                raise serializers.ValidationError({"error": "Invalid email or password"})

            if not user.is_active:
                raise serializers.ValidationError({"error": "Account is deactivated"})

            attrs['user'] = user
        else:
            raise serializers.ValidationError({"error": "Email and password are required"})

        return attrs


# ============================================================
# ROLE / COMPANY UPDATES (admin)
# ============================================================

class UserRoleUpdateSerializer(serializers.Serializer):
    """
    Validates a role assignment. Choices come from User.ROLE_CHOICES so
    adding a role to the model automatically makes it assignable here.
    """
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)


class UserCompanyUpdateSerializer(serializers.Serializer):
    """
    Assign a user to a company, optionally updating their role.

    Note: 'super_admin' and 'guest' are intentionally NOT offered here —
    those are managed through different flows. Extend the whitelist below
    only if that policy changes.
    """
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
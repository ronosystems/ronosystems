# apps/users/serializers.py

from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 
            'full_name', 'role', 'role_display', 'company', 'company_name',
            'branch', 'branch_name', 'phone', 'staff_id', 'department',
            'position', 'hire_date', 'is_verified', 'two_factor_enabled',
            'profile_picture', 'address', 'is_active', 'created_at', 'updated_at'
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


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone', 
            'address', 'profile_picture', 'branch'
        ]
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Email already exists")
        return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'confirm_password', 
            'first_name', 'last_name', 'role', 'phone'
        ]
    
    def validate(self, attrs):
        # Check password match
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords don't match"})
        
        # Validate password strength
        try:
            validate_password(attrs['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        
        # Validate role
        allowed_roles = ['company_admin', 'company_manager', 'company_cashier', 'company_agent', 'company_staff']
        if attrs.get('role') not in allowed_roles:
            raise serializers.ValidationError({"role": "Invalid role selected"})
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, style={'input_type': 'password'})
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Try to find user by email
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
            
            if not user:
                raise serializers.ValidationError({"error": "Invalid email or password"})
            
            attrs['user'] = user
        else:
            raise serializers.ValidationError({"error": "Email and password are required"})
        
        return attrs


class UserRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[
        ('super_admin', 'Super Admin'),
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('company_agent', 'Company Agent'),
        ('company_staff', 'Company Staff'),
    ])


class UserCompanyUpdateSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(required=True)
    role = serializers.ChoiceField(choices=[
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('company_agent', 'Company Agent'),
        ('company_staff', 'Company Staff'),
    ], required=False)


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
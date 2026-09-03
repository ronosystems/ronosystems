from rest_framework import serializers
from .models import Company, BusinessType
from apps.business_types.business_type_registry import BusinessTypeEnum

class BusinessTypeSerializer(serializers.ModelSerializer):
    integration = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()
    
    class Meta:
        model = BusinessType
        fields = ['id', 'name', 'description', 'icon', 'is_active', 
                 'created_at', 'updated_at', 'integration', 'slug']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_integration(self, obj):
        return obj.integration
    
    def get_slug(self, obj):
        return obj.slug

class CompanySerializer(serializers.ModelSerializer):
    business_type_name = serializers.CharField(source='business_type.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'business_type', 'business_type_name',
            'registration_number', 'address', 'city', 'state',
            'country', 'postal_code', 'email', 'phone', 'website',
            'logo', 'plan', 'subscription_start', 'subscription_end',
            'status', 'is_active', 'created_by', 'created_by_username',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_business_type(self, value):
        """Validate that the business type exists in the registry"""
        if value:
            # Check if the business type name is valid
            if not BusinessTypeEnum.validate_name(value.name):
                valid_names = ', '.join(BusinessTypeEnum.get_all_names())
                raise serializers.ValidationError(
                    f"'{value.name}' is not a valid business type. Valid types: {valid_names}"
                )
        return value

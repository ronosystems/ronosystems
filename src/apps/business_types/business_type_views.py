from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .business_type_registry import BusinessTypeEnum
from .business_type_manager import BusinessTypeManager
from apps.accounts.permissions import IsSuperAdmin

class AvailableBusinessTypesView(APIView):
    """
    Get all available business types from the registry
    This ensures consistent naming
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        business_types = BusinessTypeEnum.get_all_active()
        return Response({
            'count': len(business_types),
            'business_types': business_types,
            'message': 'These are the official business types. Use exact names when creating business types.'
        })

class ValidateBusinessTypeView(APIView):
    """
    Validate if a business type name is valid
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        name = request.data.get('name')
        if not name:
            return Response(
                {'error': 'Business type name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        is_valid = BusinessTypeEnum.validate_name(name)
        
        if is_valid:
            business_type = BusinessTypeEnum.get_by_name(name)
            return Response({
                'is_valid': True,
                'message': f"'{name}' is a valid business type",
                'details': business_type.value if business_type else None
            })
        else:
            valid_names = BusinessTypeEnum.get_all_names()
            return Response({
                'is_valid': False,
                'message': f"'{name}' is not a valid business type",
                'valid_types': valid_names,
                'suggestion': 'Use one of the valid business types above'
            }, status=status.HTTP_400_BAD_REQUEST)

class InitializeBusinessTypesView(APIView):
    """
    Super Admin: Initialize all default business types
    """
    permission_classes = [IsSuperAdmin]
    
    def post(self, request):
        try:
            created = BusinessTypeManager.initialize_default_business_types()
            return Response({
                'success': True,
                'message': f'Initialized {len(created)} business types',
                'business_types': [bt.name for bt in created]
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from .business_types import BusinessTypeEnum
from .business_type_manager import BusinessTypeManager
from apps.accounts.permissions import IsSuperAdmin

from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from apps.companies.models import BusinessType, Company

def _model_field_names():
    return [f.name for f in BusinessType._meta.get_fields()]

def _sync_enum_to_db():
    """Sync Enum -> DB kwa kutumia name (hakuna slug kwenye Model)."""
    fields = _model_field_names()
    for bt in BusinessTypeEnum.get_all_active():
        if isinstance(bt, dict):
            name = bt.get('name')
            description = bt.get('description', '')
            icon = bt.get('icon', '')
        else:
            name = getattr(bt, 'name', str(bt))
            description = getattr(bt, 'description', '')
            icon = getattr(bt, 'icon', '')

        if not name:
            continue

        defaults = {}
        if 'description' in fields:
            defaults['description'] = description
        if 'icon' in fields and icon:
            defaults['icon'] = icon
        if 'is_active' in fields:
            defaults['is_active'] = True

        # get_or_create kwa name - sio slug, kwa sababu slug haipo
        BusinessType.objects.get_or_create(name=name, defaults=defaults)

@login_required
def business_type_list(request):
    if getattr(request.user, 'role', None) != 'super_admin':
        return redirect('dashboard-router')

    _sync_enum_to_db()

    business_types = BusinessType.objects.all().order_by('name')
    for bt in business_types:
        # Company ina FK kwenda BusinessType (companies = reverse relation)
        try:
            bt.company_count = Company.objects.filter(business_type=bt).count()
        except Exception:
            try:
                bt.company_count = Company.objects.filter(business_type__name__iexact=bt.name).count()
            except Exception:
                try:
                    bt.company_count = Company.objects.filter(business_type_slug__iexact=bt.name).count()
                except Exception:
                    bt.company_count = 0

    return render(request, 'companies/business_type_list.html', {
        'business_types': business_types,
    })

# Form - fields zilizopo kweli: name, description, icon, is_active, allowed_plans
_FORM_FIELDS = [f for f in ['name', 'description', 'icon', 'is_active'] if f in _model_field_names()]

class BusinessTypeForm(forms.ModelForm):
    class Meta:
        model = BusinessType
        fields = _FORM_FIELDS
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: Pharmacy'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'fa-store'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


@login_required
def business_type_create(request):
    if getattr(request.user, 'role', None) != 'super_admin':
        return redirect('dashboard-router')

    if request.method == 'POST':
        form = BusinessTypeForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard-router')
    else:
        form = BusinessTypeForm()

    return render(request, 'companies/business_type_form.html', {
        'form': form,
        'title': 'Create Business Type',
        'button_text': 'Create Business Type',
        'object': None,
        'available_types': BusinessTypeEnum.get_all_active(),
    })

@login_required
def business_type_edit(request, pk):
    if getattr(request.user, 'role', None) != 'super_admin':
        return redirect('dashboard-router')

    obj = get_object_or_404(BusinessType, pk=pk)

    if request.method == 'POST':
        # Edit: name ni readonly, hakikisha inatoka kwenye hidden input
        data = request.POST.copy()
        data['name'] = obj.name
        form = BusinessTypeForm(data, instance=obj)
        if form.is_valid():
            form.save()
            return redirect('dashboard-router')
    else:
        form = BusinessTypeForm(instance=obj)

    return render(request, 'companies/business_type_form.html', {
        'form': form,
        'title': f'Edit: {obj.name}',
        'button_text': 'Save Changes',
        'object': obj,
        'available_types': BusinessTypeEnum.get_all_active(),
    })

    

# ============================================================
# API VIEWS
# ============================================================
class AvailableBusinessTypesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        business_types = BusinessTypeEnum.get_all_active()
        return Response({
            'count': len(business_types),
            'business_types': business_types,
            'message': 'These are the official business types. Use exact names when creating business types.'
        })

class ValidateBusinessTypeView(APIView):
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
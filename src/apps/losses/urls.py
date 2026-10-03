from django.urls import path
from . import views

app_name = 'losses'

urlpatterns = [
    # ============================================
    # BRANCH-OPTIONAL ENTRY (used by sidebar)
    # ============================================
    path(
        '<int:company_id>/',
        views.loss_list_entry,
        name='loss_list_entry',
    ),

    # ============================================
    # LIST
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/',
        views.loss_list,
        name='loss_list',
    ),

    # ============================================
    # CREATE
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/create/',
        views.loss_create,
        name='loss_create',
    ),

    # ============================================
    # EDIT
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/<int:pk>/edit/',
        views.loss_edit,
        name='loss_edit',
    ),

    # ============================================
    # DELETE
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/<int:pk>/delete/',
        views.loss_delete,
        name='loss_delete',
    ),

    # ============================================
    # VERIFY / UN-VERIFY (admin + stock controller)
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/<int:pk>/verify/',
        views.loss_verify,
        name='loss_verify',
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/<int:pk>/unverify/',
        views.loss_unverify,
        name='loss_unverify',
    ),

    # ============================================
    # API — Auto-fill cost price from product
    # ============================================
    path(
        'api/product-lookup/',
        views.api_product_lookup,
        name='api_product_lookup',
    ),
]
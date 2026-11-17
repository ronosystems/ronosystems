# /home/rs/ronosystems/src/apps/cart_orders/urls.py
from django.urls import path
from . import client_views, staff_views

app_name = 'cart-orders'

urlpatterns = [
    # ---- public customer ----
    path('',                                   client_views.view_cart,        name='view-cart'),
    path('add/',                               client_views.add_to_cart,      name='add-to-cart'),
    path('remove/',                            client_views.remove_from_cart, name='remove-from-cart'),
    path('checkout/',                          client_views.checkout,         name='checkout'),
    path('order/success/<str:order_number>/',  client_views.order_success,    name='order-success'),

    # ---- authenticated staff ----
    path('orders/',                            staff_views.order_list,              name='order-list'),
    path('orders/<int:order_id>/pick/',        staff_views.pick_order,              name='pick-order'),
    path('orders/<int:order_id>/unpick/',      staff_views.unpick_order,            name='unpick-order'),
    path('orders/<int:order_id>/follow-up/',   staff_views.mark_order_followed_up,  name='follow-up'),
    path('orders/<int:order_id>/confirm/',     staff_views.confirm_order,           name='confirm-order'),
    path('orders/<int:order_id>/delete/',      staff_views.delete_order,                  name='order-delete'),
    path('api/search-units/',                  staff_views.search_units_api,        name='search-units-api'),
    path('orders/<int:order_id>/link-sale/',   staff_views.link_sale_page,          name='link-sale'),
    path('orders/<int:order_id>/cancel/',      staff_views.cancel_order,            name='cancel-order'),
    path('orders/<int:order_id>/delete/',      staff_views.delete_cancelled_order,  name='delete-order'),
    path('orders/<int:order_id>/approve-cancellation/', staff_views.approve_cancellation, name='approve-cancellation'),
    path('orders/<int:order_id>/archive/',              staff_views.order_archive_detail, name='order-archive-detail'),
    path('orders/<int:order_id>/pay-pending/',          staff_views.pay_pending_order,    name='pay-pending-order'),
]
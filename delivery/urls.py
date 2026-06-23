"""
App-level URL routing.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboards
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('dashboard/customer/', views.customer_dashboard, name='customer_dashboard'),
    path('dashboard/merchant/', views.merchant_dashboard, name='merchant_dashboard'),
    path('dashboard/courier/', views.courier_dashboard, name='courier_dashboard'),
    path('dashboard/courier/map/', views.courier_map, name='courier_map'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),

    # Customer APIs
    path('api/merchants/', views.api_merchants, name='api_merchants'),
    path('api/menu/<int:merchant_id>/', views.api_menu, name='api_menu'),
    path('api/place-order/', views.api_place_order, name='api_place_order'),
    path('api/cancel-order/', views.api_cancel_order, name='api_cancel_order'),

    # Merchant APIs
    path('api/merchant/add-menu-item/', views.api_add_menu_item, name='api_add_menu_item'),
    path('api/merchant/create-order/', views.api_merchant_create_order, name='api_merchant_create_order'),
    path('api/merchant/accept-order/', views.api_merchant_accept_order, name='api_merchant_accept_order'),
    path('api/merchant/ready-for-pickup/', views.api_merchant_ready_for_pickup, name='api_merchant_ready_for_pickup'),

    # Courier APIs
    path('api/orders/', views.api_orders, name='api_orders'),
    path('api/accept-orders/', views.api_accept_orders, name='api_accept_orders'),
    path('api/update-status/', views.api_update_status, name='api_update_status'),
    path('api/courier/route/', views.api_courier_route, name='api_courier_route'),

    # Admin APIs
    path('api/admin/users/', views.api_admin_users, name='api_admin_users'),
    path('api/admin/create-user/', views.api_admin_create_user, name='api_admin_create_user'),
    path('api/admin/delete-user/', views.api_admin_delete_user, name='api_admin_delete_user'),
    path('api/admin/approve-user/', views.api_approve_user, name='api_approve_user'),
    path('api/admin/transfer-role/', views.api_transfer_role, name='api_transfer_role'),
    path('api/admin/orders/', views.api_admin_orders, name='api_admin_orders'),
    path('api/admin/update-order/', views.api_admin_update_order, name='api_admin_update_order'),
]
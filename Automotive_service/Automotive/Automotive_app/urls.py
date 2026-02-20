from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet, ServiceViewSet, BookingViewSet, 
    SparePartViewSet, DentingRequestViewSet, 
    AdminBookingViewSet, AdminDentingViewSet,
    RegisterView, login_view, get_user_details, PartOrderViewSet,
    AdminPartOrderViewSet, UserServiceHistoryView,
    ServiceHistoryUpdateView, # Now exists in views.py
    request_password_reset,
    StaffManagementView, toggle_staff_status,password_reset_confirm, toggle_user_role
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'spare-parts', SparePartViewSet, basename='part')
router.register(r'denting-requests', DentingRequestViewSet, basename='denting')

# Admin Dashboard ViewSets
router.register(r'admin-bookings', AdminBookingViewSet, basename='admin-bookings')
router.register(r'admin-denting', AdminDentingViewSet, basename='admin-denting')

# Order Management
router.register(r'part-orders', PartOrderViewSet, basename='part-order')
router.register(r'admin-part-orders', AdminPartOrderViewSet, basename='admin-part-orders')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', login_view, name='login'), 
    path('user-details/', get_user_details, name='user-details'),
    path('history/', UserServiceHistoryView.as_view(), name='user-history'),

    # Individual Path for History Update
    path('history/<int:pk>/update/', ServiceHistoryUpdateView.as_view(), name='update-history'),

    # Staff Management
    path('admin/users/', StaffManagementView.as_view(), name='staff-list'),
   path('admin/users/<int:user_id>/toggle_role/', toggle_user_role, name='toggle-user-role'),

    # Password Reset
    path('password-reset/', request_password_reset, name='password_reset_request'),
    path('password-reset-confirm/', password_reset_confirm, name='password_reset_confirm'),
]
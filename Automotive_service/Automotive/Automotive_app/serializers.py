from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Vehicle, Service, Booking, SparePart, DentingRequest, PartOrder, ServiceHistory

# --- USER SERIALIZER ---
class UserSerializer(serializers.ModelSerializer):
    is_mechanic = serializers.BooleanField(source='profile.is_mechanic', read_only=True)
    is_billing = serializers.BooleanField(source='profile.is_billing', read_only=True)
    is_ecommerce = serializers.BooleanField(source='profile.is_ecommerce', read_only=True)
    is_staff = serializers.BooleanField()
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'is_staff', 'is_superuser','is_mechanic', 'is_billing', 'is_ecommerce']
        extra_kwargs = {
            'is_staff': {'required': False, 'default': False},
            'password': {'write_only': True}}

# --- SPARE PART SERIALIZER ---
class SparePartSerializer(serializers.ModelSerializer):
    # We include the property in the fields list
    is_available = serializers.ReadOnlyField()

    class Meta:
        model = SparePart
        fields = [
            'id', 'name', 'brand', 'model', 'year', 
            'description', 'price', 'image', 'stock', 'is_available'
        ]

# --- DENTING & PAINTING REQUEST SERIALIZER ---
class DentingRequestSerializer(serializers.ModelSerializer):
    user_username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = DentingRequest
        fields = [
            'id', 'user_username', 'description', 'damage_image', 
            'vehicle_make', 'vehicle_model', 'status', 'created_at', 'estimated_price'
        ]
        read_only_fields = ['status', 'created_at']

# --- SERVICE SERIALIZER ---
class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'

# --- VEHICLE SERIALIZER ---
class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['id', 'make', 'model', 'year']

# --- BOOKING SERIALIZER ---
class BookingSerializer(serializers.ModelSerializer):
    user_username = serializers.ReadOnlyField(source='user.username')
    vehicle_info = serializers.SerializerMethodField()
    services_details = ServiceSerializer(source='services', many=True, read_only=True)
    service_names = serializers.SerializerMethodField()
    
    # We allow null=True here because if a booking is new, the admin might 
    # not have set the total_amount yet. This prevents 500 errors.
    total_amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        coerce_to_string=False,
        required=False,
        allow_null=True
    )
    final_amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        coerce_to_string=False,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Booking
        fields = [
            'id', 'user_username', 'vehicle', 'vehicle_info', 'services', 
            'services_details', 'service_names', 'appointment_time', 'status', 
            'total_amount', 'final_amount', 'payment_status', 'stripe_payment_intent_id'
        ]
        # Stripe IDs should never be manually edited via API
        read_only_fields = ['stripe_payment_intent_id']

    def get_vehicle_info(self, obj):
        try:
            return f"{obj.vehicle.year} {obj.vehicle.make} {obj.vehicle.model}"
        except AttributeError:
            return "N/A"

    def get_service_names(self, obj):
        # Using a list comprehension to get names of all linked services
        return [s.name for s in obj.services.all()]

# --- PART ORDER SERIALIZER ---
class PartOrderSerializer(serializers.ModelSerializer):
    user_username = serializers.ReadOnlyField(source='user.username')
    part_details = SparePartSerializer(source='part', read_only=True)
    
    total_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        coerce_to_string=False
    )

    class Meta:
        model = PartOrder
        fields = [
            'id', 'user_username', 'part', 'part_details', 'vehicle', 
            'phone_number', 'shipping_address', 'total_price',
            'payment_status', 'stripe_payment_intent_id', 'status', 'created_at','quantity',
        ]
        read_only_fields = ['payment_status', 'stripe_payment_intent_id', 'status', 'created_at']

# --- SERVICE HISTORY SERIALIZER ---
class ServiceHistorySerializer(serializers.ModelSerializer):
    vehicle_name = serializers.ReadOnlyField(source='vehicle.model')
    vehicle_make = serializers.ReadOnlyField(source='vehicle.make')
    user_username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = ServiceHistory
        fields = [
            'id', 'user_username', 'vehicle_name', 'vehicle_make', 
            'services_rendered', 'total_paid', 'odometer_reading', 
            'completion_date', 'admin_notes'
        ]

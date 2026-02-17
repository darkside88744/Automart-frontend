from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.conf import settings
import stripe
import logging

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode
from django.template.loader import render_to_string
from .tasks import send_async_email
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

# Set up logging
logger = logging.getLogger(__name__)

from .models import Vehicle, Service, Booking, SparePart, DentingRequest, PartOrder, ServiceHistory, UserProfile
from .serializers import (
    UserSerializer, 
    VehicleSerializer, 
    ServiceSerializer, 
    BookingSerializer, 
    SparePartSerializer, 
    DentingRequestSerializer,
    PartOrderSerializer,
    ServiceHistorySerializer
)

# Initialize Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

# --- AUTHENTICATION VIEWS ---

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        user.set_password(self.request.data.get('password'))
        user.save()
        
        # SEND WELCOME EMAIL ASYNC
        send_async_email.delay(
            subject="Welcome to AutoMart!",
            message=f"Hi {user.username}, thanks for joining AutoMart. You can now add your vehicles and book services.",
            recipient_list=[user.email]
        )

class IsStaffOrSpecialist(permissions.BasePermission):
    """
    Allows access if the user is a superuser, staff, or has a specialist role.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
            
        # Check standard staff status or your custom Profile roles
        is_specialist = False
        if hasattr(user, 'profile'):
            is_specialist = any([
                user.profile.is_mechanic,
                user.profile.is_billing,
                user.profile.is_ecommerce
            ])
            
        return user.is_superuser or user.is_staff or is_specialist

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)

    if user is not None:
        refresh = RefreshToken.for_user(user)
        has_vehicle = Vehicle.objects.filter(owner=user).exists()
        
        # Safely get role flags from the profile
        # Using getattr handles cases where a profile might not exist yet
        is_mechanic = getattr(user.profile, 'is_mechanic', False) if hasattr(user, 'profile') else False
        is_billing = getattr(user.profile, 'is_billing', False) if hasattr(user, 'profile') else False
        is_ecommerce = getattr(user.profile, 'is_ecommerce', False) if hasattr(user, 'profile') else False

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'username': user.username,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'is_mechanic': is_mechanic,   # ADDED
                'is_billing': is_billing,     # ADDED
                'is_ecommerce': is_ecommerce, # ADDED
                'has_vehicle': has_vehicle 
            }
        })
    return Response({'error': 'Invalid Credentials'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_details(request):
    return Response({
        'username': request.user.username,
        'is_staff': request.user.is_staff,
        'is_superuser': request.user.is_superuser
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset(request):
    email = request.data.get('email')
    user = User.objects.filter(email=email).first()
    
    if user:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_link = f"http://localhost:5173/reset-password/{uid}/{token}"
        
        subject = "AutoMart Password Reset"
        # The text version still exists as a backup
        text_content = f"Reset your password here: {reset_link}"
        
        # This HTML version prevents the "=" break because the link is inside an 'href'
        html_content = f"""
            <p>Click the button below to reset your password. This link expires shortly.</p>
            <a href="{reset_link}" 
               style="padding: 10px 20px; background-color: #e11d48; color: white; text-decoration: none; border-radius: 10px; font-weight: bold;">
               Reset My Password
            </a>
            <p>If the button doesn't work, copy-paste this URL: {reset_link}</p>
        """
        
        # Update your Celery task call to send HTML content
        send_async_email.delay(
            subject=subject,
            message=text_content,
            recipient_list=[email],
            html_message=html_content  # Make sure your task handles this!
        )
        
    return Response({"message": "If an account exists, a link has been sent."})

@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    uidb64 = request.data.get('uid')
    token = request.data.get('token')
    new_password = request.data.get('new_password')

    print(f"--- DEBUG START ---")
    print(f"Received UID: {uidb64}")
    print(f"Received Token: {token}")

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
        print(f"Found User: {user.username} (ID: {user.pk})")
    except Exception as e:
        print(f"User Lookup Error: {e}")
        return Response({"error": "Invalid User ID"}, status=400)

    is_valid = default_token_generator.check_token(user, token)
    print(f"Is Token Valid? {is_valid}")
    print(f"--- DEBUG END ---")

    if is_valid:
        user.set_password(new_password)
        user.save()
        return Response({"message": "Success"}, status=200)
    
    return Response({"error": "Token Check Failed"}, status=400)
# --- CORE FUNCTIONALITY VIEWSETS ---

class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    queryset = Vehicle.objects.all()

    def get_queryset(self):
        return Vehicle.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).order_by('-appointment_time')

    def perform_create(self, serializer):
        booking = serializer.save(user=self.request.user)
        

        # SEND BOOKING CONFIRMATION EMAIL ASYNC
        send_async_email.delay(
            "Service Booking Received",
            f"Your booking for {booking.services.name} is received.",
            [self.request.user.email] 
        )

    @action(detail=True, methods=['post'])
    def create_payment_intent(self, request, pk=None):
        try:
            booking = self.get_object()
            charge_amount = booking.final_amount if booking.final_amount else booking.total_amount
            
            if not charge_amount or charge_amount <= 0:
                return Response({'error': 'Payment amount not set by administrator.'}, status=400)

            amount_in_cents = int(float(charge_amount) * 100)
            
            intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,
                currency='inr',
                metadata={'booking_id': booking.id, 'type': 'service_booking'},
                automatic_payment_methods={'enabled': True},
            )
            
            booking.stripe_payment_intent_id = intent['id']
            booking.save()
            
            return Response({'clientSecret': intent['client_secret']})
        except Exception as e:
            logger.error(f"Stripe Intent Error: {str(e)}")
            return Response({'error': str(e)}, status=500)

    @action(detail=True, methods=['post'])
    def verify_payment(self, request, pk=None):
        payment_intent_id = request.data.get('payment_intent_id')
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            if intent['status'] == 'succeeded':
                booking = self.get_object()
                booking.payment_status = 'PAID'
                booking.save()

                # NOTIFY USER OF PAYMENT SUCCESS
                send_async_email.delay(
                    "Service Payment Confirmed",
                    f"Payment for Booking #{booking.id} was successful. See you at the workshop!",
                    [booking.user.email]
                )

                return Response({'status': 'Payment Verified', 'payment_status': 'PAID'})
            return Response({'status': f"Payment status: {intent['status']}"}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from django.db.models import Q
from .models import SparePart
from .serializers import SparePartSerializer

class SparePartViewSet(viewsets.ModelViewSet):
    serializer_class = SparePartSerializer

    def get_permissions(self):
        # AllowAny for viewing (list/retrieve) and the 'sell' action
        # Restricted to Admin for modifications
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        queryset = SparePart.objects.all()
        
        # Pull parameters from the React frontend filter inputs
        brand = self.request.query_params.get('brand')
        model = self.request.query_params.get('model')
        year = self.request.query_params.get('year')

        query = Q()
        if brand:
            # Matches React's matchesBrandOrName logic
            query |= Q(brand__icontains=brand) | Q(name__icontains=brand)
        if model:
            query &= Q(model__icontains=model)
        if year:
            query &= Q(year__icontains=year)

        return queryset.filter(query)

    @action(detail=True, methods=['post'], permission_classes=[AllowAny])
    def sell(self, request, pk=None):
        """
        Custom endpoint: /api/parts/{id}/sell/
        Decrements stock by 1 when a user processes a sale.
        """
        part = self.get_object()
        
        if part.stock > 0:
            part.stock -= 1
            part.save()
            
            # Return the updated object so React can update state immediately
            serializer = self.get_serializer(part)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(
            {"error": "This part is currently out of stock."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

class DentingRequestViewSet(viewsets.ModelViewSet):
    serializer_class = DentingRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DentingRequest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# --- SPARE PART ORDERS ---

class PartOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PartOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PartOrder.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def checkout(self, request):
        try:
            part_id = request.data.get('part_id')
            vehicle_id = request.data.get('vehicle_id')
            phone = request.data.get('phone_number')
            address = request.data.get('shipping_address')
            # 1. Get quantity from request, default to 1
            quantity = int(request.data.get('quantity', 1)) 
            
            part = SparePart.objects.get(id=part_id)
            
            # 2. Check if enough stock is available
            if part.stock < quantity:
                return Response({'error': f'Only {part.stock} items left in stock.'}, status=400)

            vehicle = Vehicle.objects.get(id=vehicle_id) if vehicle_id else None

            # 3. Calculate total price based on quantity
            total_price = float(part.price) * quantity
            amount_in_cents = int(total_price * 100)

            intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,
                currency='inr',
                metadata={
                    'user': request.user.username, 
                    'type': 'spare_part_purchase',
                    'quantity': quantity # Useful for Stripe dashboard
                },
                automatic_payment_methods={'enabled': True},
            )

            order = PartOrder.objects.create(
                user=request.user,
                part=part,
                vehicle=vehicle,
                phone_number=phone,
                shipping_address=address,
                # 4. Save the calculated total and the quantity
                total_price=total_price,
                quantity=quantity, # Ensure your PartOrder model has this field!
                payment_status='PENDING',
                stripe_payment_intent_id=intent['id']
            )

            return Response({'clientSecret': intent['client_secret'], 'order_id': order.id})
        except Exception as e:
            logger.error(f"Part Checkout Error: {str(e)}")
            return Response({'error': str(e)}, status=400)
        
    @action(detail=True, methods=['post'])
    def verify_part_payment(self, request, pk=None):
        payment_intent_id = request.data.get('payment_intent_id')
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            if intent['status'] == 'succeeded':
                order = self.get_object()
                
                # Prevent duplicate stock reduction if user refreshes
                if order.payment_status != 'PAID':
                    part = order.part
                    part.stock -= order.quantity # Decrement by ordered amount
                    part.save()
                    
                    order.payment_status = 'PAID'
                    order.save()

                    # NOTIFY USER
                    send_async_email.delay(
                        "AutoMart Order Confirmed",
                        f"Your order for {order.quantity}x {order.part.name} is confirmed.",
                        [order.user.email]
                    )

                return Response({'status': 'Paid'})
            return Response({'error': 'Payment failed'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        
    @action(detail=True, methods=['post'])
    def cancel_order(self, request, pk=None):
        try:
            order = self.get_object()

            send_async_email.delay(
                "Service Final Quote",
                f"Order cancellation requested for {order.part.name} completed. Amount will be refunded in due course.",
                [order.user.email]

                
            )
            
            if order.payment_status == 'PAID':
                if not order.stripe_payment_intent_id:
                    return Response({'error': 'No payment record found to refund.'}, status=400)
                
                refund = stripe.Refund.create(payment_intent=order.stripe_payment_intent_id)
                if refund.status in ['succeeded', 'pending']:
                    order.payment_status = 'REFUNDED'
                else:
                    return Response({'error': f'Refund failed: {refund.status}'}, status=400)

            if order.status in ['Pending', 'Confirmed']:
                order.status = 'Cancelled'
                order.save()
                
                msg = "Order cancelled and refund initiated." if order.payment_status == 'REFUNDED' else "Order cancelled."
                return Response({'status': msg, 'order_status': order.status, 'payment_status': order.payment_status}, status=status.HTTP_200_OK)
            
            return Response({'error': f'Order cannot be cancelled at stage: {order.status}'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


# --- ADMIN VIEWSETS ---

# --- ADMIN VIEWSETS ---

class AdminBookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().order_by('-appointment_time')
    serializer_class = BookingSerializer
    # UPDATED: Changed from IsAdminUser to IsStaffOrSpecialist
    permission_classes = [IsStaffOrSpecialist] 

    @action(detail=True, methods=['post'])
    def finalize_booking(self, request, pk=None):
        booking = self.get_object()
        final_amount = request.data.get('final_amount')

        if final_amount is None:
            return Response({'error': 'A final amount is required to complete the booking.'}, status=400)

        try:
            booking.final_amount = final_amount
            booking.status = 'COMPLETED'
            booking.save()

            send_async_email.delay(
                "Service Final Quote",
                f"Your service is complete. The final amount is {final_amount}. Please pay via your dashboard.",
                [booking.user.email]
            )
            
            return Response({
                'status': 'Booking Completed. User can now pay from dashboard.',
                'final_amount': booking.final_amount
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class AdminDentingViewSet(viewsets.ModelViewSet):
    queryset = DentingRequest.objects.all().order_by('-created_at')
    serializer_class = DentingRequestSerializer
    # UPDATED: Changed from IsAdminUser to IsStaffOrSpecialist
    permission_classes = [IsStaffOrSpecialist] 

class AdminPartOrderViewSet(viewsets.ModelViewSet):
    queryset = PartOrder.objects.all().order_by('-created_at')
    serializer_class = PartOrderSerializer
    # UPDATED: Changed from IsAdminUser to IsStaffOrSpecialist
    permission_classes = [IsStaffOrSpecialist] 

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        try:
            order = self.get_object()
            new_status = request.data.get('status')
            
            if not new_status:
                return Response({'error': 'Status is required'}, status=400)

            order.status = new_status
            
            send_async_email.delay(
                f"AutoMart Order Update: {new_status}",
                f"Your part order status has changed to: {new_status}",
                [order.user.email]
            )
            
            if new_status == 'Cancelled' and order.payment_status == 'PAID':
                if order.stripe_payment_intent_id:
                    refund = stripe.Refund.create(payment_intent=order.stripe_payment_intent_id)
                    if refund.status in ['succeeded', 'pending']:
                        order.payment_status = 'REFUNDED'
            
            order.save()
            return Response({
                'status': f'Order updated to {new_status}',
                'payment_status': order.payment_status
            })
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        revenue = PartOrder.objects.filter(payment_status='PAID').exclude(status='Cancelled').aggregate(total=Sum('total_price'))['total'] or 0
        active_distributions = PartOrder.objects.exclude(status__in=['Cancelled', 'Delivered']).count()

        return Response({
            'total_paid_revenue': revenue,
            'active_distributions': active_distributions
        })


# --- LOGBOOK & STAFF MANAGEMENT ---

class UserServiceHistoryView(generics.ListAPIView):
    serializer_class = ServiceHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Initialize flags
        is_mechanic = False
        is_billing = False
        
        # Access the PROFILE model where you actually saved the roles
        if hasattr(user, 'profile'):
            is_mechanic = user.profile.is_mechanic
            is_billing = user.profile.is_billing

        # Now check if they have ANY privilege
        is_privileged = (
            user.is_superuser or 
            user.is_staff or 
            is_mechanic or 
            is_billing
        )

        if is_privileged:
            # Show everything to staff/mechanics/billing
            return ServiceHistory.objects.all().order_by('-completion_date')
        
        # Show only personal records to regular customers
        return ServiceHistory.objects.filter(user=user).order_by('-completion_date')

class ServiceHistoryUpdateView(generics.UpdateAPIView):
    queryset = ServiceHistory.objects.all()
    serializer_class = ServiceHistorySerializer
    # Change this from [IsAdminUser] to use your custom permission logic
    permission_classes = [IsStaffOrSpecialist]

class IsSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)

class StaffManagementView(generics.ListAPIView):
    queryset = User.objects.all().exclude(is_superuser=True).order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsSuperUser]

@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def toggle_staff_status(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        user.is_staff = not user.is_staff
        user.save()
        return Response({'is_staff': user.is_staff}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    

# This view toggles custom roles like 'is_mechanic', 'is_billing', and 'is_ecommerce' in the UserProfile model, as well as the built-in 'is_staff' status. It uses get_or_create to ensure that a UserProfile exists for the user, preventing crashes if the profile is missing. The response indicates the new status of the role that was toggled.    
@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def toggle_user_role(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        role = request.data.get('role')
        
        # 1. Handle Built-in Django Staff Status
        if role == 'is_staff':
            user.is_staff = not user.is_staff
            user.save()
            return Response({'status': 'success'}, status=200)

        # 2. Handle Custom Roles (Mechanic, Billing, etc.)
        if role in ['is_mechanic', 'is_billing', 'is_ecommerce']:
            # get_or_create prevents the 500 crash if profile is missing
            profile, created = UserProfile.objects.get_or_create(user=user)
            current_val = getattr(profile, role)
            setattr(profile, role, not current_val)
            profile.save()
            return Response({'status': 'success'}, status=200)

        return Response({'error': 'Invalid role'}, status=400)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    except Exception as e:
        print(f"Error: {e}") # This shows up in your terminal
        return Response({'error': str(e)}, status=500)
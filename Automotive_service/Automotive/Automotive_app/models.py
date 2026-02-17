from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator

# 1. Vehicle Model
class Vehicle(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.IntegerField()
    license_plate = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"{self.year} {self.make} {self.model} ({self.owner.username})"

# 2. Service Model (Fixed Rate Catalog)
class Service(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.name

# 3. Booking Model
class Booking(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Confirmation'),
        ('CONFIRMED', 'Confirmed'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
        ('COMPLETED', 'Completed')
    )
    payment_status = models.CharField(
        max_length=20, 
        choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed')],
        default='PENDING')

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    services = models.ManyToManyField(Service)
    appointment_time = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    
    # Pricing Fields
    # total_amount acts as the dynamic bill set by admin
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    
    # Stripe Fields (Replaced Razorpay)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Booking {self.id} - {self.user.username} ({self.status})"

# 4. Denting / Painting Request
class DentingRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField()
    damage_image = models.ImageField(upload_to='denting_photos/', null=True, blank=True)
    vehicle_make = models.CharField(max_length=50)
    vehicle_model = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default='Pending Review')
    created_at = models.DateTimeField(auto_now_add=True)
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    

# 5. Spare Parts Catalog
class SparePart(models.Model):
    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=50, blank=True, null=True)
    model = models.CharField(max_length=50, blank=True, null=True)  # Added to match React filter
    year = models.CharField(max_length=10, blank=True, null=True)   # Added to match React filter
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='spare_parts/', null=True, blank=True)
    
    # New Stock Field
    stock = models.PositiveIntegerField(
        default=0, 
        validators=[MinValueValidator(0)],
        help_text="Current quantity in inventory"
    )

    @property
    def is_available(self):
        """Automatically returns True if stock is greater than zero."""
        return self.stock > 0

    def __str__(self):
        return f"{self.brand} {self.name} - Stock: {self.stock}"

    class Meta:
        ordering = ['-id']

# 6. Part Orders
class PartOrder(models.Model):
    ORDER_STATUS = (('Pending', 'Pending'), ('Confirmed', 'Confirmed'), ('Shipped', 'Shipped'), ('Delivered', 'Delivered'), ('Cancelled', 'Cancelled'))
    PAYMENT_STATUS = (('PENDING', 'Pending'), ('PAID', 'Paid'), ('FAILED', 'Failed'), ('REFUNDED', 'Refunded'))

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    part = models.ForeignKey(SparePart, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='Pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING')
    
    # Stripe Field
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

# 7. Service History (The Logbook)
class ServiceHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    services_rendered = models.TextField()
    total_paid = models.DecimalField(max_digits=10, decimal_places=2)
    odometer_reading = models.IntegerField(default=0)
    completion_date = models.DateTimeField(auto_now_add=True)
    admin_notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.vehicle.model} - {self.completion_date.date()}"


# --- AUTOMATION SIGNALS ---

@receiver(post_save, sender=Booking)
def create_service_history_on_completion(sender, instance, **kwargs):
    """
    Triggered when a booking is saved. If status is 'COMPLETED', 
    create a log in ServiceHistory.
    """
    if instance.status == 'COMPLETED':
        # Logic: Use final_amount if set, otherwise fallback to total_amount
        actual_cost = instance.final_amount if instance.final_amount is not None else instance.total_amount
        
        # Check for existing entry to prevent duplicates
        if not ServiceHistory.objects.filter(
            user=instance.user, 
            vehicle=instance.vehicle, 
            completion_date__date=instance.appointment_time.date(),
            total_paid=actual_cost
        ).exists():
            
            # Use a simpler way to join services if signal fires before M2M is ready
            # Note: In production, it's better to trigger this when payment is PAID
            service_list = instance.services.all()
            service_names = ", ".join([s.name for s in service_list]) if service_list else "General Service"
            
            ServiceHistory.objects.create(
                user=instance.user,
                vehicle=instance.vehicle,
                services_rendered=service_names,
                total_paid=actual_cost,
                odometer_reading=0, 
                admin_notes=f"Auto-generated from Booking #{instance.id}. Billing finalized."
            )

# Add these fields to handle the staff roles
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_mechanic = models.BooleanField(default=False)
    is_billing = models.BooleanField(default=False)
    is_ecommerce = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

# Trigger to create profile automatically when a user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
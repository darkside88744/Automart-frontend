from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from .models import Booking

@receiver(post_save, sender=Booking)
def handle_booking_notifications(sender, instance, created, **kwargs):
    # 1. NEW BOOKING LOGIC
    if created:
        subject = f"🚗 Booking Received: #{instance.id}"
        message = f"Hi {instance.user.username}, your booking for {instance.vehicle} is confirmed for {instance.appointment_time}."
        try:
            send_mail(subject, message, None, [instance.user.email])
        except Exception as e:
            print(f"Email error: {e}")

    # 2. PAYMENT SUCCESS LOGIC
    # We only want to send this if it's NOT a new creation (it's an update)
    # and the status is PAID.
    elif instance.payment_status == 'PAID':
        # To be extra safe, you could check if an email was already sent here
        subject = "✅ Payment Successful - AutoMart"
        message = f"Dear {instance.user.username}, we received your payment of ₹{instance.total_amount}."
        
        try:
            send_mail(subject, message, None, [instance.user.email])
        except Exception as e:
            print(f"Email error: {e}")
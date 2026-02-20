from django.contrib import admin

# Register your models here.

from .models import Vehicle, Service, Booking, SparePart, DentingRequest,PartOrder,ServiceHistory

admin.site.register(Vehicle)
admin.site.register(Service)
admin.site.register(Booking)
admin.site.register(SparePart)
admin.site.register(DentingRequest)
admin.site.register(PartOrder)
admin.site.register(ServiceHistory)



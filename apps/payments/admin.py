from django.contrib import admin
from .models import PaymentLink, Sale


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ["gateway_reference", "tenant", "amount", "currency", "status", "created_at", "paid_at"]
    list_filter = ["tenant", "status", "gateway"]
    search_fields = ["gateway_reference", "conversation__customer_wa_id"]
    readonly_fields = ["id", "created_at", "paid_at"]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "customer_wa_id", "amount_paid", "created_at"]
    list_filter = ["tenant"]
    search_fields = ["customer_wa_id"]
    readonly_fields = ["id", "created_at", "gateway_payload", "items_snapshot"]

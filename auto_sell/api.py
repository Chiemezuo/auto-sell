from ninja import NinjaAPI
from apps.catalog.api import router as catalog_router
from apps.conversations.api import router as webhooks_router
from apps.payments.api import router as payments_router

api = NinjaAPI(title="Auto-Sell API", version="1.0.0", docs_url="/docs")
api.add_router("/catalog/", catalog_router)
api.add_router("/webhooks/", webhooks_router)
api.add_router("/payments/", payments_router)

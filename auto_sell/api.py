from ninja import NinjaAPI
from apps.catalog.api import router as catalog_router

api = NinjaAPI(title="Auto-Sell API", version="1.0.0", docs_url="/docs")
api.add_router("/catalog/", catalog_router)

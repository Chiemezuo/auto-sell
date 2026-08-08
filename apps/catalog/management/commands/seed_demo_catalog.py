from django.core.management.base import BaseCommand, CommandError
from apps.tenants.models import Tenant
from apps.catalog.models import Product

# Illustrative NGN prices for testing negotiation/search/stock logic only —
# not verified against real current market rates. Adjust before relying on
# these for anything beyond bot testing.
DEMO_PRODUCTS = [
    {
        "name": "iPhone 15, 128GB",
        "description": "New, sealed. 6.1-inch Super Retina XDR, A16 Bionic, 48MP main camera, USB-C.",
        "price_min": 780_000, "price_max": 850_000,
        "stock_quantity": 0, "is_available": False,
    },
    {
        "name": "iPhone 14 Pro, 256GB",
        "description": "New, sealed. 6.1-inch Dynamic Island, A16 Bionic, 48MP ProRAW camera.",
        "price_min": 650_000, "price_max": 720_000,
        "stock_quantity": 4,
    },
    {
        "name": "iPhone 13, 128GB",
        "description": "New, sealed. 6.1-inch Super Retina XDR, A15 Bionic, dual 12MP camera.",
        "price_min": 450_000, "price_max": 500_000,
        "stock_quantity": 6,
    },
    {
        "name": "iPhone 13, 128GB (UK Used, Grade A)",
        "description": "UK Used, Grade A — minimal wear, battery health 88%+. 6.1-inch, A15 Bionic.",
        "price_min": 320_000, "price_max": 370_000,
        "stock_quantity": 3,
    },
    {
        "name": "iPhone 11, 64GB (UK Used, Grade B)",
        "description": "UK Used, Grade B — light scratches, fully functional. 6.1-inch Liquid Retina, A13 Bionic.",
        "price_min": 180_000, "price_max": 220_000,
        "stock_quantity": 1,
    },
    {
        "name": "Samsung Galaxy S23, 256GB",
        "description": "New, sealed. 6.1-inch Dynamic AMOLED 2X, Snapdragon 8 Gen 2, 50MP camera.",
        "price_min": 550_000, "price_max": 620_000,
        "stock_quantity": 3,
    },
    {
        "name": "Samsung Galaxy S21 Ultra, 256GB (UK Used, Grade A)",
        "description": "UK Used, Grade A. 6.8-inch QHD+ AMOLED, 108MP camera, S Pen support.",
        "price_min": 320_000, "price_max": 370_000,
        "stock_quantity": 2,
    },
    {
        "name": "Samsung Galaxy A54, 128GB",
        "description": "New, sealed. 6.4-inch Super AMOLED, 50MP OIS camera, 5000mAh battery.",
        "price_min": 280_000, "price_max": 320_000,
        "stock_quantity": 8,
    },
    {
        "name": "Samsung Galaxy A14, 64GB",
        "description": "New, sealed. 6.6-inch display, 50MP triple camera, 5000mAh battery.",
        "price_min": 140_000, "price_max": 165_000,
        "stock_quantity": 10,
    },
    {
        "name": "Google Pixel 7, 128GB (UK Used, Grade A)",
        "description": "UK Used, Grade A. 6.3-inch OLED, Google Tensor G2, 50MP camera, stock Android.",
        "price_min": 280_000, "price_max": 320_000,
        "stock_quantity": 1,
    },
    {
        "name": "Tecno Camon 20, 128GB",
        "description": "New, sealed. 6.67-inch AMOLED, 64MP camera with OIS, 5000mAh battery.",
        "price_min": 150_000, "price_max": 175_000,
        "stock_quantity": 12,
    },
    {
        "name": "Tecno Spark 10, 64GB",
        "description": "New, sealed. 6.6-inch HD+ display, 50MP camera, 5000mAh battery.",
        "price_min": 95_000, "price_max": 115_000,
        "stock_quantity": 15,
    },
    {
        "name": "Infinix Note 30, 128GB",
        "description": "New, sealed. 6.78-inch AMOLED, 108MP camera, 68W fast charging.",
        "price_min": 135_000, "price_max": 155_000,
        "stock_quantity": 9,
    },
    {
        "name": "Infinix Hot 40, 128GB",
        "description": "New, sealed. 6.78-inch display, 108MP camera, 5000mAh battery.",
        "price_min": 85_000, "price_max": 100_000,
        "stock_quantity": 14,
    },
    {
        "name": "itel A60, 32GB",
        "description": "New, sealed. 6.6-inch display, dual camera, 4000mAh battery. Entry-level.",
        "price_min": 45_000, "price_max": 55_000,
        "stock_quantity": 20,
    },
    {
        "name": "Xiaomi Redmi Note 12, 128GB",
        "description": "New, sealed. 6.67-inch AMOLED 120Hz, 48MP camera, 33W fast charging.",
        "price_min": 130_000, "price_max": 150_000,
        "stock_quantity": 7,
    },
    # --- Additional Apple ---
    {
        "name": "iPhone 15 Pro Max, 256GB",
        "description": "New, sealed. 6.7-inch Super Retina XDR, titanium frame, A17 Pro, 48MP camera.",
        "price_min": 1_100_000, "price_max": 1_250_000,
        "stock_quantity": 3,
    },
    {
        "name": "iPhone 14 Pro Max, 256GB",
        "description": "New, sealed. 6.7-inch Dynamic Island, A16 Bionic, 48MP ProRAW camera.",
        "price_min": 850_000, "price_max": 950_000,
        "stock_quantity": 2,
    },
    {
        "name": "iPhone 14, 128GB",
        "description": "New, sealed. 6.1-inch Super Retina XDR, A15 Bionic, dual 12MP camera.",
        "price_min": 550_000, "price_max": 620_000,
        "stock_quantity": 7,
    },
    {
        "name": "iPhone 13 Pro, 256GB",
        "description": "New, sealed. 6.1-inch ProMotion display, A15 Bionic, triple 12MP camera.",
        "price_min": 580_000, "price_max": 650_000,
        "stock_quantity": 4,
    },
    {
        "name": "iPhone 12, 128GB (UK Used, Grade A)",
        "description": "UK Used, Grade A — minimal wear, battery health 85%+. 6.1-inch, A14 Bionic.",
        "price_min": 260_000, "price_max": 300_000,
        "stock_quantity": 5,
    },
    {
        "name": "iPhone 12 Mini, 64GB (UK Used, Grade B)",
        "description": "UK Used, Grade B — visible wear, fully functional. 5.4-inch, A14 Bionic.",
        "price_min": 200_000, "price_max": 240_000,
        "stock_quantity": 3,
    },
    {
        "name": "iPhone SE (2022), 64GB",
        "description": "New, sealed. 4.7-inch Retina HD, A15 Bionic, Touch ID, single 12MP camera.",
        "price_min": 280_000, "price_max": 320_000,
        "stock_quantity": 6,
    },
    # --- Additional Samsung ---
    {
        "name": "Samsung Galaxy S24 Ultra, 512GB",
        "description": "New, sealed. 6.8-inch QHD+ AMOLED, Snapdragon 8 Gen 3, 200MP camera, S Pen.",
        "price_min": 1_300_000, "price_max": 1_450_000,
        "stock_quantity": 2,
    },
    {
        "name": "Samsung Galaxy S23 Ultra, 256GB",
        "description": "New, sealed. 6.8-inch QHD+ AMOLED, Snapdragon 8 Gen 2, 200MP camera, S Pen.",
        "price_min": 750_000, "price_max": 850_000,
        "stock_quantity": 3,
    },
    {
        "name": "Samsung Galaxy A34, 128GB",
        "description": "New, sealed. 6.6-inch Super AMOLED, 48MP OIS camera, 5000mAh battery.",
        "price_min": 220_000, "price_max": 255_000,
        "stock_quantity": 9,
    },
    {
        "name": "Samsung Galaxy M14, 128GB",
        "description": "New, sealed. 6.6-inch display, 50MP camera, 6000mAh battery.",
        "price_min": 130_000, "price_max": 150_000,
        "stock_quantity": 12,
    },
    # --- Additional Tecno ---
    {
        "name": "Tecno Camon 20 Pro, 256GB",
        "description": "New, sealed. 6.67-inch curved AMOLED, 64MP OIS camera, 5000mAh battery.",
        "price_min": 195_000, "price_max": 225_000,
        "stock_quantity": 6,
    },
    {
        "name": "Tecno Spark 10 Pro, 128GB",
        "description": "New, sealed. 6.8-inch display, 108MP camera, 5000mAh battery.",
        "price_min": 115_000, "price_max": 135_000,
        "stock_quantity": 10,
    },
    {
        "name": "Tecno Phantom V Flip, 256GB",
        "description": "New, sealed. 6.9-inch foldable AMOLED, 1.32-inch cover display, 64MP camera.",
        "price_min": 650_000, "price_max": 750_000,
        "stock_quantity": 1,
    },
    # --- Additional Infinix ---
    {
        "name": "Infinix Note 30 Pro, 256GB",
        "description": "New, sealed. 6.78-inch AMOLED, 108MP camera, 70W fast charging.",
        "price_min": 175_000, "price_max": 200_000,
        "stock_quantity": 8,
    },
    {
        "name": "Infinix Zero 30, 256GB",
        "description": "New, sealed. 6.78-inch curved AMOLED, 108MP OIS camera, 68W fast charging.",
        "price_min": 210_000, "price_max": 240_000,
        "stock_quantity": 5,
    },
    # --- Additional itel ---
    {
        "name": "itel P55, 128GB",
        "description": "New, sealed. 6.6-inch display, 50MP AI camera, 5000mAh battery.",
        "price_min": 65_000, "price_max": 78_000,
        "stock_quantity": 18,
    },
    # --- Additional Xiaomi / Poco ---
    {
        "name": "Xiaomi Redmi Note 13 Pro, 256GB",
        "description": "New, sealed. 6.67-inch AMOLED 120Hz, 200MP OIS camera, 67W fast charging.",
        "price_min": 195_000, "price_max": 225_000,
        "stock_quantity": 7,
    },
    {
        "name": "Xiaomi 13T, 256GB",
        "description": "New, sealed. 6.67-inch AMOLED 144Hz, Dimensity 8200 Ultra, Leica triple camera.",
        "price_min": 420_000, "price_max": 470_000,
        "stock_quantity": 3,
    },
    {
        "name": "Poco X6, 256GB",
        "description": "New, sealed. 6.67-inch AMOLED 120Hz, Dimensity 8300 Ultra, 64MP OIS camera.",
        "price_min": 240_000, "price_max": 270_000,
        "stock_quantity": 5,
    },
    # --- Additional Google ---
    {
        "name": "Google Pixel 8, 128GB",
        "description": "New, sealed. 6.2-inch OLED, Google Tensor G3, 50MP camera, stock Android.",
        "price_min": 480_000, "price_max": 540_000,
        "stock_quantity": 2,
    },
    # --- Oppo ---
    {
        "name": "Oppo Reno 11, 256GB",
        "description": "New, sealed. 6.7-inch AMOLED, 50MP portrait camera, 67W fast charging.",
        "price_min": 340_000, "price_max": 380_000,
        "stock_quantity": 4,
    },
    {
        "name": "Oppo A78, 128GB",
        "description": "New, sealed. 6.56-inch display, 50MP camera, 5000mAh battery.",
        "price_min": 165_000, "price_max": 190_000,
        "stock_quantity": 9,
    },
    {
        "name": "Oppo Find X6, 256GB (UK Used, Grade A)",
        "description": "UK Used, Grade A. 6.74-inch AMOLED, Hasselblad triple camera, 100W fast charging.",
        "price_min": 380_000, "price_max": 430_000,
        "stock_quantity": 2,
    },
    # --- Vivo ---
    {
        "name": "Vivo Y36, 128GB",
        "description": "New, sealed. 6.64-inch display, 50MP camera, 5000mAh battery.",
        "price_min": 145_000, "price_max": 170_000,
        "stock_quantity": 8,
    },
    {
        "name": "Vivo V29, 256GB",
        "description": "New, sealed. 6.78-inch curved AMOLED, 50MP OIS portrait camera, 80W fast charging.",
        "price_min": 310_000, "price_max": 350_000,
        "stock_quantity": 4,
    },
    # --- Nokia ---
    {
        "name": "Nokia 105 (2023)",
        "description": "New, sealed. Basic feature phone. Long-life battery, FM radio, torchlight.",
        "price_min": 12_000, "price_max": 16_000,
        "stock_quantity": 30,
    },
    {
        "name": "Nokia G22, 128GB",
        "description": "New, sealed. 6.5-inch HD+ display, 50MP camera, user-repairable design.",
        "price_min": 95_000, "price_max": 115_000,
        "stock_quantity": 6,
    },
    # --- Huawei ---
    {
        "name": "Huawei Nova 11, 256GB",
        "description": "New, sealed. 6.7-inch OLED, 60MP portrait camera, 66W fast charging.",
        "price_min": 320_000, "price_max": 360_000,
        "stock_quantity": 3,
    },
    # --- Tablets ---
    {
        "name": "Apple iPad 10th Gen, 64GB WiFi",
        "description": "New, sealed. 10.9-inch Liquid Retina, A14 Bionic, 12MP camera, USB-C.",
        "price_min": 480_000, "price_max": 540_000,
        "stock_quantity": 3,
    },
    {
        "name": "Samsung Galaxy Tab A9, 64GB",
        "description": "New, sealed. 8.7-inch display, quad speakers, 5100mAh battery.",
        "price_min": 150_000, "price_max": 175_000,
        "stock_quantity": 6,
    },
    # --- Smartwatches ---
    {
        "name": "Apple Watch Series 9, 41mm",
        "description": "New, sealed. Always-On Retina display, S9 chip, blood oxygen and ECG apps.",
        "price_min": 420_000, "price_max": 470_000,
        "stock_quantity": 0, "is_available": False,
    },
    {
        "name": "Samsung Galaxy Watch 6, 40mm",
        "description": "New, sealed. Super AMOLED display, body composition analysis, sleep tracking.",
        "price_min": 220_000, "price_max": 250_000,
        "stock_quantity": 5,
    },
    {
        "name": "Amazfit Bip 5 Smartwatch",
        "description": "New, sealed. 1.91-inch HD display, 120+ sports modes, 10-day battery life.",
        "price_min": 28_000, "price_max": 35_000,
        "stock_quantity": 15,
    },
    # --- Additional accessories ---
    {
        "name": "65W Fast Charger (USB-C, PD)",
        "description": "65W USB-C Power Delivery adapter. Fast-charges phones, tablets, and laptops.",
        "price_min": 15_000, "price_max": 20_000,
        "stock_quantity": 25,
    },
    {
        "name": "Leather Flip Case",
        "description": "PU leather flip case with card slot. Specify phone model when ordering.",
        "price_min": 6_000, "price_max": 10_000,
        "stock_quantity": None,
    },
    {
        "name": "Tempered Glass Screen Protector",
        "description": "9H hardness tempered glass, case-friendly edges. Specify phone model when ordering.",
        "price_min": 1_500, "price_max": 3_000,
        "stock_quantity": None,
    },
    {
        "name": "10,000mAh Power Bank",
        "description": "Compact power bank with dual USB output, LED battery indicator.",
        "price_min": 12_000, "price_max": 16_000,
        "stock_quantity": 20,
    },
    {
        "name": "20,000mAh Fast-Charging Power Bank",
        "description": "High-capacity power bank with 22.5W fast charge, USB-C and USB-A output.",
        "price_min": 22_000, "price_max": 28_000,
        "stock_quantity": 12,
    },
    {
        "name": "Wired Earphones (USB-C)",
        "description": "In-ear wired earphones with mic, USB-C connector.",
        "price_min": 4_000, "price_max": 7_000,
        "stock_quantity": None,
    },
    {
        "name": "Wireless Bluetooth Earbuds (TWS)",
        "description": "True wireless earbuds, touch controls, charging case, ~20hrs total battery.",
        "price_min": 15_000, "price_max": 25_000,
        "stock_quantity": 18,
    },
    {
        "name": "USB-C to USB-C Cable (1m)",
        "description": "Braided 1m USB-C to USB-C cable, supports fast charging and data transfer.",
        "price_min": 2_500, "price_max": 4_500,
        "stock_quantity": None,
    },
    {
        "name": "Car Phone Mount",
        "description": "Dashboard/air-vent phone mount, one-hand operation, adjustable clamp.",
        "price_min": 5_000, "price_max": 8_000,
        "stock_quantity": 10,
    },
    {
        "name": "Mini Bluetooth Speaker",
        "description": "Portable Bluetooth speaker, ~8hrs playtime, built-in mic for calls.",
        "price_min": 18_000, "price_max": 24_000,
        "stock_quantity": 8,
    },
    {
        "name": "20W Fast Charger (USB-C)",
        "description": "Genuine-spec 20W USB-C power adapter. Compatible with most modern phones.",
        "price_min": 8_000, "price_max": 12_000,
        "stock_quantity": None,
    },
    {
        "name": "Silicone Phone Case",
        "description": "Slim-fit silicone case, various colors. Specify phone model when ordering.",
        "price_min": 3_000, "price_max": 6_000,
        "stock_quantity": None,
    },
]


class Command(BaseCommand):
    help = "Seed a tenant's catalog with realistic (synthetic) phone-shop demo products for testing."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True, help="Slug of the tenant to seed products for")
        parser.add_argument("--clear", action="store_true", help="Delete this tenant's existing products first")

    def handle(self, *args, **options):
        slug = options["tenant_slug"]
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant with slug '{slug}'")

        if options["clear"]:
            deleted, _ = tenant.products.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing product(s) for '{slug}'"))

        created_count = 0
        for entry in DEMO_PRODUCTS:
            _, created = Product.objects.get_or_create(
                tenant=tenant,
                name=entry["name"],
                defaults={
                    "description": entry["description"],
                    "price_min": entry["price_min"],
                    "price_max": entry["price_max"],
                    "stock_quantity": entry["stock_quantity"],
                    "is_available": entry.get("is_available", True),
                },
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{slug}': {created_count} new product(s), "
            f"{len(DEMO_PRODUCTS) - created_count} already existed (skipped)."
        ))

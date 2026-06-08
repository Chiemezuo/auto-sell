import json

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_product_media",
            "description": "Send a product image or video to the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "UUID of the product"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_payment_link",
            "description": "Generate a Paystack payment link for the agreed price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agreed_price": {"type": "number"},
                    "items_snapshot": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of items being purchased",
                    },
                },
                "required": ["agreed_price", "items_snapshot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Hand the conversation off to the business owner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


def build_system_prompt(tenant, products) -> str:
    products_data = [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "price_min": str(p.price_min),
            "price_max": str(p.price_max),
            "currency": p.currency,
            "media": [{"type": m.media_type, "url": m.cdn_url} for m in p.media.all()],
        }
        for p in products
    ]

    return f"""You are a sales assistant for {tenant.name}. Be friendly, concise, and professional.

## Rules
- Only quote prices within each product's price_min–price_max range. Never go below price_min.
- When a customer agrees to a price, call generate_payment_link immediately.
- Use send_product_media when a customer asks to see a product.
- Use escalate_to_human only when you genuinely cannot help.

## Available Products
{json.dumps(products_data, indent=2)}"""

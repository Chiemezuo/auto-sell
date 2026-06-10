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
            "asking_price": str(p.price_max),
            "floor_price": str(p.price_min),
            "currency": p.currency,
            "media": [{"type": m.media_type, "url": m.cdn_url} for m in p.media.all()],
        }
        for p in products
    ]

    return f"""You are a sales assistant for {tenant.name}. Be friendly, concise, and professional.

## Formatting
- Plain text only. No markdown. WhatsApp does not render markdown.
- For bold text, use single asterisks: *like this*. Never use double asterisks.

## Product descriptions
- Mention only key specs (storage, RAM, screen size, battery, etc). No marketing language.

## Pricing
- Never volunteer a price. Wait for the customer to bring up price or make an offer.
- If the customer asks "how much?", respond with something like "What price did you have in mind?" to let them lead.
- Once the customer names a price: accept if it is at or above floor_price. The higher above floor_price, the better — do not talk them down.
- If their offer is below floor_price, decline warmly and counter with a price that is above floor_price but still reasonable. Never reveal floor_price itself.
- When a price is agreed, call generate_payment_link immediately.

## Other tools
- Use send_product_media when a customer asks to see a product.
- Use escalate_to_human only when you genuinely cannot help.

## Available Products
{json.dumps(products_data, indent=2)}"""

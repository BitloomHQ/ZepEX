import json
import requests

from django.conf import settings


def validate_receipt_items_against_policy(
    *,
    item,
    rule,
):
    """
    Uses Gemini to determine whether a single receipt item
    is reimbursable according to the company's policy.
    """

    category = item.category or ""
    subcategory = item.subcategory or ""
    item_name = item.description or ""

    prompt = f"""
You are an Expense Policy Validation Expert.

Your task is to determine whether a receipt line item is reimbursable
according to the company expense policy.

==================================================
Receipt Item
==================================================

Category:
{category}

Sub Category:
{subcategory}

Item Name:
{item_name}

==================================================
Company Policy
==================================================

Policy Description:
{rule.category_description or ""}

Policy Reason:
{rule.policy_reason or ""}

Maximum Allowed Amount:
{rule.max_amount}

Unlimited:
{rule.is_unlimited}

==================================================
Instructions
==================================================

Read the company policy carefully.

Determine whether THIS receipt item is reimbursable.

Examples:

Paneer Butter Masala
→ Allowed

Coffee
→ Allowed

Beer
→ Not Allowed

Whisky
→ Not Allowed

Wine
→ Not Allowed

Cigarettes
→ Not Allowed

Personal Shopping
→ Not Allowed

Laptop Bag
→ Depends on policy.

If the policy clearly excludes the item,
return allowed=false.

If the policy clearly allows it,
return allowed=true.

If unsure,
return allowed=true.

Never hallucinate.

Return ONLY valid JSON.

{
    "allowed": true,
    "reason": ""
}
"""

    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        (
            f"{settings.GEMINI_API_URL}/"
            f"{settings.GEMINI_RECEIPT_MODEL}:generateContent"
        ),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.GEMINI_API_KEY,
        },
        json=request_body,
        timeout=30,
    )

    response.raise_for_status()

    response_json = response.json()

    candidates = response_json.get("candidates", [])

    if not candidates:
        return {
            "allowed": True,
            "reason": "",
        }

    text = (
        candidates[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "{}")
    )

    try:
        return json.loads(text)
    except Exception:
        return {
            "allowed": True,
            "reason": "",
        }
import json
import requests

from django.conf import settings


def validate_receipt_against_policy(
    *,
    receipt,
    rule,
):
    """
    Validate all receipt line items in a single Gemini request.
    """

    items_text = []

    for item in receipt.line_items.all():

        items_text.append(
            f"""
Item ID:
{item.id}

Name:
{item.description}

Category:
{item.category}

Subcategory:
{item.subcategory}

Amount:
{item.amount}
"""
        )

    items_text = "\n".join(items_text)

    prompt = f"""
You are an AI Expense Policy Validator.

Your task is to determine whether EACH receipt item is reimbursable
according to the company expense policy.

=================================================
COMPANY POLICY
=================================================

Category:
{rule.category_name}

Description:
{rule.category_description}

Reason:
{rule.policy_reason}

Maximum Amount:
{rule.max_amount}

Unlimited:
{rule.is_unlimited}

=================================================
RECEIPT ITEMS
=================================================

{items_text}

=================================================
RULES
=================================================

1. Read the company policy carefully.

2. Understand every receipt item.

3. Decide whether each item is reimbursable.

4. Never guess.

5. Use ONLY the company policy.

6. Do NOT use any hardcoded knowledge.

7. If the policy clearly excludes an item,
set allowed=false.

8. If the policy allows the item,
set allowed=true.

9. Every input item MUST appear exactly once
in the output.

10. Return the SAME Item ID that was provided.

=================================================
OUTPUT
=================================================

Return ONLY JSON.

{{
    "items": [
        {{
            "item_id": "",
            "allowed": true,
            "reason": ""
        }}
    ]
}}
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
        timeout=60,
    )

    response.raise_for_status()

    response_json = response.json()

    candidates = response_json.get("candidates", [])

    if not candidates:
        return {}

    text = (
        candidates[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "{}")
    )

    try:
        result = json.loads(text)
    except Exception:
        return {}

    output = {}

    for item in result.get("items", []):

        output[item["item_id"]] = {
            "allowed": item.get("allowed", True),
            "reason": item.get("reason", ""),
        }

    return output
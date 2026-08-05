import json
import requests

from django.conf import settings


def validate_receipt_against_policy(
    *,
    items,
    rule,
):
    """
    Validate all receipt items belonging to a single policy category
    using one Gemini request.
    """

    items_text = []

    for index, item in enumerate(items, start=1):

        items_text.append(
            f"""
Item {index}

Name: {item.description}

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

Policy Category:
{rule.category.name}

Policy Description:
{rule.category_description}

Policy Reason:
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

6. Do NOT use hardcoded assumptions such as:
   - Beer is always rejected.
   - Coffee is always approved.

7. Reject an item ONLY if the company policy
   explicitly or logically excludes it.

8. If the policy allows meals, determine whether
   each food item qualifies.

9. If the policy excludes alcohol, reject only
   alcoholic beverages.

10. Every item must receive its own decision.

=================================================
OUTPUT
=================================================

Return ONLY JSON.

{{
    "items":[
        {{
            "name":"Paneer Butter Masala",
            "allowed":true,
            "reason":""
        }},
        {{
            "name":"Beer",
            "allowed":false,
            "reason":"Alcohol is excluded by company policy."
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

        output[item.get("name", "")] = {
            "allowed": item.get("allowed", True),
            "reason": item.get("reason", ""),
        }

    return output
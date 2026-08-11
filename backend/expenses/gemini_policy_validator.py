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
Item ID: {item.id}
Item Number: {index}

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

==================================================
COMPANY POLICY
==================================================

Policy Category:
{rule.category_name}

Policy Description:
{rule.category_description}

Policy Reason:
{rule.policy_reason}

Maximum Amount:
{rule.max_amount}

Unlimited:
{rule.is_unlimited}

==================================================
RECEIPT ITEMS
==================================================

{items_text}

==================================================
VALIDATION RULES
==================================================

1. Evaluate EVERY receipt item individually.

2. Every input Item ID MUST appear exactly once in the output.

3. Return the SAME Item ID provided in the input.

4. Use ONLY the company policy provided above.

5. Do NOT use hardcoded assumptions.

6. Do NOT assume that a category is reimbursable or
   non-reimbursable unless the company policy supports that decision.

7. If the company policy explicitly excludes an item,
   set "allowed" to false.

8. If the company policy explicitly allows an item,
   set "allowed" to true.

9. If the policy has a maximum amount and the item exceeds
   that maximum, consider the item according to the stated
   policy limit.

10. If "Unlimited" is true, do not reject an item because
    of an amount limit.

11. Consider the item's:
    - name
    - category
    - subcategory
    - amount

12. Do NOT change the receipt item's category or subcategory.

13. Do NOT invent policy rules.

14. Do NOT apply general knowledge unless it is explicitly
    supported by the company policy.

15. If the policy does not clearly allow or exclude the item,
    do not invent a reason. Use the safest interpretation
    supported by the policy.

16. Every item must receive its own decision.

17. The "reason" must briefly explain the decision using
    ONLY the company policy.

18. Do NOT return policy configuration errors.

19. Do NOT return:
    - "No policy configured"
    - "Policy not found"
    - "Duplicate receipt detected"
    - "Old bill"
    - "Over limit" unless the provided policy actually
      defines and triggers that limit.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY valid JSON.

{{
    "items": [
        {{
            "item_id": "ITEM_ID_FROM_INPUT",
            "allowed": true,
            "reason": ""
        }}
    ]
}}

IMPORTANT:

The number of output items MUST exactly match the number
of input receipt items.

Every input Item ID MUST appear exactly once.

Do not omit any item.

Do not create additional items.

Do not use item names as identifiers.
Use Item ID.
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

        item_id = str(item.get("item_id", "")).strip()

        if not item_id:
            continue

        output[item_id] = {
            "allowed": item.get("allowed", True),
            "reason": item.get("reason", ""),
        }

    return output
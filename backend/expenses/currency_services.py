from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone
from tenants.models import CompanyFinanceSettings, CompanyExchangeRate

def convert_currency(
    amount,
    from_currency,
    to_currency,
    company=None,
):
    amount = Decimal(str(amount or 0))
    from_currency = str(from_currency or "INR").upper()
    to_currency = str(to_currency or "INR").upper()

    if from_currency == to_currency:
        return {
            "success": True,
            "company_amount": amount.quantize(Decimal("0.01")),
            "company_currency": to_currency,
            "exchange_rate": Decimal("1"),
            "exchange_rate_date": timezone.now(),
            "exchange_rate_provider": settings.EXCHANGE_RATE_PROVIDER,
        }
    # ----------------------------------------
    # Company Custom Exchange Rate
    # ----------------------------------------

    if company:
        try:
            finance_settings = company.finance_settings

            if finance_settings.exchange_rate_source == "CUSTOM":
                custom_rate = CompanyExchangeRate.objects.get(
                    company=company,
                    from_currency__code=from_currency,
                    to_currency__code=to_currency,
                    is_active=True,
                )

                rate = custom_rate.exchange_rate

                converted_amount = amount * rate

                return {
                    "success": True,
                    "company_amount": converted_amount.quantize(
                        Decimal("0.01")
                    ),
                    "company_currency": to_currency,
                    "exchange_rate": rate,
                    "exchange_rate_date": timezone.now(),
                    "exchange_rate_provider": "Company Custom Rate",
                }

        except CompanyExchangeRate.DoesNotExist:
            return {
                "success": False,
                "error": (
                    f"No custom exchange rate found "
                    f"for {from_currency} → {to_currency}"
                ),
            }

        except CompanyFinanceSettings.DoesNotExist:
            pass

    if not settings.EXCHANGE_RATE_API_KEY:
        return {
            "success": False,
            "error": "Exchange rate API key is not configured.",
        }

    try:
        url = (
            f"{settings.EXCHANGE_RATE_API_URL.rstrip('/')}/"
            f"{settings.EXCHANGE_RATE_API_KEY}/latest/{from_currency}"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("result") != "success":
            return {
                "success": False,
                "error": data.get(
                    "error-type",
                    "Unable to fetch exchange rate.",
                ),
            }

        rates = data.get("conversion_rates", {})

        if to_currency not in rates:
            return {
                "success": False,
                "error": f"{to_currency} not found in conversion rates.",
            }

        rate = Decimal(str(rates[to_currency]))
        converted_amount = amount * rate

        return {
            "success": True,
            "company_amount": converted_amount.quantize(Decimal("0.01")),
            "company_currency": to_currency,
            "exchange_rate": rate,
            "exchange_rate_date": timezone.now(),
            "exchange_rate_provider": settings.EXCHANGE_RATE_PROVIDER,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }

from .base import BaseIntegrationProvider


PROVIDER_REGISTRY = {}


def register_provider(provider_name):
    """
    Register a provider implementation.
    """

    def decorator(provider_class):
        if not issubclass(
            provider_class,
            BaseIntegrationProvider,
        ):
            raise TypeError(
                "Provider must inherit from BaseIntegrationProvider."
            )

        PROVIDER_REGISTRY[provider_name] = provider_class

        return provider_class

    return decorator


def get_provider_class(provider_name):
    return PROVIDER_REGISTRY.get(
        provider_name.upper()
    )


def get_provider(provider_name, integration):
    provider_class = get_provider_class(provider_name)

    if not provider_class:
        raise ValueError(
            f"No implementation registered for {provider_name}."
        )

    return provider_class(integration)
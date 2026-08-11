from abc import ABC, abstractmethod


class BaseIntegrationProvider(ABC):

    def __init__(self, integration):
        self.integration = integration

    @abstractmethod
    def get_authorization_url(self, request):
        raise NotImplementedError

    @abstractmethod
    def exchange_code_for_token(self, code, request):
        raise NotImplementedError

    @abstractmethod
    def refresh_access_token(self):
        raise NotImplementedError

    @abstractmethod
    def test_connection(self):
        raise NotImplementedError

    @abstractmethod
    def sync(self):
        raise NotImplementedError
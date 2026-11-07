# apps/mpesa/providers/base.py
from abc import ABC, abstractmethod

class BaseProvider(ABC):
    def __init__(self, cfg):
        self.cfg = cfg

    @abstractmethod
    def initiate_payment(self, *, phone, amount, account_reference, description, callback_url):
        """Return dict with 'provider_ref' and 'raw'"""
        pass

    @abstractmethod
    def query_payment(self, *, provider_ref):
        """Return dict with 'status', 'code', 'amount', 'phone', 'raw'"""
        pass

    @abstractmethod
    def parse_webhook(self, request):
        """Return dict with 'provider_ref', 'status', 'code', 'amount', 'phone', etc."""
        pass
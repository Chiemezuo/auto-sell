from abc import ABC, abstractmethod


class PaymentGateway(ABC):
    @abstractmethod
    def initialize_transaction(self, amount: float, email: str, metadata: dict) -> dict:
        """Returns {"authorization_url": str, "reference": str}"""
        ...

    @abstractmethod
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        ...

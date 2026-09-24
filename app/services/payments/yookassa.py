"""Minimal YooKassa API client (no SDK or webhooks — status is checked by polling)."""

from __future__ import annotations

from typing import Any

import httpx

API_URL = "https://api.yookassa.ru/v3"


class YooKassaError(RuntimeError):
    pass


def rub(amount_rub: int) -> dict[str, str]:
    return {"value": f"{amount_rub}.00", "currency": "RUB"}


class YooKassaClient:
    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        return_url: str,
        receipt_email: str = "",
        vat_code: int = 1,
        base_url: str = API_URL,
        timeout: float = 20.0,
    ) -> None:
        self.return_url = return_url
        self.receipt_email = receipt_email
        self.vat_code = vat_code
        self._client = httpx.AsyncClient(
            base_url=base_url, auth=(shop_id, secret_key), timeout=httpx.Timeout(timeout, connect=10.0)
        )

    async def create_payment(
        self, amount_rub: int, description: str, metadata: dict[str, Any], idempotence_key: str
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "amount": rub(amount_rub),
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": self.return_url},
            "description": description[:128],
            "metadata": {k: str(v) for k, v in metadata.items()},
        }
        if self.receipt_email:
            body["receipt"] = {
                "customer": {"email": self.receipt_email},
                "items": [
                    {
                        "description": description[:128],
                        "quantity": "1.00",
                        "amount": rub(amount_rub),
                        "vat_code": self.vat_code,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            }
        return await self._request("POST", "/payments", json=body, headers={"Idempotence-Key": idempotence_key})

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            raise YooKassaError(f"YooKassa unreachable: {e!r}") from e
        if resp.status_code >= 400:
            raise YooKassaError(f"YooKassa HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()

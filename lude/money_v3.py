"""Lude Economy v3: exact monetary amounts, all balances expressed as integer cents.

Crypto prices remain INT$ per coin; quantities are rounded DOWN to 8 digits for
partial sales. This module does not migrate or mutate any user data.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

CENT = Decimal("0.01")
QUANTUM = Decimal("0.00000001")
MAX_SQLITE_INT = 2**63 - 1


def decimal(value) -> Decimal:
    if isinstance(value, float):
        value = str(value)
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("El importe debe ser finito.")
    return result


def cents(text: str, *, allow_zero: bool = False) -> int:
    """Parse an INT$ display amount strictly, without binary float rounding."""
    if isinstance(text, bool):
        raise ValueError("Importe inválido.")
    text = str(text).strip().replace(" ", "")
    if not text or text.count(",") > 1 or ("," in text and "." in text):
        raise ValueError("Usá un importe como 7500,25 (máximo dos decimales).")
    text = text.replace(",", ".")
    try:
        amount = decimal(text)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Importe inválido.") from exc
    if amount != amount.quantize(CENT):
        raise ValueError("Los importes admiten hasta dos decimales.")
    if amount < 0 or (not allow_zero and amount == 0):
        raise ValueError("El importe debe ser mayor que cero.")
    scaled = int(amount * 100)
    if scaled > MAX_SQLITE_INT:
        raise ValueError("El importe excede el límite permitido.")
    return scaled


def format_cents(value: int) -> str:
    amount = int(value)
    sign = "-" if amount < 0 else ""
    whole, fractional = divmod(abs(amount), 100)
    return f"INT$ {sign}{whole:,}".replace(",", ".") + f",{fractional:02d}"


def round_cents(value: Decimal) -> int:
    result = int((decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not -MAX_SQLITE_INT <= result <= MAX_SQLITE_INT:
        raise ValueError("Resultado monetario fuera del rango permitido.")
    return result


def safe_add(*amounts: int) -> int:
    total = sum(int(x) for x in amounts)
    if not -MAX_SQLITE_INT <= total <= MAX_SQLITE_INT:
        raise ValueError("El saldo resultante excede el rango permitido.")
    return total


def quantity_8(value) -> Decimal:
    qty = decimal(value)
    if qty < 0:
        raise ValueError("No se permiten unidades negativas.")
    return qty.quantize(QUANTUM, rounding=ROUND_DOWN)


@dataclass(frozen=True)
class SaleQuote:
    symbol: str
    quantity: Decimal
    price: Decimal
    gross_cents: int
    fee_cents: int
    judicial_withheld_cents: int
    credited_cents: int
    requested_cents: int | None
    destination: str
    available_quantity: Decimal
    cost_basis_cents: int

    @property
    def extra_cents(self) -> int:
        return max(0, self.credited_cents - (self.requested_cents or self.credited_cents))


def quote_sale(*, symbol: str, quantity: Decimal, available_quantity: Decimal,
               price, cost_basis_cents: int, fee_rate, judicial_rate,
               judicial_debt_cents: int, destination: str,
               requested_cents: int | None = None) -> SaleQuote:
    """Quote sale in cents; judicial withholding applies ONLY to positive gross profit."""
    available = decimal(available_quantity)
    qty = quantity_8(quantity)
    if qty <= 0 or qty > available:
        raise ValueError("Cantidad no disponible o demasiado pequeña.")
    price_dec = decimal(price)
    if price_dec <= 0:
        raise ValueError("La cotización no está disponible.")
    gross = round_cents(qty * price_dec)
    fee = max(1, round_cents(decimal(gross) / 100 * decimal(fee_rate)))
    cost_portion = (decimal(cost_basis_cents) * qty / available)
    profit = max(Decimal(0), decimal(gross) - cost_portion)
    withheld = min(max(0, int(judicial_debt_cents)), round_cents(profit / 100 * decimal(judicial_rate)))
    credited = max(0, gross - fee - withheld)
    if gross <= 0 or credited <= 0:
        raise ValueError("El importe de la venta es demasiado pequeño para cubrir los descuentos.")
    return SaleQuote(symbol, qty, price_dec, gross, fee, withheld, credited,
                     requested_cents, destination, available, int(cost_basis_cents))


def quote_net_sale(*, requested_cents: int, symbol: str, available_quantity,
                   price, cost_basis_cents: int, fee_rate, judicial_rate,
                   judicial_debt_cents: int, destination: str) -> SaleQuote:
    """Binary-search the minimal 1e-8 unit lot whose final credit meets the target.

    For any given available holding/cost basis and nonnegative rates <= 1, net
    proceeds are nondecreasing. Check the exact minimum at the chosen lot.
    """
    requested = int(requested_cents)
    if requested <= 0:
        raise ValueError("El neto solicitado debe ser mayor que cero.")
    available = quantity_8(available_quantity)
    max_lots = int(available / QUANTUM)
    if max_lots <= 0:
        raise ValueError("No tenés unidades vendibles con precisión de 8 decimales.")
    args = dict(symbol=symbol, available_quantity=decimal(available_quantity),
                price=price, cost_basis_cents=cost_basis_cents,
                fee_rate=fee_rate, judicial_rate=judicial_rate,
                judicial_debt_cents=judicial_debt_cents, destination=destination,
                requested_cents=requested)
    maximum = quote_sale(quantity=available, **args)
    if maximum.credited_cents < requested:
        raise ValueError("Tus unidades no alcanzan para el importe neto solicitado.")
    lo, hi = 1, max_lots
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            quote = quote_sale(quantity=QUANTUM * mid, **args)
            sufficient = quote.credited_cents >= requested
        except ValueError:
            sufficient = False
        if sufficient:
            hi = mid
        else:
            lo = mid + 1
    result = quote_sale(quantity=QUANTUM * lo, **args)
    if result.credited_cents < requested:
        raise ValueError("No se pudo obtener el neto solicitado.")
    return result

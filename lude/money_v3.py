"""Exact v3 money and eight-decimal crypto quotes; never mutates a database."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

CENT = Decimal("0.01")
QUANTUM = Decimal("0.00000001")
MAX_SQLITE_INT = 2**63 - 1
MIN_CRYPTO_FEE_CENTS = 100  # Preserve the former INT$ 1 minimum, not one cent.
_MONEY_INPUT = re.compile(r"(?:0|[1-9][0-9]*)(?:[.,][0-9]{1,2})?\Z", re.ASCII)


def decimal(value) -> Decimal:
    if isinstance(value, float):
        value = str(value)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("El importe debe ser numérico.") from exc
    if not result.is_finite():
        raise ValueError("El importe debe ser finito.")
    return result


def cents(text: str, *, allow_zero: bool = False) -> int:
    """Strict INT$ display input, rejecting grouping and exponents."""
    if isinstance(text, bool):
        raise ValueError("Importe inválido.")
    value = str(text).strip()
    if not _MONEY_INPUT.fullmatch(value):
        raise ValueError("Usá un importe como 7500,25 (máximo dos decimales).")
    integer_part, separator, fraction = value.replace(",", ".").partition(".")
    if len(integer_part) > 17:
        raise ValueError("El importe excede el límite permitido.")
    amount = int(integer_part) * 100 + int((fraction + "00")[:2] if separator else "00")
    if amount > MAX_SQLITE_INT:
        raise ValueError("El importe excede el límite permitido.")
    if amount == 0 and not allow_zero:
        raise ValueError("El importe debe ser mayor que cero.")
    return amount


def format_cents(value: int) -> str:
    amount = int(value)
    sign = "-" if amount < 0 else ""
    whole, fractional = divmod(abs(amount), 100)
    return f"INT$ {sign}{whole:,}".replace(",", ".") + f",{fractional:02d}"


def round_cents(value: Decimal) -> int:
    try:
        result = int((decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError("El importe monetario excede la precisión admitida.") from exc
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
    try:
        return qty.quantize(QUANTUM, rounding=ROUND_DOWN)
    except InvalidOperation as exc:
        raise ValueError("La cantidad cripto excede la precisión permitida.") from exc


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
    """Quote in cent units. Withholding applies only to positive gross profit."""
    available = decimal(available_quantity)
    qty = quantity_8(quantity)
    if qty <= 0 or qty > available:
        raise ValueError("Cantidad no disponible o demasiado pequeña.")
    price_dec = decimal(price)
    if price_dec <= 0:
        raise ValueError("La cotización no está disponible.")
    fee_rate, judicial_rate = decimal(fee_rate), decimal(judicial_rate)
    if not (0 <= fee_rate <= 1 and 0 <= judicial_rate <= 1):
        raise ValueError("Las tasas monetarias deben estar entre 0 y 100%.")
    if cost_basis_cents < 0 or judicial_debt_cents < 0:
        raise ValueError("Posición o deuda inválida; no se ejecutó la operación.")
    gross = round_cents(qty * price_dec)
    fee = max(MIN_CRYPTO_FEE_CENTS, round_cents(decimal(gross) / 100 * fee_rate))
    cost_portion = decimal(cost_basis_cents) * qty / available
    profit = max(Decimal(0), decimal(gross) - cost_portion)
    withheld = min(int(judicial_debt_cents), round_cents(profit / 100 * judicial_rate))
    credited = gross - fee - withheld
    if gross <= 0 or credited <= 0:
        raise ValueError("El importe de la venta es demasiado pequeño para cubrir los descuentos.")
    return SaleQuote(symbol, qty, price_dec, gross, fee, withheld, credited,
                     requested_cents, destination, available, int(cost_basis_cents))


def quote_net_sale(*, requested_cents: int, symbol: str, available_quantity,
                   price, cost_basis_cents: int, fee_rate, judicial_rate,
                   judicial_debt_cents: int, destination: str) -> SaleQuote:
    """Find the FIRST 1e-8 lot paying at least requested net after all deductions.

    Integer-cent fees and withholding can cause a one-cent downward jump at a
    gross-cent boundary. Plain binary search on rounded net is therefore NOT
    sufficient. Instead bracket using continuous monotonic proceeds and search
    each gross-cent bucket in ascending order. Net within one fixed-gross bucket
    is nondecreasing as the allocated cost basis increases with quantity.
    """
    requested = int(requested_cents)
    if requested <= 0:
        raise ValueError("El neto solicitado debe ser mayor que cero.")
    available = quantity_8(available_quantity)
    max_lots = int(available / QUANTUM)
    if max_lots <= 0:
        raise ValueError("No tenés unidades vendibles con precisión de 8 decimales.")
    fee_rate, judicial_rate = decimal(fee_rate), decimal(judicial_rate)
    if not (0 <= fee_rate <= 1 and 0 <= judicial_rate <= 1):
        raise ValueError("Tasa de comisión o retención inválida.")
    # When their sum exceeds 100% net proceeds need not be monotonic. Refuse an
    # unprovable exact-net quote rather than returning a potentially wrong lot.
    if fee_rate + judicial_rate > 1:
        raise ValueError("Las tasas configuradas no permiten garantizar una venta neta mínima; elegí unidades o porcentaje.")
    args = dict(symbol=symbol, available_quantity=decimal(available_quantity),
                price=price, cost_basis_cents=cost_basis_cents,
                fee_rate=fee_rate, judicial_rate=judicial_rate,
                judicial_debt_cents=judicial_debt_cents, destination=destination,
                requested_cents=requested)
    maximum = quote_sale(quantity=available, **args)
    if maximum.credited_cents < requested:
        raise ValueError("Tus unidades no alcanzan para el importe neto solicitado.")
    price_dec = decimal(price)
    cost_dec = decimal(cost_basis_cents)
    debt_dec = decimal(judicial_debt_cents)

    def lot_qty(lots):
        return QUANTUM * lots

    def gross(lots):
        return round_cents(lot_qty(lots) * price_dec)

    def continuous_net(lots):
        qty = lot_qty(lots)
        g = qty * price_dec * 100
        fee = max(Decimal(MIN_CRYPTO_FEE_CENTS), g * fee_rate)
        cost = cost_dec * qty / decimal(available_quantity)
        withheld = min(debt_dec, max(Decimal(0), g - cost) * judicial_rate)
        return g - fee - withheld

    def first_continuous(threshold):
        lo, hi = 1, max_lots
        while lo < hi:
            mid = (lo + hi) // 2
            if continuous_net(mid) >= threshold:
                hi = mid
            else:
                lo = mid + 1
        return lo

    # Three rounded components introduce less than two cents' absolute error.
    low_lot = first_continuous(Decimal(requested) - 2)
    high_lot = first_continuous(Decimal(requested) + 2)
    high_lot = min(max_lots, high_lot)
    min_gross, max_gross = gross(low_lot), gross(high_lot)
    if max_gross - min_gross > 512:
        raise ValueError("La cotización requiere demasiados escalones de redondeo; elegí unidades o porcentaje.")

    def first_gross_at_least(target, left, right):
        lo, hi = left, right
        while lo < hi:
            mid = (lo + hi) // 2
            if gross(mid) >= target:
                hi = mid
            else:
                lo = mid + 1
        return lo

    start = low_lot
    for g in range(min_gross, max_gross + 1):
        left = first_gross_at_least(g, start, high_lot + 1)
        if left > high_lot or gross(left) != g:
            continue
        end_exclusive = first_gross_at_least(g + 1, left, high_lot + 1)
        right = min(high_lot, end_exclusive - 1)
        # For fixed rounded gross, withholding only decreases as quantity grows.
        lo, hi = left, right + 1
        while lo < hi:
            mid = (lo + hi) // 2
            try:
                enough = quote_sale(quantity=lot_qty(mid), **args).credited_cents >= requested
            except ValueError:
                enough = False
            if enough:
                hi = mid
            else:
                lo = mid + 1
        if lo <= right:
            return quote_sale(quantity=lot_qty(lo), **args)
        start = max(start, end_exclusive)
    raise ValueError("No se pudo obtener un neto exacto con la posición disponible.")

"""Bond analytics calculations for yield, duration, and convexity.

Provides financial calculations for bond analysis including:
- Current Yield
- Yield to Maturity (YTM)
- Macaulay Duration
- Modified Duration
- Convexity
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from scipy.optimize import newton


@dataclass
class BondMetrics:
    """Complete bond analytics metrics.

    Attributes:
        current_yield: Annual coupon / current price (%)
        ytm: Yield to maturity (%)
        macaulay_duration: Weighted average time to receive cash flows (years)
        modified_duration: Price sensitivity to yield changes (years)
        convexity: Curvature of price-yield relationship
    """

    current_yield: Decimal
    ytm: Decimal | None
    macaulay_duration: Decimal | None
    modified_duration: Decimal | None
    convexity: Decimal | None


def calculate_current_yield(
    coupon_rate: Decimal,
    face_value: Decimal,
    current_price: Decimal,
) -> Decimal:
    """Calculate current yield for a bond.

    Current Yield = (Annual Coupon Payment / Current Price) * 100

    Args:
        coupon_rate: Annual coupon rate as percentage (e.g., 11.0 for 11%)
        face_value: Face value of the bond
        current_price: Current market price of the bond

    Returns:
        Current yield as percentage

    Example:
        >>> calculate_current_yield(
        ...     coupon_rate=Decimal("11.0"),
        ...     face_value=Decimal("1000"),
        ...     current_price=Decimal("950")
        ... )
        Decimal('11.58')  # (110 / 950) * 100
    """
    if current_price <= 0:
        raise ValueError("Current price must be positive")

    annual_coupon = face_value * (coupon_rate / Decimal("100"))
    current_yield = (annual_coupon / current_price) * Decimal("100")

    return current_yield.quantize(Decimal("0.01"))


def calculate_ytm(
    coupon_rate: Decimal,
    face_value: Decimal,
    current_price: Decimal,
    years_to_maturity: Decimal,
    payment_frequency: int = 2,
) -> Decimal | None:
    """Calculate Yield to Maturity (YTM) using Newton's method.

    YTM is the internal rate of return (IRR) if the bond is held to maturity.
    Uses numerical optimization to solve the bond pricing equation.

    Args:
        coupon_rate: Annual coupon rate as percentage (e.g., 11.0 for 11%)
        face_value: Face value of the bond
        current_price: Current market price of the bond
        years_to_maturity: Years until maturity
        payment_frequency: Payments per year (1=annual, 2=semi-annual, 4=quarterly)

    Returns:
        YTM as annual percentage, or None if calculation fails

    Example:
        >>> calculate_ytm(
        ...     coupon_rate=Decimal("11.0"),
        ...     face_value=Decimal("1000"),
        ...     current_price=Decimal("950"),
        ...     years_to_maturity=Decimal("3"),
        ...     payment_frequency=2
        ... )
        Decimal('12.47')  # Approximate
    """
    if current_price <= 0:
        raise ValueError("Current price must be positive")
    if years_to_maturity <= 0:
        raise ValueError("Years to maturity must be positive")
    if payment_frequency not in (1, 2, 4, 12):
        raise ValueError("Payment frequency must be 1, 2, 4, or 12")

    # Convert to float for numpy calculations
    coupon_rate_float = float(coupon_rate)
    face_value_float = float(face_value)
    current_price_float = float(current_price)
    years_float = float(years_to_maturity)

    # Calculate per-period values
    periods = int(years_float * payment_frequency)
    coupon_payment = (face_value_float * coupon_rate_float / 100) / payment_frequency

    # Bond pricing function: PV of coupons + PV of face value
    def bond_price(ytm_guess: float) -> float:
        """Calculate theoretical bond price given a YTM."""
        if ytm_guess <= -1:  # Prevent division by zero
            ytm_guess = -0.99

        period_rate = ytm_guess / payment_frequency

        # PV of coupon payments (annuity)
        if period_rate == 0:
            pv_coupons = coupon_payment * periods
        else:
            pv_coupons = coupon_payment * ((1 - (1 + period_rate) ** -periods) / period_rate)

        # PV of face value
        pv_face = face_value_float / ((1 + period_rate) ** periods)

        return pv_coupons + pv_face

    # Function to minimize: difference between calculated and actual price
    def price_diff(ytm_guess: float) -> float:
        return bond_price(ytm_guess) - current_price_float

    # Derivative for Newton's method (duration-based approximation)
    def price_diff_derivative(ytm_guess: float) -> float:
        period_rate = ytm_guess / payment_frequency
        if period_rate <= -1:
            period_rate = -0.99

        # Approximate derivative using duration
        duration = 0.0
        for t in range(1, periods + 1):
            pv = coupon_payment / ((1 + period_rate) ** t)
            duration += t * pv

        # Add face value contribution
        pv_face = face_value_float / ((1 + period_rate) ** periods)
        duration += periods * pv_face

        # Normalize by price
        current_p = bond_price(ytm_guess)
        if current_p > 0:
            duration = duration / current_p

        # Derivative of price with respect to yield
        return -duration * current_p / payment_frequency

    try:
        # Initial guess: approximate YTM formula
        # YTM ≈ [C + (F-P)/n] / [(F+P)/2]
        initial_guess = (
            (coupon_payment * payment_frequency)
            + ((face_value_float - current_price_float) / years_float)
        ) / ((face_value_float + current_price_float) / 2)

        # Use Newton's method to find YTM
        ytm_annual = newton(
            price_diff,
            x0=initial_guess,
            fprime=price_diff_derivative,
            maxiter=100,
            tol=1e-6,
        )

        # Convert to percentage
        ytm_pct = Decimal(str(ytm_annual * 100))
        return ytm_pct.quantize(Decimal("0.01"))

    except (RuntimeError, ValueError, ZeroDivisionError):
        # Calculation failed to converge or encountered error
        return None


def calculate_macaulay_duration(
    coupon_rate: Decimal,
    face_value: Decimal,
    ytm: Decimal,
    years_to_maturity: Decimal,
    payment_frequency: int = 2,
) -> Decimal:
    """Calculate Macaulay Duration.

    Macaulay Duration is the weighted average time to receive the bond's cash flows,
    where weights are the present values of each cash flow.

    Args:
        coupon_rate: Annual coupon rate as percentage
        face_value: Face value of the bond
        ytm: Yield to maturity as percentage
        years_to_maturity: Years until maturity
        payment_frequency: Payments per year

    Returns:
        Macaulay Duration in years
    """
    coupon_rate_float = float(coupon_rate)
    face_value_float = float(face_value)
    ytm_float = float(ytm) / 100  # Convert percentage to decimal
    years_float = float(years_to_maturity)

    periods = int(years_float * payment_frequency)
    coupon_payment = (face_value_float * coupon_rate_float / 100) / payment_frequency
    period_rate = ytm_float / payment_frequency

    # Calculate weighted average time
    weighted_time = 0.0
    total_pv = 0.0

    for t in range(1, periods + 1):
        # PV of this coupon payment
        pv_coupon = coupon_payment / ((1 + period_rate) ** t)
        time_in_years = t / payment_frequency

        weighted_time += time_in_years * pv_coupon
        total_pv += pv_coupon

    # Add face value at maturity
    pv_face = face_value_float / ((1 + period_rate) ** periods)
    weighted_time += years_float * pv_face
    total_pv += pv_face

    macaulay_duration = weighted_time / total_pv

    return Decimal(str(macaulay_duration)).quantize(Decimal("0.01"))


def calculate_modified_duration(
    macaulay_duration: Decimal,
    ytm: Decimal,
    payment_frequency: int = 2,
) -> Decimal:
    """Calculate Modified Duration.

    Modified Duration measures the percentage change in bond price
    for a 1% change in yield.

    Modified Duration = Macaulay Duration / (1 + YTM/frequency)

    Args:
        macaulay_duration: Macaulay duration in years
        ytm: Yield to maturity as percentage
        payment_frequency: Payments per year

    Returns:
        Modified Duration in years
    """
    ytm_decimal = ytm / Decimal("100")  # Convert percentage to decimal
    period_rate = ytm_decimal / Decimal(str(payment_frequency))

    modified_duration = macaulay_duration / (Decimal("1") + period_rate)

    return modified_duration.quantize(Decimal("0.01"))


def calculate_convexity(
    coupon_rate: Decimal,
    face_value: Decimal,
    ytm: Decimal,
    years_to_maturity: Decimal,
    payment_frequency: int = 2,
) -> Decimal:
    """Calculate Convexity.

    Convexity measures the curvature of the price-yield relationship.
    Higher convexity means the bond price is less sensitive to large yield changes.

    Args:
        coupon_rate: Annual coupon rate as percentage
        face_value: Face value of the bond
        ytm: Yield to maturity as percentage
        years_to_maturity: Years until maturity
        payment_frequency: Payments per year

    Returns:
        Convexity
    """
    coupon_rate_float = float(coupon_rate)
    face_value_float = float(face_value)
    ytm_float = float(ytm) / 100  # Convert percentage to decimal
    years_float = float(years_to_maturity)

    periods = int(years_float * payment_frequency)
    coupon_payment = (face_value_float * coupon_rate_float / 100) / payment_frequency
    period_rate = ytm_float / payment_frequency

    # Calculate bond price
    if period_rate == 0:
        bond_price = coupon_payment * periods + face_value_float
    else:
        pv_coupons = coupon_payment * ((1 - (1 + period_rate) ** -periods) / period_rate)
        pv_face = face_value_float / ((1 + period_rate) ** periods)
        bond_price = pv_coupons + pv_face

    # Calculate convexity
    convexity_sum = 0.0

    for t in range(1, periods + 1):
        pv = coupon_payment / ((1 + period_rate) ** t)
        convexity_sum += t * (t + 1) * pv

    # Add face value contribution
    pv_face = face_value_float / ((1 + period_rate) ** periods)
    convexity_sum += periods * (periods + 1) * pv_face

    # Normalize
    convexity = convexity_sum / (bond_price * ((1 + period_rate) ** 2) * (payment_frequency**2))

    return Decimal(str(convexity)).quantize(Decimal("0.01"))


def calculate_bond_metrics(
    coupon_rate: Decimal,
    face_value: Decimal,
    current_price: Decimal,
    maturity_date: date,
    settlement_date: date,
    payment_frequency: int = 2,
) -> BondMetrics:
    """Calculate complete bond analytics metrics.

    Args:
        coupon_rate: Annual coupon rate as percentage (e.g., 11.0)
        face_value: Face value of the bond
        current_price: Current market price
        maturity_date: Bond maturity date
        settlement_date: Settlement/valuation date (typically today)
        payment_frequency: Payments per year (1, 2, 4, or 12)

    Returns:
        BondMetrics with all calculated values

    Example:
        >>> from datetime import date
        >>> metrics = calculate_bond_metrics(
        ...     coupon_rate=Decimal("11.0"),
        ...     face_value=Decimal("1000"),
        ...     current_price=Decimal("950"),
        ...     maturity_date=date(2027, 12, 31),
        ...     settlement_date=date(2025, 1, 1),
        ...     payment_frequency=2
        ... )
        >>> print(f"Current Yield: {metrics.current_yield}%")
        >>> print(f"YTM: {metrics.ytm}%")
    """
    # Calculate years to maturity
    days_to_maturity = (maturity_date - settlement_date).days
    years_to_maturity = Decimal(str(days_to_maturity / 365.25))

    if years_to_maturity <= 0:
        raise ValueError("Bond has already matured")

    # Calculate current yield
    current_yield = calculate_current_yield(coupon_rate, face_value, current_price)

    # Calculate YTM
    ytm = calculate_ytm(
        coupon_rate,
        face_value,
        current_price,
        years_to_maturity,
        payment_frequency,
    )

    # Calculate duration and convexity (only if YTM calculated successfully)
    if ytm is not None:
        macaulay_dur = calculate_macaulay_duration(
            coupon_rate,
            face_value,
            ytm,
            years_to_maturity,
            payment_frequency,
        )

        modified_dur = calculate_modified_duration(
            macaulay_dur,
            ytm,
            payment_frequency,
        )

        convexity = calculate_convexity(
            coupon_rate,
            face_value,
            ytm,
            years_to_maturity,
            payment_frequency,
        )
    else:
        macaulay_dur = None
        modified_dur = None
        convexity = None

    return BondMetrics(
        current_yield=current_yield,
        ytm=ytm,
        macaulay_duration=macaulay_dur,
        modified_duration=modified_dur,
        convexity=convexity,
    )

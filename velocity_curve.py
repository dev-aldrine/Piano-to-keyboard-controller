import math
from typing import Dict, Callable

def apply_linear(v: float) -> float:
    return v

def apply_ease_in(v: float) -> float:
    # Quadratic Ease In: softer response on light touch, ramp up on hard hit
    return v * v

def apply_ease_out(v: float) -> float:
    # Quadratic Ease Out: louder/more responsive on light touch
    return math.sqrt(v) if v > 0 else 0.0

def apply_ease_in_out(v: float) -> float:
    # S-Curve: compressed dynamics at extremes, sensitive in mid-range
    if v < 0.5:
        return 2.0 * v * v
    else:
        return 1.0 - math.pow(-2.0 * v + 2.0, 2.0) / 2.0

def apply_exponential(v: float) -> float:
    # Cubic Ease In: very quiet pianissimo, sharp explosive fortissimo
    return v * v * v

def apply_logarithmic(v: float) -> float:
    # High sensitivity / soft touch curve
    return math.pow(v, 0.3333)

def apply_compressed(v: float) -> float:
    # Studio compression: boosts quiet notes, clamps high velocity (range ~ 0.35 to 0.95)
    return 0.35 + (v * 0.6)

VELOCITY_CURVES: Dict[str, Callable[[float], float]] = {
    "linear": apply_linear,
    "ease_in": apply_ease_in,
    "ease_out": apply_ease_out,
    "ease_in_out": apply_ease_in_out,
    "exponential": apply_exponential,
    "logarithmic": apply_logarithmic,
    "compressed": apply_compressed
}

def transform_velocity(raw_velocity: int, curve_name: str = "linear") -> int:
    '''
    Transforms raw MIDI velocity (1 to 127) using the selected velocity easing curve.
    Returns transformed velocity integer clamped between 1 and 127.
    '''
    if raw_velocity <= 0:
        return 0
    
    # Normalize to 0.0 - 1.0
    norm_v = min(1.0, max(0.0, raw_velocity / 127.0))
    curve_func = VELOCITY_CURVES.get(curve_name.lower(), apply_linear)
    transformed_norm = curve_func(norm_v)
    
    # Scale back to 1 - 127
    result = int(round(transformed_norm * 127.0))
    return max(1, min(127, result))

from enum import IntFlag

class LinkStrategy(IntFlag):
    NONE = 0
    OMC  = 1 << 0
    NC   = 1 << 1
    NCC  = 1 << 2
    LCBA = 1 << 3
    LC   = 1 << 4
    MAX  = 1 << 5

    ALL = OMC | NC | NCC | LCBA | LC | MAX


# Single source of truth for external keys (config/csv/json/etc.)
STRATEGY_KEYS: dict[LinkStrategy, str] = {
    LinkStrategy.OMC: "omc",
    LinkStrategy.NC: "nc",
    LinkStrategy.NCC: "ncc",
    LinkStrategy.LCBA: "lcba",
    LinkStrategy.LC: "lc",
    LinkStrategy.MAX: "max",
}

# Reverse lookup (also no hardcoding elsewhere)
KEY_TO_STRATEGY: dict[str, LinkStrategy] = {
    v: k for k, v in STRATEGY_KEYS.items()
}

def strategy_key(strategy: LinkStrategy) -> str:
    """Return the external key for a single strategy (not a combined mask)."""
    if strategy == LinkStrategy.NONE or (strategy & (strategy - 1)) != 0:
        raise ValueError(f"Expected a single strategy, got: {strategy}")
    return STRATEGY_KEYS[strategy]


def strategies_from_keys(keys: list[str]) -> LinkStrategy:
    mask = LinkStrategy.NONE
    for key in keys:
        mask |= KEY_TO_STRATEGY[key.lower()]
    return mask


def keys_from_mask(mask: LinkStrategy) -> list[str]:
    return [
        STRATEGY_KEYS[s]
        for s in STRATEGY_KEYS
        if s & mask
    ]


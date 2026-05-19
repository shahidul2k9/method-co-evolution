from enum import IntFlag

class LinkStrategy(IntFlag):
    NONE = 0
    OMC  = 1 << 0
    NC   = 1 << 1
    NCC  = 1 << 2
    LCBA = 1 << 3
    LC   = 1 << 4
    MAX  = 1 << 5
    LCS_U = 1 << 6
    LCS_B = 1 << 7
    LEVEN = 1 << 8
    TARANTULA = 1 << 9
    TFIDF = 1 << 10
    COMBINED = 1 << 11
    LLM_GPT_OSS_20B  = 1 << 12
    LLM_GPT_OSS_120B  = 1 << 13
    LLM_QWEN_2D5B  = 1 << 14
    TESTLINKER = 1 << 15
    TESTLINKERV2 = 1 << 16

    ALL = (
        OMC
        | NC
        | NCC
        | LCBA
        | LC
        | MAX
        | LCS_U
        | LCS_B
        | LEVEN
        | TARANTULA
        | TFIDF
        | COMBINED
        | LLM_GPT_OSS_20B
        | LLM_GPT_OSS_120B
        | LLM_QWEN_2D5B
        | TESTLINKER
        | TESTLINKERV2
    )


# Single source of truth for external keys (config/csv/json/etc.)
STRATEGY_KEYS: dict[LinkStrategy, str] = {
    LinkStrategy.OMC: "omc",
    LinkStrategy.NC: "nc",
    LinkStrategy.NCC: "ncc",
    LinkStrategy.LCBA: "lcba",
    LinkStrategy.LC: "lc",
    LinkStrategy.MAX: "max",
    LinkStrategy.LCS_U: "lcs-u",
    LinkStrategy.LCS_B: "lcs-b",
    LinkStrategy.LEVEN: "leven",
    LinkStrategy.TARANTULA: "tarantula",
    LinkStrategy.TFIDF: "tfidf",
    LinkStrategy.COMBINED: "combined",
    LinkStrategy.LLM_GPT_OSS_20B: "gpt-oss-20b",
    LinkStrategy.LLM_GPT_OSS_120B: "gpt-oss-120b",
    LinkStrategy.LLM_QWEN_2D5B: "qwen-2d5b",
    LinkStrategy.TESTLINKER: "testlinker",
    LinkStrategy.TESTLINKERV2: "testlinkerv2",
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

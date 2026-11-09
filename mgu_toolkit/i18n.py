_LANG = "pl"


def set_language(lang):
    global _LANG
    _LANG = "en" if str(lang).lower().startswith("en") else "pl"


def language():
    return _LANG


def tr(pl, en):
    return en if _LANG == "en" else pl

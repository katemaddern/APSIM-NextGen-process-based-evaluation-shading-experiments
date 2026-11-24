"""
config_loader.py
-----------------
Loads the shared paper_2 path configuration from config.sh so that
python scripts use exactly the same paths (and constants) as the
shell/sbatch scripts, with a single source of truth (config.sh).

It works by sourcing config.sh in a real bash subshell and reading back
the resulting environment — so any variable defined with `export` in
config.sh (including ones built from other variables, e.g.
MET_RAW_DIR="$MET_FILES_DIR/raw_data") is resolved correctly.

TYPE COERCION
-------------
Everything coming back from `env` is a plain string. To make numeric
constants (e.g. START_OF_EXP_YEAR="1990") usable as real ints/floats in
python without manual casting everywhere, this loader coerces values
that look like whole numbers or decimals into int/float.

This is done SAFELY: a value is only ever coerced if the *entire*
string matches a strict numeric pattern (optional sign, digits, at most
one decimal point, nothing else). Paths, filenames, globs, and anything
containing "/", letters, or underscores are left as plain strings —
they simply never match the pattern, so there's no risk of a path like
"apsim_2026_09_8109_0.sif" being misinterpreted as a number.

Examples:
    "1990"        -> 1990   (int)
    "315"         -> 315    (int)
    "0.5"         -> 0.5    (float)
    "-3"          -> -3     (int)
    "/a/b/c"      -> "/a/b/c"                 (unchanged, has "/")
    "co2_mm.csv"  -> "co2_mm.csv"             (unchanged, has letters)
    "1990_v2"     -> "1990_v2"                (unchanged, has letters)

USAGE in a python job script
-----------------------------
    import sys, os
    sys.path.insert(0, "$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments")
    from config_loader import cfg

    print(cfg.DATA_BASE)              # attribute access -> str (path)
    print(cfg["MET_RAW_DIR"])         # dict-style access also works
    print(cfg.START_OF_EXP_YEAR)      # -> int, e.g. 1990
    folder = cfg.APSIM_TEMPLATES_BEFORE_CHECKING_DIR

To point at a different config.sh (e.g. for testing, or a future
re-run in another location) without editing this file, set:
    export PAPER1_CONFIG=/path/to/other_config.sh
before running the python script, or pass config_path= explicitly:
    from config_loader import load_config
    cfg = load_config("/path/to/other_config.sh")

If you ever need the raw, un-coerced string form of a value (e.g. to
guarantee a leading zero like "007" is preserved), use:
    cfg.raw("START_OF_EXP_YEAR")
"""

import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

# Default: config.sh living next to this file.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.sh"

# Strict "this whole string is a number" pattern:
#   optional +/-, digits, optional single decimal point + digits.
# Anything with a "/", letters, underscores, multiple dots, etc. will
# NOT match — which is exactly what keeps paths/filenames untouched.
_NUMERIC_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


class Config(SimpleNamespace):
    """SimpleNamespace with extra dict-style access: cfg['KEY'] as well as cfg.KEY.

    Keeps both the coerced value (used for normal attribute/item access)
    and the original raw string (accessible via .raw(key)), in case a
    script ever needs the exact untouched string.
    """

    def __init__(self, _raw=None, **kwargs):
        super().__init__(**kwargs)
        # Stored via object.__setattr__ so it doesn't become a "cfg.XXX"
        # attribute itself and doesn't get swept up in as_dict().
        object.__setattr__(self, "_raw_values", _raw or {})

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __contains__(self, key):
        return hasattr(self, key)

    def raw(self, key):
        """Return the original, un-coerced string value for `key`."""
        return self._raw_values[key]

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if k != "_raw_values"}


def _extract_exported_keys(config_path: Path) -> set:
    """Find every `export VAR=...` name declared in config.sh, so we only
    pull those variables out of the environment (and not unrelated ones
    like PATH, HOME, etc. that also show up in `env`)."""
    keys = set()
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "):
                key = line[len("export "):].split("=")[0].strip()
                if key:
                    keys.add(key)
    return keys


def _coerce(value: str):
    """Convert `value` to int/float ONLY if the entire string is numeric.
    Anything else (paths, filenames, globs, plain words) is returned
    unchanged as a string. See module docstring for examples.
    """
    if not _NUMERIC_RE.match(value):
        return value
    if "." in value:
        return float(value)
    return int(value)


def load_config(config_path=None) -> Config:
    config_path = Path(config_path or os.environ.get("PAPER1_CONFIG", _DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        raise FileNotFoundError(f"paper_1 config file not found: {config_path}")

    exported_keys = _extract_exported_keys(config_path)

    # Source config.sh in a clean bash subshell, then dump the environment.
    cmd = f'source "{config_path}" && env'
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True, text=True, check=True,
    )

    raw_values = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key in exported_keys:
            raw_values[key] = value

    missing = exported_keys - raw_values.keys()
    if missing:
        raise RuntimeError(f"Failed to resolve config variables: {sorted(missing)}")

    coerced_values = {key: _coerce(val) for key, val in raw_values.items()}

    config_obj = Config(_raw=raw_values, **coerced_values)

    # SITE_LIST is a plain bash array in config.sh, not an `export`ed
    # scalar, so it never shows up in `env` and config_loader can't see
    # it via the normal path above (bash can't reliably export arrays
    # through the environment at all). Instead, config.sh exports
    # SITES_FILE pointing at a plain text file (one site per line, in
    # order) which both bash (`mapfile -t SITE_LIST < "$SITES_FILE"`)
    # and python read independently — same order, same single source
    # of truth, no drift.
    if hasattr(config_obj, "SITES_FILE"):
        sites_path = Path(config_obj.SITES_FILE)
        if not sites_path.is_file():
            raise FileNotFoundError(f"SITES_FILE not found: {sites_path}")
        with open(sites_path) as f:
            site_list = [line.strip() for line in f if line.strip()]
        config_obj.SITE_LIST = site_list

    # SITE_ORDER (analysis order) is a plain comma-separated scalar
    # export directly in config.sh — e.g.
    #   export SITE_ORDER="waikerie,mildura,birchip,..."
    # Unlike SITE_LIST it does NOT need a separate file: as a scalar
    # string it comes through `env` like any other export, so this
    # just needs splitting into a list. Deliberately kept independent
    # from SITE_LIST — processing order and analysis order are allowed
    # to differ.
    if hasattr(config_obj, "SITE_ORDER"):
        raw_order = config_obj.SITE_ORDER
        config_obj.SITE_ORDER = [s.strip() for s in raw_order.split(",") if s.strip()]

    object.__setattr__(config_obj, "_config_path", str(config_path))
        
    return config_obj


# Load once at import time so `from config_loader import cfg` just works.
cfg = load_config()


if __name__ == "__main__":
    # Quick manual sanity check: prints every var with its python type,
    # so you can eyeball that paths stayed strings and numbers became
    # int/float. Run with: python config_loader.py
    for k, v in sorted(cfg.as_dict().items()):
        print(f"{k:45s} {type(v).__name__:6s} {v!r}")
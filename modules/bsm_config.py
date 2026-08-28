# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Blade strike modelling configuration files.

Plain INI text files (`[fish]`/`[pump]`/`[blade]`/`[observed]` sections) -
the same shape the standalone `/Scripts/Mathematical BSM/Project` scripts
use (`pump_config/*.txt`), so a config written for one of those scripts
loads straight into Calculator unchanged. Discovered from
`input_data/BSM_config/*.txt`, listed in a combo above the Fish section -
the same "pick from a folder" shape as `LibrarySelector`, just for a plain
folder of config files rather than a sensor library.
"""
import configparser
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "input_data" / "BSM_config"

_BLADE_KEYS = ("rttr", "d_vals", "beta_vals", "delta_vals")


def list_configs():
    """Every *.txt file in CONFIG_DIR, sorted by name."""
    if not CONFIG_DIR.exists():
        return []
    return sorted(CONFIG_DIR.glob("*.txt"))


def load_config(path) -> dict:
    """Parse one config file into a `bsm_model.compute()`-shaped dict.

    Raises on a missing required section/key - the caller should show the
    exception message directly, it already names the file and field.
    """
    cp = configparser.ConfigParser()
    # keep option names case-sensitive - [pump] deliberately has both a
    # lower-case n (blade count) and upper-case N (shaft speed rpm), which
    # ConfigParser's default lower-casing would collide into one key
    cp.optionxform = str
    read = cp.read(path)
    if not read:
        raise ValueError(f"Could not read {path}")

    fish, pump, blade = cp["fish"], cp["pump"], cp["blade"]
    result = {
        "lf": fish.getfloat("lf"), "bf": fish.getfloat("bf"),
        "species": fish.get("species", "scaly").strip(),
        "wf": fish.getfloat("wf"), "alpha": fish.getfloat("alpha"),
        "eel_vcrit": fish.getfloat("eel_vcrit"),
        "n": pump.getint("n"), "N": pump.getfloat("N"),
        "Q": pump.getfloat("Q"), "r": pump.getfloat("r"),
        "bh": pump.getfloat("bh"),
    }
    for key in _BLADE_KEYS:
        result[key] = [float(x) for x in blade.get(key).split(",")]

    result["use_observed"] = False
    result["total"] = 0
    result["strike"] = 0
    if cp.has_section("observed"):
        obs = cp["observed"]
        result["use_observed"] = obs.getboolean("use_observed", fallback=False)
        result["total"] = obs.getint("total", fallback=0)
        result["strike"] = obs.getint("strike", fallback=0)
    return result

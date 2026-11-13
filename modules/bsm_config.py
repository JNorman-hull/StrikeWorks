"""Blade strike model configuration files: INI text with [fish], [pump],
[blade] and optional [observed] sections, read from
input_data/BSM_config/*.txt. Same format as the standalone Mathematical
BSM scripts' pump_config/*.txt."""
import configparser

from . import settings

# shipped presets, always under the app root (not the user's input data
# folder, which can be anywhere)
CONFIG_DIR = settings.app_root() / "input_data" / "BSM_config"

_BLADE_KEYS = ("rttr", "d_vals", "beta_vals", "delta_vals")


def list_configs():
    """Every *.txt file in CONFIG_DIR, sorted by name."""
    if not CONFIG_DIR.exists():
        return []
    return sorted(CONFIG_DIR.glob("*.txt"))


def load_config(path) -> dict:
    """Parse one config file into the dict `bsm_model.compute()` takes.
    Raises on a missing section or key."""
    cp = configparser.ConfigParser()
    # case-sensitive option names: [pump] has both n (blade count) and N
    # (shaft speed, rpm)
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

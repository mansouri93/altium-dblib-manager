# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class MetricPrefix:
    symbol: str
    name: str
    factor: float
    display_label: str

PREFIX_MAP: dict[str, MetricPrefix] = {
    "T": MetricPrefix("T", "Tera", 1e12, "T (10¹²)"),
    "G": MetricPrefix("G", "Giga", 1e9, "G (10⁹)"),
    "M": MetricPrefix("M", "Mega", 1e6, "M (10⁶)"),
    "k": MetricPrefix("k", "kilo", 1e3, "k (10³)"),
    "": MetricPrefix("", "Base", 1.0, "(none) 10⁰"),
    "m": MetricPrefix("m", "milli", 1e-3, "m (10⁻³)"),
    "µ": MetricPrefix("µ", "micro", 1e-6, "µ (10⁻⁶)"),
    "n": MetricPrefix("n", "nano", 1e-9, "n (10⁻⁹)"),
    "p": MetricPrefix("p", "pico", 1e-12, "p (10⁻¹²)"),
    "f": MetricPrefix("f", "femto", 1e-15, "f (10⁻¹⁵)"),
}

# Ordered list from high to low for UI drop-down
ALL_PREFIX_SYMBOLS: list[str] = ["G", "M", "k", "", "m", "µ", "n", "p", "f"]

@dataclass(frozen=True)
class PhysicalUnit:
    symbol: str
    name: str
    description: str
    aliases: list[str]

STANDARD_UNITS: dict[str, PhysicalUnit] = {
    "Ω": PhysicalUnit("Ω", "Ohm", "Resistance", ["ohm", "ohms", "r", "ω", "o"]),
    "F": PhysicalUnit("F", "Farad", "Capacitance", ["farad", "farads", "f"]),
    "H": PhysicalUnit("H", "Henry", "Inductance", ["henry", "henries", "h"]),
    "V": PhysicalUnit("V", "Volt", "Voltage", ["volt", "volts", "v"]),
    "A": PhysicalUnit("A", "Ampere", "Current", ["amp", "amps", "ampere", "a"]),
    "W": PhysicalUnit("W", "Watt", "Power", ["watt", "watts", "w"]),
    "Hz": PhysicalUnit("Hz", "Hertz", "Frequency", ["hertz", "hz"]),
    "%": PhysicalUnit("%", "Percent", "Tolerance", ["percent", "pct", "%"]),
    "dB": PhysicalUnit("dB", "Decibel", "Gain / Attenuation", ["decibel", "decibels", "db"]),
    "s": PhysicalUnit("s", "Second", "Time / Delay", ["sec", "second", "seconds", "s"]),
    "°C": PhysicalUnit("°C", "Celsius", "Temperature", ["c", "degc", "celsius", "°c"]),
}

# Default unit rules per category/table
DEFAULT_TABLE_CONFIG: dict[str, dict[str, dict[str, Any]]] = {
    "Resistor": {
        "Value": {
            "default_unit": "Ω",
            "allowed_units": ["Ω"],
            "allowed_prefixes": ["G", "M", "k", "", "m"],
            "allow_fraction": False,
        },
        "Power": {
            "default_unit": "W",
            "allowed_units": ["W"],
            "allowed_prefixes": ["", "m"],
            "allow_fraction": True,  # e.g., 1/4 W, 1/8 W, 1/10 W
        },
        "Tolerance": {
            "default_unit": "%",
            "allowed_units": ["%"],
            "allowed_prefixes": [""],
            "allow_fraction": False,
        }
    },
    "Capacitor": {
        "Value": {
            "default_unit": "F",
            "allowed_units": ["F"],
            "allowed_prefixes": ["m", "µ", "n", "p", "f"],
            "allow_fraction": False,
        },
        "Voltage": {
            "default_unit": "V",
            "allowed_units": ["V"],
            "allowed_prefixes": ["k", "", "m"],
            "allow_fraction": False,
        },
        "Tolerance": {
            "default_unit": "%",
            "allowed_units": ["%"],
            "allowed_prefixes": [""],
            "allow_fraction": False,
        }
    },
    "Inductor": {
        "Value": {
            "default_unit": "H",
            "allowed_units": ["H"],
            "allowed_prefixes": ["", "m", "µ", "n", "p"],
            "allow_fraction": False,
        },
        "Tolerance": {
            "default_unit": "%",
            "allowed_units": ["%"],
            "allowed_prefixes": [""],
            "allow_fraction": False,
        }
    },
    "Diode": {
        "Value": {
            "default_unit": "V",
            "allowed_units": ["V", "A"],
            "allowed_prefixes": ["k", "", "m"],
            "allow_fraction": False,
        }
    },
    "Crystal": {
        "Value": {
            "default_unit": "Hz",
            "allowed_units": ["Hz"],
            "allowed_prefixes": ["G", "M", "k", ""],
            "allow_fraction": False,
        }
    }
}


class ColumnUnitConfigManager:
    """
    Manages persistent custom unit & scale configurations per table and column.
    Saved to .cache/column_units.json.
    """
    _instance: ColumnUnitConfigManager | None = None

    def __init__(self, config_file: Path | None = None) -> None:
        if config_file is None:
            try:
                from ..config import CACHE_DIR
                self.config_file = CACHE_DIR / "column_units.json"
            except Exception:
                self.config_file = Path(".cache") / "column_units.json"
        else:
            self.config_file = Path(config_file)

        self._user_configs: dict[str, dict[str, dict[str, Any]]] = {}
        self.load()

    @classmethod
    def get_instance(cls) -> ColumnUnitConfigManager:
        if cls._instance is None:
            cls._instance = ColumnUnitConfigManager()
        return cls._instance

    def load(self) -> None:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as fp:
                    self._user_configs = json.load(fp)
            except Exception as exc:
                logger.warning(f"Failed to load column units config from {self.config_file}: {exc}")
                self._user_configs = {}
        else:
            self._user_configs = {}

    def save(self) -> None:
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as fp:
                json.dump(self._user_configs, fp, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to save column units config to {self.config_file}: {exc}")

    def get_config(self, table_name: str, col_name: str) -> dict[str, Any] | None:
        """
        Returns active configuration for a table and column.
        If disabled by user override, returns None.
        If customized, returns user config.
        Otherwise falls back to default table configs or heuristics.
        """
        if not table_name or not col_name:
            return None

        # 1. Custom user override check
        if table_name in self._user_configs and col_name in self._user_configs[table_name]:
            cfg = self._user_configs[table_name][col_name]
            if not cfg.get("enabled", True):
                return None
            return dict(cfg)

        # 2. Predefined default table config
        table_rules = DEFAULT_TABLE_CONFIG.get(table_name)
        if table_rules and col_name in table_rules:
            res = dict(table_rules[col_name])
            res["enabled"] = True
            return res

        # 3. Intelligent fallback for common column names across any category table
        if col_name == "Value":
            t_low = table_name.lower()
            if "res" in t_low:
                res = dict(DEFAULT_TABLE_CONFIG["Resistor"]["Value"])
            elif "cap" in t_low:
                res = dict(DEFAULT_TABLE_CONFIG["Capacitor"]["Value"])
            elif "ind" in t_low:
                res = dict(DEFAULT_TABLE_CONFIG["Inductor"]["Value"])
            elif "dio" in t_low:
                res = dict(DEFAULT_TABLE_CONFIG["Diode"]["Value"])
            elif "cryst" in t_low or "osc" in t_low:
                res = dict(DEFAULT_TABLE_CONFIG["Crystal"]["Value"])
            else:
                res = {
                    "default_unit": "Ω",
                    "allowed_units": list(STANDARD_UNITS.keys()),
                    "allowed_prefixes": ALL_PREFIX_SYMBOLS,
                    "allow_fraction": False,
                }
            res["enabled"] = True
            return res
        elif col_name == "Power":
            res = dict(DEFAULT_TABLE_CONFIG["Resistor"]["Power"])
            res["enabled"] = True
            return res
        elif col_name == "Tolerance":
            res = dict(DEFAULT_TABLE_CONFIG["Resistor"]["Tolerance"])
            res["enabled"] = True
            return res

        return None

    def set_config(self, table_name: str, col_name: str, config: dict[str, Any]) -> None:
        """Set custom configuration for column and persist to JSON."""
        if table_name not in self._user_configs:
            self._user_configs[table_name] = {}
        cfg_to_save = dict(config)
        cfg_to_save["enabled"] = True
        self._user_configs[table_name][col_name] = cfg_to_save
        self.save()

    def disable_config(self, table_name: str, col_name: str) -> None:
        """Mark column as having NO unit/scale enforcement and persist."""
        if table_name not in self._user_configs:
            self._user_configs[table_name] = {}
        self._user_configs[table_name][col_name] = {"enabled": False}
        self.save()

    def clear_override(self, table_name: str, col_name: str) -> None:
        """Revert column configuration to built-in system defaults."""
        if table_name in self._user_configs and col_name in self._user_configs[table_name]:
            del self._user_configs[table_name][col_name]
            if not self._user_configs[table_name]:
                del self._user_configs[table_name]
            self.save()

    def is_customized(self, table_name: str, col_name: str) -> bool:
        """Check if column has a custom user override."""
        return table_name in self._user_configs and col_name in self._user_configs[table_name]


class EngineeringValueParser:
    """
    Parses, normalizes, and validates standard electronic component values
    and metric scale prefixes.
    """

    @classmethod
    def get_column_config(cls, table_name: str, col_name: str) -> dict[str, Any] | None:
        """Fetch unit configuration for a given table and column."""
        return ColumnUnitConfigManager.get_instance().get_config(table_name, col_name)

    @classmethod
    def normalize_unit(cls, unit_str: str) -> str:
        """Normalize unit symbol or alias to canonical representation."""
        if not unit_str:
            return ""
        u_clean = unit_str.strip()
        for sym, u_obj in STANDARD_UNITS.items():
            if u_clean.lower() == sym.lower() or u_clean.lower() in u_obj.aliases:
                return sym
        return unit_str

    @classmethod
    def normalize_prefix(cls, prefix_str: str) -> str:
        """Normalize prefix (e.g., 'u' or 'U' -> 'µ', 'K' -> 'k')."""
        if not prefix_str:
            return ""
        p = prefix_str.strip()
        if p.lower() == "u" or p == "µ":
            return "µ"
        if p == "K":
            return "k"
        if p in PREFIX_MAP:
            return p
        return p

    @classmethod
    def parse(cls, text: str, default_unit: str = "") -> dict[str, Any]:
        """
        Parse raw input text into magnitude, prefix, unit, and standard formatted string.
        Examples:
          '10kΩ'   -> magnitude: 10.0, prefix: 'k', unit: 'Ω', formatted: '10kΩ'
          '4k7'    -> magnitude: 4.7,  prefix: 'k', unit: 'Ω', formatted: '4.7kΩ'
          '100nF'  -> magnitude: 100,  prefix: 'n', unit: 'F', formatted: '100nF'
          '4.7u'   -> magnitude: 4.7,  prefix: 'µ', unit: 'F', formatted: '4.7µF'
          '1/4 W'  -> magnitude: '1/4',prefix: '',  unit: 'W', formatted: '1/4 W'
          '5%'     -> magnitude: 5.0,  prefix: '',  unit: '%', formatted: '5%'
        """
        raw = text.strip()
        if not raw:
            return {
                "valid": False,
                "magnitude": None,
                "prefix": "",
                "unit": default_unit,
                "formatted": "",
                "error": "Empty value",
            }

        # 1. Fraction check (e.g., "1/4 W", "1/8W", "1/2")
        frac_match = re.match(r"^(\d+/\d+)\s*([a-zA-Z%Ω°]*)$", raw)
        if frac_match:
            fraction_str = frac_match.group(1)
            raw_unit = frac_match.group(2)
            final_unit = cls.normalize_unit(raw_unit) or default_unit
            return {
                "valid": True,
                "magnitude": fraction_str,
                "prefix": "",
                "unit": final_unit,
                "formatted": f"{fraction_str} {final_unit}".strip(),
                "error": "",
            }

        # 2. Shorthand notation check: e.g. 4k7, 2R2, 1n5, 0R1, 47k
        shorthand_match = re.match(r"^(\d+)([RrkKMmUunNpP])(\d+)?\s*([a-zA-Z%Ω°]*)$", raw)
        if shorthand_match:
            int_part = shorthand_match.group(1)
            sep_char = shorthand_match.group(2)
            dec_part = shorthand_match.group(3) or "0"
            raw_unit = shorthand_match.group(4)

            # Determine prefix and unit from separator
            sep_norm = sep_char
            inferred_unit = default_unit
            if sep_char in ("R", "r"):
                prefix = ""
                inferred_unit = "Ω"
            else:
                prefix = cls.normalize_prefix(sep_norm)

            final_unit = cls.normalize_unit(raw_unit) or inferred_unit
            num_val = float(f"{int_part}.{dec_part}") if dec_part != "0" else float(int_part)
            mag_str = str(int(num_val)) if num_val.is_integer() else str(num_val)

            formatted = cls.format(mag_str, prefix, final_unit)
            return {
                "valid": True,
                "magnitude": num_val,
                "prefix": prefix,
                "unit": final_unit,
                "formatted": formatted,
                "error": "",
            }

        # 3. Standard regex: Number + Prefix + Unit
        # Allow numbers like 10, 4.7, .1, 100.0, 1e-3, -40
        pattern = r"^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([TGMkmµuUnNpfF])?\s*([a-zA-Z%Ω°]*)$"
        match = re.match(pattern, raw)
        if match:
            num_str = match.group(1)
            pref_raw = match.group(2) or ""
            unit_raw = match.group(3) or ""

            try:
                num_val = float(num_str)
            except ValueError:
                return {
                    "valid": False,
                    "magnitude": None,
                    "prefix": "",
                    "unit": "",
                    "formatted": raw,
                    "error": "Invalid number format",
                }

            # Check if prefix was actually a unit (e.g. "10F" where 'F' might match prefix or unit)
            prefix = ""
            final_unit = default_unit

            if pref_raw:
                # If pref_raw is 'F' or 'W' and unit_raw is empty, it's unit
                if pref_raw.upper() in ("F", "W", "V", "A", "H") and not unit_raw:
                    final_unit = pref_raw.upper()
                    prefix = ""
                else:
                    prefix = cls.normalize_prefix(pref_raw)

            if unit_raw:
                final_unit = cls.normalize_unit(unit_raw)

            if not final_unit and default_unit:
                final_unit = default_unit

            mag_str = str(int(num_val)) if num_val.is_integer() else str(num_val)
            formatted = cls.format(mag_str, prefix, final_unit)

            return {
                "valid": True,
                "magnitude": num_val,
                "prefix": prefix,
                "unit": final_unit,
                "formatted": formatted,
                "error": "",
            }

        # 4. Fallback if single number without prefix/unit
        try:
            num_val = float(raw)
            mag_str = str(int(num_val)) if num_val.is_integer() else str(num_val)
            formatted = cls.format(mag_str, "", default_unit)
            return {
                "valid": True,
                "magnitude": num_val,
                "prefix": "",
                "unit": default_unit,
                "formatted": formatted,
                "error": "",
            }
        except ValueError:
            pass

        return {
            "valid": False,
            "magnitude": None,
            "prefix": "",
            "unit": "",
            "formatted": raw,
            "error": "Cannot parse engineering value",
        }

    @classmethod
    def format(cls, magnitude: Any, prefix: str, unit: str) -> str:
        """Construct standard canonical formatted string."""
        if magnitude is None or str(magnitude).strip() == "":
            return ""

        mag_str = str(magnitude).strip()
        try:
            f_val = float(mag_str)
            if f_val.is_integer():
                mag_str = str(int(f_val))
        except ValueError:
            pass

        pref_str = prefix.strip()
        unit_str = unit.strip()

        # For tolerance %, no space
        if unit_str == "%":
            return f"{mag_str}%"

        # For fractions like 1/4 W, include a space
        if "/" in mag_str:
            return f"{mag_str} {pref_str}{unit_str}".strip()

        # Standard electronic notation: 10kΩ, 4.7µF, 100nH
        return f"{mag_str}{pref_str}{unit_str}"

    @classmethod
    def validate(
        cls,
        text: str,
        table_name: str = "",
        col_name: str = "Value",
    ) -> tuple[bool, str, str]:
        """
        Validate input against strict rules for the column/table.
        Returns: (is_valid: bool, formatted_value: str, error_message: str)
        """
        cfg = cls.get_column_config(table_name, col_name)
        if not cfg:
            # Column is not unit-managed; any string is valid
            return True, text, ""

        default_unit = cfg.get("default_unit", "")
        allowed_units = cfg.get("allowed_units")
        allowed_prefixes = cfg.get("allowed_prefixes")
        allow_fraction = cfg.get("allow_fraction", False)

        res = cls.parse(text, default_unit=default_unit)
        if not res["valid"]:
            return False, text, f"Invalid format: {res.get('error', 'Pattern mismatch')}"

        if not allow_fraction and "/" in str(res.get("magnitude", "")):
            return False, text, "Fractional values are not allowed for this column."

        unit = res.get("unit", "")
        prefix = res.get("prefix", "")

        if allowed_units is not None and unit not in allowed_units:
            units_str = ", ".join(allowed_units)
            return False, text, f"Unit '{unit}' is not allowed for this column. Allowed: {units_str}"

        if allowed_prefixes is not None and prefix not in allowed_prefixes:
            prefixes_str = ", ".join([p or "(Base)" for p in allowed_prefixes])
            return False, text, f"Prefix '{prefix}' is not allowed for this column. Allowed: {prefixes_str}"

        return True, res["formatted"], ""

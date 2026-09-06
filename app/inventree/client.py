# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from pathlib import Path
import re
import sys
import urllib.parse
from typing import Any
from ..config import INVENTREE_DIR, INVENTREE_CLIENT_PATH, CACHE_DIR, format_stock_value

logger = logging.getLogger(__name__)

# Import the inventree_client module
if INVENTREE_CLIENT_PATH.exists() and str(INVENTREE_CLIENT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(INVENTREE_CLIENT_PATH.parent))

try:
    from inventree_client import (
        InventreeConnection,
        load_settings,
        test_connection as it_test_connection,
        api_get,
    )
except ImportError as exc:
    logger.error(f"Failed to import inventree_client: {exc}")
    InventreeConnection = None
    load_settings = None
    it_test_connection = None
    api_get = None

class InvenTreeClient:
    """Handles communication with the local InvenTree instance."""

    def __init__(self) -> None:
        self.conn = load_settings() if load_settings else None
        self._token: str | None = None
        self._location_cache: dict[int, str] = {}

    def reload_settings(self) -> None:
        """Reload connection configuration from settings file and reset token/cache."""
        self.conn = load_settings() if load_settings else None
        self._token = None
        self._location_cache.clear()
        logger.info(f"InvenTree client reloaded settings: {self.conn.base_url if self.conn else 'None'}")

    def is_configured(self) -> bool:
        return self.conn is not None and bool(self.conn.base_url)

    def test_connection(self) -> tuple[bool, str]:
        if not self.conn or not it_test_connection:
            return False, "InvenTree settings or client not found"
        try:
            return it_test_connection(self.conn)
        except Exception as exc:
            return False, str(exc)

    def _get_token(self) -> str:
        if not self._token:
            if not self.conn:
                raise RuntimeError("InvenTree not configured")
            self._token = self.conn.resolve_token(timeout=10)
        return self._token

    def get_location_string(self, loc_id: int | None) -> str:
        """Resolve a location ID to its hierarchical path string (e.g. Rack-02-1/02-G01)."""
        if not loc_id:
            return ""
        if loc_id in self._location_cache:
            return self._location_cache[loc_id]

        try:
            token = self._get_token()
            data = api_get(self.conn, f"/api/stock/location/{loc_id}/", token=token)
            if isinstance(data, dict):
                path = data.get("pathstring") or data.get("name") or ""
                self._location_cache[loc_id] = path
                return path
        except Exception as exc:
            logger.warning(f"Failed to resolve location {loc_id}: {exc}")
        return str(loc_id)

    def search_parts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search InvenTree parts by query string (IPN, name, description)."""
        try:
            token = self._get_token()
            q_enc = urllib.parse.quote(query.strip())
            res = api_get(self.conn, f"/api/part/?search={q_enc}&limit={limit}", token=token)
            if isinstance(res, list):
                return res
            elif isinstance(res, dict) and "results" in res:
                return res["results"]
            return []
        except Exception as exc:
            logger.error(f"Error searching InvenTree parts: {exc}")
            return []

    def find_part_by_ipn(self, ipn: str) -> dict[str, Any] | None:
        """Look up a single part by exact or normalized near IPN."""
        if not ipn or not ipn.strip():
            return None
        ipn_clean = ipn.strip()
        try:
            token = self._get_token()

            # 1. Build candidate search terms in priority order
            candidates = [ipn_clean]

            # Candidate A: strip tolerance suffix (e.g., -1%, -5%)
            no_tol = re.sub(r"-(\d+(\.\d+)?)%", "", ipn_clean).strip()
            if no_tol and no_tol not in candidates:
                candidates.append(no_tol)

            # Candidate B: normalize engineering notation (e.g., 100kΩ -> 100K, 100Ω -> 100R, uppercase)
            for base in [ipn_clean, no_tol]:
                norm = re.sub(r"(\d+)\s*[kK]\u03a9?", r"\g<1>K", base)
                norm = re.sub(r"(\d+)\s*[mM]\u03a9?", r"\g<1>M", norm)
                norm = re.sub(r"(\d+)\s*\u03a9", r"\g<1>R", norm)
                norm = norm.replace("\u03a9", "").strip()
                if norm and norm not in candidates:
                    candidates.append(norm)
                norm_upper = norm.upper()
                if norm_upper and norm_upper not in candidates:
                    candidates.append(norm_upper)

            # 2. Try candidates against exact IPN API endpoint
            for cand in candidates:
                cand_enc = urllib.parse.quote(cand)
                res = api_get(self.conn, f"/api/part/?IPN={cand_enc}", token=token)
                parts = res if isinstance(res, list) else res.get("results", [])
                if parts:
                    return parts[0]

            # 3. Fallback to general search and case-insensitive matching
            for cand in candidates:
                cand_enc = urllib.parse.quote(cand)
                res = api_get(self.conn, f"/api/part/?search={cand_enc}&limit=5", token=token)
                parts = res if isinstance(res, list) else res.get("results", [])
                for p in parts:
                    p_ipn = str(p.get("IPN") or "").strip().lower()
                    if p_ipn == cand.lower():
                        return p

            return None
        except Exception as exc:
            logger.error(f"Error finding part by IPN {ipn}: {exc}")
            return None

    def get_stock_and_location(self, part_pk: int) -> tuple[float, str]:
        """
        Return (total_stock, location_string) for a part.
        Checks default_location first, then individual stock items if needed.
        """
        try:
            token = self._get_token()
            part = api_get(self.conn, f"/api/part/{part_pk}/", token=token)
            if not isinstance(part, dict):
                return 0.0, ""

            total_stock = float(part.get("total_in_stock") or 0.0)
            def_loc_id = part.get("default_location")

            loc_str = ""
            if def_loc_id:
                loc_str = self.get_location_string(def_loc_id)

            # If no default location or want actual stock item location
            if not loc_str and total_stock > 0:
                stock_items = api_get(self.conn, f"/api/stock/?part={part_pk}", token=token)
                items = stock_items if isinstance(stock_items, list) else stock_items.get("results", [])
                loc_names = set()
                for item in items:
                    loc_id = item.get("location")
                    if loc_id:
                        loc_names.add(self.get_location_string(loc_id))
                if loc_names:
                    loc_str = ", ".join(sorted(loc_names))

            return total_stock, loc_str
        except Exception as exc:
            logger.error(f"Error getting stock/location for part {part_pk}: {exc}")
            return 0.0, ""

    def preload_locations(self) -> dict[int, str]:
        """Preload all location paths into memory cache for instant resolution."""
        try:
            token = self._get_token()
            data = api_get(self.conn, "/api/stock/location/?limit=1000", token=token)
            items = data if isinstance(data, list) else data.get("results", [])
            for item in items:
                pk = item.get("pk")
                if pk:
                    self._location_cache[pk] = item.get("pathstring") or item.get("name") or ""
        except Exception as exc:
            logger.warning(f"Error preloading locations: {exc}")
        return self._location_cache

    def get_all_categories(self) -> list[dict[str, Any]]:
        """Fetch all part categories from InvenTree."""
        try:
            token = self._get_token()
            res = api_get(self.conn, "/api/part/category/?limit=1000", token=token)
            return res if isinstance(res, list) else res.get("results", [])
        except Exception as exc:
            logger.error(f"Error fetching categories from InvenTree: {exc}")
            return []

    def get_parts_by_categories(self, category_ids: list[int], limit_per_cat: int = 500) -> list[dict[str, Any]]:
        """Fetch all parts belonging to the specified categories (with subcategories cascade)."""
        if not category_ids:
            return []

        # Ensure locations are cached
        if not self._location_cache:
            self.preload_locations()

        try:
            token = self._get_token()
            unique_parts = {}
            for cat_id in category_ids:
                res = api_get(self.conn, f"/api/part/?category={cat_id}&cascade=true&limit={limit_per_cat}", token=token)
                parts = res if isinstance(res, list) else res.get("results", [])
                for p in parts:
                    pk = p.get("pk")
                    if pk and pk not in unique_parts:
                        def_loc = p.get("default_location")
                        loc_str = self._location_cache.get(def_loc, "") if def_loc else ""
                        p["location_name"] = loc_str
                        unique_parts[pk] = p

            # For parts with stock > 0 but no default location, query stock items in batch
            parts_needing_loc = [p for p in unique_parts.values() if not p.get("location_name") and float(p.get("total_in_stock") or 0) > 0]
            if parts_needing_loc:
                try:
                    stock_res = api_get(self.conn, "/api/stock/?in_stock=true&limit=1000", token=token)
                    stock_items = stock_res if isinstance(stock_res, list) else stock_res.get("results", [])
                    stock_loc_map: dict[int, set[str]] = {}
                    for s in stock_items:
                        part_id = s.get("part")
                        loc_id = s.get("location")
                        if part_id and loc_id:
                            loc_name = self._location_cache.get(loc_id, "")
                            if loc_name:
                                stock_loc_map.setdefault(part_id, set()).add(loc_name)

                    for p in parts_needing_loc:
                        p_id = p.get("pk")
                        if p_id in stock_loc_map:
                            p["location_name"] = ", ".join(sorted(stock_loc_map[p_id]))
                except Exception as exc:
                    logger.debug(f"Could not batch resolve stock locations: {exc}")

            return list(unique_parts.values())
        except Exception as exc:
            logger.error(f"Error fetching parts by categories: {exc}")
            return []

    def get_part_by_pk(self, part_pk: int) -> dict[str, Any] | None:
        """Fetch full part details by primary key (ID)."""
        try:
            token = self._get_token()
            res = api_get(self.conn, f"/api/part/{part_pk}/", token=token)
            if isinstance(res, dict) and "pk" in res:
                stock, loc = self.get_stock_and_location(part_pk)
                res["location_name"] = loc
                res["total_in_stock"] = stock
                return res
            return None
        except Exception as exc:
            logger.error(f"Error fetching part by pk {part_pk}: {exc}")
            return None

    def get_part_parameters(self, part_pk: int) -> dict[str, str]:
        """Fetch part parameters from InvenTree (e.g. Length, Value, etc.)."""
        try:
            token = self._get_token()
            res = api_get(self.conn, f"/api/parameter/?model_type=part.part&model_id={part_pk}", token=token)
            items = res if isinstance(res, list) else res.get("results", [])
            params: dict[str, str] = {}
            for item in items:
                t_detail = item.get("template_detail") or {}
                name = t_detail.get("name")
                data = item.get("data")
                if name and data is not None:
                    params[name] = str(data)
            return params
        except Exception as exc:
            logger.debug(f"Failed to fetch parameters for part {part_pk}: {exc}")
            return {}

    def get_part_parameter_templates(self) -> list[str]:
        """Fetch all parameter template names configured in InvenTree."""
        try:
            token = self._get_token()
            res = api_get(self.conn, "/api/parameter/template/?limit=250", token=token)
            items = res if isinstance(res, list) else res.get("results", [])
            names = []
            for item in items:
                n = item.get("name")
                if n and n not in names:
                    names.append(n)
            return names
        except Exception as exc:
            logger.debug(f"Failed to fetch parameter templates: {exc}")
            return []

    def get_part_sync_data(
        self,
        part_or_pk: dict[str, Any] | int,
        format_units: bool = True,
        omit_pcs: bool = True,
    ) -> dict[str, Any]:
        """
        Fetch combined sync data for a part:
        standard attributes, location_name, parameters, and formatted stock.
        """
        if isinstance(part_or_pk, dict):
            part = dict(part_or_pk)
            pk = int(part.get("pk") or 0)
        else:
            pk = int(part_or_pk)
            part = self.get_part_by_pk(pk) or {}

        if not part and pk:
            return {}

        stock, loc = self.get_stock_and_location(pk)
        units = part.get("units") or ""
        part["total_in_stock"] = stock
        part["location_name"] = loc

        formatted_stock = format_stock_value(stock, units if format_units else None, omit_pcs=omit_pcs)
        part["formatted_stock"] = formatted_stock

        params = self.get_part_parameters(pk)
        part["parameters"] = params
        for k, v in params.items():
            if k not in part:
                part[k] = v

        return part


class ComponentLinkManager:
    """
    Manages manual and explicit links between Altium DbLib component records
    and InvenTree warehouse parts. Persists links in .cache/component_links.json.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.file_path = self.cache_dir / "component_links.json"
        self._links: dict[str, dict[str, Any]] = {}
        self._load()

    def _make_key(self, table_name: str, row_id: int) -> str:
        return f"{table_name.strip()}:{row_id}"

    def _load(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8-sig") as fp:
                    self._links = json.load(fp)
            except Exception as exc:
                logger.error(f"Failed to load component links from {self.file_path}: {exc}")
                self._links = {}
        else:
            self._links = {}

    def _save(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as fp:
                json.dump(self._links, fp, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to save component links to {self.file_path}: {exc}")

    def get_link(self, table_name: str, row_id: int) -> dict[str, Any] | None:
        """Return explicit link data or unlinked status if set, else None."""
        key = self._make_key(table_name, row_id)
        return self._links.get(key)

    def is_explicitly_unlinked(self, table_name: str, row_id: int) -> bool:
        link = self.get_link(table_name, row_id)
        return bool(link and link.get("unlinked"))

    def set_link(
        self,
        table_name: str,
        row_id: int,
        part_or_pk: dict[str, Any] | int,
        ipn: str = "",
        name: str = "",
    ) -> None:
        """Explicitly link an Altium component to an InvenTree part."""
        key = self._make_key(table_name, row_id)
        if isinstance(part_or_pk, dict):
            pk_val = int(part_or_pk.get("pk") or 0)
            ipn_val = str(part_or_pk.get("IPN") or part_or_pk.get("ipn") or ipn or "")
            name_val = str(part_or_pk.get("name") or ipn_val)
        else:
            pk_val = int(part_or_pk)
            ipn_val = str(ipn or "")
            name_val = str(name or ipn_val)

        self._links[key] = {
            "inventree_pk": pk_val,
            "inventree_ipn": ipn_val,
            "inventree_name": name_val,
            "unlinked": False,
        }
        self._save()
        logger.info(f"Set explicit link for {key} -> InvenTree PK {pk_val} ({ipn_val})")

    def remove_link(self, table_name: str, row_id: int) -> None:
        """Explicitly mark an Altium component as unlinked from warehouse."""
        key = self._make_key(table_name, row_id)
        self._links[key] = {
            "unlinked": True,
        }
        self._save()
        logger.info(f"Marked {key} as explicitly unlinked")

    def clear_override(self, table_name: str, row_id: int) -> None:
        """Clear explicit link/unlink override, returning to default auto-matching."""
        key = self._make_key(table_name, row_id)
        if key in self._links:
            del self._links[key]
            self._save()
            logger.info(f"Cleared link override for {key}")

    def get_all_table_links(self, table_name: str) -> dict[int, dict[str, Any]]:
        """Return all active links for a given table as {row_id: link_dict}."""
        prefix = f"{table_name.strip()}:"
        result: dict[int, dict[str, Any]] = {}
        for k, v in self._links.items():
            if k.startswith(prefix) and not v.get("unlinked") and v.get("inventree_pk"):
                try:
                    rid = int(k[len(prefix):])
                    result[rid] = v
                except ValueError:
                    pass
        return result

    def find_by_inventree_pk(self, table_name: str, pk: int) -> int | None:
        """Find the Access row_id linked to the given InvenTree PK."""
        prefix = f"{table_name.strip()}:"
        for k, v in self._links.items():
            if k.startswith(prefix) and not v.get("unlinked") and v.get("inventree_pk") == pk:
                try:
                    return int(k[len(prefix):])
                except ValueError:
                    pass
        return None

    def find_by_inventree_ipn(self, table_name: str, ipn: str) -> int | None:
        """Find the Access row_id linked to the given InvenTree IPN."""
        if not ipn:
            return None
        ipn_norm = ipn.strip().lower()
        prefix = f"{table_name.strip()}:"
        for k, v in self._links.items():
            if k.startswith(prefix) and not v.get("unlinked"):
                if str(v.get("inventree_ipn") or "").strip().lower() == ipn_norm:
                    try:
                        return int(k[len(prefix):])
                    except ValueError:
                        pass
        return None


# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import pyodbc
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from ..config import DB_PATH, STANDARD_COLUMNS, SYMBOL_FOOTPRINT_COLUMNS

logger = logging.getLogger(__name__)

def check_access_driver_installed() -> tuple[bool, str, str]:
    """
    Check if a compatible Microsoft Access ODBC driver is installed on Windows.
    Returns (is_installed: bool, driver_name: str, download_url: str).
    """
    download_url = "https://www.microsoft.com/en-us/download/details.aspx?id=54920"
    try:
        drivers = pyodbc.drivers()
        for d in drivers:
            if "access" in d.lower() and ("mdb" in d.lower() or "accdb" in d.lower()):
                return True, d, download_url
    except Exception as exc:
        logger.error(f"Error checking ODBC drivers: {exc}")
    return False, "", download_url


class AccessDBManager:
    """Manages Microsoft Access database operations for Altium DbLib."""

    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.driver = "Microsoft Access Driver (*.mdb, *.accdb)"
        self.conn_str = f"DRIVER={{{self.driver}}};DBQ={self.db_path.resolve()};"

    @staticmethod
    def create_new_database(db_path: str | Path) -> bool:
        """
        Create a new, empty Microsoft Access .accdb database file using ADOX / DAO.
        """
        db_p = Path(db_path).resolve()
        if db_p.exists():
            raise FileExistsError(f"File already exists: {db_p}")

        db_p.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try ADOX.Catalog
        try:
            import win32com.client
            import gc
            catalog = win32com.client.Dispatch("ADOX.Catalog")
            conn_str = f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={db_p};"
            catalog.Create(conn_str)
            conn = catalog.ActiveConnection
            conn.Close()
            del conn
            del catalog
            gc.collect()
            if db_p.exists():
                logger.info(f"Created new Access database via ADOX: {db_p}")
                return True
        except Exception as exc_adox:
            logger.warning(f"ADOX database creation failed ({exc_adox}), trying DAO...")

        # 2. Try DAO.DBEngine.120 fallback
        try:
            import win32com.client
            import gc
            engine = win32com.client.Dispatch("DAO.DBEngine.120")
            db = engine.CreateDatabase(str(db_p), ";LANGID=0x0409;CP=1252;COUNTRY=0", 128)
            db.Close()
            del db
            del engine
            gc.collect()
            if db_p.exists():
                logger.info(f"Created new Access database via DAO: {db_p}")
                return True
        except Exception as exc_dao:
            logger.error(f"DAO database creation failed: {exc_dao}")
            raise RuntimeError(f"Failed to create Access database at {db_p}: {exc_dao}")

        return False

    @contextmanager
    def _get_dao_db(self):
        """Context manager to open Access database via DAO for schema manipulation."""
        import win32com.client
        import gc
        engine = win32com.client.Dispatch("DAO.DBEngine.120")
        db = engine.OpenDatabase(str(self.db_path.resolve()))
        try:
            yield db
        finally:
            db.Close()
            del db
            del engine
            gc.collect()

    def set_db_path(self, new_path: str | Path) -> None:
        self.db_path = Path(new_path)
        self.conn_str = f"DRIVER={{{self.driver}}};DBQ={self.db_path.resolve()};"

    def test_connection(self) -> tuple[bool, str]:
        """Test if the database file can be connected to."""
        if not self.db_path.exists():
            return False, f"File does not exist: {self.db_path.name}"
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                tables = [row.table_name for row in cursor.tables(tableType='TABLE')]
            return True, f"Connected ({len(tables)} tables found)"
        except Exception as exc:
            return False, str(exc)

    @contextmanager
    def get_connection(self) -> Generator[pyodbc.Connection, None, None]:
        conn = pyodbc.connect(self.conn_str, autocommit=False)
        try:
            yield conn
        finally:
            conn.close()

    def _coerce_value(self, column_name: str, value: Any) -> Any:
        """Coerce value to correct DB data type."""
        if value is None:
            return None
        if isinstance(value, str):
            val_str = value.strip()
            return val_str if val_str != "" else None
        if column_name == "Stock":
            s_val = str(value).strip()
            return s_val if s_val != "" else None
        return value

    def list_tables(self) -> list[str]:
        """Return list of user tables in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            tables = []
            for row in cursor.tables(tableType="TABLE"):
                tname = row.table_name
                # Exclude internal MS Access tables
                if not tname.startswith("MSys") and not tname.startswith("~"):
                    tables.append(tname)
            return sorted(tables)

    def get_columns(self, table_name: str) -> list[str]:
        """Return column names for a given table in order of ordinal position in MS Access."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cols = sorted(cursor.columns(table=table_name), key=lambda r: r.ordinal_position)
                if cols:
                    return [c.column_name for c in cols]
            except Exception:
                pass
            cursor.execute(f"SELECT TOP 1 * FROM [{table_name}]")
            return [col[0] for col in cursor.description]

    def ensure_symbol_footprint_columns(self, table_name: str) -> list[str]:
        """
        Ensure all standard symbol and footprint columns (up to 3 footprints)
        exist in the given table, automatically creating missing ones via ALTER TABLE.
        """
        existing = set(self.get_columns(table_name))
        added = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for col in SYMBOL_FOOTPRINT_COLUMNS:
                if col not in existing:
                    try:
                        col_type = "LONGCHAR" if "Path" in col else "VARCHAR(255)"
                        cursor.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{col}] {col_type}")
                        added.append(col)
                    except Exception as exc:
                        logger.error(f"Failed to add column [{col}] to table [{table_name}]: {exc}")
            if added:
                conn.commit()
                logger.info(f"Auto-created missing symbol/footprint columns in [{table_name}]: {added}")
        return added

    def fetch_records(self, table_name: str) -> list[dict[str, Any]]:
        """Fetch all rows from a table as a list of dictionaries preserving ordinal column order."""
        self.ensure_symbol_footprint_columns(table_name)
        columns = self.get_columns(table_name)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            col_sql = ", ".join(f"[{col}]" for col in columns)
            cursor.execute(f"SELECT {col_sql} FROM [{table_name}] ORDER BY [ID] ASC")
            records = []
            for row in cursor.fetchall():
                record = {}
                for idx, col in enumerate(columns):
                    record[col] = row[idx]
                records.append(record)
            return records

    def fetch_single_record(self, table_name: str, row_id: int) -> dict[str, Any] | None:
        """Fetch a single record by ID preserving ordinal column order."""
        columns = self.get_columns(table_name)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            col_sql = ", ".join(f"[{col}]" for col in columns)
            cursor.execute(f"SELECT {col_sql} FROM [{table_name}] WHERE [ID] = ?", (row_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {col: row[idx] for idx, col in enumerate(columns)}

    def update_cell(self, table_name: str, row_id: int, column_name: str, value: Any) -> bool:
        """Update a single cell value for a row identified by ID."""
        val = self._coerce_value(column_name, value)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"UPDATE [{table_name}] SET [{column_name}] = ? WHERE [ID] = ?"
            cursor.execute(query, (val, row_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_record(self, table_name: str, row_id: int, data: dict[str, Any]) -> bool:
        """Update multiple fields of a row, gracefully handling calculated non-updateable columns."""
        if not data:
            return False
        clean_data = {col: self._coerce_value(col, val) for col, val in data.items() if col != "ID"}
        if not clean_data:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clauses = [f"[{col}] = ?" for col in clean_data.keys()]
            params = list(clean_data.values())
            params.append(row_id)
            query = f"UPDATE [{table_name}] SET {', '.join(set_clauses)} WHERE [ID] = ?"
            try:
                cursor.execute(query, params)
            except pyodbc.Error as exc:
                if "not updateable" in str(exc).lower() and "Part Number" in clean_data:
                    clean_data.pop("Part Number")
                    if not clean_data:
                        return False
                    set_clauses = [f"[{col}] = ?" for col in clean_data.keys()]
                    params = list(clean_data.values())
                    params.append(row_id)
                    cursor.execute(f"UPDATE [{table_name}] SET {', '.join(set_clauses)} WHERE [ID] = ?", params)
                else:
                    raise
            conn.commit()
            return cursor.rowcount > 0

    def insert_record(self, table_name: str, data: dict[str, Any] | None = None) -> int:
        """Insert a new record into table, handling calculated columns gracefully."""
        data = data or {}
        columns = self.get_columns(table_name)
        insert_cols = [c for c in columns if c != "ID" and c in data and data[c] is not None]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if insert_cols:
                col_str = ", ".join(f"[{c}]" for c in insert_cols)
                val_placeholders = ", ".join("?" for _ in insert_cols)
                params = [self._coerce_value(c, data[c]) for c in insert_cols]
                query = f"INSERT INTO [{table_name}] ({col_str}) VALUES ({val_placeholders})"
                try:
                    cursor.execute(query, params)
                except pyodbc.Error as exc:
                    # If field is calculated (not updateable), retry without it
                    if "not updateable" in str(exc).lower() and "Part Number" in insert_cols:
                        insert_cols = [c for c in insert_cols if c != "Part Number"]
                        if insert_cols:
                            col_str = ", ".join(f"[{c}]" for c in insert_cols)
                            val_placeholders = ", ".join("?" for _ in insert_cols)
                            params = [self._coerce_value(c, data[c]) for c in insert_cols]
                            cursor.execute(f"INSERT INTO [{table_name}] ({col_str}) VALUES ({val_placeholders})", params)
                        else:
                            target = "Description" if "Description" in columns else columns[1]
                            cursor.execute(f"INSERT INTO [{table_name}] ([{target}]) VALUES (NULL)")
                    else:
                        raise
            else:
                target_col = "Description" if "Description" in columns else columns[1]
                cursor.execute(f"INSERT INTO [{table_name}] ([{target_col}]) VALUES (NULL)")
            conn.commit()

            cursor.execute("SELECT @@IDENTITY")
            new_id = cursor.fetchone()[0]
            return int(new_id)

    def delete_record(self, table_name: str, row_id: int) -> bool:
        """Delete a record by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM [{table_name}] WHERE [ID] = ?", (row_id,))
            conn.commit()
            return cursor.rowcount > 0

    def create_category_table(self, table_name: str, custom_fields: list[dict[str, Any]] | None = None) -> bool:
        """
        Create a new category table.
        - ID is always AutoNumber Primary Key.
        - Part Number is mandatory (can be Short Text or Calculated).
        - Path fields are Long Text (MEMO / LONGCHAR).
        - All other regular fields are Short Text (VARCHAR(255)).
        """
        table_name = table_name.strip()
        if not table_name:
            raise ValueError("Table name cannot be empty")

        if not custom_fields:
            field_defs = [
                "[ID] AUTOINCREMENT PRIMARY KEY",
                "[Part Number] VARCHAR(255)",
                "[Description] VARCHAR(255)",
                "[Value] VARCHAR(255)",
                "[Package] VARCHAR(255)",
                "[Tolerance] VARCHAR(255)",
                "[Power] VARCHAR(255)",
                "[Manufacturer] VARCHAR(255)",
                "[Manufacturer Part Number] VARCHAR(255)",
                "[Location] VARCHAR(255)",
                "[Stock] VARCHAR(50)",
                "[Library Ref] VARCHAR(255)",
                "[Library Path] LONGCHAR",
                "[Footprint Ref] VARCHAR(255)",
                "[Footprint Path] LONGCHAR",
                "[Footprint Ref 2] VARCHAR(255)",
                "[Footprint Path 2] LONGCHAR",
                "[Footprint Ref 3] VARCHAR(255)",
                "[Footprint Path 3] LONGCHAR",
            ]
            sql = f"CREATE TABLE [{table_name}] ({', '.join(field_defs)})"
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                conn.commit()
            return True

        # Custom fields specified: build via DAO to properly support calculated expressions
        with self._get_dao_db() as db:
            tbl = db.CreateTableDef(table_name)

            # 1. ID field (Mandatory Primary Key AutoNumber)
            fld_id = tbl.CreateField("ID", 4) # dbLong
            fld_id.Attributes = 16 # dbAutoIncrField
            tbl.Fields.Append(fld_id)

            idx = tbl.CreateIndex("PrimaryKey")
            idx.Fields.Append(idx.CreateField("ID"))
            idx.Primary = True
            tbl.Indexes.Append(idx)

            has_part_number = False
            normal_fields: list[tuple[str, str]] = []
            calc_fields: list[tuple[str, str]] = []

            for f in custom_fields:
                fname = f.get("name", "").strip()
                if not fname or fname.upper() == "ID":
                    continue

                if fname.upper() == "PART NUMBER":
                    has_part_number = True

                ftype = f.get("type", "short_text").lower()
                fexpr = (f.get("expression") or "").strip()

                if ftype == "calculated" and fexpr:
                    calc_fields.append((fname, fexpr))
                else:
                    normal_fields.append((fname, ftype))

            # Pass 1: Append all base storage fields first so calculated formulas can reference them
            for fname, ftype in normal_fields:
                if ftype == "long_text" or "path" in fname.lower():
                    fld = tbl.CreateField(fname, 12)  # dbMemo
                else:
                    fld = tbl.CreateField(fname, 10, 255)  # dbText
                tbl.Fields.Append(fld)

            # Ensure Part Number is mandatory if not specified
            if not has_part_number:
                tbl.Fields.Append(tbl.CreateField("Part Number", 10, 255))

            # Pass 2: Append calculated fields now that all referenced fields exist in tbl.Fields
            for fname, fexpr in calc_fields:
                fld = tbl.CreateField(fname, 10, 255)  # dbText
                fld.Expression = fexpr
                tbl.Fields.Append(fld)

            db.TableDefs.Append(tbl)
            logger.info(f"Created category table [{table_name}] with {len(tbl.Fields)} fields via DAO.")
            return True

    def get_table_schema(self, table_name: str) -> list[dict[str, Any]]:
        """
        Return rich field information for given table:
        [{
            "name": col_name,
            "type": "autonumber" | "short_text" | "long_text" | "calculated",
            "expression": formula_str,
            "is_primary_key": bool,
            "is_mandatory": bool
        }, ...]
        """
        schema = []
        try:
            with self._get_dao_db() as db:
                tbl = db.TableDefs(table_name)
                pk_fields = set()
                try:
                    for idx in tbl.Indexes:
                        if idx.Primary:
                            for f in idx.Fields:
                                pk_fields.add(f.Name)
                except Exception:
                    pass

                for fld in tbl.Fields:
                    fname = fld.Name
                    is_pk = fname in pk_fields or (fname.upper() == "ID")

                    expr = ""
                    try:
                        expr = str(fld.Expression or "")
                    except Exception:
                        try:
                            expr = str(fld.Properties("Expression").Value or "")
                        except Exception:
                            pass

                    if is_pk:
                        ftype = "autonumber"
                    elif expr:
                        ftype = "calculated"
                    elif fld.Type == 12:  # dbMemo
                        ftype = "long_text"
                    else:
                        ftype = "short_text"

                    is_mandatory = fname.upper() in ("ID", "PART NUMBER")

                    schema.append({
                        "name": fname,
                        "type": ftype,
                        "expression": expr,
                        "is_primary_key": is_pk,
                        "is_mandatory": is_mandatory,
                    })
        except Exception as exc:
            logger.error(f"Error getting DAO schema for {table_name}: {exc}", exc_info=True)
            cols = self.get_columns(table_name)
            for c in cols:
                is_pk = c.upper() == "ID"
                is_man = c.upper() in ("ID", "PART NUMBER")
                ftype = "autonumber" if is_pk else ("long_text" if "path" in c.lower() else "short_text")
                schema.append({
                    "name": c,
                    "type": ftype,
                    "expression": "",
                    "is_primary_key": is_pk,
                    "is_mandatory": is_man,
                })
        return schema

    def add_column(
        self,
        table_name: str,
        col_name: str,
        col_type: str = "short_text",
        expression: str | None = None,
    ) -> bool:
        """Add a column to a table with support for Short Text, Long Text, and Calculated fields."""
        col_name = col_name.strip()
        if not col_name:
            raise ValueError("Column name cannot be empty")

        if col_type == "calculated" and expression:
            with self._get_dao_db() as db:
                tbl = db.TableDefs(table_name)
                fld = tbl.CreateField(col_name, 10, 255)  # dbText
                fld.Expression = expression.strip()
                tbl.Fields.Append(fld)
            logger.info(f"Added calculated column [{col_name}] with formula '{expression}' to [{table_name}]")
            return True

        sql_type = "LONGCHAR" if col_type == "long_text" or "path" in col_name.lower() else "VARCHAR(255)"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{col_name}] {sql_type}")
            conn.commit()
        logger.info(f"Added column [{col_name}] ({sql_type}) to [{table_name}]")
        return True

    def delete_column(self, table_name: str, col_name: str) -> bool:
        """Delete a column from a table. ID and Part Number are strictly protected."""
        col_name = col_name.strip()
        if col_name.upper() == "ID":
            raise ValueError("The 'ID' primary key column is mandatory and cannot be deleted.")
        if col_name.upper() == "PART NUMBER":
            raise ValueError("The 'Part Number' column is mandatory and cannot be deleted.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE [{table_name}] DROP COLUMN [{col_name}]")
            conn.commit()
        logger.info(f"Deleted column [{col_name}] from [{table_name}]")
        return True

    def edit_column(
        self,
        table_name: str,
        old_name: str,
        new_name: str,
        new_type: str = "short_text",
        new_expression: str | None = None,
    ) -> bool:
        """
        Edit a column in a table (rename, change type, or update calculated formula).
        - ID cannot be modified.
        - Part Number cannot be renamed, but its type/formula can be edited.
        """
        old_name = old_name.strip()
        new_name = new_name.strip()
        if not old_name or not new_name:
            raise ValueError("Column names cannot be empty")

        if old_name.upper() == "ID":
            raise ValueError("The 'ID' primary key column cannot be modified.")
        if old_name.upper() == "PART NUMBER" and new_name.upper() != "PART NUMBER":
            raise ValueError("The 'Part Number' column cannot be renamed.")

        schema = {f["name"]: f for f in self.get_table_schema(table_name)}
        old_field = schema.get(old_name, {})
        old_type = old_field.get("type", "short_text")
        old_expr = old_field.get("expression", "")

        # 1. Rename if name changed
        if old_name != new_name:
            with self._get_dao_db() as db:
                tbl = db.TableDefs(table_name)
                tbl.Fields(old_name).Name = new_name
            logger.info(f"Renamed column [{old_name}] -> [{new_name}] in [{table_name}]")

        current_name = new_name

        # 2. If type or expression changed
        type_changed = (old_type != new_type)
        expr_changed = (new_type == "calculated" and old_expr != (new_expression or "").strip())

        if type_changed or expr_changed:
            with self._get_dao_db() as db:
                tbl = db.TableDefs(table_name)

                # Pre-test calculated formula before deleting old field
                if new_type == "calculated":
                    clean_expr = (new_expression or "").strip()
                    test_fld_name = f"__chk_{abs(hash(current_name)) % 10000}__"
                    try:
                        test_fld = tbl.CreateField(test_fld_name, 10, 255)
                        test_fld.Expression = clean_expr
                        tbl.Fields.Append(test_fld)
                        tbl.Fields.Delete(test_fld_name)
                    except Exception as expr_err:
                        err_str = str(expr_err)
                        if "Could not find field" in err_str:
                            import re
                            m = re.search(r"Could not find field '([^']+)'", err_str)
                            if m:
                                missing_fld = m.group(1)
                                raise ValueError(
                                    f"Formula references column '{missing_fld}', which does not exist in table '{table_name}'."
                                )
                        raise ValueError(f"Invalid Access formula expression: {expr_err}")

                # Delete existing column and create new one with rollback guarantee
                tbl.Fields.Delete(current_name)
                try:
                    if new_type == "calculated":
                        fld = tbl.CreateField(current_name, 10, 255)
                        fld.Expression = (new_expression or "").strip()
                        tbl.Fields.Append(fld)
                    elif new_type == "long_text" or "path" in current_name.lower():
                        fld = tbl.CreateField(current_name, 12)  # dbMemo
                        tbl.Fields.Append(fld)
                    else:
                        fld = tbl.CreateField(current_name, 10, 255)  # dbText
                        tbl.Fields.Append(fld)
                except Exception as append_err:
                    # Rollback: restore the original column definition
                    try:
                        if old_type == "calculated" and old_expr:
                            rfld = tbl.CreateField(current_name, 10, 255)
                            rfld.Expression = old_expr
                            tbl.Fields.Append(rfld)
                        elif old_type == "long_text":
                            rfld = tbl.CreateField(current_name, 12)
                            tbl.Fields.Append(rfld)
                        else:
                            rfld = tbl.CreateField(current_name, 10, 255)
                            tbl.Fields.Append(rfld)
                        logger.warning(f"Rolled back column [{current_name}] after append failure in [{table_name}]")
                    except Exception as rb_err:
                        logger.critical(f"Failed to rollback column [{current_name}]: {rb_err}")
                    raise append_err

            logger.info(f"Updated column [{current_name}] type to {new_type} in [{table_name}]")

        return True

    def rename_table(self, old_name: str, new_name: str) -> bool:
        """Rename an existing category table in MS Access."""
        old_name = old_name.strip()
        new_name = new_name.strip()
        if not old_name or not new_name:
            raise ValueError("Table names cannot be empty")
        with self._get_dao_db() as db:
            tbl = db.TableDefs(old_name)
            tbl.Name = new_name
        logger.info(f"Renamed table [{old_name}] -> [{new_name}]")
        return True

    def drop_table(self, table_name: str) -> bool:
        """Drop (delete) a table from MS Access."""
        table_name = table_name.strip()
        if not table_name:
            raise ValueError("Table name cannot be empty")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE [{table_name}]")
            conn.commit()
        logger.info(f"Dropped table [{table_name}]")
        return True

    def batch_update_mapped_records(self, table_name: str, updates: list[tuple[int, dict[str, Any]]]) -> int:
        """
        Batch update arbitrary mapped columns for given row IDs.
        updates: list of (row_id, {column_name: value, ...})
        """
        if not updates:
            return 0
        updated_count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for row_id, fields in updates:
                clean_fields = {col: self._coerce_value(col, val) for col, val in fields.items() if col != "ID"}
                if not clean_fields:
                    continue
                cols = list(clean_fields.keys())
                set_clauses = [f"[{c}] = ?" for c in cols]
                params = list(clean_fields.values())
                params.append(row_id)
                cursor.execute(
                    f"UPDATE [{table_name}] SET {', '.join(set_clauses)} WHERE [ID] = ?",
                    params,
                )
                updated_count += cursor.rowcount
            conn.commit()
        return updated_count

    def batch_update_stock_location(self, table_name: str, updates: list[tuple[int, str, Any]]) -> int:
        """
        Batch update Location and Stock for given row IDs.
        updates: list of (row_id, location, stock)
        """
        mapped_updates = [(row_id, {"Location": loc, "Stock": stock}) for row_id, loc, stock in updates]
        return self.batch_update_mapped_records(table_name, mapped_updates)


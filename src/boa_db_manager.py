"""Database manager for Bank of America statements"""

import sqlite3
import os
import shutil
import logging
from datetime import datetime, date
from decimal import Decimal

from config import DATABASE_PATH, CURRENT_SCHEMA_VERSION
from boa_models import Statement, Transaction

logger = logging.getLogger(__name__)


class BoaDbManager:
    """Database manager for Bank of America statements"""

    def __init__(
        self,
        db_path: str = os.path.join(DATABASE_PATH, "boa_statements.db"),
        force_recreate=False,
    ):
        self.db_path = db_path
        self.backup_path = os.path.join(DATABASE_PATH, "boa db backups")

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        # --- Schema Versioning ---
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

        self.cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        current_version_row = self.cursor.fetchone()
        current_version = current_version_row[0] if current_version_row else -1

        needs_recreation = (
            force_recreate
            or current_version == -1
            or current_version < CURRENT_SCHEMA_VERSION
        )

        if needs_recreation:
            logging.info(
                "Recreating schema. Current version: %s, Target version: %s",
                current_version,
                CURRENT_SCHEMA_VERSION,
            )

            if os.path.exists(self.db_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"boa_statements_v{current_version}_{timestamp}.db"
                backup_full_path = os.path.join(self.backup_path, backup_filename)
                os.makedirs(self.backup_path, exist_ok=True)
                try:
                    shutil.copy2(self.db_path, backup_full_path)
                    logging.info("Database backup created: %s", backup_full_path)
                except Exception as e:
                    logging.error("Failed to create database backup: %s", e)

            self.drop_tables()
            self.create_schema()

            self.cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,),
            )
            self.conn.commit()
            logging.info(
                "Database schema recreated to version %s.", CURRENT_SCHEMA_VERSION
            )

        # Optimize database size
        self.conn.execute("VACUUM")

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()

    def drop_tables(self):
        """Drops all application tables and the schema_version table."""
        logging.info("Dropping all existing database tables...")
        self.cursor.execute("DROP TABLE IF EXISTS transactions")
        self.cursor.execute("DROP TABLE IF EXISTS statements")
        self.cursor.execute("DROP TABLE IF EXISTS schema_version")
        self.conn.commit()
        logging.info("All tables dropped.")

    def create_schema(self):
        """Creates the statements and transactions tables."""
        logging.info("Creating database schema...")

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank TEXT DEFAULT 'Bank of America',
                statement_type TEXT NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                statement_period TEXT,
                beginning_balance REAL NOT NULL DEFAULT 0.00,
                total_deposits REAL NOT NULL DEFAULT 0.00,
                total_withdrawals REAL NOT NULL DEFAULT 0.00,
                total_check_count INTEGER NOT NULL DEFAULT 0,
                total_check_amount REAL NOT NULL DEFAULT 0.00,
                total_fees REAL NOT NULL DEFAULT 0.00,
                ending_balance REAL NOT NULL DEFAULT 0.00,
                filename TEXT NOT NULL,
                pdf_data BLOB,
                UNIQUE(filename, statement_type)
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT,
                transaction_description TEXT,
                transaction_description_override TEXT,
                transaction_amount REAL,
                transaction_check_number TEXT,
                transaction_transaction_type TEXT,
                statement_id INTEGER NOT NULL,
                transaction_comment TEXT,
                transaction_primary_category TEXT,
                transaction_secondary_category TEXT,
                FOREIGN KEY (statement_id) REFERENCES statements(id)
            )
            """
        )

        self.conn.commit()
        logging.info("Database schema created.")

    def insert_statement(self, statement_obj: Statement) -> int | None:
        """
        Inserts a Statement object and its associated Transaction objects into the database.
        Returns the ID of the newly inserted statement, or None if insertion fails.
        """
        if self.file_exists(statement_obj.filename, statement_obj.statement_type):
            logging.warning(
                "Statement file '%s' (type: %s) already exists in database. Skipping.",
                statement_obj.filename,
                statement_obj.statement_type,
            )
            return None

        try:
            self.cursor.execute(
                """
                INSERT INTO statements (
                    bank, statement_type, year, month, start_date, end_date,
                    statement_period, beginning_balance, total_deposits,
                    total_withdrawals, total_check_count, total_check_amount,
                    total_fees, ending_balance, filename, pdf_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    statement_obj.bank,
                    statement_obj.statement_type,
                    statement_obj.year,
                    statement_obj.month,
                    statement_obj.start_date.isoformat() if statement_obj.start_date else None,
                    statement_obj.end_date.isoformat() if statement_obj.end_date else None,
                    statement_obj.statement_period,
                    float(statement_obj.beginning_balance),
                    float(statement_obj.total_deposits),
                    float(statement_obj.total_withdrawals),
                    statement_obj.total_check_count,
                    float(statement_obj.total_check_amount),
                    float(statement_obj.total_fees),
                    float(statement_obj.ending_balance),
                    statement_obj.filename,
                    statement_obj.pdf_data,
                ),
            )

            statement_id = self.cursor.lastrowid
            statement_obj.id = statement_id

            # Insert associated transactions
            for txn in statement_obj.statement_transactions:
                self.cursor.execute(
                    """
                    INSERT INTO transactions (
                        transaction_date, transaction_description,
                        transaction_description_override, transaction_amount,
                        transaction_check_number, transaction_transaction_type,
                        statement_id, transaction_comment,
                        transaction_primary_category, transaction_secondary_category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        txn.transaction_date.isoformat() if txn.transaction_date else None,
                        txn.transaction_description,
                        txn.transaction_description_override,
                        float(txn.transaction_amount) if txn.transaction_amount else None,
                        txn.transaction_check_number,
                        txn.transaction_transaction_type,
                        statement_id,
                        txn.transaction_comment,
                        txn.transaction_primary_category,
                        txn.transaction_secondary_category,
                    ),
                )

            self.conn.commit()
            logging.info(
                "Successfully inserted statement for %s (ID: %s) with %d transactions.",
                statement_obj.filename,
                statement_id,
                len(statement_obj.statement_transactions),
            )
            return statement_id

        except sqlite3.IntegrityError as e:
            self.conn.rollback()
            logging.error(
                "IntegrityError inserting statement '%s': %s",
                statement_obj.filename,
                e,
            )
            return None
        except Exception as e:
            self.conn.rollback()
            logging.error(
                "Unexpected error inserting statement '%s': %s",
                statement_obj.filename,
                e,
            )
            return None

    def physical_file_exists(self, filename: str) -> bool:
        """
        Checks if the physical PDF file (by its renamed filename)
        has at least one logical statement associated with it in the database.
        """
        self.cursor.execute(
            "SELECT 1 FROM statements WHERE filename = ? LIMIT 1",
            (filename,),
        )
        return self.cursor.fetchone() is not None

    def file_exists(self, filename: str, statement_type: str) -> bool:
        """
        Checks if a specific logical statement (identified by filename and type)
        already exists in the database.
        """
        self.cursor.execute(
            "SELECT 1 FROM statements WHERE filename = ? AND statement_type = ? LIMIT 1",
            (filename, statement_type),
        )
        return self.cursor.fetchone() is not None

    # --- Query helper methods used by boa_app.py ---

    def get_all_transactions_with_statements(self) -> list[dict]:
        """
        Fetches all transactions joined with their parent statement data.
        Returns a list of dicts with combined transaction + statement fields.
        """
        self.cursor.execute(
            """
            SELECT
                t.id, t.transaction_date, t.transaction_description,
                t.transaction_description_override, t.transaction_amount,
                t.transaction_check_number, t.transaction_transaction_type,
                t.statement_id, t.transaction_comment,
                t.transaction_primary_category, t.transaction_secondary_category,
                s.year AS statement_year, s.month AS statement_month,
                s.statement_type, s.start_date AS statement_start_date,
                s.end_date AS statement_end_date, s.statement_period,
                s.bank
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            """
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_transactions_filtered(self, year: int, category: str,
                                  month_num: int = None,
                                  account_type: str = None,
                                  statement_period: str = None) -> list[dict]:
        """
        Fetches transactions filtered by year and category, with optional
        month or statement_period filtering.
        """
        params = []
        sql = """
            SELECT
                t.id, t.transaction_date, t.transaction_description,
                t.transaction_description_override, t.transaction_amount,
                t.transaction_check_number, t.transaction_transaction_type,
                t.statement_id, t.transaction_comment,
                t.transaction_primary_category, t.transaction_secondary_category,
                s.bank, s.statement_type, s.statement_period
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.year = ?
        """
        params.append(year)

        # Category filter
        if category == 'Other':
            sql += " AND t.transaction_primary_category IS NULL"
        else:
            sql += " AND t.transaction_primary_category = ?"
            params.append(category)

        # Date/period filter
        if account_type == 'All' and month_num is not None:
            sql += """
                AND CAST(strftime('%Y', t.transaction_date) AS INTEGER) = ?
                AND CAST(strftime('%m', t.transaction_date) AS INTEGER) = ?
            """
            params.extend([year, month_num])
        elif account_type and account_type != 'All' and statement_period:
            sql += " AND s.statement_type = ? AND s.statement_period = ?"
            params.extend([account_type, statement_period])

        self.cursor.execute(sql, params)
        return [dict(row) for row in self.cursor.fetchall()]

    def get_statements_filtered(self, year: int, month_num: int = None,
                                account_type: str = None,
                                statement_period: str = None) -> list[dict]:
        """
        Fetches statements filtered by year with optional month or period filtering.
        """
        params = [year]
        sql = "SELECT * FROM statements WHERE year = ?"

        if account_type == 'All' and month_num is not None:
            sql += " AND month = ?"
            params.append(month_num)
        elif account_type and account_type != 'All':
            sql += " AND statement_type = ?"
            params.append(account_type)
            if statement_period:
                sql += " AND statement_period = ?"
                params.append(statement_period)

        self.cursor.execute(sql, params)
        return [dict(row) for row in self.cursor.fetchall()]

    def get_statement_by_id(self, statement_id: int) -> dict | None:
        """Fetches a single statement by its ID."""
        self.cursor.execute(
            "SELECT * FROM statements WHERE id = ?", (statement_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_statement_by_start_date(self, start_date_str: str) -> dict | None:
        """Fetches a single statement by its start_date."""
        self.cursor.execute(
            "SELECT * FROM statements WHERE start_date = ? LIMIT 1",
            (start_date_str,),
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_filenames(self) -> set[str]:
        """Retrieves a set of all statement filenames in the database."""
        self.cursor.execute("SELECT filename FROM statements")
        return set(row[0] for row in self.cursor.fetchall())

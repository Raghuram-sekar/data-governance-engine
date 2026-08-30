import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path
from .base import BaseConnector, ConnectorType, TableSchema, ColumnSchema


class RelationalConnector(BaseConnector):
    """
    Modular Relational Database Connector (SQLite / PostgreSQL).
    Manages structured tables (dim_customers, fct_orders, web_traffic).
    """

    def __init__(self, db_path: Optional[str] = None):
        super().__init__(name="Postgres-Relational-Adapter", connector_type=ConnectorType.RELATIONAL)
        self.db_path = db_path or str(Path(__file__).parent.parent / "relational_store.db")
        self._masked_columns = set()
        self._init_db()

    def _init_db(self):
        """Initializes relational tables and mock enterprise transactional data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. dim_customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_customers (
                customer_id TEXT PRIMARY KEY,
                full_name TEXT,
                customer_email TEXT,
                tax_ssn TEXT,
                raw_credit_card TEXT,
                region TEXT,
                is_returning INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # 2. fct_orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fct_orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT,
                order_total REAL,
                order_date TEXT,
                billing_zip TEXT,
                feedback_score INTEGER,
                FOREIGN KEY (customer_id) REFERENCES dim_customers(customer_id)
            )
        """)

        # 3. web_traffic table (Landing page & Campaign attribution)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_traffic (
                traffic_id TEXT PRIMARY KEY,
                customer_id TEXT,
                landing_page TEXT,
                traffic_source TEXT,
                is_promotion_driven INTEGER,
                FOREIGN KEY (customer_id) REFERENCES dim_customers(customer_id)
            )
        """)

        # Seed sample data if empty
        cursor.execute("SELECT COUNT(*) FROM dim_customers")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO dim_customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                ("CUST-101", "Alice Smith", "alice.smith@enterprise.com", "987-65-4321", "4111-2222-3333-4444", "NA-EAST", 1, "2026-07-01"),
                ("CUST-102", "Bob Jones", "bob.jones@gmail.com", "123-45-6789", "5500-0000-1111-2222", "NA-WEST", 0, "2026-08-15"),
                ("CUST-103", "Charlie Brown", "charlie@company.org", "555-66-7777", "3782-8224-6310-0050", "EMEA", 1, "2026-08-20"),
                ("CUST-104", "Diana Prince", "diana.prince@gov.us", "999-00-1111", "6011-0000-0000-0004", "APAC", 0, "2026-08-25"),
            ])

            cursor.executemany("""
                INSERT INTO fct_orders VALUES (?, ?, ?, ?, ?, ?)
            """, [
                ("ORD-5001", "CUST-101", 1250.00, "2026-07-15", "10001", 5),
                ("ORD-5002", "CUST-102", 450.50, "2026-08-16", "90210", None),       # New customer, no feedback required
                ("ORD-5003", "CUST-103", 2990.00, "2026-08-21", None, 4),             # Missing billing ZIP (Anomaly!)
                ("ORD-5004", "CUST-104", 820.00, "2026-08-26", "94103", None),
            ])

            cursor.executemany("""
                INSERT INTO web_traffic VALUES (?, ?, ?, ?, ?)
            """, [
                ("TRF-9001", "CUST-101", "/products/enterprise", "google_organic", 0),
                ("TRF-9002", "CUST-102", "/landing/summer-promo", "facebook_ads", 1),
                ("TRF-9003", "CUST-103", "/pricing", "direct", 0),
                ("TRF-9004", "CUST-104", "/landing/special", "facebook", None),       # Unclassified promo attribution (Anomaly!)
            ])

        conn.commit()
        conn.close()

    def connect(self) -> bool:
        return True

    def list_tables(self) -> List[TableSchema]:
        tables = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        table_names = [row[0] for row in cursor.fetchall()]

        for tbl_name in table_names:
            tables.append(self.get_table_schema(tbl_name))

        conn.close()
        return [t for t in tables if t]

    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return None

        columns = []
        for r in rows:
            col_name = r[1]
            data_type = r[2]
            is_masked = f"{table_name}.{col_name}" in self._masked_columns
            columns.append(ColumnSchema(
                name=col_name,
                data_type=data_type,
                is_nullable=not bool(r[3]),
                is_masked=is_masked
            ))

        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cursor.fetchone()[0]
        conn.close()

        return TableSchema(
            name=table_name,
            qualified_name=f"public.{table_name}",
            connector_type=ConnectorType.RELATIONAL,
            description=f"Relational table {table_name} in PostgreSQL operational schema.",
            columns=columns,
            row_count=row_count
        )

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or {})
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        conn.close()
        return result

    def apply_data_masking(self, table_name: str, column_name: str, mask_type: str = "MASK_ALL") -> bool:
        self._masked_columns.add(f"{table_name}.{column_name}")
        return True

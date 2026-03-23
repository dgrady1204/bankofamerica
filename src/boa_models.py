"""
Data models for Bank of America statements and transactions.
Plain Python classes (no ORM dependency).
"""

from __future__ import annotations
from datetime import date
from decimal import Decimal


class Transaction:
    """
    Transaction class for representing a transaction in a statement.
    """

    def __init__(
        self,
        transaction_date: date = None,
        transaction_description: str = None,
        transaction_description_override: str = None,
        transaction_amount: float = None,
        transaction_check_number: str = None,
        transaction_transaction_type: str = None,
        statement_id: int = None,
        transaction_comment: str = None,
        transaction_primary_category: str = None,
        transaction_secondary_category: str = None,
        id: int = None,
    ):
        self.id = id
        self.transaction_date = transaction_date
        self.transaction_description = transaction_description
        self.transaction_description_override = transaction_description_override
        self.transaction_amount = transaction_amount
        self.transaction_check_number = transaction_check_number
        self.transaction_transaction_type = transaction_transaction_type
        self.statement_id = statement_id
        self.transaction_comment = transaction_comment
        self.transaction_primary_category = transaction_primary_category
        self.transaction_secondary_category = transaction_secondary_category
        # Reference to parent Statement object (set in-memory, not persisted directly)
        self.statement_source: Statement | None = None

    def __repr__(self):
        return (
            f"<Transaction("
            f"id={self.id}, "
            f"transaction_date={self.transaction_date}, "
            f"transaction_description='{self.transaction_description}', "
            f"transaction_amount={self.transaction_amount})>"
        )


class Statement:
    """Statement class for bank of america statements"""

    def __init__(
        self, page_lines: dict = None, initial_filename: str = None, year: str = None
    ):
        self.id: int | None = None
        self.bank: str = 'Bank of America'
        self.filename = initial_filename
        self.statement_type: str | None = None
        self.year = int(year) if year is not None else None
        self.month: int | None = None
        self.start_date: date | None = None
        self.end_date: date | None = None
        self.statement_period: str | None = None

        self.beginning_balance = Decimal("0.00")
        self.total_deposits = Decimal("0.00")
        self.total_withdrawals = Decimal("0.00")
        self.total_check_count = 0
        self.total_check_amount = Decimal("0.00")
        self.total_fees = Decimal("0.00")
        self.ending_balance = Decimal("0.00")

        self.pdf_data: bytes | None = None
        self.page_lines = page_lines if page_lines is not None else {}
        self.page_ranges = None
        self.statement_transactions: list[Transaction] = []

    def __repr__(self):
        return f"<Statement(id={self.id}, filename={self.filename}, type={self.statement_type})>"

    def __str__(self):
        return (
            f"Statement(filename={self.filename}, type={self.statement_type}, "
            f"start={self.start_date}, end={self.end_date}, "
            f"deposits={self.total_deposits}, withdrawals={self.total_withdrawals})"
        )

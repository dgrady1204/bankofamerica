"""
boa_transaction_parser.py
"""

import re
import logging
from decimal import Decimal, InvalidOperation
from datetime import date

# Import the Transaction ORM model
from boa_models import Transaction

logger = logging.getLogger(__name__)


def _parse_year(year_str: str) -> int:
    """Parse a 2-digit or 4-digit year string into a full year integer."""
    year_int = int(year_str)
    if year_int < 100:
        year_int += 2000
    return year_int


def create_from_page_lines(statement_pages):
    """
    Create Transaction instances from page lines.

    Args:
        statement_pages (dict): Dict of page_number -> list of text lines

    Returns:
        list: List of Transaction instances
    """
    re_date = r"\d{1,2}\/\d{1,2}\/\d{2,4}"
    re_space = r" +"
    re_check_number = r"\d\d\d\d"
    re_check_amount = r"[-+]?[0-9]+.\d\d"
    re_check_search = re_date + re_space + re_check_number + re_space + re_check_amount
    transactions = []
    for page_number in statement_pages:
        for line in statement_pages[page_number]:
            transaction_date_search = re.findall(re_date, line)
            transaction_date = None
            check_search = re.findall(
                re_check_search, line.replace("*", "").replace(",", "")
            )
            if check_search:
                for check in check_search:
                    try:
                        check_date = check.split(" ")[0]
                        date_parts = check_date.split("/")
                        check_year = _parse_year(date_parts[2])
                        check_month = int(date_parts[0])
                        check_day = int(date_parts[1])
                        transaction_date = date(check_year, check_month, check_day)
                        check_number = check.split(" ")[1]
                        amount = Decimal(check.split(" ")[2].replace(",", ""))
                        new_transaction = Transaction(
                            transaction_date=transaction_date,
                            transaction_description=None,
                            transaction_amount=amount,
                            transaction_check_number=check_number,
                            transaction_transaction_type="Check",
                            transaction_comment=None,
                            transaction_primary_category=None,
                            transaction_secondary_category=None,
                        )
                        transactions.append(new_transaction)
                    except (ValueError, InvalidOperation, IndexError) as e:
                        logger.warning("Skipping unparseable check line: '%s' (%s)", line.strip(), e)
            elif transaction_date_search:
                try:
                    raw_date = transaction_date_search[0]
                    date_parts = raw_date.split("/")
                    txn_year = _parse_year(date_parts[2])
                    txn_month = int(date_parts[0])
                    txn_day = int(date_parts[1])
                    transaction_date = date(txn_year, txn_month, txn_day)
                    amount = Decimal(line.split(" ")[-1].replace(",", ""))
                    desc = " ".join(line.split()[1:-1])
                    new_transaction = Transaction(
                        transaction_date=transaction_date,
                        transaction_description=desc,
                        transaction_amount=amount,
                        transaction_check_number=None,
                        transaction_transaction_type=(
                            "Deposit" if amount > 0 else "Credit"
                        ),
                        transaction_comment=None,
                        transaction_primary_category=None,
                        transaction_secondary_category=None,
                    )
                    transactions.append(new_transaction)
                except (ValueError, InvalidOperation, IndexError) as e:
                    logger.warning("Skipping unparseable transaction line: '%s' (%s)", line.strip(), e)

    return transactions

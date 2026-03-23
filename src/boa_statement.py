# boa_statement.py

"""
Main startup module for bank of america statements.  

This module is the main entry point for processing bank of america statements.
It orchestrates finding new statement files, parsing their content,
and adding the extracted data to the database.
"""

# this is needed for union type hints
from __future__ import annotations

import os
import sys
import re
import logging
from datetime import datetime
from decimal import Decimal
import shutil

# Import ORM models
from boa_models import Statement

# Import the transaction parsing logic
from boa_transaction_parser import (
    create_from_page_lines as parse_transactions_from_pages,
)

# Import PDF reading utilities
from boa_pdf_reader import (
    extract_pages_from_statement_pdf,
    get_page_text_from_pdf_elements,
)

# Import DB Manager
from boa_db_manager import BoaDbManager

# Import shared constants
from config import STATEMENT_DIRECTORY
from config import DATABASE_PATH

# --- Setup and Logging ---


def setup_logging():
    """
    Set up logging configuration for the application.
    Configures both console and file logging handlers.
    """
    # Use basicConfig to set up handlers, and use force=True to ensure it always applies
    # This replaces the manual logger.addHandler and logger.handlers.clear()

    log_file_full_path = os.path.join(DATABASE_PATH, "boa_pdf_reader.log")
    os.makedirs(
        os.path.dirname(log_file_full_path), exist_ok=True
    )  # Ensure directory exists

    logging.basicConfig(
        level=logging.INFO,  # Or logging.DEBUG for more detail
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),  # Console output
            logging.FileHandler(log_file_full_path, mode="a"),  # File output
        ],
        force=True,  # <--- THIS IS THE CRITICAL FIX for Streamlit compatibility
    )

    # Get the root logger instance (it's already configured by basicConfig)
    logger = logging.getLogger()


# --- File System and Basic Utilities ---


def find_new_statement_files() -> dict:
    """
    Finds PDF statement files that have not been processed.
    Returns a dictionary of years and their unprocessed statement file paths.
    """
    new_pdf_files = {}
    years = [
        d
        for d in os.listdir(STATEMENT_DIRECTORY)
        if os.path.isdir(os.path.join(STATEMENT_DIRECTORY, d)) and d.isdigit()
    ]
    for year in years:
        logging.info("Scanning year: %s", year)  # FIXED: Changed print to logging.info
        pdf_dir = os.path.join(STATEMENT_DIRECTORY, str(year))
        new_pdf_files[year] = []
        for f in os.listdir(pdf_dir):
            if os.path.isfile(os.path.join(pdf_dir, f)) and f.lower().endswith(".pdf"):
                new_pdf_files[year].append(
                    os.path.join(pdf_dir, f)
                )  # FIXED: Use os.path.join for robustness
    for year in new_pdf_files:
        new_pdf_files[year] = sorted(new_pdf_files[year])
    return new_pdf_files


def verify_pdf_file_name(
    pdf_file_name: str,
) -> str | None:  # ADDED type hint for pdf_file_name
    """
    Verifies that the PDF file name is in the expected standardized format.
    """
    if re.match(
        r"BOA [A-Za-z]+ [A-Za-z]+ statement \d{8} to \d{8}\.pdf", pdf_file_name
    ):
        return pdf_file_name
    return None


def rename_statement_file(old_pdf_file_path: str, new_filename: str) -> str | None:
    """
    Renames a file on disk to a new desired filename.
    Checks if the file already has the correct name before attempting to rename.
    Returns the new absolute path if successful or if the file was already correctly named,
    None otherwise.
    """
    old_dir = os.path.dirname(old_pdf_file_path)
    old_filename_basename = os.path.basename(old_pdf_file_path)
    new_full_path = os.path.join(old_dir, new_filename)

    if old_filename_basename == new_filename:
        return new_full_path

    try:
        shutil.move(old_pdf_file_path, new_full_path)
        logging.info("Renamed '%s' to '%s'", old_filename_basename, new_filename)
        return new_full_path
    except OSError as e:
        logging.error(
            "Failed to rename file from '%s' to '%s': %s",
            old_pdf_file_path,
            new_full_path,
            e,
        )
        return None


# --------------------------------------
# Core Parsing Helpers
# --------------------------------------


def extract_pdf_lines(stmt_obj: Statement, pdf_content: bytes) -> bool:
    """
    Extracts text lines from a PDF and stores them in the provided Statement 
    object's page_lines attribute.
    Handles PDF parsing errors and ensures comprehensive error logging.
    """
    stmt_obj.page_lines = {}
    try:
        pages = extract_pages_from_statement_pdf(pdf_content) # Changed to accept bytes
        if pages:
            for page_count, page in enumerate(pages):
                stmt_obj.page_lines[page_count] = get_page_text_from_pdf_elements(page)
            return True
        logging.error("No pages extracted from PDF content.")
        return False
    except Exception as e:
        logging.error("Error extracting pages from PDF content: %s", e)
        return False

def _get_statement_bank(stmt_obj: Statement) -> str | None:
    """
    Extracts the bank name from the first page's content.
    """
    if not stmt_obj.page_lines or 0 not in stmt_obj.page_lines:
        return None
    first_page_lines = stmt_obj.page_lines[0]
    for line in first_page_lines:
        if "bank of america" in line.lower():
            return "Bank of America"
        if 'harbor one' in line.lower():
            return 'Harbor One'
        if 'eastern bank' in line.lower():
            return 'Eastern Bank'
    return None

def _get_statement_type(
    stmt_obj: Statement,
) -> str | None:  # FIXED: Corrected return type hint
    """
    Determines and returns the statement type (Checking, Savings, Combined)
    from the first page's content.
    """
    if not stmt_obj.page_lines or 0 not in stmt_obj.page_lines:
        return None
    first_page_lines = stmt_obj.page_lines[0]
    account_type = None
    for line in first_page_lines:
        lower_line = line.lower()
        if "combined" in lower_line:
            account_type = "Combined"
            break
        if "checking" in lower_line or "adv plus banking" in lower_line:
            account_type = "Checking"
            break
        if "savings" in lower_line:
            account_type = "Savings"
            break
    if not account_type:
        logging.warning(
            "Could not determine statement type for %s.", stmt_obj.filename
        )  # FIXED: Added context
        return None
    return account_type


def _extract_statement_dates_from_page(stmt_obj: Statement) -> bool:
    """
    Extracts the start and end dates from the first page's lines,
    converts them to datetime.date objects, and sets them (along with year/month)
    as attributes of the Statement object.
    Returns True on success, False on failure.
    """
    if not stmt_obj.page_lines or 0 not in stmt_obj.page_lines:
        logging.warning(
            "No page lines found for date extraction in %s.", stmt_obj.filename
        )
        return False

    first_page_lines = stmt_obj.page_lines[0]
    raw_start_date_str = None
    raw_end_date_str = None

    for line in first_page_lines:
        match = re.search(
            r"for ([A-Za-z]+\s+\d{1,2},\s+\d{4}) to ([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            line,
        )
        if match:
            raw_start_date_str = match.group(1)
            raw_end_date_str = match.group(2)
            break

    if not raw_start_date_str or not raw_end_date_str:
        logging.warning("Could not find statement dates in %s.", stmt_obj.filename)
        return False

    try:
        stmt_obj.start_date = datetime.strptime(
            raw_start_date_str, "%B %d, %Y"
        ).date()  # FIXED: .date()
        stmt_obj.end_date = datetime.strptime(
            raw_end_date_str, "%B %d, %Y"
        ).date()  # FIXED: .date()

        start_str = stmt_obj.start_date.strftime('%b %d')
        end_str = stmt_obj.end_date.strftime('%b %d')
        stmt_obj.statement_period = f"{start_str} - {end_str}"

        # Use end date to determine year and month
        stmt_obj.year = stmt_obj.end_date.year
        stmt_obj.month = stmt_obj.end_date.month

        return True
    except ValueError as e:
        logging.error(
            "Error parsing raw date strings '%s' or '%s' in %s: %s",
            raw_start_date_str,
            raw_end_date_str,
            stmt_obj.filename,
            e,
        )
        stmt_obj.start_date = None
        stmt_obj.end_date = None
        stmt_obj.year = None
        stmt_obj.month = None
        return False


def _extract_statement_balances(
    stmt_obj: Statement, first_page_lines: list[str]
) -> None:
    """
    Extracts various balance figures from the provided lines of the first page
    and populates the Statement object's balance attributes.
    """
    amount_pattern = r"[-+]?\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}"

    # FIXED: Map to actual attribute names in Statement object
    patterns_map = {
        "Beginning balance on": "beginning_balance",
        "Deposits and other additions": "total_deposits",
        "Withdrawals and other subtractions": "total_withdrawals",
        "Checks": "total_check_amount",
        "Service fees": "total_fees",
        "Ending balance on": "ending_balance",
    }
    extracted_values = {}

    for line in first_page_lines:
        for (
            keyword,
            attr_name,
        ) in patterns_map.items():  # attr_name is the key in patterns_map
            if keyword in line:
                match = re.search(
                    rf"{re.escape(keyword)}.*?({amount_pattern})\s*", line
                )
                if match:
                    amount_str = (
                        match.group(1).replace("$", "").replace(",", "").strip()
                    )
                    try:
                        extracted_values[attr_name] = Decimal(
                            amount_str
                        )  # Store with actual attribute name
                    except Exception as e:
                        logging.warning(
                            "Could not parse amount '%s' for '%s' in %s: %s",
                            amount_str,
                            keyword,
                            stmt_obj.filename,
                            e,
                        )
                    break

    # Assign extracted values to Statement attributes using setattr loop
    for attr_name in patterns_map.values():  # Iterate over the actual attribute names
        if attr_name in extracted_values:
            setattr(stmt_obj, attr_name, extracted_values[attr_name])
    # Default values for attributes not found are handled by __init__ defaults.

    # Ensure total_check_amount is zero for non-checking if not found
    if stmt_obj.statement_type == "Checking":
        if "total_check_amount" not in extracted_values:  # Check if it was extracted
            stmt_obj.total_check_amount = Decimal("0.00")
    else:  # For non-checking statement, ensure it's explicitly 0.00
        stmt_obj.total_check_amount = Decimal("0.00")

    logging.debug(
        "Extracted balances for %s (Type: %s): Beg %.2f, Dep %.2f, Wth %.2f, Chk %.2f, Fees %.2f, End %.2f",
        stmt_obj.filename,
        stmt_obj.statement_type,
        stmt_obj.beginning_balance,
        stmt_obj.total_deposits,
        stmt_obj.total_withdrawals,
        stmt_obj.total_check_amount,
        stmt_obj.total_fees,
        stmt_obj.ending_balance,
    )


def extract_combined_page_ranges(
    stmt_obj: Statement,
) -> dict[str, tuple[int, int]] | None:
    """
    Extracts page ranges for combined statements, returning a dict like
    {'checking': (start_page_idx, end_page_idx), 'savings': (start_page_idx, end_page_idx)}.
    Returns None if combined ranges cannot be extracted.
    """
    if not stmt_obj.page_lines or 0 not in stmt_obj.page_lines:
        logging.warning(
            "No page lines available to extract combined page ranges for %s.",
            stmt_obj.filename,
        )
        return None

    first_page_lines = stmt_obj.page_lines[0]
    checking_start_page = None
    savings_start_page = None

    for line in first_page_lines:
        if "Checking" in line:
            try:
                checking_start_page = int(line.split(" ")[-1])
            except ValueError:
                logging.warning(
                    "Could not parse checking page number from line: %s in %s",
                    line,
                    stmt_obj.filename,
                )
        if "Savings" in line:
            try:
                savings_start_page = int(line.split(" ")[-1])
            except ValueError:
                logging.warning(
                    "Could not parse savings page number from line: %s in %s",
                    line,
                    stmt_obj.filename,
                )

    if checking_start_page is not None and savings_start_page is not None:
        checking_range = (checking_start_page - 1, savings_start_page - 2)
        savings_range = (
            savings_start_page - 1,
            len(stmt_obj.page_lines) - 1,
        )
        return {"checking": checking_range, "savings": savings_range}

    logging.warning("Could not extract combined page ranges for %s.", stmt_obj.filename)
    return None


def _get_statement_period(stmt_obj: Statement) -> str:
    """
    Returns the statement period type (Monthly, Quarterly, Other).
    """
    if not stmt_obj.start_date or not stmt_obj.end_date:
        logging.warning(
            "Cannot determine statement period: missing datetime objects for %s.",
            stmt_obj.filename,
        )
        return "Unknown"

    diff_months = (stmt_obj.end_date.year - stmt_obj.start_date.year) * 12 + (
        stmt_obj.end_date.month - stmt_obj.start_date.month
    )
    if diff_months == 1 or (
        diff_months == 0 and (stmt_obj.end_date - stmt_obj.start_date).days >= 28
    ):
        return "Monthly"

    if diff_months == 3 or (
        diff_months == 2 and (stmt_obj.end_date - stmt_obj.start_date).days > 80
    ):
        return "Quarterly"

    return "Other"


def _build_child_statement(
    child_stmt_obj: Statement, statement_type: str, parent_statement: Statement
) -> bool:
    """
    Builds a child statement from a parent statement.
    """
    child_stmt_obj.statement_type = statement_type
    child_stmt_obj.page_lines = {
        idx: parent_statement.page_lines[idx]
        for idx in range(
            parent_statement.page_ranges[statement_type][0],
            parent_statement.page_ranges[statement_type][1] + 1,
        )
    }
    child_stmt_obj.month = parent_statement.month
    child_stmt_obj.year = parent_statement.year
    child_stmt_obj.start_date = parent_statement.start_date
    child_stmt_obj.end_date = parent_statement.end_date
    # REMOVED: child_stmt_obj.page_ranges = { ... } # This is redundant and unnecessary ORM baggage.

    first_page_idx = parent_statement.page_ranges[statement_type][0]
    if first_page_idx in child_stmt_obj.page_lines:
        _extract_statement_balances(
            child_stmt_obj, child_stmt_obj.page_lines[first_page_idx]
        )  # Calls standalone
    else:
        logging.warning(
            "First page for %s section not found in page lines for %s, cannot extract balances.",
            statement_type,
            child_stmt_obj.filename,
        )
        # Decide if this should return False and propagate failure

    child_stmt_obj.statement_transactions = parse_transactions_from_pages(
        child_stmt_obj.page_lines
    )
    if child_stmt_obj.statement_transactions:
        for transaction in child_stmt_obj.statement_transactions:
            transaction.statement_source = (
                child_stmt_obj  # Assign the parent Statement object
            )
        return True
    logging.warning(
        "Failed to create transactions for %s section from combined statement %s.",
        statement_type,
        child_stmt_obj.filename,
    )
    return False


# --- Statement-Level Processors ---


def parse_statement_summary(stmt_obj: Statement) -> bool:
    """
    Parses the statement summary information (type, dates, page ranges).
    Returns True if essential summary data is found, False otherwise.
    """
    # This will operate on whatever is in self.page_lines (full PDF or subset)
    stmt_obj.statement_type = _get_statement_type(stmt_obj)  # Calls standalone
    stmt_obj.bank = _get_statement_bank(stmt_obj)
    dates_extracted = _extract_statement_dates_from_page(stmt_obj)  # Calls standalone

    if not stmt_obj.statement_type or not dates_extracted:
        return False

    if stmt_obj.statement_type == "Combined":
        combined_ranges = extract_combined_page_ranges(stmt_obj)  # Calls standalone
        stmt_obj.page_ranges = combined_ranges
        if not combined_ranges:
            logging.warning(
                "Combined statement page ranges not identified for %s.",
                stmt_obj.filename,
            )
            return False
    return True


def generate_new_filename(stmt_obj: Statement) -> str:
    """
    Generates the new standardized filename for the PDF based on statement data.
    """
    if not all(
        [
            stmt_obj.statement_type,
            stmt_obj.start_date,
            stmt_obj.end_date,
        ]
    ):
        logging.warning(
            "Missing statement data to generate filename for %s.", stmt_obj.filename
        )
        return ""
    period = _get_statement_period(stmt_obj)  # Calls standalone
    return (
        f"BOA_{stmt_obj.statement_type}_"
        f"{period}_"
        f"Statement_{stmt_obj.start_date.strftime('%Y%m%d')}"
        f"_to_{stmt_obj.end_date.strftime('%Y%m%d')}.pdf"
    )


# --------------------------------------
# Main File Processor
# --------------------------------------


def process_single_pdf_file_to_statements(
    pdf_file_path: str, year: str, pdf_content: bytes
) -> tuple[list["Statement"], "Statement" | None]:
    """
    Processes a single PDF file, creating one or more Statement objects from it.
    Handles combined statements by splitting them into multiple Statement objects.
    Returns a tuple:
    - A list of successfully parsed Statement objects (logical statements).
    - The 'source_pdf_stmt' Statement object representing the overall PDF
    (for renaming the physical file), or None if parsing fails.
    """
    all_logical_statements_from_this_file = []

    source_pdf_stmt = Statement(initial_filename=pdf_file_path, year=year)

    # Assign the binary PDF data here
    source_pdf_stmt.pdf_data = pdf_content

    if not extract_pdf_lines(source_pdf_stmt, pdf_content):  # Call standalone
        logging.error("Failed to extract lines for %s.", pdf_file_path)
        return [], None

    if not parse_statement_summary(source_pdf_stmt):  # Call standalone
        logging.error("Failed to parse initial summary from %s.", pdf_file_path)
        return [], None

    if source_pdf_stmt.statement_type == "Combined":
        checking_stmt = Statement(initial_filename=pdf_file_path, year=year)
        if _build_child_statement(checking_stmt, "checking", source_pdf_stmt):
            checking_stmt.statement_type = "Combined Checking"
            for transaction in checking_stmt.statement_transactions:
                if transaction.transaction_transaction_type == "Check":
                    checking_stmt.total_check_count += 1
                    checking_stmt.total_check_amount += transaction.transaction_amount
            all_logical_statements_from_this_file.append(checking_stmt)

        savings_stmt = Statement(initial_filename=pdf_file_path, year=year)
        if _build_child_statement(savings_stmt, "savings", source_pdf_stmt):
            savings_stmt.statement_type = "Combined Savings"
            all_logical_statements_from_this_file.append(savings_stmt)
    else:
        # Not a combined statement, it's a single Checking or Savings statement
        _extract_statement_balances(
            source_pdf_stmt, source_pdf_stmt.page_lines[0]
        )  # Call standalone
        source_pdf_stmt.statement_transactions = parse_transactions_from_pages(
            source_pdf_stmt.page_lines
        )
        if source_pdf_stmt.statement_transactions:
            for transaction in source_pdf_stmt.statement_transactions:
                transaction.statement_source = (
                    source_pdf_stmt  # Assign the parent Statement object
                )
            all_logical_statements_from_this_file.append(source_pdf_stmt)

    logging.info(
        "Successfully parsed %s statement from %s.",
        source_pdf_stmt.statement_type,
        pdf_file_path,
    )

    return all_logical_statements_from_this_file, source_pdf_stmt


# --------------------------------------
# Overall Orchestrator
# --------------------------------------


def _get_physical_filenames_from_db(db_manager: BoaDbManager) -> set[str]:
    """
    Retrieves a set of all physical filenames (as they would be after renaming)
    currently stored in the database.
    """
    try:
        return db_manager.get_all_filenames()
    except Exception as e:
        logging.error(
            "Failed to retrieve existing physical filenames from DB for pre-check: %s",
            e,
        )
        return set()


# In src/boa_statement.py
def process_and_insert_statements(db_manager: BoaDbManager,
                                  file_path: str,
                                  pdf_content: bytes) -> list[dict]:
    """
    Processes a single uploaded statement file, parses it, and adds it to the database.
    Returns a list of status dictionaries for the file.
    """
    status_list = []
    file_status = {
        "old_filename": os.path.basename(file_path),
        "new_filename": "",
        "status": "pending",
        "message": "",
    }

    # Step 1: Process the file to get statement metadata
    # Year is derived from the PDF content (not hardcoded); pass None as placeholder
    logical_statements, master_stmt_for_pdf_file = (
        process_single_pdf_file_to_statements(
            file_path, None, pdf_content
        )
    )

    # Step 2: Check for parsing errors
    if not logical_statements:
        file_status["status"] = "error"
        file_status["message"] = "Not a valid bank statement or parsing failed."
        status_list.append(file_status)
        return status_list

    # Step 3: Generate a new filename based on the metadata
    new_filename = generate_new_filename(master_stmt_for_pdf_file)
    file_status["new_filename"] = new_filename

    # Step 4: Build the destination path and check for duplicates
    dest_dir = os.path.join(STATEMENT_DIRECTORY, str(master_stmt_for_pdf_file.year))
    os.makedirs(dest_dir, exist_ok=True)
    new_full_path = os.path.join(dest_dir, new_filename)

    existing_filenames_in_db = _get_physical_filenames_from_db(db_manager)
    if new_full_path in existing_filenames_in_db:
        file_status["status"] = "error"
        file_status["message"] = "Statement already exists in the database."
        status_list.append(file_status)
        return status_list

    # Step 5: Move the file to the destination directory with the new name
    try:
        shutil.move(file_path, new_full_path)
        logging.info("Moved '%s' to '%s'", os.path.basename(file_path), new_full_path)
    except OSError as e:
        file_status["status"] = "error"
        file_status["message"] = f"Failed to move file: {e}"
        status_list.append(file_status)
        return status_list

    # Step 6: Insert into the database using the full destination path
    for stmt_obj in logical_statements:
        stmt_obj.filename = new_full_path
        db_manager.insert_statement(stmt_obj)

    file_status["status"] = "success"
    file_status["message"] = f"File renamed to '{new_filename}' and added to database."
    status_list.append(file_status)
    return status_list


def main():
    """Main execution function: Orchestrates statement parsing and database insertion."""

    clear_log_on_start = True
    log_file_path = "boa_pdf_reader.log"

    # Conditionally clear the log file
    if clear_log_on_start and os.path.exists(log_file_path):
        try:
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.truncate(0)  # Truncate the file to zero length
            logging.info("Log file '%s' cleared successfully.", log_file_path)
        except OSError as e:
            logging.error("Failed to clear log file '%s': %s", log_file_path, e)

    setup_logging()

    try:
        logging.info("Starting new statement processing cycle.")

        # Step 1: Find new PDF files in the STATEMENT_DIRECTORY
        new_pdf_files_by_year = find_new_statement_files()
        all_new_pdf_file_paths = []
        for _, paths in new_pdf_files_by_year.items():
            all_new_pdf_file_paths.extend(paths)

        if not all_new_pdf_file_paths:
            logging.info("No new PDF files found to process.")
            return

        logging.info(
            "Found %s new PDF files to process.", len(all_new_pdf_file_paths)
        )

        # Step 2: Initialize BoaDbManager once for the entire processing cycle
        db_manager = BoaDbManager()

        # Step 3: Process and insert the new files
        status_list = []
        for file_path in all_new_pdf_file_paths:
            # Read the binary content of the PDF file
            with open(file_path, 'rb') as pdf_file:
                pdf_contents = pdf_file.read()

            # Process the single file and its content.
            # This function will also check for duplicates and handle the file renaming.
            file_results = process_and_insert_statements(db_manager, file_path, pdf_contents)
            status_list.extend(file_results)

        # The loop now handles the processing, so we just need to log a summary
        if any(s['status'] == 'success' for s in status_list):
            logging.info("Processing cycle complete. New statements added.")
        else:
            logging.info("No new statements were added to the database.")

    except Exception as e:
        logging.critical(
            "An unhandled critical error occurred during main execution: %s",
            e,
            exc_info=True,
        )
    finally:
        if 'db_manager' in locals() and db_manager:
            db_manager.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    main()

'''
src/boa_app.py
@author: dgrady

'''

import logging
import os
import io
import sys
from datetime import datetime, date
import pandas as pd
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename

# Import your database manager and models
from boa_db_manager import BoaDbManager
from boa_models import Statement, Transaction
from boa_statement import process_and_insert_statements

# --- Logging Setup ---
# Get the directory of the current file (src/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the project root (BankOfAmerica/)
project_root = os.path.join(current_dir, os.pardir)
log_file_path = os.path.join(
    project_root, "flask_boa_app.log"
)  # Changed log filename for clarity

# Ensure the log directory exists
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path, mode="a"),
    ],
    force=True,
)
app_logger = logging.getLogger(__name__)

def cleanup_temp_uploads():
    """
    Removes all files from the temp_uploads directory.
    """
    temp_dir = 'temp_uploads'
    if os.path.exists(temp_dir):
        app_logger.info("Cleaning up %s directory.", temp_dir)
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                app_logger.error("Failed to delete %s. Reason: %s", file_path, e)

# Call the cleanup function when the app starts up
cleanup_temp_uploads()

# --- Flask App Initialization ---
app = Flask(__name__)
app_logger.info("Flask application starting up...")

# In src/boa_app.py
def load_data_from_db() -> pd.DataFrame:
    """
    Loads ALL Statement and Transaction data from the SQLite database,
    joining them to enrich transaction data with statement details.
    Returns a pandas DataFrame of all transactions found.
    """
    db_manager = BoaDbManager(force_recreate=False)

    try:
        rows = db_manager.get_all_transactions_with_statements()

        if not rows:
            app_logger.info("No transaction data found in database.")
            return pd.DataFrame()

        transactions_data = []
        for row in rows:
            statement_year = row.get('statement_year')
            statement_month = row.get('statement_month')
            statement_type = row.get('statement_type')
            statement_period = row.get('statement_period')
            statement_start_date = None

            start_date_str = row.get('statement_start_date')
            end_date_str = row.get('statement_end_date')
            if start_date_str and end_date_str:
                start_date = date.fromisoformat(start_date_str)
                end_date = date.fromisoformat(end_date_str)
                statement_start_date = start_date
                start_str = start_date.strftime('%b %d')
                end_str = end_date.strftime('%b %d')
                statement_period = f"{start_str} - {end_str}"

            transaction_description_override = row.get('transaction_description_override')
            transaction_description = row.get('transaction_description')
            check_number = row.get('transaction_check_number')
            if check_number:
                transaction_description = 'Check ' + str(check_number)
            transaction_category = row.get('transaction_primary_category')
            secondary = row.get('transaction_secondary_category')
            if transaction_category and secondary:
                transaction_category = transaction_category + ' ' + secondary

            # Parse transaction_date from ISO string to datetime
            txn_date_str = row.get('transaction_date')

            transactions_data.append(
                {
                    "id": row['id'],
                    "date": txn_date_str,
                    "description": transaction_description,
                    "description_override": transaction_description_override,
                    "amount": float(row['transaction_amount']) if row['transaction_amount'] else 0.0,
                    "type": row.get('transaction_transaction_type'),
                    "check_number": check_number,
                    "statement_id": row.get('statement_id'),
                    "comment": row.get('transaction_comment'),
                    "transaction_category": (
                        transaction_category
                        if transaction_category
                        else "Other"
                    ),
                    "statement_year": statement_year,
                    "statement_month": statement_month,
                    "statement_account_type": statement_type,
                    "statement_period": statement_period,
                    "statement_start_date": statement_start_date
                }
            )

        df = pd.DataFrame(transactions_data)

        if df.empty:
            app_logger.info("No data found in database.")
            return pd.DataFrame()

        df["date"] = pd.to_datetime(df["date"])

        app_logger.info("Data loaded successfully from database for Flask app.")
        return df
    except Exception as e:
        app_logger.error(
            "Failed to load data from database for Flask app: %s", e, exc_info=True
        )
        return pd.DataFrame()
    finally:
        db_manager.close()


# --- Flask Routes ---
@app.route("/")
@app.route("/dashboard/<int:selected_year>")
def dashboard_home(selected_year: int = None):
    """
    Loads all transactions, prepares data for the dashboard grid,
    and renders the main dashboard HTML template.
    """
    account_type_filter = request.args.get('account_type', 'All')

    app_logger.info("Accessing / route for dashboard.")

    df = load_data_from_db()

    # Initialize variables for robustness
    all_available_years = []
    df_for_pivot = pd.DataFrame() # Initialize as empty DataFrame

    if not df.empty:
        if 'statement_year' in df.columns and not df['statement_year'].dropna().empty:
            all_available_years = sorted(df['statement_year']
                                         .dropna()
                                         .unique()
                                         .astype(int)
                                         .tolist(), reverse=True)

            print(f"all_available_years: {all_available_years}")
            if selected_year is None or selected_year not in all_available_years:
                selected_year = all_available_years[
                    0] if all_available_years else datetime.now().year

            df_for_pivot = df[df['statement_year'] == selected_year].copy()

            # Then, apply the account type filter if needed.
            if account_type_filter != "All":
                if account_type_filter == "Checking":
                    df_for_pivot = df_for_pivot[
                        (df_for_pivot['statement_account_type'] == 'Checking') |
                        (df_for_pivot['statement_account_type'] == 'Combined Checking')
                    ].copy()
                elif account_type_filter == "Savings":
                    df_for_pivot = df_for_pivot[
                        (df_for_pivot['statement_account_type'] == 'Savings') |
                        (df_for_pivot['statement_account_type'] == 'Combined Savings')
                    ].copy()

            # --- DEBUGGING ---
            app_logger.info("df_for_pivot columns: %s", df_for_pivot.columns.tolist())
            app_logger.info("df_for_pivot is empty? %s", df_for_pivot.empty)
            # --- END DEBUGGING ---

        else:
            app_logger.warning(
                "'statement_year' not found. Dashboard will be empty for display year."
                )

    if df.empty:
        return render_template(
            "dashboard.html",
            no_data_message="<p>No transaction data available. Please process statements.</p>",
            pivot_data=None,
            header_labels=None,
            current_year=datetime.now().year,
            selected_year=datetime.now().year,
            all_available_years=[],
            selected_account_type=account_type_filter
        )

    # Check for empty DataFrame after all filtering
    if df_for_pivot.empty:
        message = f"No transaction data found for year ({selected_year})."
        if account_type_filter != "All":
            message = (f"No transaction data found for {account_type_filter}"
                       f" account in year ({selected_year}).")
        return render_template(
            "dashboard.html",
            no_data_message=f"<p>{message}</p>",
            pivot_data=None,
            header_labels=None,
            current_year=datetime.now().year,
            selected_year=selected_year,
            all_available_years=all_available_years,
            selected_account_type=account_type_filter,
            cache_buster=datetime.now().strftime("%Y%m%d%H%M%S%f")
        )

    # Initialize header_labels for the template
    header_labels = []

    # Define standard month order for columns
    month_order = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]

    # used to fill out empty statement period headers
    month_order_abbr = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov"]


    # Conditional logic based on account type filter
    if account_type_filter == 'All':
        df_for_pivot['month_name'] = df_for_pivot['date'].dt.strftime('%B')

        header_labels = month_order

        pivot_table = pd.pivot_table(
            df_for_pivot,
            values='amount',
            index='transaction_category',
            columns='month_name',
            aggfunc='sum',
            fill_value=0
        )

        pivot_table = pivot_table.reindex(columns=month_order, fill_value=0)
    else:
        sorted_periods_df = df_for_pivot[['statement_start_date', 'statement_period']].sort_values(
            by='statement_start_date').drop_duplicates()
        statement_period_order = sorted_periods_df['statement_period'].tolist()

        header_labels = statement_period_order
        last_period_df = sorted_periods_df.iloc[-1]
        last_start_date = last_period_df['statement_start_date']

        # Use BoaDbManager to query for the statement with the last_start_date
        db_manager = BoaDbManager(force_recreate=False)
        stmt_row = db_manager.get_statement_by_start_date(
            last_start_date.isoformat() if isinstance(last_start_date, date) else str(last_start_date)
        )
        db_manager.close()
        last_end_date = date.fromisoformat(stmt_row['end_date']) if stmt_row else None

        # Generate subsequent headers to fill out the year
        if last_end_date:
            current_date = last_end_date
            while current_date.year == selected_year and len(header_labels) < 12:
                next_start_date = current_date + pd.DateOffset(days=1)
                next_end_date = next_start_date + pd.DateOffset(months=1) - pd.DateOffset(days=1)

                new_header = f"{next_start_date.strftime('%b %d')} - {next_end_date.strftime('%b %d')}"

                if next_start_date.year == selected_year:
                    header_labels.append(new_header)
                    current_date = next_end_date
                else:
                    break

        # Create the pivot table using statement_period as the column
        pivot_table = pd.pivot_table(
            df_for_pivot,
            values='amount',
            index='transaction_category',
            columns='statement_period',
            aggfunc='sum',
            fill_value=0
        )

        pivot_table = pivot_table.reindex(columns=statement_period_order, fill_value=0)

    # Add 'Total' column for each category
    pivot_table['Total'] = pivot_table.sum(axis=1)

    # Add 'Total' row for each month and grand total
    pivot_table.loc['Total'] = pivot_table.sum(axis=0)

    pivot_table.index.name = None
    pivot_table.columns.name = None

    # --- End Grid Data Preparation ---
    app_logger.info("Data for dashboard -   selected_year: %s",
                    str(selected_year))
    return render_template(
        "dashboard.html",
        pivot_data=pivot_table,
        month_order=month_order,
        header_labels=header_labels,
        current_year=datetime.now().year,
        selected_year=selected_year,
        all_available_years=all_available_years,
        selected_account_type=account_type_filter,
        cache_buster=datetime.now().strftime("%Y%m%d%H%M%S%f")
    )

@app.route("/get_details")
def get_transaction_details():
    """Endpoint to retrieve transaction details based on filters."""
    summary_rows = []

    db_manager = BoaDbManager(force_recreate=False)
    try:
        # Get and convert parameters
        year_str = request.args.get('year')
        year = int(year_str)
        category = request.args.get('category')
        statement_period = request.args.get('statement_period')
        account_type_filter = request.args.get('account_type')
        month_or_period = request.args.get('month')

        # Determine numeric month if account type is 'All'
        month_num = None
        if account_type_filter == 'All':
            try:
                month_num = datetime.strptime(month_or_period, '%B').month
            except ValueError:
                return jsonify({"error": f"Invalid month name: {month_or_period}"}), 400

        # --- Fetch transactions ---
        transaction_rows = db_manager.get_transactions_filtered(
            year=year,
            category=category,
            month_num=month_num,
            account_type=account_type_filter,
            statement_period=statement_period,
        )

        # --- Fetch statement summaries ---
        statement_rows = db_manager.get_statements_filtered(
            year=year,
            month_num=month_num,
            account_type=account_type_filter,
            statement_period=statement_period,
        )

        # --- Handle No Results ---
        if not transaction_rows and not statement_rows:
            return jsonify({
                'account_summary': [],
                'transactions': [],
                'message': 'No data found for this period'
            }), 404

        # --- Prepare statement summary data ---
        for stmt in statement_rows:
            start_dt = date.fromisoformat(stmt['start_date']) if stmt.get('start_date') else None
            end_dt = date.fromisoformat(stmt['end_date']) if stmt.get('end_date') else None
            summary_rows.append({
                'start_date': start_dt.strftime('%m-%d-%Y') if start_dt else 'N/A',
                'end_date': end_dt.strftime('%m-%d-%Y') if end_dt else 'N/A',
                'beginning_balance': float(stmt['beginning_balance']) if stmt.get('beginning_balance') else 0.0,
                'ending_balance': float(stmt['ending_balance']) if stmt.get('ending_balance') else 0.0,
                'type': stmt.get('statement_type'),
                'statement_id': stmt['id']
            })

        # --- Prepare transaction data ---
        transactions_data = []
        for tx in transaction_rows:
            bank_name = tx.get('bank', 'N/A')
            account_type = tx.get('statement_type', 'N/A')
            display_description = tx.get('transaction_description_override') or tx.get('transaction_description')
            check_number = tx.get('transaction_check_number')
            if check_number:
                display_description = f'Check {check_number}'

            txn_date_str = tx.get('transaction_date')
            txn_date = date.fromisoformat(txn_date_str) if txn_date_str else None

            transactions_data.append({
                'id': tx['id'],
                'bank': bank_name,
                'account_type': account_type,
                'date': txn_date.strftime('%m-%d-%Y') if txn_date else 'N/A',
                'description': display_description,
                'amount': float(tx['transaction_amount']) if tx.get('transaction_amount') else 0.00,
                'check_number': check_number,
                'transaction_type': tx.get('transaction_transaction_type'),
                'comment': tx.get('transaction_comment'),
                'primary_category': tx.get('transaction_primary_category'),
                'secondary_category': tx.get('transaction_secondary_category'),
            })

        # Return JSON with the prepared data
        return jsonify({
            'account_summary': summary_rows,
            'transactions': transactions_data,
            'message': 'Details loaded successfully'
        })

    except Exception as e:
        app_logger.error("Error in get_transaction_details: %s", e, exc_info=True)
        return jsonify({"error": "Failed to load details due to server error."}), 500
    finally:
        db_manager.close()


@app.route('/upload_statements', methods=['POST'])
def upload_statements():
    '''
    Endpoint to handle file upload and processing.
    '''
    if 'statements' not in request.files:
        return jsonify({'message': 'No files uploaded'}), 400

    uploaded_files = request.files.getlist('statements')
    temp_dir = 'temp_uploads'
    os.makedirs(temp_dir, exist_ok=True)
    file_paths_and_content = []
    db_manager = BoaDbManager(force_recreate=False)

    for file in uploaded_files:
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        filepath = os.path.join(temp_dir, filename)

        # Save the file to the temporary directory.
        file.save(filepath)

        # Read the file content as binary data
        with open(filepath, 'rb') as f:
            file_content = f.read()

        # Store both the path and content for processing
        file_paths_and_content.append({'path': filepath, 'content': file_content})

    # Process and insert statements with their PDF content
    status_list = []
    for item in file_paths_and_content:
        result = process_and_insert_statements(db_manager, item['path'], item['content'])
        status_list.extend(result)

    # Clean up temporary files
    for item in file_paths_and_content:
        if os.path.exists(item['path']):
            os.remove(item['path'])

    db_manager.close()
    return jsonify({'status': status_list})

@app.route("/view_statement/<int:statement_id>")
def view_statement(statement_id):
    """Endpoint to serve a PDF file for a specific statement."""
    db_manager = BoaDbManager(force_recreate=False)
    stmt_row = db_manager.get_statement_by_id(statement_id)
    db_manager.close()

    if stmt_row and stmt_row.get('pdf_data'):
        return send_file(
            io.BytesIO(stmt_row['pdf_data']),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=stmt_row.get('filename', 'statement.pdf')
        )
    return "Statement not found or no PDF data.", 404


# --- Main entry point for Flask's development server ---
if __name__ == "__main__":
    app_logger.info("Running Flask app in development mode.")
    app.run(debug=True, host="0.0.0.0", port=5000)

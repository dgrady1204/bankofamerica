let activeCell = null; // Global variable to track the selected cell
const detailContainer = document.getElementById("transaction-detail-container");
let droppedFiles = [];
const formatCurrency = (value) =>
  value.toLocaleString("en-US", { style: "currency", currency: "USD" });

// Function to handle the AJAX request for transaction details.
function fetchTransactionDetails(clickedCell) {
  const category = clickedCell.dataset.category;
  const month = clickedCell.dataset.month;
  const header = clickedCell.dataset.header;
  const currentDashboardYear = clickedCell.dataset.year;
  const selectedAccountType = document.getElementById(
    "account-type-select"
  ).value;
  let activeSummaryCell = null; // Global variable to track the selected summary cell

  // 1. Handle selection/deselection of cells
  if (activeCell) {
    activeCell.classList.remove("selected-cell");
  }
  if (activeSummaryCell) {
    activeSummaryCell.classList.remove("selected-cell");
  }
  detailContainer.innerHTML = "";
  if (activeCell === clickedCell) {
    detailContainer.style.display = "none";
    activeCell = null;
    return;
  }
  // Remove the highlight from the previous transaction details table
  if (activeSummaryCell === clickedCell) {
    detailContainer.style.display = "none";
    activeSummaryCell = null;
    return;
  }
  clickedCell.classList.add("selected-cell");
  activeCell = clickedCell;
  activeSummaryCell = clickedCell;
  detailContainer.style.display = "block";

  // 2. Make AJAX request to Flask backend
  // Dynamically set the parameter name based on the account type
  let monthParam = "";
  let statementPeriodParam = "";

  if (selectedAccountType === "All") {
    monthParam = header;
  } else {
    // We need to pass both month and statement period to handle the backend logic
    // The backend's get_details function is currently hardcoded to use month.
    // So for now we will pass a month, but in the future we'll need to update the backend
    // to handle statement_period as well.
    const month = header.split(" - ")[1].split(" ")[0];
    monthParam = month;
    statementPeriodParam = header;
  }
  const fullUrl =
    `/get_details?category=${encodeURIComponent(category)}` +
    `&month=${encodeURIComponent(monthParam)}` +
    `&year=${encodeURIComponent(currentDashboardYear)}` +
    `&account_type=${encodeURIComponent(selectedAccountType)}` +
    `&statement_period=${encodeURIComponent(statementPeriodParam)}`;

  fetch(fullUrl)
    .then((response) => {
      if (response.status === 404) {
        // Handle 404 as a "no data found" scenario
        return null; // Return null to the next .then() block
      }
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      // If the data is null (from the 404 check), display a no-data message
      if (data === null) {
        detailContainer.innerHTML = `
              <div class="balances-and-transactions-container">
                  <h2>Details for ${category} in ${header} (${currentDashboardYear}, ${selectedAccountType})</h2>
                  <p>No transactions found for this selection.</p>
              </div>
          `;
        return; // Stop execution here
      }
      const accountSummary = data.account_summary;
      const transactions = data.transactions;

      // Start of the main container
      let detailsHtml = `
          <div class="balances-and-transactions-container">
              <h2>Details for ${category} in ${header} (${currentDashboardYear}, ${selectedAccountType})</h2>
              
              <!-- NEW: Two-Column Wrapper -->
              <div class="details-content-wrapper">
                  
                  <!-- Left Column: Activity Summary -->
                  <div class="summary-column">
                      <div class="balance-summary">
      `;

      // --- Activity Summary (Left Column Content) ---
      if (accountSummary) {
        if (selectedAccountType !== "All") {
          // --- NEW: Calculate Activity for Single-Account View ---
          // The 'transactions' array is already filtered for this statement by the backend.
          let deposits = 0;
          let withdrawals = 0;
          let netActivity = 0;
          transactions.forEach((tx) => {
            const amount = parseFloat(tx.amount);
            if (amount > 0) {
              deposits += amount;
            } else {
              withdrawals += amount; // withdrawals are negative
            }
            netActivity += amount;
          });
          // --- END CALCULATION ---

          accountSummary.forEach((summary) => {
            let viewPdfButton = "";
            viewPdfButton = `
                  <button class="form-control"
                      onclick="openPdfView(${summary.statement_id}, '${summary.type}', '${summary.start_date}', '${summary.end_date}')">
                      View Statement PDF
                  </button>`;
            // *** NEW HTML STRUCTURE FOR SINGLE-ACCOUNT VIEW ***
            detailsHtml += `
                      <div class="account-summary-container">
                        <!-- Title -->
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                            <h3>${summary.type} Statement</h3>
                        </div>

                        <!-- Group 1: Balances -->
                        <div class="summary-line">
                            <span>Beginning Balance:</span>
                            <strong>${formatCurrency(
                              summary.beginning_balance
                            )}</strong>
                        </div>
                        <div class="summary-line">
                            <span>Ending Balance:</span>
                            <strong>${formatCurrency(
                              summary.ending_balance
                            )}</strong>
                        </div>

                        <hr class="summary-divider">

                        <!-- Group 2: Activity -->
                        <div class="summary-line">
                            <span>Deposits:</span>
                            <strong class="positive-amount">${formatCurrency(
                              deposits
                            )}</strong>
                        </div>
                        <div class="summary-line">
                            <span>Withdrawals:</span>
                            <strong class="negative-amount">${formatCurrency(
                              withdrawals
                            )}</strong>
                        </div>
                        
                        <hr class="summary-divider-light">

                        <div class="summary-line">
                            <strong>Net Activity:</strong>
                            <strong class="${
                              netActivity < 0
                                ? "negative-amount"
                                : "positive-amount"
                            }">${formatCurrency(netActivity)}</strong>
                        </div>

                        <!-- Group 3: Button -->
                        <div class="summary-button-container">
                            ${viewPdfButton}
                        </div>
                      </div>
                    `;
          });
        } else {
          // Content for aggregated view: Show Net Activity
          let totalDeposits = 0;
          let totalWithdrawals = 0;
          let totalNetActivity = 0;
          const accountActivity = {};
          accountActivity["Total"] = {
            deposits: 0,
            withdrawals: 0,
            net: 0,
          };

          transactions.forEach((tx) => {
            const accountKey = tx.account_type || "Unknown";
            const amount = parseFloat(tx.amount);

            if (!accountActivity[accountKey]) {
              accountActivity[accountKey] = {
                deposits: 0,
                withdrawals: 0,
                net: 0,
              };
            }

            // Deposits are typically positive, withdrawals negative
            if (amount > 0) {
              accountActivity[accountKey].deposits += amount;
              accountActivity["Total"].deposits += amount;
            } else {
              accountActivity[accountKey].withdrawals += amount;
              accountActivity["Total"].withdrawals += amount;
            }
            accountActivity[accountKey].net += amount;
            accountActivity["Total"].net += amount;
          });

          for (const [type, activity] of Object.entries(accountActivity)) {
            if (type === "Unknown") continue;

            const netActivityClass =
              activity.net < 0 ? "negative-amount" : "positive-amount";
            totalNetActivity += activity.net;

            detailsHtml += `
            <div class="account-summary-container">
                <div style="display: flex; justify-content: space-between; align-items: center">
                    <h3>${type} Activity</h3>
                </div>
                <p class="summary-line"><span>Deposits:</span> <strong class="positive-amount">${formatCurrency(
                  activity.deposits
                )}</strong></p>
                <p class="summary-line"><span>Withdrawals:</span> <strong class="negative-amount">${formatCurrency(
                  activity.withdrawals
                )}</strong></p>
                <hr style="margin: 5px 0;">
                <p class="summary-line">
                    <strong>Net Activity:</strong>
                    <strong class="${netActivityClass}">${formatCurrency(
              activity.net
            )}</strong>
                </p>
            </div>
        `;
          }
        }
      }

      // Close the balance-summary div and the new summary-column wrapper
      detailsHtml += `
                      </div> 
                  </div> 
                  
                  <!-- Right Column: Transaction Details Table -->
                  <div class="transactions-column">
      `;

      if (data.transactions.length > 0) {
        detailsHtml += `
            <table id="transaction-detail-table" border="1" class="detail-table tablesort">
                <thead>
                    <tr>
                        <th data-sort-method="my-date-sort" data-sort-initial="desc">Date</th>
                        <th data-sort-method="string">Description</th>
                        <th data-sort-method="number">Amount</th>
                    </tr>
                </thead>
                <tbody id="transaction-scroll-wrapper">
                    ${transactions
                      .map((tx) => {
                        // NEW: Create a class based on the account type
                        const rowClass = tx.account_type
                          ? `account-${tx.account_type.toLowerCase()}`
                          : "account-unknown";
                        return `
                        <tr data-id="${tx.id}" class="${rowClass}">
                            <td>${tx.date}</td>
                            <td>${tx.description}</td>
                            <td class="amount-column ${
                              tx.amount < 0 ? "negative-amount" : ""
                            }">
                                ${tx.amount.toLocaleString("en-US", {
                                  style: "currency",
                                  currency: "USD",
                                })}
                            </td>
                        </tr>
                    `;
                      })
                      .join("")}
                </tbody>
            </table>
        `;
      } else {
        detailsHtml += "<p>No transactions found for this selection.</p>";
      }

      // Close the transactions-column wrapper
      detailsHtml += `
                  </div>
              </div> 
          </div> 
      `;

      detailContainer.innerHTML = detailsHtml;
      setTimeout(() => {
        const detailTable = document.getElementById("transaction-detail-table");
        if (detailTable) {
          const ts = new Tablesort(detailTable);
          const dateHeader = detailTable.querySelector(
            'th[data-sort-method="my-date-sort"]'
          );
          if (dateHeader) {
            ts.sortTable(dateHeader, false);
          }
        }
      }, 50);
    })
    .catch((error) => {
      console.error("Error fetching details:", error);
      detailContainer.innerHTML = `<p>Error loading details: ${error.message}. Please check console for more info.</p>`;
    });
}

function updateDashboardFilters() {
  const selectedYear = document.getElementById("year-select").value;
  const selectedAccountType = document.getElementById(
    "account-type-select"
  ).value;
  window.location.href = `/dashboard/${selectedYear}?account_type=${encodeURIComponent(
    selectedAccountType
  )}`;
}

// Add a new function to handle the button click
function openPdfView(statementId, statementType, startDate, endDate) {
  // Construct the URL with the statement ID
  const url = `/view_statement/${statementId}`;

  // Construct the new tab title
  const newTitle = `${statementType} Statement from ${startDate} to ${endDate}`;

  // Open a new window or tab
  const newWindow = window.open(url, "_blank");

  // Set the title of the new window/tab after it loads
  if (newWindow) {
    newWindow.onload = function () {
      newWindow.document.title = newTitle;
    };
  }
}

// Custom Date Sort Function for MM-DD-YYYY format. Moved out of DOMContentLoaded.
Tablesort.extend(
  "my-date-sort",
  function (t) {
    return !(!t.textContent || !t.textContent.match(/^\d{2}-\d{2}-\d{4}$/));
  },
  function (t, e) {
    const dateA = new Date(t).getTime();
    const dateB = new Date(e).getTime();
    return dateB - dateA;
  }
);

document.addEventListener("DOMContentLoaded", () => {
  // All code that interacts with the DOM is now inside this listener.
  const modal = document.getElementById("add-statements-modal");
  const addStatementsButton = document.getElementById("add-statements-button");
  const closeButton = document.querySelector(".close-button");
  const fileInput = document.getElementById("file-input");
  const browseButton = document.getElementById("modal-browse-button");
  const addToDbButton = document.getElementById("add-to-db-button");
  const fileList = document.getElementById("file-list");
  const alertOkButton = document.getElementById("alert-ok-button");
  const detailContainer = document.getElementById(
    "transaction-detail-container"
  );

  // Check if the container exists before adding the listener
  if (detailContainer) {
    detailContainer.addEventListener("click", (event) => {
      const clickedRow = event.target.closest("tr");
      const table = document.getElementById("transaction-detail-table");

      // Ensure the click was on a row *inside* the transaction-detail-table
      if (clickedRow && table && table.contains(clickedRow)) {
        // Now you can call your function with the clicked row
        console.log("There was a row clicked:", clickedRow);
        openInputModal(clickedRow);
      }
    });
  }

  // Function to handle the modal opening. It's good practice to define this
  // function at a scope accessible by the event listener.
  // A global variable to hold the ID of the transaction being edited
  let currentTransactionId = null;

  function openInputModal(row) {
    // Extract data from the clicked row.
    const rowData = {
      id: row.dataset.id, // Make sure you add a data-id attribute to your <tr>
      date: row.querySelector("td:nth-child(1)").textContent,
      description: row.querySelector("td:nth-child(2)").textContent,
      amount: row.querySelector(".amount-column").textContent,
      checkNumber: row.querySelector(".check-number-column")?.textContent || "", // Optional check number
      // ... and so on for other fields
    };

    // Populate the modal's display fields
    document.getElementById("modal-date").textContent = rowData.date;
    document.getElementById("modal-description").textContent =
      rowData.description;
    document.getElementById("modal-amount").textContent = rowData.amount;
    document.getElementById("modal-check-number").textContent =
      rowData.checkNumber;
    // ... populate other display fields

    // Populate the user-editable fields
    document.getElementById("override-description").value = rowData.description; // Default value
    // You'll need to fetch the existing categories for the datalists
    // We'll discuss this in the next step.

    // Store the transaction ID for later use during save/delete
    currentTransactionId = rowData.id;

    // Show the modal
    const modal = document.getElementById("detail-modal");
    modal.style.display = "block";
  }

  // Purpose: This event listener is attached to the "Add Statements" button on the main dashboard page.
  // Action: When clicked, it sets the modal's display style to 'block', making the modal window visible to the user.
  addStatementsButton.addEventListener("click", () => {
    modal.style.display = "block";
  });

  // Purpose: This event listener is attached to the "x" button in the top-right corner of the modal window.
  // Action: When clicked, it sets the modal's display style to 'none', hiding the modal, and then calls
  // the resetModalState() function to clear the file list and button state.
  closeButton.addEventListener("click", () => {
    modal.style.display = "none";
    resetModalState();
  });

  // Purpose: This event listener is attached to the "Browse" button inside the modal.
  // Action: When clicked, it prevents the default browser behavior and programmatically
  // triggers a click on the hidden fileInput element, which opens the system's file browser.
  browseButton.addEventListener("click", (e) => {
    e.preventDefault();
    fileInput.click();
  });

  // Purpose: This event listener is attached to the hidden file input element. It's
  // triggered whenever the user selects one or more files.
  // Action: It calls the handleFiles() function, passing it the list of selected files.
  fileInput.addEventListener("change", () => {
    handleFiles(fileInput.files);
  });

  // Purpose: This event listener is attached to the "Add to Database" button inside the modal.
  // Action: When clicked, it prevents the default browser behavior and calls the uploadFiles()
  // function to initiate the file upload and processing on the backend.
  addToDbButton.addEventListener("click", (e) => {
    e.preventDefault();
    uploadFiles();
  });

  alertOkButton.addEventListener("click", hideAlert);

  // Function to handle files from a file browser or drag and drop
  function handleFiles(files) {
    // Convert the FileList to an array
    const newFiles = Array.from(files);

    // Filter out duplicates. A simple check of file name is sufficient for now.
    const uniqueNewFiles = newFiles.filter(
      (newFile) =>
        !droppedFiles.some((existingFile) => existingFile.name === newFile.name)
    );

    // Append unique new files to the existing list and sort the filenames
    droppedFiles = droppedFiles.concat(uniqueNewFiles);
    droppedFiles.sort((a, b) => a.name.localeCompare(b.name));

    // Update the UI
    displayFiles();

    // Enable the button if there are any files
    addToDbButton.disabled = droppedFiles.length === 0;

    // Solution using Event Delegation (most robust)
    // We'll place the listener on a static parent, like the 'detailContainer'
    const detailContainer = document.getElementById(
      "transaction-detail-container"
    );
  }

  /**
   * @function displayFiles
   * @description Renders the list of files stored in the global 'droppedFiles' array
   * into the file list container within the statement modal. It also
   * manages the visibility of the "Please select..." message and the
   * disabled state of the "Add to Database" button.
   * @returns {void}
   */
  function displayFiles() {
    fileList.innerHTML = "";
    if (droppedFiles.length > 0) {
      addToDbButton.disabled = false;
      // const list = document.createElement("ul");
      droppedFiles.forEach((file, index) => {
        const listItem = document.createElement("li");
        const removeButton = document.createElement("span");
        removeButton.textContent = " × ";
        removeButton.classList.add("remove-file-button");
        removeButton.addEventListener("click", () => {
          removeFile(index);
        });
        listItem.textContent = file.name;
        listItem.appendChild(removeButton);
        fileList.appendChild(listItem);
      });
    } else {
      addToDbButton.disabled = true;
    }
  }

  function uploadFiles() {
    if (droppedFiles.length === 0) {
      showAlert("Please select files to upload.");
      return;
    }

    const formData = new FormData();
    for (const file of droppedFiles) {
      formData.append("statements", file);
    }
    droppedFiles = [];

    fetch("/upload_statements", {
      method: "POST",
      body: formData,
    })
      .then((response) => response.json())
      .then((data) => {
        let message = "";
        data.status.forEach((fileStatus) => {
          if (!fileStatus.new_filename) {
            message += `${fileStatus.old_filename}\n`;
          } else if (fileStatus.old_filename === fileStatus.new_filename) {
            message += `${fileStatus.old_filename}\n`;
          } else {
            message += `${fileStatus.old_filename}\nnew filename: ${fileStatus.new_filename}\n`;
          }
          message += `${fileStatus.message}\n\n`;
        });
        showAlert(message);
      })
      .catch((error) => {
        // This catch block will display a generic message, but it should be a rare occurrence
        // for network errors.
        console.error("Upload error:", error);
      });
  }

  function showAlert(message) {
    const alertModal = document.getElementById("alert-modal");
    const alertMessage = document.getElementById("alert-message");
    alertMessage.innerText = message;
    alertModal.style.display = "block";
  }

  function hideAlert() {
    const alertModal = document.getElementById("alert-modal");
    alertModal.style.display = "none";
    closeModal();
    window.location.reload();
  }

  function removeFile(index) {
    droppedFiles.splice(index, 1);
    displayFiles();
    addToDbButton.disabled = droppedFiles.length === 0;
  }

  // Function to close the modal
  function closeModal() {
    const modal = document.getElementById("add-statements-modal");
    modal.style.display = "none";
    resetModalState();
  }

  function resetModalState() {
    droppedFiles = [];
    const fileList = document.getElementById("file-list");
    fileList.innerHTML = "";
    const addToDbButton = document.getElementById("add-to-db-button");
    addToDbButton.disabled = true;

    // Re-show the "Please select..." message
    const dropAreaText = document.querySelector("#drop-area p");
    if (dropAreaText) {
      dropAreaText.style.display = "block";
    }
  }

  const summaryTable = document.querySelector(
    ".category-month-table.tablesort"
  );
  if (summaryTable) {
    new Tablesort(summaryTable);
  }

  function openInputModal(row) {
    console.log("Row clicked:", row);
    // Your modal logic here
  }
});

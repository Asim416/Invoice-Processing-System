# Setting up Google Sheets (about 15 minutes, done once by whoever installs the tool)

Why: your purchase orders and your history live in a spreadsheet you already know how to edit.

Google changes its screens from time to time, so button names may differ slightly. The ideas stay the same. I could not
test these steps against a real Google account, so if a step does not match what you see, trust the screen over this text.

## 1. Create a service account (a robot login)

1. Go to https://console.cloud.google.com and create a project (any name).
2. In **APIs & Services**, enable the **Google Sheets API**. (If you later see an error mentioning the Drive API, enable that too.)
3. In **APIs & Services > Credentials**, choose **Create credentials > Service account**. Give it a name and finish.
4. Open the service account, go to **Keys > Add key > Create new key > JSON**. A file downloads.
5. Move that file into the `secrets` folder of this project and rename it `google-service-account.json`.
   **Treat it like a password. Never email it or commit it.** (The `secrets` folder is already excluded from git.)

## 2. Create the spreadsheet and share it

1. Create a new, empty Google Sheet.
2. Click **Share** and add the service account's email address (it looks like `name@project.iam.gserviceaccount.com`, and is inside the JSON file as `client_email`) with **Editor** access. Do not share it with anyone who should not see invoices.
3. Copy the Sheet ID from its address: `https://docs.google.com/spreadsheets/d/` **THIS_PART** `/edit`.

## 3. Tell the tool

Copy `.env.example` to `.env` (the first run of the tool already did this) and set:

```
STORAGE_BACKEND=sheets
GOOGLE_SHEET_ID=THIS_PART
GOOGLE_CREDENTIALS_FILE=secrets/google-service-account.json
```

## 4. Create the tabs and load sample data

```
python scripts/setup_sheet.py
python -m ap.doctor --online
```

The first command creates five tabs (`POs`, `PO_Lines`, `Processed`, `Runs`, `Events`) and fills the first three with the
**synthetic sample data**, but only if they are empty. Use `--no-seed` to create the tabs without sample data and type in
your own purchase orders. The second command should show `Google Sheets: connected; 12 purchase orders found`.

## What lives where

| Tab | Who writes it | Notes |
|---|---|---|
| POs, PO_Lines | You (finance) | One row per PO, and one row per item on that PO. Status must be `open` or `closed` |
| Processed | The tool, when you press *Record my decision* | Used to spot duplicate invoices. Do not delete rows |
| Runs | The tool, after every check | Includes the full result so a decision can be recorded from any computer |
| Events | The tool | For example "escalated to manager" |

The tool only reads the PO tabs and only appends to the other three. It never edits or deletes existing rows.

## If it does not work

| Message | Fix |
|---|---|
| "Google denied access ... Share it with ..." | Share the sheet with the service account email as Editor |
| "The spreadsheet was not found" | Check `GOOGLE_SHEET_ID` |
| "A required tab is missing" | Run `python scripts/setup_sheet.py` |
| "Google Sheets is rate limiting requests" | Wait a minute and try again |

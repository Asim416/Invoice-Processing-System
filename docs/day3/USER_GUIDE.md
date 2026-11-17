# Invoice Checker: User Guide (for finance staff)

You do not need any technical knowledge. Nothing in this tool pays an invoice or sends an email: **you make every decision.**

## What it does

You give it a supplier invoice (a PDF). It reads the invoice, compares it with the purchase order (PO) and your list of
already-processed invoices, then tells you whether it looks safe to pay, needs your review, or should be held. It also
writes a draft email to the vendor when something is wrong.

## Starting it

| Your computer | What to do |
|---|---|
| Windows | Open the `ap-invoice-system` folder and double-click **run.bat** |
| Mac / Linux | Open a terminal in the folder and type: `bash run.sh` |

The first start takes about a minute (it sets itself up). A browser tab opens. If it does not, type
**http://localhost:8501** into your browser. To stop the tool, close the black window.

The first time, the tool is in **demo mode**: it can only read the built-in sample invoices (more on that below).

## Checking an invoice (three steps)

1. **Add an invoice.** Choose "Upload a PDF" and drag your file in, or choose "Use a sample invoice" and pick one from the list.
2. **Check it.** Press **Check this invoice**.
3. **Decide.** Read the result, then choose *Approve for payment*, *Put on hold* or *Reject*, and press **Record my decision**.

## What the colours mean

| Colour | Message | What you should do |
|---|---|---|
| Green | Looks safe to pay | Glance at the details, then record your decision |
| Amber | Needs your review before paying | Open the reasons, follow the "What to do" line, then decide |
| Red | Do not pay yet | Put it on hold and contact the vendor |

Under **Why** you will see each reason in plain language with a suggested next step. **Draft email to the vendor** can be
copied into your email program (the tool never sends it).

## Other buttons

- **Record my decision** saves what you decided. It does not pay anything. It is also what makes the same invoice show up as a duplicate if it arrives again.
- **Send to manager** sends a short alert (vendor, invoice number, total, reasons) to your manager's Slack channel, if it has been set up. It is shown when the result is not green.
- **Check my setup** (left side) tells you in plain words if something is missing.

## Reading your own invoices

Demo mode can only read the sample invoices. To read your own PDFs, the person who set this up must switch on the "AI reader"
(an API key in the settings file). Until then you will see: *"Demo mode can only read the built-in sample invoices."*

## Things the tool cannot do (yet)

- Read scanned pictures of invoices (it needs PDFs where the text can be selected).
- Handle invoices with tax lines or in a different currency from the PO (it will ask you to review them).
- Replace your judgement: always check amber and red results yourself.

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| "Python was not found" (Windows) | Python is not installed | Install Python 3.10 or newer from python.org and tick **Add to PATH**, then run again |
| Browser page will not open | The tool is still starting, or was closed | Wait a minute, then open http://localhost:8501. If the black window is closed, run it again |
| "Only PDF invoices are supported" | You uploaded another file type | Save or export the invoice as a PDF |
| "This PDF is a picture of a page" | A scanned invoice | Read it manually; scanned invoices are not supported yet |
| "The invoice reader is busy" | Too many requests in a short time | Wait a minute and try again |
| "The app could not start because its data source is not available" | The Google Sheet cannot be reached | Ask whoever set it up to run `python -m ap.doctor --online` |
| Anything else | | Press **Check my setup** and send a screenshot, plus the "Technical details" box, to the person who set this up |

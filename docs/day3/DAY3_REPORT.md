# Day 3 Report: The Working Core

Data origin everywhere below: **synthetic**. No real user has run this. No real Google, Slack or Groq account has been used by me: my sandbox cannot reach them, so those integrations are tested against fakes and local stand-ins and are **unverified against the real services**.

## 1. The requirements, interpreted for this project

| Day 3 requirement | What it means here | Status |
|---|---|---|
| Working core flow, trigger to final output, for a non-developer | Priya uploads an invoice, gets a plain-language recommendation, records her decision | Built and tested headlessly. Not yet seen by a human |
| At least two real data-source or tool integrations | Google Sheets (POs, duplicate log, run history) and a Slack manager alert, alongside the Groq LLM | Built and tested against fakes. **Not yet tested against real accounts** |
| Validation, structured outputs, logs, useful error messages | Existing validation and JSON results, plus plain-language errors, structured logs, and friendly handling of Sheets and Slack failures | Built and tested |
| Configuration and secrets separate from code | Everything environment-specific is in `.env` or `secrets/` (git-ignored); `ap.doctor` explains missing pieces | Built and tested |
| One interface | Streamlit web app (`app.py`) with one-command launchers | Built; driven headlessly; real server health-checked |
| First execution by the target or a proxy user | A test protocol and observation form are ready | **Not run.** Needs a real person |

## 2. What was built

- **Web app** (`app.py`, `ap/ui_logic.py`, `ap/friendly.py`): upload or sample selection, colour-coded result, reasons with "what to do" in plain language, draft vendor email, an explicit decision step with no pre-selected option, escalation button, history, setup check. Demo mode is always labelled as such.
- **Google Sheets adapter** (`ap/storage_sheets.py`, `scripts/setup_sheet.py`): five tabs; PO data cached 60 s; duplicate log never cached; retries with backoff on 429 and 5xx; friendly messages for denied access, missing sheet or tab; all writes in RAW mode so vendor text can never run as a formula; a local copy of every run is kept as an audit trail.
- **Slack alerts** (`ap/notify.py`): sent only when a human presses the button; minimal message (no invoice text, no email draft); retries on 429 and 5xx honouring `Retry-After`; the webhook URL is never logged or shown; a failed alert never changes or hides the invoice result.
- **Setup and operation**: `ap/doctor.py` (plain-language checks, `--online`, `--send-test`), `run.sh` and `run.bat`, `.env.example`, `.streamlit/config.toml`.
- **Docs**: user guide, Google Sheets and Slack setup guides, proxy-user test protocol.
- **Tests**: 181 (59 new), all passing, plus mutation checks.

## 3. Evidence

| Evidence | What it shows | What it does not show |
|---|---|---|
| `evidence/pytest_full_output.txt` | 181 passed | Anything about real services or real users |
| `evidence/automated_walkthrough.txt` | A script clicks through the real app: amber result with reasons and draft email, manager alert (console), approve, then the same invoice held as a duplicate. 0 exceptions | A human using it. Labelled automated in the file itself |
| Clean-copy run of `bash run.sh` (shown in chat) | From a folder with no environment, it created a virtual environment, installed requirements, generated data, passed the setup check and had the web server healthy in 49 s; 181 tests then passed inside that fresh environment | Windows (`run.bat` is written but untested), a real browser rendering the page |
| Local fake Slack server tests | Real HTTP requests, retries, 404 handling, secret not leaked | Real Slack |
| Fake spreadsheet tests | Reads, writes, caching, retries, outage handling, RAW mode | Real Google Sheets, real permissions, real quotas |
| Mutation checks | 7 deliberate breaks of the new code, all caught | |

## 4. Defects found and fixed during Day 3

1. **Crash during a Sheets outage.** The last step (saving the run record) raised an uncaught error, so the "fail safe" path crashed. Now the local copy is kept, the reviewer still gets the result, and the CLI prints a friendly message.
2. **Stale "Recent checks" list.** It was drawn before the check ran, so a new invoice only appeared after the next click. Now drawn last.
3. **Windows-style path in an upload name** was not reduced to a plain file name on this platform. Fixed.
4. **Deprecated Streamlit parameter** removed so the app works across versions.
5. **`./run.sh` fails with "Permission denied"** after zipping or copying, because the executable bit is lost. Documentation now says `bash run.sh`.
6. **Browser did not open automatically** because my config forced headless mode. Removed.
7. **Test flaws:** one doctor test asserted almost nothing and now asserts that no test message is ever sent to a non-Slack address.

## 5. What is unverified and what it will take

| Unverified | How to verify |
|---|---|
| Real Google Sheets connection and permissions | Follow `SETUP_GOOGLE_SHEETS.md`, run `python scripts/setup_sheet.py` then `python -m ap.doctor --online`, paste the output back |
| Real Slack message | Follow `SETUP_SLACK.md`, run `python -m ap.doctor --send-test` |
| Live Groq extraction (still the biggest open item from Day 2) | `python scripts/check_llm.py` |
| `run.bat` on Windows | Double-click it on a Windows machine and report what you see |
| A real person can use it | `PROXY_USER_TEST.md` |
| How it looks and feels in a browser | Open it yourself |

My setup instructions for Google and Slack are written from general knowledge of those products and may not match their current screens.

## 6. Known limitations

- Demo mode reads only the built-in sample invoices; real PDFs need live mode and a key.
- The Sheets backend keeps one local audit copy of runs; if the app is moved to a different machine, history lives in the Sheet.
- Two people recording decisions at the same moment could, in theory, both pass the duplicate check; v1 assumes one reviewer at a time.
- Still no OCR, tax lines or currency conversion.
- Public invoice datasets such as the Northwind one contain no purchase orders, so matching needs POs you add yourself.

## 7. Can someone else run the core workflow when I am not beside them?

**Not proven yet. Here is exactly how far the evidence goes.**

What supports "yes":
- From a clean copy, one command built the environment, installed everything, created sample data, checked itself and served the app, with no manual steps and in under a minute on this machine.
- If something is missing, the tool says what and how to fix it in plain language (setup check, error banners with a "what to do" line), instead of showing a stack trace.
- Failures of the data source, alert channel or AI reader were each exercised and end in a clear message and a safe result.
- The user guide is written for non-developers and the interface never pays or sends anything by itself.

What is missing for a real "yes":
- No person other than me and a script has run it. Whether the wording is clear, whether the colours are understood and whether the setup survives a real Windows machine are exactly what the proxy-user test is for.
- The two integrations have never touched a real account.

So the honest answer today is: the design and tooling are ready for someone else to run it, and I have strong automated evidence that it behaves, but the claim "someone else can run it unaided" stays unproven until the proxy-user test is done. Day 4 should not start from "it works"; it should start from that test's findings.

## 8. AI collaboration log entries for Day 3

| Task delegated | How verified | Accepted, changed or rejected | Decision you own |
|---|---|---|---|
| Interpreted Day 3 requirements for this project | Compared against the brief | Accepted: Sheets, Slack and Streamlit | The choice of integrations and the human-triggered alert |
| Wrote the web app, adapters, setup tooling and 59 tests | Ran everything; mutation-tested; clean-copy install | Seven defects found by testing and fixed | Whether to trust results before real accounts are tested |
| Wrote user and setup guides | Not verifiable against real Google or Slack screens | Flagged as unverified in the guides | Running the setup yourself and correcting them |
| Wrote the proxy-user protocol | n/a | Results left blank on purpose | Recruiting the person and recording what you observe |

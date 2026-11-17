"""Invoice Checker: live AI invoice processing with batch upload support.

Run: streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from ap.doctor import run_checks
from ap.schemas import ErrorResponse
from ap.storage import StorageError
from ap.ui_logic import AppService, build_error_view, build_view

st.set_page_config(page_title="Invoice Checker", page_icon="🧾", layout="wide")


@st.cache_resource(show_spinner=False)
def get_service() -> AppService:
    return AppService.from_env()


try:
    service = get_service()
except StorageError as exc:
    st.title("🧾 Invoice Checker")
    st.error("The app could not start because its purchase-order data source is unavailable.")
    st.write(str(exc))
    st.caption("Check your storage configuration and run: python -m ap.doctor --online")
    st.stop()

ss = st.session_state
ss.setdefault("batch_results", [])
ss.setdefault("batch_errors", [])
ss.setdefault("batch_nonce", 0)

status = service.status()
ai_ready = status["mode"] == "live" and bool(service.settings.api_key)

with st.sidebar:
    st.header("System status")
    if ai_ready:
        st.success(f"Live AI reader: {status['model']}")
    elif status["mode"] == "live":
        st.error("AI reader is not configured")
        st.caption("Add LLM_API_KEY to your .env file, then restart the app.")
    else:
        st.warning("Sample-fixture mode is active")
        st.caption("Set EXTRACTION_MODE=live in .env to process arbitrary invoices.")
    st.write("Purchase-order data: " + ("Google Sheets" if status["storage"] == "sheets" else "Local CSV"))
    st.write("Manager alerts: " + {"slack": "Slack", "console": "Console", "none": "Off"}.get(status["notify"], status["notify"]))
    with st.expander("Check system setup"):
        if st.button("Run setup check", key="doctor"):
            for check in run_checks(service.settings, online=True):
                icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}[check.status]
                st.write(f"{icon} **{check.name}:** {check.message}")
                if check.fix and check.status != "ok":
                    st.caption("Fix: " + check.fix)
    st.subheader("Recent checks")
    history_box = st.container()

st.title("🧾 Invoice Checker")
st.caption(
    "Checks supplier invoices against purchase orders and recommends what to do. "
    "It never pays invoices or sends vendor emails automatically; a person makes every decision."
)

if not ai_ready:
    st.warning(
        "Live invoice reading is not ready. Configure a compatible LLM endpoint and API key in "
        "the project's .env file, set EXTRACTION_MODE=live, and restart the app. "
        "Do not use sample-fixture mode for your own invoices."
    )

st.subheader("1. Add invoices")
upload_mode = st.radio(
    "Input source",
    ["Upload PDF invoices", "Choose a built-in sample"],
    horizontal=True,
    key=f"source_{ss.batch_nonce}",
)

uploads = []
sample_path = None
if upload_mode == "Upload PDF invoices":
    uploads = st.file_uploader(
        "Select one or more supplier invoice PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        help="You can select multiple PDFs at once. Each invoice is processed and reported separately.",
        key=f"uploads_{ss.batch_nonce}",
    ) or []
    if uploads:
        st.caption(f"{len(uploads)} invoice(s) selected.")
        st.dataframe(
            [{"File": f.name, "Size": f"{f.size / 1024:.1f} KB"} for f in uploads],
            hide_index=True,
            use_container_width=True,
        )
else:
    samples = service.sample_invoices()
    labels = service.sample_labels()
    if not samples:
        st.info("No built-in samples are available.")
    else:
        names = [f"{name}: {labels.get(name, '')}" if labels.get(name) else name for name, _ in samples]
        selected = st.selectbox("Sample invoice", names, index=None, placeholder="Choose a sample invoice")
        if selected:
            sample_path = samples[names.index(selected)][1]

st.subheader("2. Check invoices")
has_input = bool(uploads) if upload_mode == "Upload PDF invoices" else sample_path is not None
# Keep the action visible whenever an input is selected. Previously the button was
# disabled when live AI configuration was missing, which made it appear to vanish
# or become unavailable immediately after uploading a PDF.
button_label = (
    f"Process {len(uploads)} invoice(s)"
    if upload_mode == "Upload PDF invoices" and uploads
    else "Check invoice(s)"
)
if st.button(button_label, type="primary", disabled=not has_input, key="process_invoices"):
    if not ai_ready:
        st.error(
            "Invoice processing cannot start because live AI extraction is not configured. "
            "Set EXTRACTION_MODE=live and a valid LLM_API_KEY in your .env file, "
            "then restart the app. Your uploaded files are still selected; no data was processed."
        )
    else:
        ss.batch_results = []
        ss.batch_errors = []
        items = (
            [(f.name, f.getvalue()) for f in uploads]
            if upload_mode == "Upload PDF invoices"
            else [(sample_path.name, sample_path)]
        )
        progress = st.progress(0, text="Starting invoice processing...")
        for index, (filename, payload) in enumerate(items, start=1):
            progress.progress((index - 1) / len(items), text=f"Processing {index} of {len(items)}: {filename}")
            try:
                with st.spinner(f"Reading and checking {filename}..."):
                    result = (
                        service.analyze_bytes(filename, payload)
                        if isinstance(payload, bytes)
                        else service.analyze_path(payload)
                    )
                if isinstance(result, ErrorResponse):
                    ss.batch_errors.append({"file": filename, "view": build_error_view(result)})
                else:
                    ss.batch_results.append({"file": filename, "view": build_view(result, service.policy)})
            except Exception as exc:
                # Isolate unexpected failures so one bad PDF does not stop the batch.
                from ap.friendly import friendly_error
                error = friendly_error(exc)
                ss.batch_errors.append({"file": filename, "view": build_error_view(error)})
            progress.progress(index / len(items), text=f"Processed {index} of {len(items)}")
        st.success(f"Finished processing {len(items)} invoice(s). Review each result below.")

if ss.batch_results or ss.batch_errors:
    st.divider()
    st.header("Processing results")
    total = len(ss.batch_results) + len(ss.batch_errors)
    st.caption(f"{total} file(s) processed · {len(ss.batch_results)} completed · {len(ss.batch_errors)} failed")
    for error_item in ss.batch_errors:
        with st.expander(f"❌ {error_item['file']} — Could not process", expanded=True):
            err = error_item["view"]
            st.error(err.title)
            st.write(err.what_to_do)
            with st.expander("Technical details"):
                st.json(err.technical)

    for item in ss.batch_results:
        v = item["view"]
        with st.container(border=True):
            st.subheader(item["file"])
            banner = {"green": st.success, "amber": st.warning, "red": st.error}[v.tone]
            banner(f"**{v.headline}**\n\n{v.action}")
            st.caption(v.mode_note)
            if v.reader_problem:
                st.info(v.reader_problem)

            with st.expander("Why this result?", expanded=True):
                important = [r for r in v.reasons if r.severity != "info"]
                informational = [r for r in v.reasons if r.severity == "info"]
                if not v.reasons:
                    st.write("Every check passed: the invoice matches its purchase order.")
                for reason in important:
                    st.markdown(f"**{reason.title}**")
                    st.write(reason.meaning)
                    st.write(f"**Details:** {reason.detail}")
                    st.write(f"**What to do:** {reason.next_step}")
                for reason in informational:
                    st.caption(f"{reason.title}: {reason.detail}")

            st.markdown("**Extracted invoice information**")
            if v.fields:
                st.table([{"Field": key, "Value": value} for key, value in v.fields])
                if v.lines:
                    st.dataframe(v.lines, hide_index=True, use_container_width=True)
                st.caption(v.confidence_text)
            else:
                st.write("No validated invoice fields were extracted.")

            if v.vendor_email:
                with st.expander("Draft vendor email (not sent)"):
                    st.code(v.vendor_email, language=None)
            with st.expander("Internal note"):
                st.text(v.internal_note)

            st.markdown("**Human decision**")
            if not v.can_record:
                st.info(v.cannot_record_reason)
            else:
                decision = st.radio(
                    "Choose an action",
                    ["Approve for payment", "Put on hold", "Reject"],
                    index=None,
                    horizontal=True,
                    key=f"decision_{v.run_id}",
                )
                note = st.text_input("Decision note (optional)", key=f"note_{v.run_id}", max_chars=200)
                if st.button("Record decision", key=f"record_{v.run_id}", disabled=decision is None):
                    selected_decision = {
                        "Approve for payment": "approve",
                        "Put on hold": "hold",
                        "Reject": "reject",
                    }[decision]
                    ok, message = service.record_decision(v.run_id, selected_decision, note)
                    (st.success if ok else st.error)(message)

            if v.tone != "green":
                if st.button("Send to manager", key=f"escalate_{v.run_id}"):
                    outcome = service.escalate(v.run_id, note="")
                    (st.success if outcome.sent else st.warning)(outcome.detail)

            with st.expander("Technical details"):
                st.json(v.technical)

    if st.button("Start a new batch"):
        ss.batch_nonce += 1
        ss.batch_results = []
        ss.batch_errors = []
        st.rerun()

with history_box:
    history = service.history()
    if history:
        st.dataframe(
            [{"Date": h["started_at"], "File": h["file"], "Recommendation": h["label"]} for h in history],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No invoices processed yet.")

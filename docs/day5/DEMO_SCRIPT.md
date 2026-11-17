# Five-Minute Demo: script, steps and checklist

**I cannot record a video.** This is a ready script for you to record (Loom, OBS or similar). The brief asks the demo to show:
the problem and baseline; a live flow from real input to output; the non-developer experience; evaluation and failure handling;
measured results and the most important limitation. Each part below maps to one of those, with a time budget that sums to 5:00.

**The one rule:** say only what you measured. Parts in `[SQUARE BRACKETS]` are things you must replace with your own number
or delete. If you have not run the live evaluation by the time you record, say so on camera; it is honest and it is also in the plan.

## 0. Before you hit record (15 minutes)

- [ ] `python scripts/reset_demo.py` so the history is clean and the duplicate demo behaves (local data only; it never touches Google Sheets, `.env` or `secrets/`).
- [ ] `python -m ap.doctor` shows no FAIL. For the live mode: `python scripts/check_llm.py` prints PASS.
- [ ] Decide the mode: **live** (set `EXTRACTION_MODE=live`) is far more convincing; **demo mode** works with the sample invoices but you must say "this is demo mode, a stored answer, not the AI".
- [ ] Have these open: the app (`run.bat` or `bash run.sh`), a terminal in the project folder, `docs/day5/EVALUATION_PACKAGE.md` (or the regression table), and `results/comparison.md`.
- [ ] Close anything showing secrets: `.env`, the secrets folder, your key in a terminal history, other tabs.
- [ ] Browser zoom at 125% so text is readable; do a silent 1-minute rehearsal.
- [ ] Decide your fallback: if live mode fails on camera, say so and continue in demo mode. Do not hide a failure; the failure handling is part of the story.

## 1. Script (target 5:00, about 620 spoken words)

| Time | Screen | What to do | What to say (edit into your own words) |
|---|---|---|---|
| **0:00 to 0:35** The problem and baseline | Title slide or the README | Show the manual process in one sentence. Show your Baseline A result | "Meet Priya, a fictional finance person at a 30-person company. Before paying a supplier invoice she checks it against the purchase order, looks for duplicates, and writes to the vendor if something is wrong. By hand, with a spreadsheet, I measured **[X] minutes per invoice** over 12 test invoices [say: and I knew where the planted errors were, so that is optimistic]. The risk is paying a duplicate or an overcharge." |
| **0:35 to 1:45** Live flow, real input to output | App, **Upload a PDF** or a sample | Check a PDF with an overcharge (sample `TC03`, total over the PO). Point to: the amber banner, "Why" reasons, "What to do", the read values, the draft email | "I upload an invoice. **[Live mode: the AI reads it.]** / **[Demo mode: this uses a stored answer for the built-in samples, not the AI.]** The result is amber: needs review. It says in plain language the total is higher than the purchase order and a unit price differs, and what to do next. It has drafted an email to the vendor, but it has not sent anything, and it never will. The AI's only job is reading the invoice. Fixed rules decide the label, so a model mistake cannot approve something by itself." |
| **1:45 to 2:35** The non-developer experience | App | Choose a decision (note: nothing is pre-selected), press **Record my decision**. Press **Send to manager** (Slack or the demo printout). Open **Check another invoice**. Check the clean sample `TC01`, record approve, then check it again | "Priya makes the decision: the choice is empty by default so she has to think. Recording it saves it, but pays nothing. This one is above her manager's limit, so she can send a short alert. Now a clean invoice: green. I approve it. If the same invoice arrives again, it is a duplicate and the tool says do not pay, and explains why." |
| **2:35 to 3:50** Evaluation and failure handling | Terminal, then the regression table | (a) In the app, upload a `.docx`: show the friendly error. (b) Break the reader: change the key to a wrong value in `.env`, restart, check an invoice (or just describe it if time is short): show "reader not available, needs review". (c) Show the regression table | "Things go wrong, so I tested them on purpose. A wrong file type gets a plain message. If the AI service is down, the result is Needs review, never Approve. I injected 25 kinds of simulated AI mistakes into 60 documents, 800 runs. On my first version **34 runs approved something wrongly, every one reported as high confidence**, so the confidence score was no warning. After a first fix, a held-out test showed **11 were still wrong**: my fix was too narrow. The root cause was checking that a value exists in the document but not that it sits next to the right label. After fixing that, **zero**. And I can show which safeguard stops which mistake by switching each off in turn." |
| **3:50 to 4:30** Measured results | `EVALUATION_PACKAGE.md` and `results/comparison.md` | Show what is measured and what is not | "Here is what I measured. **[If live evaluation done: decision accuracy X of 12 across three runs, extraction accuracy Y%, notional cost Z per invoice, and the review time dropped from A to B minutes.]** **[If not: I have not yet run the live evaluation or the baselines, so I make no claim about the AI's accuracy, speed or cost. The tools to measure them are built and tested.]** The 244 automated tests and the fault experiments cover the code around the model." |
| **4:30 to 5:00** The most important limitation | Limitations doc or the plan | Say the limitation plainly | "The most important limitation: all my invoices are synthetic and written by me, and simulated mistakes are not real AI mistakes. Real invoices will surprise it. So the next step is a two-week shadow rollout with a second-person audit and a small set of real, redacted invoices, and the plan and the metrics are written down." |

Word count of the quoted speech is about 620 at a relaxed 130 words a minute: it fits, with a little air. Trim before adding.

## 2. Safe demonstration of failure (nothing risky)

- **Wrong file type:** upload any `.docx`. Expected: "Only PDF invoices are supported."
- **Reader unavailable:** with live mode on, change `LLM_API_KEY` in `.env` to anything wrong, restart the app, check an invoice. Expected: Needs review with "The invoice reader is not available" and no email draft. Put the right key back afterwards.
- **Duplicate:** record a decision for `TC01`, check `TC01` again. Expected: red, "This invoice was already processed".
- **Hidden instruction:** check sample `TC12`. Expected: amber, includes "The invoice contains instruction-like text", still not approved.

## 3. Do not say

- "The AI is 9x% accurate": unless you measured it and can show the file.
- "Tested with real users" or "saves X hours": unless you ran the proxy test and the timings.
- "Production-ready" or "secure": say "built so that it fails safe" and show why.
- That demo-mode output is AI output.
- Any number you cannot point to in `docs/day5/EVALUATION_PACKAGE.md` or `results/`.

## 4. After recording

- [ ] Watch it once at normal speed: no key, no private data, no unexplained error on screen.
- [ ] Trim the dead time; keep it under 5:00.
- [ ] Put the link in the submission form's Demo Video field (it expects a Loom-style share link).
- [ ] If any number in the video later changes, re-record or add a caption.

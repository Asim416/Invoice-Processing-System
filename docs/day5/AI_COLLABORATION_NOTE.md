# AI Collaboration Note

> **Draft written by the AI assistant from the record of the work. Items marked `[YOU: ...]` are things only you can truthfully
> say. Edit or delete anything that is not true of what you did. An accurate note that credits the AI heavily is better than a
> flattering one that does not survive a question.** Remove this box before submitting.

## 1. AI tools used and the role of each

| Tool | Role | Used for |
|---|---|---|
| Claude (Anthropic), in the claude.ai chat interface; the model was Claude Sonnet 5.5 at the end of the work `[YOU: confirm the model name shown in your app; it can change mid-conversation]` | Design partner and implementer, with a sandbox to run code | Choosing and scoping the workflow; architecture and data contracts; writing nearly all code, tests, evaluation tooling and documentation; running experiments; drafting the case study and this note |
| Groq-hosted `openai/gpt-oss-120b` (a language model inside the product) | The product's reader: extracts fields from invoice text. The only AI step at run time | **Configured and tested against local stand-ins only. Not yet called for real.** `[YOU: update after you run scripts/check_llm.py and the live evaluation]` |

No other AI tools were used `[YOU: confirm, or list any others such as code assistants in your editor]`.

## 2. Work delegated to AI

Almost all of the typing was delegated:

- Option generation for the workflow, the Day 1 package (persona, workflow map, test cases, metrics), and later the design documents
- The Python package, the web app, the Google Sheets and Slack adapters, the setup checker, the adoption report
- About 244 automated tests, the fault-injection toolkit, the evaluation scripts and the documentation
- Analysis of failures, the hardening, and the drafting of the reports

What was **not** delegated, because it could not be: running the live model, timing a person, observing a user, recording the
demo, and opening the web app in a real browser. Those are marked as unverified throughout the documents.

## 3. How AI-generated results were verified

| Method | What it covered |
|---|---|
| Running everything in the sandbox | Every claim of "works" was backed by executing the code; outputs are saved in `docs/*/evidence/` |
| Automated tests (see the count in the Evaluation Package) | Rules, validation, adapters, the interface (driven headlessly), and whole-matrix regression gates |
| **Mutation checks** | Deliberately breaking each safeguard to confirm a test fails. This found tests that passed even with the safeguard deleted |
| Fault injection and a **held-out** set | Breaking the system with simulated mistakes; a second round of faults and documents never used to design the fixes |
| Clean-copy installs | Creating a fresh environment from the packaged files and running the app and tests |
| Auditing the reports against saved files | Every number in the Day 4 report was traced to a result file; one sentence was found ambiguous and corrected |
| Flagging what could not be verified | `docs/LIMITATIONS.md` lists each unverified item and how to verify it |

`[YOU: add what you personally verified. For example: which files you read line by line, which commands you ran, what you
changed. If the answer is "I ran the tests and read X", say exactly that.]`

## 4. Important results rejected or corrected

These are real events in the work, not examples:

1. **Unsourced figures.** The first explanation of the manual process used invented numbers (about 40 invoices a week, 5 to 8 minutes each). You asked whether they were real; they were illustrative. They were replaced by cited benchmark ranges (marked as vendor-published) and a plan to measure the baseline yourself.
2. **Too much AI.** The first design let the model write reasons and vendor emails. You asked me to reconsider where AI was overused; the revised design uses AI only to read the invoice, with templates and rules for everything else.
3. **Bugs in AI-written code, found by testing:** date checking so loose that an invented date passed; a fail-safe path that crashed when Google Sheets was down; a check that blocked safe results when an error message contained a digit; a retry delay of 0 treated as missing; a log handler holding a stale stream; syntax that only works on Python 3.12.
4. **Over-claiming, caught before it reached you:** the evaluation harness said "real model" when pointed at a local stand-in; stand-in results sat where they could be mistaken for live ones; a test I wrote proved almost nothing; a hand-computed expected value in a test was wrong (the code was right).
5. **The round-1 hardening did not generalize.** It was perfect on the faults it was designed against and still approved 11 held-out cases wrongly. The held-out round exposed it and led to a root-cause fix.
6. **Confidence was no warning.** All 34 wrongly approved cases on the first version carried high confidence, which led to new checks instead of a better label.

## 5. Core decisions you personally owned

`[YOU: confirm each, and add your own. A decision is yours if you could explain and defend it.]`

- Choosing the **accounts-payable invoice exception** workflow over the other options, and using **synthetic/public data** because you had no real data
- Asking for evidence of the manual process and not accepting invented numbers
- Pushing to **minimise AI** and keep a human in charge of every decision
- Choosing **Groq** as the provider and accepting the stage plan (design, build, verify) with a go-ahead at each stage
- The Day 3 choice of **Google Sheets, Slack and a web interface for a non-developer**
- Deciding how to treat unverified items: stating them rather than hiding them
- `[YOU: the choices you made in the remaining places: the thresholds, which rules to keep, what to cut]`

## 6. Be ready to explain and modify

Evaluators ask whether you can explain and change AI-generated code. Practise on these, with the file to open:

| Question | Where to look |
|---|---|
| Why is the AI used in only one place? | `docs/ARCHITECTURE.md` section 1; `ap/pipeline.py` |
| How does a wrong extraction get stopped? | `ap/validation.py`, `ap/anchors.py`, `docs/day4/FAILURE_ANALYSIS.md` |
| Add a rule, for example "flag invoices older than 90 days" | `docs/DEVELOPER_GUIDE.md` section 4 |
| What happens when the model is down? | `ap/extraction/openai_compatible.py`, `tests/test_pipeline.py` |
| Why did the first fixes fail? | `docs/day4/FAILURE_ANALYSIS.md`, A3 |
| What is not proven? | `docs/LIMITATIONS.md` |

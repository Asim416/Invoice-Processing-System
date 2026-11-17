# Proxy-User Test: can someone else run it without me?

**Status: NOT YET RUN.** Everything below the line "Results" is blank on purpose. Fill it in only from what you actually
observe. The brief asks for a first execution by the target user or a proxy user; an automated walkthrough
(`docs/day3/evidence/automated_walkthrough.txt`) is not a substitute and must not be described as one.

## Who

One person who is **not a developer**, ideally someone who uses spreadsheets and email at work (a relative or friend
who handles bills, a former colleague in finance or admin). They stand in for Priya. Do not choose someone who has seen the tool.

## Rules for you, the observer

1. Say only the script below. Do not explain, hint, or point. If they are stuck for 2 minutes, write down where, then give the smallest possible help and note that you did.
2. Write down what they do and say, not what you think they meant.
3. Time each task with a phone stopwatch.
4. Use demo mode and synthetic data. Tell them the invoices are made up.

## What to hand over

The project folder (zipped, as a stranger would receive it) and `docs/day3/USER_GUIDE.md`. Nothing else.

## Tasks (read these out as written)

| # | Say this | What you are testing |
|---|---|---|
| 0 | "Here is a folder and a one-page guide. Please get the tool running on your computer." | Can they start it unaided (setup, first run)? |
| 1 | "Please check the sample invoice called TC03 and tell me, in your own words, what the tool is telling you." | Do they understand an amber result and the reasons? |
| 2 | "What would you do next with this invoice?" | Do they find the next step and the draft email? |
| 3 | "Please check sample TC01. Then record that you approve it." | Do they find and use the decision step? |
| 4 | "Now check TC01 again. What happened and why?" | Do they understand the duplicate result? |
| 5 | "Imagine your manager should know about TC03. Show me how you would tell them." | Do they find Send to manager? |
| 6 | (Choose "Upload a PDF" yourself first, then say) "Try uploading this file." and give them a `.docx` file. | Is the error message understandable? |

## Questions afterwards (ask exactly these)

1. Did the tool pay anything or send anything by itself? (Correct answer: no.)
2. What do the green, amber and red messages mean?
3. What was the most confusing moment?
4. What would you change first?
5. Would you use this for real invoices? Why or why not?

## Hypotheses to test (set before the test; change them only with a note)

- Starts the tool unaided within 10 minutes.
- Completes tasks 1 to 5 without help.
- Correctly explains green, amber and red.
- Correctly says the tool pays and sends nothing.

## Results (fill in after the test)

| Item | Observation |
|---|---|
| Date, observer, participant role (no names needed) | |
| Operating system, Python already installed? | |
| Task 0: time to running tool, help needed | |
| Task 1: time, their explanation in their words | |
| Task 2: time, what they chose | |
| Task 3: time, any hesitation | |
| Task 4: their explanation | |
| Task 5: found Send to manager? time | |
| Task 6: could they act on the error message? | |
| Answers to questions 1 to 5 | |
| Total unaided vs aided steps | |
| Hypotheses met / not met | |

## Changes made because of the test (fill in)

| Problem observed | Change made | Re-tested? |
|---|---|---|
| | | |

# Setting up manager alerts in Slack (about 5 minutes, done once)

The tool sends a short message only when someone presses **Send to manager**. It contains the vendor, invoice number, PO,
total, the recommendation and the reasons. It never contains the invoice text or the draft email.

I could not test these steps against a real Slack workspace. If a screen differs from this text, trust the screen.

1. Go to https://api.slack.com/apps and choose **Create New App > From scratch**; pick your workspace.
2. Open **Incoming Webhooks**, switch it **On**, then **Add New Webhook to Workspace** and choose the channel your manager reads.
3. Copy the webhook address (it starts with `https://hooks.slack.com/services/`). **It is a secret: anyone who has it can post to that channel.**
4. In `.env` set:

```
NOTIFY_BACKEND=slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

5. Send one test message: `python -m ap.doctor --send-test`. A message saying "Test message from Invoice Checker setup" should appear in the channel.

To rehearse without Slack, set `NOTIFY_BACKEND=console`: the alert is printed in the terminal window instead.

Your workspace admin may need to approve the app. If Slack rejects the message, the tool says so, keeps the invoice result,
and suggests contacting the manager another way.

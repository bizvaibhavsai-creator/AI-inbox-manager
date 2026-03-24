# n8n Workflow Setup Guide

## Step 1: Import Workflows
1. Open n8n at `http://localhost:5678`
2. Login with `admin` / `changeme` (change this!)
3. Go to **Workflows** > **Import from File**
4. Import each JSON file in order:
   - `1-slack-notification.json`
   - `2-approval-handler.json`
   - `3-followup-cron.json`

## Step 2: Configure Slack
1. Create a Slack App at https://api.slack.com/apps
2. Enable **Interactivity & Shortcuts**
   - Set Request URL to: `http://YOUR_SERVER:5678/webhook/slack-interaction`
3. Add Bot Token Scopes:
   - `chat:write`
   - `chat:write.public`
4. Install to your workspace
5. In n8n, add Slack credentials using the Bot Token
6. Update all Slack nodes to use your credentials
7. Create a `#inbox-manager` channel in Slack

## Step 3: Configure Google Sheets
1. In n8n, add Google Sheets credentials (OAuth2)
2. Create a Google Sheet with columns:
   - Timestamp, Lead Email, Campaign, Category, Response, Status, Approved By
3. Update the `Log to Google Sheets` node with your Sheet ID
4. Copy the Sheet ID to your `.env` file

## Step 4: Configure Instantly.ai Webhook
1. Go to Instantly.ai > Settings > Webhooks
2. Add a webhook:
   - Event: `reply_received`
   - URL: `http://YOUR_SERVER:8000/webhook/instantly`
3. Save and test

## Step 5: Activate Workflows
1. Toggle each workflow to **Active**
2. Test by sending yourself a test email through a campaign

The server_queue module introduces a generic queueing system for
scheduling and processing background jobs in Odoo.

Features:

- Queue jobs to:
  - Execute a method on any model (recordset or model level)
  - Run a predefined server action
- Pass arguments (args) and keyword arguments (kwargs)
- Schedule future execution via run_at or delay in seconds
- Automatic retry logic with configurable maximum retries and backoff
  delay
- Records job duration, attempts, state transitions
- Supports optional post_message on success or failure (with job link)
- Executes as a specific user (user_id)
- Enqueue server actions instead of running them immediately
- Dashboard views: graph, pivot, KPIs
- Security groups: Read Only and Manager
- Cron jobs:
  - Process pending jobs
  - Cleanup old completed jobs
  - Notify administrator of failed jobs

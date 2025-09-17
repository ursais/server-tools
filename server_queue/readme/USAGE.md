1.  Create or use a Server Action or model method
2.  Use server.queue to enqueue the job with:
    - Target model and method or Server Action ID
    - Arguments and keyword arguments
    - Optional execution user, delay, and retries

## Example:

To enqueue a Server Action for later execution:

``` python
self.env['server.queue'].enqueue(
    model_name='ir.actions.server',
    method_name='run',
    args=[action_id],
    kwargs={'additional_param': value},
    post_message=True,
    group_id=self.env.ref('server_queue.group_general'),
)
```

## Queue Groups

- Jobs can be assigned to a queue group.
- Groups provide default retry and delay policies.
- The group dashboard shows job statistics and allows quick actions:
  - View all jobs for a group
  - View only failed jobs

## Manually Enqueue a Job

``` python
self.env['server.queue'].enqueue(
    name="Create Partner",
    model_name="res.partner",
    method_name="create",
    args=[[{'name': 'John Doe'}]],
    user_id=self.env.uid,
    post_message=True,
    delay_seconds=120,
    max_retries=2,
)
```

## Enqueue a Server Action

``` python
action = self.env.ref("my_module.ir_actions_server_action")
self.env['server.queue'].enqueue(
    name="Run Action",
    model_name="res.partner",
    server_action_id=action.id,
    target_res_id=42,
    kwargs={'context_flag': True},
    post_message=True,
)
```

## Auto-Enqueue Server Actions from UI

To enqueue instead of immediately run a server action:

1.  Open the Server Action form.
2.  Enable the checkbox: **Enqueue Instead of Execute**
3.  When triggered, the user will see a confirmation message.
4.  Job is created and picked up by the cron or manual run.

## Processing Jobs

- ✅ Automatically: via cron (default interval: 5 minutes)
- 🛠 Manually:
  - Open a job and click **Run Now**
  - Select multiple jobs in list view and trigger actions

## Failure and Retry

- Job states: pending, running, retry, failed, done
- Max retries is enforced per job
- Retry is delayed using run_at, configurable via system param:
  - server_queue.retry_delay_seconds (default: 60)

## Notifications

- Failed jobs post a message on the related record (if supported) with
  link to job
- Admin receives an email summary of unnotified failed jobs daily

## Security & Permissions

- Server Queue: Read Only – View jobs
- Server Queue: Manager – Full control over jobs and execution

## Enqueue Sale Order Confirmation via Server Action

You can create a server action on the sale.order model to defer order
confirmation:

``` python
jobs = []
for order in records:
    job = env['server.queue'].enqueue(
        name=f"Defer Confirmation: {order.name}",
        model_name="sale.order",
        method_name="action_confirm",
        args=[[order.id]],
        user=env.user,
        post_message=True,
        max_retries=3,
    )
    jobs.append(job)

# Return a notification summary to the user
action = {
    "type": "ir.actions.client",
    "tag": "display_notification",
    "params": {
        "title": "Jobs Queued",
        "message": "\n".join(
            [f"{len(jobs)} Sale Order confirmation job(s) enqueued."] +
            [f"• {job.name}" for job in jobs]
        ),
        "type": "success",
        "sticky": False,
    }
}
```

This will show a to-do style notification in the UI, confirming how many
jobs were queued, without navigating away.

## Enqueue Sale Order Confirmation from Python Code

You can also enqueue confirmation directly from your own module logic:

``` python
self.env['server.queue'].enqueue(
    name=f"Defer Confirmation: {sale_order.name}",
    model_name="sale.order",
    method_name="action_confirm",
    args=[[sale_order.id]],
    user=self.env.user,
    post_message=True,
    max_retries=3,
)
```

This schedules the confirmation method to run in the background queue
with retry logic, user context, and optional notifications.

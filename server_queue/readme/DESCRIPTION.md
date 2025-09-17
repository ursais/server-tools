This module provides an infrastructure to queue and defer method or
Server Action execution. It supports retry logic, user context, backoff
delays, and tracking of job results.

## Features

- Enqueue calls to model methods or Server Actions
- Configure retry policies and backoff delay
- Schedule jobs to run at a specific time
- Job dependencies and execution order
- Notifications on job failure or success (optional)
- Security access control and user execution context
- Group jobs using Queue Groups:
  - Define default retry/delay settings per group
  - View dashboards with job state KPIs
  - Use Kanban boards with quick actions to filter jobs by group

## Why Use This Module

This module is ideal when you need:

- A simple way to queue and schedule background jobs
- Full visibility into job states and results from the Odoo UI
- Built-in support for retrying, delayed execution, and user context
- Triggering jobs manually or automatically via Server Actions
- Queue grouping with dashboards and job KPIs

## Compared to OCA queue_job

While both modules offer background job processing, they differ
significantly:

- **server_queue** is lightweight, UI-centric, and easy to configure
- **queue_job** is performance-oriented and designed for large-scale
  async processing

Use server_queue when: - You need traceable, retryable jobs with clear
user-facing results - You prefer a module that runs within Odoo cron
without separate workers - You want group-based dashboards and admin
visibility

Use queue_job when: - You have high-volume, backend-heavy processing
needs - You're integrating with OCA connectors or batch processing
frameworks - You want to define jobs using Python decorators (@job)

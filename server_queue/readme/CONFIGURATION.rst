System Parameters
-----------------

The module supports the following optional configuration via system parameters
(`Settings > Technical > Parameters > System Parameters`):

- `server_queue.retry_delay_seconds`:
  Delay (in seconds) to wait before retrying a failed job.
  Default: `60`.

Queue Groups
------------

You may configure Queue Groups (menu: *Server Queue > Queue Groups*) to define:

- Default maximum retries per job
- Default delay between retries
- Active/inactive group status
- Logical grouping for jobs (e.g., by integration)

Each job will inherit these settings if assigned to a group.

Access Rights
-------------

Two security groups are available:

- **Server Queue / Manager**: Full access to all features and job management
- **Server Queue / Read Only**: Can view jobs but not modify or run them

Notifications
-------------

You may enable notifications:

- Email notifications for grouped job failures (administrator)
- `post_message` on the related record if supported


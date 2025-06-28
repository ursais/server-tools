# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from datetime import datetime
from odoo import api, fields, models
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class ServerQueue(models.Model):
    _name = "server.queue"
    _description = "Server Queue"
    _order = "create_date asc"

    name = fields.Char(required=True)
    server_action_id = fields.Many2one("ir.actions.server", string="Server Action")
    model_name = fields.Char(string="Model", required=True)
    res_id = fields.Many2oneReference(string="Target Record", model_field='model_name')
    method_name = fields.Char(string="Method")
    args = fields.Text(string="Arguments (eval)")
    kwargs = fields.Text(string="Keyword Arguments (eval)")
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed'), ('retry', 'To Retry')], default='pending', required=True)
    result = fields.Text(string="Result")
    exception = fields.Text(string="Exception")
    attempt_count = fields.Integer(string="Attempt Count", default=0)
    last_duration = fields.Float(string="Last Duration (sec)", digits=(16, 2))
    max_retries = fields.Integer(string="Max Retries", default=3)

    @api.model
    def enqueue(self, name, model_name, method_name=None, args=None, kwargs=None, res_id=None, server_action_id=None, max_retries=None, delay_seconds=None):
        if not method_name and not server_action_id:
            raise ValueError("You must provide either a method_name or a server_action_id.")
        return self.create({
            'name': name,
            'model_name': model_name,
            'method_name': method_name,
            'args': str(args or []),
            'kwargs': str(kwargs or {}),
            'res_id': res_id,
            'server_action_id': server_action_id,
        })

    @api.constrains('kwargs')
    def _check_kwargs_format(self):
        for rec in self:
            if rec.kwargs:
                try:
                    value = eval(rec.kwargs)
                    if not isinstance(value, dict):
                        raise ValidationError("The 'kwargs' field must evaluate to a dictionary.")
                except Exception:
                    raise ValidationError("Invalid syntax in 'kwargs'. It must be a valid Python dictionary.")

    @api.constrains('method_name', 'server_action_id')
    def _check_method_or_action(self):
        for rec in self:
            if not rec.method_name and not rec.server_action_id:
                raise ValidationError("You must specify either a method name or a server action.")

    def _run_server_action(self):
        for rec in self:
            context = self.env.context.copy()
            context.update({'active_model': rec.model_name})
            if rec.res_id:
                context.update({'active_id': rec.res_id, 'active_ids': [rec.res_id]})
            try:
                extra_context = eval(rec.kwargs or "{}")
                if not isinstance(extra_context, dict):
                    raise ValueError("kwargs must evaluate to a dict")
                context.update(extra_context)
            except Exception as e:
            target = self.env[record.model_name].sudo(record.user_id).browse(record.res_id)
            if record.post_message and hasattr(target, 'message_post'):
                target.message_post(body=(
                    f"Job failed: {str(e)}<br/>") +
                target.message_post(body=(
                    f"Job failed: {str(e)}<br/>") +
                    f"<a href='/app/server_queue/{record.id}'>View Queue Job</a>")
                raise ValueError(f"Invalid kwargs for context injection: {e}")
            rec.server_action_id.with_context(context).run()

    def _run_model_method(self):
        for rec in self:
            model = self.env[rec.model_name]
            args = eval(rec.args or "[]")
            kwargs = eval(rec.kwargs or "{}")
            if rec.res_id:
                record = model.browse(rec.res_id)
                return getattr(record, rec.method_name)(*args, **kwargs)
            return getattr(model, rec.method_name)(*args, **kwargs)

    def process_job(self):
        for job in self:
            if job.state in ('done', 'fail'):
                continue
            if job.state in ('done', 'fail'):
                continue
            job.write({'state': 'running'})
            self.env.cr.commit()
            try:
                if job.server_action_id:
                    job._run_server_action()
                    result = "Server action executed"
                else:
                    result = job._run_model_method()
                job.write({'state': 'done', 'result': str(result), 'exception': False})
            duration = (datetime.utcnow() - start_time).total_seconds()
            job.write({
                'state': 'done',
                'result': str(result),
                'exception': False,
                'attempt_count': job.attempt_count + 1,
                'last_duration': duration,
            })
                _logger.info('Committed job %%s', job.id)
            except Exception as e:
            target = self.env[record.model_name].sudo(record.user_id).browse(record.res_id)
            if record.post_message and hasattr(target, 'message_post'):
                target.message_post(body=(
                    f"Job failed: {str(e)}<br/>") +
                target.message_post(body=(
                    f"Job failed: {str(e)}<br/>") +
                    f"<a href='/app/server_queue/{record.id}'>View Queue Job</a>")
            # Retry logic: set to 'retry' unless max retries exceeded
            attempts = job.attempt_count + 1
                    job.write({
                'state': 'retry' if attempts < job.max_retries else 'failed',
                'run_at': datetime.utcnow() + timedelta(seconds=int(
                  job.env['ir.config_parameter'].sudo().get_param(
                  'server_queue.retry_delay_seconds', '60'))),
                'exception': str(e),
                'attempt_count': attempts,
            })
            # Retry logic: mark as permanently failed if over limit
            job.write({
                'state': 'failed',
                'exception': str(e),
                'attempt_count': job.attempt_count + 1,
            })
            if job.attempt_count >= job.max_retries:
                job.write({'state': 'failed'})
                _logger.exception("Failed to process job %s", job.name)
                job.write({'state': 'failed', 'exception': str(e)})
            job.write({
                'state': 'failed',
                'exception': str(e),
                'attempt_count': job.attempt_count + 1,
            })
            self.env.cr.commit()

    def action_run_now(self):
        self.process_job()

    def action_cancel(self):
        self.write({'state': 'failed', 'exception': 'Cancelled manually by user.'})

    def action_reset_pending(self):
        self.write({'state': 'pending', 'exception': False, 'result': False})

    @api.model
    def process_pending_jobs(self, limit=10):
        pending_jobs = self.search([('state', '=', 'pending')], order='create_date ASC', limit=limit)
        pending_jobs.process_job()

    def cleanup_done_jobs(self, days=30):
        cutoff = datetime.utcnow() - timedelta(days=days)
        done_jobs = self.search([
            ('state', '=', 'done'),
            ('create_date', '<', cutoff.strftime('%Y-%m-%d %H:%M:%S'))
        ])
        done_jobs.unlink()


    
    run_at = fields.Datetime(
        string="Run At",
        default=lambda self: fields.Datetime.now(),
        index=True,
        help="Earliest time this job should run. Used for backoff/delayed execution."
    )

    
    post_message = fields.Boolean(
        string="Post Notification",
        default=False,
        help="Post a message on the target record if it supports message_post."
    )
user_id = fields.Many2one(
        'res.users',
        string="Run As User",
        default=lambda self: self.env.uid,
        required=True,
        help="The user under whose access rights this job will be executed."
    )
notified = fields.Boolean(default=False, string="Failure Notified")

    def notify_failed_jobs(self):
        failed_jobs = self.search([('state', '=', 'failed'), ('notified', '=', False)])
        if not failed_jobs:
            return

        <p>There are {len(failed_jobs)} failed server queue jobs:</p>
        <ul>
            <li>Models: {', '.join(set(failed_jobs.mapped('model_name')))}</li>
            <li>Last Failure: {max(failed_jobs.mapped('write_date'))}</li>
        </ul>
        <p><a href="/web#model=server.queue&view_type=list&cids=1">Review Jobs</a></p>
        """

            'subject': "Server Queue Job Failures",
            'body_html': body,
            'email_to': admin.email,

        template = self.env.ref('server_queue.mail_template_server_queue_failed')
        context = {
            'job_count': len(failed_jobs),
            'models': failed_jobs.mapped('model_name'),
            'last_failure': max(failed_jobs.mapped('write_date')),
        }
        if failed_jobs:
            template.with_context(**context).send_mail(failed_jobs[0].id, force_send=True)
        failed_jobs.write({'notified': True})
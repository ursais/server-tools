# Copyright (c) 2025 Daniel Reis
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError
from datetime import timedelta
from freezegun import freeze_time
import logging

_logger = logging.getLogger(__name__)

class TestServerQueue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Queue = self.env['server.queue']
        self.res_partner = self.env['res.partner'].create({'name': 'Test Partner'})

    def test_enqueue_and_run_method(self):
        job = self.Queue.enqueue(
            model_name='res.partner',
            method_name='write',
            args=[[self.res_partner.id], {'name': 'Updated Name'}],
            user_id=self.env.uid,
            post_message=True,
        )
        self.assertEqual(job.state, 'pending')
        job.process_job()
        self.assertEqual(job.state, 'done')
        self.assertEqual(self.res_partner.name, 'Updated Name')

    def test_retry_logic(self):
        job = self.Queue.create({
            'model_name': 'res.partner',
            'method_name': 'non_existent_method',
            'args': [[self.res_partner.id]],
            'user_id': self.env.uid,
            'max_retries': 1,
        })
        job.process_job()
        self.assertEqual(job.state, 'retry')
        job.process_job()
        self.assertEqual(job.state, 'failed')

    def test_server_action_execution(self):
        action = self.env['ir.actions.server'].create({
            'name': 'Test Action',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'state': 'code',
            'code': "records.write({'name': 'Actioned'})",
        })
        job = self.Queue.enqueue(
            model_name='res.partner',
            target_res_id=self.res_partner.id,
            server_action_id=action.id,
            user_id=self.env.uid,
            post_message=True,
        )
        job.process_job()
        self.res_partner.invalidate_cache()
        self.assertEqual(self.res_partner.name, 'Actioned')
        self.assertEqual(job.state, 'done')

    def test_run_at_and_delay(self):
        job = self.Queue.enqueue(
            model_name='res.partner',
            method_name='write',
            args=[[self.res_partner.id], {'name': 'Delayed'}],
            delay_seconds=300,
        )
        self.assertGreater(job.run_at, job.create_date)

    def test_notify_failed_jobs(self):
        failed_job = self.Queue.create({
            'model_name': 'res.partner',
            'method_name': 'non_existent_method',
            'args': [[self.res_partner.id]],
            'user_id': self.env.uid,
            'state': 'failed',
            'notified': False,
        })
        self.Queue.notify_failed_jobs()
        failed_job.invalidate_cache()
        self.assertTrue(failed_job.notified)

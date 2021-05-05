from odoo.tests import common


@common.tagged("-at_install", "post_install")
class TestApply(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.Category = self.env["product.category"]
        self.Log = self.env["auditlog.log"]

    def test_100_create_category(self):
        # Demo data has Sync Rule for product Categories
        self.categA = self.Category.create({"name": "Category A"})
        self.logA = self.Log.search(
            [("res_id", "=", self.categA.id), ("state", "!=", "logged")]
        )
        self.categA.with_context({}).unlink()  # FIXME: without with_context should work

        self.assertIn("Category A", self.logA.raw_args_kwargs)
        self.assertEqual(
            self.logA.state, "captured", "Create method generates a sync log"
        )

        self.logA.prepare_auditlog_events()
        self.assertTrue(self.logA.external_id)
        self.assertIn("Category A", self.logA.prepared_args_kwargs)
        self.assertEqual(self.logA.state, "Prepared", "Preprocess assigns an XMLID")

        self.logA.state = "Pulled"

        self.logA.apply_event_data()
        count = self.Category.search([("name", "=", "Category A")], count=True)
        self.assertEqual(self.logA.state, "Processed")
        self.assertEqual(count, 1, "Apply recreates the Category")

        self.logA.state = "Pulled"
        self.logA.apply_event_data()
        self.assertEqual(self.logA.state, "Processed")
        count = self.Category.search([("name", "=", "Category A")], count=True)
        self.assertEqual(
            count, 1, "Repeating apply does not create a duplicate Category"
        )

from odoo.tests import Form, common


@common.tagged("-at_install", "post_install")
class TestApply(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.Category = self.env["product.category"]
        self.Log = self.env["auditlog.log"]
        self.ProductTemplate = self.env["product.template"]
        self.IrModel = self.env["ir.model"]
        self.StockPicking = self.env["stock.picking"]
        self.stock_location = self.env.ref("stock.stock_location_stock")
        self.warehouse = self.env["stock.warehouse"].search(
            [("lot_stock_id", "=", self.stock_location.id)], limit=1
        )

    def test_100_create_category(self):
        # Demo data has Sync Rule for product Category
        self.categA = self.Category.create({"name": "Category A"})
        self.model_id = self.IrModel.search([("model", "=", self.Category._name)])

        # Search relevant logs from created Category.
        self.logA = self.Log.search(
            [
                ("res_id", "=", self.categA.id),
                ("model_id", "=", self.model_id.id),
                ("state", "!=", "logged"),
            ]
        )

        self.assertIn("Category A", self.logA.raw_args_kwargs)
        self.assertEqual(
            self.logA.state, "captured", "Create method generates a sync log"
        )

        # call prepare event data method
        self.logA.prepare_auditlog_events()
        self.assertTrue(self.logA.external_id)
        self.assertIn("Category A", self.logA.prepared_args_kwargs)
        self.assertEqual(self.logA.state, "Prepared", "Preprocess assigns an XMLID")

        self.categA.unlink()

        self.logA.state = "Pulled"

        # call apply event data method
        self.logA.apply_event_data()
        count = self.Category.search([("name", "=", "Category A")], count=True)
        self.assertEqual(self.logA.state, "Processed")
        self.assertEqual(count, 1, "Apply recreates the Category")

        self.logA.state = "Pulled"
        self.logA.apply_event_data()
        self.assertNotEqual(self.logA.state, "Processed")
        count = self.Category.search([("name", "=", "Category A")], count=True)
        self.assertEqual(
            count, 1, "Repeating apply does not create a duplicate Category"
        )

    def test_101_create_product_template(self):
        # Demo data has Sync Rule for product template

        self.productA = self.ProductTemplate.create({"name": "Product A"})
        self.model_id = self.IrModel.search(
            [("model", "=", self.ProductTemplate._name)]
        )
        self.productlogA = self.Log.search(
            [
                ("res_id", "=", self.productA.id),
                ("model_id", "=", self.model_id.id),
                ("state", "!=", "logged"),
            ]
        )

        self.assertIn("Product A", self.productlogA.raw_args_kwargs)
        self.assertEqual(
            self.productlogA.state, "captured", "Create method generates a sync log"
        )

        # Call prepare event data method
        self.productlogA.prepare_auditlog_events()
        self.assertTrue(self.productlogA.external_id)
        self.assertIn("Product A", self.productlogA.prepared_args_kwargs)
        self.assertEqual(
            self.productlogA.state, "Prepared", "Preprocess assigns an XMLID"
        )

        self.productA.unlink()

        # Call apply event data method
        self.productlogA.state = "Pulled"
        self.productlogA.apply_event_data()
        count = self.ProductTemplate.search([("name", "=", "Product A")], count=True)
        self.assertEqual(self.productlogA.state, "Processed")
        self.assertEqual(count, 1, "Apply recreates the Product")

        # Repeating call apply event data method
        self.productlogA.state = "Pulled"
        self.productlogA.apply_event_data()
        self.assertNotEqual(self.productlogA.state, "Processed")
        count = self.ProductTemplate.search([("name", "=", "Product A")], count=True)
        self.assertEqual(
            count, 1, "Repeating apply does not create a duplicate Product"
        )

    def test_102_create_stock_picking(self):
        # Demo data has Sync Rule for Stock Picking

        self.productA = self.env["product.product"].create(
            {"name": "Product A", "type": "product"}
        )
        # Create a new picking with the one products.
        picking_form = Form(self.StockPicking)
        picking_form.picking_type_id = self.warehouse.in_type_id
        picking_form.origin = "Picking-Test"
        with picking_form.move_ids_without_package.new() as move_line:
            move_line.product_id = self.productA
            move_line.product_uom_qty = 5
        self.receipt = picking_form.save()

        self.model_id = self.IrModel.search([("model", "=", self.StockPicking._name)])
        self.receiptlog = self.Log.search(
            [
                ("res_id", "=", self.receipt.id),
                ("model_id", "=", self.model_id.id),
                ("state", "!=", "logged"),
            ]
        )

        self.assertIn("Picking-Test", self.receiptlog.raw_args_kwargs)
        self.assertEqual(
            self.receiptlog.state, "captured", "Create method generates a sync log"
        )

        # Call prepare event data method
        self.receiptlog.prepare_auditlog_events()
        self.assertTrue(self.receiptlog.external_id)
        self.assertIn("Picking-Test", self.receiptlog.prepared_args_kwargs)
        self.assertEqual(
            self.receiptlog.state, "Prepared", "Preprocess assigns an XMLID"
        )

        self.receipt.unlink()

        self.receiptlog.state = "Pulled"

        # Call apply event data method
        self.receiptlog.apply_event_data()
        count = self.StockPicking.search([("origin", "=", "Picking-Test")], count=True)
        self.assertEqual(self.receiptlog.state, "Processed")
        self.assertEqual(count, 1, "Apply recreates the Picking")

        # Repeating call apply event data method
        self.receiptlog.state = "Pulled"
        self.receiptlog.apply_event_data()
        self.assertNotEqual(self.receiptlog.state, "Processed")
        count = self.StockPicking.search([("origin", "=", "Picking-Test")], count=True)
        self.assertEqual(
            count, 1, "Repeating apply does not create a duplicate Picking"
        )

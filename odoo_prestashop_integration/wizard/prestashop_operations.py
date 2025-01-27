from odoo import models, fields
from datetime import timedelta

IMPORT_OPERATIONS = [
    ('import_order', 'Import Order'),
    ('import_category','Import Category'),
    ("import_product", "Import Product"),
    ("import_customers", "Import Customer"),
]


class PrestashopOperations(models.TransientModel):
    _name = 'prestashop.operations'
    _description = 'Prestashop Import Export'

    def _get_default_marketplace(self):
        instance_id = self._context.get('active_id')
        return instance_id

    def _get_default_from_date_order(self):
        instance_id = self.env.context.get('active_id')
        instance_id = self.env['prestashop.instance.integration'].search([('id', '=', instance_id)], limit=1)
        from_date_order = instance_id.last_order_synced_date if instance_id.last_order_synced_date else fields.Datetime.now() - timedelta(
            30)
        from_date_order = fields.Datetime.to_string(from_date_order)
        return from_date_order

    def _get_default_to_date(self):
        to_date = fields.Datetime.now()
        to_date = fields.Datetime.to_string(to_date)
        return to_date

    instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance',
        default=_get_default_marketplace
    )
    prestashop_operation = fields.Selection(
        selection=[('import', 'Import')],
        string='Prestashop Operations',
        default='import'
    )
    import_operations = fields.Selection(
        selection=IMPORT_OPERATIONS,
        string='Import Operations',
        default='import_order'
    )
    # Import Order fields
    from_date_order = fields.Datetime(
        string='From OrderDate',
        default=_get_default_from_date_order
    )
    to_date_order = fields.Datetime(
        string='To OrderDate',
        default=_get_default_to_date
    )
    prestashop_order_id = fields.Char(
        string='Order IDs'
    )

    # Import Product fields
    prestashop_product_id = fields.Char(
        string='Product IDs'
    )

    def execute_process_of_prestashop(self):
        """
        This method is used to execute an import and export process.
        """
        instance = self.instance_id
        queue_ids = False
        model_action = False
        model_form = False
        if self.prestashop_operation == 'import':
            if self.import_operations == "import_product":
                product_queue_ids = self.env['prestashop.product.data.queue'].import_product_from_prestashop_to_odoo(instance,
                                                                                                          self.prestashop_product_id)
                if product_queue_ids:
                    queue_ids = product_queue_ids
                    model_action = "odoo_prestashop_integration.action_prestashop_product_process"
                    model_form = "odoo_prestashop_integration.view_prestashop_product_queue_form"
            elif self.import_operations == "import_category":
                print('CATEGORY')
                self.env['product.category'].prestashop_to_odoo_import_product_categories(instance.id)
            elif self.import_operations == "import_customers":
                print('CUSTOMER')
                customer_queue_ids = self.env['customer.data.queue'].import_customers_from_prestashop_to_odoo(instance)
                if customer_queue_ids:
                    queue_ids = customer_queue_ids
                    model_action = "odoo_prestashop_integration.action_prestashop_customer_queue"
                    model_form = "odoo_prestashop_integration.prestashop_customer_data_form"
            elif self.import_operations == "import_order":
                print('Order')
                order_queue_ids = self.env['order.data.queue'].import_orders_from_prestashop_to_odoo(instance,
                                                                                                  self.from_date_order,
                                                                                                  self.to_date_order,
                                                                                                  self.prestashop_order_id)
                if order_queue_ids:
                    queue_ids = order_queue_ids
                    model_action = "odoo_prestashop_integration.action_prestashop_order_queue_process"
                    model_form = "odoo_prestashop_integration.view_form_prestashop_order_queue_form"

        # Based on queue ids, action & form view open particular model with created queue records.
        if queue_ids and model_action and model_form:
            action = self.env.ref(model_action).sudo().read() and self.env.ref(model_action).sudo().read()[0]
            form_view = self.sudo().env.ref(model_form)

            if len(queue_ids) != 1:
                action["domain"] = [("id", "in", queue_ids)]
            else:
                action.update({"view_id": (form_view.id, form_view.name), "res_id": queue_ids[0],
                               "views": [(form_view.id, "form")]})
            return action

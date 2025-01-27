import logging
import requests
import json
from odoo import models, fields, tools, api

_logger = logging.getLogger("Prestashop Inventory Queue")


class PrestashopInventoryDataQueue(models.Model):
    _name = "prestashop.inventory.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Inventory Data Queue"
    _order = 'id DESC'

    @api.depends('prestashop_inventory_queue_line_ids.state')
    def _compute_queue_line_state_and_count(self):
        """
        Compute method to set queue state automatically based on queue line states.
        """
        for queue in self:
            queue_line_ids = queue.prestashop_inventory_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(
        string='Name'
    )
    instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance',
        help='Select Instance Id'
    )
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                   ('completed', 'Completed'), ('failed', 'Failed')],
        tracking=True,
        default='draft',
        compute="_compute_queue_line_state_and_count"
    )
    prestashop_inventory_queue_line_ids = fields.One2many(
        comodel_name="prestashop.inventory.data.queue.line",
        inverse_name="prestashop_inventory_queue_id",
        string="Inventory Queue Lines"
    )
    prestashop_log_id = fields.Many2one(
        comodel_name='prestashop.log',
        string="Logs"
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        """
        sequence = self.env.ref("odoo_prestashop_integration.seq_inventory_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(PrestashopInventoryDataQueue, self).create(vals_list)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue.
        """
        for queue in self:
            if queue.prestashop_inventory_queue_line_ids:
                queue.prestashop_inventory_queue_line_ids.unlink()
        return super(PrestashopInventoryDataQueue, self).unlink()

    def generate_prestashop_inventory_queue(self, instance, location):
        """
        This method is used to create new record of inventory queue.
        """
        return self.create({
            'instance_id': instance.id,
        })

    def create_prestashop_inventory_queue_job(self, instance_id, prestashop_inventory_list, log_id):
        """
        Based on the batch size inventory queue will create.
        """
        queue_id_list = []
        batch_size = 50
        for prestashop_inventories in tools.split_every(batch_size, prestashop_inventory_list):
            queue_id = self.generate_prestashop_inventory_queue(instance_id)
            for inventory in prestashop_inventories:
                self.env['prestashop.inventory.data.queue.line'].create_prestashop_inventory_queue_line(inventory, instance_id,
                                                                                             queue_id, log_id)
            queue_id_list.append(queue_id.id)
            if not queue_id.prestashop_inventory_queue_line_ids:
                queue_id.unlink()
        return queue_id_list

    def process_queue_to_export_stock(self):
        """
        In this method from queue record button clicked & export inventory from odoo to prestashop.
        """
        self.export_inventory_from_odoo_to_prestashop()

    def export_inventory_from_odoo_to_prestashop(self):
        """
        This method is used to export inventory from odoo to prestashop.
        """
        instance_id = self.env['prestashop.instance.integration'].browse()

        log_id = self.env['prestashop.log'].generate_prestashop_logs('order', 'export', instance_id, 'Process Started')
        try:
            # Check Authentication Process
            url = ''.format()
            headers = {
                'Authorization': 'Bearer {}'.format(),
            }

            try:
                # Prepare Order Data
                request_data = json.dumps({ })
                response_status, response_data = instance_id.api_calling_method("POST", url,
                                                                                request_data, headers)

                if response_status:
                    print('response_date',response_status)
                else:
                    log_msg = f"Something went wrong\n{response_data}."
                    self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'export', instance_id, log_msg,
                                                                         request_data, log_msg, log_id, True)
            except Exception as e:
                log_msg = f"Something went wrong\n{e}."
                self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'export', instance_id, log_msg,
                                                                     False, log_msg, log_id, True)

        except Exception as e:
            log_msg = f"Something went wrong.\n{e}."
            self.env['prestashop.log.line'].generate_prestashop_process_line('order', 'export', instance_id, log_msg,
                                                                 False, log_msg, log_id, True)

        finally:
            log_id.prestashop_operation_message = 'Process Has Been Finished'
            if not log_id.prestashop_operation_line_ids:
                log_id.unlink()


class PrestashopInventoryDataQueueLine(models.Model):
    _name = "prestashop.inventory.data.queue.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product'
    )
    prestashop_inventory_queue_id = fields.Many2one(
        comodel_name='prestashop.inventory.data.queue',
        string='Inventory Data Queue'
    )
    instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance',
        help='Select Instance Id'
    )
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('completed', 'Completed'), ('failed', 'Failed')],
        default='draft'
    )
    inventory_data_to_process = fields.Text(
        string="Inventory Data"
    )
    number_of_fails = fields.Integer(
        string="Number of attempts",
        help="This field gives information regarding how many time we will try to proceed the order",
        copy=False
    )

    def create_prestashop_inventory_queue_line(self, prestashop_inventory_dict, instance_id, queue_id, log_id):
        """
        From this method queue line will create if not exists.
        """
        existing_queue = self.search(
            [('product_id', '=', prestashop_inventory_dict.get('product_id')), ('state', '=', 'draft')])
        if existing_queue:
            existing_queue.inventory_data_to_process = prestashop_inventory_dict.get('inventory_data_to_process')
            message = "Inventory data queue line already exists with product => {}".format(
                existing_queue.product_id.name)
            self.env['prestashop.log.line'].generate_prestashop_process_line('inventory', 'import', instance_id,
                                                                             message, False, message, log_id, True)
            return existing_queue
        inventory_queue_line_id = self.create({
            'product_id': prestashop_inventory_dict.get('product_id'),
            'state': 'draft',
            'inventory_data_to_process': prestashop_inventory_dict.get('inventory_data_to_process'),
            'instance_id': instance_id and instance_id.id or False,
            'prestashop_inventory_queue_id': queue_id and queue_id.id or False,
        })
        message = "New Inventory data queue line created with product => {}".format(
            inventory_queue_line_id.product_id.name)
        self.env['prestashop.log.line'].generate_prestashop_process_line('inventory', 'import', instance_id,
                                                                         message, False, message, log_id, False)
        return inventory_queue_line_id

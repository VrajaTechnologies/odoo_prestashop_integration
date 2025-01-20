import logging
import re
from odoo import models, fields, tools, api
import pprint

_logger = logging.getLogger("Prestashop Product Queue")


class ProductDataQueue(models.Model):
    _name = "product.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Prestashop Product Data Queue"
    _order = 'id DESC'

    @api.depends('prestashop_product_queue_line_ids.state')
    def _compute_product_queue_line_state_and_count(self):
        for queue in self:
            queue_line_ids = queue.prestashop_product_queue_line_ids
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
        compute="_compute_product_queue_line_state_and_count"
    )
    product_queue_line_total_record = fields.Integer(
        string='Total Records',
        help="This Button Shows Number of Total Records"
    )
    product_queue_line_draft_record = fields.Integer(
        string='Draft Records',
        help="This Button Shows Number of Draft Records"
    )
    product_queue_line_fail_record = fields.Integer(
        string='Fail Records',
        help="This Button Shows Number of Fail Records"
    )
    product_queue_line_done_record = fields.Integer(
        string='Done Records',
        help="This Button Shows Number of Done Records"
    )
    product_queue_line_cancel_record = fields.Integer(
        string='Cancel Records',
        help="This Button Shows Number of Done Records"
    )
    prestashop_product_queue_line_ids = fields.One2many(
        comodel_name="product.data.queue.line",
        inverse_name="prestashop_product_queue_id",
        string="Product Queue Lines"
    )
    prestashop_log_id = fields.Many2one(
        comodel_name='prestashop.log',
        string="Logs"
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        DG
        """
        sequence = self.env.ref("odoo_prestashop_integration.seq_product_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(ProductDataQueue, self).create(vals_list)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue
        DG
        """
        for queue in self:
            if queue.prestashop_product_queue_line_ids:
                queue.prestashop_product_queue_line_ids.unlink()
        return super(ProductDataQueue, self).unlink()

    def generate_prestashop_product_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def create_prestashop_product_queue_job(self, instance_id, prestashop_product_list):
        """
        Based on the batch size product queue will create.
        DG
        """
        queue_id_list = []
        batch_size = 50
        for prestashop_products in tools.split_every(batch_size, prestashop_product_list):
            queue_id = self.generate_prestashop_product_queue(instance_id)
            for product in prestashop_products:
                prestashop_product_dict = product
                self.env['product.data.queue.line'].create_prestashop_product_queue_line(prestashop_product_dict, instance_id,
                                                                                      queue_id)
            queue_id_list.append(queue_id.id)
        return queue_id_list

    def fetch_product_from_prestashop_to_odoo(self, instance, prestashop_product_ids=False):
        """
       This method is used to import all Products from prestashop to odoo.
       DG
       """
        prestashop_product_list = []
        if prestashop_product_ids:
            template_ids = list(set(re.findall(re.compile(r"(\d+)"), prestashop_product_ids)))
            for temp_id in template_ids:
                api_operation = "http://%s@%s/api/products/?output_format=JSON&filter[id]=[%s]&display=full" % (
                    instance.prestashop_api_key, instance.prestashop_url, temp_id)
                response_status, product_response_data = instance.send_get_request_from_odoo_to_prestashop(
                    api_operation)
                if response_status:
                    product_dicts = product_response_data.get('products')
                    prestashop_product_list.extend(product_dicts)
                else:
                    _logger.info("Getting Some Error In Fetch The product :: \n {}".format(product_response_data))
        else:
            try:
                api_operation = "http://%s@%s/api/products/?output_format=JSON" % (
                    instance and instance.prestashop_api_key,
                    instance and instance.prestashop_url)
                response_status, response_data = instance.send_get_request_from_odoo_to_prestashop(api_operation)
                if response_status:
                    _logger.info("prestashop Get Product Response : {0}".format(response_data))
                    products = response_data.get('products')[10:20]
                    for product in products:
                        prod_id = product.get('id')
                        if prod_id:
                            api_operation = "http://%s@%s/api/products/?output_format=JSON&filter[id]=[%s]&display=full" % (
                                instance and instance.prestashop_api_key,
                                instance and instance.prestashop_url, prod_id)
                            response_status, product_response_data = instance.send_get_request_from_odoo_to_prestashop(
                                api_operation)
                            if response_status:
                                product_dicts = product_response_data.get('products')
                                prestashop_product_list.extend(product_dicts)
                            else:
                                _logger.info("Getting Some Error In Fetch The product :: \n {}".format(product_response_data))
            except Exception as e:
                _logger.info("Getting Some Error In Fetch The product :: \n {}".format(e))
        return prestashop_product_list

    def import_product_from_prestashop_to_odoo(self, instance, prestashop_product_ids=False):
        """
        From operation wizard's button, this method will call if product import option gets selected.
        DG
        """
        queue_id_list, prestashop_product_list = [], []
        last_synced_date = fields.Datetime.now()

        if prestashop_product_ids:
            prestashop_product_list = self.fetch_product_from_prestashop_to_odoo(instance, prestashop_product_ids)
        else:
            prestashop_product_list = self.fetch_product_from_prestashop_to_odoo(instance)
        if prestashop_product_list:
            queue_id_list = self.create_prestashop_product_queue_job(instance, prestashop_product_list)
            if queue_id_list:
                instance.last_product_synced_date = last_synced_date
        return queue_id_list

    def process_prestashop_product_queue_using_cron(self):
        """
        This method is used for process product data queue automatically using cron job.
        """
        instance_ids = self.env['prestashop.instance.integration'].search([])
        if instance_ids:
            for instance_id in instance_ids:
                self.with_context(from_cron=True).process_prestashop_product_queue(instance_id)
        return True

    def process_prestashop_product_queue(self, instance_id=False):
        """
        This method is used for Create product from prestashop To Odoo
        From product queue create product in odoo
        DG
        """
        prestashop_product_object, instance_id = self.env['prestashop.product.listing'], instance_id or self.instance_id
        if self._context.get('from_cron'):
            product_data_queues = self.search([('instance_id', '=', instance_id.id), ('state', '!=', 'completed')],
                                              order="id asc")
        else:
            product_data_queues = self
        for product_data_queue in product_data_queues:
            if not product_data_queue.prestashop_log_id:
                log_id = self.env['prestashop.log'].generate_prestashop_logs('product', 'import', instance_id, 'Process Started')
            else:
                log_id = product_data_queue.prestashop_log_id
            self._cr.commit()

            if self._context.get('from_cron'):
                product_data_queue_lines = product_data_queue.prestashop_product_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed'])
            else:
                product_data_queue_lines = product_data_queue.prestashop_product_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed', 'failed'] and x.number_of_fails < 3)

            commit_counter = 0
            for line in product_data_queue_lines:
                commit_counter += 1
                if commit_counter == 10:
                    self._cr.commit()
                    commit_counter = 0
                try:
                    prestashop_product_listing = prestashop_product_object.prestashop_create_products(product_queue_line=line,
                                                                                instance=instance_id, log_id=log_id)
                    if not prestashop_product_listing:
                        line.number_of_fails += 1
                    else:
                        line.product_template_id = prestashop_product_listing.product_tmpl_id.id
                except Exception as error:
                    line.state = 'failed'
                    error_msg = 'Getting Some Error When Try To Process Product Queue From Prestashop To Odoo'
                    self.env['prestashop.log.line'].with_context(
                        for_variant_line=line).generate_prestashop_process_line('product', 'import', instance_id,
                                                                                error_msg, False, error, log_id, True)
                    _logger.info(error)
            self.prestashop_log_id = log_id.id
            log_id.prestashop_operation_message = 'Process Has Been Finished'
            if not log_id.prestashop_operation_line_ids:
                log_id.unlink()


class ProductDataQueueLine(models.Model):
    _name = "product.data.queue.line"
    _description = "Product Data Queue Line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string='Name'
    )
    prestashop_product_queue_id = fields.Many2one(
        comodel_name='product.data.queue',
        string='Product Data Queue'
    )
    instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance',
        help='Select Instance Id'
    )
    product_data_id = fields.Char(
        string="Product Data ID",
        help='This is the Product Id of Prestashop Product'
    )
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                   ('completed', 'Completed'), ('failed', 'Failed')],
        default='draft'
    )
    product_data_to_process = fields.Text(
        string="Product Data"
    )
    product_template_id = fields.Many2one(
        comodel_name="product.template"
    )
    number_of_fails = fields.Integer(
        string="Number of attempts",
        help="This field gives information regarding how many time we will try to proceed the order",
        copy=False
    )
    log_line = fields.One2many(
        comodel_name='prestashop.log.line', inverse_name='product_queue_line'
    )

    def create_prestashop_product_queue_line(self, prestashop_product_dict, instance_id, queue_id):
        """
        From this method queue line will create.
        DG
        """
        product_queue_line_id = self.create({
            'product_data_id': prestashop_product_dict.get('id'),
            'state': 'draft',
            'name': prestashop_product_dict.get('name', '').strip(),
            'product_data_to_process': pprint.pformat(prestashop_product_dict),
            'instance_id': instance_id and instance_id.id or False,
            'prestashop_product_queue_id': queue_id and queue_id.id or False,
        })
        return product_queue_line_id

class ProductVariantQueueLine(models.Model):
    _name = "product.variant.queue.line"
    _description = "Product Variant Queue Line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string='Name')
    prestashop_variant_product_queue_id = fields.Many2one('product.data.queue', string='Product Variant Data Queue')
    instance_id = fields.Many2one('prestashop.instance.integration', string='Instance',
                                  help='Select Instance Id')
    product_variant_data_id = fields.Char(string="Product Variant Data ID", help='This is the Product Id of Prestashop Product')
    state = fields.Selection(selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                                        ('completed', 'Completed'), ('failed', 'Failed')], default='draft')
    variant_data_to_process = fields.Text(string="Variant Data")
    product_id = fields.Many2one("product.product")
    number_of_fails = fields.Integer(string="Number of attempts",
                                     help="This field gives information regarding how many time we will try to proceed the order",
                                     copy=False)
    log_line = fields.One2many('prestashop.log.line', 'product_queue_line')
from odoo import models, fields, _, api
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
import json
import base64
import logging
from requests import request
_logger = logging.getLogger("Prestashop: ")


class PrestashopInstanceIntegrations(models.Model):
    _name = 'prestashop.instance.integration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Prestashop Instance Integration'

    name = fields.Char(
        string='Name',
        help='Enter Instance Name',
        copy=False,
        tracking=True
    )
    active = fields.Boolean(
        string='Active',
        copy=False,
        tracking=True,
        default=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        help='Select Company',
        copy=False,
        tracking=True,
        default=lambda self: self.env.user.company_id
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        help='Select Warehouse',
        copy=False,
        tracking=True
    )
    prestashop_shop_urls_id = fields.Char(
        string='Prestashop Shop URL ID',
        copy=False
    )
    prestashop_shop_id = fields.Char(
        string='Prestashop Shop ID',
        copy=False
    )
    last_order_synced_date = fields.Datetime(
        string="Last Order Synced Date",
        copy=False,
        tracking=True
    )
    last_product_synced_date = fields.Datetime(
        string="Last Product Synced Date",
        copy=False,
        tracking=True
    )
    last_synced_customer_date = fields.Datetime(
        string='Last Customer Synced Date',
        copy=False,
        tracking=True
    )
    last_synced_inventory_date = fields.Datetime(
        string='Last Inventory Synced Date',
        copy=False,
        tracking=True
    )
    prestashop_url = fields.Char(
        string='Prestashop Url',
        help='Enter Prestashop Url',
        copy=False,
        tracking=True
    )
    prestashop_api_key = fields.Char(
        string='Prestashop API Key',
        help='Enter Prestashop API Key',
        copy=False,
        tracking=True
    )
    price_list_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Price List",
        copy=False,
        tracking=True
    )
    image = fields.Binary(
        string="Image",
        help="Select Image."
    )
    create_product_if_not_found = fields.Boolean(
        string='Create Product in Odoo if not matched.',
        default=False
    )
    order_status_ids = fields.Many2many(
        comodel_name='prestashop.order.status',
        string='Order Status',
        required=True
    )
    prestashop_discount_product_id = fields.Many2one('product.product', string="Prestashop Discount Product",
                                                     copy=False, tracking=True, default=lambda self: self.env.ref(
            'odoo_prestashop_integration.discount_product', False),
                                                     help="this product will be considered as a discount product for add \n"
                                                          "sale order line with discount value")

    prestashop_gift_product_id = fields.Many2one('product.product', string="Prestashop Gift Product",
                                                 copy=False, tracking=True,
                                                 default=lambda self: self.env.ref(
                                                     'odoo_prestashop_integration.gift_card_product', False),
                                                 help="this product will be considered as a gift product for add \n"
                                                      "sale order line")
    prestashop_shipping_product_id = fields.Many2one('product.product', string="Prestashop Shipping Product",
                                                     copy=False, tracking=True,
                                                     default=lambda self: self.env.ref(
                                                         'odoo_prestashop_integration.shipping_product', False),
                                                     help="this product will be considered as a Shipping product for add \n"
                                                          "sale order line")
    # is_sync_images = fields.Boolean("Sync Product Images?",
    #                                 help="If true then Images will be sync at the time of Import Products.",
    #                                 default=False)

    apply_tax_in_order = fields.Selection(
        selection=[("odoo_tax", "Odoo Default Tax Behaviour"),
                   ("create_prestashop_tax", "Create new tax If Not Found")],
        default='odoo_tax',
        copy=False,
        help=""" For Prestashop Orders :- \n
                        1) Odoo Default Tax Behaviour - The Taxes will be set based on Odoo's
                                     default functional behaviour i.e. based on Odoo's Tax and Fiscal Position configurations. \n
                        2) Create New Tax If Not Found - System will search the tax data received 
                        from Prestashop in Odoo, will create a new one if it fails in finding it.""")

    auto_fulfilled_gif_card_order = fields.Boolean(
        string='Auto Fulfilled Gift Card Order',
        default=True,
        tracking=True
    )
    notify_customer = fields.Boolean(
        string='Notify Customer Once Update Order Status',
        default=False,
        tracking=True
    )
    is_verified = fields.Boolean(
        string='Verified ?'
    )

    def prestashop_unlink_old_records_cron(self):
        """
        This method is used when unlink old records cron will execute and logs more than 30 days old will be deleted.
        """
        today_date = datetime.now().date()
        month_ago = today_date - timedelta(days=30)
        prestashop_log_data = self.env['prestashop.log'].search([]).filtered(lambda x: x.create_date.date() < month_ago)
        if prestashop_log_data:
            prestashop_log_data.unlink()
        order_data_queue = self.env['order.data.queue'].search([]).filtered(lambda x: x.create_date.date() < month_ago)
        if order_data_queue:
            order_data_queue.unlink()
        inventory_data_queue = self.env['prestashop.inventory.data.queue'].search([]).filtered(
            lambda x: x.create_date.date() < month_ago)
        if inventory_data_queue:
            inventory_data_queue.unlink()

    def send_get_request_from_odoo_to_prestashop(self, api_operation):
        try:
            _logger.info("Prestashop API Request Data : %s" % (api_operation))
            data = "%s" % (self.prestashop_api_key)
            encode_data = base64.b64encode(data.encode("utf-8"))
            authorization_data = "Basic %s" % (encode_data.decode("utf-8"))
            headers = {"Authorization": "%s" % authorization_data}
            response_data = request(method='GET', url=api_operation, headers=headers)
            if response_data.status_code in [200, 201]:
                result = response_data.json()
                _logger.info("Prestashop API Response Data : %s" % (result))
                return True, result
            else:
                result = response_data.json()
                _logger.info("Prestashop API Response Data : %s" % (result))
                return False, result
        except Exception as e:
            _logger.info("Prestashop API Response Data : %s" % (e))
            return False, e

    def action_test_connection(self):
        try:
            api_operation = f"http://{self.prestashop_api_key}@{self.prestashop_url}/api/shop_urls/?output_format=JSON&display=full&filter[domain]=[{self.prestashop_url}]"
            response_status, response_data = self.send_get_request_from_odoo_to_prestashop(api_operation)
            if response_status:
                _logger.info("Prestashop Shop URLs Response : {0}".format(response_data))
                shop_urls = response_data.get('shop_urls')
                for shop_url in shop_urls:
                    if shop_url.get('active') == "1" and shop_url.get('domain') == self.prestashop_url:
                        message = _("Everything seems properly set up!")
                        self.with_context({'is_check_connection_from_write': True}).write({'is_verified': True,
                                                                                           'prestashop_shop_urls_id': shop_url.get('id'),
                                                                                           'prestashop_shop_id': shop_url.get('id_shop')
                                                                                           })
                        _logger.info(message)
                    else:
                        raise ValidationError("Something went wrong!")
            else:
                raise ValidationError(response_data.get('errors'))
        except Exception as e:
            self.with_context({'is_check_connection_from_write': True}).write({'is_verified': False})
            message = _("Issue in Connection! \n {}".format(e))
            _logger.info(message)
            raise ValidationError(message)

    @api.model_create_multi
    def create(self, vals):
        """
        This method is used to check connection at the time of creating record of FTP Syncing.
        Author: DG
        """
        res = super(PrestashopInstanceIntegrations, self).create(vals)
        res.action_test_connection()
        return res

    def write(self, vals):
        """
        This method is used to check connection at the time of write record of FTP Syncing.
        Author: DG
        """
        res = super(PrestashopInstanceIntegrations, self).write(vals)
        if 'prestashop_url' in vals or 'prestashop_api_key' in vals:
            self.action_test_connection()
        return res

    def action_prestashop_open_instance_view_form(self):
        form_id = self.sudo().env.ref('odoo_prestashop_integration.prestashop_instance_integration_form')
        action = {
            'name': _('Prestashop Instance'),
            'view_id': False,
            'res_model': 'prestashop.instance.integration',
            'context': self._context,
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(form_id.id, 'form')],
            'type': 'ir.actions.act_window',
        }
        return action

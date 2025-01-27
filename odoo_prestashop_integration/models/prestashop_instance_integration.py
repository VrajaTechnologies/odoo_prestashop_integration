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

    name = fields.Char(string='Name', help='Enter Instance Name', copy=False, tracking=True)
    active = fields.Boolean(string='Active', copy=False, tracking=True, default=True)
    company_id = fields.Many2one('res.company', string='Company', help='Select Company',
                                 copy=False, tracking=True, default=lambda self: self.env.user.company_id)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', help='Select Warehouse',
                                   copy=False, tracking=True)
    prestashop_store_time_zone = fields.Char(string='Prestashop Store Time Zone',
                                          help='This field used to import order process', copy=False)
    last_order_synced_date = fields.Datetime(string="Last Order Synced Date", copy=False, tracking=True)
    last_product_synced_date = fields.Datetime(string="Last Product Synced Date", copy=False, tracking=True)
    last_synced_customer_date = fields.Datetime(string='Last Customer Synced Date', copy=False, tracking=True)
    last_synced_inventory_date = fields.Datetime(string='Last Inventory Synced Date', copy=False, tracking=True)
    prestashop_url = fields.Char(string='Prestashop Url', help='Enter Prestashop Url', copy=False, tracking=True)
    prestashop_api_key = fields.Char(string='Prestashop API Key', help='Enter Prestashop API Key', copy=False, tracking=True)
    price_list_id = fields.Many2one('product.pricelist', string="Price List", copy=False, tracking=True)
    order_status_ids = fields.Many2many('prestashop.order.status', string='Order Status', required=True)
    image = fields.Binary(string="Image", help="Select Image.")
    create_product_if_not_found = fields.Boolean('Create Product in Odoo if not matched.', default=False)
    is_sync_images = fields.Boolean("Sync Product Images?",
                                    help="If true then Images will be sync at the time of Import Products.",
                                    default=False)
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

    apply_tax_in_order = fields.Selection(
        [("odoo_tax", "Odoo Default Tax Behaviour"), ("create_prestashop_tax",
                                                      "Create new tax If Not Found")], default='odoo_tax',
        copy=False, help=""" For Prestashop Orders :- \n
                        1) Odoo Default Tax Behaviour - The Taxes will be set based on Odoo's
                                     default functional behaviour i.e. based on Odoo's Tax and Fiscal Position configurations. \n
                        2) Create New Tax If Not Found - System will search the tax data received 
                        from Prestashop in Odoo, will create a new one if it fails in finding it.""")

    auto_fulfilled_gif_card_order = fields.Boolean(string='Auto Fulfilled Gift Card Order', default=True, tracking=True)
    notify_customer = fields.Boolean(string='Notify Customer Once Update Order Status', default=False, tracking=True)


    # def api_calling_method(self, request_type, api_url, request_data, header):
    #     """
    #     This method is used to call API & based on status code it will return value.
    #     """
    #     _logger.info("Request API URL:::: %s" % api_url)
    #     _logger.info("Data:::: %s" % request_data)
    #     response_data = requests.request(method=request_type, url=api_url, headers=header, data=request_data)
    #     if response_data.status_code in [200, 201]:
    #         response_data = response_data.json()
    #         _logger.info(">>> Response Data {}".format(response_data))
    #         return True, response_data
    #     else:
    #         return False, response_data.text

    def send_get_request_from_odoo_to_prestashop(self, api_operation=False):
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
                _logger.info("Prestashop API Response Data : %s" % (response_data.text))
                return False, response_data.text
        except Exception as e:
            _logger.info("Prestashop API Response Data : %s" % (e))
            return False, e


    def action_test_connection(self):
        pass

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

# -*- coding: utf-8 -*-
from odoo import models, fields


class ReturnNoReturn(models.Model):
    _name = 'prestashop.order.status'
    _description = 'Order Status Data'

    name = fields.Char(string="Order State")
    order_status_id = fields.Char(string="Order Status ID")
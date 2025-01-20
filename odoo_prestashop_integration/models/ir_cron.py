from odoo import models, fields


class IrCron(models.Model):
    _inherit = 'ir.cron'

    prestashop_instance = fields.Many2one('prestashop.instance.integration')

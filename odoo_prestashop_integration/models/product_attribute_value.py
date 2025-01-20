from odoo import models, fields

class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    prestashop_option_value_id = fields.Char(string="Product Option Value ID")

    def get_attribute_values(self, name, attr_value_id, attribute_id, auto_create=False):
        """
        Returns the attribute value if it is found; otherwise, creates a new one and returns it.
        DG
        """
        attribute_values = self.search([('name', '=', name), ('attribute_id', '=', attribute_id)], limit=1)
        if not attribute_values:
            attribute_values = self.search([('name', '=ilike', name), ('attribute_id', '=', attribute_id)], limit=1)
        if not attribute_values and auto_create:
            return self.create(({'name': name, 'attribute_id': attribute_id, 'prestashop_option_value_id': attr_value_id}))
        if not attribute_values.prestashop_option_value_id:
            attribute_values.prestashop_option_value_id = attr_value_id
        return attribute_values

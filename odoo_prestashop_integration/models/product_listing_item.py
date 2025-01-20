import logging
from odoo import models, fields

_logger = logging.getLogger("Prestashop Product: ")


class PrestashopProductListingItem(models.Model):
    _name = 'prestashop.product.listing.item'
    _description = 'Prestashop Product Listing Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string="Title"
    )
    prestashop_instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance',
        ondelete='cascade'
    )
    prestashop_product_listing_id = fields.Many2one(
        comodel_name='prestashop.product.listing',
        string="Product Listing",
        ondelete = 'cascade'
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product'
    )
    prestashop_product_variant_id = fields.Char(
        string='Prestashop Product ID'
    )
    product_sku = fields.Char(
        string='SKU'
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    # image_ids = fields.Many2many('prestashop.product.image', 'prestashop_product_image_listing_item_rel', 'listing_item_id',
    #                              'prestashop_image_id', string="Images")
    active = fields.Boolean(
        default=True
    )
    exported_in_prestashop = fields.Boolean(
        default=False
    )
    combination_price = fields.Float(
        string='Price'
    )
    combination_quantity = fields.Float(
        string='Quantity'
    )
    combination_weight = fields.Float(
        string='Weight'
    )

    stock_value = fields.Float(string="Stock Value")
    inventory_item_id = fields.Char(string="Inventory Item ID")
    inventory_policy = fields.Selection([("continue", "Allow"), ("deny", "Denied")],
                                        string="Sale out of stock products?",
                                        default="deny",
                                        help="If true than customers are allowed to place an order for the product"
                                             "variant when it is out of stock.")
    inventory_management = fields.Selection([("prestashop", "Prestashop tracks this product Inventory"),
                                             ("Dont track Inventory", "Don't track Inventory")],
                                            default="prestashop",
                                            help="If you select 'Prestashop tracks this product Inventory' than prestashop"
                                                 "tracks this product inventory.if select 'Don't track Inventory' then"
                                                 "after we can not update product stock from odoo")

    def set_prestashop_variant_sku(self, product_template, variant_data):
        """
        This method updates the variant SKU based on the attribute and attribute value.
        @param: self, prestashop_attributes, product_template
        @return: odoo_product_variant
        DG
        """
        odoo_product_variant = False
        for variation in variant_data:
            # From variant/combination get product option values IDs & matched with odoo product variant's
            # product template attribute values data & which matched inside it set SKU/Internal reference.
            variant_option_values_ids = [opt_vals.get('id') for opt_vals in
                                         variation.get('associations').get('product_option_values')]

            for odoo_product_variant in product_template.product_variant_ids:
                product_attribute_values = odoo_product_variant.with_user(1).product_template_attribute_value_ids
                mapped_values_ids = product_attribute_values.product_attribute_value_id.mapped(
                    'prestashop_option_value_id')

                # Sort attribute values by ID for consistent comparison
                sorted_values_ids = product_attribute_values.sorted(lambda v: v.id).product_attribute_value_id.mapped(
                    'prestashop_option_value_id')

                if mapped_values_ids == variant_option_values_ids or sorted_values_ids == variant_option_values_ids:
                    _logger.info(
                        "Matching Variant Found: Option Labels => {0}, Attribute Values => {1}, Variant ID => {2}".format(
                            variant_option_values_ids, sorted_values_ids, odoo_product_variant))

                    vals = {
                        'default_code': variation.get('reference'),
                        'lst_price': float(variation.get('price')),
                        'standard_price': float(variation.get('wholesale_price')),
                        'prestashop_variant_id': variation.get('id'),
                        'weight': float(variation.get('weight')),
                        'barcode': variation.get('upc'),
                    }
                    odoo_product_variant.with_user(1).write(vals)
                    _logger.info("Product Variant Updated: {0}".format(odoo_product_variant.default_code))
                    self._cr.commit()
                    break

        return odoo_product_variant

    def prepare_prestashop_attribute_values(self, prestashop_attributes):
        """Prepare a list of attribute values.
        :param result: Response of the product.
        @return: attrib_line_vals (list of attribute vals)
        DG
        """
        product_attribute_obj = self.env["product.attribute"]
        product_attribute_value_obj = self.env["product.attribute.value"]
        attrib_line_vals = []
        for attrib in prestashop_attributes:
            attrib_name = attrib.get("name")
            attrib_values = attrib.get("values")
            attrib_values_ids = attrib.get("values_ids")
            attribute = product_attribute_obj.get_attribute(attrib_name, auto_create=True)[0]
            attr_val_ids = [
                product_attribute_value_obj.get_attribute_values(attr_value, attr_value_id, attribute.id, auto_create=True)[0].id
                for attr_value,attr_value_id in zip(attrib_values, attrib_values_ids)]

            if attr_val_ids:
                attribute_line_ids_data = [0, False,
                                           {"attribute_id": attribute.id, "value_ids": [[6, False, attr_val_ids]]}]
                attrib_line_vals.append(attribute_line_ids_data)
        return attrib_line_vals

    def prestashop_create_product_with_variant(self, product_data, prestashop_attributes, variant_data):
        """
        Create a product template and variant.
        DG
        """
        product_template_obj = self.env["product.template"]
        product_template = False

        # Get product name from the response
        template_title = product_data.get("name", "")
        if not template_title:
            _logger.warning("Product name is missing in the response.")
            return False

        # Prepare attribute lines specific to this product based on option values
        relevant_attrib_line_vals = self.prepare_prestashop_attribute_values(prestashop_attributes)
        if relevant_attrib_line_vals:
            template_vals = {
                "name": template_title,
                "type": "product",
                "attribute_line_ids": relevant_attrib_line_vals,
                "invoice_policy": "order",
            }
            # Create product template with relevant attributes and values
            product_template = product_template_obj.create(template_vals)

            # Set Prestashop variant SKUs for this product
            odoo_product_variant = self.set_prestashop_variant_sku(product_template, variant_data)
            if not odoo_product_variant:
                _logger.warning("Failed to set Prestashop variant SKUs for product: %s", template_title)
                product_template.unlink()  # Cleanup partially created template
                return False

        return product_template


class ProductProduct(models.Model):
    _inherit = 'product.product'

    prestashop_variant_id = fields.Integer(
        string='Prestashop Variant ID'
    )
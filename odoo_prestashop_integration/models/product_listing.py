import pytz
import logging
from odoo import models, fields, api

_logger = logging.getLogger("Prestashop Product: ")
utc = pytz.utc


class PrestashopProductListing(models.Model):
    _name = 'prestashop.product.listing'
    _description = 'Prestashop Product Listing'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    def compute_count_of_variants(self):
        """
        This method is used to count total variants in product listing module.
        DG
        """
        for rec in self:
            rec.total_variants_in_prestashop = len(rec.prestashop_product_listing_items)

    name = fields.Char(
        string='Name'
    )
    prestashop_instance_id = fields.Many2one(
        comodel_name='prestashop.instance.integration',
        string='Instance'
    )
    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string="Product Template"
    )
    product_catg_id = fields.Many2one(
        comodel_name='product.category',
        string="Product Category"
    )
    prestashop_category_ids = fields.Many2many(
        comodel_name='product.category',
        string='Prestashop Categories'
    )
    prestashop_product_id = fields.Char(
        string="Prestashop Product ID"
    )
    inventory_item_id = fields.Char(
        string='Inventory Item ID',
    )
    description = fields.Text(
        string="Description"
    )
    last_sync_date = fields.Datetime(
        string="Last Synced",
        copy=False
    )
    prestashop_product_listing_items = fields.One2many(
        comodel_name='prestashop.product.listing.item',
        inverse_name='prestashop_product_listing_id',
        string='Product Listing Items'
    )
    product_data_queue_id = fields.Many2one(
        comodel_name='prestashop.product.data.queue',
        string='Product Queue'
    )
    exported_in_prestashop = fields.Boolean(
        default=False
    )
    total_variants_in_prestashop = fields.Integer(
        string="Total Variants",
        compute="compute_count_of_variants"
    )
    published_at = fields.Datetime(
        string="Published Date"
    )
    # image_ids = fields.One2many('prestashop.product.image', 'prestashop_listing_id', 'Images')

    def fetch_combination_prestashop_to_odoo(self, instance, log_id, product_data):
        """
        DG
        """
        try:
            combination_api_operation = "http://%s@%s/api/combinations/?output_format=JSON&filter[id_product]=%s&display=full" % (
            instance.prestashop_api_key, instance.prestashop_url, product_data.get('id'))
            combination_response_status, combination_response_data = instance.send_get_request_from_odoo_to_prestashop(
                combination_api_operation)
            if combination_response_status:
                if combination_response_data:
                    return combination_response_data.get('combinations')
                else:
                    return []
            else:
                log_msg = f"Something went wrong, not getting successful response of combinations from Prestashop\n{combination_response_data}."
                self.env['prestashop.log.line'].generate_prestashop_process_line('product', 'import', instance,
                                                                                 log_msg, False, log_msg, log_id, True)
        except Exception as e:
            log_msg = f"Something went wrong, not getting successful response of combinations from Prestashop\n{e}."
            self.env['prestashop.log.line'].generate_prestashop_process_line('product', 'import', instance,
                                                                             log_msg, False, log_msg, log_id, True)

    def synchronize_variant_data_with_existing_template(self, instance, variant_data, product_data,
                                                        prestashop_product_listing, product_listing_vals,
                                                        product_queue_line, log_id):
        """
        This method syncs prestashop variant data with an existing prestashop template in Odoo.
        DG
        """
        need_to_archive = False
        variant_ids = []
        prestashop_attributes = self.env['product.attribute'].create_product_option_from_prestashop(instance,
                                                                                                    product_data,
                                                                                                    log_id)
        odoo_product_template = prestashop_product_listing.product_tmpl_id
        name = product_listing_vals.get("template_title", "")

        for variant in variant_data:
            variant_id = variant.get("id")
            product_sku = variant.get("reference")

            if not product_sku:
                message = "Product %s have no sku having variant id %s." % (name, variant_id)
                _logger.info(message)
                self.env['prestashop.log.line'].with_context(
                    for_variant_line=product_queue_line).generate_prestashop_process_line(
                    'product', 'import', instance, message,
                    False, False, log_id, True)
                if product_queue_line:
                    product_queue_line.state = 'failed'
                continue

            # Here we are not passing SKU while searching prestashop product, Because We are updating existing product.
            odoo_product_variant = self.env["product.product"]
            prestashop_product_listing_item_obj = self.env["prestashop.product.listing.item"]

            prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                [("prestashop_product_variant_id", "=", variant_id), ("prestashop_instance_id", "=", instance.id)], limit=1)
            if product_sku:
                if not prestashop_product_listing_item:
                    prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                        [("product_sku", "=", product_sku), ("prestashop_product_variant_id", "=", False),
                         ("prestashop_instance_id", "=", instance.id)], limit=1)
                if not prestashop_product_listing_item:
                    prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                        [("product_id.default_code", "=", product_sku), ("prestashop_product_variant_id", "=", False),
                         ("prestashop_instance_id", "=", instance.id)], limit=1)
                if not prestashop_product_listing_item:
                    odoo_product_variant = odoo_product_variant.search([("default_code", "=", product_sku)], limit=1)
            if prestashop_product_listing_item and not odoo_product_variant:
                odoo_product_variant = prestashop_product_listing_item.product_id

            product_listing_item_vals = self.prepare_product_listing_item_vals(instance, variant)
            domain = [("prestashop_product_variant_id", "=", False), ("prestashop_instance_id", "=", instance.id),
                      ("prestashop_product_listing_id", "=", prestashop_product_listing.id)]
            if not prestashop_product_listing_item:
                domain.append(("product_sku", "=", product_sku))
                prestashop_product_listing_item = prestashop_product_listing_item_obj.search(domain, limit=1)

                if not prestashop_product_listing_item:
                    attribute_value_domain = [('prestashop_variant_id', '=', variant_id)]
                    if attribute_value_domain:
                        odoo_product_variant = odoo_product_variant.search(attribute_value_domain, limit=1)

                if odoo_product_variant:
                    prestashop_product_listing_item = self.create_or_update_prestashop_product_listing_item(
                        product_listing_item_vals,
                        prestashop_product_listing_item,
                        prestashop_product_listing,
                        odoo_product_variant)

                # If odoo's product not matched with response, then need to create a new product in odoo or not.
                elif instance.create_product_if_not_found:
                    if odoo_product_template.attribute_line_ids:
                        prestashop_product_listing_item = self.sync_odoo_product_variant(odoo_product_template,
                                                                                      prestashop_attributes,
                                                                                      variant, prestashop_product_listing,
                                                                                      product_listing_item_vals)
                    else:
                        attribute_line_data = self.env[
                            'prestashop.product.listing.item'].prepare_prestashop_attribute_values(
                            prestashop_attributes)
                        odoo_product_variant = self.prestashop_create_product_without_variant(name, variant, attribute_line_data)

                        need_to_archive = True
                        prestashop_product_listing, prestashop_product_listing_item = self.with_context(
                            without_variant=True).create_or_update_prestashop_product_listing_and_listing_item(
                            product_listing_vals, product_listing_item_vals, prestashop_product_listing,
                            prestashop_product_listing_item, odoo_product_variant, update_product_listing=True,
                            update_product_listing_item=True)

                    if isinstance(prestashop_product_listing_item, str):
                        message = prestashop_product_listing_item
                        _logger.info(message)
                        self.env['prestashop.log.line'].with_context(
                            for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import',
                                                                                               instance,
                                                                                               message, False, False,
                                                                                               log_id, True)
                        if product_queue_line:
                            product_queue_line.state = 'failed'
                        variant_ids = []
                        break
                else:
                    message = "Product %s not found for SKU %s in Odoo." % (name, product_sku)
                    _logger.info(message)
                    self.env['prestashop.log.line'].with_context(
                        for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import',
                                                                                           instance, message,
                                                                                           False, False, log_id, True)
                    if product_queue_line:
                        product_queue_line.state = 'failed'
                    continue
            else:
                self.create_or_update_prestashop_product_listing_item(product_listing_item_vals,
                                                                   prestashop_product_listing_item)
            instance.price_list_id.set_product_price(prestashop_product_listing_item.product_id.id,
                                                     variant.get("price"))
            variant_ids.append(variant_id)

        return variant_ids, need_to_archive

    def sync_product_with_existing_product_listing(self, prestashop_product_listing, product_data, instance,
                                                   product_category, product_categories, log_id, product_queue_line):
        """
        Import existing prestashop product listing.
        DG
        """
        product_listing_vals = self.prepare_prestashop_product_listing_vals(product_data, instance, product_category,
                                                                            product_categories)
        variant_data = self.fetch_combination_prestashop_to_odoo(instance, log_id, product_data)

        self.create_or_update_prestashop_product_listing(product_listing_vals, prestashop_product_listing)

        variant_ids, need_to_archive = self.synchronize_variant_data_with_existing_template(instance, variant_data,
                                                                                            product_data,
                                                                                            prestashop_product_listing,
                                                                                            product_listing_vals,
                                                                                            product_queue_line, log_id)
        if need_to_archive:
            products_to_archive = prestashop_product_listing.prestashop_product_listing_items.filtered(
                lambda x: int(x.prestashop_product_variant_id) not in variant_ids)
            products_to_archive.write({"active": False})
        return prestashop_product_listing if variant_ids else False

    def prestashop_create_products(self, product_queue_line, instance, log_id, order_line_product_listing_id=False):
        """
        This method is used to create or update prestashop product listing, listing item & also Odoo's product &
        product variants.
        :param: order_line_product_listing_id: This parameter is used when import order process running & at that time product not found in Odoo based on product id.
        DG
        """
        if order_line_product_listing_id:
            product_data = self.env['prestashop.product.data.queue'].fetch_product_from_prestashop_to_odoo(instance,
                                                                                                prestashop_product_ids=order_line_product_listing_id)
            for product in product_data:
                product_data = product
        else:
            product_data = eval(product_queue_line.product_data_to_process)

        if not product_data:
            return True

        # Identify whether all products from PrestaShop that belong to multiple categories are available in Odoo or not.
        category_ids = product_data.get('associations') and product_data.get('associations').get('categories')
        product_category_obj = self.env['product.category']
        for prestashop_category_id in category_ids:
            product_category = product_category_obj.search(
                [('prestashop_category_id', '=', prestashop_category_id.get('id'))])
            if not product_category:
                product_category_obj.prestashop_to_odoo_import_product_categories(instance.id, log_id)
        prestashop_product_categories_ids = [int(item['id']) for item in category_ids]
        product_categories = product_category_obj.search(
            [('prestashop_category_id', 'in', prestashop_product_categories_ids)])

        # Perform a final search using the default category to set it in the product.
        product_category = self.env['product.category'].search(
            [('prestashop_category_id', '=', product_data.get('id_category_default'))])
        if not product_category:
            process_message = "This product [{}], you can't import without category".format(product_data.get('name'))
            self.env['prestashop.log.line'].generate_prestashop_process_line('product', 'import', instance,
                                                                             process_message, False, process_message,
                                                                             log_id, True)
            return False

        prestashop_product_listing = self.search(
            [("prestashop_product_id", "=", product_data.get("id")), ("prestashop_instance_id", "=", instance.id)])

        if not prestashop_product_listing:
            prestashop_product_listing = self.create_new_product_listing(product_data, instance, product_category,
                                                                         product_categories, log_id, product_queue_line)
        else:
            prestashop_product_listing = self.sync_product_with_existing_product_listing(prestashop_product_listing,
                                                                                         product_data, instance,
                                                                                         product_category,
                                                                                         product_categories, log_id,
                                                                                         product_queue_line)
        # # Image sync process
        # if prestashop_product_listing and instance.is_sync_images:
        #     self.sync_product_image_from_prestashop(instance, prestashop_product_listing, product_data)
        #
        if product_queue_line and prestashop_product_listing and not prestashop_product_listing.product_data_queue_id:
            prestashop_product_listing.product_data_queue_id = product_queue_line.prestashop_product_queue_id
        if prestashop_product_listing and product_queue_line:
            product_queue_line.state = "completed"
            msg = "Product => {} is successfully imported in odoo.".format(prestashop_product_listing.name)
            _logger.info(msg)
            self.env['prestashop.log.line'].with_context(
                for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import', instance, msg,
                                                                                   False,
                                                                                   product_data, log_id, False)
            self._cr.commit()
        return prestashop_product_listing


    def create_or_update_prestashop_product_listing_and_listing_item(self, product_listing_vals, product_listing_item_vals,
                                                                  prestashop_product_listing, prestashop_product_listing_item,
                                                                  odoo_product_variant, update_product_listing=False,
                                                                  update_product_listing_item=False):
        """
        This method is used to create or update prestashop template and/or variant.
        DG
        """
        if update_product_listing:
            prestashop_product_listing = self.create_or_update_prestashop_product_listing(product_listing_vals,
                                                                                    prestashop_product_listing,
                                                                                    odoo_product_variant)
        if update_product_listing_item:
            prestashop_product_listing_item = self.create_or_update_prestashop_product_listing_item(product_listing_item_vals,
                                                                                              prestashop_product_listing_item,
                                                                                              prestashop_product_listing,
                                                                                              odoo_product_variant)
        return prestashop_product_listing, prestashop_product_listing_item

    def sync_odoo_product_variant(self, odoo_product_template, prestashop_attributes, variant_data,
                                  prestashop_product_listing, product_listing_item_vals):
        """
        Check for new attributes and generate a new variant in Odoo.
        DG
        """
        product_attribute_value_obj = self.env["product.attribute.value"]
        odoo_product_variant = self.env["product.product"]

        product_sku = variant_data.get("reference")
        odoo_attribute_lines = odoo_product_template.attribute_line_ids.filtered(
            lambda x: x.attribute_id.create_variant == "always")
        if len(odoo_attribute_lines) != len(prestashop_attributes):
            return "Product %s has tried to add a new attribute for SKU %s in Odoo." % (
                prestashop_product_listing.name, product_sku
            )
        for attrib in prestashop_attributes:
            for attrib_value, attrib_value_id in zip(attrib.get("values"), attrib.get("values_ids")):
                attrib_name = attrib.get("name")

                attribute_id = odoo_attribute_lines.filtered(
                    lambda x: x.display_name == attrib_name).attribute_id.id
                value_id = product_attribute_value_obj.get_attribute_values(
                    attrib_value, attrib_value_id, attribute_id, auto_create=True)[0].id

                attribute_line = odoo_attribute_lines.filtered(lambda x: x.attribute_id.id == attribute_id)
                if value_id not in attribute_line.value_ids.ids:
                    attribute_line.value_ids = [(4, value_id, False)]
        odoo_product_template._create_variant_ids()

        # Set Prestashop variant SKUs for this product
        variant_option_values_ids = [opt_vals.get('id') for opt_vals in
                                     variant_data.get('associations').get('product_option_values')]

        for odoo_product_variant in odoo_product_template.product_variant_ids:
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
                    'default_code': variant_data.get('reference'),
                    'lst_price': float(variant_data.get('price')),
                    'standard_price': float(variant_data.get('wholesale_price')),
                    'prestashop_variant_id': variant_data.get('id'),
                    'weight': float(variant_data.get('weight')),
                    'barcode': variant_data.get('upc'),
                }
                odoo_product_variant.with_user(1).write(vals)
                self._cr.commit()
                break

        if not odoo_product_variant:
            return "Unknown error occurred. Couldn't find product %s with SKU %s in Odoo." % (
                prestashop_product_listing.name, product_sku
            )
        prestashop_product_listing_item = self.create_or_update_prestashop_product_listing_item(
            product_listing_item_vals, False, prestashop_product_listing, odoo_product_variant
        )
        return prestashop_product_listing_item

    def create_new_product_listing(self, product_data, instance, product_category, product_categories, log_id,
                                   product_queue_line):
        """
        This function serves the purpose of bringing in new products from Prestashop to Odoo.
        DG
        """
        need_to_update_prestashop_product_listing = True
        prestashop_product_listing = False

        product_listing_vals = self.prepare_prestashop_product_listing_vals(product_data, instance, product_category,
                                                                            product_categories)
        name = product_listing_vals.get("template_title")
        odoo_product_template = False

        variant_data = self.fetch_combination_prestashop_to_odoo(instance, log_id, product_data)
        if not variant_data:
            odoo_product_variant = self.prestashop_create_product_without_variant(name, product_data)
            if odoo_product_variant:
                prestashop_product_listing = self.with_context(
                    without_variant=True).create_or_update_prestashop_product_listing(product_listing_vals, False,
                                                                                      odoo_product_variant,
                                                                                      product_data=product_data)
                instance.price_list_id.set_product_price(odoo_product_variant.id, product_data.get("price"))

        for variant in variant_data:
            variant_id = variant.get("id")
            product_sku = variant.get("reference")

            if not product_sku:
                message = "Product %s have no sku having variant id %s." % (name, variant_id)
                _logger.info(message)
                self.env['prestashop.log.line'].with_context(
                    for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import', instance,
                                                                                       message, False, False, log_id,
                                                                                       True)
                if product_queue_line:
                    product_queue_line.state = 'failed'
                continue

            product_listing_item_vals = self.prepare_product_listing_item_vals(instance, variant, product_data)

            odoo_product_variant = self.env["product.product"]
            prestashop_product_listing_item_obj = self.env["prestashop.product.listing.item"]

            prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                [("prestashop_product_variant_id", "=", variant_id), ("prestashop_instance_id", "=", instance.id)], limit=1)
            if product_sku:
                if not prestashop_product_listing_item:
                    prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                        [("product_sku", "=", product_sku), ("prestashop_product_variant_id", "=", False),
                         ("prestashop_instance_id", "=", instance.id)], limit=1)
                if not prestashop_product_listing_item:
                    prestashop_product_listing_item = prestashop_product_listing_item_obj.search(
                        [("product_id.default_code", "=", product_sku), ("prestashop_product_variant_id", "=", False),
                         ("prestashop_instance_id", "=", instance.id)], limit=1)
                if not prestashop_product_listing_item:
                    odoo_product_variant = odoo_product_variant.search([("default_code", "=", product_sku)], limit=1)
            if prestashop_product_listing_item and not odoo_product_variant:
                odoo_product_variant = prestashop_product_listing_item.product_id
            if odoo_product_variant:
                odoo_product_template = odoo_product_variant.product_tmpl_id

            if prestashop_product_listing_item:
                self.create_or_update_prestashop_product_listing_item(product_listing_item_vals,
                                                                   prestashop_product_listing_item)
                if need_to_update_prestashop_product_listing:
                    prestashop_product_listing = self.create_or_update_prestashop_product_listing(product_listing_vals,
                                                                                            prestashop_product_listing_item.prestashop_product_listing_id,
                                                                                            odoo_product_variant, False)
            elif odoo_product_variant:
                prestashop_product_listing, prestashop_product_listing_item = self.create_or_update_prestashop_product_listing_and_listing_item(
                    product_listing_vals, product_listing_item_vals, prestashop_product_listing,
                    prestashop_product_listing_item, odoo_product_variant,
                    update_product_listing=need_to_update_prestashop_product_listing, update_product_listing_item=True)
                need_to_update_prestashop_product_listing = False

            # If odoo's product or prestashop listing & listing item not matched with response,
            # then need to create a new product in odoo or not.
            elif instance.create_product_if_not_found:
                prestashop_attributes = self.env['product.attribute'].create_product_option_from_prestashop(instance,
                                                                                                            product_data,
                                                                                                            log_id)
                if odoo_product_template and odoo_product_template.attribute_line_ids:
                    if not prestashop_product_listing:
                        prestashop_product_listing = self.create_or_update_prestashop_product_listing(product_listing_vals,
                                                                                                False, False,
                                                                                                odoo_product_template)
                    prestashop_product_listing_item = self.sync_odoo_product_variant(odoo_product_template,
                                                                                  prestashop_attributes,
                                                                                  variant, prestashop_product_listing,
                                                                                  product_listing_item_vals)
                    need_to_update_prestashop_product_listing = False
                else:
                    odoo_product_template = prestashop_product_listing_item_obj.prestashop_create_product_with_variant(
                        product_data, prestashop_attributes, variant_data)
                    attribute_value_domain = [('prestashop_variant_id', '=', variant_id)]
                    odoo_product_variant = odoo_product_template.product_variant_ids.search(attribute_value_domain, limit=1)
                    prestashop_product_listing, prestashop_product_listing_item = self.create_or_update_prestashop_product_listing_and_listing_item(
                        product_listing_vals, product_listing_item_vals, prestashop_product_listing,
                        prestashop_product_listing_item, odoo_product_variant, update_product_listing=True,
                        update_product_listing_item=True)
                    need_to_update_prestashop_product_listing = False
                if isinstance(prestashop_product_listing_item, str):
                    message = prestashop_product_listing_item
                    _logger.info(message)
                    self.env['prestashop.log.line'].with_context(
                        for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import',
                                                                                              instance, message, False,
                                                                                              False, log_id, True)
                    if product_queue_line:
                        product_queue_line.state = 'failed'
                    continue
            else:
                message = "Product %s not found for SKU %s in Odoo." % (name, product_sku)
                _logger.info(message)
                self.env['prestashop.log.line'].with_context(
                    for_variant_line=product_queue_line).generate_prestashop_process_line('product', 'import', instance,
                                                                                       message, False, False, log_id,
                                                                                       True)
                if product_queue_line:
                    product_queue_line.state = 'failed'
                continue

            if need_to_update_prestashop_product_listing and prestashop_product_listing:
                prestashop_product_listing = self.create_or_update_prestashop_product_listing(product_listing_vals,
                                                                                        prestashop_product_listing)
                need_to_update_prestashop_product_listing = False

            instance.price_list_id.set_product_price(prestashop_product_listing_item.product_id.id,
                                                     variant.get("price"))
        return prestashop_product_listing

    def prestashop_create_product_without_variant(self, product_name, variant_data, attribute_line_data=[]):
        """
        Create product without variants.
        DG
        """
        odoo_product_variant = self.env["product.product"]
        product_sku = variant_data.get("reference", "")
        if product_sku:
            vals = {
                "name": product_name,
                "type": "product",
                "default_code": product_sku,
                "invoice_policy": "order",
                "barcode": variant_data.get("upc"),
                "lst_price": variant_data.get("price"),
                "standard_price": variant_data.get("wholesale_price")
            }
            odoo_product_variant = odoo_product_variant.create(vals)
            if attribute_line_data:
                odoo_product_variant.product_tmpl_id.write({"attribute_line_ids": attribute_line_data})
        return odoo_product_variant

    def create_or_update_prestashop_product_listing(self, product_listing_vals, prestashop_product_listing,
                                                    odoo_product_variant=False, odoo_product_template=False,
                                                    product_data=False):
        """
        Create new or update existing Prestashop template in Odoo.
        @param: product_listing_vals, prestashop_product_listing, odoo_product_variant
        @return: prestashop_product_listing
        DG
        """
        vals = {
            "prestashop_instance_id": product_listing_vals.get("prestashop_instance_id"),
            "name": product_listing_vals.get("template_title"),
            "prestashop_product_id": product_listing_vals.get("prestashop_tmpl_id"),
            "product_catg_id": product_listing_vals.get("prestashop_product_category"),
            "prestashop_category_ids": product_listing_vals.get('prestashop_category_ids'),
        }
        if self._context.get('without_variant', False):
            stock_available_data = product_data.get('associations').get('stock_availables')
            if len(stock_available_data) == 1:
                vals['inventory_item_id'] = stock_available_data[0].get('id')
        if prestashop_product_listing:
            prestashop_product_listing.write(vals)
        else:
            product_tmpl_id = odoo_product_variant.product_tmpl_id.id if odoo_product_variant else (
                odoo_product_template.id if odoo_product_template else None
            )
            vals.update({"product_tmpl_id": product_tmpl_id})
            prestashop_product_listing = self.create(vals)
        return prestashop_product_listing

    def create_or_update_prestashop_product_listing_item(self, product_listing_item_vals, prestashop_product_listing_item,
                                                      prestashop_product_listing=False, odoo_product_variant=False):
        """
        Create a new prestashop variant into Odoo or update an existing one.
        DG
        """
        prestashop_product_listing_item_obj = self.env["prestashop.product.listing.item"]
        if not prestashop_product_listing_item and prestashop_product_listing and odoo_product_variant:
            product_listing_item_vals.update({"name": odoo_product_variant.name,
                                              "product_id": odoo_product_variant.id,
                                              "prestashop_product_listing_id": prestashop_product_listing.id})
            prestashop_product_listing_item = prestashop_product_listing_item_obj.create(product_listing_item_vals)
            if not odoo_product_variant.default_code:
                odoo_product_variant.default_code = prestashop_product_listing_item.product_sku
        elif prestashop_product_listing_item:
            prestashop_product_listing_item.write(product_listing_item_vals)
        return prestashop_product_listing_item

    def prepare_product_listing_item_vals(self, instance, prestashop_variant_data, product_data):
        """
        Prepare Prestashop product listing item values.
        DG
        """
        stock_available_data = product_data.get('associations').get('stock_availables')
        stock_available_id = next((item['id'] for item in stock_available_data if
                                   item['id_product_attribute'] == str(prestashop_variant_data.get("id"))), None)
        product_listing_item_vals = {
            "exported_in_prestashop": True,
            "active": True,
            "prestashop_instance_id": instance.id,
            "prestashop_product_variant_id": prestashop_variant_data.get("id"),
            "combination_price": prestashop_variant_data.get("price"),
            "combination_quantity": prestashop_variant_data.get("quantity"),
            "combination_weight": prestashop_variant_data.get("weight"),
            "product_sku": prestashop_variant_data.get("reference", ""),
        }
        if stock_available_id:
            product_listing_item_vals['inventory_item_id'] = stock_available_id
        return product_listing_item_vals

    def prepare_prestashop_product_listing_vals(self, product_data, instance, product_category, product_categories):
        """
        This method is designed for crafting values for a Prestashop product listing.
        DG
        """
        product_listing_vals = {
            "prestashop_instance_id": instance.id,
            "template_title": product_data.get("name"),
            "prestashop_tmpl_id": product_data.get("id"),
            "prestashop_product_category": product_category.id if product_category else False,
            "prestashop_category_ids": [(6, 0, product_categories.ids or [])],
        }

        return product_listing_vals

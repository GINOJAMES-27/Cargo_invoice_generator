from odoo import models, fields, api
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
import re
import base64


class CargoShippoRate(models.Model):
    _name = 'cargo.shippo.rate'
    _description = 'Shippo Shipping Rate Option'
    
    invoice_id = fields.Many2one('cargo.manual.invoice', string='Invoice', ondelete='cascade')
    object_id = fields.Char(string='Rate ID')
    provider = fields.Char(string='Carrier')
    servicelevel_name = fields.Char(string='Service Level')
    amount = fields.Float(string='Amount')
    currency = fields.Char(string='Currency')
    estimated_days = fields.Integer(string='Est. Days')
    
    def action_select_rate(self):
        for rate in self:
            rate.invoice_id.write({
                'shippo_rate_estimate': rate.amount,
                'shippo_rate_currency': rate.currency,
                'shippo_est_delivery': str(rate.estimated_days),
                'shippo_carrier_used': rate.provider,
                'shippo_service_used': rate.servicelevel_name,
                'shippo_transaction_id': rate.object_id,
                'carrier': rate.provider,
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Rate Selected',
                    'message': f"Selected {rate.provider} for {rate.amount} {rate.currency}",
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }


class CargoManualInvoice(models.Model):
    _name = 'cargo.manual.invoice'
    _description = 'Cargo Manual Invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'invoice_number'

    # ── System & Metadata ──────────────────────────────────────────────
    invoice_number = fields.Char(
        string='Invoice Number',
        readonly=True,
        copy=False,
        default='New',
        tracking=True,
    )
    shipping_date = fields.Datetime(
        string='Shipping Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    shipment_type = fields.Selection(
        [('domestic', 'Domestic'), ('international', 'International')],
        string='Shipment Type',
        default='international',
        required=True,
        tracking=True,
    )
    agent_name = fields.Char(
        string='User',
        default=lambda self: self.env.user.name,
        readonly=True,
    )
    email_sent = fields.Boolean(
        string='Email Sent',
        default=False,
        copy=False,
    )

    # ── Shipper Info ───────────────────────────────────────────────────
    origin = fields.Char(string='Origin', default='Saudi Arabia Riyadh', required=True)
    shipper_name = fields.Char(string='Shipper Name', required=True)
    shipper_mobile = fields.Char(string='Mobile', required=True)
    shipper_tel = fields.Char(string='Tel')
    shipper_id_no = fields.Char(string='ID No')
    shipper_company = fields.Char(string='Company')
    shipper_email = fields.Char(string='Email ID')
    shipper_address = fields.Char(string='Address', required=True)

    # ── Receiver Info ──────────────────────────────────────────────────
    destination = fields.Char(string='Old Destination', required=False, help="Deprecated field")
    destination_country_id = fields.Many2one('res.country', string='Destination Country', required=True)
    receiver_city = fields.Char(string='City', required=True)
    receiver_zip = fields.Char(string='ZIP / Postal Code', required=True)
    receiver_name = fields.Char(string='Receiver Name', required=True)
    receiver_mobile = fields.Char(string='Mobile', required=True)
    receiver_tel = fields.Char(string='Tel')
    receiver_company = fields.Char(string='Company')
    receiver_email = fields.Char(string='Email ID')
    receiver_address = fields.Char(string='Address', required=True)

    # ── Cargo Details ──────────────────────────────────────────────────
    weight = fields.Float(string='Weight', required=True)
    pieces = fields.Integer(string='Pieces', required=True, default=1)
    carrier = fields.Char(string='Carrier', required=True)
    airway_bill = fields.Char(string='Airway Bill')
    product_info = fields.Text(string='Product Info', required=True)
    special_info = fields.Text(string='Special Info')
    paymode = fields.Selection(
        [('cash', 'Cash'), ('card', 'Card'), ('company', 'Company')],
        string='Paymode',
        default='cash',
        required=True,
    )
    status = fields.Char(string='Status', default='ORDER PLACED', required=True, tracking=True)

    # ── Financials ─────────────────────────────────────────────────────
    net_amount = fields.Float(string='Net Amount', required=True)
    vat_amount = fields.Float(string='VAT 15%')
    extra_charge = fields.Float(string='Extra Charge')
    gross_total = fields.Float(
        string='Gross Total',
        compute='_compute_gross_total',
        store=True,
        tracking=True,
    )

    @api.depends('net_amount', 'vat_amount', 'extra_charge')
    def _compute_gross_total(self):
        for rec in self:
            rec.gross_total = rec.net_amount + rec.vat_amount + rec.extra_charge

    @api.onchange('shipment_type', 'net_amount')
    def _onchange_compute_vat(self):
        if self.shipment_type == 'domestic':
            self.vat_amount = round(self.net_amount * 0.15, 2)
        else:
            self.vat_amount = 0.0

    @api.constrains('shipper_mobile')
    def _check_shipper_mobile(self):
        for rec in self:
            if rec.shipper_mobile and not re.match(r'^[\d\s\+\-()]{7,20}$', rec.shipper_mobile):
                raise ValidationError('Shipper Mobile: Enter a valid phone number (7-20 digits).')

    @api.constrains('receiver_mobile')
    def _check_receiver_mobile(self):
        for rec in self:
            if rec.receiver_mobile and not re.match(r'^[\d\s\+\-()]{7,20}$', rec.receiver_mobile):
                raise ValidationError('Receiver Mobile: Enter a valid phone number (7-20 digits).')

    @api.constrains('shipper_email')
    def _check_shipper_email(self):
        for rec in self:
            if rec.shipper_email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', rec.shipper_email):
                raise ValidationError('Shipper Email: Enter a valid email address.')

    @api.constrains('receiver_email')
    def _check_receiver_email(self):
        for rec in self:
            if rec.receiver_email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', rec.receiver_email):
                raise ValidationError('Receiver Email: Enter a valid email address.')

    @api.constrains('net_amount')
    def _check_net_amount(self):
        for rec in self:
            if rec.net_amount < 0:
                raise ValidationError('Net Amount cannot be negative.')

    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight <= 0:
                raise ValidationError('Weight must be greater than zero.')

    @api.constrains('pieces')
    def _check_pieces(self):
        for rec in self:
            if rec.pieces <= 0:
                raise ValidationError('Pieces must be at least 1.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('invoice_number', 'New') == 'New':
                vals['invoice_number'] = self.env['ir.sequence'].next_by_code(
                    'cargo.manual.invoice'
                ) or 'New'
        return super().create(vals_list)

    def action_print_invoice(self):
        return self.env.ref(
            'cargo_manual_invoicing.action_report_cargo_invoice'
        ).report_action(self)

    def _get_invoice_pdf(self):
        """Generate the invoice PDF and return as base64."""
        report = self.env.ref('cargo_manual_invoicing.action_report_cargo_invoice')
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            report, self.ids
        )
        return base64.b64encode(pdf_content)

    def action_send_email(self):
        """Send invoice PDF to both shipper and receiver emails."""
        self.ensure_one()

        # Collect recipient emails
        recipients = []
        if self.shipper_email:
            recipients.append(self.shipper_email)
        if self.receiver_email and self.receiver_email not in recipients:
            recipients.append(self.receiver_email)

        if not recipients:
            raise ValidationError(
                'No email addresses found!\n'
                'Please fill in Shipper Email or Receiver Email before sending.'
            )

        # Generate PDF attachment
        pdf_data = self._get_invoice_pdf()
        attachment = self.env['ir.attachment'].create({
            'name': '%s.pdf' % self.invoice_number.replace('/', '-'),
            'type': 'binary',
            'datas': pdf_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        # Build email body
        body_html = """
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; border: 1px solid #ddd;">
            <div style="background: #000; color: #fff; padding: 20px; text-align: center;">
                <h2 style="margin: 0; font-size: 18px;">BRIGHTNESS OF HOPE AIR CARGO EST</h2>
                <p style="margin: 5px 0 0; font-size: 15px;">مؤسسة سطوع الأمل للشحن الجوي</p>
                <p style="margin: 8px 0 0; font-size: 11px; color: #aaa;">CR: 1010791259 | VAT: 311239685900003</p>
            </div>
            <div style="background: #f5f5f5; padding: 15px 20px; border-bottom: 1px solid #ddd;">
                <h3 style="margin: 0; color: #111;">Invoice: %s</h3>
                <p style="margin: 5px 0 0; color: #555; font-size: 13px;">
                    Date: %s | Type: %s
                </p>
            </div>
            <div style="padding: 20px;">
                <table style="width: 100%%; border-collapse: collapse;">
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; width: 30%%;">From (Shipper)</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s<br/><span style="color: #666; font-size: 12px;">%s</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">To (Receiver)</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s<br/><span style="color: #666; font-size: 12px;">%s</span></td>
                    </tr>
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Carrier</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Airway Bill</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s</td>
                    </tr>
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Weight / Pieces</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s kg / %s pcs</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Product</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">%s</td>
                    </tr>
                </table>
                <table style="width: 100%%; border-collapse: collapse; margin-top: 15px;">
                    <tr>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; color: #555;">Net Amount</td>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; text-align: right; font-weight: 600;">%.2f SAR</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; color: #555;">VAT 15%%</td>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; text-align: right; font-weight: 600;">%.2f SAR</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; color: #555;">Extra Charge</td>
                        <td style="padding: 8px 10px; border: 1px solid #ddd; text-align: right; font-weight: 600;">%.2f SAR</td>
                    </tr>
                </table>
                <div style="background: #000; color: #fff; padding: 15px; text-align: center; margin-top: -1px; font-size: 20px; font-weight: 800;">
                    GROSS TOTAL: %.2f SAR
                </div>
                <p style="margin-top: 15px; color: #555; font-size: 12px; line-height: 1.6;">
                    Please find the full invoice attached as a PDF document.<br/>
                    For any queries, contact us at: <strong>0574436896 / 0573370566</strong>
                </p>
            </div>
            <div style="background: #222; color: #999; padding: 12px 20px; text-align: center; font-size: 10px; line-height: 1.6;">
                Brightness of Hope Air Cargo Est<br/>
                Riyadh-Al Aziziyah, Abu Saad Al-Wazir Street, Saudi Arabia
            </div>
        </div>
        """ % (
            self.invoice_number or '',
            self.shipping_date or '',
            (self.shipment_type or '').upper(),
            self.shipper_name or '',
            self.origin or '',
            self.receiver_name or '',
            self.destination or '',
            self.carrier or '-',
            self.airway_bill or '-',
            self.weight,
            self.pieces,
            self.product_info or '-',
            self.net_amount,
            self.vat_amount,
            self.extra_charge,
            self.gross_total,
        )

        # Send to each recipient
        mail_values = {
            'subject': 'Cargo Invoice %s — Brightness of Hope Air Cargo' % self.invoice_number,
            'body_html': body_html,
            'email_from': self.env.user.email_formatted or self.env.company.email,
            'attachment_ids': [(4, attachment.id)],
        }

        for email_addr in recipients:
            mail = self.env['mail.mail'].sudo().create(dict(
                mail_values,
                email_to=email_addr,
            ))
            mail.send()

        # Mark as sent and log in chatter
        self.email_sent = True
        self.message_post(
            body='Invoice emailed to: %s' % ', '.join(recipients),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Email Sent Successfully!',
                'message': 'Invoice %s sent to: %s' % (
                    self.invoice_number, ', '.join(recipients)
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    # ── Shippo Integration Fields ──────────────────────────────────────
    shippo_rate_ids = fields.One2many('cargo.shippo.rate', 'invoice_id', string='Available Rates')
    shippo_sent = fields.Boolean(string="Shipped via Shippo", default=False, copy=False)
    shippo_shipment_id = fields.Char(string="Shippo Shipment ID", copy=False)
    shippo_transaction_id = fields.Char(string="Shippo Transaction ID", copy=False)
    shippo_rate_estimate = fields.Float(string="Estimated Shipping Cost", copy=False)
    shippo_rate_currency = fields.Char(string="Currency", copy=False)
    shippo_est_delivery = fields.Char(string="Est. Delivery Days", copy=False)
    shippo_tracking_status = fields.Char(string="Tracking Status", default='Not Created', copy=False, tracking=True)
    shippo_tracking_url = fields.Char(string="Tracking URL", copy=False)
    shippo_label_url = fields.Char(string="Label URL", copy=False)
    shippo_carrier_used = fields.Char(string="Carrier Used", copy=False)
    shippo_service_used = fields.Char(string="Service Level Used", copy=False)
    shippo_label = fields.Binary(string="Shipping Label", copy=False, attachment=True)

    def action_get_shippo_rates(self):
        self.ensure_one()
        try:
            service = self.env['shippo.integration.service']
            shipment = service.create_shipment(self)
            
            self.shippo_shipment_id = shipment.object_id
            
            # Clear existing rates
            self.shippo_rate_ids.unlink()
            
            # Find the best rate from our default carrier
            default_carrier = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.shippo_default_carrier', 'dhl_express')
            default_service = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.shippo_default_servicelevel', 'dhl_express_worldwide')
            
            best_rate = None
            rate_vals_list = []
            
            for rate in shipment.rates:
                rate_vals = {
                    'invoice_id': self.id,
                    'object_id': rate.object_id,
                    'provider': rate.provider,
                    'servicelevel_name': rate.servicelevel.name,
                    'amount': float(rate.amount),
                    'currency': rate.currency,
                    'estimated_days': getattr(rate, 'estimated_days', 0) or 0,
                }
                rate_vals_list.append(rate_vals)
                
                if rate.provider == default_carrier and rate.servicelevel.token == default_service:
                    best_rate = rate
                    
            if rate_vals_list:
                self.env['cargo.shippo.rate'].create(rate_vals_list)
            
            if not best_rate and shipment.rates:
                # Fallback to cheapest rate if default isn't found
                best_rate = min(shipment.rates, key=lambda r: float(r.amount))
                
            if not best_rate:
                # pyrefly: ignore [missing-import]
                from odoo.exceptions import UserError
                raise UserError("No rates returned by Shippo for this route.")

            self.shippo_rate_estimate = float(best_rate.amount)
            self.shippo_rate_currency = best_rate.currency
            self.shippo_est_delivery = best_rate.estimated_days or 'Unknown'
            self.shippo_carrier_used = best_rate.provider
            self.shippo_service_used = best_rate.servicelevel.name
            
            # Save the rate object_id in transaction_id temporarily until we buy it
            self.shippo_transaction_id = best_rate.object_id
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Rates Retrieved',
                    'message': f"Estimated cost: {best_rate.amount} {best_rate.currency} via {best_rate.provider}",
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        except Exception as e:
            # pyrefly: ignore [missing-import]
            from odoo.exceptions import UserError
            raise UserError(str(e))

    def action_buy_shippo_label(self):
        self.ensure_one()
        if not self.shippo_transaction_id:
            # pyrefly: ignore [missing-import]
            from odoo.exceptions import UserError
            raise UserError("Please Get Rates first before buying a label.")

        try:
            service = self.env['shippo.integration.service']
            transaction = service.buy_label(self.shippo_transaction_id)
            
            if transaction.status == 'SUCCESS':
                self.shippo_sent = True
                self.shippo_transaction_id = transaction.object_id
                self.shippo_label_url = transaction.label_url
                self.shippo_tracking_url = transaction.tracking_url_provider
                self.airway_bill = transaction.tracking_number
                self.shippo_tracking_status = 'PRE_TRANSIT'
                self.status = 'SHIPPED'
                
                # Download label
                import requests
                import base64
                response = requests.get(transaction.label_url)
                if response.status_code == 200:
                    self.shippo_label = base64.b64encode(response.content)
            else:
                # pyrefly: ignore [missing-import]
                from odoo.exceptions import UserError
                
                carrier_errors = []
                if hasattr(transaction, 'messages') and transaction.messages:
                    for m in transaction.messages:
                        if isinstance(m, dict) and 'text' in m:
                            carrier_errors.append(m['text'])
                        elif hasattr(m, 'text'):
                            carrier_errors.append(m.text)
                            
                if carrier_errors:
                    msg = "\n".join(carrier_errors)
                else:
                    msg = f"Raw Response:\n{str(transaction)}"
                    
                raise UserError(f"Label purchase failed:\n{msg}")

        except Exception as e:
            # pyrefly: ignore [missing-import]
            from odoo.exceptions import UserError
            raise UserError(str(e))

    def action_track_shippo(self):
        self.ensure_one()
        if not self.airway_bill or not self.shippo_carrier_used:
            return

        try:
            service = self.env['shippo.integration.service']
            status = service.track_shipment(self.shippo_carrier_used, self.airway_bill)
            
            if status and status.tracking_status:
                self.shippo_tracking_status = status.tracking_status.status
                if self.shippo_tracking_status == 'DELIVERED':
                    self.status = 'DELIVERED'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Tracking Updated',
                        'message': f"Current Status: {self.shippo_tracking_status}",
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            pass

    def action_download_label(self):
        self.ensure_one()
        if self.shippo_label_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.shippo_label_url,
                'target': 'new',
            }

    @api.model
    def _cron_update_shippo_tracking(self):
        shipments = self.search([
            ('shippo_sent', '=', True),
            ('shippo_tracking_status', 'not in', ['DELIVERED', 'RETURNED', 'FAILURE'])
        ])
        for shipment in shipments:
            shipment.action_track_shippo()
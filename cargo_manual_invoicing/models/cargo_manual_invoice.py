from odoo import models, fields, api
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
import re
import base64
import logging
import io
import urllib.parse
import uuid

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:
    qrcode = None
    _logger.warning("The 'qrcode' library is not installed. ZATCA QR codes will not be generated.")

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
    access_token = fields.Char(
        string='Security Token',
        copy=False,
        default=lambda self: str(uuid.uuid4())
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
    delivery_partner = fields.Selection([
        ('dhl', 'DHL'),
        ('fedex', 'FedEx'),
        ('aramex', 'Aramex'),
        ('ups', 'UPS'),
        ('manual', 'Manual (Other)')
    ], string='Delivery Partner', required=True, default='dhl')
    manual_delivery_partner = fields.Char(string='Manual Delivery Partner')
    carrier = fields.Char(string='Carrier', compute='_compute_carrier', store=True)

    @api.depends('delivery_partner', 'manual_delivery_partner')
    def _compute_carrier(self):
        for rec in self:
            if rec.delivery_partner == 'manual':
                rec.carrier = rec.manual_delivery_partner or ''
            elif rec.delivery_partner:
                rec.carrier = dict(self._fields['delivery_partner'].selection).get(rec.delivery_partner, '')
            else:
                rec.carrier = ''
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

    # ── ZATCA QR Code ──────────────────────────────────────────────────
    zatca_qr_image = fields.Binary(
        string='ZATCA QR Code',
        compute='_compute_zatca_qr_image',
    )

    @api.depends('invoice_number', 'shipping_date', 'gross_total', 'vat_amount')
    def _compute_zatca_qr_image(self):
        if not qrcode:
            for rec in self:
                rec.zatca_qr_image = False
            return

        for rec in self:
            if not rec.invoice_number or rec.invoice_number == 'New':
                rec.zatca_qr_image = False
                continue

            seller_name = "Brightness of Hope Air Cargo Est"
            vat_number = "311239685900003"
            # Format to ISO 8601 (Odoo stores datetime as UTC natively)
            timestamp = rec.shipping_date.isoformat() + "Z" if rec.shipping_date else ""
            total = "%.2f" % (rec.gross_total or 0.0)
            vat = "%.2f" % (rec.vat_amount or 0.0)

            def get_tlv(tag, value):
                value_bytes = value.encode('utf-8')
                return bytes([tag, len(value_bytes)]) + value_bytes

            tlv_data = b""
            tlv_data += get_tlv(1, seller_name)
            tlv_data += get_tlv(2, vat_number)
            tlv_data += get_tlv(3, timestamp)
            tlv_data += get_tlv(4, total)
            tlv_data += get_tlv(5, vat)

            b64_string = base64.b64encode(tlv_data).decode('utf-8')

            try:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=2,
                    border=1,
                )
                qr.add_data(b64_string)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                buffer = io.BytesIO()
                try:
                    img.save(buffer, format="PNG")  # type: ignore
                except TypeError:
                    # PyPNGImage does not accept 'format' keyword argument
                    img.save(buffer)
                rec.zatca_qr_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            except Exception as e:
                _logger.error("Failed to generate ZATCA QR code: %s", str(e))
                rec.zatca_qr_image = False

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

    def action_send_whatsapp(self):
        self.ensure_one()
        if not self.receiver_mobile:
            raise ValidationError("Receiver Mobile number is required to send a WhatsApp message.")
            
        # Clean the phone number (remove spaces, plus, dashes)
        phone = re.sub(r'[^0-9]', '', self.receiver_mobile)
        if not phone:
            raise ValidationError("Invalid Receiver Mobile number.")

        # Generate base URL for the public PDF link
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if not self.access_token:
            self.access_token = str(uuid.uuid4())
            
        pdf_link = f"{base_url}/cargo/invoice/pdf/{self.id}/{self.access_token}"
        
        # Build message
        message = (
            f"Hello {self.receiver_name},\n\n"
            f"Your cargo invoice {self.invoice_number} has been generated.\n"
            f"Gross Total: {self.gross_total} SAR\n"
        )
        if self.airway_bill:
            message += f"Tracking / Airway Bill: {self.airway_bill}\n"
            
        message += f"\nYou can view and download your PDF invoice here: {pdf_link}"
        
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }


from odoo import models, fields, api
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError, UserError
import re
import base64
import logging
import io

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:
    qrcode = None
    _logger.warning("The 'qrcode' library is not installed. ZATCA QR codes will not be generated.")


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

    # ── ZATCA Configuration ────────────────────────────────────────────
    zatca_invoice_hash = fields.Char(string='ZATCA Invoice Hash', readonly=True, help="SHA-256 hash of the generated ZATCA XML.")
    zatca_previous_hash = fields.Char(string='Previous Invoice Hash (PIH)', readonly=True, help="Hash of the previous invoice in the sequence.")
    zatca_signed_xml = fields.Text(string='Signed ZATCA XML', readonly=True, help="The final, signed UBL 2.1 XML ready for submission.")

    zatca_qr_image = fields.Binary(
        string='ZATCA QR Code',
        help='ZATCA Phase 2 Enhanced QR Code',
    )
    
    zatca_status = fields.Selection([
        ('pending', 'Pending'),
        ('reported', 'Reported'),
        ('cleared', 'Cleared'),
        ('failed', 'Failed')
    ], string='ZATCA Status', default='pending', readonly=True, tracking=True)
    zatca_response_msgs = fields.Text(string='ZATCA Response Messages', readonly=True)

    def _generate_zatca_phase2_qr(self):
        """Generates Phase 2 ZATCA QR Code containing 9 TLV tags."""
        self.ensure_one()
        # pyrefly: ignore [missing-import]
        try:
            import qrcode
            import io
            import base64
        except ImportError:
            qrcode = None

        if not qrcode:
            self.zatca_qr_image = False
            return

        try:
            # The Seller Name in the QR MUST MATCH EXACTLY what is in the XML <cbc:RegistrationName>!
            seller_name = "Brightness of Hope Air Cargo Est"
            vat_number = "311239685900003"
            
            # Fallbacks
            timestamp = self.shipping_date.strftime('%Y-%m-%dT%H:%M:%SZ') if self.shipping_date else ""
            total = "%.2f" % (self.gross_total or 0.0)
            vat = "%.2f" % (self.vat_amount or 0.0)

            def get_tlv(tag, value_bytes):
                return bytes([tag, len(value_bytes)]) + value_bytes

            csid_cert = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_api_key')
            
            phase2_tags = b""
            # Check if we have Phase 2 requirements
            if self.zatca_signed_xml and self.zatca_invoice_hash and csid_cert:
                try:
                    # pyrefly: ignore [missing-import]
                    from lxml import etree
                    root = etree.fromstring(self.zatca_signed_xml.encode('utf-8'))
                    
                    # Tag 3: Extract EXACT IssueDate and IssueTime from XML
                    issue_date_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueDate')
                    issue_time_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueTime')
                    if issue_date_elem is not None and issue_time_elem is not None:
                        # ZATCA XML contains KSA Time (UTC+3) but QR Code Tag 3 MUST be UTC (Zulu)
                        # pyrefly: ignore [missing-import]
                        from datetime import datetime, timedelta
                        xml_time_str = f"{issue_date_elem.text.strip()}T{issue_time_elem.text.strip()}"
                        try:
                            # Parse KSA time, subtract 3 hours for UTC, and format with Z
                            ksa_dt = datetime.strptime(xml_time_str, '%Y-%m-%dT%H:%M:%S')
                            utc_dt = ksa_dt - timedelta(hours=3)
                            timestamp = utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                        except Exception:
                            timestamp = xml_time_str + 'Z'
                            
                    # Tag 6: XML Hash MUST BE EXTRACTED FROM DigestValue
                    digest_elem = root.find('.//ds:DigestValue', namespaces={'ds': 'http://www.w3.org/2000/09/xmldsig#'})
                    if digest_elem is not None and digest_elem.text:
                        hash_bytes = digest_elem.text.strip().encode('utf-8')
                    else:
                        hash_bytes = self.zatca_invoice_hash.strip().encode('utf-8')
                    phase2_tags += get_tlv(6, hash_bytes)

                    # Tag 7: ECDSA Signature MUST BE EXTRACTED FROM SignatureValue
                    sig_val_elem = root.find('.//ds:SignatureValue', namespaces={'ds': 'http://www.w3.org/2000/09/xmldsig#'})
                    if sig_val_elem is not None and sig_val_elem.text:
                        sig_bytes = sig_val_elem.text.strip().encode('utf-8')
                        phase2_tags += get_tlv(7, sig_bytes)
                    else:
                        raise ValueError("SignatureValue not found in XML")

                    # Tag 8 & 9: Extract certificate from the SIGNED XML itself
                    cert_elem = root.find('.//ds:X509Certificate', namespaces={'ds': 'http://www.w3.org/2000/09/xmldsig#'})
                    if cert_elem is not None and cert_elem.text:
                        cert_b64 = cert_elem.text.strip()
                        
                        first_decode = base64.b64decode(cert_b64)
                        # pyrefly: ignore [missing-import]
                        from cryptography.hazmat.backends import default_backend
                        # pyrefly: ignore [missing-import]
                        from cryptography.hazmat.primitives import serialization
                        # pyrefly: ignore [missing-import]
                        from cryptography import x509
                        try:
                            cert = x509.load_der_x509_certificate(first_decode, default_backend())
                        except Exception:
                            second_decode = base64.b64decode(first_decode)
                            cert = x509.load_der_x509_certificate(second_decode, default_backend())
                        
                        pub_key_bytes = cert.public_key().public_bytes(
                            encoding=serialization.Encoding.DER,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo
                        )
                        phase2_tags += get_tlv(8, pub_key_bytes)
                        phase2_tags += get_tlv(9, cert.signature)
                    else:
                        raise ValueError("X509Certificate not found in signed XML")

                    _logger.info("ZATCA Phase 2 QR generated successfully for %s", self.invoice_number)
                except Exception as e:
                    _logger.error("Phase 2 QR generation failed, falling back to Phase 1: %s", str(e))
            else:
                _logger.warning("Missing Phase 2 requirements (XML/Hash/CSID), falling back to Phase 1 QR")

            # Assemble all tags in exact order 1-9
            tlv_data = b""
            tlv_data += get_tlv(1, seller_name.encode('utf-8'))
            tlv_data += get_tlv(2, vat_number.encode('utf-8'))
            tlv_data += get_tlv(3, timestamp.encode('utf-8'))
            tlv_data += get_tlv(4, total.encode('utf-8'))
            tlv_data += get_tlv(5, vat.encode('utf-8'))
            tlv_data += phase2_tags

            b64_string = base64.b64encode(tlv_data).decode('utf-8')
            _logger.info("ZATCA Phase 2 QR - Total TLV Length: %d bytes -> Base64: %d chars", len(tlv_data), len(b64_string))
            
            # [BR-KSA-27] Inject the Base64 QR Code into the Signed XML
            if self.zatca_signed_xml:
                try:
                    # Safely inject the QR code using string replacement to avoid ANY XML canonicalization changes
                    # that could invalidate the Digital Signature or the Invoice Hash.
                    if ">PLACEHOLDER<" in self.zatca_signed_xml:
                        self.zatca_signed_xml = self.zatca_signed_xml.replace(">PLACEHOLDER<", f">{b64_string}<")
                        _logger.info("Successfully replaced QR Code PLACEHOLDER in the Signed XML")
                    else:
                        _logger.warning("QR PLACEHOLDER not found in Signed XML!")
                except Exception as e:
                    _logger.error("Failed to inject QR Code into XML: %s", str(e))

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
                try:
                    img.save(buffer, format="PNG")  # type: ignore
                except TypeError:
                    img.save(buffer)
                self.zatca_qr_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            except Exception as e:
                _logger.warning("Could not save QR code image to database due to error: %s", str(e))
                self.zatca_qr_image = False

        except Exception as e:
            _logger.error("Failed to generate ZATCA QR code: %s", str(e))
            self.zatca_qr_image = False

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
            
            # ── ZATCA Hash Chaining (PIH) ──
            # Look up the most recent invoice by ID
            last_invoice = self.search([], order='id desc', limit=1)
            if last_invoice and last_invoice.zatca_invoice_hash:
                vals['zatca_previous_hash'] = last_invoice.zatca_invoice_hash
            else:
                # First invoice base hash
                vals['zatca_previous_hash'] = 'NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=='
                
        records = super().create(vals_list)
        
        # Now that records are created and have their IDs, generate the ZATCA XML and store the hash
        for rec in records:
            # We will implement ZatcaXmlBuilder next, which will return the base64 hash
            try:
                # Need to use sudo() to access settings. res.config.settings is transient.
                settings = self.env['res.config.settings'].sudo().create({})
                
                # Phase C: Generate XML and Hash
                invoice_root, invoice_hash = self.env['zatca.xml.builder'].generate_and_hash_invoice(rec, settings)
                if invoice_hash:
                    rec.zatca_invoice_hash = invoice_hash
                    
                    # Phase D: Sign the XML
                    signed_xml_string = self.env['zatca.signing.service'].sign_xml(invoice_root, settings, invoice_hash)
                    if signed_xml_string:
                        rec.zatca_signed_xml = signed_xml_string
                        
                        # Phase E: Generate Phase 2 QR Code
                        rec._generate_zatca_phase2_qr()

            except Exception as e:
                _logger.error("Failed to generate ZATCA XML Hash during creation: %s", str(e))
                # For this prototype we won't block creation, but in real ZATCA you might
                pass
                
        return records

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

    def action_send_zatca(self):
        """Generates XML, signs it, builds QR, and sends to ZATCA Compliance/Reporting API."""
        self.ensure_one()
        # pyrefly: ignore [missing-import]
        try:
            import requests
            import base64
            import json
            # pyrefly: ignore [missing-import]
            from lxml import etree
        except ImportError:
            raise UserError("Missing required python packages: requests, base64, json, lxml.")

        settings = self.env['res.config.settings'].sudo().create({})
        
        # 1. Generate XML and Hash
        if not self.zatca_invoice_hash or not self.zatca_signed_xml:
            invoice_root, invoice_hash_b64 = self.env['zatca.xml.builder'].sudo().generate_and_hash_invoice(self, settings)
            if not invoice_hash_b64:
                raise UserError("Failed to generate XML Hash.")
            
            # 2. Sign XML
            signed_xml_str = self.env['zatca.signing.service'].sudo().sign_xml(invoice_root, settings, invoice_hash_b64)
            if not signed_xml_str:
                raise UserError("Failed to sign XML.")
            
            self.zatca_invoice_hash = invoice_hash_b64
            self.zatca_signed_xml = signed_xml_str

        # 3. Generate QR Code directly into the signed XML
        try:
            self._generate_zatca_phase2_qr()
        except Exception as e:
            _logger.warning("QR generation error ignored for DB save: %s", str(e))
            
        if not self.zatca_signed_xml or ">PLACEHOLDER<" in self.zatca_signed_xml:
            raise UserError("QR Code generation failed. Signed XML is incomplete.")

        # Extract UUID
        qr_xml_str = self.zatca_signed_xml
        root = etree.fromstring(qr_xml_str.encode('utf-8'))
        uuid_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}UUID')
        uuid_val = uuid_elem.text if uuid_elem is not None else '00000000-0000-0000-0000-000000000000'

        # Build payload
        payload = {
            'invoiceHash': self.zatca_invoice_hash,
            'uuid': uuid_val,
            'invoice': base64.b64encode(qr_xml_str.encode('utf-8')).decode('utf-8')
        }

        # Setup API Request
        base_url = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_sandbox_url') or "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal"
        base_url = base_url.rstrip('/')
        
        if 'developer-portal' in base_url:
            url = base_url + '/compliance/invoices'
        else:
            # We generate Simplified Invoices (0200000), so we must use the Reporting endpoint
            url = base_url + '/invoices/reporting/single'
        
        csid = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_api_key')
        secret = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_api_secret')
        if not csid or not secret:
            raise UserError("ZATCA API Key (CSID) or Secret is missing in settings.")

        auth_str = f"{csid.strip()}:{secret.strip()}"
        auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

        headers = {
            'Accept-Version': 'V2',
            'Accept-Language': 'en',
            'Clearance-Status': '0',  # 0 for Simplified Invoices, 1 for Standard
            'Content-Type': 'application/json',
            'Authorization': f'Basic {auth_b64}'
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            resp_data = response.json()
            
            # Parse Status
            reporting_status = resp_data.get('reportingStatus', '')
            clearance_status = resp_data.get('clearanceStatus', '')
            val_results = resp_data.get('validationResults', {})
            val_status = val_results.get('status', '')
            
            # Determine overall status
            if reporting_status == 'REPORTED' or clearance_status == 'CLEARED' or val_status == 'PASS':
                self.zatca_status = 'reported' if reporting_status == 'REPORTED' else 'cleared'
            else:
                self.zatca_status = 'failed'
                
            # Formatting Response Messages
            msgs = []
            if val_results.get('errorMessages'):
                msgs.append("ERRORS:\n" + "\n".join([f"- {m.get('code')}: {m.get('message')}" for m in val_results['errorMessages']]))
            if val_results.get('warningMessages'):
                msgs.append("WARNINGS:\n" + "\n".join([f"- {m.get('code')}: {m.get('message')}" for m in val_results['warningMessages']]))
            if val_results.get('infoMessages'):
                msgs.append("INFO:\n" + "\n".join([f"- {m.get('code')}: {m.get('message')}" for m in val_results['infoMessages']]))
                
            self.zatca_response_msgs = "\n\n".join(msgs) if msgs else json.dumps(resp_data, indent=2)
            
            if response.status_code not in (200, 202):
                _logger.error("ZATCA Submission Failed: HTTP %s - %s", response.status_code, response.text)
                
        except Exception as e:
            self.zatca_status = 'failed'
            self.zatca_response_msgs = f"Network or Parsing Error:\n{str(e)}"
import base64
import hashlib
from datetime import datetime
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

try:
    # pyrefly: ignore [missing-import]
    from lxml import etree
except ImportError:
    etree = None

class ZatcaXmlBuilder(models.AbstractModel):
    _name = 'zatca.xml.builder'
    _description = 'ZATCA UBL 2.1 XML Builder'

    @api.model
    def generate_and_hash_invoice(self, invoice, settings):
        """Generates the UBL 2.1 XML and returns its SHA-256 Base64 hash."""
        if not etree:
            _logger.error("lxml library is not installed. Cannot generate ZATCA XML.")
            return False

        # Define Namespaces
        NSMAP = {
            None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            'cac': "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            'ext': "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
        }

        # Create Root Element
        invoice_root = etree.Element("Invoice", nsmap=NSMAP)

        # ProfileID & ID
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ProfileID").text = "reporting:1.0"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = invoice.invoice_number or "INV-0000"

        # UUID (ZATCA Requires a UUID, we can just hash the ID or generate one)
        # Odoo doesn't generate UUIDs natively per record by default, we'll hash the ID
        uuid_str = hashlib.md5((invoice.invoice_number or "123").encode()).hexdigest()
        uuid_format = f"{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}UUID").text = uuid_format

        # Dates
        issue_date = invoice.shipping_date.strftime('%Y-%m-%d') if invoice.shipping_date else datetime.now().strftime('%Y-%m-%d')
        issue_time = invoice.shipping_date.strftime('%H:%M:%S') if invoice.shipping_date else datetime.now().strftime('%H:%M:%S')
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueDate").text = issue_date
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueTime").text = issue_time

        # Invoice Type Code (0100000 for Standard, 388 is the UN/CEFACT code for Invoice)
        invoice_type_code = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoiceTypeCode", name="0100000")
        invoice_type_code.text = "388"
        
        # Document Currency
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}DocumentCurrencyCode").text = "SAR"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxCurrencyCode").text = "SAR"

        # Additional Document Reference (PIH)
        add_doc_ref = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AdditionalDocumentReference")
        etree.SubElement(add_doc_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "PIH"
        attach = etree.SubElement(add_doc_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Attachment")
        doc_desc = etree.SubElement(attach, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}EmbeddedDocumentBinaryObject", mimeCode="text/plain")
        doc_desc.text = invoice.zatca_previous_hash or "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

        # Accounting Supplier Party
        supplier_party = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AccountingSupplierParty")
        party = etree.SubElement(supplier_party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Party")
        
        party_tax_scheme = etree.SubElement(party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PartyTaxScheme")
        etree.SubElement(party_tax_scheme, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}CompanyID").text = settings.zatca_vat_number or "311239685900003"
        tax_scheme = etree.SubElement(party_tax_scheme, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
        etree.SubElement(tax_scheme, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "VAT"

        party_legal_entity = etree.SubElement(party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PartyLegalEntity")
        etree.SubElement(party_legal_entity, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}RegistrationName").text = settings.zatca_company_name or "Company Name"

        # Accounting Customer Party
        customer_party = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AccountingCustomerParty")
        c_party = etree.SubElement(customer_party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Party")
        c_party_name = etree.SubElement(c_party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PartyName")
        etree.SubElement(c_party_name, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Name").text = invoice.shipper_name or "Unknown Customer"

        # Tax Total
        tax_total = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal")
        tax_amt = etree.SubElement(tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR")
        tax_amt.text = f"{invoice.vat_amount:.2f}"

        # Legal Monetary Total
        legal_total = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}LegalMonetaryTotal")
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}LineExtensionAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExclusiveAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxInclusiveAmount", currencyID="SAR").text = f"{invoice.gross_total:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}AllowanceTotalAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ChargeTotalAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PrepaidAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PayableAmount", currencyID="SAR").text = f"{invoice.gross_total:.2f}"

        # Invoice Line
        inv_line = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine")
        etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "1"
        inv_qty = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoicedQuantity", unitCode="PCE")
        inv_qty.text = f"{float(invoice.pieces):.2f}"
        etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}LineExtensionAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"

        item = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Item")
        etree.SubElement(item, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Name").text = invoice.product_info or "Cargo Services"

        price = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Price")
        etree.SubElement(price, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PriceAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"

        # Generate XML String for hashing (raw UBL body before signatures)
        xml_string = etree.tostring(invoice_root, pretty_print=False, encoding='UTF-8', xml_declaration=True)

        # SHA-256 Hashing 
        hash_digest = hashlib.sha256(xml_string).digest()
        base64_hash = base64.b64encode(hash_digest).decode('utf-8')

        return invoice_root, base64_hash

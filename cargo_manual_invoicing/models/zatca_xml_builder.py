import base64
import hashlib
import copy
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

        # CustomizationID, ProfileID & ID (Must be exactly in this order for UBL 2.1)
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}CustomizationID").text = "KSAEN16931:UBL-2.1:core:ubl:2.1"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ProfileID").text = "reporting:1.0"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = invoice.invoice_number or "INV-0000"

        # UUID (ZATCA Requires a UUID, we can just hash the ID or generate one)
        # Odoo doesn't generate UUIDs natively per record by default, we'll hash the ID
        uuid_str = hashlib.md5((invoice.invoice_number or "123").encode()).hexdigest()
        uuid_format = f"{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}UUID").text = uuid_format

        # Dates: ZATCA expects the XML IssueDate/IssueTime to be in local KSA time (UTC+3)
        from datetime import timedelta
        base_date = invoice.shipping_date if invoice.shipping_date else datetime.now()
        ksa_date = base_date + timedelta(hours=3)
        
        issue_date = ksa_date.strftime('%Y-%m-%d')
        issue_time = ksa_date.strftime('%H:%M:%S')
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueDate").text = issue_date
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IssueTime").text = issue_time

        # Invoice Type Code (0200000 for Simplified B2C, 388 is the UN/CEFACT code for Invoice)
        invoice_type_code = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoiceTypeCode", name="0200000")
        invoice_type_code.text = "388"
        
        # Document Currency
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}DocumentCurrencyCode").text = "SAR"
        etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxCurrencyCode").text = "SAR"

        # Invoice Counter Value (ICV)
        icv_ref = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AdditionalDocumentReference")
        etree.SubElement(icv_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "ICV"
        etree.SubElement(icv_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}UUID").text = str(invoice.id or 1)

        # Additional Document Reference (PIH)
        add_doc_ref = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AdditionalDocumentReference")
        etree.SubElement(add_doc_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "PIH"
        attach = etree.SubElement(add_doc_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Attachment")
        doc_desc = etree.SubElement(attach, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}EmbeddedDocumentBinaryObject", mimeCode="text/plain")
        doc_desc.text = invoice.zatca_previous_hash or "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

        # QR Code Placeholder (must exist before Hashing)
        qr_ref = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AdditionalDocumentReference")
        etree.SubElement(qr_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "QR"
        qr_attach = etree.SubElement(qr_ref, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Attachment")
        qr_desc = etree.SubElement(qr_attach, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}EmbeddedDocumentBinaryObject", mimeCode="text/plain")
        qr_desc.text = "PLACEHOLDER"

        # Signature (BR-KSA-60) - Required for Hash Verification Pipeline
        signature = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Signature")
        etree.SubElement(signature, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "urn:oasis:names:specification:ubl:signature:Invoice"
        sig_method = etree.SubElement(signature, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}SignatureMethod")
        sig_method.text = "urn:oasis:names:specification:ubl:dsig:enveloped:xades"

        # Accounting Supplier Party
        supplier_party = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}AccountingSupplierParty")
        party = etree.SubElement(supplier_party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Party")
        
        # BR-KSA-08: Seller CRN
        party_identification = etree.SubElement(party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PartyIdentification")
        etree.SubElement(party_identification, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="CRN").text = "1010791259"
        
        # BR-08 & BR-KSA-37: Seller Postal Address
        postal_address = etree.SubElement(party, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PostalAddress")
        etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}StreetName").text = "Prince Sultan Road"
        etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}BuildingNumber").text = "1234"
        etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}CitySubdivisionName").text = "Al Olaya"
        etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}CityName").text = "Riyadh"
        etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PostalZone").text = "12211"
        country = etree.SubElement(postal_address, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Country")
        etree.SubElement(country, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IdentificationCode").text = "SA"
        
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

        # Tax Logic
        if invoice.vat_amount > 0:
            tax_cat = "S"
            tax_pct = "15.00"
            doc_tax = f"{invoice.vat_amount:.2f}"
        else:
            tax_cat = "Z"
            tax_pct = "0.00"
            doc_tax = "0.00"

        # Tax Total (BR-KSA-EN16931-09: Need a second TaxTotal in document currency)
        tax_total_sar = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal")
        etree.SubElement(tax_total_sar, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = doc_tax

        # Tax Total with Subtotals
        tax_total = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal")
        tax_amt = etree.SubElement(tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR")
        tax_amt.text = doc_tax
        
        if invoice.vat_amount > 0:
            # Tax Subtotal 1 (Main Cargo - Standard Rated)
            tax_subtotal = etree.SubElement(tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxSubtotal")
            etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxableAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"
            etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = doc_tax
            tax_category = etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxCategory")
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5305", schemeAgencyID="6").text = "S"
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Percent").text = "15.00"
            tax_scheme2 = etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
            etree.SubElement(tax_scheme2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5153", schemeAgencyID="6").text = "VAT"

            # Tax Subtotal 2 (Extra Charge - Zero Rated)
            if invoice.extra_charge > 0:
                tax_subtotal2 = etree.SubElement(tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxSubtotal")
                etree.SubElement(tax_subtotal2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxableAmount", currencyID="SAR").text = f"{invoice.extra_charge:.2f}"
                etree.SubElement(tax_subtotal2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = "0.00"
                tax_category2 = etree.SubElement(tax_subtotal2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxCategory")
                etree.SubElement(tax_category2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5305", schemeAgencyID="6").text = "Z"
                etree.SubElement(tax_category2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Percent").text = "0.00"
                etree.SubElement(tax_category2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode").text = "VATEX-SA-32"
                etree.SubElement(tax_category2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReason").text = "Export of goods"
                tax_scheme_ec = etree.SubElement(tax_category2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
                etree.SubElement(tax_scheme_ec, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5153", schemeAgencyID="6").text = "VAT"

        else:
            # Combined Tax Subtotal (Everything is Zero Rated)
            total_taxable = invoice.net_amount + invoice.extra_charge
            tax_subtotal = etree.SubElement(tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxSubtotal")
            etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxableAmount", currencyID="SAR").text = f"{total_taxable:.2f}"
            etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = "0.00"
            tax_category = etree.SubElement(tax_subtotal, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxCategory")
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5305", schemeAgencyID="6").text = "Z"
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Percent").text = "0.00"
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode").text = "VATEX-SA-32"
            etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReason").text = "Export of goods"
            tax_scheme2 = etree.SubElement(tax_category, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
            etree.SubElement(tax_scheme2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5153", schemeAgencyID="6").text = "VAT"

        # Legal Monetary Total
        total_net = invoice.net_amount + invoice.extra_charge
        legal_total = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}LegalMonetaryTotal")
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}LineExtensionAmount", currencyID="SAR").text = f"{total_net:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExclusiveAmount", currencyID="SAR").text = f"{total_net:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxInclusiveAmount", currencyID="SAR").text = f"{invoice.gross_total:.2f}"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}AllowanceTotalAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ChargeTotalAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PrepaidAmount", currencyID="SAR").text = "0.00"
        etree.SubElement(legal_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PayableAmount", currencyID="SAR").text = f"{invoice.gross_total:.2f}"

        # Invoice Line 1 (Main Cargo)
        inv_line = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine")
        etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "1"
        inv_qty = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoicedQuantity", unitCode="PCE")
        inv_qty.text = f"{float(invoice.pieces):.2f}"
        etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}LineExtensionAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"
        
        line_tax_total = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal")
        etree.SubElement(line_tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = doc_tax
        etree.SubElement(line_tax_total, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}RoundingAmount", currencyID="SAR").text = f"{(invoice.net_amount + invoice.vat_amount):.2f}"

        item = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Item")
        
        # BR-KSA-F-06-C19: Item name must be at least 3 characters
        item_name_text = invoice.product_info if invoice.product_info and len(invoice.product_info) >= 3 else "Cargo Services"
        etree.SubElement(item, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Name").text = item_name_text
        
        classified_tax = etree.SubElement(item, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}ClassifiedTaxCategory")
        etree.SubElement(classified_tax, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5305", schemeAgencyID="6").text = tax_cat
        etree.SubElement(classified_tax, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Percent").text = tax_pct
        if tax_cat == "Z":
            etree.SubElement(classified_tax, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode").text = "VATEX-SA-32"
            etree.SubElement(classified_tax, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReason").text = "Export of goods"
        tax_scheme3 = etree.SubElement(classified_tax, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
        etree.SubElement(tax_scheme3, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5153", schemeAgencyID="6").text = "VAT"

        price = etree.SubElement(inv_line, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Price")
        etree.SubElement(price, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PriceAmount", currencyID="SAR").text = f"{invoice.net_amount:.2f}"

        # Invoice Line 2 (Extra Charge) if applicable
        if invoice.extra_charge > 0:
            inv_line2 = etree.SubElement(invoice_root, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine")
            etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID").text = "2"
            inv_qty2 = etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoicedQuantity", unitCode="PCE")
            inv_qty2.text = "1.00"
            etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}LineExtensionAmount", currencyID="SAR").text = f"{invoice.extra_charge:.2f}"
            
            line_tax_total2 = etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal")
            etree.SubElement(line_tax_total2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxAmount", currencyID="SAR").text = "0.00"
            etree.SubElement(line_tax_total2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}RoundingAmount", currencyID="SAR").text = f"{invoice.extra_charge:.2f}"

            item2 = etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Item")
            etree.SubElement(item2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Name").text = "Extra Charge"
            
            classified_tax2 = etree.SubElement(item2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}ClassifiedTaxCategory")
            etree.SubElement(classified_tax2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5305", schemeAgencyID="6").text = "Z"
            etree.SubElement(classified_tax2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Percent").text = "0.00"
            etree.SubElement(classified_tax2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode").text = "VATEX-SA-32"
            etree.SubElement(classified_tax2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReason").text = "Export of goods"
            tax_scheme4 = etree.SubElement(classified_tax2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxScheme")
            etree.SubElement(tax_scheme4, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID", schemeID="UN/ECE 5153", schemeAgencyID="6").text = "VAT"

            price2 = etree.SubElement(inv_line2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}Price")
            etree.SubElement(price2, "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}PriceAmount", currencyID="SAR").text = f"{invoice.extra_charge:.2f}"

        # Generate XML String for hashing (raw UBL body before signatures)
        # Due to lxml C14N11 and XPath transform discrepancies with Java's XMLSignatureFactory,
        # we will use ZATCA's official SDK to guarantee a perfect Hash.
        import tempfile
        import subprocess
        import re
        import os

        # ZATCA expects the XML to be complete (with QR placeholder and Signature) before hashing
        xml_string = etree.tostring(invoice_root, pretty_print=False, encoding='UTF-8', xml_declaration=True)
        
        # Write to temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.xml')
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(xml_string)

        try:
            # Call ZATCA SDK fatoora.bat using its absolute path
            sdk_dir = "C:/ZATCHA-SDK/zatca-einvoicing-sdk-Java-238-R3.4.8/Apps"
            fatoora_cmd = "fatoora.bat" if os.name == 'nt' else "fatoora"
            fatoora_path = os.path.join(sdk_dir, fatoora_cmd)
            
            res = subprocess.run(
                [fatoora_path, "-generateHash", "-invoice", temp_path], 
                cwd=sdk_dir, 
                capture_output=True, 
                text=True,
                shell=(os.name == 'nt')  # Windows batch files often require shell=True
            )
            
            match = re.search(r'\*\*\* INVOICE HASH = ([A-Za-z0-9+/=]+)', res.stdout)
            if match:
                base64_hash = match.group(1)
            else:
                _logger.error("Failed to extract ZATCA Hash from SDK. Output: %s", res.stdout)
                # Fallback to python (will likely fail ZATCA validation)
                hash_root = copy.deepcopy(invoice_root)
                for sig in hash_root.xpath(".//cac:Signature", namespaces={'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}):
                    sig.getparent().remove(sig)
                for qr in hash_root.xpath(".//cac:AdditionalDocumentReference[cbc:ID='QR']//cbc:EmbeddedDocumentBinaryObject", namespaces={'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2', 'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'}):
                    qr.text = ""
                xml_string_c14n = etree.tostring(hash_root, method="c14n2")
                base64_hash = base64.b64encode(hashlib.sha256(xml_string_c14n).digest()).decode('utf-8')

        finally:
            # Cleanup temp file
            try:
                os.remove(temp_path)
            except Exception:
                pass

        return invoice_root, base64_hash

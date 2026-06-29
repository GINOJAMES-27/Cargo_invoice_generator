import base64
import hashlib
import logging
from odoo import models, api, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    # pyrefly: ignore [missing-import]
    from lxml import etree
    # pyrefly: ignore [missing-import]
    from cryptography.hazmat.primitives import hashes
    # pyrefly: ignore [missing-import]
    from cryptography.hazmat.primitives.asymmetric import ec
    # pyrefly: ignore [missing-import]
    from cryptography.hazmat.primitives import serialization
except ImportError:
    etree = None
    hashes = None
    ec = None
    serialization = None

class ZatcaSigningService(models.AbstractModel):
    _name = 'zatca.signing.service'
    _description = 'ZATCA XML Digital Signing Service (XMLDSig)'

    @api.model
    def sign_xml(self, invoice_root, settings):
        """
        Takes an lxml Element (Invoice), canonicalizes it, hashes it,
        signs it with the ECDSA private key, and injects the UBLExtensions.
        Returns the signed XML string.
        """
        if not etree or not ec:
            raise UserError(_("Python 'lxml' and 'cryptography' libraries must be installed."))
            
        private_key_pem = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_private_key')
        csid_cert = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_api_key')
        
        if not private_key_pem or not csid_cert:
            _logger.error("Missing Private Key or CSID in settings. Cannot sign XML.")
            return False

        try:
            # 1. Canonicalize (C14N) the raw invoice and calculate Digest
            canonicalized_xml = etree.tostring(invoice_root, method="c14n", exclusive=False, with_comments=False)
            digest_hash = hashlib.sha256(canonicalized_xml).digest()
            digest_b64 = base64.b64encode(digest_hash).decode('utf-8')

            # 2. Construct SignedInfo Block for XMLDSig
            # In ZATCA, SignedInfo contains references to the Digest above
            signed_info_xml = f"""
            <ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
                <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
                <ds:Reference URI="">
                    <ds:Transforms>
                        <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                            <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
                        </ds:Transform>
                        <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                            <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
                        </ds:Transform>
                        <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                    </ds:Transforms>
                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <ds:DigestValue>{digest_b64}</ds:DigestValue>
                </ds:Reference>
            </ds:SignedInfo>
            """
            signed_info_elem = etree.fromstring(signed_info_xml.strip())
            
            # Canonicalize the SignedInfo block to sign it exactly as it appears
            canonicalized_signed_info = etree.tostring(signed_info_elem, method="c14n", exclusive=False, with_comments=False)

            # 3. Load Private Key and Sign the SignedInfo Block
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None
            )
            
            # Sign using ECDSA SHA-256
            signature_bytes = private_key.sign(
                canonicalized_signed_info,
                ec.ECDSA(hashes.SHA256())
            )
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

            # 4. Construct the UBLExtensions Block
            # Remove header and footer from CSID cert
            csid_clean = csid_cert.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "").replace("\n", "").strip()

            extensions_xml = f"""
            <ext:UBLExtensions xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2" xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">
                <ext:UBLExtension>
                    <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
                    <ext:ExtensionContent>
                        <sig:UBLDocumentSignatures>
                            <sac:SignatureInformation>
                                <cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">urn:oasis:names:specification:ubl:signature:1</cbc:ID>
                                <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
                                <ds:Signature Id="signature">
                                    {signed_info_xml}
                                    <ds:SignatureValue>{signature_b64}</ds:SignatureValue>
                                    <ds:KeyInfo>
                                        <ds:X509Data>
                                            <ds:X509Certificate>{csid_clean}</ds:X509Certificate>
                                        </ds:X509Data>
                                    </ds:KeyInfo>
                                </ds:Signature>
                            </sac:SignatureInformation>
                        </sig:UBLDocumentSignatures>
                    </ext:ExtensionContent>
                </ext:UBLExtension>
            </ext:UBLExtensions>
            """
            
            # 5. Inject UBLExtensions into the root XML
            extensions_elem = etree.fromstring(extensions_xml.strip())
            invoice_root.insert(0, extensions_elem)
            
            # Return final signed XML string
            final_xml_string = etree.tostring(invoice_root, pretty_print=True, encoding='UTF-8', xml_declaration=True)
            return final_xml_string.decode('utf-8')
            
        except Exception as e:
            _logger.error("ZATCA Signing Failed: %s", str(e))
            return False
#Zatcha Integration Till Phase D completed
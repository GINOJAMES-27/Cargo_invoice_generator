import base64
import hashlib
import logging
import datetime
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
    # pyrefly: ignore [missing-import]
    from cryptography import x509
except ImportError:
    etree = None
    hashes = None
    ec = None
    serialization = None
    x509 = None

class ZatcaSigningService(models.AbstractModel):
    _name = 'zatca.signing.service'
    _description = 'ZATCA XML Digital Signing Service (XMLDSig)'

    @api.model
    def sign_xml(self, invoice_root, settings, invoice_hash_b64):
        """
        Takes an lxml Element (Invoice), canonicalizes it, hashes it,
        signs it with the ECDSA private key, constructs XAdES properties,
        and injects the UBLExtensions.
        """
        if not etree or not ec or not x509:
            raise UserError(_("Python 'lxml' and 'cryptography' libraries must be installed."))
            
        private_key_pem = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_private_key')
        csid_cert = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.zatca_api_key')
        
        if not private_key_pem or not csid_cert:
            _logger.error("Missing Private Key or CSID in settings. Cannot sign XML.")
            return False

        try:
            # 1. Prepare Certificate and parse properties
            csid_clean = csid_cert.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "").replace("\n", "").strip()
            # Handle double base64 if present
            try:
                decoded_once = base64.b64decode(csid_clean).decode('utf-8')
                if decoded_once.startswith('MII'):
                    csid_clean = decoded_once
            except Exception:
                pass
                
            der_cert = base64.b64decode(csid_clean)
            cert_obj = x509.load_der_x509_certificate(der_cert)
            
            issuer_name = cert_obj.issuer.rfc4514_string()
            serial_number = cert_obj.serial_number
            cert_hash_b64 = base64.b64encode(hashlib.sha256(der_cert).digest()).decode('utf-8')
            signing_time = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

            # 2. Construct XAdES SignedProperties using pure lxml to guarantee C14N exactness
            xades_ns = "http://uri.etsi.org/01903/v1.3.2#"
            ds_ns = "http://www.w3.org/2000/09/xmldsig#"
            
            NSMAP = {'xades': xades_ns, 'ds': ds_ns}
            xades_props = etree.Element("{%s}SignedProperties" % xades_ns, Id="xadesSignedProperties", nsmap=NSMAP)
            
            signed_sig_props = etree.SubElement(xades_props, "{%s}SignedSignatureProperties" % xades_ns)
            etree.SubElement(signed_sig_props, "{%s}SigningTime" % xades_ns).text = signing_time
            
            signing_cert = etree.SubElement(signed_sig_props, "{%s}SigningCertificate" % xades_ns)
            cert = etree.SubElement(signing_cert, "{%s}Cert" % xades_ns)
            
            cert_digest = etree.SubElement(cert, "{%s}CertDigest" % xades_ns)
            digest_method = etree.SubElement(cert_digest, "{%s}DigestMethod" % ds_ns, Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            etree.SubElement(cert_digest, "{%s}DigestValue" % ds_ns).text = cert_hash_b64
            
            issuer_serial = etree.SubElement(cert, "{%s}IssuerSerial" % xades_ns)
            etree.SubElement(issuer_serial, "{%s}X509IssuerName" % ds_ns).text = issuer_name
            etree.SubElement(issuer_serial, "{%s}X509SerialNumber" % ds_ns).text = str(serial_number)
            
            # Canonicalize just the SignedProperties
            xades_c14n = etree.tostring(xades_props, method="c14n", exclusive=False, with_comments=False)
            xades_hash_b64 = base64.b64encode(hashlib.sha256(xades_c14n).digest()).decode('utf-8')
            xades_props_xml = etree.tostring(xades_props, encoding='unicode')

            # 3. Construct SignedInfo Block for XMLDSig
            signed_info_xml = f"""
            <ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
                <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
                <ds:Reference Id="invoiceSignedData" URI="">
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
                    <ds:DigestValue>{invoice_hash_b64}</ds:DigestValue>
                </ds:Reference>
                <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <ds:DigestValue>{xades_hash_b64}</ds:DigestValue>
                </ds:Reference>
            </ds:SignedInfo>
            """
            signed_info_elem = etree.fromstring(signed_info_xml.strip())
            canonicalized_signed_info = etree.tostring(signed_info_elem, method="c14n", exclusive=False, with_comments=False)

            # 4. Load Private Key and Sign the SignedInfo Block
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None
            )
            signature_bytes = private_key.sign(
                canonicalized_signed_info,
                ec.ECDSA(hashes.SHA256())
            )
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

            # 5. Construct full ds:Signature with ds:Object
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
                                    <ds:Object>
                                        <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="#signature">
                                            {xades_props_xml.strip()}
                                        </xades:QualifyingProperties>
                                    </ds:Object>
                                </ds:Signature>
                            </sac:SignatureInformation>
                        </sig:UBLDocumentSignatures>
                    </ext:ExtensionContent>
                </ext:UBLExtension>
            </ext:UBLExtensions>
            """
            
            # 6. Inject UBLExtensions into the root XML
            extensions_elem = etree.fromstring(extensions_xml.strip())
            invoice_root.insert(0, extensions_elem)
            
            final_xml_string = etree.tostring(invoice_root, pretty_print=False, encoding='UTF-8', xml_declaration=True)
            return final_xml_string.decode('utf-8')
            
        except Exception as e:
            _logger.error("ZATCA Signing Failed: %s", str(e))
            return False
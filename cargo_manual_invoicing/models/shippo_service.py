import logging
from odoo import models, api
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

import sys
import os

# Ensure local site-packages is in path for dynamic imports
local_packages = r'C:\Users\dell\AppData\Roaming\Python\Python312\site-packages'
if os.path.exists(local_packages) and local_packages not in sys.path:
    sys.path.append(local_packages)

class ShippoIntegrationService(models.AbstractModel):
    _name = 'shippo.integration.service'
    _description = 'Shippo API Integration Service'

    @api.model
    def _ensure_shippo_installed(self):
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        libs_dir = os.path.join(os.path.dirname(current_dir), 'libs')
        if os.path.exists(libs_dir) and libs_dir not in sys.path:
            sys.path.insert(0, libs_dir)
            
        try:
            # Force reload if v3 was already loaded in memory (v3 doesn't have 'config')
            if 'shippo' in sys.modules and not hasattr(sys.modules['shippo'], 'config'):
                del sys.modules['shippo']
                
            # pyrefly: ignore [missing-import]
            import shippo
            return shippo
        except ImportError as e:
            raise UserError(f"Python 'shippo' library is not installed. Error: {e}")

    @api.model
    def _get_api_key(self):
        api_key = self.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.shippo_api_key')
        if not api_key:
            raise UserError("Shippo API Token is missing. Please configure it in Settings.")
        return api_key

    @api.model
    def _test_shippo_connection(self):
        try:
            shippo = self._ensure_shippo_installed()
        except UserError as e:
            return False, str(e)
        
        api_key = self._get_api_key()
        # Initialize shippo globally as per shippo docs
        shippo.config.api_key = api_key

        try:
            # We can test by fetching carrier accounts
            shippo.CarrierAccount.all()
            return True, "Successfully connected to Shippo API!"
        except Exception as e:
            return False, f"Shippo Connection Failed: {str(e)}"

    @api.model
    def _build_from_address(self):
        params = self.env['ir.config_parameter'].sudo()
        # TEMPORARY TEST: Using a US address so Shippo's default USPS carrier can generate rates!
        # We must completely bypass get_param because your Odoo Settings will override it
        return {
            "name": "Shippo Test Shipper",
            "company": "Shippo Test",
            "street1": "731 Market St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94103",
            "country": "US",
            "phone": "+14151234567",
            "email": "support@goshippo.com"
        }

    @api.model
    def _build_to_address(self, invoice):
        # We now have dedicated fields for City, ZIP, and Country
        city = invoice.receiver_city or 'Unknown'
        zip_code = invoice.receiver_zip or '00000'
        
        # Use the ISO code from the new dropdown, fallback to 'SA'
        country_iso = invoice.destination_country_id.code if invoice.destination_country_id else 'SA'

        # Sanitize phone number (Shippo is very strict)
        import re
        raw_phone = str(invoice.receiver_mobile or invoice.receiver_tel or '')
        clean_phone = re.sub(r'[^\d+]', '', raw_phone)
        if not clean_phone:
            clean_phone = "+14151234567" if country_iso == 'US' else "+966500000000"
        elif not clean_phone.startswith('+'):
            if country_iso == 'US' and len(clean_phone) == 10:
                clean_phone = "+1" + clean_phone
            elif country_iso == 'SA' and len(clean_phone) == 9:
                clean_phone = "+966" + clean_phone

        return {
            "name": invoice.receiver_name or invoice.receiver_company or 'Receiver',
            "company": invoice.receiver_company or '',
            "street1": invoice.receiver_address or 'Unknown',
            "city": city,
            "zip": zip_code,
            "country": country_iso,
            "phone": clean_phone,
            "email": invoice.receiver_email or ''
        }

    @api.model
    def _build_parcel(self, invoice):
        # Weight in kg. Shippo expects mass_unit and weight
        return {
            "length": "10",
            "width": "10",
            "height": "10",
            "distance_unit": "cm",
            "weight": str(invoice.weight or 1.0),
            "mass_unit": "kg"
        }

    @api.model
    def create_shipment(self, invoice):
        """ Creates a Shipment in Shippo to get live rates. """
        shippo = self._ensure_shippo_installed()

        shippo.config.api_key = self._get_api_key()

        from_address = self._build_from_address()
        to_address = self._build_to_address(invoice)
        parcel = self._build_parcel(invoice)

        try:
            shipment = shippo.Shipment.create(
                address_from=from_address,
                address_to=to_address,
                parcels=[parcel],
                async_=False
            )
            return shipment
        except Exception as e:
            raise UserError(f"Shippo Error: {str(e)}")

    @api.model
    def buy_label(self, rate_object_id):
        """ Purchases a label using a specific Rate Object ID. """
        shippo = self._ensure_shippo_installed()

        shippo.config.api_key = self._get_api_key()

        try:
            transaction = shippo.Transaction.create(
                rate=rate_object_id,
                label_file_type="PDF",
                async_=False
            )
            
            # USPS test labels and international labels sometimes return QUEUED immediately.
            # We must poll the API a few times until it flips to SUCCESS or ERROR.
            import time
            retries = 4
            while transaction.status == 'QUEUED' and retries > 0:
                time.sleep(2)
                transaction = shippo.Transaction.retrieve(transaction.object_id)
                retries -= 1
                
            return transaction
        except Exception as e:
            raise UserError(f"Shippo Error: {str(e)}")

    @api.model
    def track_shipment(self, carrier, tracking_number):
        """ Retrieves the latest tracking status from Shippo. """
        try:
            shippo = self._ensure_shippo_installed()
        except UserError:
            return None

        shippo.config.api_key = self._get_api_key()

        try:
            status = shippo.Track.get_status(carrier, tracking_number)
            return status
        except Exception as e:
            _logger.error(f"Shippo Tracking Error: {str(e)}")
            return None

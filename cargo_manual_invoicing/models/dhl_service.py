import json
import base64
import requests
from datetime import datetime
from odoo import models, api
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)

class DHLIntegrationService(models.AbstractModel):
    _name = 'dhl.integration.service'
    _description = 'DHL Express API Integration Service'

    @api.model
    def _get_dhl_credentials(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        api_key = get_param('cargo_manual_invoicing.dhl_api_key')
        api_secret = get_param('cargo_manual_invoicing.dhl_api_secret')
        account_number = get_param('cargo_manual_invoicing.dhl_account_number')
        sandbox_mode = get_param('cargo_manual_invoicing.dhl_sandbox_mode', 'True') == 'True'
        
        if sandbox_mode:
            url = get_param('cargo_manual_invoicing.dhl_sandbox_url', 'https://express.api.dhl.com/mydhlapi/test')
        else:
            url = get_param('cargo_manual_invoicing.dhl_production_url', 'https://express.api.dhl.com/mydhlapi')

        shipper_country = get_param('cargo_manual_invoicing.dhl_shipper_country_code', 'SA')
        shipper_city = get_param('cargo_manual_invoicing.dhl_shipper_city', 'Riyadh')
        shipper_postal_code = get_param('cargo_manual_invoicing.dhl_shipper_postal_code', '11564')

        if not api_key or not api_secret or not account_number:
            raise UserError("DHL API credentials are not fully configured. Please check your settings.")

        return {
            'api_key': api_key,
            'api_secret': api_secret,
            'account_number': account_number,
            'base_url': url.rstrip('/'),
            'shipper_country': shipper_country,
            'shipper_city': shipper_city,
            'shipper_postal_code': shipper_postal_code
        }

    @api.model
    def _dhl_request(self, endpoint, method='GET', payload=None, params=None):
        creds = self._get_dhl_credentials()
        url = f"{creds['base_url']}/{endpoint.lstrip('/')}"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        auth = (creds['api_key'], creds['api_secret'])
        
        try:
            if method == 'GET':
                response = requests.get(url, auth=auth, headers=headers, params=params, timeout=15)
            elif method == 'POST':
                response = requests.post(url, auth=auth, headers=headers, json=payload, timeout=20)
            else:
                raise UserError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"DHL API Error: {response.status_code} - {response.text}"
            _logger.error(error_msg)
            try:
                err_data = response.json()
                if 'detail' in err_data:
                    raise UserError(f"DHL Error: {err_data['detail']}")
                else:
                    raise UserError(error_msg)
            except ValueError:
                raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Connection to DHL API failed: {str(e)}"
            _logger.error(error_msg)
            raise UserError(error_msg)

    @api.model
    def _test_dhl_connection(self):
        try:
            creds = self._get_dhl_credentials()
            params = {
                'accountNumber': creds['account_number'],
                'originCountryCode': creds['shipper_country'],
                'originCityName': creds['shipper_city'],
                'destinationCountryCode': 'QA',
                'destinationCityName': 'Doha',
                'weight': 1,
                'length': 10,
                'width': 10,
                'height': 10,
                'plannedShippingDate': datetime.now().strftime('%Y-%m-%d'),
                'isCustomsDeclarable': 'false',
                'unitOfMeasurement': 'metric'
            }
            self._dhl_request('rates', method='GET', params=params)
            return True, "Successfully connected to DHL API and retrieved rates."
        except Exception as e:
            return False, str(e)

    @api.model
    def dhl_create_shipment(self, invoice):
        creds = self._get_dhl_credentials()
        
        planned_date = invoice.shipping_date.strftime('%Y-%m-%dT%H:%M:%S GMT+03:00') if invoice.shipping_date else datetime.now().strftime('%Y-%m-%dT%H:%M:%S GMT+03:00')
        
        # basic parse for origin/destination
        dest_country = invoice.destination[:2].upper() if invoice.destination and len(invoice.destination) >= 2 else "SA"
        dest_city = invoice.destination or "Destination"
        
        orig_country = creds['shipper_country']
        orig_city = invoice.origin or creds['shipper_city']

        payload = {
            "plannedShippingDateAndTime": planned_date,
            "pickup": {
                "isRequested": False
            },
            "productCode": "P", 
            "accounts": [
                {
                    "typeCode": "shipper",
                    "number": creds['account_number']
                }
            ],
            "customerDetails": {
                "shipperDetails": {
                    "postalAddress": {
                        "postalCode": creds['shipper_postal_code'],
                        "cityName": orig_city,
                        "countryCode": orig_country,
                        "addressLine1": invoice.shipper_address or "Not Provided"
                    },
                    "contactInformation": {
                        "email": invoice.shipper_email or "noemail@example.com",
                        "phone": invoice.shipper_mobile or "0000000000",
                        "companyName": invoice.shipper_company or invoice.shipper_name,
                        "fullName": invoice.shipper_name or "Shipper"
                    }
                },
                "receiverDetails": {
                    "postalAddress": {
                        "cityName": dest_city,
                        "countryCode": dest_country,
                        "addressLine1": invoice.receiver_address or "Not Provided"
                    },
                    "contactInformation": {
                        "email": invoice.receiver_email or "noemail@example.com",
                        "phone": invoice.receiver_mobile or "0000000000",
                        "companyName": invoice.receiver_company or invoice.receiver_name,
                        "fullName": invoice.receiver_name or "Receiver"
                    }
                }
            },
            "content": {
                "packages": [
                    {
                        "weight": invoice.weight,
                        "dimensions": {
                            "length": 10,
                            "width": 10,
                            "height": 10
                        }
                    } for i in range(invoice.pieces)
                ],
                "isCustomsDeclarable": False,
                "description": invoice.product_info or "Cargo Shipment",
                "incoterm": "DAP",
                "unitOfMeasurement": "metric"
            }
        }
        
        response = self._dhl_request('shipments', method='POST', payload=payload)
        
        tracking_number = None
        tracking_url = None
        label_base64 = None
        
        if 'shipmentTrackingNumber' in response:
            tracking_number = response['shipmentTrackingNumber']
            tracking_url = response.get('trackingUrl')
            
        if 'documents' in response:
            for doc in response['documents']:
                if doc.get('typeCode') == 'label' and doc.get('format') == 'pdf':
                    label_base64 = doc.get('content')
                    break
                    
        return tracking_number, tracking_url, label_base64

    @api.model
    def dhl_track_shipment(self, tracking_number):
        if not tracking_number:
            raise UserError("No tracking number provided.")
            
        response = self._dhl_request(f'tracking?trackingNumber={tracking_number}')
        
        if 'shipments' in response and len(response['shipments']) > 0:
            shipment = response['shipments'][0]
            status = shipment.get('events', [{}])[0].get('description', 'Status Unknown')
            return status
        else:
            return "No tracking information found."

    @api.model
    def dhl_get_rates(self, invoice):
        creds = self._get_dhl_credentials()
        planned_date = invoice.shipping_date.strftime('%Y-%m-%d') if invoice.shipping_date else datetime.now().strftime('%Y-%m-%d')
        
        dest_country = invoice.destination[:2].upper() if invoice.destination and len(invoice.destination) >= 2 else "SA"
        dest_city = invoice.destination or "Destination"
        orig_country = creds['shipper_country']
        orig_city = invoice.origin or creds['shipper_city']

        params = {
            'accountNumber': creds['account_number'],
            'originCountryCode': orig_country,
            'originCityName': orig_city,
            'destinationCountryCode': dest_country,
            'destinationCityName': dest_city,
            'weight': invoice.weight,
            'length': 10,
            'width': 10,
            'height': 10,
            'plannedShippingDate': planned_date,
            'isCustomsDeclarable': 'false',
            'unitOfMeasurement': 'metric'
        }
        
        response = self._dhl_request('rates', method='GET', params=params)
        
        if 'products' in response and len(response['products']) > 0:
            try:
                price = response['products'][0]['totalPrice'][0]['price']
                return float(price)
            except (KeyError, IndexError, ValueError):
                return 0.0
        return 0.0

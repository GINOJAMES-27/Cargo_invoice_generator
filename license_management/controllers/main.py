from odoo import http, _
# pyrefly: ignore [missing-import]
from odoo.http import request
# pyrefly: ignore [missing-import]
from odoo.addons.web.controllers.home import Home

class LicenseHomeController(Home):

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        # Allow normal handling to process POST if credentials are provided
        response = super().web_login(redirect=redirect, **kw)
        
        # If user is logged in
        if request.session.uid:
            ICP = request.env['ir.config_parameter'].sudo()
            status = ICP.get_param('license.status', 'draft')
            mode = ICP.get_param('license.mode', 'block')
            
            try:
                admin_uid = int(ICP.get_param('license.admin_uid', '2'))
            except ValueError:
                admin_uid = 2
                
            # If status is expired/suspended and mode is block, redirect to expired page
            if status in ['expired', 'suspended', 'invalid'] and mode == 'block':
                # Check if it's not the admin
                if request.session.uid != admin_uid and request.session.uid != 1:
                    return request.redirect('/license/expired')
                    
        return response

class LicenseController(http.Controller):

    @http.route('/license/expired', type='http', auth="public")
    def license_expired_page(self, **kw):
        ICP = request.env['ir.config_parameter'].sudo()
        
        vendor_name = ICP.get_param('license.vendor_name', 'Your Company')
        vendor_email = ICP.get_param('license.vendor_email', 'support@yourcompany.com')
        vendor_phone = ICP.get_param('license.vendor_phone', '')
        
        license_key = ICP.get_param('license.key', '')
        # Mask the key
        if license_key and len(license_key) > 9:
            masked_key = license_key[:5] + '****-****-****-' + license_key[-4:]
        else:
            masked_key = 'No License Key'
            
        expiry_date = ICP.get_param('license.expiry', 'Unknown')
        status = ICP.get_param('license.status', 'expired')
        
        db_name = request.env.cr.dbname
        
        values = {
            'vendor_name': vendor_name,
            'vendor_email': vendor_email,
            'vendor_phone': vendor_phone,
            'masked_key': masked_key,
            'expiry_date': expiry_date,
            'db_name': db_name,
            'status': status.upper()
        }
        
        return request.render('license_management.license_expired_page', values)

    @http.route('/license/status', type='json', auth="user")
    def get_license_status(self):
        # Endpoint for the OWL banner to fetch the status
        ICP = request.env['ir.config_parameter'].sudo()
        status = ICP.get_param('license.status', 'draft')
        expiry = ICP.get_param('license.expiry', '')
        
        # Determine banner colors and message
        banner_data = {
            'show': False,
            'color': '',
            'message': '',
            'is_admin': request.session.uid == 2 or request.env.user.has_group('base.group_system')
        }
        
        if status == 'active':
            return banner_data
            
        if status == 'expiring':
            # Calculate days
            if expiry:
                from datetime import datetime
                today = datetime.now().date()
                try:
                    exp_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                    days = (exp_date - today).days
                    if days > 14:
                        banner_data.update({'show': banner_data['is_admin'], 'color': 'warning', 'message': f'Your license expires in {days} days. Please renew.'})
                    elif days > 6:
                        banner_data.update({'show': banner_data['is_admin'], 'color': 'warning', 'message': f'License expiring soon! {days} days remaining. Contact support.'})
                    else:
                        banner_data.update({'show': banner_data['is_admin'], 'color': 'danger', 'message': f'LICENSE EXPIRING! Only {days} days left. Renew immediately!'})
                except Exception:
                    pass
        elif status == 'grace':
            banner_data.update({'show': True, 'color': 'danger', 'message': 'LICENSE EXPIRED! You are currently in the grace period. Renew NOW!'})
            
        return banner_data

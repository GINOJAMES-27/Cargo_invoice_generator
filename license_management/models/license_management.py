from odoo import models, fields, api, exceptions, _
from datetime import timedelta
import hashlib
import json
import hmac
import secrets
import string

SECRET_SALT = "V3nD0r_S3cr3t_S@lt_2026!"  # The secret salt for checksums

class LicenseManagement(models.Model):
    _name = 'license.management'
    _description = 'Software License'
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    customer_name = fields.Char(string='Customer Name', required=True)
    customer_email = fields.Char(string='Customer Email')
    customer_phone = fields.Char(string='Customer Phone')
    company_name = fields.Char(string='Company Name')
    database_uuid = fields.Char(string='Database UUID')
    database_name = fields.Char(string='Database Name')
    
    license_key = fields.Char(string='License Key', copy=False, readonly=True)
    license_status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expiring', 'Expiring Soon'),
        ('grace', 'Grace Period'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('invalid', 'Invalid')
    ], string='Status', default='draft', required=True)
    
    issue_date = fields.Date(string='Issue Date', default=fields.Date.context_today)
    expiry_date = fields.Date(string='Expiry Date', required=True)
    grace_period_days = fields.Integer(string='Grace Period (Days)', default=15)
    
    grace_expiry_date = fields.Date(string='Grace Expiry Date', compute='_compute_dates', store=True)
    days_remaining = fields.Integer(string='Days Remaining', compute='_compute_dates')
    is_in_grace = fields.Boolean(string='Is In Grace', compute='_compute_dates')
    is_fully_expired = fields.Boolean(string='Is Fully Expired', compute='_compute_dates')
    
    last_verification_date = fields.Datetime(string='Last Verification')
    next_verification_date = fields.Datetime(string='Next Verification')
    
    activation_count = fields.Integer(string='Activation Count', default=0)
    max_activations = fields.Integer(string='Max Activations', default=1)
    
    is_online_validation = fields.Boolean(string='Online Validation')
    license_server_url = fields.Char(string='License Server URL')
    licensed_modules = fields.Char(string='Licensed Modules')
    
    license_mode = fields.Selection([
        ('block', 'Block Login'),
        ('readonly', 'Read-Only Mode')
    ], string='Expiration Mode', default='block')
    
    notes = fields.Text(string='Internal Notes')
    license_payload = fields.Text(string='License Payload')
    license_checksum = fields.Char(string='Checksum', readonly=True)
    
    admin_user_id = fields.Many2one('res.users', string='Admin User', default=2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('license.management') or _('New')
            if not vals.get('license_key'):
                chars = string.ascii_uppercase + string.digits
                segments = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
                vals['license_key'] = 'OD18-' + '-'.join(segments)
        records = super().create(vals_list)
        for rec in records:
            rec._recalculate_checksum()
        return records

    def write(self, vals):
        res = super().write(vals)
        critical_fields = ['license_key', 'expiry_date', 'license_status', 'database_uuid']
        if any(field in vals for field in critical_fields):
            for rec in self:
                rec._recalculate_checksum()
        return res

    @api.depends('expiry_date', 'grace_period_days')
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.expiry_date:
                rec.grace_expiry_date = rec.expiry_date + timedelta(days=rec.grace_period_days or 0)
                rec.days_remaining = (rec.expiry_date - today).days
                rec.is_in_grace = rec.expiry_date < today <= rec.grace_expiry_date
                rec.is_fully_expired = today > rec.grace_expiry_date
            else:
                rec.grace_expiry_date = False
                rec.days_remaining = 0
                rec.is_in_grace = False
                rec.is_fully_expired = False

    def _recalculate_checksum(self):
        checksum_data = f"{self.license_key}|{self.expiry_date}|{self.license_status}|{self.database_uuid}|{SECRET_SALT}"
        new_checksum = hashlib.sha256(checksum_data.encode()).hexdigest()
        if self.license_checksum != new_checksum:
            self.env.cr.execute(
                "UPDATE license_management SET license_checksum=%s WHERE id=%s",
                (new_checksum, self.id)
            )

    def _check_tampering(self):
        self.ensure_one()
        if not self.license_checksum:
            return False
        checksum_data = f"{self.license_key}|{self.expiry_date}|{self.license_status}|{self.database_uuid}|{SECRET_SALT}"
        calculated = hashlib.sha256(checksum_data.encode()).hexdigest()
        if calculated != self.license_checksum:
            self.license_status = 'invalid'
            self._log_event('tampering', 'License checksum mismatch. Tampering detected.')
            return False
        return True

    def action_activate(self):
        self.ensure_one()
        current_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        if self.database_uuid and self.database_uuid != current_uuid:
            raise exceptions.UserError(_('This license is bound to another database (UUID mismatch).'))
        
        if not self.database_uuid:
            self.database_uuid = current_uuid
            self.database_name = self.env.cr.dbname

        if self.activation_count >= self.max_activations:
            raise exceptions.UserError(_('Maximum activation count reached for this license.'))

        self.activation_count += 1
        self.license_status = 'active'
        self._update_system_parameters()
        self._log_event('activation', 'License activated successfully.')

    def action_suspend(self):
        self.ensure_one()
        self.license_status = 'suspended'
        self._update_system_parameters()
        self._log_event('login_blocked', 'License suspended manually.')

    def action_renew(self, new_expiry):
        self.ensure_one()
        self.expiry_date = new_expiry
        self.license_status = 'active'
        self.last_verification_date = fields.Datetime.now()
        self._update_system_parameters()
        self._log_event('renewal', f'License renewed until {new_expiry}.')

    def action_verify(self):
        self.ensure_one()
        if not self._check_tampering():
            self._update_system_parameters()
            return

        current_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        if self.database_uuid and self.database_uuid != current_uuid:
            self.license_status = 'invalid'
            self._log_event('tampering', 'Database UUID mismatch during verification.')
            self._update_system_parameters()
            return

        self._compute_dates()
        today = fields.Date.context_today(self)
        
        if today <= self.expiry_date:
            if (self.expiry_date - today).days <= 30:
                self.license_status = 'expiring'
            else:
                self.license_status = 'active'
        elif today <= self.grace_expiry_date:
            self.license_status = 'grace'
        else:
            self.license_status = 'expired'
            
        self.last_verification_date = fields.Datetime.now()
        self._update_system_parameters()
        self._log_event('verification', f'License verified. Status updated to {self.license_status}.')

    def _update_system_parameters(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('license.key', self.license_key or '')
        ICP.set_param('license.expiry', str(self.expiry_date) if self.expiry_date else '')
        ICP.set_param('license.status', self.license_status or 'draft')
        ICP.set_param('license.last_check', str(self.last_verification_date) if self.last_verification_date else '')
        ICP.set_param('license.grace_period', str(self.grace_period_days))
        ICP.set_param('license.server', self.license_server_url or '')
        ICP.set_param('license.online_validation', str(self.is_online_validation))
        ICP.set_param('license.mode', self.license_mode or 'block')
        ICP.set_param('license.admin_uid', str(self.admin_user_id.id if self.admin_user_id else 2))

    def _log_event(self, event_type, description):
        self.ensure_one()
        self.env['license.log'].sudo().create({
            'license_id': self.id,
            'event_type': event_type,
            'description': description,
            'user_id': self.env.user.id,
            'ip_address': 'unknown' # Could be extracted from request in controllers
        })

    @api.model
    def _cron_check_license_status(self):
        active_licenses = self.search([('license_status', 'not in', ['draft', 'invalid'])])
        for license in active_licenses:
            license.action_verify()
            # In a full implementation, we'd add online verification request and email sending here

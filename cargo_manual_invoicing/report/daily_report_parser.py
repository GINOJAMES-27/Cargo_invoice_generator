from odoo import api, models, fields
from datetime import datetime

class DailyCollectionReportParser(models.AbstractModel):
    _name = 'report.cargo_manual_invoicing.report_daily_collection_document'
    _description = 'Daily Collection Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = data.get('domain', [])
        form = data.get('form', {})

        invoice_obj = self.env['cargo.manual.invoice']
        
        # 1. Overall Summary (read_group without groupby)
        overall = invoice_obj.read_group(domain, ['gross_total', 'net_amount', 'vat_amount', 'extra_charge'], [])
        
        # 2. By Payment Mode
        paymodes = invoice_obj.read_group(domain, ['gross_total'], ['paymode'])
        
        # 3. By Shipment Type
        shipment_types = invoice_obj.read_group(domain, ['gross_total'], ['shipment_type'])
        
        # 4. Agent-wise Breakdown
        agents = invoice_obj.read_group(domain, ['gross_total'], ['agent_name'])
        # For agent-wise, we need cash/card/company breakdown as well.
        # We can either loop through agents and read_group again, or do a multi-groupby.
        agent_paymodes = invoice_obj.read_group(domain, ['gross_total'], ['agent_name', 'paymode'], lazy=False)
        agent_shipments = invoice_obj.read_group(domain, ['gross_total'], ['agent_name', 'shipment_type'], lazy=False)
        
        # Detailed lines if requested
        invoice_lines = []
        if form.get('report_type') == 'detailed':
            invoice_lines = invoice_obj.search_read(
                domain, 
                ['invoice_number', 'shipping_date', 'agent_name', 'shipper_name', 
                 'destination', 'paymode', 'carrier', 'gross_total', 'shipment_type'],
                order='agent_name asc, shipping_date asc'
            )

        # Calculate counts safely
        def get_count(group_dict, group_field=None):
            if '__count' in group_dict:
                return group_dict['__count']
            if group_field and f'{group_field}_count' in group_dict:
                return group_dict[f'{group_field}_count']
            # Fallback for overall
            for k in group_dict.keys():
                if k.endswith('_count'):
                    return group_dict[k]
            return 1 # Fallback if completely unknown, though shouldn't happen

        # Restructure Agent Summary
        agent_summary = []
        for ag in agents:
            ag_name = ag['agent_name'] or 'Unknown'
            # Find paymodes for this agent
            c_cash = sum(x['gross_total'] for x in agent_paymodes if x['agent_name'] == ag['agent_name'] and x['paymode'] == 'cash')
            c_card = sum(x['gross_total'] for x in agent_paymodes if x['agent_name'] == ag['agent_name'] and x['paymode'] == 'card')
            c_comp = sum(x['gross_total'] for x in agent_paymodes if x['agent_name'] == ag['agent_name'] and x['paymode'] == 'company')
            
            d_count = sum(get_count(x, 'shipment_type') for x in agent_shipments if x['agent_name'] == ag['agent_name'] and x['shipment_type'] == 'domestic')
            i_count = sum(get_count(x, 'shipment_type') for x in agent_shipments if x['agent_name'] == ag['agent_name'] and x['shipment_type'] == 'international')
            
            agent_summary.append({
                'agent_name': ag_name,
                'total_invoices': get_count(ag, 'agent_name'),
                'cash_total': c_cash,
                'card_total': c_card,
                'company_total': c_comp,
                'gross_total': ag['gross_total'],
                'domestic_count': d_count,
                'international_count': i_count,
            })

        # Calculate percentages for paymodes
        total_gross = overall[0]['gross_total'] if overall and overall[0].get('gross_total') else 0.0
        paymode_data = []
        for pm in paymodes:
            pm_val = pm['paymode']
            pm_label = pm_val.capitalize() if pm_val else 'Unknown'
            pm_total = pm['gross_total'] or 0.0
            pm_pct = (pm_total / total_gross * 100) if total_gross else 0.0
            
            paymode_data.append({
                'paymode': pm_val,
                'label': pm_label,
                'count': get_count(pm, 'paymode'),
                'total': pm_total,
                'pct': pm_pct
            })

        # Rebuild shipment types to fix __count error
        shipment_data = []
        for st in shipment_types:
            shipment_data.append({
                'shipment_type': st['shipment_type'],
                'count': get_count(st, 'shipment_type'),
                'gross_total': st['gross_total'] or 0.0
            })

        report_data = {
            'date_from': form.get('date_from'),
            'date_to': form.get('date_to'),
            'generated_by': self.env.user.name,
            'generated_at': fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'company_name': self.env.company.name or 'Brightness of Hope Air Cargo Est',
            'report_type': form.get('report_type'),
            
            'total_invoices': get_count(overall[0]) if overall else 0,
            'total_gross': total_gross,
            'total_net': overall[0]['net_amount'] if overall and overall[0].get('net_amount') else 0.0,
            'total_vat': overall[0]['vat_amount'] if overall and overall[0].get('vat_amount') else 0.0,
            'total_extra': overall[0]['extra_charge'] if overall and overall[0].get('extra_charge') else 0.0,
            
            'paymode_data': paymode_data,
            'shipment_types': shipment_data,
            'agent_summary': agent_summary,
            'invoice_lines': invoice_lines,
        }

        return {
            'doc_ids': docids,
            'doc_model': 'cargo.daily.report.wizard',
            'docs': self.env['cargo.daily.report.wizard'].browse(docids),
            'data': report_data,
        }

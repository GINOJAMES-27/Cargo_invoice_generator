import json
import logging
import base64
import tempfile
import os
from datetime import datetime, timedelta
from odoo import http
# pyrefly: ignore [missing-import]
from odoo.http import request

_logger = logging.getLogger(__name__)

class CargoAIController(http.Controller):

    def _import_openai(self):
        import importlib.util
        import sys
        
        public_site = r'C:\temp\python_libs'
        if public_site not in sys.path:
            sys.path.insert(0, public_site)
        
        openai_init_path = r'C:\temp\python_libs\openai\__init__.py'
        spec = importlib.util.spec_from_file_location('openai', openai_init_path)
        openai = importlib.util.module_from_spec(spec)
        sys.modules['openai'] = openai
        spec.loader.exec_module(openai)
        return openai

    def _get_openai_client(self):
        openai_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.openai_api_key')
        if not openai_key:
            return {'error': 'Speech-to-text requires an OpenAI API Key configured in settings.'}
        try:
            openai = self._import_openai()
            return openai.OpenAI(api_key=openai_key)
        except Exception as e:
            return {'error': f'Python openai library absolute import error: {e}'}

    def _get_groq_client(self):
        groq_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.groq_api_key')
        if not groq_key:
            return None
        try:
            openai = self._import_openai()
            return openai.OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1"
            )
        except Exception as e:
            return {'error': f'Python openai library absolute import error: {e}'}

    def _get_gemini_client(self):
        gemini_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.gemini_api_key')
        if not gemini_key:
            return None
        try:
            openai = self._import_openai()
            return openai.OpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
        except Exception as e:
            return {'error': f'Python openai library absolute import error: {e}'}

    @http.route('/cargo/ai/speech_to_text', type='json', auth='user')
    def handle_speech_to_text(self, audio_data):
        groq_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.groq_api_key')
        gemini_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.gemini_api_key')
        openai_key = request.env['ir.config_parameter'].sudo().get_param('cargo_manual_invoicing.openai_api_key')
        
        if not gemini_key and not openai_key and not groq_key:
            return {'error': 'No AI API Key configured for Speech-to-Text.'}
            
        try:
            if groq_key:
                client = self._get_groq_client()
                if isinstance(client, dict):
                    return client # Error dict
                    
                # Decode base64 to binary
                audio_binary = base64.b64decode(audio_data)
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                    tmp.write(audio_binary)
                    tmp_path = tmp.name
                    
                # Send to Whisper
                with open(tmp_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-large-v3-turbo", 
                        file=audio_file
                    )
                    
                os.remove(tmp_path)
                return {'text': transcript.text}

            elif gemini_key:
                import urllib.request
                import json
                
                url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}'
                
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Transcribe the following audio accurately. Reply ONLY with the transcription, nothing else. Do not wrap in quotes."},
                            {
                                "inline_data": {
                                    "mime_type": "audio/webm",
                                    "data": audio_data
                                }
                            }
                        ]
                    }]
                }
                
                import urllib.error
                models_to_try = [
                    'gemini-2.5-flash',
                    'gemini-1.5-flash',
                    'gemini-1.5-flash-8b',
                    'gemini-2.5-pro'
                ]
                
                response = None
                last_exception = None
                for model_name in models_to_try:
                    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}'
                    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST')
                    req.add_header('Content-Type', 'application/json')
                    try:
                        response = urllib.request.urlopen(req)
                        break # Success!
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            last_exception = e
                            continue # Try next model
                        else:
                            raise e
                            
                if not response:
                    if last_exception and last_exception.code == 429:
                        return {'error': "Voice assistant rate limit reached! You've used the microphone too many times in the last minute. Please wait 60 seconds or type your request."}
                    if last_exception:
                        raise last_exception
                    raise Exception("Speech-to-text failed for unknown reasons.")
                result = json.loads(response.read().decode('utf-8'))
                
                text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                return {'text': text.strip()}
                
            else:
                client = self._get_openai_client()
                if isinstance(client, dict):
                    return client # Error dict
                    
                # Decode base64 to binary
                audio_binary = base64.b64decode(audio_data)
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                    tmp.write(audio_binary)
                    tmp_path = tmp.name
                    
                # Send to Whisper
                with open(tmp_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1", 
                        file=audio_file
                    )
                    
                os.remove(tmp_path)
                return {'text': transcript.text}
                
        except Exception as e:
            _logger.exception("Speech-to-Text failed")
            return {'error': str(e)}

    @http.route('/cargo/ai/query', type='json', auth='user')
    def handle_ai_query(self, query):
        try:
            ai_provider = None
            client = self._get_groq_client()
            if isinstance(client, dict): return client
            
            if client:
                ai_provider = 'groq'
            else:
                client = self._get_gemini_client()
                if isinstance(client, dict): return client
                if client:
                    ai_provider = 'gemini'
                else:
                    client = self._get_openai_client()
                    if isinstance(client, dict):
                        return {'error': 'No Groq, Gemini, or OpenAI API Key configured in settings.'}
                    ai_provider = 'openai'

            system_prompt = """
            You are an AI assistant for a Cargo & Courier agency running on Odoo.
            You help users by parsing their natural language speech into structured tool calls.
            
            The user manages 'cargo.manual.invoice' records.
            Fields include:
            - origin (str)
            - shipper_name (str)
            - shipper_mobile (str)
            - shipper_vat_no (str)
            - destination_country_id (Many2one to res.country)
            - receiver_name (str)
            - receiver_mobile (str)
            - weight (float)
            - pieces (int)
            - delivery_partner (selection: dhl, fedex, aramex, smsa, manual)
            - shipment_type (selection: domestic, international)
            - gross_total (float)
            
            Use the provided tools to satisfy the user's intent.
            Today's date is: """ + datetime.now().strftime('%Y-%m-%d')

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "fill_invoice_form",
                        "description": "Opens a new Cargo Invoice form pre-filled with the extracted data.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "shipper_name": {"type": "string"},
                                "shipper_mobile": {"type": "string"},
                                "destination": {"type": "string", "description": "The country name"},
                                "receiver_name": {"type": "string"},
                                "receiver_mobile": {"type": "string"},
                                "weight": {"type": "number"},
                                "pieces": {"type": "integer"},
                                "delivery_partner": {"type": "string", "enum": ["dhl", "fedex", "aramex", "smsa", "manual"]}
                            }
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "query_shipment_count",
                        "description": "Ask the database for the number of shipments matching criteria.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                                "shipment_type": {"type": "string", "enum": ["domestic", "international"]}
                            }
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "generate_report",
                        "description": "Generate a daily collection report for a given date range.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                                "date_to": {"type": "string", "description": "YYYY-MM-DD"}
                            },
                            "required": ["date_from", "date_to"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "communicate_invoice",
                        "description": "Send an invoice to the customer via Email.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "invoice_number": {"type": "string", "description": "The exact invoice number, e.g., INV/2026/0001"},
                                "method": {"type": "string", "enum": ["email"]}
                            },
                            "required": ["invoice_number", "method"]
                        }
                    }
                }
            ]

            openai = self._import_openai()
            
            if ai_provider == 'groq':
                model_name = "llama-3.3-70b-versatile"
            elif ai_provider == 'gemini':
                model_name = "gemini-2.5-flash"
            else:
                model_name = "gpt-4o-mini"
                
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.0
                )
            except openai.RateLimitError:
                if ai_provider == 'gemini':
                    response = client.chat.completions.create(
                        model="gemini-2.5-pro",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": query}
                        ],
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.0
                    )
                else:
                    raise
            
            message = response.choices[0].message
            
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                if function_name == 'fill_invoice_form':
                    country_id = False
                    if args.get('destination'):
                        country = request.env['res.country'].search([('name', 'ilike', args['destination'])], limit=1)
                        if country:
                            country_id = country.id
                            
                    context = {}
                    if args.get('shipper_name'): context['default_shipper_name'] = args['shipper_name']
                    if args.get('shipper_mobile'): context['default_shipper_mobile'] = args['shipper_mobile']
                    if country_id: context['default_destination_country_id'] = country_id
                    if args.get('receiver_name'): context['default_receiver_name'] = args['receiver_name']
                    if args.get('receiver_mobile'): context['default_receiver_mobile'] = args['receiver_mobile']
                    if args.get('weight'): context['default_weight'] = args['weight']
                    if args.get('pieces'): context['default_pieces'] = args['pieces']
                    if args.get('delivery_partner'): context['default_delivery_partner'] = args['delivery_partner']
                    
                    return {
                        'action_type': 'ir.actions.act_window',
                        'action': {
                            'name': 'New Cargo Invoice (AI)',
                            'type': 'ir.actions.act_window',
                            'res_model': 'cargo.manual.invoice',
                            'view_mode': 'form',
                            'views': [[False, 'form']],
                            'target': 'current',
                            'context': context
                        }
                    }
                    
                elif function_name == 'generate_report':
                    domain = [
                        ('shipping_date', '>=', args['date_from'] + ' 00:00:00'),
                        ('shipping_date', '<=', args['date_to'] + ' 23:59:59')
                    ]
                    return {
                        'action_type': 'ir.actions.report',
                        'action': {
                            'type': 'ir.actions.report',
                            'report_name': 'cargo_manual_invoicing.report_daily_collection_document',
                            'report_type': 'qweb-pdf',
                            'name': 'Daily Collection Report',
                            'data': {
                                'form': {
                                    'date_from': args['date_from'],
                                    'date_to': args['date_to'],
                                    'report_type': 'detailed'
                                },
                                'domain': domain
                            },
                            'context': {'active_model': 'cargo.manual.invoice', 'active_ids': []}
                        }
                    }
                    
                elif function_name == 'communicate_invoice':
                    invoice = request.env['cargo.manual.invoice'].search([('invoice_number', 'ilike', args['invoice_number'])], limit=1)
                    if not invoice:
                        return {
                            'action_type': 'chat_response',
                            'message': f"I couldn't find invoice number {args['invoice_number']}."
                        }
                    
                    try:
                        if args['method'] == 'email':
                            action = invoice.action_send_email()
                            return {
                                'action_type': action.get('type'),
                                'action': action
                            }
                    except Exception as e:
                        return {
                            'action_type': 'chat_response',
                            'message': f"Failed to send via {args['method']}: {str(e)}"
                        }
                        
                elif function_name == 'query_shipment_count':
                    domain = []
                    if args.get('date_from'):
                        domain.append(('shipping_date', '>=', args['date_from'] + ' 00:00:00'))
                    if args.get('date_to'):
                        domain.append(('shipping_date', '<=', args['date_to'] + ' 23:59:59'))
                    if args.get('shipment_type'):
                        domain.append(('shipment_type', '=', args['shipment_type']))
                        
                    count = request.env['cargo.manual.invoice'].search_count(domain)
                    return {
                        'action_type': 'chat_response',
                        'message': f"I found {count} shipments matching your criteria."
                    }
                    
            return {
                'action_type': 'chat_response',
                'message': message.content or "I couldn't understand the request. Please try again."
            }

        except Exception as e:
            _logger.exception("AI Query completely failed")
            return {'error': "INTERNAL_ERROR: " + str(e) + " - " + str(type(e))}

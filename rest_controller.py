import json
import logging
from odoo import http
from odoo.http import request
from datetime import datetime

_logger = logging.getLogger(__name__)


class RestApi(http.Controller):
    """This is a controller which is used to generate responses based on the
    api requests"""

    def auth_api_key(self, api_key):
        """This function is used to authenticate the api-key when sending a
        request"""
        user_id = request.env['res.users'].sudo().search([('api_key', '=', api_key)])
        if api_key is not None and user_id:
             response = True
        elif not user_id:
            response = ('<html><body><h2>Invalid <i>API Key</i> '
                        '!</h2></body></html>')
        else:
            response = ("<html><body><h2>No <i>API Key</i> Provided "
                        "!</h2></body></html>")
        return response

    def generate_response(self, method, model, rec_id):
        """This function is used to generate the response based on the type
        of request and the parameters given"""
        option = request.env['connection.api'].search(
            [('model_id', '=', model)], limit=1)
        model_name = option.model_id.model
        if method != 'DELETE':
            data = json.loads(request.httprequest.data)
        else:
            data = {}
        fields = []
        if data:
            for field in data['fields']:
                fields.append(field)
        if not fields and method != 'DELETE':
            return ("<html><body><h2>No fields selected for the model"
                    "</h2></body></html>")
        if not option:
            return ("<html><body><h2>No Record Created for the model"
                    "</h2></body></html>")
        try:
            if method == 'GET':
                fields = []
                for field in data['fields']:
                    fields.append(field)
                if not option.is_get:
                    return ("<html><body><h2>Method Not Allowed"
                            "</h2></body></html>")
                else:
                    datas = []
                    if rec_id != 0:
                        partner_records = request.env[
                            str(model_name)
                        ].search_read(
                            domain=[('id', '=', rec_id)],
                            fields=fields
                        )

                        # Manually convert datetime fields to string format
                        for record in partner_records:
                            for key, value in record.items():
                                if isinstance(value, datetime):
                                    record[key] = value.isoformat()
                        data = json.dumps({
                            'records': partner_records
                        })
                        datas.append(data)
                        return request.make_response(data=datas)
                    else:
                        partner_records = request.env[
                            str(model_name)
                        ].search_read(
                            domain=[],
                            fields=fields
                        )

                        # Manually convert datetime fields to string format
                        for record in partner_records:
                            for key, value in record.items():
                                if isinstance(value, datetime):
                                    record[key] = value.isoformat()

                        data = json.dumps({
                            'records': partner_records
                        })
                        datas.append(data)
                        return request.make_response(data=datas)
        except:
            return ("<html><body><h2>Invalid JSON Data"
                    "</h2></body></html>")
        if method == 'POST':
            if not option.is_post:
                return request.make_response(
                    "<html><body><h2>Method Not Allowed</h2></body></html>", status=405
                )
            else:
                try:
                    # Parse incoming JSON data
                    data = json.loads(request.httprequest.data)

                    # Extract the badge_number from the incoming data
                    badge_number = data['values']['employee_id']

                    # Search for the corresponding employee_id from the hr_employee model
                    employee = request.env['hr.employee'].search([
                        ('barcode', '=', badge_number)
                    ], limit=1)

                    if not employee:
                        return request.make_response(
                            "<html><body><h2>No matching employee found. Skipping.</h2></body></html>", status=404
                        )

                    # Use the employee_id from the found employee
                    employee_id = employee.id

                    # Check if the employee has an active contract
                    active_contract = request.env['hr.contract'].search([
                        ('employee_id', '=', employee_id),
                        ('state', '=', 'open')  # Ensure the contract is active
                    ], limit=1)

                    if not active_contract:
                        return request.make_response(
                            "<html><body><h2>No active contract found. Skipping attendance creation.</h2></body></html>",
                            status=404
                        )

                    # Extract check-in or check-out date_time
                    check_in_date_time = data['values'].get('check_in', None)
                    check_out_date_time = data['values'].get('check_out', None)

                    if check_in_date_time:
                        check_in_date = datetime.strptime(check_in_date_time, '%Y-%m-%d %H:%M:%S').date()
                        existing_record = request.env[str(model_name)].search([
                            ('employee_id', '=', employee_id),
                            ('check_in', '>=', str(check_in_date) + " 00:00:00"),
                            ('check_in', '<=', str(check_in_date) + " 23:59:59")
                        ])

                        if existing_record:
                            return request.make_response(
                                f"<html><body><h2>Duplicate check-in entry detected for employee {employee_id} on {check_in_date}</h2></body></html>",
                                status=409
                            )

                        data['values']['employee_id'] = employee_id
                        new_check_in = request.env[str(model_name)].create(data['values'])
                        return request.make_response(
                            json.dumps({'New check-in resource': [{
                                'id': new_check_in.id,
                                'check_in': new_check_in.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                            }]}),
                            status=201
                        )

                    elif check_out_date_time:
                        check_out_date = datetime.strptime(check_out_date_time, '%Y-%m-%d %H:%M:%S').date()
                        existing_check_in = request.env[str(model_name)].search([
                            ('employee_id', '=', employee_id),
                            ('check_in', '>=', str(check_out_date) + " 00:00:00"),
                            ('check_in', '<=', str(check_out_date) + " 23:59:59"),
                            ('check_out', '=', False)
                        ], limit=1)

                        if existing_check_in:
                            existing_check_in.write({'check_out': check_out_date_time})
                            return request.make_response(
                                json.dumps({'Updated check-out resource': [{
                                    'id': existing_check_in.id,
                                    'check_in': existing_check_in.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                                    'check_out': existing_check_in.check_out.strftime('%Y-%m-%d %H:%M:%S'),
                                }]}),
                                status=204
                            )

                        return request.make_response(
                            f"<html><body><h2>No matching check-in record found for employee {employee_id} on {check_out_date}</h2></body></html>",
                            status=404
                        )

                    else:
                        return request.make_response(
                            "<html><body><h2>Both check-in and check-out are missing in the request.</h2></body></html>",
                            status=400
                        )

                except Exception as e:
                    return request.make_response(
                        f"<html><body><h2>Error: {str(e)}</h2></body></html>", status=500
                    )
        if method == 'PUT':
            if not option.is_put:
                return ("<html><body><h2>Method Not Allowed"
                        "</h2></body></html>")
            else:
                if rec_id == 0:
                    return ("<html><body><h2>No ID Provided"
                            "</h2></body></html>")
                else:
                    resource = request.env[str(model_name)].browse(
                        int(rec_id))
                    if not resource.exists():
                        return ("<html><body><h2>Resource not found"
                                "</h2></body></html>")
                    else:
                        try:
                            datas = []
                            data = json.loads(request.httprequest.data)
                            resource.write(data['values'])
                            partner_records = request.env[
                                str(model_name)].search_read(
                                domain=[('id', '=', resource.id)],
                                fields=fields
                            )
                            new_data = json.dumps(
                                {'Updated resource': partner_records,
                                 })
                            datas.append(new_data)
                            return request.make_response(data=datas)

                        except:
                            return ("<html><body><h2>Invalid JSON Data "
                                    "!</h2></body></html>")
        if method == 'DELETE':
            if not option.is_delete:
                return ("<html><body><h2>Method Not Allowed"
                        "</h2></body></html>")
            else:
                if rec_id == 0:
                    return ("<html><body><h2>No ID Provided"
                            "</h2></body></html>")
                else:
                    resource = request.env[str(model_name)].browse(
                        int(rec_id))
                    if not resource.exists():
                        return ("<html><body><h2>Resource not found"
                                "</h2></body></html>")
                    else:

                        records = request.env[
                            str(model_name)].search_read(
                            domain=[('id', '=', resource.id)],
                            fields=['id', 'display_name']
                        )
                        remove = json.dumps(
                            {"Resource deleted": records,
                             })
                        resource.unlink()
                        return request.make_response(data=remove)

    @http.route(['/send_request'], type='http',
                auth='none',
                methods=['GET', 'POST', 'PUT', 'DELETE'], csrf=False)
    def fetch_data(self, **kw):
        """This controller will be called when sending a request to the
        specified url, and it will authenticate the api-key and then will
        generate the result"""
        http_method = request.httprequest.method
        api_key = request.httprequest.headers.get('api-key')
        auth_api = self.auth_api_key(api_key)
        model = kw.get('model')
        username = request.httprequest.headers.get('login')
        password = request.httprequest.headers.get('password')
        credential = {'login': username, 'password': password, 'type': 'password'}
        request.session.authenticate(request.session.db, credential)
        model_id = request.env['ir.model'].search(
            [('model', '=', model)])
        if not model_id:
            return ("<html><body><h3>Invalid model, check spelling or maybe "
                    "the related "
                    "module is not installed"
                    "</h3></body></html>")

        if auth_api == True:
            if not kw.get('Id'):
                rec_id = 0
            else:
                rec_id = int(kw.get('Id'))
            result = self.generate_response(http_method, model_id.id, rec_id)
            return result
        else:
            return auth_api

    @http.route(['/odoo_connect'], type="http", auth="none", csrf=False,
                methods=['GET'])
    def odoo_connect(self, **kw):
        """This is the controller which initializes the api transaction by
        generating the api-key for specific user and database"""
        username = request.httprequest.headers.get('login')
        password = request.httprequest.headers.get('password')
        db = request.httprequest.headers.get('db')
        try:
            request.session.update(http.get_default_session(), db=db)
            credential = {'login': username, 'password': password,
                          'type': 'password'}

            auth = request.session.authenticate(db, credential)
            user = request.env['res.users'].browse(auth['uid'])
            api_key = request.env.user.generate_api(username)
            datas = json.dumps({"Status": "auth successful",
                                "User": user.name,
                                "api-key": api_key})
            return request.make_response(data=datas)
        except:
            return ("<html><body><h2>wrong login credentials"
                    "</h2></body></html>")

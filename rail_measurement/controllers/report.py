from odoo.addons.web.controllers.report import ReportController
from odoo import http
from odoo.addons.base.models.ir_actions_report import IrActionsReport

class CustomReportController(ReportController):

    @http.route(['/report/download'], type='http', auth="user")
    def report_download(self, data, context=None, token=None, readonly=True):
        import json
        from odoo.tools.safe_eval import safe_eval, time as safe_time

        requestcontent = json.loads(data)
        url, type_ = requestcontent[0], requestcontent[1]

        if type_ == 'qweb-pdf':
            pattern = '/report/pdf/'
            reportname = url.split(pattern)[1].split('?')[0]
            docids = None
            if '/' in reportname:
                reportname, docids = reportname.split('/')

            report_model = http.request.env['ir.actions.report']
            if reportname in report_model.SALE_REPORT_REFS and docids:
                ids = [int(x) for x in docids.split(",") if x.isdigit()]
                custom = report_model._get_sale_custom_report(ids)
                if custom and custom.report_name not in report_model.SALE_REPORT_REFS:
                    if custom.print_report_name and len(ids) == 1:
                        obj = http.request.env[custom.model].browse(ids)

                        report_name = safe_eval(custom.print_report_name, {'object': obj, 'time': safe_time})
                        # On laisse le parent générer la response, on change juste le header
                        response = super().report_download(data, context=context, token=token, readonly=readonly)
                        from werkzeug.http import dump_header
                        response.headers['Content-Disposition'] = f'attachment; filename="{report_name}.pdf"'
                        return response

        return super().report_download(data, context=context, token=token, readonly=readonly)
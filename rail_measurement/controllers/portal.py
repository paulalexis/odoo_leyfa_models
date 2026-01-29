from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import logging
_logger = logging.getLogger(__name__)

class RailPortal(CustomerPortal):

    @http.route(['/my/measurement/new'], type='http', auth="user", website=True)
    def portal_new_measurement(self, **kw):
        # On récupère toutes les lignes actives pour le dropdown
        lignes = request.env['leyfa.ligne'].search([])
        
        return request.render("rail_measurement.template_form_measurement", {
            'lignes': lignes # On transmet la liste au template
        })

    @http.route(['/my/measurement/submit'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def portal_submit_measurement(self, **post):
        # 1. On récupère la valeur brute
        raw_ligne_id = post.get('ligne_id')

        _logger.info("Received ligne_id: %s", raw_ligne_id)

        
        # 2. Sécurité : Si vide ou non trouvé, on peut soit mettre False, soit renvoyer une erreur
        if not raw_ligne_id:
            # Optionnel : renvoyer l'utilisateur sur le formulaire avec un message d'erreur
            return request.redirect('/my/measurement/new?error=no_ligne')

        # 3. On crée l'enregistrement
        measurement = request.env['rail.measurement'].sudo().create({
            # On convertit en int seulement si on a une valeur
            'ligne_id': int(raw_ligne_id), 
            'partner_id': request.env.user.partner_id.id,
        })
        
        return request.redirect('/my/measurement/%s' % measurement.id)

    # Route pour voir le détail et discuter (Chatter)
    @http.route(['/my/measurement/<int:res_id>'], type='http', auth="user", website=True)
    def portal_my_measurement_detail(self, res_id, **kw):
        measurement = request.env['rail.measurement'].browse(res_id)
        # Vérification sommaire de sécurité
        if measurement.partner_id != request.env.user.partner_id:
            return request.redirect('/my')
            
        return request.render("rail_measurement.template_detail_measurement", {
            'measurement': measurement,
            'page_name': 'measurement_detail',
        })
    
    @http.route(['/my/measurements'], type='http', auth="user", website=True)
    def portal_my_measurements(self, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # On récupère toutes les mesures du client
        measurements = request.env['rail.measurement'].search([
            ('partner_id', '=', partner.id)
        ], order='create_date desc')

        values.update({
            'measurements': measurements,
            'page_name': 'measurement_list', # Utile pour le fil d'ariane
        })
        return request.render("rail_measurement.portal_my_measurements", values)
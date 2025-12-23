from odoo import models, fields, api, exceptions, _
from datetime import datetime
import logging
from odoo.exceptions import UserError, ValidationError


class RailMeasurement(models.Model):
    _name = 'rail.measurement'
    _description = 'Prestation de mesure de voie ferrée'
    _rec_name = 'reference'
    _order = 'date_start desc'
    _inherit = ['mail.thread', 'mail.activity.mixin'] 

    name = fields.Char(string='Name', required=True, default='New Measurement')
    reference = fields.Char(
        string='Référence', 
        required=True, 
        copy=False, 
        readonly=True,
        default='New'
    )

    # Champs pour code affaire
    code_affaire = fields.Char(string="Code Affaire", store=True, tracking=True)
    
    nature_mission = fields.Selection([
        ('R', 'R (Relevés seuls)'),
        ('E', 'E (Relevés et études)')
    ], string="Nature Mission", required=True)

    ligne_id = fields.Many2one(
        'leyfa.ligne', 
        string='Ligne Ferroviaire', 
        required=True,
        tracking=True
    )
    exercice_id = fields.Many2one(
        'leyfa.exercice.comptable', 
        string='Exercice Comptable',
        tracking=True
    )
    type_affaire_id = fields.Many2one(
        'leyfa.affaire.type', 
        string="Type d'affaire",
        tracking=True
    )

    type_requires_nature = fields.Boolean(string="Nécessite Nature", default=False)

    @api.onchange('type_affaire_id')
    def _onchange_type_affaire_id(self):
        if self.type_affaire_id:
            # We manually push the value so the UI sees it instantly
            self.type_requires_nature = self.type_affaire_id.requires_nature
        else:
            self.type_requires_nature = False
        
        # If it's no longer required, wipe the value
        if not self.type_requires_nature:
            self.nature_mission = False
    
    # Hidden technical field to track the state and prevent "ping-pong" loops
    last_synced_code = fields.Char(readonly=True)

    def _get_next_available_code(self, prefix):
        """Helper to find the next free number for a given prefix"""
        # We search for the highest code starting with prefix + 3 digits
        # We ignore the current record (self._origin.id) to avoid self-collision
        domain = [
            ('code_affaire', '=like', prefix + '___'),
            ('id', '!=', self._origin.id if hasattr(self, '_origin') else False)
        ]
        existing = self.env['rail.measurement'].search(domain, order='code_affaire desc', limit=1)
        
        if existing:
            try:
                last_seq = int(existing.code_affaire[-3:])
                return f"{prefix}{str(last_seq + 1).zfill(3)}"
            except (ValueError, TypeError):
                return f"{prefix}001"
        return f"{prefix}001"

    @api.onchange('code_affaire', 'exercice_id', 'ligne_id', 'type_affaire_id', 'nature_mission')
    def _sync_leyfa_naming_logic(self):
        # 1. UI Visibility Logic
        if self.type_affaire_id:
            self.type_requires_nature = self.type_affaire_id.requires_nature
        else:
            self.type_requires_nature = False
        if not self.type_requires_nature:
            self.nature_mission = False

        warning_msg = False
        is_manual_code_edit = self.code_affaire != self.last_synced_code
        
        # 2. Case A: Manual Code Entry
        if is_manual_code_edit and self.code_affaire:
            code = self.code_affaire.strip().upper()
            if len(code) >= 5:
                # A1. Parse Exercice
                ex = self.env['leyfa.exercice.comptable'].search([('name', '=', code[0:1])], limit=1)
                if ex: self.exercice_id = ex
                
                # A2. Parse Middle & Nature
                middle = code[1:-3]
                if middle.endswith(('R', 'E')):
                    self.nature_mission = middle[-1]
                    middle = middle[:-1]
                else:
                    self.nature_mission = False
                
                # A3. Parse Ligne & Type
                lines = self.env['leyfa.ligne'].search([])
                for line in lines:
                    if line.surnom and middle.startswith(line.surnom.upper()):
                        self.ligne_id = line
                        type_code = middle[len(line.surnom):]
                        ty = self.env['leyfa.affaire.type'].search([('code', '=', type_code)], limit=1)
                        if ty: self.type_affaire_id = ty
                        break

                # A4. Collision Check: Does this specific code already exist?
                # We check the database for the exact code entered
                collision = self.env['rail.measurement'].search_count([
                    ('code_affaire', '=', code),
                    ('id', '!=', self._origin.id if hasattr(self, '_origin') else False)
                ])
                
                if collision > 0:
                    prefix = code[:-3]
                    new_code = self._get_next_available_code(prefix)
                    warning_msg = {
                        'title': _("Code déjà utilisé"),
                        'message': _("Le code %s existe déjà. Le système a automatiquement généré le numéro suivant : %s.") % (code, new_code)
                    }
                    self.code_affaire = new_code
                else:
                    self.code_affaire = code
            
            self.last_synced_code = self.code_affaire

        # 3. Case B: Field Change (Auto-generation)
        else:
            ex_n = self.exercice_id.name or ""
            li_s = self.ligne_id.surnom or ""
            ty_c = self.type_affaire_id.code or ""
            na_c = self.nature_mission or ""
            
            if ex_n and li_s and ty_c:
                if not self.type_requires_nature or na_c:
                    prefix = f"{ex_n}{li_s}{ty_c}{na_c}".upper()
                    
                    # Regenerate only if the current code is empty or doesn't match fields
                    if not self.code_affaire or not self.code_affaire.startswith(prefix):
                        new_code = self._get_next_available_code(prefix)
                        self.code_affaire = new_code
                        self.last_synced_code = new_code

        # 4. Notify user if there was a collision
        if warning_msg:
            return {'warning': warning_msg}
    
    @api.constrains('code_affaire', 'exercice_id', 'ligne_id', 'type_affaire_id', 'nature_mission')
    def _check_readonly_states(self):
        for record in self:
            # Check if we are in a state other than draft during a modification
            if record.state != 'draft':
                # Note: We check if the field was actually changed in the database
                # context.get('install_mode') prevents issues during module installation
                if not self.env.context.get('install_mode'):
                    raise ValidationError(_("Vous ne pouvez pas modifier le codage d'affaire une fois que la mesure n'est plus en brouillon."))

    def action_generate_code_affaire(self):
        for record in self:
            if not (record.exercice_id and record.ligne_id and record.type_affaire_id):
                raise exceptions.UserError("Veuillez remplir l'exercice, la ligne et le type d'affaire.")
            
            # Determine if we need Nature
            nature_code = ""
            if record.type_affaire_id.requires_nature:
                if not record.nature_mission:
                    raise exceptions.UserError(f"Le type '{record.type_affaire_id.name}' nécessite de préciser la Nature (R ou E).")
                nature_code = record.nature_mission

            # Build the prefix
            prefix = f"{record.exercice_id.name}{record.ligne_id.surnom}{record.type_affaire_id.code}{nature_code}"
            
            # Find the next available number for this specific prefix
            existing_records = self.env['rail.measurement'].search([
                ('code_affaire', '=like', prefix + '___') # Search for prefix + 3 digits
            ], order='code_affaire desc', limit=1)

            next_number = 1
            if existing_records:
                suffix = existing_records.code_affaire[len(prefix):]
                try:
                    next_number = int(suffix) + 1
                except:
                    next_number = 1

            record.code_affaire = f"{prefix}{str(next_number).zfill(3)}"

    # Informations client et commande
    partner_id = fields.Many2one('res.partner', string='Client', required=True)
    sale_order_id = fields.Many2one(
        'sale.order', 
        string='Bon de commande',
        domain="[('partner_id', '=', partner_id)]"
    )
    sale_order_line_id = fields.Many2one('sale.order.line', string='Ligne de commande', readonly=True)
    
    # Informations sur la prestation
    date_start = fields.Datetime(string='Date de début', required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Date de fin')
    duration = fields.Float(string='Durée (heures)', compute='_compute_duration', store=True)
    
    # Localisation
    pk_initial = fields.Float(string='PK Initial (km)', required=True, digits=(10, 3))
    pk_final = fields.Float(string='PK Final (km)', required=True, digits=(10, 3))
    distance = fields.Float(string='Distance (km)', compute='_compute_distance', store=True)
    
    # ========== NOUVEAUTÉ: Types de chariots requis (Devis) ==========
    chariot_type_lines = fields.One2many(
        'rail.measurement.chariot.type.line',
        'measurement_id',
        string='Types de chariots requis',
        help="Définition des besoins en chariots (étape devis)"
    )
    
    # ========== NOUVEAUTÉ: Chariots affectés (Planification) ==========
    # REMPLACEZ VOTRE CHAMP ACTUEL PAR CECI :
    assigned_chariot_ids = fields.Many2many(
        'chariot',
        # On retire le nom de la table explicite ('rail_measurement_chariot...') 
        # car pour un champ calculé, c'est mieux de laisser Odoo gérer.
        string='Chariots affectés',
        compute='_compute_all_assigned_chariots', # <--- LA CLÉ EST ICI
        store=True,                               # <--- INDISPENSABLE POUR LE CALENDRIER
        readonly=True
    )

    # AJOUTEZ CETTE FONCTION JUSTE EN DESSOUS :
    @api.depends('chariot_type_lines.assigned_chariot_ids')
    def _compute_all_assigned_chariots(self):
        for record in self:
            # Cette commande magique récupère tous les chariots de toutes les lignes
            # et les copie dans le champ principal pour le calendrier.
            record.assigned_chariot_ids = record.chariot_type_lines.mapped('assigned_chariot_ids')
    
    
    chariots_assigned = fields.Boolean(
        string='Chariots affectés',
        compute='_compute_chariots_assigned',
        store=True
    )
    
    # Ressources humaines
    team_ids = fields.Many2many(
        'hr.employee', 
        string='Équipe',
        relation='rail_measurement_employee_rel'
    )
    team_leader_id = fields.Many2one('hr.employee', string='Chef d\'équipe')
    
    # État et suivi
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmée'),
        ('planned', 'Planifiée'), # ← Nouveau état après affectation des chariots
        ('in_progress', 'En cours'),
        ('done', 'Terminée'),
        ('cancelled', 'Annulée')
    ], string='État', default='draft', required=True, tracking=True)
    
    # Résultats
    measurement_file = fields.Binary(string='Fichier de mesure')
    measurement_filename = fields.Char(string='Nom du fichier')
    report = fields.Html(string='Rapport')
    notes = fields.Text(string='Notes')
    
    # Facturation
    invoiced = fields.Boolean(string='Facturé', default=False)
    price_unit = fields.Float(string='Prix unitaire (€/km)')
    price_total = fields.Float(string='Prix total', compute='_compute_price_total', store=True)

    @api.depends('assigned_chariot_ids')
    def _compute_chariots_assigned(self):
        for record in self:
            record.chariots_assigned = bool(record.assigned_chariot_ids)

    def _get_measurement_details(self):
        """Génère la description pour la ligne de devis en utilisant les nouveaux modèles"""
        self.ensure_one()
        date_str_start = self.date_start.strftime('%d/%m/%Y') if self.date_start else 'N/A'
        date_str_end = self.date_end.strftime('%d/%m/%Y') if self.date_end else 'N/A'
        
        details = [f"REF: {self.reference}"]
        
        # Info Ligne
        if self.ligne_id:
            details.append(f"Ligne: {self.ligne_id.name} ({self.ligne_id.surnom})")
        
        # Info Type d'affaire
        if self.type_affaire_id:
            details.append(f"Mission: {self.type_affaire_id.name}")
            
        details.append(f"PK: {self.pk_initial} → {self.pk_final} ({self.distance} km)")
        
        if self.chariot_type_lines:
            chariot_info = "Chariots: " + ", ".join([
                f"{line.quantity}x {line.chariot_type_id.name}" 
                for line in self.chariot_type_lines
            ])
            details.append(chariot_info)
        
        details.append(f"Dates: {date_str_start} - {date_str_end}")
        return "\n".join(details)

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Handle Reference generation (Sequence)
        # We do this before super() so the value is included in the initial database write
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = self.env['ir.sequence'].next_by_code('rail.measurement') or 'New'

        # 2. Create the records
        records = super(RailMeasurement, self).create(vals_list)

        # 3. Handle Inverse Link to Sale Order Line
        # We do this after super() because we need the record.id to exist
        for record in records:
            if record.sale_order_line_id:
                # Update the SO line to point back to this specific measurement
                # Use .id to avoid singleton errors if multi-creating
                record.sale_order_line_id.rail_measurement_id = record.id
                
        return records
        
    def write(self, vals):
        result = super(RailMeasurement, self).write(vals)
        
        desc_fields = [
            'pk_initial', 'pk_final', 'track', 'line_name', 
            'date_start', 'team_leader_id', 'chariot_type_lines'
        ]

        logger = logging.getLogger(__name__)
        logger.info(f"RailMeasurement write called with vals: {vals}")
        
        for record in self:
            if record.sale_order_line_id:
                # Sync Quantity if PKs changed
                if ('pk_initial' in vals or 'pk_final' in vals) and record.sale_order_line_id.product_uom_qty != record.distance:
                    record.sale_order_line_id.product_uom_qty = record.distance
                
                # Sync Description if details changed
                if any(f in vals for f in desc_fields):
                    product_desc = record.sale_order_line_id.product_id.get_product_multiline_description_sale()
                    new_desc = f"{product_desc}\n\n{record._get_measurement_details()}"
                    
                    if record.sale_order_line_id.name != new_desc:
                        record.sale_order_line_id.name = new_desc

        return result

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for record in self:
            if record.date_start and record.date_end:
                delta = record.date_end - record.date_start
                record.duration = delta.total_seconds() / 3600.0
            else:
                record.duration = 0.0

    @api.depends('pk_initial', 'pk_final')
    def _compute_distance(self):
        for record in self:
            record.distance = abs(record.pk_final - record.pk_initial)

    @api.depends('distance', 'price_unit')
    def _compute_price_total(self):
        for record in self:
            record.price_total = record.distance * record.price_unit

    @api.constrains('pk_initial', 'pk_final')
    def _check_pk_values(self):
        for record in self:
            if record.state == 'draft':
                continue
            if record.pk_initial < 0 or record.pk_final < 0:
                raise exceptions.ValidationError("Les valeurs de PK ne peuvent pas être négatives.")
            if record.pk_initial == record.pk_final:
                raise exceptions.ValidationError("Le PK initial et final doivent être différents.")

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end and record.date_start:
                if record.date_end < record.date_start:
                    raise exceptions.ValidationError("La date de fin ne peut pas être antérieure à la date de début.")

    def action_confirm(self):
        """Confirme la mesure - vérifie que les types de chariots sont définis"""
        for record in self:
            if not record.chariot_type_lines:
                raise exceptions.ValidationError("Vous devez définir les types de chariots nécessaires avant de confirmer.")
            record.state = 'confirmed'

    def action_validate_assignment(self):
            """
            Valide l'affectation en vérifiant les quantités et les conflits de calendrier.
            Ne modifie PAS l'état physique du chariot (qui reste 'available'),
            mais verrouille la mesure en état 'planned'.
            """
            for record in self:
                # 1. Vérifications de base
                if not record.date_start or not record.date_end:
                    raise exceptions.ValidationError("Veuillez définir les dates de début et de fin avant de valider.")

                if not record.chariot_type_lines:
                    raise exceptions.ValidationError("Aucun besoin en chariots défini.")

                # 2. Vérification ligne par ligne
                for line in record.chariot_type_lines:
                    # A. Vérification de la Quantité
                    assigned_qty = len(line.assigned_chariot_ids)
                    if assigned_qty != line.quantity:
                        raise exceptions.ValidationError(
                            f"Type {line.chariot_type_id.name} : Vous devez affecter exactement "
                            f"{line.quantity} chariot(s). Actuellement : {assigned_qty}."
                        )

                    # B. Vérification de l'état PHYSIQUE (Maintenance, etc.)
                    # Un chariot peut être libre au calendrier mais en panne physiquement
                    broken_carts = line.assigned_chariot_ids.filtered(lambda c: c.state != 'available')
                    if broken_carts:
                        names = ", ".join(broken_carts.mapped('name'))
                        raise exceptions.ValidationError(
                            f"Impossible de valider : les chariots suivants ne sont pas en état de marche "
                            f"(Maintenance ou Hors service) : {names}"
                        )

                    # C. Vérification ultime du CALENDRIER (Conflits)
                    # On s'assure que personne n'a réservé ces chariots sur ces dates entre temps
                    for chariot in line.assigned_chariot_ids:
                        conflicts = self.env['rail.measurement'].search([
                            ('id', '!=', record.id),                    # Pas moi-même
                            ('state', 'not in', ['draft', 'cancelled']), # Mesures actives
                            ('date_start', '<', record.date_end),       # Chevauchement temporel...
                            ('date_end', '>', record.date_start),       # ...stricte
                            # On regarde si ce chariot est utilisé dans les lignes de l'autre mesure
                            ('chariot_type_lines.assigned_chariot_ids', 'in', chariot.id) 
                        ])

                        if conflicts:
                            conflict_list = "\n".join([
                                f"- {c.reference} ({c.date_start} au {c.date_end})" 
                                for c in conflicts
                            ])
                            raise exceptions.ValidationError(
                                f"CONFLIT DE PLANNING :\n"
                                f"Le chariot '{chariot.name}' ne peut pas être validé car il est déjà réservé "
                                f"sur cette période par :\n{conflict_list}"
                            )

                # 3. Validation réussie
                # On ne touche PAS au state du chariot (il reste 'available' pour le filtre de base)
                # La réservation est actée par l'existence de cette mesure en état 'planned'
                record.state = 'planned'

    # --- MODIFIEZ action_done et action_cancel ---
    # Pour libérer les chariots, il faut boucler sur les lignes
    def action_done(self):
        self.write({'state': 'done', 'date_end': fields.Datetime.now()})
        for line in self.chariot_type_lines:
            line.assigned_chariot_ids.write({'state': 'available'})
    
    def action_start(self):
        """Démarre la mesure et enregistre la date réelle"""
        for record in self:
            # 1. Vérification de l'état
            if record.state != 'planned':
                raise exceptions.ValidationError("La mesure doit être planifiée (chariots validés) avant de pouvoir démarrer.")
            
            # 2. Mise à jour de la mesure
            record.write({
                'state': 'in_progress',
                'date_start': fields.Datetime.now() # On capture l'heure exacte du clic
            })

            # 3. Verrouillage des chariots (Sécurité)
            # On parcourt les lignes pour s'assurer que tous les chariots affectés sont bien marqués "En utilisation"
            for line in record.chariot_type_lines:
                if line.assigned_chariot_ids:
                    # Le write s'applique à tous les IDs du recordset Many2many d'un coup
                    line.assigned_chariot_ids.write({'state': 'in_use'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        for line in self.chariot_type_lines:
            line.assigned_chariot_ids.write({'state': 'available'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})


# ========== NOUVEAU MODÈLE: Ligne de type de chariot ==========
class RailMeasurementChariotTypeLine(models.Model):
    _name = 'rail.measurement.chariot.type.line'
    _description = 'Besoin en type de chariot pour une mesure'

    measurement_id = fields.Many2one('rail.measurement', required=True, ondelete='cascade')
    chariot_type_id = fields.Many2one('chariot.type', string='Type requis', required=True)
    quantity = fields.Integer(string='Qté requise', required=True, default=1)
    
    assigned_chariot_ids = fields.Many2many(
        'chariot',
        string='Chariots affectés',
        domain="[('cart_type_id', '=', chariot_type_id), ('state', '=', 'available')]" 
        # Note: Le domain ci-dessus est un filtre de base, 
        # le filtre de date sera appliqué via l'onchange ci-dessous.
    )

    # === ALGORITHME DE DÉTECTION DE CONFLIT ===
    @api.onchange('chariot_type_id')
    def _onchange_compute_allowed_chariots(self):
        """
        Met à jour le domaine pour n'afficher que les chariots libres
        sur la période de la mesure parente.
        """
        if self.measurement_id.state != 'draft' and (not self.env.context.get('check_avail_start') or not self.env.context.get('check_avail_end')):
                    raise UserError(
                        "✋ Action impossible !\n\n"
                        "Veuillez d'abord définir la 'Date de début' et la 'Date de fin' "
                        "dans le formulaire (en haut) pour que je puisse calculer "
                        "les disponibilités des chariots."
                    )
        
        if not self.measurement_id.date_start or not self.measurement_id.date_end:
            return {}

        start = self.measurement_id.date_start
        end = self.measurement_id.date_end

        # 1. Trouver toutes les mesures qui chevauchent la nôtre
        # (Start A < End B) et (End A > Start B)
        overlapping_measurements = self.env['rail.measurement'].search([
            ('id', '!=', self.measurement_id.id.origin), # Ne pas se compter soi-même
            ('state', 'not in', ['draft', 'cancelled']),  # Ignorer les brouillons/annulés
            ('date_start', '<', end),
            ('date_end', '>', start),
        ])

        # 2. Récupérer les IDs des chariots pris par ces mesures
        busy_chariot_ids = overlapping_measurements.mapped('assigned_chariot_ids').ids

        # 3. Construire le domaine
        return {
            'domain': {
                'assigned_chariot_ids': [
                    ('cart_type_id', '=', self.chariot_type_id.id), # Bon type
                    ('state', '=', 'available'),                    # Physiquement opérationnel
                    ('id', 'not in', busy_chariot_ids)              # Pas déjà réservé
                ]
            }
        }
    
    # === SÉCURITÉ CÔTÉ SERVEUR ===
    # Au cas où l'utilisateur force la saisie ou change les dates après coup
    @api.constrains('assigned_chariot_ids')
    def _check_availability_conflicts(self):
        for line in self:
            start = line.measurement_id.date_start
            end = line.measurement_id.date_end
            
            for chariot in line.assigned_chariot_ids:
                # Chercher conflit
                conflicts = self.env['rail.measurement'].search([
                    ('id', '!=', line.measurement_id.id),
                    ('state', 'not in', ['draft', 'cancelled']),
                    ('date_start', '<', end),
                    ('date_end', '>', start),
                    ('assigned_chariot_ids', 'in', chariot.id)
                ])
                
                if conflicts:
                    dates = f"{conflicts[0].date_start} - {conflicts[0].date_end}"
                    raise exceptions.ValidationError(
                        f"Le chariot {chariot.name} est déjà réservé sur la mesure "
                        f"{conflicts[0].reference} ({dates})."
                    )
    
    @api.constrains('quantity')
    def _check_quantity(self):
        for record in self:
            if record.quantity < 1:
                raise exceptions.ValidationError("La quantité doit être au moins 1.")


class RailMeasurementWizardChariotTypeLine(models.TransientModel):
    _name = 'rail.measurement.wizard.chariot.type.line'
    _description = 'Ligne de type de chariot dans le wizard'

    wizard_id = fields.Many2one(
        'rail.measurement.wizard',
        required=True,
        ondelete='cascade'
    )
    chariot_type_id = fields.Many2one('chariot.type', string='Type de chariot', required=True)
    quantity = fields.Integer(string='Quantité', required=True, default=1)

# ========== WIZARD: Affectation des chariots ==========
class RailMeasurementAssignChariotWizard(models.TransientModel):
    _name = 'rail.measurement.assign.chariot.wizard'
    _description = 'Assistant d\'affectation de chariots physiques'

    measurement_id = fields.Many2one('rail.measurement', string='Mesure', required=True)
    chariot_type_lines = fields.One2many(
        related='measurement_id.chariot_type_lines',
        string='Besoins',
        readonly=True
    )
    assignment_line_ids = fields.One2many(
        'rail.measurement.assign.chariot.line.wizard',
        'wizard_id',
        string='Affectations'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'measurement_id' in res:
            measurement = self.env['rail.measurement'].browse(res['measurement_id'])
            lines = []
            for type_line in measurement.chariot_type_lines:
                # Chercher les chariots disponibles de ce type
                available_chariots = self.env['chariot'].search([
                    ('cart_type_id', '=', type_line.chariot_type_id.id),
                    ('state', '=', 'available')
                ], limit=type_line.quantity)
                
                for chariot in available_chariots:
                    lines.append((0, 0, {
                        'chariot_type_id': type_line.chariot_type_id.id,
                        'chariot_id': chariot.id,
                    }))
            
            res['assignment_line_ids'] = lines
        return res

    def action_assign(self):
        """Affecte les chariots à la mesure"""
        self.ensure_one()
        chariot_ids = self.assignment_line_ids.mapped('chariot_id')
        self.measurement_id.assigned_chariot_ids = [(6, 0, chariot_ids.ids)]
        return {'type': 'ir.actions.act_window_close'}


class RailMeasurementAssignChariotLineWizard(models.TransientModel):
    _name = 'rail.measurement.assign.chariot.line.wizard'
    _description = 'Ligne d\'affectation de chariot'

    wizard_id = fields.Many2one(
        'rail.measurement.assign.chariot.wizard',
        required=True,
        ondelete='cascade'
    )
    chariot_type_id = fields.Many2one('chariot.type', string='Type requis', readonly=True)
    chariot_id = fields.Many2one(
        'chariot',
        string='Chariot physique',
        required=True,
        domain="[('cart_type_id', '=', chariot_type_id), ('state', '=', 'available')]"
    )


# ========== WIZARD: Création de mesure depuis devis ==========
class RailMeasurementWizard(models.TransientModel):
    _name = 'rail.measurement.wizard'
    _description = 'Assistant de liaison de mesure'

    mode = fields.Selection([
        ('create', 'Créer une nouvelle mesure (Ouvrira le formulaire complet)'),
        ('link', 'Lier une mesure existante'),
    ], default='create', required=True, string="Action")

    # Only used for the 'Link' mode
    measurement_id = fields.Many2one(
        'rail.measurement',
        string='Mesure existante',
        domain="[('sale_order_line_id','=',False), ('partner_id', '=', partner_id)]"
    )

    # Technical fields to pass context
    sale_order_line_id = fields.Many2one('sale.order.line', string='Ligne de commande')
    partner_id = fields.Many2one('res.partner', string='Client')

    def action_apply(self):
        self.ensure_one()

        if self.mode == 'link':
            if not self.measurement_id:
                raise exceptions.UserError("Veuillez sélectionner une mesure existante.")
            
            # 1. Link the existing measurement to the Sales Order Line
            self.measurement_id.write({'sale_order_line_id': self.sale_order_line_id.id})
            self.sale_order_line_id.rail_measurement_id = self.measurement_id.id
            return {'type': 'ir.actions.act_window_close'}

        else:
            # 2. Create Mode: Redirect to a NEW form view of rail.measurement
            return {
                'type': 'ir.actions.act_window',
                'name': 'Nouvelle Mesure de Voie',
                'res_model': 'rail.measurement',
                'view_mode': 'form',
                'target': 'new', # Opens in a popup/sub-window
                'context': {
                    'default_sale_order_line_id': self.sale_order_line_id.id,
                    'default_partner_id': self.partner_id.id,
                    'default_sale_order_id': self.sale_order_line_id.order_id.id,
                    'default_price_unit': self.sale_order_line_id.price_unit,
                }
            }

# ========== Héritages existants ==========
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rail_measurement = fields.Boolean(
        string='Prestation de mesure ferroviaire',
        help='Cochez cette case pour les produits de type mesure de voie ferrée'
    )
    rail_measurement_price_per_km = fields.Float(
        string='Prix par km (€)',
        help='Prix unitaire par kilomètre pour les mesures de voie'
    )
    rail_measurement_count = fields.Integer(
        string='Nombre de mesures',
        compute='_compute_rail_measurement_count'
    )

    def _compute_rail_measurement_count(self):
        for tmpl in self:
            tmpl.rail_measurement_count = self.env['rail.measurement'].search_count([
                ('sale_order_line_id.product_id.product_tmpl_id', '=', tmpl.id)
            ])

    def action_view_rail_measurements(self):
        self.ensure_one()
        return {
            'name': 'Historique des Mesures',
            'type': 'ir.actions.act_window',
            'res_model': 'rail.measurement',
            'view_mode': 'list,form',
            'domain': [('sale_order_line_id.product_id.product_tmpl_id', '=', self.id)],
            'context': {'create': False}
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    measurement_ids = fields.One2many('rail.measurement', 'sale_order_id', string='Mesures de voie')
    measurement_count = fields.Integer(string='Nombre de mesures', compute='_compute_measurement_count')

    @api.depends('measurement_ids')
    def _compute_measurement_count(self):
        for order in self:
            order.measurement_count = len(order.measurement_ids)

    def action_view_measurements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mesures de voie',
            'res_model': 'rail.measurement',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id
            }
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rail_measurement_id = fields.Many2one('rail.measurement', string='Mesure de voie', copy=False)
    is_rail_measurement = fields.Boolean(related='product_id.is_rail_measurement', string='Est une mesure ferroviaire')

    rail_pk_initial = fields.Float(related='rail_measurement_id.pk_initial', readonly=False, string="PK Début")
    rail_pk_final = fields.Float(related='rail_measurement_id.pk_final', readonly=False, string="PK Fin")
    # rail_ligne_id = fields.Char(related='rail_measurement_id.ligne_id', readonly=False, string="Voie")
    rail_date_start = fields.Datetime(related='rail_measurement_id.date_start', readonly=False, string="Date Début")
    rail_team_leader_id = fields.Many2one(related='rail_measurement_id.team_leader_id', readonly=False, string="Chef d'équipe")
    rail_reference = fields.Char(related='rail_measurement_id.reference', readonly=True, string="Réf. Mesure")

    def action_open_rail_measurement_form(self):
        self.ensure_one()
        if not self.rail_measurement_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mesure de voie',
            'res_model': 'rail.measurement',
            'res_id': self.rail_measurement_id.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context),
        }

    @api.onchange('product_id', 'product_uom_qty')
    def _onchange_product_id_rail_measurement(self):
        if self.product_id and self.product_id.is_rail_measurement:
            if self.product_id.product_tmpl_id.rail_measurement_price_per_km:
                self.price_unit = self.product_id.product_tmpl_id.rail_measurement_price_per_km

    def action_create_rail_measurement(self):
        self.ensure_one()
        
        if not self.product_id.is_rail_measurement:
            raise exceptions.UserError("Ce produit n'est pas une prestation de mesure ferroviaire.")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configurer la mesure de voie',
            'res_model': 'rail.measurement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_sale_order_line_id': self.id,
                'default_partner_id': self.order_id.partner_id.id,
                'default_price_unit': self.price_unit,
            }
        }
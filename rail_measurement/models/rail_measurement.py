from odoo import models, fields, api, exceptions, _
from datetime import datetime
import logging
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from datetime import timedelta, time, datetime

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
    nature_mission = fields.Selection([
            ('R', 'R (Relevés seuls)'),
            ('E', 'E (Relevés et études)')
        ], 
        string="Nature Mission",
        tracking=True
    )

    type_requires_nature = fields.Boolean(string="Nécessite Nature", default=False)


    ## Champs additionnels pour le marché (Excel)
    desc_typologie_detail = fields.Selection([
            ('gop', 'GOP'),
            ('modernisation', 'MODERNISATION'),
            ('patrimonial', 'PATRIMONIAL'),
            ('bdml', 'BDML'),
            ('oge', 'OGE')
        ], string="Typologie détail")
    
    desc_nature_travaux = fields.Selection([
        ('rvb', 'RVB'),
        ('rav', 'RAV'),
        ('rb', 'RB'),
        ('rt', 'RT'),
        ('rr', 'RR'),
        ('rb_rt', 'RB+RT'),
        ('rr_rb', 'RR+RB'),
        ('rb_relevage', 'RB+ RELEVAGE'),
        ('entretien', 'ENTRETIEN'),
        ('supp_defauts', 'SUPP. DEFAUTS'),
        ('pb_gabarits', 'PB GABARITS'),
        ('epure_carnet', 'EPURE - CARNET'),
        ('rr_rt', 'RR+RT'),
        ('rt_relevage', 'RT + RELEVAGE'),
    ], string="Nature des travaux")

    desc_methodologie = fields.Selection([
        ('sr_nat', 'SR NAT'),
        ('sr_zd', 'SR ZD'),
        ('hors_suite', 'HORS SUITE'),
        ('archive', 'ARCHIVE'),
        ('base_absolue', 'BASE ABSOLUE'),
        ('base_relative', 'BASE RELATIVE'),
        ('mrt', 'MRT'),
    ], string="Méthodologie")

    desc_annee = fields.Integer(
        string="Année", 
        default=lambda self: fields.Date.today().year,
        help="Année de référence du projet"
    )

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
            logger = logging.getLogger(__name__)
            logger.info(f"&&&&&&&&&&&&& {self.last_synced_code} vs {self.code_affaire} &&&&&&&&&&&&&")
            self.last_synced_code = self.code_affaire
            logger.info(f"&&&&&&&&&&&&& {self.last_synced_code} vs {self.code_affaire} &&&&&&&&&&&&&")
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
            logger = logging.getLogger(__name__)
            logger.info("Auto-generating code_affaire based on field changes.")
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
            if record.state != 'presale':
                # Note: We check if the field was actually changed in the database
                # context.get('install_mode') prevents issues during module installation
                if not self.env.context.get('install_mode'):
                    raise ValidationError(_(f"Vous ne pouvez pas modifier le codage d'affaire une fois que la mesure n'est plus en brouillon."))

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
    sale_order_line_etudes_id = fields.Many2one('sale.order.line', string='Ligne de commande études', readonly=True)

    ## Voie
    voie_ids = fields.Many2many(
        'leyfa.type.voie',           # Modèle de destination
        'rail_measurement_voie_rel', # NOM DE LA TABLE DE LIAISON (à ajouter)
        'measurement_id',            # Colonne 1 (ID de ce modèle)
        'voie_id',                   # Colonne 2 (ID du type de voie)
        string="Voies de circulation"
    )
    voie_count = fields.Integer(string="Nombre de voies", compute='_compute_voie_count')
    
    @api.depends('voie_ids')
    def _compute_voie_count(self):
        for ligne in self:
            ligne.voie_count = len(ligne.voie_ids)

    # Informations sur la prestation
    date_start = fields.Date(string='Date de début')
    date_end = fields.Date(string='Date de fin')

    @api.onchange('date_start', 'date_end')
    def _onchange_dates_week_rounding(self):
        """ Arrondit visuellement après la sélection """
        if self.date_start:
            # weekday() : 0=Lundi, 6=Dimanche
            self.date_start = self.date_start - timedelta(days=self.date_start.weekday())
        if self.date_end:
            self.date_end = self.date_end + timedelta(days=6 - self.date_end.weekday())
    
    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            # Set date_end to 7 days after date_start by default
            self.date_end = self.date_start + timedelta(days=7)

    # --- 2. LA SÉCURITÉ (Bloque la sauvegarde si incorrect) ---
    @api.constrains('date_start', 'date_end')
    def _check_dates_weeks(self):
        for record in self:
            if record.date_start and record.date_start.weekday() != 0:
                raise ValidationError(_("La date de début doit obligatoirement être un Lundi."))
            if record.date_end and record.date_end.weekday() != 6:
                raise ValidationError(_("La date de fin doit obligatoirement être un Dimanche."))
    

    # Localisation
    pk_initial = fields.Float(string='PK Initial (km)', digits=(10, 0), default=None)
    pk_final = fields.Float(string='PK Final (km)', digits=(10, 0), default=None)

    lineaire = fields.Float(
        string='Linéaire', digits=(10, 0), store=True, readonly=False
    )
    lineaire_releve = fields.Float(
        string='Linéaire relevé', digits=(10, 0), store=True, readonly=False
    )
    lineaire_etudes = fields.Float(
        string='Linéaire études', digits=(10, 0), store=True, readonly=False
    )

    # Facturation
    invoiced = fields.Boolean(string='Facturé', default=False)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # PRIX UNITAIRE : calculé si KM ou TOTAL changent
    price_unit = fields.Monetary(
        string='Prix unitaire (€/km)', 
        compute='_compute_price_unit', store=True, readonly=False
    )

    # PRIX TOTAL : calculé si PRIX UNITAIRE change
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    price_releve = fields.Monetary(
        string='Montant relevé', store=True, readonly=False
    )
    price_etudes = fields.Monetary(
        string='Montant études', store=True, readonly=False
    )
    price_total = fields.Monetary(
        string='Prix total', store=True, readonly=False, compute='_compute_price_total'
    )
    @api.depends('price_releve', 'price_etudes', 'nature_mission')
    def _compute_price_total(self):
        for rec in self:
            if rec.nature_mission == 'R' or not rec.nature_mission:
                rec.price_total = rec.price_releve
            elif rec.nature_mission == 'E':
                rec.price_total = rec.price_releve + rec.price_etudes
    
    price_releve_daily = fields.Float(
        string='Prix journalier relevé', 
        compute='_compute_daily_prices',
        digits=(16, 5)
    )
    price_etudes_daily = fields.Float(
        string='Prix journalier études', 
        compute='_compute_daily_prices',
        digits=(16, 5)
    )
    price_total_daily = fields.Float(
        string='Prix journalier total', 
        compute='_compute_daily_prices',
        digits=(16, 5)
    )

    @api.depends('price_releve', 'price_etudes', 'price_total', 'total_nb_periods')
    def _compute_daily_prices(self):
        for rec in self:
            # On récupère le nombre de périodes (créneaux)
            nb = rec.total_nb_periods
            if nb > 0:
                rec.price_releve_daily = rec.price_releve / nb
                rec.price_etudes_daily = rec.price_etudes / nb
                rec.price_total_daily = rec.price_total / nb
            else:
                rec.price_releve_daily = 0.0
                rec.price_etudes_daily = 0.0
                rec.price_total_daily = 0.0
    
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
        string='Chariots affectés booleén',
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
    

    ### Etats et suivi ###
    # État et suivi
    state = fields.Selection([
        ('presale', 'Pré-vente'),
        ('production', 'Production'),
        ('measure', 'Mesure'),
        ('study', 'Études'),
        ('invoicing', 'Facturation'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé')
    ], string='État', default='presale', required=True, tracking=True,
       compute='_compute_state', store=True, readonly=False)

    @api.depends('sale_order_id.state')
    def _compute_state(self):
        for record in self:
            so_state = record.sale_order_id.state
            
            # CAS 1 : La commande est annulée
            if so_state == 'cancel':
                record.state = 'cancelled'
            
            # CAS 2 : La commande est en Devis (Quotation) ou Envoyée
            # On force le retour en 'presale' même si on était en 'cancelled' ou en 'production'
            elif so_state in ['draft', 'sent']:
                record.state = 'presale'
            
            # CAS 3 : La commande est confirmée (Bon de commande)
            # On passe en 'production' seulement si on vient du début du flux (presale ou cancelled)
            elif so_state in ['sale', 'done']:
                if record.state in ['presale', 'cancelled']:
                    record.state = 'production'
            
            # Sinon, on garde l'état actuel (pour ne pas écraser l'avancement "planned", "measured", etc.)
            else:
                if not record.state:
                    record.state = 'presale'

    sale_substate = fields.Selection([
        ('waiting', 'En attente de devis'),
        ('draft', 'Devis'),
        ('sent', 'Devis envoyé'),
        ('sale', 'Bon de commande'),
        ('done', 'Verrouillé'),
        ('cancel', 'Annulé'),
    ], string="État de la Vente", compute='_compute_sale_substate', store=True)

    @api.depends('sale_order_id.state')
    def _compute_sale_substate(self):
        for record in self:
            if record.sale_order_id:
                record.sale_substate = record.sale_order_id.state
            else:
                record.sale_substate = 'waiting'

    prod_substate = fields.Selection([
        ('mission', 'Réception Mission'),
        ('team', 'Constitution Équipe'),
        ('urgence', 'Vérification Urgence'),
        ('material', 'Vérification Matériel'),
        ('assigned', 'Chariots Affectés')
    ], string="Étape Production")
    
    measure_substate = fields.Selection([
        ('daily', 'Production Terrain'),
        ('checking', 'Contrôle Avancement'),
        ('files', 'Génération Fichiers')
    ], string="Étape Mesure")

    study_substate = fields.Selection([
        ('reception', 'Réception Mesures'),
        ('analysis', 'Analyse & Étude'),
        ('validation', 'Validation Finale')
    ], string="Étape Étude")

    view_level = fields.Selection([
        ('overview', 'Vue Macro (Global)'),
        ('sale_detail', 'Détail : Vente'),
        ('prod_detail', 'Détail : Production'),
        ('measure_detail', 'Détail : Mesure'),
        ('study_detail', 'Détail : Études')
    ], default='overview', string="Niveau de Vue")

    mermaid_graph = fields.Text(compute='_compute_mermaid_graph')

    @api.depends('state', 'prod_substate', 'measure_substate', 'study_substate', 'view_level', 'sale_order_id.state')
    def _compute_mermaid_graph(self):
        for rec in self:
            if rec.view_level == 'overview':
                rec.mermaid_graph = rec._generate_macro_graph()
            elif rec.view_level == 'sale_detail':
                rec.mermaid_graph = rec._generate_sale_micro()
            elif rec.view_level == 'prod_detail':
                rec.mermaid_graph = rec._generate_prod_micro()
            elif rec.view_level == 'measure_detail':
                rec.mermaid_graph = rec._generate_measure_micro()
            else:
                rec.mermaid_graph = rec._generate_study_micro()

    def _generate_macro_graph(self):
        lines = [
            "graph LR",
            "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
            "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
            "classDef invisible fill:none,stroke:none,color:none",
            "",
            "  %% Ligne 1 : Flux nominal",
            "  PRESALE[Pré-Vente] --> PROD[Production]",
            "  PROD --> MEASURE[Mesure]",
            "  MEASURE --> STUDY[Études]",
            "  STUDY --> INV[Facturation]",
            "  INV --> DONE((Fin))",
            "",
            "  %% Ligne 2 : Annulation",
            "  %% ~~~ crée un lien invisible qui force CANCELLED à rester sous PRESALE",
            "  PRESALE ~~~ EMPTY[ ]",
            "  EMPTY -.-> CANCELLED[Annulé]",
            "",
            "  class EMPTY invisible"
        ]

        mapping = {
            'presale': 'PRESALE', 'production': 'PROD', 'measure': 'MEASURE', 
            'study': 'STUDY', 'invoicing': 'INV', 'done': 'DONE'
        }

        # 1. Utilisation de ton helper
        graph_content = self._apply_styles(lines, mapping, self.state, 
                                           ['presale', 'production', 'measure', 'study', 'invoicing', 'done'])
        
        res_lines = graph_content.split('\n')
        
        # 2. Gestion de la surbrillance
        if self.state == 'cancelled':
            res_lines.append("  class CANCELLED active")
            res_lines.append("  class PRESALE,PROD,MEASURE,STUDY,INV,DONE done")
        else:
            res_lines.append("  class CANCELLED done")

        return "\n".join(res_lines)

    def _generate_sale_micro(self):
        """Graphe basé sur les états de sale.order_id, incluant l'attente et le regroupement final"""
        lines = [
            "graph LR", 
            "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px", 
            "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
            "WAIT[Attente Devis] --> DRAFT[Devis]",
            "DRAFT --> SENT[Envoyé]",
            "SENT --> FINAL([Vente Confirmée])"
        ]

        # Mapping des états techniques vers les nœuds Mermaid
        mapping = {
            'waiting': 'WAIT',
            'draft': 'DRAFT',
            'sent': 'SENT',
            'confirmed_all': 'FINAL'
        }

        # Détermination de l'état actuel pour le graphe
        if not self.sale_order_id:
            current_sale_state = 'waiting'
        else:
            raw_state = self.sale_order_id.state
            # Regroupement des états finaux de vente
            if raw_state in ['sale', 'done']:
                current_sale_state = 'confirmed_all'
            else:
                current_sale_state = raw_state

        # Application des styles selon l'ordre chronologique
        return self._apply_styles(
            lines, 
            mapping, 
            current_sale_state, 
            ['waiting', 'draft', 'sent', 'confirmed_all']
        )

    def _generate_prod_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                 "M1(Mission) --> M2[Équipe]", "M2 --> M3{Matériel?}", "M3 -- Non --> M3_U[Urgence]", "M3_U --> M4[Chariots]", "M3 -- Oui --> M4", "M4 --> M5((Prêt))"]
        mapping = {'mission': 'M1', 'team': 'M2', 'material': 'M3', 'urgence': 'M3_U', 'assigned': 'M4', 'final': 'M5'}
        return self._apply_styles(lines, mapping, self.prod_substate, ['mission', 'team', 'material', 'urgence', 'assigned'])

    def _generate_measure_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                 "ME1[Terrain] --> ME2{Fini?}", "ME2 -- Non --> ME1", "ME2 -- Oui --> ME3[Fichiers]", "ME3 --> ME4((OK))"]
        mapping = {'daily': 'ME1', 'checking': 'ME2', 'files': 'ME3', 'final': 'ME4'}
        return self._apply_styles(lines, mapping, self.measure_substate, ['daily', 'checking', 'files'])

    def _generate_study_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                 "S1[Réception] --> S2[Analyse]", "S2 --> S3{Validation}", "S3 -- KO --> S1", "S3 -- OK --> S4((Fin))"]
        mapping = {'reception': 'S1', 'analysis': 'S2', 'validation': 'S3', 'final': 'S4'}
        return self._apply_styles(lines, mapping, self.study_substate, ['reception', 'analysis', 'validation'])

    def _apply_styles(self, lines, mapping, current, order):
        if self.state == 'cancelled':
            for node in mapping.values():
                lines.append(f"class {node} done")
            return "\n".join(lines)
        
        if current in order:
            idx = order.index(current)
            for i, key in enumerate(order):
                node = mapping.get(key)
                if node:
                    if i < idx: lines.append(f"class {node} done")
                    elif i == idx: lines.append(f"class {node} active")
        return "\n".join(lines)
    
    state_tip = fields.Html(compute='_compute_state_tip')

    @api.depends('state', 'sale_substate', 'prod_substate', 'measure_substate', 'study_substate')
    def _compute_state_tip(self):
        # Dictionnaire des conseils par sous-état
        tips = {
            # Vente (sale_substate) - Quand state == 'presale'
            'waiting': """<b>Action :</b> Aucun devis n'est lié à cette mesure. Ajoutez un produit de mesure ferroviaire à un devis et liez cette mesure à ce dernier
                        en cliquant sur le bouton <b>+</b> sur la ligne du devis.
                        <br/><i>Note : Le client du devis doit être identique à celui de la mesure.</i>""",
            'draft': """<b>Devis :</b> Le devis est en cours de rédaction. Renseignez tous les champs nécessaires à son élaboration, puis envoyez-le au client ou 
                        confirmez-le directement.""",
            'sent': "📧 <b>En attente :</b> Le devis a été envoyé au client. En attente de signature pour lancer la production.",
            'sale': "🚀 <b>Confirmé :</b> La vente est validée ! Le pôle Production peut maintenant prendre le relais.",
            
            # Production (prod_substate) - Quand state == 'production'
            'mission': "📄 <b>Fiche Mission :</b> Vérifiez que les accès aux emprises ferroviaires sont bien autorisés pour ces PK.",
            'team': "👷 <b>Équipe :</b> Assurez-vous que les agents possèdent les habilitations sécurité requises.",
            'material': "🔧 <b>Matériel :</b> Vérifiez l'étalonnage des capteurs laser et la charge des batteries.",
            'assigned': "🚛 <b>Logistique :</b> Les chariots sont affectés. Le départ terrain est prêt.",

            # Mesure (measure_substate) - Quand state == 'measure'
            'daily': "🛰️ <b>Terrain :</b> Saisie des données brutes en cours. Veillez à la stabilité du signal GNSS.",
            'checking': "🧐 <b>Contrôle :</b> Vérification de la cohérence des courbes de mesure avant de quitter le site.",
            'files': "💾 <b>Fichiers :</b> Génération des fichiers .csv et .raw pour le pôle Études.",

            # Étude (study_substate) - Quand state == 'study'
            'reception': "📥 <b>Réception :</b> Intégration des fichiers terrain dans le logiciel d'analyse.",
            'analysis': "📉 <b>Analyse :</b> Calcul des flèches et des dévers. Identification des points hors tolérance.",
            'validation': "⚖️ <b>Expertise :</b> Validation finale par l'expert technique avant facturation.",
            
            # Autres
            'invoicing': "💰 <b>Facturation :</b> Les livrables sont envoyés. La facture peut être émise.",
            'done': "🏁 <b>Terminé :</b> Mission clôturée et archivée.",
            'cancelled': """⚠️ <b>Annulé :</b> Le processus a été annulé. Cela peut se produire si la mesure a été retirée 
                    de sa vente associée, ou si cette dernière a été annulée.
                    <br/>Si vous souhaitez relancer la mesure, vous pouvez la remettre dans l'état pré-vente."""
        }

        for record in self:
            # Sélection de la clé de message appropriée
            key = False
            if record.state == 'presale':
                key = record.sale_substate
            elif record.state == 'production':
                key = record.prod_substate
            elif record.state == 'measure':
                key = record.measure_substate
            elif record.state == 'study':
                key = record.study_substate
            else:
                key = record.state

            # Récupération du message
            msg = tips.get(key, "<i>Aucun conseil spécifique pour cette étape.</i>")
            
            # Formatage de la boîte (Alert Bootstrap)
            record.state_tip = f'''
                <div class="alert alert-info d-flex align-items-center m-0" 
                     style="border-left: 5px solid #714B67; background-color: #f8f9fa;">
                    <div class="flex-grow-1">{msg}</div>
                </div>
            '''

    ### PLANNING ###
    planning_ids = fields.One2many('rail.measurement.planning', 'measurement_id', string="Planning Hebdomadaire")

    def action_generate_planning(self):
        """
        Synchronise les lignes de planning avec les dates de mission :
        - Ajoute les nouvelles semaines
        - Supprime les semaines hors intervalle
        - Conserve les données des semaines déjà existantes
        """
        self.ensure_one()
        if not self.date_start or not self.date_end:
            return

        # 1. Normalisation des dates (Lundi de début / Dimanche de fin)
        d1 = self.date_start - timedelta(days=self.date_start.weekday())
        d2 = self.date_end + timedelta(days=6 - self.date_end.weekday())

        # 2. Identifier les semaines cibles (celles qui DOIVENT exister)
        target_weeks = []
        current = d1
        while current <= d2:
            year, week, _ = current.isocalendar()
            # On stocke (année, semaine, date_lundi)
            target_weeks.append((year, week, current))
            current += timedelta(days=7)

        target_keys = [(y, w) for y, w, d in target_weeks]

        # 3. SUPPRESSION : On retire les semaines qui ne sont plus dans l'intervalle
        to_delete = self.planning_ids.filtered(
            lambda p: (p.year, p.week_number) not in target_keys
        )
        if to_delete:
            to_delete.unlink()

        # 4. AJOUT : On crée les semaines manquantes
        existing_keys = {(p.year, p.week_number) for p in self.planning_ids}
        new_vals = []
        
        for year, week, date_from in target_weeks:
            if (year, week) not in existing_keys:
                new_vals.append({
                    'measurement_id': self.id,
                    'year': year,
                    'week_number': week,
                    'date_from': date_from,
                    'date_to': date_from + timedelta(days=6),
                    # Les jours J/N restent à 'none' par défaut
                })

        if new_vals:
            self.env['rail.measurement.planning'].create(new_vals)

        # 5. Mise à jour des dates sur la fiche (si l'utilisateur avait mis des mauvais jours)
        if self.date_start != d1 or self.date_end != d2:
            self.write({'date_start': d1, 'date_end': d2})

        return True
    
    total_nb_periods = fields.Integer(
        string="Nombre de pédiodes", 
        compute="_compute_total_nb_periods"
    )

    @api.depends('planning_ids.nb_periods')
    def _compute_total_nb_periods(self):
        for rec in self:
            # On somme le champ nb_periods de chaque ligne du planning
            rec.total_nb_periods = sum(rec.planning_ids.mapped('nb_periods'))

    
    display_weeks = fields.Char(compute='_compute_display_weeks', string="Période")

    @api.depends('date_start', 'date_end')
    def _compute_display_weeks(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                y1, w1, _ = rec.date_start.isocalendar()
                y2, w2, _ = rec.date_end.isocalendar()
                # Format S01/26
                rec.display_weeks = f"S{w1:02}/{str(y1)[2:]} → S{w2:02}/{str(y2)[2:]}"
            else:
                rec.display_weeks = "Choisir les dates..."





    ###########
    # Résultats
    measurement_file = fields.Binary(string='Fichier de mesure')
    measurement_filename = fields.Char(string='Nom du fichier')
    report = fields.Html(string='Rapport')
    notes = fields.Text(string='Notes')

    @api.depends('assigned_chariot_ids')
    def _compute_chariots_assigned(self):
        for record in self:
            record.chariots_assigned = bool(record.assigned_chariot_ids)

    def _get_measurement_details(self):
        """Génère la description pour la ligne de devis en utilisant les nouveaux modèles"""
        self.ensure_one()        
        details = []

        if self.code_affaire:
            details.append(f"Code Affaire: {self.code_affaire}")
        if self.date_start:
            if self.date_start and self.date_end:
                details.append(f"Dates: {self.date_start.strftime('%d/%m/%Y')} - {self.date_end.strftime('%d/%m/%Y')}")
            else:
                details.append(f"Date de début: {self.date_start.strftime('%d/%m/%Y')}")
        
        # Info Ligne
        if self.ligne_id:
            details.append(f"Ligne: {self.ligne_id.name} ({self.ligne_id.surnom})")
        # Info voies
        if self.voie_count > 0:
            voie_names = " / ".join(self.voie_ids.mapped('name'))
            details.append(f"Voies: {voie_names}")
        # Info PK
        if not (self.pk_initial == 0 and self.pk_final == 0):
            details.append(f"PK: {self.pk_initial} → {self.pk_final}")

        # Info Type d'affaire
        if self.type_affaire_id:
            details.append(f"Mission: {self.type_affaire_id.name}")
        
        return "\n".join(details)

    def update_sale_order_line(self):
        """Met à jour les DEUX lignes de commande liées (Relevé et Études)"""
        for record in self:
            # On ne synchronise que si le devis est en brouillon
            if record.sale_order_id and record.sale_order_id.state == 'draft':                
                # --- LIGNE 1 : RELEVÉ (sale_order_line_id) ---
                if record.sale_order_line_id:
                    # On ajoute une mention [RELEVÉ] pour la clarté sur le devis
                    new_name = f"[RELEVÉ {record.reference}]\n\n{record._get_measurement_details()}"
                    unit = self.env.ref('rail_measurement.product_uom_periode', raise_if_not_found=False) if record.total_nb_periods > 0 else self.env.ref('rail_measurement.uom_none', raise_if_not_found=False)

                    record.sale_order_line_id.with_context(from_measurement_module=True).write({
                        'name': new_name,
                        'product_uom_qty': record.total_nb_periods if record.total_nb_periods > 0 else 1.0,
                        'price_unit': record.price_releve_daily if record.total_nb_periods > 0 else record.price_releve,
                        'product_uom_id': unit,
                    })
                
                # Si le type a changé et ne demande plus de ligne études, on la supprime
                if record.sale_order_line_etudes_id and (record.nature_mission == 'R' or not record.nature_mission):
                    line_to_delete = record.sale_order_line_etudes_id
                    record.sale_order_line_etudes_id = False 
                    # On appelle unlink avec le contexte qui "donne la permission"
                    line_to_delete.with_context(allow_study_deletion=True).unlink()
                
                if not self.env.context.get('delete_study_line') and record.nature_mission == 'E' and not record.sale_order_line_etudes_id:
                    etudes_sol = self.env['sale.order.line'].create({
                        'order_id': record.sale_order_id.id,
                        'product_id': record.sale_order_line_id.product_id.id,
                        'rail_measurement_id': record.id, # Pour garder la trace
                        # On peut initialiser le nom ici, mais update_sale_order_line le fera proprement
                    })
                    record.sale_order_line_etudes_id = etudes_sol.id

                # --- LIGNE 2 : ÉTUDES (sale_order_line_etudes_id) ---
                if record.sale_order_line_etudes_id:
                    # On ajoute une mention [ÉTUDES]
                    new_name_etudes = f"[ÉTUDES {record.reference}]"
                    unit = self.env.ref('rail_measurement.product_uom_periode', raise_if_not_found=False) if record.total_nb_periods > 0 else self.env.ref('rail_measurement.uom_none', raise_if_not_found=False)
                    logger = logging.getLogger(__name__)
                    logger.info(f"Updating study line for measurement {record.reference} with unit {unit.name} and qty {record.total_nb_periods}")

                    record.sale_order_line_etudes_id.with_context(from_measurement_module=True).write({
                        'name': new_name_etudes,
                        'product_uom_qty': record.total_nb_periods if record.total_nb_periods > 0 else 1.0,
                        'price_unit': record.price_etudes_daily if record.total_nb_periods > 0 else record.price_etudes,
                        'product_uom_id': unit,
                    })
                

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Génération de la référence (Séquence)
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = self.env['ir.sequence'].next_by_code('rail.measurement') or 'New'

        # 2. Création des enregistrements
        records = super(RailMeasurement, self).create(vals_list)

        # 3. Lien inverse et mise à jour de la description de la ligne de commande
        records.update_sale_order_line()
        return records

    def write(self, vals):
        # Appel au super pour enregistrer les modifications
        result = super(RailMeasurement, self).write(vals)

        # Si on modifie des champs qui impactent la description ou le lien
        self.update_sale_order_line()
        return result
    
    def unlink(self):
        """ 
        Lors de la suppression d'une mesure, on remet la description 
        standard sur la ligne de commande liée avant de supprimer.
        """
        for record in self:
            if record.sale_order_line_id:
                standard_desc = record.sale_order_line_id.product_id.get_product_multiline_description_sale()
                record.sale_order_line_id.with_context(from_measurement_module=True).write({
                    'name': standard_desc,
                    'product_uom_qty': 1.0,
                    'price_unit': 0.0,
                    'product_uom_id': self.env.ref('rail_measurement.uom_none', raise_if_not_found=False),
                })
                record.sale_order_line_etudes_id.with_context(allow_study_deletion=True).unlink()
        return super(RailMeasurement, self).unlink()

    # @api.constrains('pk_initial', 'pk_final')
    # def _check_pk_values(self):
    #     for record in self:
    #         if record.state == 'draft':
    #             continue
    #         if record.pk_initial < 0 or record.pk_final < 0:
    #             raise exceptions.ValidationError("Les valeurs de PK ne peuvent pas être négatives.")
    #         if record.pk_initial == record.pk_final:
    #             raise exceptions.ValidationError("Le PK initial et final doivent être différents.")

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
                            ('state', 'not in', ['presale', 'cancelled']), # Mesures actives
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
            # record.write({
            #     'state': 'in_progress',
            #     'date_start': fields.Datetime.now() # On capture l'heure exacte du clic
            # })

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
        if self.sale_order_id :
            self.write({'state': 'presale', 'sale_substate': self.sale_order_id.state})
        else:
            self.write({'state': 'presale', 'sale_substate': 'waiting'})


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
        if self.measurement_id.state != 'presale' and (not self.env.context.get('check_avail_start') or not self.env.context.get('check_avail_end')):
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
            ('state', 'not in', ['presale', 'cancelled']),  # Ignorer les brouillons/annulés
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
                    ('state', 'not in', ['presale', 'cancelled']),
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
        domain="[('sale_order_line_id','=',False), ('partner_id', '=', partner_id), ('state', 'in', ['presale'])]",
    )

    # Technical fields to pass context
    sale_order_line_id = fields.Many2one('sale.order.line', string='Ligne de commande')
    partner_id = fields.Many2one('res.partner', string='Client')

    def action_apply(self):
        self.ensure_one()

        if self.mode == 'link':
            if not self.measurement_id:
                raise exceptions.UserError("Veuillez sélectionner une mesure existante.")
            
            measurement = self.measurement_id
            main_sol = self.sale_order_line_id
            quotation = main_sol.order_id

            # 1. Lien de la mesure à la ligne principale (Relevé) et au devis
            measurement.write({
                'sale_order_line_id': main_sol.id,
                'sale_order_id': quotation.id,
            })
            
            # 2. Lien inverse sur la SOL principale
            main_sol.rail_measurement_id = measurement.id

            # 4. Synchronisation des noms, prix et quantités pour les deux lignes
            measurement.update_sale_order_line()

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

    is_main_measurement_line = fields.Boolean(
        compute="_compute_is_main_measurement_line",
        string="Est la ligne de mesure principale"
    )

    @api.depends('rail_measurement_id.sale_order_line_id')
    def _compute_is_main_measurement_line(self):
        for line in self:
            # On vérifie si cette ligne est bien celle enregistrée comme 'principale' sur la mesure
            if line.rail_measurement_id and line.rail_measurement_id.sale_order_line_id.id == line._origin.id:
                line.is_main_measurement_line = True
            else:
                line.is_main_measurement_line = False
    
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

    def action_remove_rail_measurement(self):
        self.ensure_one()
        if self.rail_measurement_id:
            # On supprime la ligne d'étude si elle existe
            if self.rail_measurement_id.sale_order_line_etudes_id:
                etudes_line = self.rail_measurement_id.sale_order_line_etudes_id
                etudes_line.with_context(allow_study_deletion=True).unlink()
            
            # 1. On nettoie d'abord la fiche de mesure
            # On lui retire les liens vers la vente et on peut aussi forcer le contexte ici
            self.rail_measurement_id.with_context(delete_study_line=True).write({
                'sale_order_id': False,
                'sale_order_line_id': False,
                'sale_order_line_etudes_id': False,
            })

            # 2. On nettoie la ligne de commande actuelle (self)
            # On utilise le contexte pour autoriser la modification du nom/prix/qté
            standard_name = self.product_id.get_product_multiline_description_sale()
            
            self.with_context(from_measurement_module=True).write({
                'rail_measurement_id': False,
                'name': standard_name,
                'product_uom_qty': 1.0,
                'price_unit': self.product_id.list_price,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def unlink(self):
        # On vérifie si on n'est pas dans un "unlink automatique" autorisé
        if not self.env.context.get('allow_study_deletion'):
            for line in self:
                # Si la ligne est liée à une mesure EN TANT QUE ligne d'études
                m = line.rail_measurement_id
                if m and line.id == m.sale_order_line_etudes_id.id:
                    raise exceptions.UserError(_(
                        "Action impossible : La ligne d'études est gérée automatiquement par le formulaire mesure.\n"
                        "👉 Pour la retirer, annulez les modifications apportées au devis et modifiez la 'Nature de la mission' sur la fiche de mesure associée."
                    ))
                
        for line in self:
            # On récupère la mesure liée
            m = line.rail_measurement_id
            if m:
                if line.id == m.sale_order_line_id.id:
                    m.with_context(delete_study_line=True).write({
                        'state': 'presale',
                        'sale_order_id': False,
                        'sale_order_line_id': False,
                        'sale_order_line_etudes_id': False,
                        'sale_substate': 'waiting'
                    })
                    line.rail_measurement_id = False
                elif line.id == m.sale_order_line_etudes_id.id:
                    m.with_context(delete_study_line=True).write({'sale_order_line_etudes_id': False})

        return super(SaleOrderLine, self).unlink()

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
    
    # Sécurité côté serveur pour empêcher la modification directe de la quantité ou du prix
    def write(self, vals):
        # 1. On vérifie si l'utilisateur essaie de toucher au prix ou à la quantité
        restricted_fields = ['product_uom_qty', 'price_unit']

        if any(field in vals for field in restricted_fields):
            # 2. On vérifie si la modification vient du module (via le contexte)
            if self.is_rail_measurement and not self.env.context.get('from_measurement_module'):
                for line in self:
                    # 3. Si la ligne est liée à une mesure, on bloque
                    if line.rail_measurement_id:
                        raise exceptions.UserError(_(
                            "Action impossible : La quantité et le prix de cette ligne sont synchronisés avec le module de mesure.\n"
                            "👉 Pour modifier ces valeurs, annulez les modifications apportées au devis et modifiez directement la fiche de mesure associée."
                        ))
                    else:
                        raise exceptions.UserError(_(
                            "Action impossible : La quantité et le prix de cette ligne sont synchronisés avec un module de mesure.\n"
                            "👉 Pour modifier ces valeurs, annulez les modifications apportées au devis et liez une fiche de mesure à cette ligne de devis."
                        ))
        
        return super(SaleOrderLine, self).write(vals)

class RailMeasurementPlanning(models.Model):
    _name = 'rail.measurement.planning'
    _description = 'Planning Hebdomadaire de Mesure'
    _order = 'year, week_number'

    measurement_id = fields.Many2one('rail.measurement', ondelete='cascade')
    
    # Infos de la semaine
    year = fields.Integer("Année")
    week_number = fields.Integer("Semaine")
    week_label = fields.Char("S", compute="_compute_week_label")
    date_from = fields.Date("Du")
    date_to = fields.Date("Au")

    # Slots de travail (J/N)
    PLAN_OPT = [('none', '-'), ('day', 'J'), ('night', 'N')]
    
    mon = fields.Selection(PLAN_OPT, string="Lun", default='none')
    tue = fields.Selection(PLAN_OPT, string="Mar", default='none')
    wed = fields.Selection(PLAN_OPT, string="Mer", default='none')
    thu = fields.Selection(PLAN_OPT, string="Jeu", default='none')
    fri = fields.Selection(PLAN_OPT, string="Ven", default='none')
    sat = fields.Selection(PLAN_OPT, string="Sam", default='none')
    sun = fields.Selection(PLAN_OPT, string="Dim", default='none')

    @api.depends('year', 'week_number')
    def _compute_week_label(self):
        for rec in self:
            rec.week_label = f"S{rec.week_number}/{rec.year % 100:02d}"
    
    def action_copy_to_all(self):
        self.ensure_one()
        # 1. On prépare les valeurs à copier
        vals = {
            'mon': self.mon,
            'tue': self.tue,
            'wed': self.wed,
            'thu': self.thu,
            'fri': self.fri,
            'sat': self.sat,
            'sun': self.sun,
        }
        # 2. On récupère toutes les autres lignes de la même mesure
        # self.measurement_id.planning_ids contient toutes les lignes, on enlève self (l'actuelle)
        other_weeks = self.measurement_id.planning_ids - self
        
        # 3. On écrit les valeurs sur toutes les autres lignes d'un coup (très rapide)
        if other_weeks:
            other_weeks.write(vals)
        
        self._compute_nb_periods()
        self.measurement_id.update_sale_order_line()

        return True
    
    nb_periods = fields.Integer(string="Nb de créneaux", compute="_compute_nb_periods")
    @api.depends('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
    def _compute_nb_periods(self):
        for rec in self:
            count = 0
            for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']:
                if rec[day] in ['day', 'night']:
                    count += 1
            rec.nb_periods = count
    
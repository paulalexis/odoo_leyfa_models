from odoo import models, fields, api, exceptions, _, Command
from datetime import datetime
import logging
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from datetime import timedelta, time, datetime
import base64, openpyxl, io

class RailMeasurement(models.Model):
    _name = 'rail.measurement'
    _description = 'Prestation de mesure de voie ferrée'
    _rec_name = 'reference'
    _order = 'date_start desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _compute_display_name(self):
        for record in self:
            name = record.reference or ""
            if record.code_affaire:
                record.display_name = f"[{record.code_affaire}] {name}"
            else:
                record.display_name = name

    name = fields.Char(string='Name', required=True, default='New Measurement')
    reference = fields.Char(
        string='Référence', 
        required=True, 
        copy=False, 
        readonly=True,
        default='New'
    )

    # Champs pour code affaire
    code_affaire = fields.Char(string="Code Affaire", store=True, tracking=True,
                                help="Code d'affaire de la forme ELLLTTXXX où :\n" \
                                "E = Exercice Comptable\n" \
                                "LLL = Ligne Ferroviaire (surnom)\n" \
                                "TT = Type d'affaire\n" \
                                "XXX = Numéro unique (automatique)")

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

    type_requires_nature = fields.Boolean(string="Nécessite Nature", default=False, tracking=True)

    ## Champs additionnels pour le marché (Excel)
    desc_typologie_detail = fields.Selection([
        ('gop', 'GOP'),
        ('modernisation', 'MODERNISATION'),
        ('patrimonial', 'PATRIMONIAL'),
        ('bdml', 'BDML'),
        ('oge', 'OGE')
    ], string="Typologie détail", tracking=True)
    
    desc_nature_travaux = fields.Selection([
        ('rvb', 'RVB'),
        ('rvb_hs', 'RVB - HS'),
        ('rav', 'RAV'),
        ('rb', 'RB'),
        ('rt', 'RT'),
        ('rr', 'RR'),
        ('rb_rt', 'RB+RT'),
        ('rr_rb', 'RR+RB'),
        ('rrn_hs', 'RRN - HS'),
        ('rb_relevage', 'RB+ RELEVAGE'),
        ('rr_rt', 'RR+RT'),
        ('rt_relevage', 'RT + RELEVAGE'),
    ], string="Nature des travaux", tracking=True)

    desc_methodologie = fields.Selection([
        ('sr_hp', 'SR Haute Performance'),
        ('sr_hr', 'SR Haut Rendement'),
        ('sr_hc', 'SR Haute Contrainte'),
        ('hors_suite', 'HORS SUITE'),
        ('archive', 'ARCHIVE'),
        ('base_absolue', 'BASE ABSOLUE'),
        ('base_relative', 'BASE RELATIVE'),
        ('mrt', 'MRT'),
    ], string="Méthodologie", tracking=True)

    desc_annee = fields.Integer(
        string="Année", 
        # default=lambda self: fields.Date.today().year,
        help="Année de référence du projet",
        tracking=True
    )
    desc_observations = fields.Text(string="Observations", tracking=True)

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
            # ('code_affaire', '=like', prefix + '___'), On ne cherche pas à ce que les affaires soient regroupé... étrange mais process actuel
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
            self.last_synced_code = self.code_affaire
            code = self.code_affaire.strip().upper()
            if len(code) >= 5:
                # A1. Parse Exercice
                ex = self.env['leyfa.exercice.comptable'].search([('name', '=', code[0:1])], limit=1)
                if ex: self.exercice_id = ex
                print(f"Parsed Exercice: {ex.name if ex else 'None'}")
                
                # A2. Parse Middle & Nature
                middle = code[1:] if code[-3:].isdigit() is False else code[1:-3]
                if middle.endswith(('R', 'E')) and not middle[-3] == 'MOE':
                    self.nature_mission = middle[-1]
                    middle = middle[:-1]
                else:
                    self.nature_mission = False
                print(f"Parsed Middle: {middle}, Nature: {self.nature_mission}")
                
                # A3. Parse Ligne & Type
                lines = self.env['leyfa.ligne'].search([])
                for line in lines:
                    if line.surnom and middle[0:len(line.surnom)] == line.surnom.upper():
                        self.ligne_id = line
                        type_code = middle[len(line.surnom):]
                        ty = self.env['leyfa.affaire.type'].search([('code', '=', type_code)], limit=1)
                        if ty: self.type_affaire_id = ty
                        print(f"Parsed Ligne: {line.surnom}, Type: {type_code}")
                        break

                # A4. Collision Check: Does this specific code already exist?
                # We check the database for the exact code entered
                

                if code[-3:].isdigit() is False:
                    new_code = self._get_next_available_code(code)
                    self.code_affaire = new_code
                else:
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
    partner_id = fields.Many2one('res.partner', string='Client', required=True, tracking=True)
    sale_order_id = fields.Many2one(
        'sale.order', 
        string='Bon de commande',
        domain="[('partner_id', '=', partner_id)]",
        tracking=True
    )

    ## Voie
    voie_ids = fields.Many2many(
        'leyfa.type.voie',           # Modèle de destination
        'rail_measurement_voie_rel', # NOM DE LA TABLE DE LIAISON (à ajouter)
        'measurement_id',            # Colonne 1 (ID de ce modèle)
        'voie_id',                   # Colonne 2 (ID du type de voie)
        string="Voies de circulation",
        tracking=True
    )
    voie_count = fields.Integer(string="Nombre de voies", compute='_compute_voie_count')
    
    @api.depends('voie_ids')
    def _compute_voie_count(self):
        for ligne in self:
            ligne.voie_count = len(ligne.voie_ids)

    # Informations sur la prestation
    date_start = fields.Date(string='Date de début', tracking=True)
    date_end = fields.Date(string='Date de fin', tracking=True)

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

    # Facturation
    invoiced = fields.Boolean(string='Facturé', default=False)

    # PRIX UNITAIRE : calculé si KM ou TOTAL changent
    price_unit = fields.Monetary(
        string='Prix unitaire (€/km)', 
        compute='_compute_price_unit', store=True, readonly=False
    )

    # PRIX TOTAL : calculé si PRIX UNITAIRE change
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    price_releve = fields.Monetary(
        string='Montant relevé', store=True, readonly=False, tracking=True
    )
    price_etudes = fields.Monetary(
        string='Montant études', store=True, readonly=False, tracking=True
    )
    price_total = fields.Monetary(
        string='Prix total', store=True, readonly=False, compute='_compute_price_total', tracking=True
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

    ### Etats et suivi ###
    # État et suivi
    state = fields.Selection([
        ('presale', 'Pré-vente'),
        ('production', 'Planification'),
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
                    record.prod_substate = 'mission'
            
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
        ('urgence', 'Vérification Urgence'),
        ('material', 'Vérification Matériel'),
        ('assigned', 'Chariots Affectés')
    ], string="Étape Production")
    
    measure_substate = fields.Selection([
        ('waiting_prod', 'En Attente'),
        ('reperage', 'Repérage'),
        ('geometrie', 'Mesure Géométrie'),
        ('position', 'Mesure Position'),
        ('catenaire', 'Mesure Caténaire'),
        ('done', 'Mesure Terminée'),
    ], string="Étape Mesure")

    study_substate = fields.Selection([
        ('reception', 'Réception Mesures'),
        ('analysis', 'Analyse & Étude'),
        ('validation', 'Validation Finale')
    ], string="Étape Étude")

    view_level = fields.Selection([
        ('overview', 'Vue Macro (Global)'),
        ('sale_detail', 'Détail : Vente'),
        ('prod_detail', 'Détail : Planification'),
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
            "  PRESALE[Pré-Vente] --> PROD[Planification]",
            "  subgraph Production",
            "  PROD --> MEASURE[Mesure]",
            "  MEASURE --> STUDY[Études]",
            "  end",
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
                 "M1[Fiche Mission] --> M2{Matériel ?}", "M2 -- Non --> M2_U[Demande de matériel]", "M2_U --> M2", "M2 -- Oui --> M3([Chariots réservés])", "M3 -.-> M4[Production quotidienne]"]
        mapping = {'mission': 'M1', 'material': 'M2', 'urgence': 'M2_U', 'assigned': 'M3', 'final': 'M4'}
        return self._apply_styles(lines, mapping, self.prod_substate, ['mission', 'material', 'urgence', 'assigned'])

    def _generate_measure_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                 "ME1[En attente] --> ME2[Repérage]", "subgraph Production quotidienne", "ME2 --> ME3[Mesure Géométrie]", "ME3 --> ME4[Mesure Position]", "ME4 --> ME5[Mesure Caténaire]", "end", "ME5 --> ME6((Fin))"]
        mapping = {'waiting_prod': 'ME1', 'reperage': 'ME2', 'geometrie': 'ME3', 'position': 'ME4', 'catenaire': 'ME5', 'done': 'ME6'}
        return self._apply_styles(lines, mapping, self.measure_substate, ['waiting_prod', 'reperage', 'geometrie', 'position', 'catenaire', 'done'])

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
            'presale_waiting': """<b>Action :</b> Aucun devis n'est lié à cette mesure. Ajoutez un produit de mesure ferroviaire à un devis et liez cette mesure à ce dernier
                        en cliquant sur le bouton <b>+</b> sur la ligne du devis.
                        <br/><i>Note : Le client du devis doit être identique à celui de la mesure.</i>""",
            'presale_draft': """<b>Devis :</b> Le devis est en cours de rédaction. Renseignez tous les champs nécessaires à son élaboration, puis envoyez-le au client ou 
                        confirmez-le directement.""",
            'presale_sent': "<b>En attente :</b> Le devis a été envoyé au client. En attente de signature pour lancer la production.",
            'presale_sale': "<b>Confirmé :</b> La vente est validée ! Le pôle Production peut maintenant prendre le relais.",
            
            # Production (prod_substate) - Quand state == 'production'
            'production_mission': "<b>Fiche Mission :</b> Complétez et vérifiez la fiche mission. Pensez à ajouter les agents (et leur planning) et le matériel nécessaire. Ensuite, confirmez.",
            'production_material': "<b>Affectation des chariots :</b> Répondez aux besoins définis dans la fiche mission en affectant les chariots.",
            'production_assigned': "<b>Plannifié :</b> Les chariots sont affectés et la mesure a été ajoutée à la production quotidienne.",
            'production_urgence': "<b>En attente de chariots :</b> Libérez des chariots ailleurs pour répondre à la demande en matériel (pas encore codé).",

            # Mesure (measure_substate) - Quand state == 'measure'
            'measure_waiting_prod': f"<b>En attente :</b> La mesure n'a pas encore commencé. Elle commencera le {self.date_start.strftime('%d/%m/%Y')}." if self.date_start else "",
            'measure_daily': "🛰️ <b>Terrain :</b> Saisie des données brutes en cours. Veillez à la stabilité du signal GNSS.",
            'measure_checking': "🧐 <b>Contrôle :</b> Vérification de la cohérence des courbes de mesure avant de quitter le site.",
            'measure_files': "💾 <b>Fichiers :</b> Génération des fichiers .csv et .raw pour le pôle Études.",

            # Étude (study_substate) - Quand state == 'study'
            'study_reception': "📥 <b>Réception :</b> Intégration des fichiers terrain dans le logiciel d'analyse.",
            'study_analysis': "📉 <b>Analyse :</b> Calcul des flèches et des dévers. Identification des points hors tolérance.",
            'study_validation': "⚖️ <b>Expertise :</b> Validation finale par l'expert technique avant facturation.",
            
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
                key = record.state + '_' + record.sale_substate
            elif record.state == 'production':
                key = record.state + '_' + record.prod_substate
            elif record.state == 'measure':
                key = record.state + '_' + record.measure_substate
            elif record.state == 'study':
                key = record.state + '_' + record.study_substate
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

    show_chatter = fields.Boolean(string='Afficher le suivi', default=False)

    ### VENTE & DEVIS ###
    ## Consistance
    # Tableau 1
    consistance_lines = fields.One2many(
        'rail.measurement.consistance.line',
        'measurement_id',
        string='Consistance de la mesure'
    )

    total_theo_consistance = fields.Float(string="Total Théorique", compute="_compute_consistance_totals", digits=(7, 0))
    total_releve_consistance = fields.Float(string="Total Relevé", compute="_compute_consistance_totals", digits=(7, 0))

    @api.depends('consistance_lines.pkd', 'consistance_lines.pkf', 'consistance_lines.maj_deb', 'consistance_lines.maj_fin')
    def _compute_consistance_totals(self):
        for reg in self:
            theo = 0.0
            releve = 0.0
            for line in reg.consistance_lines:
                diff = abs(line.pkf - line.pkd)
                theo += diff
                releve += (diff + line.maj_deb + line.maj_fin)
            reg.total_theo_consistance = theo
            reg.total_releve_consistance = releve

    default_ligne_id = fields.Many2one(
        'leyfa.ligne', 
        string='Ligne Ferroviaire par défaut', 
        required=True,
        tracking=True,
        default=lambda self: self.ligne_id
    )

    @api.onchange('consistance_lines')
    def _onchange_line_ids_ligne_inheritance(self):
        current_default = self.default_ligne_id

        for line in self.consistance_lines:
            if not line.ligne_id:
                # Si la ligne est nouvelle ou vide, on applique la valeur "courante"
                line.ligne_id = current_default
            else:
                # Si l'utilisateur a modifié la ligne manuellement, 
                current_default = line.ligne_id


    def action_open_import_wizard(self):
        return {
            'name': _('Importer la consistance'),
            'type': 'ir.actions.act_window',
            'res_model': 'rail.consistance.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_measurement_id': self.id}
        }

    # Tableau 2 (cibles et plaquettes provisoires)
    cible_line_ids = fields.One2many(
        'rail.measurement.cible.line', 
        'measurement_id', 
        string='Matériel de repérage'
    )

    @api.onchange('type_affaire_id')
    def _onchange_cibles_logic(self):
        surnom = self.type_affaire_id.code if self.type_affaire_id else False
        
        target_types = ['cible', 'mire']
        if surnom == 'P': 
            target_types.append('prov')
        if surnom in ['R', 'C']: 
            target_types.append('courbe')

        commands = []
        current_lines = self.cible_line_ids
        seen_types = set()

        # 1. Identifier les lignes à supprimer ou garder
        for line in current_lines:
            # On utilise ._origin pour les records déjà sauvés si besoin
            l_type = line.line_type
            
            if l_type not in target_types or l_type in seen_types:
                # Suppression : si la ligne existe en base, delete, sinon simple retrait
                if line._origin:
                    commands.append(Command.delete(line._origin.id))
                else:
                    commands.append(Command.clear()) # Nettoie le cache virtuel
            else:
                seen_types.add(l_type)

        # 2. Ajouter les manquants
        mapping_names = {
            'cible': 'Cibles MT40174',
            'prov': 'Plaquettes provisoires chainage',
            'courbe': 'Plaquettes courbe définitives',
            'mire': 'Mires sur supports caténaires'
        }

        for t in target_types:
            if t not in seen_types:
                commands.append(Command.create({
                    'name': mapping_names.get(t, ""),
                    'line_type': t,
                    'qty': 0
                }))

        if commands:
            self.cible_line_ids = commands


    quai_line_ids = fields.One2many(
        'rail.measurement.quai.line',
        'measurement_id',
        string='Quais à mesurer'
    )


    ## DEVIS

    itinerary_duration = fields.Selection([
        ('gt7', '> 7h'), ('6_7', '[6h - 7h]'),
        ('5_6', '[5h - 6h['), ('4_5', '[04h - 05h]'), ('3h30_4', '[03h30 - 04h['),
        ('3_3h30', '[03h00 - 03h30['), ('2h30_3', '[02h30 - 03h['),
        ('2_2h30', '[02h00- 02h30['), ('lt2', '< 2h'),
    ], string="TTE", help="Temps de Travail Effectif", default='4_5', tracking=True)


    def change_product_qty(self, default_code, qty):
        """ 
        Met à jour la quantité d'un produit spécifique dans le devis associé.
        :param default_code: Le code interne (default_code) du produit (ex: '1.5')
        :param qty: La nouvelle quantité à appliquer
        """
        self.ensure_one()
        if not self.sale_order_id:
            return False

        # On cherche la ligne de commande qui correspond au produit ayant ce code
        # On utilise .filtered() pour être sûr de ne modifier que ce devis précis
        order_line = self.sale_order_id.order_line.filtered(
            lambda l: l.product_id.default_code == default_code
        )

        if order_line:
            # Si la ligne existe, on met à jour la quantité (on prend la première si doublons)
            order_line[0].write({'product_uom_qty': qty})
            return True
        
        return False

    def update_sale_order(self):
        nb_km_releve = int(self.total_releve_consistance / 1000.0)

        ## FORFAIT

        ## 1.1
        self.change_product_qty('1.1', nb_km_releve/2)
        ## 1.2 et 1.5
        if self.type_affaire_id.code == 'P':
            # DEBUG : let's print all cible lines:
            for line in self.cible_line_ids:
                logging.getLogger(__name__).info(f"Cible Line: {line.line_type} - Qty: {line.qty}") 
            prov_line = self.cible_line_ids.filtered(lambda l: l.line_type == 'prov')
            logging.getLogger(__name__).info(f"Type d'affaire : {self.cible_line_ids}::::{prov_line.qty}")
            prov_qty = prov_line.qty if prov_line else 0
            self.change_product_qty('1.2', prov_qty)
            self.change_product_qty('1.5', prov_qty)
        if self.type_affaire_id.code in ['R', 'C']:
            courbe_line = self.cible_line_ids.filtered(lambda l: l.line_type == 'courbe')
            courbe_qty = courbe_line.qty if courbe_line else 0
            self.change_product_qty('1.2', courbe_qty)
            self.change_product_qty('1.5', courbe_qty)
        
        # 2.1
        self.change_product_qty('2.1', nb_km_releve)
        self.change_product_qty('3.1', nb_km_releve/2)
        self.change_product_qty('3.2', nb_km_releve)
        self.change_product_qty('3.3', nb_km_releve)
    

    ##### PRODUCTION & PLANIFICATION #####
    existing_chariot_type_ids = fields.Many2many(
        'chariot.type', 
        compute='_compute_existing_chariot_types',
        string="Types déjà utilisés"
    )

    equipe_id_1 = fields.Many2one('equipe.terrain', string="Équipe n°1", help="L'équipe doit être disponible.")
    equipe_id_2 = fields.Many2one('equipe.terrain', string="Équipe n°2", help="L'équipe doit être disponible.")

    # Champ de contrôle pour l'affichage
    has_second_team = fields.Boolean(
        string="Ajouter une deuxième équipe ?", 
        default=False
    )

    # Dans rail_measurement.py

    unavailable_equipe_ids = fields.Many2many(
        'equipe.terrain', 
        compute='_compute_unavailable_equipe_ids',
        help="Technique : liste des équipes occupées sur cette période"
    )

    @api.depends('date_start', 'date_end')
    def _compute_unavailable_equipe_ids(self):
        for rec in self:
            if not rec.date_start or not rec.date_end:
                rec.unavailable_equipe_ids = [(6, 0, [])]
                continue
            
            # On cherche les conflits de dates sur les autres mesures
            domain = [
                ('id', '!=', rec._origin.id if rec._origin else rec.id),
                ('date_start', '<', rec.date_end),
                ('date_end', '>', rec.date_start),
                ('state', '!=', 'cancel'),
            ]
            conflicts = self.env['rail.measurement'].search(domain)
            
            # On cumule les IDs des équipes 1 et 2 déjà prises
            booked_ids = conflicts.mapped('equipe_id_1').ids + conflicts.mapped('equipe_id_2').ids
            rec.unavailable_equipe_ids = [(6, 0, list(set(booked_ids)))]

    @api.constrains('date_start', 'date_end', 'equipe_id_1', 'equipe_id_2', 'state')
    def _check_teams_availability(self):
        for rec in self:
            # On ne vérifie que si les dates et au moins une équipe sont renseignées
            if not rec.date_start or not rec.date_end or rec.state == 'cancel':
                continue
            
            # 1. Vérification : Équipe 1 ne doit pas être Équipe 2
            if rec.has_second_team and rec.equipe_id_1 and rec.equipe_id_2:
                if rec.equipe_id_1 == rec.equipe_id_2:
                    raise ValidationError(_("Erreur : L'équipe n°1 et l'équipe n°2 ne peuvent pas être la même."))

            # 2. Préparation des équipes à vérifier
            teams_to_check = []
            if rec.equipe_id_1:
                teams_to_check.append(rec.equipe_id_1.id)
            if rec.has_second_team and rec.equipe_id_2:
                teams_to_check.append(rec.equipe_id_2.id)

            if not teams_to_check:
                continue

            # 3. Recherche de conflits sur d'autres mesures
            domain = [
                ('id', '!=', rec.id), # Pas la mesure actuelle
                ('state', '!=', 'cancel'),
                ('date_start', '<', rec.date_end), # Chevauchement de dates
                ('date_end', '>', rec.date_start),
                '|',
                ('equipe_id_1', 'in', teams_to_check),
                ('equipe_id_2', 'in', teams_to_check),
            ]
            
            conflict = self.env['rail.measurement'].search(domain, limit=1)

            if conflict:
                # Identification de l'équipe qui pose problème pour un message précis
                team_name = ""
                if rec.equipe_id_1 and (conflict.equipe_id_1 == rec.equipe_id_1 or conflict.equipe_id_2 == rec.equipe_id_1):
                    team_name = rec.equipe_id_1.name
                else:
                    team_name = rec.equipe_id_2.name

                raise ValidationError(_(
                    "Conflit de planification !\n\n"
                    "L'équipe '%s' est déjà réservée sur l'affaire '%s' "
                    "du %s au %s.\n\n"
                    "Veuillez choisir une autre équipe ou modifier les dates."
                ) % (
                    team_name,
                    conflict.code_affaire or conflict.name,
                    conflict.date_start.strftime('%d/%m/%Y'),
                    conflict.date_end.strftime('%d/%m/%Y')
                ))

    @api.depends('chariot_type_lines.chariot_type_id')
    def _compute_existing_chariot_types(self):
        for rec in self:
            # On récupère tous les IDs sélectionnés dans les lignes
            rec.existing_chariot_type_ids = rec.chariot_type_lines.mapped('chariot_type_id')

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
        
        for year, week, date_start in target_weeks:
            if (year, week) not in existing_keys:
                new_vals.append({
                    'measurement_id': self.id,
                    'year': year,
                    'week_number': week,
                    'date_start': date_start,
                    'date_end': date_start + timedelta(days=6),
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

    ### MESURES
    reperage_file = fields.Binary(string='Fichier de mesure -- Repérage')
    reperage_filename = fields.Char(string='Nom du fichier -- Repérage')
    report = fields.Html(string='Rapport')
    notes = fields.Text(string='Notes')

    day_file_ids = fields.One2many(
        'rail.measurement.day.file', 
        'measurement_id', 
        string="Fichiers terrain"
    )

    avancement_start = fields.Float(string='PK début relevé (km)', digits=(10, 3))
    avancement_end = fields.Float(string='PK fin relevé (km)', digits=(10, 3))
    
    avancement_pourcentage = fields.Float(
        string='Progression',
        # compute='_compute_avancement_pourcentage',
        store=True
    )

    # @api.depends('avancement_start', 'avancement_end', 'pk_initial', 'pk_final')
    # def _compute_avancement_pourcentage(self):
    #     for rec in self:
    #         total_dist = abs(rec.pk_final - rec.pk_initial)
    #         if total_dist > 0:
    #             progress_dist = abs(rec.avancement_end - rec.avancement_start)
    #             percentage = (progress_dist / total_dist) * 100
    #             rec.avancement_pourcentage = min(percentage, 100.0)
    #         else:
    #             rec.avancement_pourcentage = 0.0
    
    @api.model
    def action_upload_measurement_file(self):
        logging.getLogger(__name__).info("Opening measurement file import wizard")
        return {
            'name': 'Importer un fichier de mesure',
            'type': 'ir.actions.act_window',
            'res_model': 'rail.file.import.wizard',
            'view_mode': 'form',
            # 'views': [[ID_DE_LA_VUE, 'TYPE']] 
            # Utiliser False permet de prendre la vue par défaut
            'views': [[False, 'form']], 
            'target': 'new',
            'context': self.env.context,
        }



    ###########
    # Résultats

    @api.depends('assigned_chariot_ids')
    def _compute_chariots_assigned(self):
        for record in self:
            record.chariots_assigned = bool(record.assigned_chariot_ids)


    @api.model_create_multi
    def create(self, vals_list):
        # 1. Génération de la référence (Séquence)
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = self.env['ir.sequence'].next_by_code('rail.measurement') or 'New'
            
        # 2. Création des enregistrements
        records = super(RailMeasurement, self).create(vals_list)

        if records.sale_order_id:
            records.sale_order_id.measurement_id = records.id
        
        # 3. Lien inverse et mise à jour de la description de la ligne de commande
        # records.update_sale_order_line()
        return records

    def write(self, vals):
        # Appel au super pour enregistrer les modifications
        result = super(RailMeasurement, self).write(vals)

        # Si on modifie des champs qui impactent la description ou le lien
        # if self.state == 'presale':
        #     self.update_sale_order_line()
        
        return result
    
    def unlink(self):
        """ 
        Lors de la suppression d'une mesure, on remet la description 
        standard sur la ligne de commande liée avant de supprimer.
        """
        # for record in self:
            # if record.sale_order_line_id:
            #     standard_desc = record.sale_order_line_id.product_id.get_product_multiline_description_sale()
            #     record.sale_order_line_id.with_context(from_measurement_module=True).write({
            #         'name': standard_desc,
            #         'product_uom_qty': 1.0,
            #         'price_unit': 0.0,
            #         'product_uom_id': self.env.ref('rail_measurement.uom_none', raise_if_not_found=False),
            #     })
            #     record.sale_order_line_etudes_id.with_context(allow_study_deletion=True).unlink()
        return super(RailMeasurement, self).unlink()

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end and record.date_start:
                if record.date_end < record.date_start:
                    raise exceptions.ValidationError("La date de fin ne peut pas être antérieure à la date de début.")

    def action_validate_assignment(self):
        self.ensure_one()
        
        # --- 1. BLOCAGES STRICTS (Ne peuvent pas être ignorés) ---
        if not self.date_start or not self.date_end:
            raise exceptions.UserError("Veuillez définir les dates de début et de fin.")
        if not self.chariot_type_lines:
            raise exceptions.UserError("Aucun besoin en chariots défini.")

        soft_errors = [] # Liste pour le wizard

        for line in self.chariot_type_lines:
            # A. Vérification Quantité (STRICT)
            if len(line.assigned_chariot_ids) != line.quantity:
                raise exceptions.UserError(f"Type {line.chariot_type_id.name} : Quantité incorrecte.")

            # B. Vérification État PHYSIQUE (SOUPLE)
            broken = line.assigned_chariot_ids.filtered(lambda c: c.state != 'available')
            if broken:
                soft_errors.append(f"⚠️ Matériel indisponible : {', '.join(broken.mapped('name'))}")

            # C. Vérification CONFLITS PLANNING (SOUPLE)
            for chariot in line.assigned_chariot_ids:
                conflicts = self.env['rail.measurement'].search([
                    ('id', '!=', self.id),
                    ('state', 'not in', ['draft', 'cancelled']),
                    ('date_start', '<', self.date_end),
                    ('date_end', '>', self.date_start),
                    ('chariot_type_lines.assigned_chariot_ids', 'in', chariot.id)
                ])
                if conflicts:
                    soft_errors.append(f"⚠️ Conflit planning pour {chariot.name} avec {conflicts[0].reference}")

        # --- 2. DÉCISION FINALE ---
        if soft_errors:
            # On ouvre le wizard pour demander si on passe en mode URGENCE
            return {
                'name': 'Conflits détectés : Passer en mode Urgence ?',
                'type': 'ir.actions.act_window',
                'res_model': 'rail.urgent.assignment.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_measurement_id': self.id,
                    'default_message': "\n".join(soft_errors) + "\n\nVoulez-vous passer ce dossier en 'Demande Matériel - Urgence' ?",
                }
            }
    
        self.prod_substate = 'assigned'
        self.state = 'measure'
        self.measure_substate = 'waiting_prod'

        return True

    def action_modifier_fiche(self):
        self.ensure_one()

        for line in self.chariot_type_lines:
            line.assigned_chariot_ids = [(5, 0, 0)]  # Détache tous les chariots

        self.prod_substate = 'mission'

        return True
    
    def action_confirm_fiche_mission(self):
        """Confirme la mesure - vérifie les dates et les types de chariots"""
        for record in self:
            # 1. Vérifier si les dates sont remplies
            if not record.date_start or not record.date_end:
                raise UserError("✋ Action impossible : Veuillez définir les dates de début et de fin de mission.")

            # 2. Vérifier la cohérence chronologique
            if record.date_end < record.date_start:
                raise UserError("✋ Erreur de saisie : La date de fin ne peut pas être antérieure à la date de début.")

            # 3. Vérifier qu'il y a au moins une ligne de besoin chariot
            if not record.chariot_type_lines:
                raise UserError("✋ Action requise : Vous devez définir au moins un type de chariot pour cette mission.")

            # Si tout est OK, on passe à l'étape suivante
            record.prod_substate = 'material'
    
    def action_demande_matériel(self):
        """Passe à l'étape de demande de matériel"""
        for record in self:
            record.prod_substate = 'urgence'
    
    def action_matériel_recu(self):
        """Passe à l'étape d'affectation des chariots"""
        for record in self:
            record.prod_substate = 'material'
    
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
    
    def action_import_consistance_lines(self):
        # On cherche l'ID de l'action de la vue liste des lignes
        # Si vous n'avez pas d'action dédiée, on en définit une ici
        return {
            'name': 'Importation des lignes',
            'type': 'ir.actions.act_window',
            'res_model': 'rail.measurement.consistance.line',
            'view_mode': 'list',
            'target': 'current',  # On change de vue pour "nettoyer" le modèle actif
            'domain': [('measurement_id', '=', self.id)],
            'context': {
                'default_measurement_id': self.id,
                'default_ligne_id': self.default_ligne_id.id,
                # C'est ce flag qui permet de garder le lien lors de l'import
                'active_test': False, 
            },
        }


    ### PORTAIL CLIENT

    def _compute_access_url(self):
        super(RailMeasurement, self)._compute_access_url()
        for rec in self:
            rec.access_url = '/my/measurement/%s' % (rec.id)


# ========== NOUVEAU MODÈLE: Ligne de type de chariot ==========
class RailMeasurementChariotTypeLine(models.Model):
    _name = 'rail.measurement.chariot.type.line'
    _description = 'Besoin en type de chariot pour une mesure'

    measurement_id = fields.Many2one('rail.measurement', required=True, ondelete='cascade')
    chariot_type_id = fields.Many2one('chariot.type', string='Type requis', required=True)
    quantity = fields.Integer(string='Quantité', required=True, default=1)
    
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
        if self.measurement_id.state and (not self.env.context.get('check_avail_start') or not self.env.context.get('check_avail_end')):
            if self.measurement_id.state != 'presale' and (self.measurement_id.state != 'production' or not self.measurement_id.prod_substate in ['mission', 'material']):
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
    
    # === FILTRAGE DES TYPES DÉJÀ UTILISÉS ===
    @api.onchange('measurement_id')
    def _onchange_chariot_type_id_domain(self):
        """
        Filtre le dropdown 'Type requis' pour ne proposer que les types
        qui ne sont pas encore présents dans le tableau.
        """
        # 1. On récupère les IDs de tous les types déjà sélectionnés dans les lignes
        # Note : self.measurement_id.chariot_type_lines contient toutes les lignes (y compris l'actuelle)
        already_selected_ids = self.measurement_id.chariot_type_lines.mapped('chariot_type_id').ids
        
        # 2. Si on est en train de modifier une ligne existante, 
        # on doit autoriser son propre type dans la liste (sinon il disparaît du dropdown)
        if self.chariot_type_id:
            already_selected_ids = [tid for tid in already_selected_ids if tid != self.chariot_type_id._origin.id]
        
        logger = logging.getLogger(__name__)
        logger.info(f"Already selected chariot type IDs: {already_selected_ids}")

        # 3. On retourne le domaine filtré
        return {'domain': {'chariot_type_id': [('id', 'not in', already_selected_ids)]}}

    # === SÉCURITÉ ABSOLUE (Contrainte SQL Odoo 19) ===
    _unique_type_per_measurement = models.Constraint(
        'unique(measurement_id, chariot_type_id)',
        '✋ Erreur : Ce type de chariot est déjà présent dans le tableau.'
    )
    
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
                        f"{conflicts[0].reference} ({dates}).\n"
                        f"Si aucun chariot n'est disponible, et que vous souhaitez forcer l'affectation, passez la mesure en mode 'Demande Matériel - Urgence'."
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
        # domain="[('sale_order_line_id','=',False), ('partner_id', '=', partner_id), ('state', 'in', ['presale'])]",
        domain="[('sale_order_id','=',False), ('partner_id', '=', partner_id), ('state', 'in', ['presale'])]",
    )

    # Technical fields to pass context
    sale_order_id = fields.Many2one('sale.order', string='Ligne de commande')
    partner_id = fields.Many2one('res.partner', string='Client')

    def action_apply(self):
        self.ensure_one()

        if self.mode == 'link':
            if not self.measurement_id:
                raise exceptions.UserError("Veuillez sélectionner une mesure existante.")
            
            measurement = self.measurement_id
            quotation = self.sale_order_id

            # 1. Lien de la mesure à la ligne principale (Relevé) et au devis
            measurement.write({
                'sale_order_id': quotation.id,
            })

            
            # 2. Lien inverse sur la SOL principale
            quotation.measurement_id = measurement.id

            # 4. Synchronisation des noms, prix et quantités pour les deux lignes
            # measurement.update_sale_order_line()

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
                    'default_partner_id': self.partner_id.id,
                    'default_sale_order_id': self.sale_order_id.id,
                }
            }

# ========== Héritages existants ==========
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rail_measurement = fields.Boolean(
        string='Prestation de mesure ferroviaire',
        help='Cochez cette case pour les produits de type mesure de voie ferrée'
    )

    def action_view_rail_measurements(self):
        self.ensure_one()
        return {
            'name': 'Historique des Mesures',
            'type': 'ir.actions.act_window',
            'res_model': 'rail.measurement',
            'view_mode': 'list,form',
            'context': {'create': False}
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    measurement_id = fields.Many2one('rail.measurement', string='Mesures de voie')

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
    
    def action_create_rail_measurement(self):
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configurer la mesure de voie',
            'res_model': 'rail.measurement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }
    
    def action_update_sale_order_from_measurement(self):
        self.measurement_id.update_sale_order()

    def action_remove_measurement(self):
        self.ensure_one()
        if self.measurement_id:
            # 1. Détachement de la mesure
            measurement = self.measurement_id
            measurement.with_context(delete_study_line=True).write({
                'sale_order_id': False,
            })
            self.measurement_id = False
        
            # 2. Reset complet du devis
            # On supprime toutes les lignes actuelles (le (5, 0, 0) vide la One2many)
            self.write({
                'order_line': [(5, 0, 0)],
                'sale_order_template_id': False
            })

            # 3. Ré-application du modèle SNCF
            template = self.env.ref('rail_measurement.template_bordereau_sncf_complet', raise_if_not_found=False)
            if template:
                self.sale_order_template_id = template
                self._onchange_sale_order_template_id()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    itinerary_duration = fields.Selection(
        related='measurement_id.itinerary_duration', 
        string="Durée d'itinéraire (Mesure)",
        store=True
    )

    @api.onchange('order_line', 'itinerary_duration')
    def _onchange_rail_discounts(self):
        logging.getLogger(__name__).info("Updating rail measurement discounts on sale order...")
        DURATION_RATES = {
            'tte': 0.0, 'gt7': -0.05, '6_7': -0.035, '5_6': -0.025,
            '4_5': 0.0, '3h30_4': 0.025, '3_3h30': 0.07,
            '2h30_3': 0.15, '2_2h30': 0.25, 'lt2': 0.50
        }

        for order in self:
            # 1. Totaux
            lines_1_4 = order.order_line.filtered(lambda l: l.product_id.default_code and l.product_id.default_code[:2] in ['1.', '2.', '3.', '4.', 'FO'])
            total_1_4 = sum(lines_1_4.mapped('price_subtotal'))
            
            lines_cda = order.order_line.filtered(lambda l: l.product_id.default_code not in ['REMISE_ITIN', 'REMISE_VOL'] and not l.display_type)
            total_cda = sum(lines_cda.mapped('price_subtotal'))

            # 2. Calcul Taux Volume (CDA)
            vol_rate, vol_label = 0.0, "< 30 000 €"
            if total_cda >= 200000: vol_rate, vol_label = -0.025, "> 200 k€"
            elif total_cda >= 100000: vol_rate, vol_label = -0.015, "[100k - 200k["
            elif total_cda >= 50000: vol_rate, vol_label = -0.015, "[50k - 100k["
            elif total_cda >= 30000: vol_rate, vol_label = -0.007, "[30k - 50k["

            # 3. Taux Itinéraire (Depuis la MESURE)
            dur_key = order.itinerary_duration or 'tte'
            dur_rate = DURATION_RATES.get(dur_key, 0.0)
            
            # Récupération du label propre
            selection_values = dict(self.env['rail.measurement'].fields_get(allfields=['itinerary_duration'])['itinerary_duration']['selection'])
            dur_label = selection_values.get(dur_key)

            # 4. Update des lignes
            for line in order.order_line:
                if line.product_id.default_code == 'REMISE_ITIN':
                    line.name = f"Remise/Majoration Itinéraire ({dur_label})"
                    line.product_uom_qty = dur_rate
                    line.price_unit = total_1_4
                    line.price_total = total_1_4*dur_rate
                if line.product_id.default_code == 'REMISE_VOL':
                    line.name = f"Remise sur Volume CDA ({vol_label})"
                    line.product_uom_qty = vol_rate
                    line.price_unit = total_cda
                    line.price_total = total_cda*vol_rate

class RailMeasurementPlanning(models.Model):
    _name = 'rail.measurement.planning'
    _description = 'Planning Hebdomadaire de Mesure'
    _order = 'year, week_number'

    measurement_id = fields.Many2one('rail.measurement', ondelete='cascade')
    
    # Infos de la semaine
    year = fields.Integer("Année")
    week_number = fields.Integer("Semaine")
    week_label = fields.Char("S", compute="_compute_week_label")
    date_start = fields.Date("Du")
    date_end = fields.Date("Au")

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
        # self.measurement_id.update_sale_order_line()

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
    
    # Champs techniques pour compter les fichiers par jour
    mon_has_file = fields.Boolean(compute='_compute_files_presence')
    tue_has_file = fields.Boolean(compute='_compute_files_presence')
    wed_has_file = fields.Boolean(compute='_compute_files_presence')
    thu_has_file = fields.Boolean(compute='_compute_files_presence')
    fri_has_file = fields.Boolean(compute='_compute_files_presence')
    sat_has_file = fields.Boolean(compute='_compute_files_presence')
    sun_has_file = fields.Boolean(compute='_compute_files_presence')

    day_file_ids = fields.One2many('rail.measurement.day.file', 'planning_id', string="Fichiers de la semaine")

    def _compute_files_presence(self):
        for rec in self:
            # On vérifie la présence de fichiers pour chaque jour de la semaine
            days_with_files = rec.day_file_ids.mapped('day')
            rec.mon_has_file = 'mon' in days_with_files
            rec.tue_has_file = 'tue' in days_with_files
            rec.wed_has_file = 'wed' in days_with_files
            rec.thu_has_file = 'thu' in days_with_files
            rec.fri_has_file = 'fri' in days_with_files
            rec.sat_has_file = 'sat' in days_with_files
            rec.sun_has_file = 'sun' in days_with_files

    def action_view_day_files(self):
        """ 
        Ouvre une vue avec les fichiers de la semaine. 
        On pourrait pousser le vice à filtrer par jour, 
        mais voir tous les fichiers de la semaine est plus simple.
        """
        return {
            'name': 'Fichiers de la semaine',
            'type': 'ir.actions.act_window',
            'res_model': 'rail.measurement.day.file',
            'view_mode': 'list,form',
            'domain': [('planning_id', '=', self.id)],
            'context': {'default_planning_id': self.id},
            'target': 'new',
        }

    # Récupération des équipes (pour filtrer le calendrier)
    equipe_id_1 = fields.Many2one(related='measurement_id.equipe_id_1', store=True)
    equipe_id_2 = fields.Many2one(related='measurement_id.equipe_id_2', store=True)
    
    # Champ technique pour la couleur dans le calendrier Odoo
    # 0 = Gris/Blanc, 1 = Rouge, 4 = Bleu, etc.
    calendar_color = fields.Integer(compute='_compute_calendar_color', store=True)

    @api.depends('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
    def _compute_calendar_color(self):
        for rec in self:
            # Si aucun créneau n'est défini (J ou N), on met la couleur 0 (Gris)
            if rec.nb_periods == 0:
                rec.calendar_color = 0 
            else:
                # Sinon on met une couleur (ex: 4 pour bleu ou 2 pour orange)
                rec.calendar_color = 4

class RailMeasurementDayFile(models.Model):
    _name = 'rail.measurement.day.file'
    _description = 'Fichier de mesure journalier'

    planning_id = fields.Many2one('rail.measurement.planning', string="Semaine", ondelete='cascade')
    day = fields.Selection([
        ('mon', 'Lundi'), ('tue', 'Mardi'), ('wed', 'Mercredi'),
        ('thu', 'Jeudi'), ('fri', 'Vendredi'), ('sat', 'Samedi'), ('sun', 'Dimanche')
    ], string="Jour")
    week_number = fields.Integer(
        related='planning_id.week_number', 
        string="N° Semaine", 
        readonly=True, 
        store=True
    )
    
    file = fields.Binary(string="Fichier", required=True)
    file_name = fields.Char(string="Nom du fichier")
    
    # Lien technique vers la mesure parente pour faciliter les recherches
    measurement_id = fields.Many2one('rail.measurement', related='planning_id.measurement_id', store=True)

class RailUrgentAssignmentWizard(models.TransientModel):
    _name = 'rail.urgent.assignment.wizard'
    _description = 'Confirmation de demande urgente'

    measurement_id = fields.Many2one('rail.measurement', string="Mesure")
    message = fields.Text(string="Alertes détectées", readonly=True)

    def action_confirm(self):
        """L'utilisateur a cliqué sur OUI : On passe en mode URGENCE"""
        self.measurement_id.prod_substate = 'urgence'
        return {'type': 'ir.actions.act_window_close'}

class ConsistanceLine(models.Model):
    _name = 'rail.measurement.consistance.line'
    _description = 'Ligne de consistance pour une mesure'

    measurement_id = fields.Many2one('rail.measurement', ondelete='cascade')
    ligne_id = fields.Many2one('leyfa.ligne', string='Ligne')
    voie_id = fields.Many2one('leyfa.type.voie', string="Voie")
    desc_nature_travaux = fields.Many2one('rail.nature.travaux', string="Type Tx")

    # Localisation
    zone_debut = fields.Many2one('rail.type.alignement.courbe', string="Début zone sur")
    pkd = fields.Float(string="PKD", digits=(7, 0))
    pkf = fields.Float(string="PKF", digits=(7, 0))
    zone_fin = fields.Many2one('rail.type.alignement.courbe', string="Fin zone sur")

    # Calculs automatiques
    
    maj_deb = fields.Float(string="Maj. Début", digits=(7, 0))
    maj_fin = fields.Float(string="Maj. Fin", digits=(7, 0))
    

    # Limites et détails
    nombre_courbes = fields.Integer(string="Nb Courbes")
    longueur_courbes = fields.Float(string="Long. Courbes", digits=(7, 0))
    nombres_quais = fields.Integer(string="Nb Quais")
    longueur_quais = fields.Float(string="Long. Quais", digits=(7, 0))
    observations = fields.Text(string="Observations")

    limite_amont = fields.Float(string="Limite Amont", digits=(7, 0), compute='_compute_limites')
    limite_aval = fields.Float(string="Limite Aval", digits=(7, 0), compute='_compute_limites')
    
    @api.onchange('pkd', 'pkf', 'maj_deb', 'maj_fin')
    def _compute_limites(self):
        for rec in self:
            rec.limite_amont = rec.pkd - rec.maj_deb
            rec.limite_aval = rec.pkf + rec.maj_fin
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-fill ligne_id from measurement if missing during import"""
        for vals in vals_list:
            if not vals.get('ligne_id') and vals.get('measurement_id'):
                measurement = self.env['rail.measurement'].browse(vals['measurement_id'])
                if measurement.default_ligne_id:
                    vals['ligne_id'] = measurement.default_ligne_id.id
        
        return super().create(vals_list)
    
class RailConsistanceImportWizard(models.TransientModel):
    _name = 'rail.consistance.import.wizard'
    _description = 'Wizard Import Excel (Consistance & Quais)'

    measurement_id = fields.Many2one('rail.measurement', string="Parent")
    file = fields.Binary(string='Fichier Excel (.xlsx)')
    filename = fields.Char()
    replace_existing = fields.Boolean(
        string="Remplacer les lignes existantes", 
        default=True,
        help="Si coché, les tableaux actuels seront vidés avant l'importation."
    )

    def action_import(self):
        self.ensure_one()
        if not self.file:
            return

        data = base64.b64decode(self.file)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            raise UserError(_("Erreur lors de la lecture du fichier : %s") % str(e))

        # --- CONFIGURATION DU MAPPING ---
        # Format : 'Nom Technique Champ': (Index_Colonne_Excel, 'type', 'Optionnel_Model_M2O')

        if self.replace_existing:
            # On vide les deux tableaux liés à la mesure
            self.measurement_id.consistance_lines.unlink()
            self.measurement_id.quai_line_ids.unlink()
        
        mapping_consistance = {
            'ligne_id': (0, 'm2o', 'leyfa.ligne'),
            'voie_id': (1, 'm2o', 'leyfa.type.voie'),
            'desc_nature_travaux': (2, 'm2o', 'rail.nature.travaux'),
            'zone_debut': (3, 'm2o', 'rail.type.alignement.courbe'),
            'pkd': (4, 'float'),
            'pkf': (5, 'float'),
            'zone_fin': (6, 'm2o', 'rail.type.alignement.courbe'),
            'maj_deb': (8, 'float'),
            'maj_fin': (9, 'float'),
            'nombre_courbes': (13, 'int'),
            'longueur_courbes': (14, 'float'),
            'nombres_quais': (15, 'int'),
            'longueur_quais': (16, 'float'),
            'observations': (22, 'char'),
        }

        mapping_quais = {
            'ligne_id': (0, 'm2o', 'leyfa.ligne'),
            'voie_id': (1, 'm2o', 'leyfa.type.voie'),
            'pkd': (2, 'float'),
            'pkf': (3, 'float'),
            'nom_gare': (6, 'char'),
        }

        # --- EXECUTION ---
        # 1. Consistance (Obligatoire)
        self._process_sheet(wb, 'process_consistance', 'rail.measurement.consistance.line', mapping_consistance, required=True)
        
        # 2. Quais (Optionnel : si l'onglet n'existe pas ou est vide, on ignore)
        if 'process_quais' in wb.sheetnames:
            self._process_sheet(wb, 'process_quais', 'rail.measurement.quai.line', mapping_quais, required=False)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Importation réussie'),
                'message': _('Les lignes ont été mises à jour avec succès.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'}, # <--- C'est ici la clé
            }
        }

    def _process_sheet(self, wb, sheet_name, res_model, mapping, required=False):
        """ Méthode générique pour traiter un onglet Excel """
        if sheet_name not in wb.sheetnames:
            if required:
                raise UserError(_("L'onglet '%s' est requis dans le fichier Excel.") % sheet_name)
            return

        sheet = wb[sheet_name]
        records_to_create = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2), start=2):
            cells = [cell.value for cell in row]
            if not cells or cells[0] is None: # On saute si la 1ère colonne est vide
                continue

            vals = {'measurement_id': self.measurement_id.id}
            
            for field_name, config in mapping.items():
                col_idx = config[0]
                data_type = config[1]
                
                # Sécurité : vérifier si la colonne existe dans cette ligne
                val_raw = cells[col_idx] if len(cells) > col_idx else None
                
                # Parsing selon le type défini
                try:
                    if data_type == 'm2o':
                        vals[field_name] = self._parse_m2o(config[2], val_raw, row_idx, col_idx + 1)
                    elif data_type == 'float':
                        vals[field_name] = self._parse_float(val_raw, row_idx, col_idx + 1)
                    elif data_type == 'int':
                        vals[field_name] = self._parse_int(val_raw, row_idx, col_idx + 1)
                    elif data_type == 'char':
                        vals[field_name] = str(val_raw).strip() if val_raw else False
                except Exception as e:
                    raise UserError(_("Erreur onglet [%s] %s") % (sheet_name, str(e)))

            records_to_create.append(vals)

        if records_to_create:
            self.env[res_model].create(records_to_create)

    # --- HELPERS DE PARSING ---

    def _get_coord(self, row, col):
        return f"{openpyxl.utils.get_column_letter(col)}{row}"

    def _is_excel_error(self, value):
        errors = ['#REF!', '#VALUE!', '#N/A', '#NAME?', '#DIV/0!', '#NULL!', '#NUM!']
        return isinstance(value, str) and any(err in value.upper() for err in errors)

    def _parse_float(self, value, row, col):
        if value is None or self._is_excel_error(value) or value == '':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            raise UserError(_("Valeur numérique invalide à la cellule %s ('%s' reçu).") % (self._get_coord(row, col), value))

    def _parse_int(self, value, row, col):
        if value is None or self._is_excel_error(value) or value == '':
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            raise UserError(_("Nombre entier invalide à la cellule %s ('%s' reçu).") % (self._get_coord(row, col), value))

    def _parse_m2o(self, model, value, row, col):
        if not value or self._is_excel_error(value):
            return False
        name = str(value).strip()
        record = self.env[model].search([('name', '=', name)], limit=1)
        return record.id if record else False

    def action_download_template(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/rail_measurement/static/src/templates/template_consistance_quais'
            '.xlsx',
            'target': 'new',
        }

# Les fields.selections sont ici des classe au cas où il y aurait nouveauté ou changement de nom etc

class RailNatureTravaux(models.Model):
    _name = 'rail.nature.travaux'
    _description = 'Nature des travaux'
    _order = 'name'

    name = fields.Char(string="Code", required=True)
    description = fields.Char(string="Description")

class TypeAlignementCourbe(models.Model):
    _name = 'rail.type.alignement.courbe'
    _description = 'Type d\'alignement ou de courbe'
    _order = 'name'

    name = fields.Char(string="Type", required=True)

# Nécessaire pour le tableau 2 de consistance
class RailMeasurementCibleLine(models.Model):
    _name = 'rail.measurement.cible.line'
    _description = 'Ligne de cible pour une mesure'

    measurement_id = fields.Many2one('rail.measurement', ondelete='cascade')
    name = fields.Char(string="Repérages voie et obstacles", required=True) # Ce champ causait l'erreur
    qty = fields.Integer(string="Quantité")
    observation = fields.Char(string="Observations")
    line_type = fields.Selection([
        ('cible', 'Cible'),
        ('prov', 'Provisoire'),
        ('courbe', 'Courbe'),
        ('mire', 'Mire'),
    ], string="Type")

class QuaiLine(models.Model):
    _name = 'rail.measurement.quai.line'
    _description = 'Ligne de tableau de quais pour une mesure'

    measurement_id = fields.Many2one('rail.measurement', ondelete='cascade')

    ligne_id = fields.Many2one('leyfa.ligne', string='Ligne')
    voie_id = fields.Many2one('leyfa.type.voie', string="Voie")
    pkd = fields.Float(string="PK Début", digits=(7, 0))
    pkf = fields.Float(string="PK Fin", digits=(7, 0))
    longueur = fields.Float(string="Longueur", digits=(7, 0))
    nom_gare = fields.Char(string="Nom de la gare")
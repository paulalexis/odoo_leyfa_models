from odoo import models, fields, api

class TestProcess(models.Model):
    _name = 'test.process'
    _description = 'Processus Production - Mesure - Etude'

    name = fields.Char(required=True, string="Référence Mission")
    description = fields.Html(string="Observations")
    
    # État Macro
    state = fields.Selection([
        ('production', 'Pôle Production'),
        ('measure', 'Pôle Mesure'),
        ('study', 'Pôle Études'),
        ('done', 'Terminé')
    ], default='production', string="Statut Global")
    
    # Sous-étapes (Micro)
    prod_substate = fields.Selection([
        ('mission', 'Réception Mission'),
        ('team', 'Constitution Équipe'),
        ('material', 'Vérification Matériel'),
        ('assigned', 'Chariots Affectés')
    ], string="Étape Production", default='mission')
    
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
        ('prod_detail', 'Détail : Production'),
        ('measure_detail', 'Détail : Mesure'),
        ('study_detail', 'Détail : Études')
    ], default='overview', string="Niveau de Vue")
    
    urgent_material_needed = fields.Boolean(string="Réappro Urgent", default=False)
    mermaid_graph = fields.Text(compute='_compute_mermaid_graph')

    @api.depends('state', 'prod_substate', 'measure_substate', 'study_substate', 'view_level', 'urgent_material_needed')
    def _compute_mermaid_graph(self):
        for rec in self:
            if rec.view_level == 'overview':
                rec.mermaid_graph = rec._generate_macro_graph()
            elif rec.view_level == 'prod_detail':
                rec.mermaid_graph = rec._generate_prod_micro()
            elif rec.view_level == 'measure_detail':
                rec.mermaid_graph = rec._generate_measure_micro()
            else:
                rec.mermaid_graph = rec._generate_study_micro()

    def _generate_macro_graph(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px", "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                 "PROD[Production] --> MEASURE[Mesure]", "MEASURE --> STUDY[Études]", "STUDY --> DONE((Fin))"]
        return self._apply_styles(lines, {'production': 'PROD', 'measure': 'MEASURE', 'study': 'STUDY', 'done': 'DONE'}, self.state, ['production', 'measure', 'study', 'done'])

    def _generate_prod_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "M1(Mission) --> M2[Équipe]", "M2 --> M3{Matériel?}", "M3 -- Non --> M3_U[Urgence]", "M3_U --> M4[Chariots]", "M3 -- Oui --> M4", "M4 --> M5((Prêt))"]
        return self._apply_styles(lines, {'mission': 'M1', 'team': 'M2', 'material': 'M3', 'assigned': 'M4'}, self.prod_substate, ['mission', 'team', 'material', 'assigned'])

    def _generate_measure_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "ME1[Terrain] --> ME2{Fini?}", "ME2 -- Non --> ME1", "ME2 -- Oui --> ME3[Fichiers]", "ME3 --> ME4((OK))"]
        return self._apply_styles(lines, {'daily': 'ME1', 'checking': 'ME2', 'files': 'ME3'}, self.measure_substate, ['daily', 'checking', 'files'])

    def _generate_study_micro(self):
        lines = ["graph LR", "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:2px",
                 "S1[Réception] --> S2[Analyse]", "S2 --> S3{Validation}", "S3 -- KO --> S1", "S3 -- OK --> S4((Fin))"]
        return self._apply_styles(lines, {'reception': 'S1', 'analysis': 'S2', 'validation': 'S3'}, self.study_substate, ['reception', 'analysis', 'validation'])

    def _apply_styles(self, lines, mapping, current, order):
        if current in order:
            idx = order.index(current)
            for i, key in enumerate(order):
                node = mapping.get(key)
                if node:
                    if i < idx: lines.append(f"class {node} done")
                    elif i == idx: lines.append(f"class {node} active")
        return "\n".join(lines)

    def action_next(self):
        if self.state == 'production':
            steps = ['mission', 'team', 'material', 'assigned']
            curr = steps.index(self.prod_substate)
            if self.prod_substate == 'assigned':
                self.state, self.measure_substate = 'measure', 'daily'
            else: self.prod_substate = steps[curr+1]
        elif self.state == 'measure':
            steps = ['daily', 'checking', 'files']
            curr = steps.index(self.measure_substate)
            if self.measure_substate == 'files':
                self.state, self.study_substate = 'study', 'reception'
            else: self.measure_substate = steps[curr+1]
        elif self.state == 'study':
            steps = ['reception', 'analysis', 'validation']
            curr = steps.index(self.study_substate)
            if self.study_substate == 'validation': self.state = 'done'
            else: self.study_substate = steps[curr+1]
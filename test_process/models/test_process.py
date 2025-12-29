from odoo import models, fields, api

class TestProcess(models.Model):
    _name = 'test.process'
    _description = 'Processus Mesurage SNCF'

    name = fields.Char(required=True, string="Référence")
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('geo', 'Géométrie'),
        ('obs_check', 'Vérification Obstacle'),
        ('maint', 'Maintenance'),
        ('gab', 'Gabarit'),
        ('done', 'Terminé')
    ], default='draft', string="Statut")

    obstacle_detected = fields.Boolean(string="Obstacle détecté")
    mermaid_graph = fields.Text(compute='_compute_mermaid_graph')

    @api.depends('state', 'obstacle_detected')
    def _compute_mermaid_graph(self):
        for rec in self:
            # 1. GRAPH STRUCTURE (Static: Always show all branches)
            lines = [
                "graph LR",
                # Define Styles
                "classDef active fill:#714B67,color:#fff,stroke:#333,stroke-width:4px",
                "classDef done fill:#e2e2e2,color:#999,stroke:#ccc",
                "classDef pending fill:#fff,color:#bfbfbf,stroke:#eee",
                "classDef decision fill:#fff,stroke:#333,stroke-width:2px",
                
                # Full Flowchart Definition
                "  START(Brouillon) --> GEO(Géométrie)",
                "  GEO --> CHECK{Obstacle?}",
                "  CHECK -- Oui --> MAINT[Maintenance]",
                "  MAINT --> GAB[Gabarit]",
                "  CHECK -- Non --> GAB",
                "  GAB --> END((Validation))"
            ]

            # 2. HIGHLIGHTING LOGIC
            # Map state to Mermaid Node IDs
            mapping = {
                'draft': 'START',
                'geo': 'GEO',
                'obs_check': 'CHECK',
                'maint': 'MAINT',
                'gab': 'GAB',
                'done': 'END'
            }
            
            # Determine order to color "Done" vs "Future"
            order = ['draft', 'geo', 'obs_check', 'maint', 'gab', 'done']
            current_index = order.index(rec.state)

            for i, state_key in enumerate(order):
                node_id = mapping[state_key]
                
                # Logic to apply classes
                if i < current_index:
                    lines.append(f"  class {node_id} done")
                elif i == current_index:
                    lines.append(f"  class {node_id} active")
                else:
                    lines.append(f"  class {node_id} pending")

            # 3. SPECIAL HANDLING FOR THE BRANCHING
            # If we are at the check or past it, and NO obstacle was detected, 
            # we explicitly grey out the Maintenance node even if the process continues.
            if not rec.obstacle_detected:
                lines.append("  class MAINT pending")
            
            # Make the decision diamond always look like a decision
            if rec.state != 'obs_check':
                lines.append("  class CHECK decision")

            rec.mermaid_graph = "\n".join(lines)

    def action_next(self):
        """Logic to move through the full flowchart"""
        if self.state == 'draft':
            self.state = 'geo'
        elif self.state == 'geo':
            self.state = 'obs_check'
        elif self.state == 'obs_check':
            self.state = 'maint' if self.obstacle_detected else 'gab'
        elif self.state == 'maint':
            self.state = 'gab'
        elif self.state == 'gab':
            self.state = 'done'
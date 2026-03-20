import re
from odoo import api, fields, models, _

class WizardNewContact(models.TransientModel):
    _name = 'rail.wizard.new.contact'
    _description = 'Assistant création contact'

    # Hierarchy selection
    level_1_id = fields.Many2one('res.partner', string='Niveau 1')
    level_2_id = fields.Many2one('res.partner', string='Niveau 2')
    level_3_id = fields.Many2one('res.partner', string='Niveau 3')
    level_4_id = fields.Many2one('res.partner', string='Niveau 4')

    # Computed Parent
    selected_parent_id = fields.Many2one(
        'res.partner',
        string='Parent sélectionné',
        compute='_compute_selected_parent',
        store=True,
    )

    # Address fields in the wizard
    parent_street = fields.Char(string='Rue')
    parent_street2 = fields.Char(string='Complément adresse')
    parent_zip = fields.Char(string='Code postal')
    parent_city = fields.Char(string='Ville')

    signature_text = fields.Text(string='Signature email')
    new_department_name = fields.Char(string='Nouveau département')

    # Contact fields
    contact_name = fields.Char(string='Nom du contact')
    contact_job = fields.Char(string='Poste')
    contact_email = fields.Char(string='Email')
    contact_phone = fields.Char(string='Téléphone')

    result_partner_id = fields.Many2one('res.partner', readonly=True)

    # In wizard fields
    origin_res_model = fields.Char()
    origin_res_id = fields.Integer()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sncf_param = self.env['ir.config_parameter'].sudo().get_param('rail_measurement.sncf_reseau_id', 0)
        if sncf_param:
            sncf_id = int(sncf_param)
            res['level_1_id'] = sncf_id
            partner = self.env['res.partner'].browse(sncf_id)
            # Load current address
            res['parent_street'] = partner.street or ''
            res['parent_street2'] = partner.street2 or ''
            res['parent_zip'] = partner.zip or ''
            res['parent_city'] = partner.city or ''
        return res

    @api.depends('level_1_id', 'level_2_id', 'level_3_id', 'level_4_id')
    def _compute_selected_parent(self):
        for rec in self:
            rec.selected_parent_id = rec.level_4_id or rec.level_3_id or rec.level_2_id or rec.level_1_id

    # Onchanges for navigation logic
    @api.onchange('level_1_id')
    def _onchange_level_1(self):
        self.level_2_id = self.level_3_id = self.level_4_id = False
        if self.level_1_id: self._update_local_address(self.level_1_id)

    @api.onchange('level_2_id')
    def _onchange_level_2(self):
        self.level_3_id = self.level_4_id = False
        if self.level_2_id: self._update_local_address(self.level_2_id)

    @api.onchange('level_3_id')
    def _onchange_level_3(self):
        self.level_4_id = False
        if self.level_3_id: self._update_local_address(self.level_3_id)

    def _update_local_address(self, partner):
        self.parent_street = partner.street or ''
        self.parent_street2 = partner.street2 or ''
        self.parent_zip = partner.zip or ''
        self.parent_city = partner.city or ''

    # Navigation Buttons
    # def action_select_level_1(self):
    #     children = self.env['res.partner'].search([('parent_id', '=', self.level_1_id.id), ('is_company', '=', True)])
    #     if len(children) == 1: self.level_2_id = children[0]
    #     return self._reopen()

    # def action_select_level_2(self):
    #     children = self.env['res.partner'].search([('parent_id', '=', self.level_1_id.id), ('is_company', '=', True)])
    #     if len(children) == 1: self.level_3_id = children[0]
    #     return self._reopen()

    # def action_select_level_3(self):
    #     children = self.env['res.partner'].search([('parent_id', '=', self.level_2_id.id), ('is_company', '=', True)])
    #     if len(children) == 1: self.level_4_id = children[0]
    #     return self._reopen()
    
    # def action_select_level_4(self):
    #     children = self.env['res.partner'].search([('parent_id', '=', self.level_3_id.id), ('is_company', '=', True)])
    #     if len(children) == 1: self.level_4_id = children[0]
    #     return self._reopen()

    def action_parse_signature(self):
        text = self.signature_text or ''
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        lines = [l for l in lines if not re.match(r'^[-_=|*]{2,}$', l)]

        # Reset
        self.contact_name = self.contact_job = self.contact_email = self.contact_phone = ''

        # ── 1. Email & Phone ─────────────────────────────────────────────────────
        email_search = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', text)
        phone_search = re.search(
            r'(\+33\s?\(0\)\s?[1-9](?:[\s\.\-]?\d{2}){4}'
            r'|\+33[\s\.\-]?[1-9](?:[\s\.\-]?\d{2}){4}'
            r'|0033\s?[1-9](?:[\s\.\-]?\d{2}){4}'
            r'|0[1-9](?:[\s\.\-]?\d{2}){4})',
            text
        )

        email = email_search.group(0).strip() if email_search else ''

        phone = ''
        if phone_search:
            digits = re.sub(r'\(0\)', '', phone_search.group(0))
            digits = re.sub(r'[\s\.\-]', '', digits)
            if digits.startswith('+33'):  digits = '0' + digits[3:]
            if digits.startswith('0033'): digits = '0' + digits[4:]
            phone = ' '.join(digits[j:j+2] for j in range(0, 10, 2))

        # ── 2. Pre-classify every line ───────────────────────────────────────────
        STREET_KEYWORDS = re.compile(
            r'\b(rue|avenue|av|boulevard|bd|bld|quai|allée|allee|impasse|'
            r'chemin|place|route|voie|passage|cité|cite|square|lot|domaine|'
            r'rond[- ]point|zone)\b', re.IGNORECASE
        )

        def classify(line):
            if email and email in line:
                return 'email'
            if re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', line):
                return 'email'
            if phone_search and re.sub(r'[\s\.\-\(\)]', '', phone_search.group(0)) in re.sub(r'[\s\.\-\(\)]', '', line):
                return 'phone'
            if re.search(r'(\+33|0033|\b0[1-9]\d{8}\b)', line):
                return 'phone'
            if re.match(r'^\d{5}\s', line):
                return 'zip'
            if re.match(r'^(CS|BP|TSA|CEDEX)\s*\d+', line, re.IGNORECASE):
                return 'street2'
            if re.match(r'https?://', line, re.IGNORECASE):
                return 'url'
            return 'unknown'

        classified = {line: classify(line) for line in lines}

        # ── 3. Address parsing ───────────────────────────────────────────────────
        street, street2, zip_code, city = '', '', '', ''

        for i, line in enumerate(lines):
            cls = classified[line]

            # Case A: "63 rue de Villiers, 92208 Neuilly-sur-Seine Cedex | France"
            m_inline = re.search(r',\s*(\d{5})\s+([^|,]+)', line)
            if m_inline and cls not in ('email', 'phone', 'url'):
                zip_code = m_inline.group(1)
                city = m_inline.group(2).strip()
                street_part = line[:m_inline.start()].strip()
                if street_part and classified.get(street_part) not in ('email', 'phone'):
                    street = street_part
                continue

            # Case B: standalone ZIP line "93418 Saint-Denis Cedex"
            if cls == 'zip':
                m_zip = re.match(r'^(\d{5})\s+(.+)$', line)
                if not m_zip:
                    continue
                zip_code, city = m_zip.group(1), m_zip.group(2).strip()

                # Walk upward to collect street lines (skip phone/email/url/zip)
                candidates = []
                for k in range(i - 1, max(i - 4, -1), -1):
                    prev = lines[k]
                    prev_cls = classified[prev]
                    if prev_cls in ('email', 'phone', 'url', 'zip'):
                        break
                    candidates.append(prev)

                # Assign street / street2
                # Prefer the line with a street keyword as `street`, rest as `street2`
                street_idx = next(
                    (j for j, c in enumerate(candidates) if STREET_KEYWORDS.search(c)),
                    None
                )
                if street_idx is not None:
                    street = candidates[street_idx]
                    # Everything above street_idx goes to street2 (e.g. CS, BP, bâtiment)
                    above = candidates[:street_idx]
                    if above:
                        street2 = above[0]
                elif candidates:
                    # No keyword found: topmost candidate is street, next is street2
                    if len(candidates) >= 2:
                        street2 = candidates[0]
                        street  = candidates[1]
                    else:
                        street = candidates[0]

                continue

            # Case C: "1 place Samuel de Champlain | 92400 Courbevoie | France"
            m_pipe = re.search(r'\|\s*(\d{5})\s+([^|]+)', line)
            if m_pipe and cls not in ('email', 'phone', 'url'):
                zip_code = m_pipe.group(1)
                city = m_pipe.group(2).strip()
                street_part = line[:m_pipe.start()].strip().rstrip('|').strip()
                if street_part and classified.get(street_part) not in ('email', 'phone'):
                    street = street_part
                continue

        # ── 4. Name & Job ────────────────────────────────────────────────────────
        skip = {'email', 'phone', 'url', 'zip', 'street2'}
        for line in lines:
            if classified[line] in skip:
                continue
            if zip_code and zip_code in line:
                continue
            if len(line.split()) < 2:
                continue
            if re.search(r'\d', line):
                continue
            # Skip lines that look like company/org (contains known company words) — heuristic
            if not self.contact_name:
                self.contact_name = line
            elif not self.contact_job:
                self.contact_job = line
                break

        # ── 5. Assign ────────────────────────────────────────────────────────────
        if email:     self.contact_email   = email
        if phone:     self.contact_phone   = phone
        if street:    self.parent_street   = street
        if street2:   self.parent_street2  = street2
        if zip_code:  self.parent_zip      = zip_code
        if city:      self.parent_city     = city

        return self._reopen()



    def action_confirm(self):
        self.ensure_one()
        target_parent = self.selected_parent_id

        # 1. Update the EXISTING parent ONLY if it's NOT the Level 1 (HQ) 
        # OR if it's the only one and the address was changed.
        # This prevents overwriting SNCF General address by accident.
        if target_parent and target_parent != self.level_1_id:
            target_parent.write({
                'street': self.parent_street,
                'street2': self.parent_street2,
                'zip': self.parent_zip,
                'city': self.parent_city,
            })

        # 2. Create New Department if requested
        if self.new_department_name:
            target_parent = self.env['res.partner'].create({
                'name': self.new_department_name,
                'is_company': True,
                'parent_id': self.selected_parent_id.id,
                'street': self.parent_street,
                'street2': self.parent_street2,
                'zip': self.parent_zip,
                'city': self.parent_city,
                'type': 'other', # Setting type to 'other' helps break address sync in some Odoo versions
            })

        # 3. Create the Contact
        # We pass the address directly to the contact. 
        # If it differs from the parent, Odoo will treat it as a specific address.
        self.result_partner_id = self.env['res.partner'].create({
            'name': self.contact_name,
            'parent_id': target_parent.id,
            'function': self.contact_job,
            'email': self.contact_email,
            'phone': self.contact_phone,
            'street': self.parent_street,
            'street2': self.parent_street2,
            'zip': self.parent_zip,
            'city': self.parent_city,
            'type': 'contact',
            'is_company': False,
        })

        # In action_confirm
        if self.origin_res_model and self.origin_res_id:
            origin = self.env[self.origin_res_model].browse(self.origin_res_id)
            origin.partner_id = self.result_partner_id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contact créé'),
                'message': _('Le contact %s a été créé.') % self.result_partner_id.name,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
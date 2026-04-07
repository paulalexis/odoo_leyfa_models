/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillStart, onWillUpdateProps, xml } from "@odoo/owl";

const ROLE_CYCLE = ["R", "A", "S", "C", "I"];
const ROLE_LABELS = {
    R: "Responsible", A: "Accountable", S: "Supportive", C: "Consulted", I: "Informed",
};
const STATE_OPTIONS = [
    { value: "not_started", label: "○ Non commencé" },
    { value: "in_progress", label: "◐ En cours" },
    { value: "blocked",     label: "✕ Bloqué"     },
    { value: "done",        label: "✓ Terminé"     },
];

class RasciMatrixWidget extends Component {
    static props = { ...standardFieldProps };

    static template = xml`
<div class="rasci-matrix-widget">
    <t t-if="state.loading">
        <div class="d-flex align-items-center gap-2 p-4 text-muted">
            <div class="spinner-border spinner-border-sm" role="status"/>
            <span>Chargement de la matrice RASCI…</span>
        </div>
    </t>

    <t t-else="">
        <!-- Add member dropdown -->
        <t t-if="state.showAddMenu">
            <div class="rasci-add-overlay" t-on-click="(ev) => this.onAddOverlayClick(ev)">
                <div class="rasci-add-menu" t-att-style="'top:' + state.addMenuY + 'px;left:' + state.addMenuX + 'px'">
                    <div class="rasci-add-menu-search">
                        <input
                            class="rasci-add-search-input"
                            placeholder="Rechercher ou saisir un nom externe…"
                            t-att-value="state.addSearch"
                            t-on-input="(ev) => this.onAddSearch(ev)"
                            t-on-keydown="(ev) => this.onAddSearchKey(ev)"
                        />
                    </div>
                    <div class="rasci-add-menu-list">
                        <t t-foreach="filteredAddOptions" t-as="opt" t-key="opt.key">
                            <div
                                class="rasci-add-menu-item"
                                t-att-class="opt.type === 'department' ? 'rasci-add-dept' : opt.type === 'external' ? 'rasci-add-external' : 'rasci-add-emp'"
                                t-on-click="() => this.onAddMember(opt)">
                                <t t-if="opt.type === 'department'">
                                    <i class="fa fa-building-o me-2"/>
                                    <strong t-esc="opt.name"/>
                                    <span class="text-muted ms-1">(<t t-esc="opt.count"/> employés)</span>
                                </t>
                                <t t-elif="opt.type === 'external'">
                                    <i class="fa fa-globe me-2 text-muted"/>
                                    <span>Ajouter </span>
                                    <strong t-esc="opt.name"/>
                                    <span class="text-muted ms-1"> comme externe</span>
                                </t>
                                <t t-else="">
                                    <i class="fa fa-user me-2"/>
                                    <span t-esc="opt.name"/>
                                    <t t-if="opt.deptName">
                                        <span class="text-muted ms-1" t-esc="'— ' + opt.deptName"/>
                                    </t>
                                </t>
                            </div>
                        </t>
                        <t t-if="!filteredAddOptions.length">
                            <div class="rasci-add-menu-empty">Aucun résultat</div>
                        </t>
                    </div>
                </div>
            </div>
        </t>

        <div class="rasci-matrix-wrapper">
            <table class="rasci-matrix-table">
                <thead>
                    <tr class="rasci-employee-header">
                        <th class="rasci-task-col-header">Tâche / Etat</th>
                        <t t-foreach="state.members" t-as="emp" t-key="emp.id">
                            <th
                                draggable="true"
                                t-att-data-member-id="emp.id"
                                t-att-class="'rasci-col-draggable' + (state.dragOverMemberId === emp.id ? ' rasci-col-drag-over' : '') + (state.dragSourceMemberId === emp.id ? ' rasci-col-dragging' : '')"
                                t-on-dragstart="(ev) => this.onColDragStart(ev, emp)"
                                t-on-dragover="(ev) => this.onColDragOver(ev, emp)"
                                t-on-dragleave="(ev) => this.onColDragLeave(ev, emp)"
                                t-on-drop="(ev) => this.onColDrop(ev, emp)"
                                t-on-dragend="(ev) => this.onColDragEnd(ev)"
                            >
                                <div class="rasci-emp-header">
                                    <i class="fa fa-grip-vertical rasci-drag-handle" title="Glisser pour réordonner"/>
                                    <span t-att-title="emp.name" t-esc="emp.shortName"/>
                                    <t t-if="emp.isExternal">
                                        <i class="fa fa-globe rasci-external-icon" title="Membre externe (hors entreprise)"/>
                                    </t>
                                    <t t-if="emp.deptName">
                                        <small class="rasci-emp-dept" t-esc="emp.deptName"/>
                                    </t>
                                    <div class="rasci-emp-actions">
                                        <t t-if="state.currentUserCanEdit">
                                            <t t-if="!emp.isExternal">
                                                <i
                                                    t-attf-class="fa fa-pencil rasci-edit-toggle #{isMemberPilot(emp) || emp.canEdit ? 'rasci-edit-on' : 'rasci-edit-off'} #{isMemberPilot(emp) ? 'rasci-edit-locked' : ''}"
                                                    t-att-title="isMemberPilot(emp) ? 'Pilote du projet — édition toujours autorisée'
                                                                : emp.canEdit ? 'Retirer le droit d\'édition'
                                                                : 'Autoriser l\'édition'"
                                                    t-on-click="() => this.onToggleCanEdit(emp)"
                                                />
                                            </t>
                                            <button
                                                class="rasci-remove-col-btn"
                                                t-on-click="() => this.onRemoveMember(emp)"
                                                title="Retirer de la matrice">
                                                ✕
                                            </button>
                                        </t>
                                    </div>
                                </div>
                            </th>
                        </t>
                        <th class="rasci-add-col-header" style="width:36px; padding:0;">
                            <button class="rasci-add-col-btn" t-on-click="(ev) => this.openAddMenu(ev)" title="Ajouter un employé, département ou externe">
                                +
                            </button>
                        </th>
                    </tr>
                </thead>
                <tbody>
                    <t t-foreach="state.tasks" t-as="task" t-key="task.id">
                        <tr class="rasci-task-row" t-att-data-state="task.state">
                            <td class="rasci-task-name">
                                <t t-if="task.editing and state.currentUserCanEdit">
                                    <input
                                        class="rasci-task-input"
                                        t-att-value="task.name"
                                        t-on-blur="(ev) => this.onTaskNameBlur(ev, task)"
                                        t-on-keydown="(ev) => this.onTaskNameKey(ev, task)"
                                    />
                                </t>
                                <t t-else="">
                                    <span
                                        t-attf-class="rasci-task-label #{state.currentUserCanEdit ? '' : 'rasci-readonly'}"
                                        t-esc="task.name"
                                        t-on-dblclick="() => state.currentUserCanEdit and this.onTaskNameDblClick(task)"
                                        t-att-title="state.currentUserCanEdit ? 'Double-click to rename' : ''"
                                    />
                                </t>
                                <select
                                    class="rasci-state-select"
                                    t-att-class="'rasci-state-' + task.state"
                                    t-att-disabled="!state.currentUserCanEdit or this.props.record.data.state !== 'active'"
                                    t-on-change="(ev) => this.onStateChange(ev, task)">
                                    <t t-foreach="stateOptions" t-as="opt" t-key="opt.value">
                                        <option
                                            t-att-value="opt.value"
                                            t-att-selected="opt.value === task.state"
                                            t-esc="opt.label"/>
                                    </t>
                                </select>
                                <t t-if="state.currentUserCanEdit">
                                    <button
                                        class="rasci-task-delete-btn"
                                        t-on-click="() => this.onDeleteTask(task)"
                                        title="Retirer de la matrice">✕</button>
                                </t>
                            </td>
                            <t t-foreach="state.members" t-as="emp" t-key="emp.id">
                                <td
                                    class="rasci-cell rasci-cell-multi"
                                    t-att-class="(state.dragSourceMemberId === emp.id ? ' rasci-col-dragging-cell' : '') + (state.dragOverMemberId === emp.id ? ' rasci-col-drag-over-cell' : '')"
                                    t-on-contextmenu="(ev) => ev.preventDefault()">
                                    <t t-foreach="ROLE_CYCLE" t-as="role" t-key="role">
                                        <t t-set="active" t-value="hasRole(task.id, emp.id, role)"/>
                                        <span
                                            t-attf-class="rasci-badge-toggle rasci-badge-#{role} #{active ? 'active' : 'inactive'} #{active and hasReport(task.id, emp.id, role) ? 'has-report' : ''}"
                                            t-esc="role"
                                            t-on-click="(ev) => this.onBadgeClick(ev, task.id, emp.id, role)"
                                            t-on-contextmenu="(ev) => this.onBadgeContextMenu(ev, task.id, emp.id, role)"
                                            t-att-title="active ? ROLE_LABELS[role] + ' — clic droit pour décrire' : 'Cliquer pour assigner ' + ROLE_LABELS[role]"
                                        />
                                    </t>
                                </td>
                            </t>
                            <td style="width:36px; padding:0;"/>
                        </tr>
                    </t>
                    <tr class="rasci-add-task-row">
                        <td t-att-colspan="state.members.length + 3">
                            <t t-if="state.addingTask">
                                <input
                                    class="rasci-task-input rasci-new-task-input"
                                    placeholder="Libellé de la tâche…"
                                    t-on-blur="(ev) => this.onNewTaskBlur(ev)"
                                    t-on-keydown="(ev) => this.onNewTaskKey(ev)"
                                />
                            </t>
                            <t t-else="">
                                <button class="rasci-add-task-btn" t-on-click="() => this.onAddTask()">
                                    + Ajouter une tâche
                                </button>
                            </t>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Description modal -->
        <t t-if="state.editingCell">
            <div class="rasci-desc-overlay" t-on-click="(ev) => this.onOverlayClick(ev)">
                <div class="rasci-desc-modal">
                    <div class="rasci-desc-modal-header">
                        <strong>
                            <t t-esc="state.editingCell.roleName"/> —
                            <t t-esc="state.editingCell.taskName"/> /
                            <t t-esc="state.editingCell.empName"/>
                        </strong>
                        <button class="rasci-desc-close" t-on-click="() => this.closeDescModal()">✕</button>
                    </div>
                    <div class="rasci-desc-body">
                        <label class="rasci-desc-label">Rôle spécifique</label>
                        <input
                            class="rasci-desc-input"
                            placeholder="Précisez le rôle…"
                            t-att-value="state.editingCell.description"
                            t-on-input="(ev) => this.onDescInput(ev)"
                        />
                        <label class="rasci-desc-label mt-3">Rapport</label>
                        <textarea
                            class="rasci-desc-textarea"
                            placeholder="Rapport sur cette tâche…"
                            t-att-value="state.editingCell.report"
                            t-on-input="(ev) => this.onReportInput(ev)"
                        />
                    </div>
                    <div class="rasci-desc-footer">
                        <button class="btn btn-primary btn-sm" t-on-click="() => this.saveDescription()">Sauvegarder</button>
                        <button class="btn btn-secondary btn-sm ms-2" t-on-click="() => this.closeDescModal()">Annuler</button>
                    </div>
                </div>
            </div>
        </t>

        <div class="mt-3 p-2 bg-light border rounded d-flex flex-wrap gap-3 align-items-center small">
            <strong>Legende :</strong>
            <t t-foreach="roleEntries" t-as="entry" t-key="entry.key">
                <span>
                    <span t-attf-class="rasci-badge-#{entry.key}" t-esc="entry.key"/>
                    <span class="ms-1" t-esc="entry.label"/>
                </span>
            </t>
            <span><i class="fa fa-globe text-muted"/> = Membre externe</span>
            
            <!-- Help Icon with Tooltip -->
            <span class="ms-auto" 
                title="Clic pour assigner les rôles. Clic droit pour éditer la description. Double-clic sur une tâche pour la renommer. Glisser les colonnes pour les réordonner." 
                data-bs-toggle="tooltip">
                <i class="fa fa-question-circle text-muted" style="cursor: help;"/>
            </span>
        </div>
    </t>
</div>`;

    setup() {
        this.orm       = useService("orm");
        this.actionSvc = useService("action");
        this.notif     = useService("notification");

        this.ROLE_LABELS  = ROLE_LABELS;
        this.ROLE_CYCLE   = ROLE_CYCLE;
        this.stateOptions = STATE_OPTIONS;
        this.roleEntries  = Object.entries(ROLE_LABELS).map(([k, v]) => ({ key: k, label: v }));

        this.state = useState({
            loading: true,
            members: [],
            tasks: [],
            assignments: {},
            addingTask: false,
            editingCell: null,
            showAddMenu: false,
            addMenuX: 0,
            addMenuY: 0,
            addSearch: "",
            currentUserCanEdit: this.props.record.data.state === 'draft',
            currentEmployeeId: false,
            allEmployees: [],
            allDepartments: [],
            // drag-and-drop state
            dragSourceMemberId: null,
            dragOverMemberId: null,
        });

        onWillStart(() => this._load());
        onWillUpdateProps((nextProps) => {
            const nextId = nextProps.record?.resId || nextProps.record?.data?.matrix_project_id || false;
            const isNew = nextProps.record?.isNew;

            if (isNew) {
                Object.assign(this.state, {
                    loading: false,
                    members: [], tasks: [], assignments: {},
                    addingTask: false, editingCell: null,
                    showAddMenu: false, addSearch: "",
                    currentUserCanEdit: true,
                    currentEmployeeId: this.state.currentEmployeeId,
                    allEmployees: this.state.allEmployees,
                    allDepartments: this.state.allDepartments,
                    dragSourceMemberId: null,
                    dragOverMemberId: null,
                });
                return;
            }
            if (nextId && nextId !== this.projectId) this._load(nextId);
        });
    }

    get projectId() {
        return this.props.record?.resId || this.props.record?.data?.matrix_project_id || false;
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    async _load(projectId = this.projectId) {
        this.state.loading = true;
        if (!projectId) { this.state.loading = false; return; }

        const [members, tasks, assignments, allEmployees, allDepartments, currentEmployeeId, serverCanEdit] = await Promise.all([
            this._loadMembers(projectId),
            this._loadTasks(projectId),
            this._loadAssignments(projectId),
            this._loadAllEmployees(),
            this._loadAllDepartments(),
            this._loadCurrentEmployeeId(),
            this.orm.call("rasci.project", "get_current_user_can_edit", [projectId]),
        ]);

        const pilotId = this.props.record.data.pilot_id?.[0];
        const isPilot = !!pilotId && !!currentEmployeeId && pilotId === currentEmployeeId;
        const editable = serverCanEdit || isPilot;

        Object.assign(this.state, {
            loading: false, members, tasks, assignments,
            allEmployees, allDepartments, currentEmployeeId,
            currentUserCanEdit: editable,
        });
    }

    async _loadCurrentEmployeeId() {
        const result = await this.orm.searchRead(
            "hr.employee", [["user_id", "=", this.env.uid]], ["id"], { limit: 1 }
        );
        return result?.[0]?.id || false;
    }

    async _reloadTasks() {
        this.state.tasks = await this._loadTasks(this.projectId);
    }

    async _loadMembers(projectId) {
        const rows = await this.orm.searchRead(
            "rasci.project.member",
            [["project_id", "=", projectId]],
            ["id", "employee_id", "department_id", "sequence", "can_edit", "is_external", "external_name"],
            { order: "sequence asc, id asc" }
        );

        // Build a full department tree so we can find the deepest/leaf department
        // for each employee. We load all departments with their parent to resolve the chain.
        const allDepts = await this._loadAllDepartmentsWithParent();
        const deptMap = {};
        for (const d of allDepts) deptMap[d.id] = d;

        return rows.map(r => {
            const isExternal = r.is_external;
            const name = isExternal ? (r.external_name || "?") : r.employee_id[1];
            const empId = isExternal ? `ext_${r.id}` : r.employee_id[0];

            // Resolve the deepest department name for this member.
            // rasci.project.member has a department_id field that points to the
            // top-level department. For a better label we walk the employee's own
            // department chain (loaded separately below).
            const rawDeptId   = r.department_id ? r.department_id[0] : false;
            const rawDeptName = r.department_id ? r.department_id[1] : "";
            const leafDeptName = this._leafDeptName(rawDeptId, deptMap) || rawDeptName;

            return {
                id:         empId,
                name:       name,
                shortName:  this._toShortName(name),
                deptId:     rawDeptId,
                deptName:   leafDeptName,
                memberId:   r.id,
                canEdit:    !isExternal && (r.can_edit || r.employee_id?.[0] === this.props.record.data.pilot_id?.[0]),
                isExternal: isExternal,
                sequence:   r.sequence,
            };
        });
    }

    /**
     * Returns the name of the deepest (leaf) department in the hierarchy
     * rooted at deptId, using deptMap which maps id → { id, name, parent_id }.
     *
     * Strategy: walk DOWN — find any dept whose complete ancestor chain includes
     * deptId, and that has no children in the map. If none found, use deptId's
     * own name (it is already a leaf or unknown).
     */
    _leafDeptName(deptId, deptMap) {
        if (!deptId || !deptMap[deptId]) return "";

        // Build child map
        const children = {};
        for (const d of Object.values(deptMap)) {
            const pid = d.parent_id ? d.parent_id[0] : null;
            if (pid) {
                if (!children[pid]) children[pid] = [];
                children[pid].push(d.id);
            }
        }

        // BFS/DFS to collect all descendants of deptId
        const descendants = [];
        const queue = [deptId];
        while (queue.length) {
            const cur = queue.shift();
            const kids = children[cur] || [];
            if (!kids.length && cur !== deptId) {
                descendants.push(cur); // leaf node
            }
            queue.push(...kids);
        }

        // If the dept itself has no children it IS the leaf
        if (!children[deptId] || !children[deptId].length) {
            return deptMap[deptId].name;
        }

        // Return the name of the first leaf found (closest leaf in BFS order)
        if (descendants.length) {
            return deptMap[descendants[0]].name;
        }

        return deptMap[deptId].name;
    }

    async _loadAllDepartmentsWithParent() {
        return await this.orm.searchRead(
            "hr.department", [], ["id", "name", "parent_id"], { order: "name asc" }
        );
    }

    async _loadAllEmployees() {
        return await this.orm.searchRead(
            "hr.employee", [["active", "=", true]], ["id", "name", "department_id"], { order: "name asc" }
        );
    }

    async _loadAllDepartments() {
        return await this.orm.searchRead(
            "hr.department", [], ["id", "name"], { order: "name asc" }
        );
    }

    async _loadTasks(projectId) {
        const rows = await this.orm.searchRead(
            "rasci.task",
            [["project_id", "=", projectId]],
            ["id", "name", "state", "sequence", "open_help_request_count"],
            { order: "sequence asc, id asc" }
        );
        return rows.map(r => ({
            id: r.id, name: r.name, state: r.state,
            openHelp: r.open_help_request_count || 0, editing: false,
        }));
    }

    async _loadAssignments(projectId) {
        return await this.orm.call("rasci.role.assignment", "get_matrix_data", [projectId]);
    }

    // ── Drag-and-drop column reordering ───────────────────────────────────────

    onColDragStart(ev, emp) {
        if (!this.state.currentUserCanEdit) { ev.preventDefault(); return; }
        this.state.dragSourceMemberId = emp.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(emp.id));
        // Slight delay so the drag image renders before the opacity change
        setTimeout(() => {}, 0);
    }

    onColDragOver(ev, emp) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        if (emp.id !== this.state.dragSourceMemberId) {
            this.state.dragOverMemberId = emp.id;
        }
    }

    onColDragLeave(ev, emp) {
        if (this.state.dragOverMemberId === emp.id) {
            this.state.dragOverMemberId = null;
        }
    }

    async onColDrop(ev, targetEmp) {
        ev.preventDefault();
        const sourceId = this.state.dragSourceMemberId;
        this.state.dragSourceMemberId = null;
        this.state.dragOverMemberId   = null;

        if (!sourceId || sourceId === targetEmp.id) return;

        const members = this.state.members;
        const fromIdx = members.findIndex(m => m.id === sourceId);
        const toIdx   = members.findIndex(m => m.id === targetEmp.id);
        if (fromIdx === -1 || toIdx === -1) return;

        // Reorder locally
        const [moved] = members.splice(fromIdx, 1);
        members.splice(toIdx, 0, moved);

        // Persist new sequences
        await this._persistMemberSequences();
    }

    onColDragEnd(ev) {
        this.state.dragSourceMemberId = null;
        this.state.dragOverMemberId   = null;
    }

    async _persistMemberSequences() {
        // Write each member's new sequence (10-based) to the database
        const writes = this.state.members.map((m, idx) => {
            const seq = (idx + 1) * 10;
            m.sequence = seq;
            return this.orm.write("rasci.project.member", [m.memberId], { sequence: seq });
        });
        try {
            await Promise.all(writes);
        } catch(e) {
            console.error("Erreur lors de la sauvegarde de l'ordre des colonnes:", e);
            this.notif.add("N'a pas pu sauvegarder l'ordre des colonnes.", { type: "danger" });
        }
    }

    // ── Add member menu ───────────────────────────────────────────────────────

    get filteredAddOptions() {
        const search = this.state.addSearch.toLowerCase().trim();
        // Collect already-present internal employee ids
        const existingEmpIds = new Set(
            this.state.members.filter(m => !m.isExternal).map(m => m.id)
        );
        const options = [];

        // ① External guest — shown whenever user has typed something
        if (search.length >= 1) {
            options.push({
                key:  'external_new',
                type: 'external',
                name: this.state.addSearch.trim(),
            });
        }

        // ② Departments
        for (const dept of this.state.allDepartments) {
            const empsInDept = this.state.allEmployees.filter(
                e => e.department_id?.[0] === dept.id && !existingEmpIds.has(e.id)
            );
            if (!empsInDept.length) continue;
            if (!search || dept.name.toLowerCase().includes(search)) {
                options.push({
                    key: `dept_${dept.id}`, type: "department",
                    id: dept.id, name: dept.name,
                    count: empsInDept.length, employees: empsInDept,
                });
            }
        }

        // ③ Individual employees
        for (const emp of this.state.allEmployees) {
            if (existingEmpIds.has(emp.id)) continue;
            if (!search || emp.name.toLowerCase().includes(search)) {
                options.push({
                    key: `emp_${emp.id}`, type: "employee",
                    id: emp.id, name: emp.name,
                    deptName: emp.department_id?.[1] || "",
                });
            }
        }

        return options.slice(0, 21);
    }

    async openAddMenu(ev) {
        if (!this.state.currentUserCanEdit) return;
        const rect = ev.currentTarget.getBoundingClientRect();
        await this._ensureSaved();

        const menuWidth = 280, menuHeight = 320;
        let x = rect.left, y = rect.bottom + 4;
        if (x + menuWidth  > window.innerWidth)  x = window.innerWidth  - menuWidth  - 8;
        if (y + menuHeight > window.innerHeight) y = rect.top - menuHeight - 4;

        this.state.addMenuX    = Math.max(8, x);
        this.state.addMenuY    = Math.max(8, y);
        this.state.addSearch   = "";
        this.state.showAddMenu = true;

        setTimeout(() => {
            const input = document.querySelector(".rasci-add-search-input");
            if (input) input.focus();
        }, 50);
    }

    onAddOverlayClick(ev) {
        if (ev.target.classList.contains("rasci-add-overlay")) this.state.showAddMenu = false;
    }

    onAddSearch(ev) { this.state.addSearch = ev.target.value; }

    onAddSearchKey(ev) { if (ev.key === "Escape") this.state.showAddMenu = false; }

    async onAddMember(opt) {
        this.state.showAddMenu = false;

        // ── External guest ────────────────────────────────────────────────────
        if (opt.type === 'external') {
            const name = opt.name.trim();
            if (!name) return;
            try {
                const result = await this.orm.create("rasci.project.member", [{
                    project_id:    this.projectId,
                    is_external:   true,
                    external_name: name,
                    sequence:      (this.state.members.length + 1) * 10,
                }]);
                const memberId = Array.isArray(result) ? result[0] : result;
                this.state.members.push({
                    id:         `ext_${memberId}`,
                    name:       name,
                    shortName:  this._toShortName(name),
                    deptId:     false,
                    deptName:   "",
                    memberId:   memberId,
                    canEdit:    false,
                    isExternal: true,
                    sequence:   (this.state.members.length) * 10,
                });
            } catch(e) {
                console.error("Erreur ajout externe:", e);
                this.notif.add(`Erreur lors de l'ajout de "${name}".`, { type: "danger" });
            }
            return;
        }

        // ── Employee / Department ─────────────────────────────────────────────
        const toAdd = opt.type === "department"
            ? opt.employees
            : [{ id: opt.id, name: opt.name, department_id: [null, opt.deptName] }];

        const existingEmpIds = new Set(
            this.state.members.filter(m => !m.isExternal).map(m => m.id)
        );
        for (const emp of toAdd) {
            if (existingEmpIds.has(emp.id)) continue;
            try {
                const result = await this.orm.create("rasci.project.member", [{
                    project_id:  this.projectId,
                    employee_id: emp.id,
                    sequence:    (this.state.members.length + 1) * 10,
                }]);
                const memberId = Array.isArray(result) ? result[0] : result;
                this.state.members.push({
                    id:         emp.id,
                    name:       emp.name,
                    shortName:  this._toShortName(emp.name),
                    deptId:     emp.department_id?.[0] || false,
                    deptName:   emp.department_id?.[1] || "",
                    memberId:   memberId,
                    canEdit:    false,
                    isExternal: false,
                    sequence:   (this.state.members.length) * 10,
                });
                existingEmpIds.add(emp.id);
            } catch(e) {
                console.error("Erreur ajout membre:", e);
                this.notif.add(`Erreur sur l'ajout de ${emp.name}.`, { type: "danger" });
            }
        }
    }

    async onRemoveMember(emp) {
        if (!confirm(`Retirer ${emp.name} de la matrice ? Tous ses rôles sur ce projet seront définitivement supprimés.`)) return;
        try {
            await this.orm.unlink("rasci.project.member", [emp.memberId]);
            for (const key of Object.keys(this.state.assignments)) {
                if (key.endsWith(`_${emp.id}`)) delete this.state.assignments[key];
            }
            const idx = this.state.members.findIndex(m => m.id === emp.id);
            if (idx !== -1) this.state.members.splice(idx, 1);
            this.notif.add(`${emp.name} a été retiré du projet.`, { type: "success" });
        } catch(e) {
            console.error("Retirer membre erreur:", e);
            this.notif.add("Erreur lors du retrait du membre.", { type: "danger" });
        }
    }

    isMemberPilot(emp) {
        return !emp.isExternal && emp.id === this.props.record.data.pilot_id?.[0];
    }

    async onToggleCanEdit(emp) {
        if (emp.isExternal || this.isMemberPilot(emp)) return;
        const newVal = !emp.canEdit;
        emp.canEdit = newVal;
        try {
            await this.orm.write("rasci.project.member", [emp.memberId], { can_edit: newVal });
            this.notif.add(
                newVal ? `${emp.name} peut maintenant modifier la matrice.`
                       : `${emp.name} ne peut plus modifier la matrice.`,
                { type: "success", sticky: false }
            );
        } catch(e) {
            emp.canEdit = !newVal;
            this.notif.add("Erreur lors de la mise à jour des droits.", { type: "danger" });
        }
    }

    // ── Badge / role helpers ──────────────────────────────────────────────────

    _memberKey(emp) {
        return emp.isExternal ? emp.id : emp.id;
    }

    async onBadgeClick(ev, taskId, empId, role) {
        if (!this.state.currentUserCanEdit) return;
        ev.stopPropagation();
        const key     = `${taskId}_${empId}`;
        const current = this.state.assignments[key] || [];
        const isActive = current.some(a => a.role === role);
        const desc     = current.find(a => a.role === role)?.description || '';

        const ROLE_ORDER = ['R', 'A', 'S', 'C', 'I'];
        if (isActive) {
            this.state.assignments[key] = current.filter(a => a.role !== role);
        } else {
            const updated = [...current, { role, description: '' }];
            updated.sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
            this.state.assignments[key] = updated;
        }

        try {
            await this.orm.call("rasci.role.assignment", "set_role", [taskId, empId, role, desc]);
        } catch(e) {
            this.state.assignments[key] = current;
            this.notif.add("N'a pas pu enregistrer l'attribution de rôle.", { type: "danger" });
        }
    }

    hasReport(taskId, empId, role) {
        return !!(this.getAssignment(taskId, empId).find(r => r.role === role)?.report);
    }

    onBadgeContextMenu(ev, taskId, empId, role) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!this.hasRole(taskId, empId, role)) return;
        const task = this.state.tasks.find(t => t.id === taskId);
        const emp  = this.state.members.find(e => e.id === empId);
        const current = this.getAssignment(taskId, empId).find(a => a.role === role) || {};
        this.state.editingCell = {
            taskId, empId, role,
            taskName:    task?.name || '',
            empName:     emp?.name || '',
            roleName:    ROLE_LABELS[role] || role,
            description: current.description || '',
            report:      current.report || '',
        };
    }

    getAssignment(taskId, empId) {
        return this.state.assignments[`${taskId}_${empId}`] || [];
    }

    hasRole(taskId, empId, role) {
        return this.getAssignment(taskId, empId).some(a => a.role === role);
    }

    _toShortName(full) {
        if (!full) return "?";
        const parts = full.trim().split(/\s+/);
        if (parts.length === 1) return parts[0];
        return `${parts[0]} ${parts[parts.length - 1][0]}.`;
    }

    // ── Description modal ─────────────────────────────────────────────────────

    onDescInput(ev)   { if (this.state.editingCell) this.state.editingCell.description = ev.target.value; }
    onReportInput(ev) { if (this.state.editingCell) this.state.editingCell.report = ev.target.value; }

    async saveDescription() {
        const { taskId, empId, role, description, report } = this.state.editingCell;
        const key   = `${taskId}_${empId}`;
        const entry = (this.state.assignments[key] || []).find(a => a.role === role);
        if (entry) { entry.description = description; entry.report = report; }
        try {
            await this.orm.call("rasci.role.assignment", "update_role", [taskId, empId, role, description, report]);
            this.notif.add("Enregistré.", { type: "success", sticky: false });
        } catch(e) {
            this.notif.add("N'a pas pu enregistrer.", { type: "danger" });
        }
        this.closeDescModal();
    }

    closeDescModal()  { this.state.editingCell = null; }
    onOverlayClick(ev) {
        if (ev.target.classList.contains("rasci-desc-overlay")) this.closeDescModal();
    }

    // ── Task CRUD ─────────────────────────────────────────────────────────────

    _recomputeProgress() {
        const tasks = this.state.tasks;
        const total = tasks.length;
        const done  = tasks.filter(t => t.state === "done").length;
        this.props.record.update({ progress: total ? (done / total * 100) : 0 });
    }

    async _ensureSaved() {
        if (this.props.record.isNew) {
            const wasEditable = this.state.currentUserCanEdit;
            await this.props.record.save();
            await this._load();
            if (wasEditable) this.state.currentUserCanEdit = true;
        }
    }

    async _createTask(name) {
        try {
            const result = await this.orm.create("rasci.task", [{
                name, project_id: this.projectId,
                state: "not_started",
                sequence: (this.state.tasks.length + 1) * 10,
            }]);
            const id = Array.isArray(result) ? result[0] : result;
            this.state.tasks.push({ id, name, state: "not_started", openHelp: 0, editing: false });
            this._recomputeProgress();
            this.notif.add(`Tâche "${name}" créée.`, { type: "success", sticky: false });
        } catch(e) {
            this.notif.add("N'a pas pu créer la tâche.", { type: "danger" });
        }
    }

    async onAddTask() {
        if (!this.state.currentUserCanEdit) return;
        await this._ensureSaved();
        this.state.addingTask = true;
        setTimeout(() => {
            const input = document.querySelector(".rasci-new-task-input");
            if (input) input.focus();
        }, 50);
    }

    async onNewTaskBlur(ev) {
        if (ev.target.dataset.confirmed) return;
        const name = ev.target.value.trim();
        if (name) await this._createTask(name);
        this.state.addingTask = false;
    }

    async onNewTaskKey(ev) {
        if (ev.key === "Enter") {
            ev.target.dataset.confirmed = "true";
            const name = ev.target.value.trim();
            if (name) await this._createTask(name);
            this.state.addingTask = false;
        } else if (ev.key === "Escape") {
            ev.target.dataset.confirmed = "true";
            this.state.addingTask = false;
        }
    }

    onTaskNameDblClick(task) { if (this.state.currentUserCanEdit) task.editing = true; }

    async onTaskNameBlur(ev, task) {
        const name = ev.target.value.trim();
        if (name && name !== task.name) await this._renameTask(task, name);
        task.editing = false;
    }

    async onTaskNameKey(ev, task) {
        if (ev.key === "Enter") {
            const name = ev.target.value.trim();
            if (name && name !== task.name) await this._renameTask(task, name);
            task.editing = false;
        } else if (ev.key === "Escape") {
            task.editing = false;
        }
    }

    async _renameTask(task, name) {
        const prev = task.name;
        task.name = name;
        try {
            await this.orm.write("rasci.task", [task.id], { name });
        } catch(e) {
            task.name = prev;
            this.notif.add("N'a pas pu renommer la tâche.", { type: "danger" });
        }
    }

    async onDeleteTask(task) {
        if (!this.state.currentUserCanEdit) return;
        if (!confirm(`Supprimer la tâche "${task.name}" ?`)) return;
        try {
            await this.orm.unlink("rasci.task", [task.id]);
            const idx = this.state.tasks.findIndex(t => t.id === task.id);
            if (idx !== -1) this.state.tasks.splice(idx, 1);
            for (const key of Object.keys(this.state.assignments)) {
                if (key.startsWith(`${task.id}_`)) delete this.state.assignments[key];
            }
            this._recomputeProgress();
            this.notif.add(`Tâche "${task.name}" supprimée.`, { type: "success", sticky: false });
        } catch(e) {
            this.notif.add("N'a pas pu supprimer la tâche.", { type: "danger" });
        }
    }

    async onStateChange(ev, task) {
        if (!this.state.currentUserCanEdit) return;
        const newState = ev.target.value;
        const prev     = task.state;
        task.state     = newState;
        try {
            await this.orm.write("rasci.task", [task.id], { state: newState });
            this.notif.add(
                `"${task.name}" → ${STATE_OPTIONS.find(o => o.value === newState)?.label || newState}`,
                { type: "success", sticky: false }
            );
            this._recomputeProgress();
        } catch(e) {
            task.state = prev;
            this.notif.add("N'a pas pu mettre à jour l'état de la tâche.", { type: "danger" });
        }
    }
}

registry.category("fields").add("rasci_matrix", {
    component: RasciMatrixWidget,
    displayName: "Matrice RASCI",
    supportedTypes: ["integer"],
});
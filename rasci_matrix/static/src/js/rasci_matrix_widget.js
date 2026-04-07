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
    { value: "done",        label: "✓ Terminé"         },
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
                            placeholder="Rechercher un employé ou un département…"
                            t-att-value="state.addSearch"
                            t-on-input="(ev) => this.onAddSearch(ev)"
                            t-on-keydown="(ev) => this.onAddSearchKey(ev)"
                        />
                    </div>
                    <div class="rasci-add-menu-list">
                        <t t-foreach="filteredAddOptions" t-as="opt" t-key="opt.key">
                            <div
                                class="rasci-add-menu-item"
                                t-att-class="opt.type === 'department' ? 'rasci-add-dept' : 'rasci-add-emp'"
                                t-on-click="() => this.onAddMember(opt)">
                                <t t-if="opt.type === 'department'">
                                    <i class="fa fa-building-o me-2"/>
                                    <strong t-esc="opt.name"/>
                                    <span class="text-muted ms-1">(<t t-esc="opt.count"/> employees)</span>
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
                            <div class="rasci-add-menu-empty">No results</div>
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
                            <th>
                                <div class="rasci-emp-header">
                                    <span t-att-title="emp.name" t-esc="emp.shortName"/>
                                    <t t-if="emp.deptName">
                                        <small class="rasci-emp-dept" t-esc="emp.deptName"/>
                                    </t>
                                    <div class="rasci-emp-actions">
                                        <t t-if="state.currentUserCanEdit">
                                            <!-- Pencil: toggles edit permission for this member -->
                                            <i
                                                t-attf-class="fa fa-pencil rasci-edit-toggle #{isMemberPilot(emp) || emp.canEdit ? 'rasci-edit-on' : 'rasci-edit-off'} #{isMemberPilot(emp) ? 'rasci-edit-locked' : ''}"
                                                t-att-title="isMemberPilot(emp) ? 'Pilote du projet — édition toujours autorisée'
                                                            : emp.canEdit ? 'Retirer le droit d\'édition'
                                                            : 'Autoriser l\'édition'"
                                                t-on-click="() => this.onToggleCanEdit(emp)"
                                            />
                                            <!-- X: remove from matrix -->
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
                            <button class="rasci-add-col-btn" t-on-click="(ev) => this.openAddMenu(ev)" title="Add employee or department">
                                +
                            </button>
                        </th>
                        <!-- <th class="rasci-add-support-header">Demandes de support</th> -->
                    </tr>
                </thead>
                <tbody>
                    <!-- <t t-if="!state.members.length">
                        <tr>
                            <td t-att-colspan="3" class="text-center text-muted p-4">
                                Cliquez sur <strong>+</strong> pour ajouter des employés ou des départements.
                            </td>
                        </tr>
                    </t> -->
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
                                    t-att-title="!state.currentUserCanEdit ? 'Vous n\'avez pas les droits pour modifier l\'état'
                                                : this.props.record.data.state !== 'active' ? 'Activer le projet pour changer d\'état'
                                                : ''"
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
                                <t t-set="assignment" t-value="getAssignment(task.id, emp.id)"/>
                                <td
                                    class="rasci-cell rasci-cell-multi"
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
                            <!-- <td class="text-center" style="padding:4px 6px; vertical-align:middle;">
                                <t t-if="task.openHelp > 0">
                                    <span class="rasci-task-help-badge" t-esc="task.openHelp"/>
                                </t>
                                <button class="rasci-task-help-btn" t-on-click="() => this.onRequestHelp(task)">
                                    ? Support
                                </button>
                            </td> -->
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
            <span class="text-muted">— Clic pour assigner les rôles. Clic droit pour éditer la description. Double-clic sur une tâche pour la renommer.</span>
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
            currentUserCanEdit: this.props.record.data.state === 'draft',  // ← true immediately for draft
            currentEmployeeId: false,
            allEmployees: [],
            allDepartments: [],
        });

        onWillStart(() => this._load());
        onWillUpdateProps((nextProps) => {
            const nextId = nextProps.record?.resId || nextProps.record?.data?.matrix_project_id || false;
            const isNew = nextProps.record?.isNew;
            
            if (isNew) {
                // Reset everything for a blank new record
                Object.assign(this.state, {
                    loading: false,
                    members: [],
                    tasks: [],
                    assignments: {},
                    addingTask: false,
                    editingCell: null,
                    showAddMenu: false,
                    addSearch: "",
                    currentUserCanEdit: true,  // new record → creator can always edit
                    currentEmployeeId: this.state.currentEmployeeId,  // keep, no need to reload
                    allEmployees: this.state.allEmployees,            // keep, no need to reload
                    allDepartments: this.state.allDepartments,        // keep, no need to reload
                });
                return;
            }

            if (nextId && nextId !== this.projectId) {
                this._load(nextId);
            }
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

        const projectState = this.props.record.data.state;
        const pilotId = this.props.record.data.pilot_id?.[0];
        const isPilot = !!pilotId && !!currentEmployeeId && pilotId === currentEmployeeId;

        // serverCanEdit already accounts for pilot check on Python side
        const editable = serverCanEdit || isPilot;

        Object.assign(this.state, {
            loading: false,
            members,
            tasks,
            assignments,
            allEmployees,
            allDepartments,
            currentEmployeeId,
            currentUserCanEdit: editable,
        });
    }

    async _loadCurrentEmployeeId() {
        const result = await this.orm.searchRead(
            "hr.employee",
            [["user_id", "=", this.env.uid]],
            ["id"],
            { limit: 1 }
        );
        return result?.[0]?.id || false;
    }

    // Separate lightweight reload that preserves currentUserCanEdit
    async _reloadTasks() {
        const tasks = await this._loadTasks(this.projectId);
        this.state.tasks = tasks;
    }

    async _createTask(name) {
        try {
            const result = await this.orm.create("rasci.task", [{
                name, project_id: this.projectId,
                state: "not_started",
                sequence: (this.state.tasks.length + 1) * 10,
            }]);
            const id = Array.isArray(result) ? result[0] : result;
            // Push directly to state — no full reload needed
            this.state.tasks.push({ id, name, state: "not_started", openHelp: 0, editing: false });
            this._recomputeProgress();
            this.notif.add(`Tâche "${name}" créée.`, { type: "success", sticky: false });
        } catch(e) {
            console.error("create task error:", e);
            this.notif.add("N'a pas pu créer la tâche.", { type: "danger" });
        }
    }

    _recomputeProgress() {
        // Does NOT touch currentUserCanEdit — safe to call anytime
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
            if (wasEditable) {
                this.state.currentUserCanEdit = true;
            }
        }
    }

    async _loadMembers(projectId) {
        const rows = await this.orm.searchRead(
            "rasci.project.member",
            [["project_id", "=", projectId]],
            ["id", "employee_id", "department_id", "sequence", "can_edit"],  // ← add can_edit
            { order: "sequence asc, id asc" }
        );
        return rows.map(r => ({
            id:        r.employee_id[0],
            name:      r.employee_id[1],
            shortName: this._toShortName(r.employee_id[1]),
            deptId:    r.department_id ? r.department_id[0] : false,
            deptName:  r.department_id ? r.department_id[1] : "",
            memberId:  r.id,
            canEdit:   r.can_edit || r.employee_id[0] === this.props.record.data.pilot_id?.[0],  // ← pilot always true
        }));
    }

    async _loadAllEmployees() {
        return await this.orm.searchRead(
            "hr.employee",
            [["active", "=", true]],
            ["id", "name", "department_id"],
            { order: "name asc" }
        );
    }

    async _loadAllDepartments() {
        return await this.orm.searchRead(
            "hr.department",
            [],
            ["id", "name"],
            { order: "name asc" }
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

    // ── Add member menu ───────────────────────────────────────────────────────

    get filteredAddOptions() {
        const search = this.state.addSearch.toLowerCase();
        const existingIds = new Set(this.state.members.map(m => m.id));
        const options = [];

        // Departments first
        for (const dept of this.state.allDepartments) {
            const empsInDept = this.state.allEmployees.filter(
                e => e.department_id?.[0] === dept.id && !existingIds.has(e.id)
            );
            if (!empsInDept.length) continue;
            if (!search || dept.name.toLowerCase().includes(search)) {
                options.push({
                    key:   `dept_${dept.id}`,
                    type:  "department",
                    id:    dept.id,
                    name:  dept.name,
                    count: empsInDept.length,
                    employees: empsInDept,
                });
            }
        }

        // Individual employees
        for (const emp of this.state.allEmployees) {
            if (existingIds.has(emp.id)) continue;
            if (!search || emp.name.toLowerCase().includes(search)) {
                options.push({
                    key:     `emp_${emp.id}`,
                    type:    "employee",
                    id:      emp.id,
                    name:    emp.name,
                    deptName: emp.department_id?.[1] || "",
                });
            }
        }

        return options.slice(0, 20);  // cap at 20 for performance
    }

    async openAddMenu(ev) {
        if (!this.state.currentUserCanEdit) return;
        
        // Capture rect BEFORE any await — ev.currentTarget becomes null after async suspension
        const rect = ev.currentTarget.getBoundingClientRect();
        
        await this._ensureSaved();
        
        const menuWidth = 280;
        const menuHeight = 320;

        let x = rect.left;
        let y = rect.bottom + 4;

        if (x + menuWidth > window.innerWidth) {
            x = window.innerWidth - menuWidth - 8;
        }
        if (y + menuHeight > window.innerHeight) {
            y = rect.top - menuHeight - 4;
        }

        this.state.addMenuX  = Math.max(8, x);
        this.state.addMenuY  = Math.max(8, y);
        this.state.addSearch = "";
        this.state.showAddMenu = true;

        setTimeout(() => {
            const input = document.querySelector(".rasci-add-search-input");
            if (input) input.focus();
        }, 50);
    }

    onAddOverlayClick(ev) {
        if (ev.target.classList.contains("rasci-add-overlay")) {
            this.state.showAddMenu = false;
        }
    }

    onAddSearch(ev) { this.state.addSearch = ev.target.value; }

    onAddSearchKey(ev) { if (ev.key === "Escape") this.state.showAddMenu = false; }

    async onAddMember(opt) {
        this.state.showAddMenu = false;
        const toAdd = opt.type === "department"
            ? opt.employees
            : [{ id: opt.id, name: opt.name, department_id: [null, opt.deptName] }];

        const existingIds = new Set(this.state.members.map(m => m.id));
        for (const emp of toAdd) {
            if (existingIds.has(emp.id)) continue;
            try {
                const memberId = await this.orm.create("rasci.project.member", [{
                    project_id:  this.projectId,
                    employee_id: emp.id,
                    sequence:    (this.state.members.length + 1) * 10,
                }]);
                const id = Array.isArray(memberId) ? memberId[0] : memberId;
                const newMember = {
                    id:        emp.id,
                    name:      emp.name,
                    shortName: this._toShortName(emp.name),
                    deptId:    emp.department_id?.[0] || false,
                    deptName:  emp.department_id?.[1] || "",
                    memberId:  id,
                    canEdit:   false,
                };
                this.state.members.push(newMember);
                existingIds.add(emp.id);
            } catch(e) {
                console.error("Nouveau membre erreur:", e);
                this.notif.add(`Erreur sur l'ajout de ${emp.name}.`, { type: "danger" });
            }
        }
    }

    async onRemoveMember(emp) {
        // 1. Restriction: Only allow modification if project is active
        // if (this.props.record.data.state !== 'active') {
        //     this.notif.add("Le projet doit être 'Actif' pour modifier les membres.", { type: "warning" });
        //     return;
        // }

        // 2. Confirmation
        if (!confirm(`Retirer ${emp.name} de la matrice? Tous ses rôles sur ce projet seront définitivement supprimés.`)) {
            return;
        }

        try {
            // 3. Delete the member record (Python unlink handles role cleanup)
            await this.orm.unlink("rasci.project.member", [emp.memberId]);

            // 4. Update Local State (UI)
            // Remove all role assignments for this employee from the local state object
            for (const key of Object.keys(this.state.assignments)) {
                if (key.endsWith(`_${emp.id}`)) {
                    delete this.state.assignments[key];
                }
            }

            // Remove the employee from the column headers list
            const idx = this.state.members.findIndex(m => m.id === emp.id);
            if (idx !== -1) {
                this.state.members.splice(idx, 1);
            }

            this.notif.add(`${emp.name} a été retiré du projet.`, { type: "success" });
            
        } catch(e) {
            console.error("Retirer membre erreur:", e);
            this.notif.add("Erreur lors du retrait du membre.", { type: "danger" });
        }
    }

    isMemberPilot(emp) {
        return emp.id === this.props.record.data.pilot_id?.[0];
    }
    
    async onToggleCanEdit(emp) {
        if (this.isMemberPilot(emp)) return;
        const newVal = !emp.canEdit;
        emp.canEdit = newVal;  // optimistic
        try {
            await this.orm.write("rasci.project.member", [emp.memberId], { can_edit: newVal });
            this.notif.add(
                newVal ? `${emp.name} peut maintenant modifier la matrice.`
                    : `${emp.name} ne peut plus modifier la matrice.`,
                { type: "success", sticky: false }
            );
        } catch(e) {
            emp.canEdit = !newVal;  // rollback
            this.notif.add("Erreur lors de la mise à jour des droits.", { type: "danger" });
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    async onBadgeClick(ev, taskId, empId, role) {
        if (!this.state.currentUserCanEdit) return;
        ev.stopPropagation();
        const key = `${taskId}_${empId}`;
        const current = this.state.assignments[key] || [];
        const isActive = current.some(a => a.role === role);
        const desc = current.find(a => a.role === role)?.description || '';

        // Optimistic update
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
            // Rollback
            this.state.assignments[key] = current;
            this.notif.add("N'a pas pu enregistrer l'attribution de rôle.", { type: "danger" });
        }
    }

    hasReport(taskId, empId, role) {
        const a = this.getAssignment(taskId, empId).find(r => r.role === role);
        return !!(a?.report);
    }

    onBadgeContextMenu(ev, taskId, empId, role) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!this.hasRole(taskId, empId, role)) return;
        const task = this.state.tasks.find(t => t.id === taskId);
        const emp  = this.state.members.find(e => e.id === empId);
        const assignments = this.getAssignment(taskId, empId);
        const current = assignments.find(a => a.role === role) || {};
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

    getRoleDescription(taskId, empId, role) {
        const a = this.getAssignment(taskId, empId).find(r => r.role === role);
        return a?.description || '';
    }

    _toShortName(full) {
        if (!full) return "?";
        const parts = full.trim().split(/\s+/);
        if (parts.length === 1) return parts[0]; // single word → show fully
        return `${parts[0]} ${parts[parts.length - 1][0]}.`;
    }

    // ── Cell handlers ─────────────────────────────────────────────────────────

    onCellContextMenu(ev, taskId, empId) {
        ev.preventDefault();
        const current = this.state.assignments[`${taskId}_${empId}`] || { role: "", description: "" };
        if (!current.role) return;
        const task = this.state.tasks.find(t => t.id === taskId);
        const emp  = this.state.members.find(e => e.id === empId);
        this.state.editingCell = {
            taskId, empId,
            taskName:    task?.name || "",
            empName:     emp?.name || "",
            roleName:    ROLE_LABELS[current.role] || current.role,
            description: current.description || "",
        };
    }

    onDescInput(ev) {
        if (this.state.editingCell) this.state.editingCell.description = ev.target.value;
    }

    onReportInput(ev) {
        if (this.state.editingCell) this.state.editingCell.report = ev.target.value;
    }

    async saveDescription() {
        const { taskId, empId, role, description, report } = this.state.editingCell;
        const key = `${taskId}_${empId}`;
        const current = this.state.assignments[key] || [];
        const entry = current.find(a => a.role === role);
        if (entry) {
            entry.description = description;
            entry.report = report;
        }
        try {
            await this.orm.call("rasci.role.assignment", "update_role", [taskId, empId, role, description, report]);
            this.notif.add("Enregistré.", { type: "success", sticky: false });
        } catch(e) {
            this.notif.add("N'a pas pu enregistrer.", { type: "danger" });
        }
        this.closeDescModal();
    }

    closeDescModal() { this.state.editingCell = null; }

    onOverlayClick(ev) {
        if (ev.target.classList.contains("rasci-desc-overlay")) this.closeDescModal();
    }

    // ── Task CRUD ─────────────────────────────────────────────────────────────

    async onAddTask() {
        if (!this.state.currentUserCanEdit) return;
        await this._ensureSaved();
        this.state.addingTask = true;
        // Wait for OWL to render the input, then focus it
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

    onTaskNameDblClick(task) {
        if (!this.state.currentUserCanEdit) return;
        task.editing = true; 
    }

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
        if (!confirm(`Delete task "${task.name}"?`)) return;
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
            console.error("Delete error:", e);
            this.notif.add("N'a pas pu supprimer la tâche.", { type: "danger" });
        }
    }

    async onStateChange(ev, task) {
        if (!this.state.currentUserCanEdit) return;
        const newState = ev.target.value;
        const prev     = task.state;
        task.state = newState;
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

    async onRequestHelp(task) {
        await this.actionSvc.doAction({
            type: "ir.actions.act_window",
            name: `Request Help — ${task.name}`,
            res_model: "rasci.help.request",
            view_mode: "form",
            views: [[false, "form"]],
            context: {
                default_task_id:    task.id,
                default_project_id: this.projectId,
                default_name:       `Help needed: ${task.name}`,
            },
            target: "new",
        });
        const refreshed = await this._loadTasks(this.projectId);
        for (const t of refreshed) {
            const existing = this.state.tasks.find(x => x.id === t.id);
            if (existing) existing.openHelp = t.openHelp;
        }
    }
}

registry.category("fields").add("rasci_matrix", {
    component: RasciMatrixWidget,
    displayName: "Matrice RASCI",
    supportedTypes: ["integer"],
});
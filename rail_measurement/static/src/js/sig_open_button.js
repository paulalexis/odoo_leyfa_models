/** @odoo-module **/

import { Component, xml, useEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SigOpenMapButton extends Component {
    static template = xml`
        <button t-att-class="'btn ' + (props.btnClass || 'btn-primary') + ' btn-md'"
                style="height:calc(1.5em + 0.75rem + 2px);padding:0.375rem 0.75rem;font-size:0.875rem;"
                t-on-click="onClick">
            <t t-out="props.label || '🗺️ SIG'"/>
        </button>
    `;

    static props = {
        label: { type: String, optional: true },
        "*": true,
    };

    setup() {
        this.sigMap = useService("sig_map");
        this.env = useEnv();
    }

    onClick() {
        const record = this.env.model?.root;
        const val = record?.data?.sig_controller_id;
        const measurementId = record?.resId;

        if (!val) {
            this.env.services.orm.call(
                record.resModel,
                'action_open_sig_float',
                [[record.resId]],
            ).then((result) => {
                const id = (result && typeof result === 'object') ? result.id : result;
                this.sigMap.open(id, measurementId);
            });
            return;
        }

        const id = Array.isArray(val) ? val[0] : (val.id || val);
        this.sigMap.open(id, measurementId);
    }
}

registry.category("view_widgets").add("sig_open_map", {
    component: SigOpenMapButton,
    extractProps: (attrs, record) => ({
        record,
        label: attrs.options?.label || null,
    }),
});
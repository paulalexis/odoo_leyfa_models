/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";

patch(ListController.prototype, {
    async onButtonClicked(record, button) {
        // If it's our measurement button, save first
        if (button.name === 'action_open_rail_measurement_form') {
            // Check if form has unsaved changes
            const root = this.model.root;
            if (root.isDirty) {
                // Save the form
                await root.save({ stayInEdition: false });
            }
        }
        
        // Call the original method
        return super.onButtonClicked(...arguments);
    }
});
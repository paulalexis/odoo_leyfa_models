/** @odoo-module **/
import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, {
    setup() {
        super.setup();
        this.actionService = useService("action");
    },

    async onUploadButtonClick() {
        // On appelle la fonction sans envoyer d'arguments supplémentaires
        const action = await this.model.orm.call(
            "rail.measurement",
            "action_upload_measurement_file",
            []
        );

        if (action) {
            this.actionService.doAction(action);
        }
    }
});
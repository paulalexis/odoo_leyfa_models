/** @odoo-module **/

import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { patch } from "@web/core/utils/patch";

patch(AutoComplete.prototype, {
    onKeyDown(ev) {
        if (ev.key === "Enter") {
            const inputVal = this.state.inputValue ? this.state.inputValue.trim().toLowerCase() : "";
            if (!inputVal) return super.onKeyDown(ev);

            const { sources, focusedOptionIndex } = this.state;

            // Si l'utilisateur n'a pas surligné d'option avec les flèches
            if (sources.length > 0 && focusedOptionIndex === -1) {
                const allOptions = sources.flatMap(s => s.options || []);
                
                // --- LOGIQUE DE PRIORITÉ ---
                // 1. On cherche s'il y a une correspondance EXACTE (ex: "V2" == "V2")
                let optionToSelect = allOptions.find(opt => 
                    opt.label && opt.label.toLowerCase() === inputVal
                );

                // 2. Si pas de correspondance exacte, on prend la première suggestion (ex: "V2" -> "V2L")
                if (!optionToSelect && allOptions.length > 0) {
                    optionToSelect = allOptions[0];
                }

                if (optionToSelect && optionToSelect.type !== 'search_more') {
                    // On retrouve la source de l'option choisie
                    const source = sources.find(s => s.options.includes(optionToSelect));
                    
                    this.onOptionClick(optionToSelect, source);
                    
                    // Empêche la création d'une nouvelle ligne sur Enter
                    ev.preventDefault();
                    ev.stopPropagation();
                    return;
                }
            }
        }
        super.onKeyDown(ev);
    }
});
/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class LicenseBanner extends Component {
    setup() {
        this.action = useService("action");
        this.state = useState({
            show: false,
            message: "",
            color: "",
            dismissed: false
        });

        onWillStart(async () => {
            try {
                const result = await rpc("/license/status", {});
                if (result && result.show) {
                    this.state.show = true;
                    this.state.message = result.message;
                    this.state.color = result.color;
                }
            } catch (error) {
                console.error("Failed to fetch license status", error);
            }
        });
    }

    onDismiss() {
        this.state.dismissed = true;
    }

    openSettings() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "License Settings",
            res_model: "res.config.settings",
            views: [[false, "form"]],
            target: "current",
            context: { module: "license_management" }
        });
    }
}

LicenseBanner.template = "license_management.LicenseBanner";

// Register the banner to be added to the UI
registry.category("systray").add("license_management.LicenseBannerItem", {
    Component: LicenseBanner,
});

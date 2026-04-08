from frappe import _


def get_data():
    return [
        {
            "module_name": "FonoUC Integration",
            "color": "#5e64ff",
            "icon": "octicon octicon-device-mobile",
            "type": "module",
            "label": _("FonoUC PBX"),
            "description": "PBX Integration — CDR Logs, Campaigns, Agent Status",
        }
    ]


def has_permission():
    return True

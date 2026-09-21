"""Local config file (config.json) loading -- API key and Excel workbook path."""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    changed = False
    if not os.path.exists(CONFIG_PATH):
        config = {
            "api_key": "PASTE_YOUR_PROPLINE_KEY_HERE",
            "tracking_workbook_path": "",
            "tavily_api_key": "PASTE_YOUR_TAVILY_KEY_HERE",
            "groq_api_key": "PASTE_YOUR_GROQ_KEY_HERE",
        }
        changed = True
    else:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        if "tracking_workbook_path" not in config:
            config["tracking_workbook_path"] = ""
            changed = True
        if "tavily_api_key" not in config:
            config["tavily_api_key"] = "PASTE_YOUR_TAVILY_KEY_HERE"
            changed = True
        if "groq_api_key" not in config:
            config["groq_api_key"] = "PASTE_YOUR_GROQ_KEY_HERE"
            changed = True
        if "gemini_api_key" in config:
            del config["gemini_api_key"]
            changed = True
    if changed:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    return config

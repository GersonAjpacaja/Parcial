import os
import subprocess
import yaml
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "dmvpn_portal_2026"

BASE_DIR = "/opt/parcial"
INVENTORY_PATH = os.path.join(BASE_DIR, "inventory", "hosts.yml")
ANSIBLE_BIN = os.path.join(BASE_DIR, "venv", "bin", "ansible-playbook")
DEPLOY_PLAYBOOK = os.path.join(BASE_DIR, "playbooks", "deploy_dmvpn.yml")
REMOVE_PLAYBOOK = os.path.join(BASE_DIR, "playbooks", "eliminar_spoke.yml")
REMOVE_VAR = "target_spoke"  # Cambia esto si eliminar_spoke.yml usa otro nombre de variable


def load_inventory():
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_inventory(data):
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def run_ansible(cmd):
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "0"
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    result = subprocess.run(cmd, cwd=BASE_DIR, env=env, capture_output=True, text=True)
    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode == 0, output.strip()


@app.route("/", methods=["GET"])
def index():
    inv = load_inventory()
    children = inv.get("all", {}).get("children", {})
    hubs = children.get("hubs", {}).get("hosts") or {}
    spokes = children.get("spokes", {}).get("hosts") or {}
    return render_template("index.html", hubs=hubs, spokes=spokes)


@app.route("/add", methods=["POST"])
def add_spoke():
    hostname = request.form.get("hostname", "").strip().upper()
    ip_addr = request.form.get("ip_addr", "").strip()
    node_id = request.form.get("node_id", "").strip()

    if not hostname or not ip_addr or not node_id.isdigit():
        flash("Completa todos los campos para poder continuar (Node ID debe ser numérico).", "error")
        return redirect(url_for("index"))

    inv = load_inventory()
    spokes_section = inv["all"]["children"].setdefault("spokes", {})
    if spokes_section.get("hosts") is None:
        spokes_section["hosts"] = {}

    spokes_section["hosts"][hostname] = {
        "ansible_host": ip_addr,
        "node_id": int(node_id),
    }
    save_inventory(inv)

    success, log_output = run_ansible([ANSIBLE_BIN, DEPLOY_PLAYBOOK, "--limit", hostname])
    inv = load_inventory()
    children = inv.get("all", {}).get("children", {})
    return render_template(
        "index.html",
        hubs=children.get("hubs", {}).get("hosts") or {},
        spokes=children.get("spokes", {}).get("hosts") or {},
        log_output=log_output,
        last_action=f"Alta de sucursal {hostname} ({ip_addr})",
        action_success=success,
    )


@app.route("/remove/<hostname>", methods=["POST"])
def remove_spoke(hostname):
    hostname = hostname.strip().upper()
    success, log_output = run_ansible(
        [ANSIBLE_BIN, REMOVE_PLAYBOOK, "-e", f"{REMOVE_VAR}={hostname}"]
    )

    if success:
        inv = load_inventory()
        spokes_hosts = inv["all"]["children"].get("spokes", {}).get("hosts") or {}
        spokes_hosts.pop(hostname, None)
        inv["all"]["children"]["spokes"]["hosts"] = spokes_hosts
        save_inventory(inv)

    inv = load_inventory()
    children = inv.get("all", {}).get("children", {})
    return render_template(
        "index.html",
        hubs=children.get("hubs", {}).get("hosts") or {},
        spokes=children.get("spokes", {}).get("hosts") or {},
        log_output=log_output,
        last_action=f"Baja de sucursal {hostname} (DMVPN + Zabbix)",
        action_success=success,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

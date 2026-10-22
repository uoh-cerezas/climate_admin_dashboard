from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)
CONFIG_DIR = Path(os.environ.get("CLIMATE_CONFIG_DIR", "/config"))
MONTH_NAMES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def load_yaml(filename: str) -> tuple[dict, list[str]]:
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}, [f"No existe {path}"]
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            return {}, [f"{filename} debe contener un objeto YAML"]
        return value, []
    except (OSError, yaml.YAMLError) as exc:
        return {}, [f"No se pudo leer {filename}: {exc}"]


def valid_clock(value, label: str, errors: list[str], maximum: int = 59) -> None:
    if not isinstance(value, int) or not 0 <= value <= maximum:
        errors.append(f"{label} fuera de rango")


def validate(pipeline: dict, email: dict, load_errors: list[str]) -> dict:
    errors = list(load_errors)
    warnings: list[str] = []
    valid_clock(pipeline.get("schedule_hour"), "hora de generación", errors, 23)
    valid_clock(pipeline.get("schedule_minute"), "minuto de generación", errors)
    valid_clock(email.get("send_hour"), "hora de envío", errors, 23)
    valid_clock(email.get("send_minute"), "minuto de envío", errors)
    for config, key, label in ((pipeline, "schedule_timezone", "schedule_timezone"), (email, "timezone", "timezone de email")):
        try:
            ZoneInfo(str(config.get(key, "")))
        except Exception:
            errors.append(f"{label} inválida")
    for prefix in ("schedule_start", "schedule_end", "season_start"):
        try:
            date(2024, int(pipeline[prefix + "_month"]), int(pipeline[prefix + "_day"]))
        except (KeyError, TypeError, ValueError):
            labels = {"schedule_start": "inicio del período", "schedule_end": "fin del período", "season_start": "inicio de temporada"}
            errors.append(f"fecha {labels[prefix]} inválida")
    metadata = pipeline.get("report_metadata") or {}
    if metadata.get("enabled") and not metadata.get("database"):
        errors.append("report_metadata.database es obligatorio cuando está habilitado")
    if email.get("enabled") and email.get("delivery_method") == "smtp":
        smtp = email.get("smtp") or {}
        if not smtp.get("host") or not smtp.get("port"):
            errors.append("SMTP incompleto")
        if not smtp.get("password_env") and not smtp.get("password_file"):
            errors.append("SMTP no tiene referencia de contraseña")
    if email.get("enabled") and not email.get("sites"):
        warnings.append("correo habilitado sin campos destinatarios")
    return {"errors": errors, "warnings": warnings}


def safe_pipeline(config: dict) -> dict:
    def annual_date(prefix):
        try:
            month = int(config[prefix + "_month"])
            day = int(config[prefix + "_day"])
            date(2000, month, day)
            return f"{datetime.now().year:04d}-{month:02d}-{day:02d}"
        except (KeyError, TypeError, ValueError):
            return ""

    schedule_start = annual_date("schedule_start")
    schedule_end = annual_date("schedule_end")
    def annual_label(value):
        if not value:
            return "—"
        parsed = date.fromisoformat(value)
        return f"{parsed.day:02d}/{parsed.month:02d} ({MONTH_NAMES[parsed.month - 1]})"
    return {
        "schedule": {
            "Inicio del período": annual_label(schedule_start),
            "Fin del período": annual_label(schedule_end),
        },
        "schedule_editable": {"end": schedule_end},
    }


def safe_email(config: dict) -> dict:
    summary = {
        "Envío habilitado": config.get("enabled"),
        "Método de entrega": config.get("delivery_method"),
        "Hora de envío": f"{int(config.get('send_hour')):02d}:{int(config.get('send_minute')):02d}" if isinstance(config.get("send_hour"), int) and isinstance(config.get("send_minute"), int) else "—",
    }
    sender = config.get("sender") or {}
    summary["Remitente"] = sender.get("display_name") or sender.get("email") or "—"
    smtp = config.get("smtp") or {}
    summary["Servidor SMTP"] = f"{smtp.get('host', '—')}:{smtp.get('port', '—')}"
    sites = {}
    for site, value in (config.get("sites") or {}).items():
        value = value or {}

        def addresses(items):
            result = []
            for item in items or []:
                result.append(item if isinstance(item, str) else item.get("email", ""))
            return ", ".join(x for x in result if x) or "—"

        primary = addresses(value.get("to"))
        sites[site] = {"enabled": bool(primary != "—"), "to": primary}
    global_cc = []
    for item in config.get("global_cc") or []:
        global_cc.append(item if isinstance(item, str) else item.get("email", ""))
    return {
        "summary": summary,
        "editable": {
            "enabled": bool(config.get("enabled")),
            "send_hour": config.get("send_hour", 0),
            "send_minute": config.get("send_minute", 0),
        },
        "sites": sites,
        "global_cc": "; ".join(item for item in global_cc if item),
    }


def read_config() -> dict:
    pipeline, pipeline_errors = load_yaml("pipeline.yaml")
    email, email_errors = load_yaml("email.yaml")
    return {
        "config_dir": str(CONFIG_DIR),
        "pipeline": safe_pipeline(pipeline),
        "email": safe_email(email),
        "validation": validate(pipeline, email, pipeline_errors + email_errors),
    }


def _write_yaml(filename: str, value: dict) -> None:
    path = CONFIG_DIR / filename
    if not path.exists():
        raise OSError(f"No existe el archivo configurable {path}")
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, allow_unicode=True, sort_keys=False)


def _valid_recipient(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", value))


def update_editable_config(payload: dict) -> dict:
    pipeline, pipeline_errors = load_yaml("pipeline.yaml")
    email, email_errors = load_yaml("email.yaml")
    if pipeline_errors or email_errors:
        raise ValueError("; ".join(pipeline_errors + email_errors))
    schedule = payload.get("schedule") or {}
    end_date = schedule.get("end")
    if end_date:
        try:
            parsed = date.fromisoformat(end_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("La fecha final no es válida") from exc
        if parsed.day != 2:
            raise ValueError("La fecha final debe ser el día 2 del mes")
        pipeline["schedule_end_month"] = parsed.month
        pipeline["schedule_end_day"] = parsed.day
    email_values = payload.get("email") or {}
    for key in ("enabled", "timezone", "send_hour", "send_minute", "retry_minutes"):
        if key in email_values:
            email[key] = email_values[key]
    for key, maximum in (("send_hour", 23), ("send_minute", 59), ("retry_minutes", 1440)):
        if key in email_values and (not isinstance(email[key], int) or not 0 <= email[key] <= maximum):
            labels = {"send_hour": "hora de envío", "send_minute": "minuto de envío", "retry_minutes": "reintento"}
            raise ValueError(f"{labels[key]} fuera de rango")
    if "timezone" in email_values:
        try:
            ZoneInfo(str(email["timezone"]))
        except Exception as exc:
            raise ValueError("La zona horaria del correo no es válida") from exc
    global_cc_payload = payload.get("global_cc")
    if global_cc_payload is not None:
        addresses = [item.strip() for item in re.split(r"[;,]", str(global_cc_payload)) if item.strip()]
        if any(not _valid_recipient(item) for item in addresses):
            raise ValueError("Hay un CC global inválido")
        email["global_cc"] = [{"email": item} for item in addresses]

    sites_payload = payload.get("sites")
    if sites_payload is not None:
        sites = email.setdefault("sites", {})
        for site, values in sites_payload.items():
            if site not in sites:
                continue
            values = values or {}
            sites[site] = sites.get(site) or {}
            enabled = values.get("enabled", False) is True
            for field in ("to",):
                addresses = [item.strip() for item in re.split(r"[;,]", str(values.get(field, ""))) if item.strip()]
                if enabled and not addresses:
                    raise ValueError(f"{site} está habilitado pero no tiene destinatarios")
                if any(not _valid_recipient(item) for item in addresses):
                    raise ValueError(f"Destinatario inválido en {site}")
                sites[site][field] = [{"email": item} for item in addresses] if enabled else []
            sites[site]["cc"] = []
    candidate_validation = validate(pipeline, email, [])
    if candidate_validation["errors"]:
        raise ValueError("; ".join(candidate_validation["errors"]))
    _write_yaml("pipeline.yaml", pipeline)
    _write_yaml("email.yaml", email)
    return read_config()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def api_config():
    return jsonify(read_config())


@app.post("/api/config")
def api_update_config():
    try:
        return jsonify(update_editable_config(request.get_json(silent=True) or {}))
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/validate")
def api_validate():
    return jsonify(read_config()["validation"])


@app.get("/api/health")
def api_health():
    validation = read_config()["validation"]
    return jsonify({"status": "ok" if not validation["errors"] else "degraded", "error_count": len(validation["errors"])})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8070)


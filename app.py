from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from flask import Flask, current_app, jsonify, render_template, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

import diagnosis
import vehicle_modules


HISTORY_LIMIT = 50
AUDIO_MAX_BYTES = 12 * 1024 * 1024
TELEMETRY_MAX_BYTES = 1024 * 1024


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=Path(app.instance_path) / "history.sqlite3",
        MAX_CONTENT_LENGTH=AUDIO_MAX_BYTES + 256 * 1024,
        MAX_FORM_PARTS=12,
    )
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False

    database = Path(app.config["DATABASE"])
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                vehicle_key TEXT NOT NULL,
                vehicle_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS history_lookup ON history (kind, vehicle_key, id)
        """)

    @app.errorhandler(ValueError)
    def invalid_input(error: ValueError):
        return jsonify(error=str(error)), 400

    @app.errorhandler(BadRequest)
    def malformed_request(_error: BadRequest):
        return jsonify(error="Не удалось прочитать запрос. Проверьте данные и повторите попытку."), 400

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error: RequestEntityTooLarge):
        return jsonify(error="Запрос слишком большой. Допустимо до 12 МБ для WAV и до 1 МБ для CSV."), 413

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/model")
    def model():
        return jsonify(result=diagnosis.model_info())

    @app.get("/api/history")
    def history():
        return jsonify(items=read_history(limit=HISTORY_LIMIT))

    @app.post("/api/diagnose")
    def diagnose():
        data = json_object()
        vehicle = read_vehicle(data)
        symptoms = read_text(data, "symptoms", 2000, "Симптомы")
        additional = read_text(data, "additional", 1200, "Дополнительные симптомы")
        code = read_text(data, "dtc", 20, "Код OBD-II").upper()
        if not (symptoms or additional or code):
            raise ValueError("Опишите симптомы или укажите код OBD-II.")

        dtc_result = vehicle_modules.lookup_dtc(code) if code else None
        result = diagnosis.diagnose("\n".join(filter(None, (symptoms, additional))))
        result = {**result, "dtc": dtc_result}
        if vehicle.get("make", "").casefold() in {"haval", "хавал"}:
            result["vehicle_note"] = "Отдельная оценка модели для автомобилей Haval не проводилась."
        return save_result(
            "diagnosis", vehicle, {"symptoms": symptoms, "additional": additional, "dtc": code}, result
        )

    @app.post("/api/dtc")
    def dtc():
        data = json_object()
        code = read_text(data, "code", 20, "Код OBD-II").upper()
        if not code:
            raise ValueError("Введите код OBD-II, например P0301.")
        return save_result("dtc", read_vehicle(data), {"code": code}, vehicle_modules.lookup_dtc(code))

    @app.post("/api/audio")
    def audio():
        vehicle = read_vehicle(request.form)
        filename, content = read_upload("WAV", AUDIO_MAX_BYTES)
        result = vehicle_modules.analyze_audio(content)
        return save_result("audio", vehicle, {"filename": filename}, result)

    @app.post("/api/fuel")
    def fuel():
        data = json_object()
        vehicle = read_vehicle(data)
        actual = read_number(data, "actual", "Фактический расход", required=True)
        baseline = read_number(data, "baseline", "Обычный расход")
        recent_records = read_history(kind="fuel", vehicle=vehicle, limit=12)
        previous_values = [record["input"]["actual"] for record in reversed(recent_records)]
        result = vehicle_modules.analyze_fuel(actual, baseline=baseline, history=previous_values)
        return save_result("fuel", vehicle, {"actual": actual, "baseline": baseline}, result)

    @app.post("/api/telemetry")
    def telemetry():
        vehicle = read_vehicle(request.form)
        filename, content = read_upload("CSV", TELEMETRY_MAX_BYTES)
        result = vehicle_modules.analyze_telemetry(content)
        return save_result("telemetry", vehicle, {"filename": filename}, result)

    @app.post("/api/prediction")
    def prediction():
        data = json_object() if request.is_json else request.form
        vehicle = read_vehicle(data)
        if request.files.get("file"):
            filename, content = read_upload("CSV", TELEMETRY_MAX_BYTES)
            telemetry_result = vehicle_modules.analyze_telemetry(content)
            source = {"filename": filename}
        else:
            latest = read_history(kind="telemetry", vehicle=vehicle or None, limit=1, include_samples=True)
            if not latest:
                raise ValueError("Загрузите CSV или сначала сохраните запись телеметрии в разделе мониторинга.")
            vehicle = latest[0]["vehicle"]
            telemetry_result = latest[0]["result"]
            source = {"telemetry_id": latest[0]["id"], **latest[0]["input"]}
        result = vehicle_modules.predict_telemetry(telemetry_result["samples"])
        return save_result("prediction", vehicle, source, result)

    @app.post("/api/assistant")
    def assistant():
        data = json_object()
        issue = read_text(data, "issue", 1500, "Вопрос")
        context = read_text(data, "context", 2000, "Контекст")
        if not issue:
            raise ValueError("Введите код OBD-II или вопрос об автомобиле.")
        result = vehicle_modules.explain(issue, context=context)
        return save_result("assistant", read_vehicle(data), {"issue": issue, "context": context}, result)

    return app


def json_object() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Отправьте данные в формате JSON.")
    return data


def read_text(data, key: str, length: int, label: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > length:
        raise ValueError(f"Допустимая длина поля «{label}» — до {length} символов.")
    return value.strip()


def read_number(data: dict, key: str, label: str, *, required: bool = False) -> float | None:
    value = data.get(key)
    if value is None or isinstance(value, str) and not value.strip():
        if required:
            raise ValueError(f"Заполните поле «{label}».")
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    if isinstance(value, bool):
        raise ValueError(f"Введите число в поле «{label}».")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"Введите число в поле «{label}».") from None
    if not math.isfinite(number):
        raise ValueError(f"Введите конечное число в поле «{label}».")
    return number


def read_vehicle(data) -> dict:
    vehicle = {}
    for key, label in (("make", "Марка"), ("model", "Модель"), ("engine", "Двигатель")):
        value = read_text(data, key, 64, label)
        if value:
            vehicle[key] = value

    year = data.get("year")
    if year is None or isinstance(year, str) and not year.strip():
        return vehicle
    if isinstance(year, str) and year.strip().isascii() and year.strip().isdigit() and len(year.strip()) == 4:
        year = int(year.strip())
    last_year = datetime.now().year + 1
    if type(year) is not int or not 1886 <= year <= last_year:
        raise ValueError(f"Введите год выпуска от 1886 до {last_year}.")
    vehicle["year"] = year
    return vehicle


def read_upload(file_type: str, max_bytes: int) -> tuple[str, bytes]:
    upload = request.files.get("file")
    if not upload or not upload.filename:
        raise ValueError(f"Выберите файл {file_type}.")
    filename = upload.filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.casefold().endswith(f".{file_type.casefold()}") or len(filename) > 200:
        raise ValueError(f"Выберите файл с расширением .{file_type.casefold()}.")
    content = upload.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise RequestEntityTooLarge()
    if not content:
        raise ValueError("Выбранный файл пуст.")
    return filename, content


def vehicle_key(vehicle: dict) -> str:
    values = [" ".join(str(vehicle.get(key, "")).casefold().split()) for key in ("make", "model", "year", "engine")]
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def connect_history() -> sqlite3.Connection:
    connection = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def history_view(kind: str, payload: dict) -> dict:
    if kind == "telemetry":
        return {key: value for key, value in payload.items() if key != "samples"}
    return payload


def save_result(kind: str, vehicle: dict, inputs: dict, result: dict):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = [json.dumps(value, ensure_ascii=False, allow_nan=False) for value in (vehicle, inputs, result)]
    with closing(connect_history()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO history (kind, created_at, vehicle_key, vehicle_json, input_json, result_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, timestamp, vehicle_key(vehicle), *records),
        )
        record_id = cursor.lastrowid
    return jsonify(
        result=result,
        record={
            "id": record_id,
            "kind": kind,
            "created_at": timestamp,
            "vehicle": vehicle,
            "input": inputs,
            "result": history_view(kind, result),
        },
    )


def read_history(
    *, kind: str | None = None, vehicle: dict | None = None, limit: int, include_samples: bool = False
) -> list[dict]:
    conditions = []
    values = []
    if kind is not None:
        conditions.append("kind = ?")
        values.append(kind)
    if vehicle is not None:
        conditions.append("vehicle_key = ?")
        values.append(vehicle_key(vehicle))
    query = "SELECT id, kind, created_at, vehicle_json, input_json, result_json FROM history"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    values.append(limit)
    history = []
    with closing(connect_history()) as connection:
        for row in connection.execute(query, values):
            result = json.loads(row["result_json"])
            history.append({
                "id": row["id"],
                "kind": row["kind"],
                "created_at": row["created_at"],
                "vehicle": json.loads(row["vehicle_json"]),
                "input": json.loads(row["input_json"]),
                "result": result if include_samples else history_view(row["kind"], result),
            })
    return history


app = create_app()


if __name__ == "__main__":
    from argparse import ArgumentParser
    from threading import Thread
    import webbrowser

    from werkzeug.serving import make_server

    parser = ArgumentParser(description="AI Car Doctor local server")
    parser.add_argument("--port", type=int, default=5000, help="0 selects an available port")
    parser.add_argument("--open", action="store_true", help="open the default browser")
    args = parser.parse_args()
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"AI Car Doctor: {url}", flush=True)
    if args.open:
        Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()

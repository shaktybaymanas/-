"""Record three standard OBD-II measurements from a local ELM327 adapter."""

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from vehicle_modules import TELEMETRY_FIELDS


def _record(port, output, duration, interval):
    try:
        import obd
    except ImportError as exc:
        raise RuntimeError("Установите библиотеку адаптера командой python -m pip install obd") from exc

    if output.exists():
        raise RuntimeError("Файл уже существует. Укажите новое имя.")
    connection = obd.OBD(portstr=port, fast=False, timeout=1)
    try:
        if not connection.is_connected():
            raise RuntimeError("Нет соединения с автомобилем. Проверьте порт, адаптер и питание OBD-II.")
        commands = (
            (obd.commands.RPM, "rpm"),
            (obd.commands.COOLANT_TEMP, "celsius"),
            (obd.commands.SPEED, "kph"),
        )
        if not all(connection.supports(command) for command, _ in commands):
            raise RuntimeError("Адаптер или автомобиль не сообщил поддержку всех трёх каналов телеметрии.")

        rows = 0
        with output.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(TELEMETRY_FIELDS)
            deadline = time.monotonic() + duration
            try:
                while time.monotonic() < deadline:
                    tick = time.monotonic()
                    replies = [connection.query(command) for command, _ in commands]
                    if all(not reply.is_null() for reply in replies):
                        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                        readings = [round(reply.value.to(unit).magnitude, 3) for reply, (_, unit) in zip(replies, commands)]
                        writer.writerow([stamp, *readings])
                        handle.flush()
                        rows += 1
                    time.sleep(max(0, min(deadline - time.monotonic(), interval + tick - time.monotonic())))
            except KeyboardInterrupt:
                pass
        if not rows:
            raise RuntimeError("Не получено ни одной полной строки. Проверьте показания адаптера.")
        return rows
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="COM-порт или устройство, например COM3")
    parser.add_argument("--output", required=True, type=Path, help="Путь к новому CSV")
    parser.add_argument("--duration", default=60, type=int, help="Длительность записи в секундах")
    parser.add_argument("--interval", default=2, type=float, help="Желаемый интервал в секундах")
    args = parser.parse_args()
    if not 30 <= args.duration <= 3000 or not 1 <= args.interval <= 30:
        parser.error("Укажите длительность 30–3000 c и интервал 1–30 c.")
    try:
        count = _record(args.port, args.output, args.duration, args.interval)
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"Ошибка записи OBD-II. {exc}\n")
    print(f"Число сохранённых замеров — {count}. Файл {args.output}")


if __name__ == "__main__":
    main()

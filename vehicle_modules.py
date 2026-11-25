"""OBD-II reference, numeric analyses, and driver-oriented explanations."""

import csv
import io
import math
import re
import statistics
import wave
from datetime import datetime

import numpy as np


GM_MISFIRE = {
    "label": "General Motors, бюллетень 19-NA-219",
    "url": "https://static.nhtsa.gov/odi/tsbs/2023/MC-10235802-0001.pdf",
}
GM_EVAP = {
    "label": "General Motors, бюллетень 21-NA-124",
    "url": "https://static.nhtsa.gov/odi/tsbs/2021/MC-10198890-9999.pdf",
}
EPA_OBD = {
    "label": "EPA, вопросы и ответы об OBD",
    "url": "https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1009Z15.TXT",
}
FUEL_ECONOMY = {
    "label": "FuelEconomy.gov, факторы расхода топлива",
    "url": "https://www.fueleconomy.gov/feg/factors.shtml",
}
HYUNDAI_WARNINGS = {
    "label": "Hyundai, контрольные лампы",
    "url": "https://ownersmanual.hyundai.com/full_webhelp/LX2/2024/en_US/warning_indicator_lights.html",
}
HYUNDAI_OVERHEAT = {
    "label": "Hyundai, перегрев двигателя",
    "url": "https://ownersmanual.hyundai.com/full_webhelp/LX3/2026/en_US/topic_ibz_ptc_qcc.html",
}
OEM_CODE_CAUTION = (
    "Код описывает наблюдение блока управления. Причину устанавливают по результатам проверок. "
    "Порядок проверок зависит от модели автомобиля и указан в сервисной документации."
)
DTC_PATTERN = re.compile(r"\b[PCBU][0-3][0-9A-F]{3}\b", re.ASCII)
DTC_TRANSLITERATION = str.maketrans("РСВАЕ", "PCBAE")


def _dtc_entry(title, system, summary, checkpoints, source):
    return {
        "title": title,
        "system": system,
        "summary": summary,
        "checkpoints": checkpoints,
        "sources": [source],
    }


_MISFIRE_CHECKS = [
    "Сопутствующие коды и условия, записанные в момент ошибки (freeze frame)",
    "Система зажигания, работа форсунки и компрессия цилиндра по процедуре производителя",
]
_EVAP_CHECKS = [
    "Уплотнение крышки бака, если она предусмотрена конструкцией",
    "Герметичность магистралей и работа клапанов EVAP по процедуре производителя",
]
_DTC = {
    "P0300": _dtc_entry(
        "Случайные или множественные пропуски воспламенения", "Работа двигателя",
        "Блок управления обнаружил пропуски воспламенения без привязки к одному цилиндру.",
        _MISFIRE_CHECKS, GM_MISFIRE,
    ),
    "P0101": _dtc_entry(
        "Показания расходомера воздуха вне ожидаемого диапазона", "Впуск воздуха",
        "Блок управления определил, что показания канала измерения расхода воздуха выходят за ожидаемые пределы.",
        ["Герметичность впуска", "Показания расходомера и состояние его разъёма"],
        {"label": "Volkswagen, памятка 21-20-01TT", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10172567-0001.pdf"},
    ),
    "P0128": _dtc_entry(
        "Двигатель прогревается медленнее, чем ожидает ЭБУ", "Система охлаждения",
        "Температура охлаждающей жидкости при прогреве оказалась ниже расчётного значения.",
        ["Показания датчика температуры при прогреве", "Работа термостата по процедуре производителя"],
        {"label": "FCA, бюллетень 18-036-21", "url": "https://static.nhtsa.gov/odi/tsbs/2021/MC-10194053-9999.pdf"},
    ),
    "P0171": _dtc_entry(
        "Слишком бедная смесь в ряду цилиндров 1", "Топливная смесь",
        "Блок управления определил, что в первом ряду цилиндров требуется слишком большая коррекция подачи топлива.",
        ["Топливные коррекции и сопутствующие коды", "Герметичность впуска и параметры подачи топлива"],
        {"label": "FCA, бюллетень 18-036-21", "url": "https://static.nhtsa.gov/odi/tsbs/2021/MC-10194053-9999.pdf"},
    ),
    "P0299": _dtc_entry(
        "Давление наддува ниже ожидаемого", "Наддув",
        "В режиме, где двигатель запрашивал наддув, фактическое давление оказалось ниже расчётного.",
        ["Заданное и фактическое давление", "Герметичность впуска и управление наддувом"],
        {"label": "General Motors, бюллетень PI1366", "url": "https://static.nhtsa.gov/odi/tsbs/2014/SB-10056605-3612.pdf"},
    ),
    "P0420": _dtc_entry(
        "Эффективность катализатора ниже порога в ряду 1", "Выпуск и очистка выхлопа",
        "По данным контроля выхлопа блок управления определил, что эффективность катализатора первого ряда ниже порога.",
        ["Сопутствующие коды и показания датчиков кислорода", "Герметичность выпуска и состояние катализатора"],
        {"label": "Hyundai, бюллетень 20-FL-010H", "url": "https://static.nhtsa.gov/odi/tsbs/2020/MC-10182322-0001.pdf"},
    ),
    "P0442": _dtc_entry(
        "Обнаружена небольшая утечка в системе EVAP", "Улавливание паров топлива",
        "Встроенная проверка выявила небольшое нарушение герметичности контура паров топлива.",
        _EVAP_CHECKS, GM_EVAP,
    ),
    "P0455": _dtc_entry(
        "Обнаружена крупная утечка в системе EVAP", "Улавливание паров топлива",
        "Встроенная проверка системы улавливания паров топлива сообщила о значительной утечке.",
        _EVAP_CHECKS, GM_EVAP,
    ),
    "P0562": _dtc_entry(
        "Низкое напряжение бортовой сети", "Электропитание",
        "Блок управления зафиксировал напряжение питания ниже допустимого для контролируемого режима.",
        ["Данные о напряжении при появлении ошибки", "Аккумулятор, клеммы и система зарядки"],
        {"label": "Volkswagen, справочник Passat", "url": "https://static.nhtsa.gov/odi/tsbs/2014/MC-10074004-2280.pdf"},
    ),
}
for cylinder in range(1, 9):
    _DTC[f"P030{cylinder}"] = _dtc_entry(
        f"Пропуски воспламенения в цилиндре {cylinder}", "Работа двигателя",
        f"Блок управления обнаружил сбои сгорания смеси в цилиндре {cylinder}.",
        _MISFIRE_CHECKS, GM_MISFIRE,
    )


def lookup_dtc(code):
    """Look up one standardized code, preserving unknown codes for the user's notes."""
    normalized = str(code).strip().upper().translate(DTC_TRANSLITERATION)
    if not DTC_PATTERN.fullmatch(normalized):
        raise ValueError("Введите один пятизначный код OBD-II, например P0301 или P0420.")
    entry = _DTC.get(normalized)
    if entry is None:
        return {
            "code": normalized, "found": False, "system": "OBD-II",
            "title": "Код отсутствует в справочнике",
            "summary": "Код имеет формат OBD-II. Расшифровка может зависеть от производителя и блока управления.",
            "recommendation": "Сверьте код, модель и двигатель с документацией производителя автомобиля.",
            "checkpoints": [], "sources": [],
        }
    recommendation = OEM_CODE_CAUTION
    sources = entry["sources"][:]
    if normalized.startswith("P030"):
        recommendation += " Если Check Engine мигает, снизьте нагрузку и как можно скорее обратитесь в сервис."
        sources.append(EPA_OBD)
    return {
        **entry, "code": normalized, "found": True, "recommendation": recommendation,
        "sources": sources, "checkpoints": entry["checkpoints"][:],
    }


def _pcm_samples(payload, width):
    if width == 1:
        return np.frombuffer(payload, dtype="u1").astype(np.float32) - 128
    if width == 3:
        octets = np.frombuffer(payload, dtype="u1").reshape(-1, 3).astype(np.int32)
        values = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        return ((values ^ 0x800000) - 0x800000).astype(np.float32)
    return np.frombuffer(payload, dtype=f"<i{width}").astype(np.float32)


def analyze_audio(file_bytes):
    """Measure properties of an uncompressed WAV recording locally."""
    if not isinstance(file_bytes, (bytes, bytearray)) or len(file_bytes) > 12 * 1024 * 1024:
        raise ValueError("Загрузите WAV-файл размером до 12 МБ.")
    try:
        with wave.open(io.BytesIO(file_bytes), "rb") as recorded:
            channels, width, rate, frames = recorded.getparams()[:4]
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 192000:
                raise ValueError("Нужен WAV PCM с 1–2 каналами и частотой 8–192 кГц.")
            if not 0.5 <= frames / rate <= 30:
                raise ValueError("Длительность записи должна быть от 0,5 до 30 секунд.")
            payload = recorded.readframes(frames)
    except (EOFError, wave.Error, OverflowError) as exc:
        raise ValueError("Файл не удалось прочитать. Используйте WAV PCM без сжатия.") from exc
    if len(payload) != frames * width * channels:
        raise ValueError("Запись WAV обрезана. Экспортируйте файл заново.")

    samples = _pcm_samples(payload, width).reshape(-1, channels)
    samples /= 2 ** (8 * width - 1)
    power_by_channel = np.mean(samples**2, axis=0, dtype=np.float64)
    channel = int(np.argmax(power_by_channel))
    signal = samples[:, channel]
    rms = math.sqrt(float(power_by_channel[channel]))
    peak = float(np.max(np.abs(signal)))
    clipping = float(np.mean(np.abs(signal) >= 0.999)) * 100
    waveform = [round(float(np.max(np.abs(bucket))), 4) for bucket in np.array_split(signal, 64)]
    dominant_frequency = _dominant_frequency(signal, rate)

    if rms < 0.001:
        title = "Очень тихая аудиозапись"
        advice = "Для сравнения запишите звук с того же расстояния в более тихом месте."
    elif clipping >= 0.5:
        title = "В записи есть перегруженные участки"
        advice = "Перезапишите звук с чуть большего расстояния, чтобы избежать перегрузки микрофона."
    else:
        title = "Характеристики записи рассчитаны"
        advice = "Сравнивайте записи, сделанные с одинакового расстояния и при одинаковых оборотах."
    return {
        "title": title,
        "summary": "Уровень сигнала и частотный пик относятся к выбранной записи. Для диагностики по звуку нужна модель на размеченных записях.",
        "recommendation": advice,
        "duration_seconds": round(frames / rate, 2), "sample_rate_hz": rate,
        "channels": channels, "rms_dbfs": round(20 * math.log10(rms), 1) if rms else None,
        "peak_dbfs": round(20 * math.log10(peak), 1) if peak else None,
        "dominant_frequency_hz": dominant_frequency, "clipped_pct": round(clipping, 2),
        "waveform": waveform,
    }


def _dominant_frequency(signal, rate):
    length = min(len(signal), rate)
    step = length // 2
    window = np.hanning(length)
    power = np.zeros(length // 2 + 1)
    for start in range(0, len(signal) - length + 1, step):
        segment = signal[start:start + length]
        power += np.abs(np.fft.rfft((segment - np.mean(segment)) * window)) ** 2
    frequencies = np.fft.rfftfreq(length, 1 / rate)
    power[(frequencies < 15) | (frequencies > 8000)] = 0
    total = float(np.sum(power))
    peak = int(np.argmax(power))
    return round(float(frequencies[peak]), 1) if total and power[peak] / total >= 0.015 else None


def _number(value, label, minimum, maximum):
    try:
        number = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} — введите число от {minimum} до {maximum}.") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} — введите число от {minimum} до {maximum}.")
    return number


def analyze_fuel(actual, baseline=None, history=()):
    """Compare l/100 km against a user baseline or the previous eight comparable trips."""
    value = _number(actual, "Фактический расход", 0.1, 100)
    recent = [_number(item, "Расход в истории", 0.1, 100) for item in list(history or ())[-8:]]
    reference = None
    source = None
    if baseline is not None and str(baseline).strip():
        reference = _number(baseline, "Базовый расход", 0.1, 100)
        source = "manual"
    elif len(recent) >= 3:
        reference = statistics.median(recent)
        source = "history"

    delta = round(value - reference, 2) if reference is not None else None
    delta_pct = round((value / reference - 1) * 100, 1) if reference is not None else None
    if delta_pct is None:
        status, title = "insufficient", "Нужна база для сравнения"
        summary = "Укажите обычный расход или добавьте три предыдущих замера в сопоставимых условиях."
    else:
        if delta_pct >= 15:
            status, title = "above", "Расход заметно выше базового"
        elif delta_pct <= -15:
            status, title = "below", "Расход заметно ниже базового"
        else:
            status, title = "near", "Расход близок к базовому"
        method = "введённым значением" if source == "manual" else "медианой предыдущих замеров"
        summary = f"Отклонение от базового расхода {delta_pct:+.1f} % по сравнению с {method}. Порог заметного отклонения в прототипе — 15 %."
    return {
        "actual": value, "baseline": reference, "baseline_source": source, "delta": delta,
        "delta_pct": delta_pct, "history": [*recent, value], "status": status, "title": title,
        "summary": summary,
        "recommendation": "Сравнивайте поездки с похожим маршрутом, погодой и загрузкой. Если рост повторяется, покажите журнал замеров в сервисе.",
        "sources": [FUEL_ECONOMY],
    }


TELEMETRY_FIELDS = ("timestamp", "rpm", "coolant_c", "speed_kmh")
_TELEMETRY_RANGES = {"rpm": (0, 16384), "coolant_c": (-40, 215), "speed_kmh": (0, 255)}


def _read_timestamp(value):
    try:
        value = (value or "").strip()
        if len(value) < 16 or value[10] not in {"T", " "}:
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Укажите дату и время ISO 8601, например 2026-01-01T10:00:00.") from exc


def analyze_telemetry(csv_text_or_bytes):
    """Read ISO-timestamped CSV with RPM, coolant temperature, and speed."""
    if isinstance(csv_text_or_bytes, bytes):
        try:
            csv_text_or_bytes = csv_text_or_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Сохраните таблицу в формате CSV UTF-8.") from exc
    if not isinstance(csv_text_or_bytes, str) or not csv_text_or_bytes.strip():
        raise ValueError("Загрузите непустой файл телеметрии CSV.")
    if len(csv_text_or_bytes) > 512 * 1024:
        raise ValueError("Файл телеметрии должен быть размером до 512 КБ.")
    source = csv_text_or_bytes.lstrip("\ufeff\n\r ")
    separator = ";" if ";" in source.splitlines()[0] else ","
    data = csv.DictReader(io.StringIO(source), delimiter=separator, strict=True)
    samples = []
    stamps = []
    try:
        data.fieldnames = [name.strip().casefold() for name in data.fieldnames or ()]
        if len(data.fieldnames) != len(set(data.fieldnames)) or not set(TELEMETRY_FIELDS) <= set(data.fieldnames):
            raise ValueError("В CSV нужны уникальные столбцы timestamp, rpm, coolant_c и speed_kmh.")
        for line_number, row in enumerate(data, start=2):
            if len(samples) >= 3000:
                raise ValueError("Загрузите CSV с максимум 3000 замерами.")
            try:
                if None in row:
                    raise ValueError("Число значений превышает число столбцов.")
                stamp = _read_timestamp(row["timestamp"])
                if stamps and stamp <= stamps[-1]:
                    raise ValueError("Время должно строго возрастать.")
                point = {
                    key: _number(row[key], key, *bounds)
                    for key, bounds in _TELEMETRY_RANGES.items()
                }
            except TypeError as exc:
                raise ValueError(f"Строка {line_number}. Укажите часовой пояс во всех строках или оставьте его пустым во всех строках.") from exc
            except ValueError as exc:
                raise ValueError(f"Строка {line_number}. {exc}") from exc
            stamps.append(stamp)
            samples.append({"timestamp": stamp.isoformat(), **point})
    except csv.Error as exc:
        raise ValueError("Не удалось прочитать таблицу CSV. Проверьте формат полей.") from exc
    if not samples:
        raise ValueError("В CSV нет строк с замерами.")
    return {
        "title": "Журнал OBD-II обработан",
        "summary": "В журнале доступны последний замер и графики за всю поездку.",
        "recommendation": "Сверяйте показания в сопоставимых условиях и учитывайте предупреждения на приборной панели.",
        "sample_count": len(samples), "duration_seconds": round((stamps[-1] - stamps[0]).total_seconds(), 2),
        "samples": samples, "latest": samples[-1], "prediction": predict_telemetry(samples),
    }


def predict_telemetry(samples):
    """Extrapolate a recent temperature trend when the measurement series supports it."""
    current = samples[-1]["coolant_c"] if samples else None
    result = {
        "status": "insufficient", "title": "Мало данных для прогноза температуры",
        "summary": "Нужно не менее пяти замеров за 30–120 секунд непрерывной работы двигателя.",
        "recommendation": "Запишите более длинный участок поездки с равномерным шагом замеров.",
        "slope_c_per_min": None, "current_c": current, "projected_c": None,
        "horizon_seconds": None, "r_squared": None, "sample_count": 0,
    }
    if not samples:
        return result

    end = _read_timestamp(samples[-1]["timestamp"])
    recent = []
    for point in reversed(samples):
        elapsed = (_read_timestamp(point["timestamp"]) - end).total_seconds()
        if elapsed < -120 or point["rpm"] <= 0:
            break
        recent.append((elapsed, point["coolant_c"]))
    result["sample_count"] = len(recent)
    if len(recent) < 5 or recent[-1][0] > -30:
        return result

    seconds, temperature = np.array(recent[::-1], dtype=float).T
    duration = -seconds[0]
    if np.max(np.diff(seconds)) > duration / 3:
        result["summary"] = "В журнале есть слишком длинные интервалы между соседними замерами."
        return result

    slope, intercept = np.polyfit(seconds, temperature, 1)
    fitted = intercept + slope * seconds
    total_variation = float(np.sum((temperature - np.mean(temperature)) ** 2))
    r_squared = 1 - float(np.sum((temperature - fitted) ** 2)) / total_variation if total_variation > 1e-10 else 1.0
    per_minute = float(slope * 60)
    result.update(slope_c_per_min=round(per_minute, 2), r_squared=round(r_squared, 3))
    if r_squared < 0.55 and np.ptp(temperature) > 1.5:
        result.update(
            status="variable", title="Температура меняется неравномерно",
            summary="Линия тренда слабо описывает последние измерения. Продолжать её за пределы журнала ненадёжно.",
        )
        return result

    horizon = min(30, int(duration / 2))
    if per_minute > 0.25:
        status, title = "rising", "Температура растёт"
    elif per_minute < -0.25:
        status, title = "falling", "Температура снижается"
    else:
        status, title = "flat", "Температура почти стабильна"
    projected = float(intercept + slope * horizon)
    if not _TELEMETRY_RANGES["coolant_c"][0] <= projected <= _TELEMETRY_RANGES["coolant_c"][1]:
        result.update(status="variable", title="Температура меняется слишком быстро", summary="Продолжение линии тренда выходит за диапазон шкалы OBD-II.")
        return result
    result.update(
        status=status, title=title, projected_c=round(projected, 1), horizon_seconds=horizon,
        summary=f"Скорость изменения {per_minute:+.2f} °C в минуту. Линия тренда даёт оценку {projected:.1f} °C через {horizon} с при сохранении текущих условий.",
        recommendation="Учитывайте стадию прогрева и режим движения. Для прогноза отказов нужны размеченные данные о поломках.",
    )
    return result


def explain(issue, context=""):
    """Explain a common symptom or DTC with a local reference response."""
    normalized = str(issue or "").strip()
    if len(normalized) < 3:
        raise ValueError("Опишите вопрос или введите код OBD-II, например P0301.")
    question = normalized.casefold().replace("ё", "е")
    if "давлен" in question and ("масл" in question or "oil" in question):
        return {
            "title": "Предупреждение о низком давлении масла",
            "summary": "При горящем индикаторе давления масла и работающем двигателе есть риск повреждения двигателя.",
            "recommendation": "Безопасно остановитесь и заглушите двигатель. Дальнейшие действия проверьте по руководству автомобиля или уточните в службе помощи на дороге.",
            "sources": [HYUNDAI_WARNINGS],
        }
    if "перегрев" in question or "overheat" in question:
        return {
            "title": "Предупреждение о перегреве",
            "summary": "Если указатель ушёл в красную зону или появилось сообщение о перегреве, двигателю нужна немедленная проверка.",
            "recommendation": "Безопасно остановитесь. При выходе пара или утечке охлаждающей жидкости заглушите двигатель. Горячая система охлаждения находится под давлением. Следуйте руководству своего автомобиля.",
            "sources": [HYUNDAI_OVERHEAT],
        }
    if ("мига" in question or "flash" in question) and ("чек" in question or "check engine" in question):
        return {
            "title": "Мигает Check Engine",
            "summary": "Мигание может указывать на серьёзные пропуски воспламенения, опасные для катализатора.",
            "recommendation": "Снизьте нагрузку и как можно скорее обратитесь в сервис. Сверьтесь с руководством автомобиля.",
            "sources": [EPA_OBD],
        }

    code = DTC_PATTERN.search(normalized.upper().translate(DTC_TRANSLITERATION))
    if code:
        return lookup_dtc(code.group())
    if "расход" in question or "fuel economy" in question:
        return {
            "title": "Почему изменился расход топлива",
            "summary": "На расход влияют короткие поездки, температура воздуха, пробки, скорость и нагрузка. Сравнение в одинаковых условиях помогает понять, повторяется ли отклонение.",
            "recommendation": "Сравните несколько поездок по одному маршруту в разделе «Расход топлива». Если повышение повторяется, передайте замеры специалисту.",
            "sources": [FUEL_ECONOMY],
        }
    if any(word in question for word in ("стук", "звук", "треск", "шум", "knock", "rattle")):
        return {
            "title": "Как описать звук двигателя",
            "summary": "Для проверки важны место и время появления звука, температура двигателя, связь с оборотами и длительность.",
            "recommendation": "При отсутствии предупреждений и опасных симптомов приложите короткую запись. При сильном стуке или предупреждении на панели безопасно остановитесь и обратитесь за помощью.",
            "sources": [HYUNDAI_OVERHEAT],
        }
    if "obd" in question or "обд" in question or "чек" in question or "check engine" in question:
        return {
            "title": "Что означает Check Engine",
            "summary": "Блок управления включает индикатор, когда встроенная проверка обнаруживает проблему. Сканер помогает прочитать сохранённый код и условия его появления.",
            "recommendation": "Введите считанный код в справочник. Если лампа мигает, снизьте нагрузку и как можно скорее обратитесь в сервис.",
            "sources": [EPA_OBD],
        }
    context_codes = set(DTC_PATTERN.findall(str(context or "").upper().translate(DTC_TRANSLITERATION)))
    if len(context_codes) == 1:
        code_from_context = context_codes.pop()
        explanation = lookup_dtc(code_from_context)
        explanation["summary"] = f"В описании указан код {code_from_context}. " + explanation["summary"]
        return explanation
    return {
        "title": "Что уточнить перед проверкой",
        "summary": "Можно объяснить код OBD-II, предупреждение на панели, изменение расхода или звук двигателя.",
        "recommendation": "Укажите код либо напишите, когда появляется симптом, какие индикаторы горят и меняется ли поведение автомобиля.",
        "sources": [],
    }

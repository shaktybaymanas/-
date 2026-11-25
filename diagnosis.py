"""Classify a symptom description by component category using a portable text model."""

import gzip
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path


DATA_DIRECTORY = Path(__file__).resolve().parent / "data"
SOURCE_NAME = "NHTSA ODI Consumer Complaints"
SOURCE_URL = "https://www.nhtsa.gov/nhtsa-datasets-and-apis#complaints"
CLASSES = {
    "engine": {
        "label": "Двигатель и охлаждение",
        "description": "В похожих жалобах указывали двигатель или систему его охлаждения.",
        "checks": [
            "Уточните, когда появляется шум или неровная работа: после запуска, на холостом ходу или при разгоне.",
            "Попросите в сервисе считать коды ошибок и проверить двигатель по описанным условиям.",
        ],
    },
    "powertrain": {
        "label": "Трансмиссия",
        "description": "В похожих жалобах указывали коробку передач или элементы привода.",
        "checks": ["Запишите, на какой передаче и при какой скорости возникает симптом.",
                   "Передайте условия проявления симптома и считанные коды сервису."],
    },
    "fuel": {
        "label": "Топливная система",
        "description": "В похожих жалобах указывали подачу топлива или связанные компоненты.",
        "checks": ["Сравните расход на сопоставимом маршруте и запишите обстоятельства последней заправки.",
                   "Передайте сведения сервису для проверки топливной системы."],
    },
    "electrical": {
        "label": "Электрооборудование",
        "description": "В похожих жалобах указывали питание автомобиля или другие электрические компоненты.",
        "checks": ["Запишите, какие приборы отключаются и какие сообщения появляются на панели.",
                   "Попросите проверить аккумулятор, зарядку и питание затронутых устройств."],
    },
    "brakes": {
        "label": "Тормозная система",
        "description": "В похожих жалобах указывали тормоза или связанные с ними компоненты.",
        "checks": ["Запишите индикаторы панели и условия, при которых изменилось торможение.",
                   "Передайте описание специалисту для проверки тормозной системы."],
    },
    "steering": {
        "label": "Рулевое управление",
        "description": "В похожих жалобах указывали рулевое управление или его усилитель.",
        "checks": ["Запишите, возникает ли симптом при повороте руля или движении прямо.",
                   "Запланируйте проверку рулевого управления с учётом условий проявления."],
    },
    "suspension": {
        "label": "Подвеска и колёса",
        "description": "В похожих жалобах указывали подвеску, колёса или шины.",
        "checks": ["Запишите сторону, скорость и тип покрытия, на которых замечаете симптом.",
                   "Попросите в сервисе проверить подвеску и колёса в указанной зоне."],
    },
}


# Phrases are lexical translations used as features, never a mapping to classes.
RUSSIAN_PHRASES = tuple(
    (re.compile(pattern), translation)
    for pattern, translation in (
        (r"\b(?:расход\w*\s+(?:топлив|бензин)\w*|(?:топлив|бензин)\w*\s+(?:уходит|расходуется)\s+больше|жрет\s+бензин)", "fuel consumption"),
        (r"\b(?:не\s+завод\w+|не\s+запуска\w+|не\s+запуст\w+)", "will not start"),
        (r"\b(?:долго\s+завод\w+|тяжело\s+завод\w+|плохо\s+завод\w+)", "hard to start cranking"),
        (r"\b(?:при\s+холодном\s+запуск\w*|на\s+холодн\w+)", "cold start"),
        (r"\bпри\s+(?:запуск|заводк)\w*\s+(?:двигател|мотор)\w*", "engine start"),
        (r"\b(?:при\s+запуск\w*|при\s+завод\w+)", "when starting"),
        (r"\b(?:чек\s+энджин|чек\s+двигателя|горит\s+чек|замигал\s+чек|мигает\s+чек)\b", "check engine light"),
        (r"\b(?:педал\w+\s+тормоз\w*|тормозн\w+\s+педал\w*)", "brake pedal"),
        (r"\b(?:педал\w+\s+газ\w*|нажима\w*\s+(?:на\s+)?газ\b)", "accelerator pedal"),
        (r"\b(?:туг\w+\s+рул\w*|рул\w*\s+туг\w+|(?:туго|тяжело)\s+крут\w+\s+рул\w*|рул\w+\s+тяжело\s+крут\w+)", "steering wheel hard to turn"),
        (r"\b(?:теря\w+\s+мощност\w*|потер\w+\s+мощност\w*|не\s+тянет)\b", "loss of power"),
        (r"\b(?:на\s+холост\w*\s+ход\w*|холост\w+\s+оборот\w*)", "at idle engine rpm"),
        (r"\bплава\w*\s+оборот\w*", "rough idle unstable rpm"),
        (r"\b(?:быстро\s+разряжа\w+|сел\s+аккумулятор|аккумулятор\s+садится)\b", "battery draining"),
        (r"\b(?:при\s+переключ\w+|переключ\w+\s+передач\w*)", "when shifting gears"),
        (r"\b(?:запах\w*\s+(?:бензин|топлив)\w*|пахнет\s+(?:бензин|топлив)\w*)", "fuel smell gasoline odor"),
        (r"\b(?:двигател\w*|мотор\w*|движок\w*)", "engine"),
        (r"\b(?:стук\w*|стуч\w*|застуч\w*|цок\w*)", "knocking noise"),
        (r"\b(?:треск\w*|скрежет\w*|хруст\w*)", "grinding rattling noise"),
        (r"\b(?:скрип\w*|свист\w*|писк\w*)", "squealing noise"),
        (r"\b(?:гуд\w*|гул\w*|шум\w*)", "humming noise"),
        (r"\b(?:увелич\w*|вырос\w*|растет)\b", "increased"),
        (r"\b(?:глох\w*|глохнет|заглох\w*)", "stalled"),
        (r"\b(?:перегрев\w*|закипа\w*|закип\w*)", "engine overheating"),
        (r"\b(?:антифриз\w*|охлаждающ\w+\s+жидкост\w*|тосол\w*)", "coolant"),
        (r"\b(?:масл\w+|маслян\w*)", "oil"),
        (r"\b(?:дым\w*|задым\w*)", "smoke"),
        (r"\b(?:пропуск\w+\s+зажиган\w*|троит|троени\w*)", "engine misfire"),
        (r"\b(?:свеч\w+|катуш\w+\s+зажиган\w*|зажиган\w*)", "spark plug ignition"),
        (r"\b(?:при\s+разгон\w*|ускоря\w*|ускорени\w*)", "when accelerating"),
        (r"\b(?:вибрац\w*|вибрир\w*|тряс\w*|трясет|трясёт)", "shaking vibration"),
        (r"\b(?:дерга\w*|рывк\w*|рывок|пина\w*)", "jerking"),
        (r"\b(?:кпп|акпп|мкпп|коробк\w*|вариатор\w*|трансмисси\w*)", "transmission"),
        (r"\b(?:сцеплен\w*|муфт\w+)", "clutch"),
        (r"\b(?:передач\w+|переключа\w+)", "gear shift"),
        (r"\bтормо[зж]\w*\b", "brakes braking"),
        (r"\bабс\b", "abs"),
        (r"\b(?:рул\w*|гур|эур)\b", "steering wheel"),
        (r"\b(?:амортизатор\w*|подвеск\w*|стойк\w*)", "suspension strut shock absorber"),
        (r"\b(?:колес\w*|шин\w+|покрышк\w*)", "wheel tire"),
        (r"\b(?:ям\w+|кочк\w+|неровност\w+)", "bumps rough road"),
        (r"\b(?:топлив\w+|бензин\w*)", "fuel gasoline"),
        (r"\b(?:аккумулятор\w*|акб)\b", "battery"),
        (r"\b(?:генератор\w*|зарядк\w*)", "alternator charging"),
        (r"\b(?:стартер\w*)", "starter"),
        (r"\b(?:прибор\w*|панел\w*|индикатор\w*)", "dashboard warning light"),
        (r"\b(?:фары|фар\w*|свет\w*|электрик\w*)", "lights electrical"),
    )
)

CONTACT_TEMPLATE = re.compile(r"\b(?:the contact (?:stated|reported|indicated|mentioned) that|the contact owns)\b")
PERSONAL_FIELDS = re.compile(
    r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b|\b[\w]{17}\b|\b\d{3}[- .]\d{3}[- .]\d{4}\b",
    flags=re.IGNORECASE,
)
WORDS = re.compile(r"(?u)\b[a-z][a-z0-9]{1,19}\b")
CYRILLIC = re.compile(r"[а-яё]", flags=re.IGNORECASE)
GENERAL_WORDS = {"auto", "broken", "car", "doing", "happened", "information", "issue", "know", "more",
                 "no", "not", "problem", "something", "thing", "trouble", "unknown", "vehicle", "working"}


def clean_english(text):
    text = PERSONAL_FIELDS.sub(" ", text.lower())
    return CONTACT_TEMPLATE.sub(" ", text)


def translate_features(text):
    original = text.lower()
    text = original.replace("ё", "е")
    english = []
    matches = []
    for pattern, translation in RUSSIAN_PHRASES:
        while (match := pattern.search(text)) is not None:
            matches.append((match.start(), original[match.start():match.end()]))
            english.append((match.start(), translation))
            text = text[:match.start()] + " " * (match.end() - match.start()) + text[match.end():]
    if not matches:
        return "", []
    translated = " ".join(fragment for _, fragment in sorted(english))
    english_words = " ".join(WORDS.findall(text))
    return f"{translated} {english_words}", list(dict.fromkeys(fragment for _, fragment in sorted(matches)))


@lru_cache(maxsize=1)
def load_model():
    try:
        with gzip.open(DATA_DIRECTORY / "symptom_model.json.gz", "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def model_info():
    try:
        with (DATA_DIRECTORY / "model_metrics.json").open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "name": "TF-IDF + Logistic Regression",
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "classes": [],
            "train_size": 0,
            "test_size": 0,
            "accuracy": None,
            "macro_f1": None,
        }


def _scores(model, words):
    vocabulary = model["vocabulary"]
    both_orders = [*words, *(f"{a} {b}" for a, b in zip(words, words[1:]))]
    counts = Counter(vocabulary[term] for term in both_orders if term in vocabulary)
    weighted = {
        index: (1.0 + math.log(count)) * model["idf"][index]
        for index, count in counts.items()
    }
    length = math.sqrt(sum(value ** 2 for value in weighted.values())) or 1.0
    raw = [
        bias + sum(weights[index] * value / length for index, value in weighted.items())
        for bias, weights in zip(model["intercepts"], model["coefficients"])
    ]
    highest = max(raw)
    exp_values = [math.exp(score - highest) for score in raw]
    denominator = sum(exp_values)
    return [score / denominator for score in exp_values]


def diagnose(text):
    language = "ru" if CYRILLIC.search(text) else "en"
    matched = []
    if language == "ru":
        text, matched = translate_features(text)

    result = {"status": "insufficient", "candidates": [], "input_language": language,
              "matched_terms": matched,
              "note": "Опишите, что именно происходит и при каких условиях. Можно использовать английский текст."}
    model = load_model()
    if model is None:
        return {**result, "status": "unavailable", "note": "Файл обученной модели отсутствует."}

    stop_words = set(model["stop_words"])
    words = [word for word in WORDS.findall(clean_english(text)) if word not in stop_words]
    known = {word for word in words if word in model["vocabulary"] and word not in GENERAL_WORDS}
    if len(known) < 2:
        return result
    scores = _scores(model, words)
    ranking = sorted(zip(model["classes"], scores), key=lambda pair: pair[1], reverse=True)
    if not ranking or ranking[0][1] < 0.28:
        return {**result, "note": "Описание подходит сразу нескольким категориям. Добавьте наблюдаемые признаки: звук, индикатор или условия появления."}

    candidates = [
        {"id": category, "score": round(score, 4), **CLASSES[category]}
        for category, score in ranking[:3]
    ]
    note = "Баллы отражают близость к категориям жалоб NHTSA. Фактическую причину подтверждает диагностика автомобиля."
    if language == "ru":
        note += " Русские фразы обработаны ограниченным словарём. Качество измерено на английских жалобах."
    return {**result, "status": "ok", "candidates": candidates, "note": note}

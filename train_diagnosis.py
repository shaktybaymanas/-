"""Train and evaluate the symptom model from the official NHTSA complaint archive."""

import argparse
import gzip
import hashlib
import json
import re
import shutil
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from threadpoolctl import threadpool_limits

from diagnosis import CLASSES, DATA_DIRECTORY, SOURCE_NAME, SOURCE_URL, WORDS, _scores, clean_english


ARCHIVE_URL = "https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip"
DICTIONARY_URL = "https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt"
SEED = 42
SPLIT_LIMITS = {"train": 2800, "validation": 700, "test": 900}
COMPONENTS = {
    "ENGINE": "engine",
    "ENGINE AND ENGINE COOLING": "engine",
    "POWER TRAIN": "powertrain",
    "FUEL/PROPULSION SYSTEM": "fuel",
    "FUEL SYSTEM, GASOLINE": "fuel",
    "FUEL SYSTEM, DIESEL": "fuel",
    "ELECTRICAL SYSTEM": "electrical",
    "SERVICE BRAKES": "brakes",
    "SERVICE BRAKES, HYDRAULIC": "brakes",
    "SERVICE BRAKES, AIR": "brakes",
    "PARKING BRAKE": "brakes",
    "STEERING": "steering",
    "SUSPENSION": "suspension",
    "WHEELS": "suspension",
    "TIRES": "suspension",
}
OWNERS = {"EVOQ", "IVOQ", "MAVQ", "MIVQ", "MVOQ", "SVOQ", "VOQ", "LETR"}
STOP_WORDS = sorted((ENGLISH_STOP_WORDS | {"contact", "vehicle", "dealer", "manufacturer"}) - {"no", "not", "off"})


def hash_value(value):
    return hashlib.sha256(f"{SEED}|{value}".encode()).hexdigest()


def normalize_group(make, model):
    return " ".join(WORDS.findall(f"{make} {model}".lower()))


def complaint_rows(archive_path):
    with ZipFile(archive_path) as archive:
        member, = (entry for entry in archive.namelist() if entry.lower().endswith(".txt"))
        with archive.open(member) as file:
            for line in file:
                fields = line.decode("cp1252", errors="replace").rstrip("\r\n").split("\t")
                if len(fields) <= 45 or fields[45] != "V" or fields[20] not in OWNERS:
                    continue
                odi, make, model, component, description = (fields[i].strip() for i in (1, 3, 4, 11, 19))
                if odi.isdecimal() and make and model and description:
                    yield odi, make, model, COMPONENTS.get(component.split(":", maxsplit=1)[0]), description


def collect_examples(archive_path):
    reports = {}
    excluded = set()
    for odi, make, model, category, description in complaint_rows(archive_path):
        if not category:
            excluded.add(odi)
            continue
        group = normalize_group(make, model)
        original = clean_english(description)
        # Remove the vehicle name where it is explicitly spelled out in narratives.
        text = re.sub(r"\b" + re.escape(f"{make} {model}".lower()) + r"\b", " ", original)
        words = WORDS.findall(text)
        if len(words) < 8:
            excluded.add(odi)
            continue
        record = category, group, " ".join(words)
        if reports.setdefault(odi, record) != record:
            excluded.add(odi)

    seen_texts = {}
    conflicting = set()
    for odi, sample in sorted(reports.items()):
        if odi in excluded:
            continue
        category, group, text = sample
        first_odi, first_category, _ = seen_texts.setdefault(text, (odi, category, group))
        if first_odi != odi and first_category != category:
            conflicting.add(text)
    samples = defaultdict(list)
    for text, (odi, category, group) in seen_texts.items():
        if text in conflicting:
            continue
        group_fold = int(hash_value(group)[:8], 16) % 100
        split = "train" if group_fold < 68 else "validation" if group_fold < 84 else "test"
        samples[split, category].append((odi, category, group, text))

    selected = {}
    for split, limit in SPLIT_LIMITS.items():
        selected[split] = [
            example for category in CLASSES
            for example in sorted(samples[split, category], key=lambda item: hash_value(item[0]))[:limit]
        ]
    group_sets = [{row[2] for row in rows} for rows in selected.values()]
    assert sum(map(len, group_sets)) == len(set.union(*group_sets)), "Vehicle group overlap"
    return selected


def rounded(values):
    return np.round(values, decimals=8).tolist()


def write_model(vectorizer, learner, reference_rows, expected):
    model = {
        "version": 1,
        "classes": learner.classes_.tolist(),
        "stop_words": STOP_WORDS,
        "vocabulary": {term: int(index) for term, index in vectorizer.vocabulary_.items()},
        "idf": rounded(vectorizer.idf_),
        "coefficients": rounded(learner.coef_),
        "intercepts": rounded(learner.intercept_),
    }
    stop_words = set(STOP_WORDS)
    portable_scores = [_scores(model, [word for word in WORDS.findall(text) if word not in stop_words])
                       for text in reference_rows]
    np.testing.assert_allclose(portable_scores, expected, atol=1e-6, rtol=1e-6)
    encoded = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode()
    (DATA_DIRECTORY / "symptom_model.json.gz").write_bytes(gzip.compress(encoded, mtime=0))


def train(archive_path, skip_forest):
    with archive_path.open("rb") as handle:
        archive_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    samples = collect_examples(archive_path)
    for split, rows in samples.items():
        print(f"{split} {len(rows)} {dict(Counter(row[1] for row in rows))}", flush=True)
        if {row[1] for row in rows} != set(CLASSES):
            raise ValueError(f"The {split} split lacks component classes")
    train, validation, test = (samples[name] for name in ("train", "validation", "test"))
    train_labels, validation_labels, test_labels = ([r[1] for r in s] for s in (train, validation, test))
    vectorizer = TfidfVectorizer(token_pattern=WORDS.pattern, stop_words=STOP_WORDS, ngram_range=(1, 2),
                                  sublinear_tf=True, min_df=4, max_features=14000)
    train_matrix = vectorizer.fit_transform([row[3] for row in train])
    validation_matrix = vectorizer.transform([row[3] for row in validation])
    test_text = [row[3] for row in test]
    test_matrix = vectorizer.transform(test_text)
    learner = LogisticRegression(C=5, max_iter=240, random_state=SEED)
    with threadpool_limits(limits=3):
        learner.fit(train_matrix, train_labels)
    validation_reference = learner.predict(validation_matrix)
    validation_results = {
        "logistic_regression": round(float(f1_score(validation_labels, validation_reference, average="macro")), 4)
    }
    print(f"Logistic regression validation Macro F1 {validation_results['logistic_regression']}", flush=True)
    scores = learner.predict_proba(test_matrix)
    labels = learner.classes_.tolist()
    predicted = learner.predict(test_matrix)
    test_label_indices = np.array([labels.index(label) for label in test_labels])
    top_three = np.argsort(scores, axis=1)[:, -3:]
    top_three_accuracy = float(np.any(top_three == test_label_indices[:, None], axis=1).mean())
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    write_model(vectorizer, learner, test_text[:25], scores[:25])

    if not skip_forest:
        forest = RandomForestClassifier(n_estimators=48, max_depth=26, min_samples_leaf=2,
                                        max_features="sqrt", n_jobs=2, random_state=SEED)
        forest.fit(train_matrix, train_labels)
        validation_results["random_forest"] = round(float(f1_score(
            validation_labels, forest.predict(validation_matrix), average="macro")), 4)
        print(f"Random Forest validation Macro F1 {validation_results['random_forest']}", flush=True)

    report = classification_report(test_labels, predicted, labels=labels, output_dict=True, zero_division=0)
    metrics = {
        "status": "ready",
        "name": "TF-IDF + Logistic Regression",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "archive_url": ARCHIVE_URL,
        "archive_sha256": archive_hash,
        "data_dictionary_url": DICTIONARY_URL,
        "data_period": "2020–2024",
        "language": "en",
        "target": "Категория компонента из жалобы владельца",
        "classes": [{"id": label, "label": CLASSES[label]["label"]} for label in labels],
        "train_size": len(train),
        "validation_size": len(validation),
        "test_size": len(test),
        "accuracy": round(float(accuracy_score(test_labels, predicted)), 4),
        "macro_f1": round(float(f1_score(test_labels, predicted, average="macro")), 4),
        "top3_accuracy": round(top_three_accuracy, 4),
        "baseline_accuracy": round(max(Counter(test_labels).values()) / len(test_labels), 4),
        "validation_macro_f1": validation_results,
        "test_per_class": report,
        "confusion_matrix": confusion_matrix(test_labels, predicted, labels=labels).tolist(),
        "model_groups": {split: len({row[2] for row in rows}) for split, rows in samples.items()},
        "sklearn_version": sklearn_version,
        "random_seed": SEED,
        "note": "Английские жалобы владельцев в США. Выборки разделены по марке и модели автомобиля. Качество на русских описаниях и Haval отдельно не измерялось.",
    }
    (DATA_DIRECTORY / "model_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
                                                        encoding="utf-8")
    print(f"Test accuracy {metrics['accuracy']}, Macro F1 {metrics['macro_f1']}, Top-3 {metrics['top3_accuracy']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("nhtsa-2020-2024.zip"))
    parser.add_argument("--skip-forest", action="store_true", help="Skip the validation-only Random Forest benchmark")
    args = parser.parse_args()
    if not args.archive.is_file():
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        partial = args.archive.with_suffix(args.archive.suffix + ".part")
        with urllib.request.urlopen(ARCHIVE_URL, timeout=90) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        partial.replace(args.archive)
    train(args.archive, args.skip_forest)


if __name__ == "__main__":
    main()

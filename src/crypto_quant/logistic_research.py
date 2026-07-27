"""Fixed-recipe rolling archive Logistic research without deployment authority."""

import json
import math
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, canonical_json, stable_id
from .causal_research import causal_dataset_hash
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "logistic-archive-research-v1.schema.json"
_ZERO_HASH = "0" * 64
_PRECISION = Decimal("0.000000000001")
_FEATURE_COUNT = 9
_L2 = 0.1
_FIT_RATE = 0.05
_FIT_ITERATIONS = 1000
_PLATT_RATE = 0.01
_PLATT_ITERATIONS = 500
_THRESHOLD = Decimal("0.55")
_BOUNDARY = timedelta(hours=24)
_WARNINGS = (
    "EXPLORATORY_ARCHIVE_OOS_IS_NOT_SEALED_RELEASE_AUDIT",
    "SIMPLE_BASELINE_ECONOMIC_GATE_NOT_PASSED",
    "LONG_ONLY_SHORT_NOT_EVALUATED",
    "NO_MODEL_APPROVED_OR_DEPLOYABLE",
    "NO_PROFITABILITY_CLAIM",
)


class LogisticResearchError(ValueError):
    """The frozen recipe, split, training, or artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LogisticResearchError("LOGISTIC_RESEARCH_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LogisticResearchError("LOGISTIC_RESEARCH_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LogisticResearchError("LOGISTIC_RESEARCH_TIME_INVALID")
    return parsed


def _q(value: float) -> str:
    if not math.isfinite(value):
        raise LogisticResearchError("LOGISTIC_RESEARCH_NUMBER_INVALID")
    decimal = Decimal(str(value)).quantize(
        _PRECISION,
        rounding=ROUND_HALF_EVEN,
    )
    return canonical_decimal(decimal)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-min(value, 700.0)))
    exp_value = math.exp(max(value, -700.0))
    return exp_value / (1.0 + exp_value)


def _matrix(
    samples: Sequence[Mapping[str, Any]],
) -> Tuple[Sequence[Sequence[float]], Sequence[int]]:
    features = []
    labels = []
    for sample in samples:
        values = sample.get("feature_values")
        label = sample.get("y_take")
        if (
            not isinstance(values, Sequence)
            or len(values) != _FEATURE_COUNT
            or label not in (0, 1)
        ):
            raise LogisticResearchError("LOGISTIC_RESEARCH_SAMPLE_INVALID")
        try:
            row = [float(Decimal(value)) for value in values]
        except Exception as error:
            raise LogisticResearchError(
                "LOGISTIC_RESEARCH_SAMPLE_INVALID"
            ) from error
        if any(not math.isfinite(value) for value in row):
            raise LogisticResearchError("LOGISTIC_RESEARCH_SAMPLE_INVALID")
        features.append(row)
        labels.append(label)
    if not features:
        raise LogisticResearchError("LOGISTIC_RESEARCH_SAMPLE_INVALID")
    return features, labels


def _standardizer(
    features: Sequence[Sequence[float]],
) -> Tuple[Sequence[float], Sequence[float]]:
    count = len(features)
    means = [
        sum(row[index] for row in features) / count
        for index in range(_FEATURE_COUNT)
    ]
    deviations = [
        math.sqrt(
            sum((row[index] - means[index]) ** 2 for row in features)
            / count
        )
        for index in range(_FEATURE_COUNT)
    ]
    if any(value <= 1e-15 or not math.isfinite(value) for value in deviations):
        raise LogisticResearchError("LOGISTIC_RESEARCH_ZERO_VARIANCE_FEATURE")
    return means, deviations


def _standardize(
    features: Sequence[Sequence[float]],
    means: Sequence[float],
    deviations: Sequence[float],
) -> Sequence[Sequence[float]]:
    return [
        [
            (row[index] - means[index]) / deviations[index]
            for index in range(_FEATURE_COUNT)
        ]
        for row in features
    ]


def _fit_logistic(
    features: Sequence[Sequence[float]],
    labels: Sequence[int],
) -> Tuple[float, Sequence[float]]:
    prevalence = min(
        max(sum(labels) / len(labels), 1e-6),
        1.0 - 1e-6,
    )
    intercept = math.log(prevalence / (1.0 - prevalence))
    weights = [0.0] * _FEATURE_COUNT
    count = len(labels)
    for _ in range(_FIT_ITERATIONS):
        probabilities = [
            _sigmoid(
                intercept
                + sum(weight * value for weight, value in zip(weights, row))
            )
            for row in features
        ]
        errors = [
            probability - label
            for probability, label in zip(probabilities, labels)
        ]
        intercept -= _FIT_RATE * sum(errors) / count
        gradients = [
            sum(error * row[index] for error, row in zip(errors, features))
            / count
            + _L2 * weights[index]
            for index in range(_FEATURE_COUNT)
        ]
        weights = [
            weight - _FIT_RATE * gradient
            for weight, gradient in zip(weights, gradients)
        ]
    return intercept, weights


def _fit_platt(
    scores: Sequence[float],
    labels: Sequence[int],
) -> Tuple[float, float]:
    if not scores or len(scores) != len(labels):
        raise LogisticResearchError("LOGISTIC_RESEARCH_CALIBRATION_INVALID")
    slope = 1.0
    intercept = 0.0
    count = len(labels)
    for _ in range(_PLATT_ITERATIONS):
        probabilities = [
            _sigmoid(intercept + slope * score) for score in scores
        ]
        errors = [
            probability - label
            for probability, label in zip(probabilities, labels)
        ]
        intercept -= _PLATT_RATE * sum(errors) / count
        slope -= _PLATT_RATE * (
            sum(error * score for error, score in zip(errors, scores))
            / count
        )
    if not math.isfinite(slope) or not math.isfinite(intercept):
        raise LogisticResearchError("LOGISTIC_RESEARCH_CALIBRATION_INVALID")
    return intercept, slope


def _effective_event_count(values: Sequence[Decimal]) -> int:
    count = len(values)
    if count < 2:
        return count
    floats = [float(value) for value in values]
    mean = sum(floats) / count
    denominator = sum((value - mean) ** 2 for value in floats)
    if denominator <= 0:
        return 0
    correlations = []
    for lag in range(1, min(count - 1, 100) + 1):
        correlations.append(
            sum(
                (floats[index] - mean) * (floats[index - lag] - mean)
                for index in range(lag, count)
            )
            / denominator
        )
    positive_sum = 0.0
    for index in range(0, len(correlations) - 1, 2):
        pair = correlations[index] + correlations[index + 1]
        if pair <= 0:
            break
        positive_sum += pair
    tau = max(1.0, 1.0 + 2.0 * positive_sum)
    return max(1, math.floor(count / tau))


def _recipe(dataset: Mapping[str, Any]) -> Dict[str, Any]:
    contract = {
        "recipe_version": "FIXED_L2_LOGISTIC_PLATT_V1",
        "feature_schema_hash": dataset["feature_schema"]["feature_schema_hash"],
        "label_policy_hash": dataset["label_policy"]["label_policy_hash"],
        "direction": "LONG",
        "model_family": "LOGISTIC_REGRESSION",
        "standardization": "FIT_WINDOW_ZSCORE_POPULATION",
        "l2_penalty": "0.1",
        "fit_learning_rate": "0.05",
        "fit_iterations": _FIT_ITERATIONS,
        "platt_learning_rate": "0.01",
        "platt_iterations": _PLATT_ITERATIONS,
        "acceptance_threshold": "0.55",
        "parameter_precision": 12,
        "purge_hours": 24,
        "embargo_hours": 24,
        "shuffle": False,
        "trial_count": 1,
    }
    return {
        "recipe_version": contract["recipe_version"],
        "recipe_hash": business_hash(contract),
        **{key: value for key, value in contract.items() if key != "recipe_version"},
    }


def _samples_for_window(
    samples: Sequence[Mapping[str, Any]],
    *,
    start: datetime,
    end: datetime,
    embargo_start: bool,
    purge_end: bool,
) -> Sequence[Mapping[str, Any]]:
    effective_start = start + _BOUNDARY if embargo_start else start
    effective_end = end - _BOUNDARY if purge_end else end
    selected = []
    for sample in samples:
        decision = _utc(sample["decision_time"])
        label_end = _utc(sample["label_end_time_exclusive"])
        if effective_start <= decision < effective_end and label_end <= end:
            selected.append(sample)
    return selected


def logistic_research_hash(research: Mapping[str, Any]) -> str:
    return artifact_self_hash(research, "research_hash")


def build_logistic_archive_research(
    *,
    dataset: Mapping[str, Any],
    folds: Sequence[Mapping[str, Any]],
    recorded_at: str,
) -> Dict[str, Any]:
    """Execute one fixed rolling Logistic recipe across frozen archive folds."""

    _utc(recorded_at)
    if (
        not isinstance(dataset, Mapping)
        or dataset.get("dataset_hash") != causal_dataset_hash(dataset)
        or dataset.get("research_eligibility")
        != "ARCHIVE_CAUSAL_RESEARCH_ONLY"
        or not isinstance(folds, Sequence)
        or not folds
    ):
        raise LogisticResearchError("LOGISTIC_RESEARCH_INPUT_INVALID")
    samples = dataset["samples"]
    recipe = _recipe(dataset)
    fold_artifacts = []
    predictions = []
    for fold in folds:
        try:
            fit_start = _utc(fold["fit_window_start"])
            fit_end = _utc(fold["fit_window_end_exclusive"])
            calibration_start = _utc(fold["calibration_window_start"])
            calibration_end = _utc(fold["calibration_window_end_exclusive"])
            oos_start = _utc(fold["oos_window_start"])
            oos_end = _utc(fold["oos_window_end_exclusive"])
            fold_index = fold["fold_index"]
            fold_id = fold["fold_id"]
        except (KeyError, TypeError, LogisticResearchError) as error:
            raise LogisticResearchError("LOGISTIC_RESEARCH_FOLD_INVALID") from error
        if not (
            fit_start < fit_end == calibration_start
            and calibration_start < calibration_end == oos_start
            and oos_start < oos_end
            and fold.get("purge_duration_hours") == 24
            and fold.get("embargo_duration_hours") == 24
        ):
            raise LogisticResearchError("LOGISTIC_RESEARCH_FOLD_INVALID")
        fit_samples = _samples_for_window(
            samples,
            start=fit_start,
            end=fit_end,
            embargo_start=False,
            purge_end=True,
        )
        calibration_samples = _samples_for_window(
            samples,
            start=calibration_start,
            end=calibration_end,
            embargo_start=True,
            purge_end=True,
        )
        oos_samples = _samples_for_window(
            samples,
            start=oos_start,
            end=oos_end,
            embargo_start=True,
            purge_end=True,
        )
        if not fit_samples or not calibration_samples or not oos_samples:
            raise LogisticResearchError("LOGISTIC_RESEARCH_SPLIT_EMPTY")
        fit_x, fit_y = _matrix(fit_samples)
        calibration_x, calibration_y = _matrix(calibration_samples)
        oos_x, _ = _matrix(oos_samples)
        means, deviations = _standardizer(fit_x)
        fit_z = _standardize(fit_x, means, deviations)
        calibration_z = _standardize(calibration_x, means, deviations)
        oos_z = _standardize(oos_x, means, deviations)
        intercept, weights = _fit_logistic(fit_z, fit_y)
        calibration_scores = [
            intercept
            + sum(weight * value for weight, value in zip(weights, row))
            for row in calibration_z
        ]
        platt_intercept, platt_slope = _fit_platt(
            calibration_scores,
            calibration_y,
        )
        parameter_values = {
            "feature_means": [_q(value) for value in means],
            "feature_standard_deviations": [
                _q(value) for value in deviations
            ],
            "logistic_intercept": _q(intercept),
            "logistic_weights": [_q(value) for value in weights],
            "platt_intercept": _q(platt_intercept),
            "platt_slope": _q(platt_slope),
            "constant_probability": _q(sum(fit_y) / len(fit_y)),
        }
        inference_means = [
            float(Decimal(value)) for value in parameter_values["feature_means"]
        ]
        inference_deviations = [
            float(Decimal(value))
            for value in parameter_values["feature_standard_deviations"]
        ]
        inference_intercept = float(
            Decimal(parameter_values["logistic_intercept"])
        )
        inference_weights = [
            float(Decimal(value))
            for value in parameter_values["logistic_weights"]
        ]
        inference_platt_intercept = float(
            Decimal(parameter_values["platt_intercept"])
        )
        inference_platt_slope = float(
            Decimal(parameter_values["platt_slope"])
        )
        inference_oos = _standardize(
            oos_x,
            inference_means,
            inference_deviations,
        )
        fold_predictions = []
        for sample, row in zip(oos_samples, inference_oos):
            score = inference_intercept + sum(
                weight * value
                for weight, value in zip(inference_weights, row)
            )
            probability = _q(
                _sigmoid(
                    inference_platt_intercept
                    + inference_platt_slope * score
                )
            )
            accepted = Decimal(probability) >= _THRESHOLD
            realized = Decimal(sample["realized_net_return_24h"])
            filtered = realized if accepted else Decimal("0")
            prediction = {
                "sample_id": sample["sample_id"],
                "fold_id": fold_id,
                "fold_index": fold_index,
                "decision_time": sample["decision_time"],
                "p_net_positive": probability,
                "accepted": accepted,
                "y_take": sample["y_take"],
                "realized_net_return_24h": canonical_decimal(realized),
                "baseline_net_return": canonical_decimal(realized),
                "filtered_net_return": canonical_decimal(filtered),
                "paired_increment": canonical_decimal(filtered - realized),
            }
            fold_predictions.append(prediction)
            predictions.append(prediction)
        count = len(fold_predictions)
        logistic_brier = sum(
            (
                Decimal(prediction["p_net_positive"])
                - Decimal(prediction["y_take"])
            )
            ** 2
            for prediction in fold_predictions
        ) / Decimal(count)
        constant_probability = Decimal(
            parameter_values["constant_probability"]
        )
        constant_brier = sum(
            (constant_probability - Decimal(prediction["y_take"])) ** 2
            for prediction in fold_predictions
        ) / Decimal(count)
        baseline_sum = sum(
            (
                Decimal(prediction["baseline_net_return"])
                for prediction in fold_predictions
            ),
            Decimal("0"),
        )
        filtered_sum = sum(
            (
                Decimal(prediction["filtered_net_return"])
                for prediction in fold_predictions
            ),
            Decimal("0"),
        )
        accepted_count = sum(
            prediction["accepted"] for prediction in fold_predictions
        )
        fit_effective = _effective_event_count(
            [
                Decimal(sample["realized_net_return_24h"])
                for sample in fit_samples
            ]
        )
        feature_limit = fit_effective // 20
        fold_artifacts.append(
            {
                "fold_id": fold_id,
                "fold_index": fold_index,
                "fit_window_start": fold["fit_window_start"],
                "fit_window_end_exclusive": fold["fit_window_end_exclusive"],
                "calibration_window_start": fold["calibration_window_start"],
                "calibration_window_end_exclusive": fold[
                    "calibration_window_end_exclusive"
                ],
                "oos_window_start": fold["oos_window_start"],
                "oos_window_end_exclusive": fold[
                    "oos_window_end_exclusive"
                ],
                "fit_sample_count": len(fit_samples),
                "calibration_sample_count": len(calibration_samples),
                "oos_sample_count": count,
                "accepted_oos_sample_count": accepted_count,
                "fit_effective_event_count": fit_effective,
                "feature_count_limit": feature_limit,
                "feature_complexity_eligible": _FEATURE_COUNT
                <= feature_limit,
                "parameters": parameter_values,
                "prediction_root_hash": business_hash(fold_predictions),
                "metrics": {
                    "logistic_brier": canonical_decimal(logistic_brier),
                    "constant_brier": canonical_decimal(constant_brier),
                    "baseline_net_return_sum": canonical_decimal(baseline_sum),
                    "filtered_net_return_sum": canonical_decimal(filtered_sum),
                    "paired_increment_sum": canonical_decimal(
                        filtered_sum - baseline_sum
                    ),
                    "acceptance_rate": canonical_decimal(
                        Decimal(accepted_count) / Decimal(count)
                    ),
                },
            }
        )
    if predictions != sorted(
        predictions,
        key=lambda prediction: (
            prediction["decision_time"],
            prediction["fold_index"],
        ),
    ):
        raise LogisticResearchError("LOGISTIC_RESEARCH_PREDICTION_ORDER_INVALID")
    total = len(predictions)
    accepted_total = sum(prediction["accepted"] for prediction in predictions)
    logistic_brier = sum(
        (
            Decimal(prediction["p_net_positive"])
            - Decimal(prediction["y_take"])
        )
        ** 2
        for prediction in predictions
    ) / Decimal(total)
    constant_brier = sum(
        (
            Decimal(fold["parameters"]["constant_probability"])
            - Decimal(prediction["y_take"])
        )
        ** 2
        for fold in fold_artifacts
        for prediction in predictions
        if prediction["fold_id"] == fold["fold_id"]
    ) / Decimal(total)
    baseline_total = sum(
        (Decimal(value["baseline_net_return"]) for value in predictions),
        Decimal("0"),
    )
    filtered_total = sum(
        (Decimal(value["filtered_net_return"]) for value in predictions),
        Decimal("0"),
    )
    summary = {
        "fold_count": len(fold_artifacts),
        "oos_sample_count": total,
        "accepted_oos_sample_count": accepted_total,
        "acceptance_rate": canonical_decimal(
            Decimal(accepted_total) / Decimal(total)
        ),
        "logistic_brier": canonical_decimal(logistic_brier),
        "constant_brier": canonical_decimal(constant_brier),
        "brier_better_fold_count": sum(
            Decimal(fold["metrics"]["logistic_brier"])
            < Decimal(fold["metrics"]["constant_brier"])
            for fold in fold_artifacts
        ),
        "baseline_net_return_sum": canonical_decimal(baseline_total),
        "filtered_net_return_sum": canonical_decimal(filtered_total),
        "paired_increment_sum": canonical_decimal(
            filtered_total - baseline_total
        ),
        "baseline_nonnegative_quarter_count": sum(
            Decimal(fold["metrics"]["baseline_net_return_sum"]) >= 0
            for fold in fold_artifacts
        ),
        "filtered_nonnegative_quarter_count": sum(
            Decimal(fold["metrics"]["filtered_net_return_sum"]) >= 0
            for fold in fold_artifacts
        ),
        "feature_complexity_eligible_fold_count": sum(
            fold["feature_complexity_eligible"] for fold in fold_artifacts
        ),
        "simple_baseline_economic_gate_status": (
            "NOT_PASSED_EXPLORATORY_POINT_ESTIMATE"
        ),
    }
    identity = {
        "dataset_hash": dataset["dataset_hash"],
        "recipe_hash": recipe["recipe_hash"],
        "fold_prediction_roots": [
            fold["prediction_root_hash"] for fold in fold_artifacts
        ],
    }
    research = {
        "$schema": "./logistic-archive-research-v1.schema.json",
        "schema_version": "1.0.0",
        "research_id": stable_id("logistic_archive_research", identity),
        "research_hash": _ZERO_HASH,
        "recorded_at": recorded_at,
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": dataset["dataset_hash"],
        "recipe": recipe,
        "folds": fold_artifacts,
        "predictions_root_hash": business_hash(predictions),
        "predictions": predictions,
        "summary": summary,
        "research_status": (
            "EXPLORATORY_LOGISTIC_BRIER_BETTER_THAN_CONSTANT"
            if logistic_brier < constant_brier
            else "EXPLORATORY_LOGISTIC_NOT_BETTER_THAN_CONSTANT"
        ),
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "release_oos_eligibility": "INELIGIBLE_EXPLORATORY_ARCHIVE",
        "model_activation_eligibility": "INELIGIBLE_RESEARCH_ONLY",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    research["research_hash"] = logistic_research_hash(research)
    if tuple(_validator().iter_errors(research)):
        raise LogisticResearchError("LOGISTIC_RESEARCH_SCHEMA_INVALID")
    return research


def logistic_research_reasons(
    research: Mapping[str, Any],
    *,
    dataset: Mapping[str, Any],
    folds: Sequence[Mapping[str, Any]],
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(research, Mapping):
        return ("LOGISTIC_RESEARCH_INVALID",)
    try:
        if tuple(_validator().iter_errors(research)):
            reasons.append("LOGISTIC_RESEARCH_SCHEMA_INVALID")
        if research.get("research_hash") != logistic_research_hash(research):
            reasons.append("LOGISTIC_RESEARCH_HASH_MISMATCH")
        rebuilt = build_logistic_archive_research(
            dataset=dataset,
            folds=folds,
            recorded_at=research["recorded_at"],
        )
        if business_hash(rebuilt) != business_hash(research):
            reasons.append("LOGISTIC_RESEARCH_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, LogisticResearchError):
        reasons.append("LOGISTIC_RESEARCH_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_logistic_research(
    *,
    research: Mapping[str, Any],
    output_path: Path,
) -> None:
    if (
        not isinstance(research, Mapping)
        or tuple(_validator().iter_errors(research))
        or research.get("research_hash") != logistic_research_hash(research)
    ):
        raise LogisticResearchError("LOGISTIC_RESEARCH_INVALID")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _publish_exact(path, canonical_json(research).encode("utf-8"))


def load_logistic_research(path: Path) -> Mapping[str, Any]:
    try:
        research = _strict_json_bytes(
            Path(path).expanduser().resolve().read_bytes()
        )
    except OSError as error:
        raise LogisticResearchError("LOGISTIC_RESEARCH_READ_FAILED") from error
    if (
        tuple(_validator().iter_errors(research))
        or research.get("research_hash") != logistic_research_hash(research)
    ):
        raise LogisticResearchError("LOGISTIC_RESEARCH_INVALID")
    return research

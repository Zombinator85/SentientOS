from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.daemons import pulse_bus

EXTRACTOR_ID = "gaze_adapter"
EXTRACTOR_VERSION = "1"
EVENT_TYPE = "perception.gaze"
PRIVACY_CHOICES = ("public", "internal", "private")
PIPELINE_CHOICES = ("auto", "sdk", "camera", "os")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_import_cv2() -> Any | None:
    try:
        import cv2
    except Exception:
        return None
    return cv2


def _safe_import_mediapipe() -> Any | None:
    try:
        import mediapipe as mp
    except Exception:
        return None
    return mp


def _safe_import_sdk() -> tuple[Any | None, str | None]:
    try:
        import tobii_research as tr
    except Exception:
        return None, None
    return tr, getattr(tr, "__version__", "unknown")


def _safe_import_pyautogui() -> Any | None:
    try:
        import pyautogui
    except Exception:
        return None
    return pyautogui


def _estimate_from_camera() -> tuple[dict[str, Any] | None, str | None]:
    cv2 = _safe_import_cv2()
    mp = _safe_import_mediapipe()
    if cv2 is None or mp is None:
        return None, "camera_estimation_dependencies_unavailable"

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        return None, "webcam_unavailable"
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        return None, "failed_to_capture_webcam_frame"

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as fm:
        results = fm.process(rgb)

    if not results.multi_face_landmarks:
        return {
            "gaze_point_norm": None,
            "gaze_vector": [0.0, 0.0, 1.0],
            "confidence": 0.18,
            "calibration_state": "uncalibrated",
            "calibration_confidence": 0.1,
            "source_pipeline": "camera_estimate",
            "degradation_reason": "no_face_detected",
            "pipeline_id": "mediapipe_facemesh",
        }, None

    lm = results.multi_face_landmarks[0].landmark
    left_eye = lm[468] if len(lm) > 468 else lm[33]
    right_eye = lm[473] if len(lm) > 473 else lm[263]
    eye_x = _clip01((left_eye.x + right_eye.x) / 2.0)
    eye_y = _clip01((left_eye.y + right_eye.y) / 2.0)

    dx = (eye_x - 0.5) * 1.2
    dy = (0.5 - eye_y) * 1.2
    dz = max(0.0, 1.0 - min(1.0, dx * dx + dy * dy)) ** 0.5

    return {
        "gaze_point_norm": [eye_x, eye_y],
        "gaze_vector": [float(dx), float(dy), float(dz)],
        "confidence": 0.42,
        "calibration_state": "uncalibrated",
        "calibration_confidence": 0.25,
        "source_pipeline": "camera_estimate",
        "degradation_reason": "coarse_camera_estimate_not_calibrated",
        "pipeline_id": "mediapipe_facemesh",
    }, None


def _estimate_from_os() -> tuple[dict[str, Any] | None, str | None]:
    pyautogui = _safe_import_pyautogui()
    if pyautogui is None:
        return None, "os_accessibility_dependencies_unavailable"
    try:
        width, height = pyautogui.size()
        pos = pyautogui.position()
    except Exception:
        return None, "os_accessibility_cursor_probe_failed"
    if width <= 0 or height <= 0:
        return None, "invalid_display_geometry"

    x_norm = _clip01(float(pos.x) / float(width))
    y_norm = _clip01(float(pos.y) / float(height))
    return {
        "gaze_point_norm": [x_norm, y_norm],
        "gaze_point_px": [float(pos.x), float(pos.y)],
        "confidence": 0.2,
        "calibration_state": "unknown",
        "calibration_confidence": 0.0,
        "source_pipeline": "os_accessibility",
        "degradation_reason": "cursor_proxy_only_not_true_eye_tracking",
        "pipeline_id": "os_accessibility_cursor_proxy",
        "display_geometry": {"x": 0.0, "y": 0.0, "width": float(width), "height": float(height)},
    }, None


def _estimate_from_sdk() -> tuple[dict[str, Any] | None, str | None]:
    tr, sdk_version = _safe_import_sdk()
    if tr is None:
        return None, "eye_tracker_sdk_unavailable"
    _ = tr
    return {
        "gaze_point_norm": None,
        "confidence": 0.12,
        "calibration_state": "unknown",
        "source_pipeline": "eye_tracker_sdk",
        "degradation_reason": "sdk_detected_but_runtime_collection_not_configured",
        "pipeline_id": "tobii_sdk",
        "sdk_version": sdk_version or "unknown",
    }, None


def _choose_pipeline(pipeline: str) -> tuple[dict[str, Any], str]:
    attempts: list[tuple[str, Any]]
    if pipeline == "sdk":
        attempts = [("sdk", _estimate_from_sdk)]
    elif pipeline == "camera":
        attempts = [("camera", _estimate_from_camera)]
    elif pipeline == "os":
        attempts = [("os", _estimate_from_os)]
    else:
        attempts = [("sdk", _estimate_from_sdk), ("camera", _estimate_from_camera), ("os", _estimate_from_os)]

    reasons: list[str] = []
    for _name, fn in attempts:
        estimate, reason = fn()
        if estimate is not None:
            return estimate, ""
        if reason:
            reasons.append(reason)

    return {
        "gaze_point_norm": None,
        "confidence": 0.05,
        "calibration_state": "unknown",
        "source_pipeline": "none",
        "degradation_reason": ";".join(reasons) if reasons else "no_gaze_pipeline_available",
        "pipeline_id": "none",
    }, ";".join(reasons)


def _raw_reference(estimate: dict[str, Any], output_dir: Path) -> str | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_gaze_raw.json"
    path.write_text(json.dumps({"raw": estimate}, sort_keys=True), encoding="utf-8")
    return str(path)


def build_perception_payload(
    *,
    privacy_class: str,
    retain_raw: bool,
    raw_output_dir: Path,
    screen_width: int | None,
    screen_height: int | None,
    pipeline: str,
) -> dict[str, Any]:
    estimate, fallback_reason = _choose_pipeline(pipeline)
    point_norm = estimate.get("gaze_point_norm")

    payload: dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "timestamp": _iso_now(),
        "source": "local.gaze",
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": _clip01(float(estimate.get("confidence", 0.05))),
        "privacy_class": privacy_class,
        "provenance": {
            "extractor": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "pipeline_id": str(estimate.get("pipeline_id", "none")),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "sdk_version": estimate.get("sdk_version", ""),
        },
        "gaze_point_norm": point_norm,
        "calibration_state": str(estimate.get("calibration_state", "unknown")),
        "source_pipeline": str(estimate.get("source_pipeline", "none")),
        "raw_samples_retained": bool(retain_raw),
        "redaction_applied": not retain_raw,
    }

    if "gaze_vector" in estimate:
        payload["gaze_vector"] = estimate["gaze_vector"]
    if "calibration_confidence" in estimate:
        payload["calibration_confidence"] = _clip01(float(estimate["calibration_confidence"]))
    if "display_geometry" in estimate:
        payload["display_geometry"] = estimate["display_geometry"]

    if point_norm and screen_width and screen_height:
        payload["gaze_point_px"] = [float(point_norm[0]) * float(screen_width), float(point_norm[1]) * float(screen_height)]
        payload["display_geometry"] = {"x": 0.0, "y": 0.0, "width": float(screen_width), "height": float(screen_height)}

    degradation_reason = estimate.get("degradation_reason") or fallback_reason
    if degradation_reason:
        payload["degradation_reason"] = str(degradation_reason)

    if retain_raw:
        payload["raw_samples_reference"] = _raw_reference(estimate, raw_output_dir)

    return payload


def emit_pulse(payload: dict[str, Any], *, output_log: Path) -> dict[str, Any]:
    event = {
        "timestamp": payload["timestamp"],
        "source_daemon": EXTRACTOR_ID,
        "event_type": EVENT_TYPE,
        "payload": payload,
        "priority": "info",
        "event_origin": "local",
        "context": {"privacy_class": payload["privacy_class"]},
    }
    try:
        published = pulse_bus.publish(event)
        return {"published": True, "event": published}
    except Exception as exc:
        output_log.parent.mkdir(parents=True, exist_ok=True)
        with output_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return {"published": False, "error": str(exc), "fallback_log": str(output_log), "event": event}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit perception.gaze events from offline best-effort gaze telemetry")
    parser.add_argument("--privacy-class", default="internal", choices=PRIVACY_CHOICES)
    parser.add_argument("--retain-raw", action="store_true", default=False)
    parser.add_argument("--raw-output-dir", default="glow/perception/quarantine/gaze_raw")
    parser.add_argument("--iterations", type=int, default=1, help="number of captures; 0 means run forever")
    parser.add_argument("--seconds", type=float, default=None, help="capture budget in seconds")
    parser.add_argument("--output-log", default="glow/perception/perception_gaze_events.jsonl")
    parser.add_argument("--screen-width", type=int, default=None)
    parser.add_argument("--screen-height", type=int, default=None)
    parser.add_argument("--pipeline", default="auto", choices=PIPELINE_CHOICES)
    args = parser.parse_args(argv)

    count = 0
    started = time.time()
    while True:
        payload = build_perception_payload(
            privacy_class=args.privacy_class,
            retain_raw=bool(args.retain_raw),
            raw_output_dir=Path(args.raw_output_dir),
            screen_width=args.screen_width,
            screen_height=args.screen_height,
            pipeline=args.pipeline,
        )
        result = emit_pulse(payload, output_log=Path(args.output_log))
        print(json.dumps(result, sort_keys=True))
        count += 1

        if args.iterations > 0 and count >= args.iterations:
            break
        if args.seconds is not None and (time.time() - started) >= args.seconds:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

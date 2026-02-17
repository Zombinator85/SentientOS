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

EXTRACTOR_ID = "vision_adapter"
EXTRACTOR_VERSION = "1"
EVENT_TYPE = "perception.vision"
PRIVACY_CHOICES = ("public", "internal", "private")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compute_motion_score(cv2: Any, previous_gray: Any | None, current_frame: Any) -> tuple[float | None, Any]:
    gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    if previous_gray is None:
        return None, gray
    diff = cv2.absdiff(previous_gray, gray)
    motion = float(diff.mean() / 255.0)
    return _clip01(motion), gray


def _compute_lighting_score(cv2: Any, frame: Any) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return _clip01(float(gray.mean() / 255.0))


def _normalize_bbox(x: int, y: int, w: int, h: int, width: int, height: int) -> list[float]:
    return [_clip01(x / width), _clip01(y / height), _clip01(w / width), _clip01(h / height)]


def _estimate_head_pose_from_bbox(bbox: list[float]) -> tuple[list[float], float]:
    cx = bbox[0] + (bbox[2] / 2.0)
    cy = bbox[1] + (bbox[3] / 2.0)
    yaw = (cx - 0.5) * 60.0
    pitch = (0.5 - cy) * 40.0
    roll = 0.0
    return [roll, pitch, yaw], 0.35


def _estimate_gaze_from_head_pose(head_pose_rpy: list[float]) -> tuple[list[float], float]:
    _roll, pitch, yaw = head_pose_rpy
    dx = max(-1.0, min(1.0, yaw / 45.0))
    dy = max(-1.0, min(1.0, -pitch / 30.0))
    dz_sq = max(0.0, 1.0 - (dx * dx + dy * dy))
    dz = dz_sq ** 0.5
    return [float(dx), float(dy), float(dz)], 0.3


def _haar_pipeline(cv2: Any, frame: Any) -> tuple[dict[str, Any], int, str, float | None]:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    features: dict[str, Any] = {"face_present": False}
    if len(faces) == 0:
        return features, 0, "opencv_haar", 0.5

    x, y, w, h = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
    height, width = frame.shape[:2]
    bbox = _normalize_bbox(int(x), int(y), int(w), int(h), width, height)
    head_pose_rpy, head_conf = _estimate_head_pose_from_bbox(bbox)
    gaze_vector, gaze_conf = _estimate_gaze_from_head_pose(head_pose_rpy)

    features = {
        "face_present": True,
        "face_bbox": bbox,
        "face_landmarks": {"format": "none", "points": []},
        "head_pose_rpy": head_pose_rpy,
        "head_pose_confidence": head_conf,
        "gaze_vector": gaze_vector,
        "gaze_confidence": gaze_conf,
    }
    return features, int(len(faces)), "opencv_haar", 0.72


def _mediapipe_pipeline(mp: Any, cv2: Any, frame: Any) -> tuple[dict[str, Any], int, str, float | None]:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = frame.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as fm:
        results = fm.process(rgb)

    if not results.multi_face_landmarks:
        return {"face_present": False}, 0, "mediapipe_facemesh", 0.58

    landmarks = results.multi_face_landmarks[0].landmark
    points = [[_clip01(lm.x), _clip01(lm.y)] for lm in landmarks]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    head_pose_rpy, head_conf = _estimate_head_pose_from_bbox(bbox)
    gaze_vector, gaze_conf = _estimate_gaze_from_head_pose(head_pose_rpy)

    features = {
        "face_present": True,
        "face_bbox": [_clip01(v) for v in bbox],
        "face_landmarks": {"format": "mediapipe_468", "points": points},
        "head_pose_rpy": head_pose_rpy,
        "head_pose_confidence": head_conf,
        "gaze_vector": gaze_vector,
        "gaze_confidence": gaze_conf,
    }
    _ = (h, w)
    return features, 1, "mediapipe_facemesh", 0.85


def _retain_frame(cv2: Any, frame: Any, *, privacy_class: str, output_dir: Path) -> str | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{stamp}_{privacy_class}.jpg"
    if cv2.imwrite(str(path), frame):
        return str(path)
    return None


def _build_degraded_payload(*, privacy_class: str, reason: str) -> dict[str, Any]:
    return {
        "event_type": EVENT_TYPE,
        "timestamp": _iso_now(),
        "source": "local.webcam",
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": 0.1,
        "privacy_class": privacy_class,
        "provenance": {
            "extractor": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "pipeline_id": "none",
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "frame_size": {"width": 0, "height": 0},
        "fps_estimate": None,
        "faces_detected": None,
        "features": {"face_present": False},
        "raw_frame_retained": False,
        "redaction_applied": True,
        "degradation_reason": reason,
    }


def build_perception_payload(
    *,
    privacy_class: str,
    retain_raw: bool,
    raw_output_dir: Path,
    device_hint: str | None,
    previous_gray: Any | None,
) -> tuple[dict[str, Any], Any | None]:
    cv2 = _safe_import_cv2()
    if cv2 is None:
        return _build_degraded_payload(privacy_class=privacy_class, reason="opencv(cv2) unavailable"), None

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        return _build_degraded_payload(privacy_class=privacy_class, reason="webcam unavailable"), None

    started = time.time()
    ok, frame = capture.read()
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()

    if not ok or frame is None:
        return _build_degraded_payload(privacy_class=privacy_class, reason="failed to capture frame"), None

    motion_score, gray = _compute_motion_score(cv2, previous_gray, frame)
    lighting_score = _compute_lighting_score(cv2, frame)

    mp = _safe_import_mediapipe()
    if mp is not None:
        features, faces_detected, pipeline_id, base_conf = _mediapipe_pipeline(mp, cv2, frame)
    else:
        features, faces_detected, pipeline_id, base_conf = _haar_pipeline(cv2, frame)

    elapsed = max(0.001, time.time() - started)
    fps_estimate = float(fps) if fps and fps > 0 else float(1.0 / elapsed)
    confidence = float(base_conf or 0.4)

    payload: dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "timestamp": _iso_now(),
        "source": "local.webcam",
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": confidence,
        "privacy_class": privacy_class,
        "provenance": {
            "extractor": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "pipeline_id": pipeline_id,
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "frame_size": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
        "fps_estimate": float(fps_estimate),
        "faces_detected": int(faces_detected),
        "features": features,
        "raw_frame_retained": bool(retain_raw),
        "redaction_applied": not retain_raw,
        "lighting_score": lighting_score,
    }
    if motion_score is not None:
        payload["motion_score"] = motion_score
    if device_hint:
        payload["device_hint"] = device_hint
    if retain_raw:
        raw_ref = _retain_frame(cv2, frame, privacy_class=privacy_class, output_dir=raw_output_dir)
        if raw_ref:
            payload["raw_frame_reference"] = raw_ref
    return payload, gray


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
        return {
            "published": False,
            "error": str(exc),
            "fallback_log": str(output_log),
            "event": event,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit perception.vision events from offline webcam telemetry")
    parser.add_argument("--privacy-class", default="internal", choices=PRIVACY_CHOICES)
    parser.add_argument("--retain-raw", action="store_true", default=False)
    parser.add_argument("--raw-output-dir", default="glow/perception/quarantine/vision_raw")
    parser.add_argument("--device-hint", default=None)
    parser.add_argument("--iterations", type=int, default=1, help="number of captures; 0 means run forever")
    parser.add_argument("--seconds", type=float, default=None, help="capture budget in seconds")
    parser.add_argument("--output-log", default="glow/perception/perception_vision_events.jsonl")
    args = parser.parse_args(argv)

    count = 0
    started = time.time()
    previous_gray = None
    while True:
        payload, previous_gray = build_perception_payload(
            privacy_class=args.privacy_class,
            retain_raw=bool(args.retain_raw),
            raw_output_dir=Path(args.raw_output_dir),
            device_hint=args.device_hint,
            previous_gray=previous_gray,
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

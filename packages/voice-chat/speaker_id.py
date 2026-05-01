"""Speaker identification using ECAPA-TDNN embeddings (SpeechBrain).

Uses a pre-trained ECAPA-TDNN model for 192-dim speaker embeddings.
EER ~1% on VoxCeleb1, vs ~15-20% for MFCC baseline.
Runs on CPU, ~150ms per 1s audio on Apple Silicon.
"""
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger("voice_chat")

# --- ECAPA-TDNN Model (lazy-loaded singleton) ---

_ecapa_model = None
_EMBEDDING_DIM = 192


def _get_ecapa():
    global _ecapa_model
    if _ecapa_model is None:
        from speechbrain.inference.speaker import EncoderClassifier
        logger.info("[speaker_id] Loading ECAPA-TDNN model...")
        t0 = time.time()
        _ecapa_model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/tmp/sb_ecapa",
        )
        logger.info(f"[speaker_id] ECAPA-TDNN loaded in {time.time()-t0:.1f}s")
    return _ecapa_model


def compute_embedding(wav: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Compute 192-dim ECAPA-TDNN speaker embedding from float32 waveform."""
    model = _get_ecapa()
    signal = torch.tensor(wav, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        embedding = model.encode_batch(signal)
    emb = embedding.squeeze().numpy()
    # L2 normalize
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


# --- Audio I/O ---

_FFMPEG = "/opt/homebrew/bin/ffmpeg"


def audio_bytes_to_wav(audio_bytes: bytes) -> np.ndarray | None:
    """Convert audio bytes (webm/wav/any ffmpeg format) to float32 16kHz mono."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        try:
            result = subprocess.run(
                [_FFMPEG, "-i", f.name, "-ar", "16000", "-ac", "1",
                 "-f", "f32le", "-loglevel", "error", "-"],
                capture_output=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        if len(result.stdout) < 3200:  # < 0.1s at 16kHz
            return None
        return np.frombuffer(result.stdout, dtype=np.float32)


# --- Speaker Profile Management ---

class SpeakerIdentifier:
    """Manages speaker profiles and performs identification."""

    def __init__(self, profiles_dir: str | Path):
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profiles: dict[str, dict] = {}
        # Enrollment state
        self._enrolling: str | None = None
        self._enroll_display: str = ""
        self._enroll_samples: list[np.ndarray] = []
        self._load_profiles()

    def _load_profiles(self):
        index_file = self.profiles_dir / "speakers.json"
        if not index_file.exists():
            return
        try:
            meta = json.loads(index_file.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for name, info in meta.items():
            emb_file = self.profiles_dir / f"{name}.npy"
            if emb_file.exists():
                emb = np.load(emb_file)
                if emb.shape[0] != _EMBEDDING_DIM:
                    logger.warning(
                        f"[speaker_id] profile '{name}' has dim={emb.shape[0]}, "
                        f"expected {_EMBEDDING_DIM} — skipping (re-enrollment needed)"
                    )
                    continue
                self.profiles[name] = {
                    "embedding": emb,
                    "samples": info.get("samples", 0),
                    "display_name": info.get("display_name", name),
                }
        logger.info(f"[speaker_id] loaded {len(self.profiles)} profile(s)")

    def _save_profiles(self):
        meta = {}
        for name, profile in self.profiles.items():
            np.save(self.profiles_dir / f"{name}.npy", profile["embedding"])
            meta[name] = {
                "samples": profile["samples"],
                "display_name": profile["display_name"],
            }
        (self.profiles_dir / "speakers.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )

    # --- Enrollment ---

    def start_enrollment(self, name: str, display_name: str = "") -> str:
        """Start enrollment for a speaker. Returns status message."""
        self._enrolling = name
        self._enroll_display = display_name or name
        self._enroll_samples = []
        return f"登録開始: {self._enroll_display}さん、3〜5回話してください"

    def add_enrollment_sample(self, audio_bytes: bytes) -> dict:
        """Add a voice sample during enrollment. Returns status."""
        if not self._enrolling:
            return {"ok": False, "message": "登録が開始されていません"}

        wav = audio_bytes_to_wav(audio_bytes)
        if wav is None:
            return {"ok": False, "message": "音声を認識できませんでした"}

        # Check audio quality (minimum length, sufficient energy)
        duration = len(wav) / 16000
        energy = float(np.sqrt(np.mean(wav ** 2)))
        if duration < 0.5:
            return {"ok": False, "message": "音声が短すぎます（0.5秒以上必要）"}
        if energy < 0.01:
            return {"ok": False, "message": "音声が小さすぎます。マイクに向かって話してください"}
        logger.info(f"[speaker_id] enroll sample check: duration={duration:.1f}s, energy={energy:.4f}")

        embedding = compute_embedding(wav)
        self._enroll_samples.append(embedding)
        n = len(self._enroll_samples)

        # Check consistency between samples
        if n >= 2:
            sims = []
            for i in range(n - 1):
                sims.append(cosine_similarity(self._enroll_samples[i], embedding))
            avg_sim = np.mean(sims)
            if avg_sim < 0.7:
                logger.warning(f"[speaker_id] enrollment sample {n} low similarity: {avg_sim:.3f}")

        logger.info(f"[speaker_id] enrollment sample {n} added "
                     f"(duration={duration:.1f}s, energy={energy:.4f})")

        if n >= 3:
            return {"ok": True, "samples": n,
                    "message": f"サンプル {n}/5 — あと{max(0, 5-n)}回（3回以上で登録可能）",
                    "can_finish": True}
        return {"ok": True, "samples": n,
                "message": f"サンプル {n}/5 — あと{3-n}回以上必要",
                "can_finish": False}

    def finish_enrollment(self) -> dict:
        """Finalize enrollment with collected samples."""
        if not self._enrolling or len(self._enroll_samples) < 3:
            return {"ok": False,
                    "message": "サンプルが足りません（最低3つ必要）"}

        name = self._enrolling
        display_name = self._enroll_display
        # Average all sample embeddings
        avg_embedding = np.mean(self._enroll_samples, axis=0)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm

        self.profiles[name] = {
            "embedding": avg_embedding,
            "samples": len(self._enroll_samples),
            "display_name": display_name,
        }
        self._save_profiles()

        # Clear enrollment state
        n = len(self._enroll_samples)
        self._enrolling = None
        self._enroll_display = ""
        self._enroll_samples = []

        logger.info(f"[speaker_id] enrolled '{display_name}' ({name}) with {n} samples")
        return {"ok": True,
                "message": f"{display_name}さんの声を登録しました（{n}サンプル）"}

    def cancel_enrollment(self):
        self._enrolling = None
        self._enroll_display = ""
        self._enroll_samples = []

    @property
    def is_enrolling(self) -> bool:
        return self._enrolling is not None

    # --- Identification ---

    def identify(self, audio_bytes: bytes, threshold: float = 0.45) -> dict:
        """Identify speaker from audio bytes.

        Returns: {speaker: str|None, display_name: str, similarity: float, all_scores: dict}
        Threshold 0.45 for ECAPA-TDNN (cross-device enrollment/identification).
        """
        if not self.profiles:
            return {"speaker": None, "display_name": "", "similarity": 0.0,
                    "all_scores": {}}

        wav = audio_bytes_to_wav(audio_bytes)
        if wav is None:
            return {"speaker": None, "display_name": "", "similarity": 0.0,
                    "all_scores": {}}

        duration = len(wav) / 16000
        if duration < 1.0:
            logger.info(f"[speaker_id] skip identify: too short ({duration:.1f}s)")
            return {"speaker": None, "display_name": "", "similarity": 0.0,
                    "all_scores": {}}

        embedding = compute_embedding(wav)
        logger.debug(f"[speaker_id] identify: duration={duration:.1f}s, energy={float(np.sqrt(np.mean(wav**2))):.4f}, "
                      f"emb[:3]={embedding[:3]}")
        return self.identify_from_embedding(embedding, threshold)

    def identify_from_embedding(self, embedding: np.ndarray,
                                 threshold: float = 0.45) -> dict:
        """Identify speaker from a pre-computed embedding."""
        scores = {}
        best_name = None
        best_sim = -1.0

        for name, profile in self.profiles.items():
            sim = cosine_similarity(embedding, profile["embedding"])
            scores[name] = round(sim, 4)
            if sim > best_sim:
                best_sim = sim
                best_name = name

        if best_sim >= threshold and best_name:
            display = self.profiles[best_name]["display_name"]
            return {"speaker": best_name, "display_name": display,
                    "similarity": round(best_sim, 4), "all_scores": scores}

        return {"speaker": None, "display_name": "", "similarity": round(best_sim, 4),
                "all_scores": scores}

    def identify_wav(self, wav: np.ndarray, threshold: float = 0.45) -> dict:
        """Identify speaker from float32 16kHz mono waveform."""
        if not self.profiles:
            return {"speaker": None, "display_name": "", "similarity": 0.0,
                    "all_scores": {}}
        embedding = compute_embedding(wav)
        return self.identify_from_embedding(embedding, threshold)

    # --- Profile management ---

    def remove_profile(self, name: str) -> bool:
        if name not in self.profiles:
            return False
        del self.profiles[name]
        (self.profiles_dir / f"{name}.npy").unlink(missing_ok=True)
        self._save_profiles()
        logger.info(f"[speaker_id] removed profile '{name}'")
        return True

    def list_profiles(self) -> list[dict]:
        return [
            {"name": name, "display_name": p["display_name"], "samples": p["samples"]}
            for name, p in self.profiles.items()
        ]

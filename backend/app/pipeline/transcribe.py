"""Transcrição com timestamps por palavra (faster-whisper, roda local e grátis)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class Word:
    text: str
    start: float
    end: float


class Transcriber(Protocol):
    def transcribe(self, wav_path: str, language: str | None = None,
                   progress: Callable[[float], None] | None = None) -> list[Word]: ...


_models: dict[tuple, object] = {}
_models_lock = threading.Lock()


class WhisperTranscriber:
    """Carrega o modelo uma vez e reutiliza (modelos 'small'/'medium' dão bom resultado em português)."""

    def __init__(self, model: str = "small", device: str = "auto", compute_type: str = "int8"):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type

    def _model(self):
        key = (self.model_name, self.device, self.compute_type)
        with _models_lock:
            if key not in _models:
                from faster_whisper import WhisperModel  # import tardio: é pesado

                _models[key] = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            return _models[key]

    def transcribe(self, wav_path: str, language: str | None = None,
                   progress: Callable[[float], None] | None = None) -> list[Word]:
        model = self._model()
        segments, info = model.transcribe(
            wav_path,
            language=None if language in (None, "", "auto") else language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        total = float(getattr(info, "duration", 0) or 0)
        words: list[Word] = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append(Word(text, float(w.start), float(w.end)))
            if progress and total > 0:
                progress(min(1.0, float(seg.end) / total))
        return words


def get_transcriber(settings) -> Transcriber:
    return WhisperTranscriber(settings.whisper_model, settings.whisper_device, settings.whisper_compute)

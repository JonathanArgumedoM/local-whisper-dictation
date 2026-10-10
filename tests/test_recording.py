import json
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.dictation_app import DictationApp, usage_help_text


class RecordingRecoveryTests(unittest.TestCase):
    def setUp(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
        config.update(status_beeps=False, max_record_seconds=0)
        with patch("src.dictation_app.keyboard.Controller"):
            self.app = DictationApp(config)
        self.app.set_status = Mock()
        self.log = patch("src.dictation_app.log_runtime_error").start()
        patch("src.dictation_app.TargetWindow.capture", return_value=None).start()
        self.addCleanup(patch.stopall)

    def test_missing_microphone_does_not_escape_and_can_retry(self):
        stream = Mock()
        with patch("src.dictation_app.sd.InputStream", side_effect=[RuntimeError("No input device"), stream]):
            self.app.start_recording()
            self.assertFalse(self.app.recording)
            self.assertIsNone(self.app.stream)
            self.app.start_recording()
        self.assertTrue(self.app.recording)
        stream.start.assert_called_once()
        self.app.stop_recording()
        stream.close.assert_called_once()

    def test_start_failure_closes_partial_stream(self):
        stream = Mock()
        stream.start.side_effect = RuntimeError("Device disconnected")
        with patch("src.dictation_app.sd.InputStream", return_value=stream):
            self.app.start_recording(toggle=True)
        stream.close.assert_called_once()
        self.assertFalse(self.app.recording)
        self.assertFalse(self.app.toggle_recording)
        self.assertIsNone(self.app.stream)

    def test_stop_failure_still_closes_stream_and_can_retry(self):
        broken, healthy = Mock(), Mock()
        broken.stop.side_effect = RuntimeError("Disconnected while recording")
        with patch("src.dictation_app.sd.InputStream", side_effect=[broken, healthy]):
            self.app.start_recording()
            self.app.stop_recording()
            broken.close.assert_called_once()
            self.assertFalse(self.app.recording)
            self.assertFalse(self.app.transcribing)
            self.assertIsNone(self.app.stream)
            self.app.start_recording()
            self.assertTrue(self.app.recording)
            self.app.stop_recording()

    def test_close_failure_does_not_escape_to_hotkey_listener(self):
        stream = Mock()
        stream.close.side_effect = RuntimeError("Close failed")
        with patch("src.dictation_app.sd.InputStream", return_value=stream):
            self.app.start_recording()
            self.app.stop_recording()
        self.assertIsNone(self.app.stream)
        self.assertFalse(self.app.recording)

    def test_timer_and_key_release_schedule_only_one_transcription(self):
        self.app.recording = True
        self.app.stream = Mock()
        self.app.recording_started_at = time.time() - 1
        self.app.audio_queue.put(np.zeros((16000, 1), dtype=np.float32))
        worker = Mock()
        with patch("src.dictation_app.threading.Thread", return_value=worker):
            self.app.stop_recording()
            self.assertTrue(self.app.transcribing)
            self.app.stop_recording()
        worker.start.assert_called_once()

    def test_newline_only_reaches_paste(self):
        self.app.transcribe_local = Mock(return_value="Nueva línea.")
        self.app.paste_text = Mock()
        with patch("src.dictation_app.write_wav"), patch("src.dictation_app.Path.unlink"):
            self.app.transcribe_and_paste(np.zeros((16000, 1), dtype=np.float32))
        self.app.paste_text.assert_called_once_with("\n")
        self.assertFalse(self.app.transcribing)

    def test_local_help_matches_disabled_toggle_and_limit(self):
        config = {**self.app.config, "max_record_seconds": 45, "hotkey": ["f8"]}
        text = usage_help_text(config)
        self.assertIn("Dictado local", text)
        self.assertIn("F8", text)
        self.assertIn("desactivado", text)
        self.assertIn("45 segundos", text)
        self.assertNotIn("API key validada", text)


if __name__ == "__main__":
    unittest.main()

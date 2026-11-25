from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

from app import create_app


class ApiTest(unittest.TestCase):
    def setUp(self):
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.config = {"TESTING": True, "DATABASE": Path(temporary_directory.name) / "history.sqlite3"}
        self.client = create_app(self.config).test_client()

    def test_history_persists_across_app_instances(self):
        response = self.client.post("/api/dtc", json={"code": " p0301 ", "make": "Hyundai", "year": "2024"})
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["result"]["code"], "P0301")
        self.assertTrue(payload["result"]["found"])
        self.assertEqual(payload["record"]["vehicle"], {"make": "Hyundai", "year": 2024})
        restarted = create_app(self.config).test_client()
        self.assertEqual(restarted.get("/api/history").get_json()["items"], [payload["record"]])

    def test_invalid_input_does_not_create_history(self):
        invalid_requests = [
            ("/api/diagnose", {"symptoms": "", "year": "2024"}),
            ("/api/diagnose", {"symptoms": "Неровный холостой ход", "year": True}),
            ("/api/dtc", {"code": "unknown"}),
            ("/api/fuel", {"actual": "NaN", "baseline": 10}),
        ]
        for route, data in invalid_requests:
            with self.subTest(route=route, data=data):
                response = self.client.post(route, json=data)
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertTrue(response.get_json()["error"])
        self.assertEqual(self.client.get("/api/history").get_json()["items"], [])

    def test_fuel_uses_matching_vehicle_history(self):
        for make, actual in (("Hyundai", 8), ("Haval", 15), ("Hyundai", 10)):
            response = self.client.post("/api/fuel", json={"actual": actual, "baseline": 9, "make": make})
            self.assertEqual(response.status_code, 200, response.get_json())
        response = self.client.post("/api/fuel", json={"actual": "13,5", "baseline": 9, "make": "HYUNDAI"})
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["record"]["input"]["actual"], 13.5)
        self.assertEqual(payload["result"]["delta_pct"], 50.0)
        self.assertIn(8, payload["result"]["history"])
        self.assertIn(10, payload["result"]["history"])
        self.assertNotIn(15, payload["result"]["history"])

    def test_pcm_upload_is_analyzed_without_storing_the_file(self):
        data = BytesIO()
        with wave.open(data, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(8000)
            frames = struct.pack("<8h", 0, 1000, 1500, 1000, 0, -1000, -1500, -1000)
            recording.writeframes(frames * 2000)
        data.seek(0)
        response = self.client.post("/api/audio", data={"file": (data, "engine.wav")})
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["result"]["duration_seconds"], 2.0)
        self.assertEqual(payload["record"]["input"], {"filename": "engine.wav"})

    def test_demo_wav_upload_larger_than_a_multipart_chunk(self):
        sample = Path(__file__).resolve().parents[1] / "static" / "sample-signal.wav"
        with sample.open("rb") as handle:
            response = self.client.post("/api/audio", data={"file": (handle, sample.name)})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["result"]["dominant_frequency_hz"], 86.0)

    def test_prediction_reuses_only_matching_saved_telemetry(self):
        header = "timestamp,rpm,coolant_c,speed_kmh\n"
        rows = [f"2026-01-01T10:00:{step * 10:02d},1200,{76 + step / 2},50\n" for step in range(6)]
        content = BytesIO((header + "".join(rows)).encode("utf-8"))
        response = self.client.post("/api/telemetry", data={"file": (content, "log.csv"), "make": "Hyundai"})
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(len(payload["result"]["samples"]), 6)
        self.assertNotIn("samples", payload["record"]["result"])

        wrong_vehicle = self.client.post("/api/prediction", json={"make": "Haval"})
        self.assertEqual(wrong_vehicle.status_code, 400, wrong_vehicle.get_json())
        prediction = self.client.post("/api/prediction", json={}).get_json()
        self.assertEqual(prediction["record"]["vehicle"], {"make": "Hyundai"})
        self.assertEqual(prediction["record"]["input"]["telemetry_id"], payload["record"]["id"])
        self.assertEqual(prediction["result"]["slope_c_per_min"], 3.0)


if __name__ == "__main__":
    unittest.main()

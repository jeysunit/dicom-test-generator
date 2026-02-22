"""Patient master data loading service."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.exceptions import FileReadError, PatientDataInvalidError, PatientNotFoundError
from app.core.models import Patient


class PatientLoaderService:
    """患者マスターデータの読み込みサービス."""

    def __init__(self) -> None:
        self._project_root = Path(__file__).resolve().parents[2]
        self._patient_master_path = self._project_root / "data" / "patients_master.yaml"

    def load_all(self) -> list[Patient]:
        """患者マスターの全患者を返す."""
        data = self._load_master_data()
        patients_raw = data.get("patients", [])
        if not isinstance(patients_raw, list):
            raise PatientDataInvalidError("'patients' must be a list")

        try:
            return [Patient.model_validate(item) for item in patients_raw]
        except ValidationError as exc:
            raise PatientDataInvalidError(f"Failed to validate patient master data: {exc}") from exc

    def find_by_id(self, patient_id: str) -> Patient:
        """患者IDから患者情報を検索して返す."""
        for patient in self.load_all():
            if patient.patient_id == patient_id:
                return patient
        raise PatientNotFoundError(patient_id)

    def _load_master_data(self) -> dict:
        path = self._patient_master_path
        if not path.exists():
            raise FileReadError(str(path), "File does not exist")

        try:
            with path.open("r", encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp)
        except yaml.YAMLError as exc:
            raise PatientDataInvalidError(f"Failed to parse patient master YAML: {exc}") from exc
        except OSError as exc:
            raise FileReadError(str(path), str(exc)) from exc

        if not isinstance(loaded, dict):
            raise PatientDataInvalidError("Patient master root must be a mapping")
        return loaded


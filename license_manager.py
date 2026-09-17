import base64
import hashlib
import json
import os
import platform
import uuid
from datetime import datetime, timezone

from qgis.PyQt.QtCore import QSettings, QStandardPaths
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox

PRODUCT = "GISDataInspector"
TRIAL_HOURS = 24
RSA_N = 21514663369000084018316754234422623902455242756814971820422956510757648574522056230174968711601025343143944951687107116995911873456193505096380850501103862845965864219927879723596716028992681724764068281004978794621478589600501295265221391078021374826561263454876414871885207162297048508768064762705073330321976256771664357667802408939180851842928467325152353547284653112047095506338104517937815319442544010234283561168084742585042186878317451318730943309908148856573838713036211141416751497035409537267911414131244115659253556230888547812442822800803676376372084099446917090381894342758454026528651998617492970014471
RSA_E = 65537


def _b64u(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_dec(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def machine_id():
    parts = [platform.system(), platform.machine(), platform.node()]
    try:
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\Cryptography") as key:
                parts.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
        except Exception:
            pass
    return hashlib.sha256("|".join(parts).encode("utf-8", "ignore")).hexdigest().upper()


def _state_path():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.expanduser("~")
    folder = os.path.join(base, PRODUCT)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, ".trial_state.json")


def _read_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_state(state):
    path = _state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def _rsa_verify(message, signature):
    # PKCS#1 v1.5 SHA-256 verification without external crypto packages.
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(message).digest()
    k = (RSA_N.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= RSA_N:
        return False
    em = pow(s, RSA_E, RSA_N).to_bytes(k, "big")
    sep = em.find(b"\x00", 2)
    if not em.startswith(b"\x00\x01") or sep < 10:
        return False
    return em[sep + 1:] == digest_info


class LicenseManager:
    def __init__(self, parent=None):
        self.parent = parent
        self.settings = QSettings("GISInTelugu", PRODUCT)
        self.mid = machine_id()

    def status(self):
        key = self.settings.value("license/key", "", type=str).strip()
        if key:
            ok, msg = self._validate_license(key)
            if ok:
                return True, "licensed", msg

        now = _utc_now()
        state = _read_state()
        first_text = state.get("first_run") or self.settings.value("trial/first_run", "", type=str)
        last_text = state.get("last_seen") or self.settings.value("trial/last_seen", "", type=str)

        if not first_text:
            first_text = _iso(now)
            state = {"first_run": first_text, "last_seen": first_text}
            _write_state(state)
            self.settings.setValue("trial/first_run", first_text)
            self.settings.setValue("trial/last_seen", first_text)
            self.settings.sync()
            return True, "trial", "24-hour trial started now."

        try:
            first = _parse_iso(first_text)
            last = _parse_iso(last_text or first_text)
        except Exception:
            return False, "expired", "Trial state is invalid."

        if now.timestamp() < last.timestamp() - 300:
            return False, "clock", "System clock rollback detected."

        if now > last:
            state["last_seen"] = _iso(now)
            _write_state(state)
            self.settings.setValue("trial/last_seen", state["last_seen"])
            self.settings.sync()

        remaining = int(TRIAL_HOURS * 3600 - (now - first).total_seconds())
        if remaining > 0:
            h, rem = divmod(remaining, 3600)
            m = rem // 60
            return True, "trial", f"Trial active — approximately {h}h {m}m remaining."
        return False, "expired", "The 24-hour trial has expired."

    def _validate_license(self, key):
        try:
            parts = key.split(".")
            if len(parts) != 2:
                return False, "Invalid license format."
            payload_bytes = _b64u_dec(parts[0])
            signature = _b64u_dec(parts[1])
            if not _rsa_verify(payload_bytes, signature):
                return False, "Invalid license signature."
            payload = json.loads(payload_bytes.decode("utf-8"))
            if payload.get("product") != PRODUCT:
                return False, "License is for another product."
            if str(payload.get("machine_id", "")).upper() != self.mid:
                return False, "License is not valid for this computer."
            expires = payload.get("expires_at")
            if expires and _utc_now() > _parse_iso(expires):
                return False, "License has expired."
            return True, "License activated successfully."
        except Exception as exc:
            return False, f"License validation failed: {exc}"

    def require_access(self):
        allowed, _mode, _message = self.status()
        return allowed or self.show_license_dialog()

    def show_license_dialog(self):
        allowed, mode, message = self.status()
        if allowed:
            QMessageBox.information(self.parent, "GIS Data Inspector", message)
            return True
        prompt = ("Your 24-hour trial has expired.\n\nMachine ID:\n" + self.mid +
                  "\n\nPaste your license key below:")
        key, ok = QInputDialog.getText(self.parent, "GIS Data Inspector — License", prompt)
        if not ok or not key.strip():
            return False
        valid, validation_message = self._validate_license(key.strip())
        if not valid:
            QMessageBox.critical(self.parent, "GIS Data Inspector — License", validation_message)
            return False
        self.settings.setValue("license/key", key.strip())
        self.settings.sync()
        QMessageBox.information(self.parent, "GIS Data Inspector — License", validation_message)
        return True

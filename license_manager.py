import base64
import hashlib
import json
import os
import platform
import re
import subprocess
import uuid
from datetime import datetime, timezone

from qgis.PyQt.QtCore import QSettings, QStandardPaths
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox

PRODUCT = "GISDataInspector"
TRIAL_HOURS = 24
# Public RSA key only. The private signing key is never shipped with the plugin.
RSA_N = 22547485548353752942725971494942334511080071135664926281375140654058768841846279060272427004685155569995868575412638134775593743879891978919011539587585655670294343100865696848050369601569271210583451734777504178220012329761472700198941206498668888452097233558990016252181069681541851014715294694867278371359608669159390818429078747264065316224808780699375289401002636418594270113936013974555051183582055084406901063863598562923634115280260557600038771839024267825397177402632948551730008822683796277089625874033818139391209942771960598423961976697578396542994494322744027447861401215814511394283848544247
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
    raw = "|".join(parts).encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest().upper()


def _state_path():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.expanduser("~")
    folder = os.path.join(base, "GISDataInspector")
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
    # PKCS#1 v1.5 SHA-256 verification, implemented without external packages.
    digest_info_prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    expected = digest_info_prefix + hashlib.sha256(message).digest()
    k = (RSA_N.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= RSA_N:
        return False
    em = pow(s, RSA_E, RSA_N).to_bytes(k, "big")
    prefix = b"\\x00\\x01"
    sep = em.find(b"\\x00", 2)
    if not em.startswith(prefix) or sep < 10:
        return False
    return em[sep + 1:] == expected


class LicenseManager:
    def __init__(self, parent=None):
        self.parent = parent
        self.settings = QSettings("GISInTelugu", PRODUCT)
        self.mid = machine_id()

    def status(self):
        # Returns (allowed, mode, message).
        license_key = self.settings.value("license/key", "", type=str).strip()
        if license_key:
            ok, message = self._validate_license(license_key)
            if ok:
                return True, "licensed", message

        now = _utc_now()
        state = _read_state()
        first_text = state.get("first_run") or self.settings.value("trial/first_run", "", type=str)
        last_text = state.get("last_seen") or self.settings.value("trial/last_seen", "", type=str)

        if not first_text:
            first_text = _iso(now)
            state["first_run"] = first_text
            state["last_seen"] = first_text
            _write_state(state)
            self.settings.setValue("trial/first_run", first_text)
            self.settings.setValue("trial/last_seen", first_text)
            self.settings.sync()
            return True, "trial", "24-hour trial started now."

        try:
            first = _parse_iso(first_text)
            last = _parse_iso(last_text) if last_text else first
        except Exception:
            return False, "expired", "Trial state is invalid."

        # Detect meaningful system clock rollback.
        if now.timestamp() < last.timestamp() - 300:
            return False, "clock", "System clock rollback detected."

        if now > last:
            state["last_seen"] = _iso(now)
            _write_state(state)
            self.settings.setValue("trial/last_seen", state["last_seen"])
            self.settings.sync()

        elapsed = (now - first).total_seconds()
        remaining = max(0, int(TRIAL_HOURS * 3600 - elapsed))
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            return True, "trial", f"Trial active — approximately {hours}h {minutes}m remaining."

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
            if payload.get("machine_id", "").upper() != self.mid:
                return False, "License is not valid for this computer."
            expires = payload.get("expires_at")
            if expires:
                if _utc_now() > _parse_iso(expires):
                    return False, "License has expired."
            return True, "License activated successfully."
        except Exception as exc:
            return False, f"License validation failed: {exc}"

    def show_license_dialog(self):
        allowed, mode, message = self.status()
        if allowed:
            if mode == "trial":
                QMessageBox.information(self.parent, "GIS Data Inspector — Trial", message)
            else:
                QMessageBox.information(self.parent, "GIS Data Inspector — License", message)
            return True

        prompt = (
            "Your 24-hour trial has expired.\n\n"
            "Machine ID:\n" + self.mid +
            "\n\nPaste your license key below."
        )
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

    def require_access(self):
        allowed, mode, message = self.status()
        if allowed:
            return True
        return self.show_license_dialog()

    def machine_id_text(self):
        return self.mid

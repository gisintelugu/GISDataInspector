import argparse, base64, json
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def b64u(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

p = argparse.ArgumentParser(description="Generate GIS Data Inspector licenses")
p.add_argument("--machine-id", required=True)
p.add_argument("--days", type=int, default=365)
p.add_argument("--customer", default="")
p.add_argument("--private-key", required=True)
a = p.parse_args()

key = serialization.load_pem_private_key(open(a.private_key, "rb").read(), password=None)
now = datetime.now(timezone.utc).replace(microsecond=0)
payload = {
    "product": "GISDataInspector",
    "machine_id": a.machine_id.strip().upper(),
    "issued_at": now.isoformat(),
    "customer": a.customer,
    "expires_at": (now + timedelta(days=a.days)).isoformat() if a.days > 0 else None,
}
data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
signature = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
print(b64u(data) + "." + b64u(signature))

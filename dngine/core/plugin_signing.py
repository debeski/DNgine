from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


MANIFEST_FILENAME = "manifest.json"
SIGNATURE_FILENAME = "signature.json"


@dataclass(frozen=True)
class SignedPackageVerification:
    package_id: str
    package_version: str
    signer: str
    manifest: dict[str, object]


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_trusted_signers(path: Path) -> dict[str, Ed25519PublicKey]:
    signers_path = Path(path)
    if not signers_path.exists():
        return {}
    try:
        payload = json.loads(signers_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    signers: dict[str, Ed25519PublicKey] = {}
    for entry in payload.get("signers", []):
        if not isinstance(entry, dict):
            continue
        signer_id = str(entry.get("signer", "")).strip()
        public_key = str(entry.get("public_key", "")).strip()
        if not signer_id or not public_key:
            continue
        try:
            key = serialization.load_pem_public_key(public_key.encode("utf-8"))
        except Exception:
            continue
        if isinstance(key, Ed25519PublicKey):
            signers[signer_id] = key
    return signers


def load_private_signing_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The private signing key must be an Ed25519 key.")
    return key


def sign_manifest(manifest: dict[str, object], *, signer: str, private_key: Ed25519PrivateKey) -> dict[str, object]:
    signature = private_key.sign(_canonical_json_bytes(manifest))
    return {
        "version": 1,
        "algorithm": "ed25519",
        "signer": signer,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def verify_manifest_signature(
    manifest: dict[str, object],
    signature_payload: dict[str, object],
    *,
    trusted_signers: dict[str, Ed25519PublicKey],
) -> str:
    signer = str(signature_payload.get("signer", "")).strip()
    if not signer:
        raise ValueError("Signed package metadata is missing a signer id.")
    public_key = trusted_signers.get(signer)
    if public_key is None:
        raise ValueError(f"Signer '{signer}' is not trusted.")
    signature_text = str(signature_payload.get("signature", "")).strip()
    if not signature_text:
        raise ValueError("Signed package metadata is missing the signature payload.")
    try:
        signature = base64.b64decode(signature_text.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("Signed package signature is invalid.") from exc
    public_key.verify(signature, _canonical_json_bytes(manifest))
    return signer


def _verify_manifest_files(
    manifest: dict[str, object],
    *,
    read_bytes,
) -> None:
    files = manifest.get("files", [])
    if not isinstance(files, list) or not files:
        raise ValueError("Signed package manifest is missing file entries.")
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("Signed package file metadata is invalid.")
        relative_path = str(entry.get("path", "")).replace("\\", "/").strip()
        expected_hash = str(entry.get("sha256", "")).strip()
        if not relative_path or not expected_hash:
            raise ValueError("Signed package file metadata is incomplete.")
        payload = read_bytes(relative_path)
        if _sha256_bytes(payload) != expected_hash:
            raise ValueError(f"Signed package file verification failed for '{relative_path}'.")


def verify_signed_archive(archive_path: Path, signers_path: Path) -> SignedPackageVerification:
    trusted_signers = load_trusted_signers(signers_path)
    with zipfile.ZipFile(archive_path, "r") as archive:
        try:
            manifest = json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
            signature_payload = json.loads(archive.read(SIGNATURE_FILENAME).decode("utf-8"))
        except KeyError as exc:
            raise ValueError("Signed package archive is missing manifest or signature data.") from exc
        signer = verify_manifest_signature(manifest, signature_payload, trusted_signers=trusted_signers)
        _verify_manifest_files(
            manifest,
            read_bytes=lambda relative_path: archive.read(relative_path),
        )
    return SignedPackageVerification(
        package_id=str(manifest.get("package_id", "")).strip(),
        package_version=str(manifest.get("package_version", "")).strip(),
        signer=signer,
        manifest=manifest,
    )


def verify_installed_signed_package(package_root: Path, signers_path: Path) -> SignedPackageVerification:
    package_root = Path(package_root)
    manifest_path = package_root / MANIFEST_FILENAME
    signature_path = package_root / SIGNATURE_FILENAME
    if not manifest_path.exists() or not signature_path.exists():
        raise ValueError("Signed package install is missing manifest or signature files.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    signature_payload = json.loads(signature_path.read_text(encoding="utf-8"))
    signer = verify_manifest_signature(manifest, signature_payload, trusted_signers=load_trusted_signers(signers_path))
    _verify_manifest_files(
        manifest,
        read_bytes=lambda relative_path: (package_root / relative_path).read_bytes(),
    )
    return SignedPackageVerification(
        package_id=str(manifest.get("package_id", "")).strip(),
        package_version=str(manifest.get("package_version", "")).strip(),
        signer=signer,
        manifest=manifest,
    )

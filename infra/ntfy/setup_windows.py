"""Configure a local, private ntfy server. Run with the project's Python environment."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import string
import subprocess
import time
from urllib.request import urlopen
import zipfile

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from dotenv import dotenv_values, set_key
import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'artifacts/ntfy-runtime'
PRIVATE = RUNTIME / 'private'
VERSION = '2.34.0'
ARCHIVE = f'ntfy_{VERSION}_windows_amd64.zip'
BINARY = RUNTIME / f'ntfy_{VERSION}_windows_amd64/ntfy.exe'
CA = RUNTIME / 'niannian-ntfy-ca.crt'


def protect(path, directory=False):
    output = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
    sid = next(csv.reader(output.strip().splitlines()))[-1]
    assert re.fullmatch(r'S-1-[0-9-]+', sid)
    rights = '(OI)(CI)F' if directory else 'F'
    subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
        f'*{sid}:{rights}', f'*S-1-5-18:{rights}'], check=True, capture_output=True)


def download():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    release = f'https://github.com/binwiederhier/ntfy/releases/download/v{VERSION}/'
    for name in (ARCHIVE, 'checksums.txt'):
        target = RUNTIME / name
        if not target.exists():
            with urlopen(release + name, timeout=60) as response:
                target.write_bytes(response.read())
    entries = [line.split() for line in (RUNTIME / 'checksums.txt').read_text().splitlines()]
    expected = next(digest for digest, name in entries if name == ARCHIVE)
    assert hashlib.sha256((RUNTIME / ARCHIVE).read_bytes()).hexdigest() == expected, 'Archive checksum mismatch'
    with zipfile.ZipFile(RUNTIME / ARCHIVE) as archive:
        member, = [name for name in archive.namelist() if Path(name).name == 'ntfy.exe']
        binary = archive.read(member)
    BINARY.parent.mkdir(exist_ok=True)
    if not BINARY.exists() or hashlib.sha256(BINARY.read_bytes()).digest() != hashlib.sha256(binary).digest():
        BINARY.write_bytes(binary)


def password_hash(password):
    # Send literal LF: Windows text pipes insert CR, which ntfy treats as part of the password.
    result = subprocess.run([str(BINARY), 'user', 'hash'], input=(password + '\n' + password + '\n').encode(),
        capture_output=True, timeout=15, check=True)
    match = re.search(r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}', result.stdout.decode('utf-8'))
    if not match:
        raise RuntimeError('ntfy did not return a password hash')
    return match.group()


def certificates(host):
    key_path = PRIVATE / 'ca-key.pem'
    now = datetime.now(timezone.utc)
    if key_path.exists() and CA.exists():
        root_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        root = x509.load_pem_x509_certificate(CA.read_bytes())
    else:
        root_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'NianNian Local Push CA')])
        root = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .sign(root_key, hashes.SHA256()))
        key_path.write_bytes(root_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        CA.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'NianNian Private Push')]))
        .issuer_name(root.subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
            x509.IPAddress(ipaddress.ip_address('127.0.0.1')), x509.IPAddress(ipaddress.ip_address(host))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(root_key, hashes.SHA256()))
    (PRIVATE / 'server-key.pem').write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (PRIVATE / 'server.crt').write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + CA.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='This computer IPv4 address reachable by the phone')
    parser.add_argument('--port', type=int, default=8443)
    args = parser.parse_args()
    assert os.name == 'nt' and 1024 <= args.port <= 65535
    ipaddress.IPv4Address(args.host)
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise RuntimeError('Port already used; stop the existing ntfy process before reconfiguration')
    download()
    PRIVATE.mkdir(exist_ok=True)
    protect(PRIVATE, directory=True)
    secrets_file = PRIVATE / 'secrets.json'
    if secrets_file.exists():
        credentials = json.loads(secrets_file.read_text(encoding='utf-8'))
    else:
        credentials = dict(publisher_password=secrets.token_urlsafe(32), subscriber_password=secrets.token_urlsafe(24),
            publisher_token='tk_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(29)),
            topic='family-' + secrets.token_hex(16))
        secrets_file.write_text(json.dumps(credentials), encoding='utf-8')
    certificates(args.host)
    base_url = f'https://{args.host}:{args.port}'
    config = {
        'base-url': base_url, 'listen-http': '-', 'listen-https': f'0.0.0.0:{args.port}',
        'key-file': str(PRIVATE / 'server-key.pem'), 'cert-file': str(PRIVATE / 'server.crt'),
        'auth-file': str(PRIVATE / 'auth.db'), 'auth-default-access': 'deny-all',
        'auth-users': [f"niannian-publisher:{password_hash(credentials['publisher_password'])}:user",
            f"niannian-family:{password_hash(credentials['subscriber_password'])}:user"],
        'auth-access': [f"niannian-publisher:{credentials['topic']}:wo", f"niannian-family:{credentials['topic']}:ro"],
        'auth-tokens': [f"niannian-publisher:{credentials['publisher_token']}:NianNian backend"],
        'cache-file': str(PRIVATE / 'cache.db'), 'cache-duration': '1h',
        'enable-login': True, 'enable-signup': False, 'log-level': 'error',
    }
    config_path = PRIVATE / 'server.yml'
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    connection = dict(server=base_url, username='niannian-family', password=credentials['subscriber_password'],
        topic=credentials['topic'], subscription_url=f"ntfy://{args.host}:{args.port}/{credentials['topic']}",
        ca_certificate=str(CA), instructions='Import the CA in ntfy Settings > Advanced > Manage certificates; add this account, then subscribe with instant delivery.')
    (PRIVATE / 'phone-connection.json').write_text(json.dumps(connection, ensure_ascii=False, indent=2), encoding='utf-8')
    installed = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
        "if (Get-Service -Name NianNianNtfy -ErrorAction SilentlyContinue) { 'installed' }"],
        capture_output=True, text=True, check=True).stdout.strip() == 'installed'
    process = None
    if installed:
        subprocess.run(['powershell.exe', '-NoProfile', '-Command', 'Start-Service -Name NianNianNtfy'],
            capture_output=True, check=True)
    else:
        with (PRIVATE / 'stdout.log').open('ab') as out, (PRIVATE / 'stderr.log').open('ab') as err:
            process = subprocess.Popen([str(BINARY), 'serve', '--config', str(config_path)], cwd=RUNTIME,
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        (PRIVATE / 'pid').write_text(str(process.pid))
    context = ssl.create_default_context(cafile=str(CA))
    with httpx.Client(verify=context, trust_env=False, timeout=2) as client:
        for _ in range(40):
            if process is not None and process.poll() is not None:
                raise RuntimeError('ntfy exited; inspect its private error log')
            try:
                if client.get(f'https://127.0.0.1:{args.port}/v1/health').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError('ntfy readiness timed out')
        account = ('niannian-family', credentials['subscriber_password'])
        check = client.get(f"https://127.0.0.1:{args.port}/{credentials['topic']}/json?poll=1", auth=account)
        if check.status_code != 200:
            raise RuntimeError('Phone account authentication failed')
    env_path = ROOT / '.env'
    previous = dotenv_values(env_path)
    updates = dict(NOTIFICATION_EXTERNAL_ENABLED='true', NOTIFICATION_PUSH_PROVIDER='ntfy',
        NTFY_BASE_URL=base_url, NTFY_CA_FILE=CA.as_posix(), PUSH_API_KEY=credentials['publisher_token'])
    if not previous.get('CONTACT_ENCRYPTION_KEY'):
        updates['CONTACT_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    for key, value in updates.items():
        set_key(str(env_path), key, value)
    protect(env_path)
    print(f'ntfy {VERSION} ready at {base_url}; TLS verification enabled')
    print('Publisher: write-only; phone account: read-only; anonymous access: denied')
    print('Backend .env updated; phone credentials remain in the private runtime directory')


if __name__ == '__main__':
    main()

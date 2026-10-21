from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from netpilot.main import create_app
from netpilot.config import Settings

ROOT=Path(__file__).resolve().parents[1]


def test_fixed_bundle_metadata_and_readonly_wrapper(tmp_path):
    app=create_app(Settings(_env_file=None,rag_enabled=False,diagnosis_db_path=tmp_path/"assets.db"))
    with TestClient(app) as client:
        metadata=client.get("/api/client-tools/windows").json()
        bundle=client.get("/static/client-tools/netpilot-windows-check.zip")
        assert bundle.status_code == 200 and "attachment" in bundle.headers["content-disposition"]
        assert sha256(bundle.content).hexdigest() == metadata["sha256"]["netpilot-windows-check.zip"]
        with ZipFile(BytesIO(bundle.content)) as archive:
            assert set(archive.namelist()) == {"client_diagnostic_windows.ps1","run_client_diagnostic_windows.cmd"}
            for name in archive.namelist():
                assert archive.read(name) == (ROOT/"scripts"/name).read_bytes()
                assert sha256(archive.read(name)).hexdigest() == metadata["sha256"][name]
        assert client.get("/api/client-tools/windows/source").text == (ROOT/"scripts/client_diagnostic_windows.ps1").read_text(encoding="utf-8")
        assert client.get("/static/client-tools/client_diagnostic_windows.ps1").content == (ROOT/"scripts/client_diagnostic_windows.ps1").read_bytes()
        assert client.get("/static/client-tools/run_client_diagnostic_windows.cmd").content == (ROOT/"scripts/run_client_diagnostic_windows.cmd").read_bytes()
    wrapper=(ROOT/"scripts/run_client_diagnostic_windows.cmd").read_text().casefold()
    assert 'powershell.exe -nologo -noprofile -file "%~dp0client_diagnostic_windows.ps1"' in wrapper
    for forbidden in ["executionpolicy","bypass","runas","invoke-webrequest","invoke-restmethod","http://","https://","set-net","set-dns","reg add","reg delete","curl","bitsadmin"]:
        assert forbidden not in wrapper
    assert metadata["snapshot_schema_version"] == 1

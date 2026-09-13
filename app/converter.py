import asyncio
import shutil
import subprocess
from pathlib import Path

from app.config import LIBREOFFICE_CONCURRENCY

_semaphore = asyncio.Semaphore(LIBREOFFICE_CONCURRENCY)

# (#7) Disables macro execution entirely (security level 3 = "Very High" —
# no macros run, from any source, ever, with no prompt). Templates are
# fully user-authored and their contents aren't otherwise checked, so
# macros must never run during conversion.
_MACRO_SECURITY_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
  <prop oor:name="MacroSecurityLevel" oor:op="fuse">
   <value>3</value>
  </prop>
 </item>
</oor:items>
"""


async def convert_to_pdf(docx_path: str, guid: str) -> str:
    async with _semaphore:
        return await asyncio.to_thread(_convert_sync, docx_path, guid)


def _prepare_locked_down_profile(user_install: str) -> None:
    user_dir = Path(user_install) / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "registrymodifications.xcu").write_text(_MACRO_SECURITY_XCU)


def _convert_sync(docx_path: str, guid: str) -> str:
    user_install = f"/tmp/lo_{guid}"
    try:
        _prepare_locked_down_profile(user_install)
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--norestore",
                f"-env:UserInstallation=file://{user_install}",
                "--convert-to", "pdf",
                "--outdir", "/tmp",
                docx_path,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PDF conversion failed: {exc}") from exc
    finally:
        shutil.rmtree(user_install, ignore_errors=True)

    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    if not Path(pdf_path).exists():
        raise RuntimeError("PDF conversion produced no output file")
    return pdf_path

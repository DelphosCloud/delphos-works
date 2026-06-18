import asyncio
import shutil
import subprocess
from pathlib import Path

_semaphore = asyncio.Semaphore(3)


async def convert_to_pdf(docx_path: str, guid: str) -> str:
    async with _semaphore:
        return await asyncio.to_thread(_convert_sync, docx_path, guid)


def _convert_sync(docx_path: str, guid: str) -> str:
    user_install = f"/tmp/lo_{guid}"
    try:
        subprocess.run(
            [
                "libreoffice",
                "--headless",
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

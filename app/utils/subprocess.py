import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class SubprocessResult:
    stdout: str
    stderr: str


async def run_subprocess(command: list[str], *, timeout_seconds: float) -> SubprocessResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(stderr or f"command failed with exit code {process.returncode}")
    return SubprocessResult(stdout=stdout, stderr=stderr)


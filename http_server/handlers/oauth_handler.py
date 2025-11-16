from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pathlib import Path
import typing as t


class OAuthHandler:
    @staticmethod
    def _static_file_path(filename: str) -> Path:
        base_dir = Path(__file__).resolve().parent.parent
        return base_dir / "webstatic" / filename

    @staticmethod
    def oauth_page() -> t.Union[FileResponse, Response]:
        """Serve OAuth HTML page"""
        file_path = OAuthHandler._static_file_path("oauth.html")
        if file_path.exists():
            return FileResponse(path=str(file_path), media_type="text/html")
        return Response(content="OAuth page not found", status_code=404)

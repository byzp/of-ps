from fastapi import Response
from fastapi.responses import FileResponse
import typing as t


class OAuthHandler:
    @staticmethod
    def oauth_page(WEBSTATIC_DIR) -> t.Union[FileResponse, Response]:
        file_path = WEBSTATIC_DIR / "oauth.html"
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                media_type="text/html",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return Response(content="OAuth page not found", status_code=404)

from flask import send_file, Response
import os


class OAuthHandler:
    @staticmethod
    def oauth_page():
        """Serve OAuth HTML page"""
        file_path = os.path.join("webstatic", "oauth.html")
        if os.path.exists(file_path):
            return send_file(file_path, mimetype="text/html")
        return Response(status=404)

    @staticmethod
    def security_code():
        """Serve security code image"""
        file_path = os.path.join("webstatic", "scode.png")
        if os.path.exists(file_path):
            return send_file(file_path, mimetype="image/png")
        return Response(status=404)

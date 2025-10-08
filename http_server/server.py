import logging
from flask import Flask, request, jsonify
import time

from config import Config
from http_server.handlers.oauth_handler import OAuthHandler
from http_server.handlers.login_handler import LoginHandler
from http_server.handlers.dispatch_handler import DispatchHandler

logger = logging.getLogger(__name__)


class HTTPServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        self.setup_middleware()

    def setup_routes(self):
        """Configure all routes"""

        # Static routes (use a named function instead of a lambda)
        def hello_world():
            return "hello, World"

        self.app.route('/')(hello_world)

        # Dispatch routes (these are methods on DispatchHandler)
        self.app.route('/dispatch/client_hot_update', methods=['POST'])(
            DispatchHandler.hot_update
        )
        self.app.route('/dispatch/region_info', methods=['POST'])(
            DispatchHandler.region_info
        )
        
        def a():
            return  '{"data":[]}'
        self.app.route('/dispatch/get_notice_url_list', methods=['POST'])(a)
        
        def b():
            t=time.time()
            return '{"data":[], "serverTime":'+str(round(t * 1000))+'}}'

        self.app.route('/dispatch/get_notice_list', methods=['POST'])(b)
        
        def c():
            t=time.time()
            return '{"code":0,"data":{"server_timestamp":'+str(round(t * 1000))+',"sync_batch_size":100,"sync_interval":90},"msg":""}'
        self.app.route('/config', methods=['GET'])(c)
        
        def d():
            return '{"code":0}'
        self.app.route('/sync', methods=['POST'])(d)

        # Use a named function that returns JSON instead of a lambda
        def get_login_url_list():
            # If you want valid JSON: return jsonify([])
            return jsonify({})

        self.app.route('/dispatch/get_login_url_list', methods=['POST'])(
            get_login_url_list
        )

        # OAuth routes
        self.app.route('/open/oauth', methods=['GET'])(
            OAuthHandler.oauth_page
        )
        self.app.route('/open/scode', methods=['GET'])(
            OAuthHandler.security_code
        )

        # Login routes
        self.app.route('/open/uloginDo', methods=['POST'])(
            LoginHandler.handle_login
        )

        # Use a named function instead of lambda for /login.success
        def login_success():
            # returning empty body and 500 status as in original code
            return ('', 500)

        self.app.route('/login.success', methods=['GET'])(
            login_success
        )

    def setup_middleware(self):
        """Setup middleware"""
        @self.app.after_request
        def log_request(response):
            logger.info(f"<< {request.method} {request.path} - {response.status_code}")
            return response

    def start(self):
        """Start HTTP server"""
        logger.info(f"HTTP server started at http://{Config.HTTP_HOST}:{Config.HTTP_PORT}/")
        self.app.run(
            host=Config.HTTP_HOST,
            port=Config.HTTP_PORT,
            debug=False,
            threaded=True
        )

"""Production entry point. Hosting platforms provide PORT at runtime."""
import os

import uvicorn


if __name__ == '__main__':
    uvicorn.run(
        'main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8000')),
        workers=1, proxy_headers=True,
        # WebSocket handshake/access logs can otherwise include query-string JWTs.
        access_log=False, log_level='warning',
        ws_max_size=768 * 1024, ws_max_queue=4, limit_concurrency=64,
        timeout_graceful_shutdown=120,
    )

"""HTTP layer. Bodies are read as raw JSON so FastAPI/pydantic never coerces "5" -> 5;
all business validation lives in the engine, one error shape for every failure."""
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import engine, present
from .storage import Store

NAME_MAX = 80
DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'


class ApiError(Exception):
    def __init__(self, status, code, message, index=None):
        self.status, self.code, self.message, self.index = status, code, message, index


def error(status, code, message, index=None):
    body = {'code': code, 'message': message}
    if index is not None:
        body['index'] = index
    return JSONResponse({'error': body}, status_code=status)


async def json_body(request):
    try:
        return json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        raise ApiError(422, 'INVALID_JSON', '请求体不是合法的 JSON') from None


def ops_of(body):
    if not isinstance(body, dict) or not isinstance(body.get('ops'), list):
        raise ApiError(422, 'INVALID_BODY', '请求体须为 {"ops": [...]}')
    return body['ops']


def create_app(db_path, snapshot_path=engine.SEED):
    snap = engine.load_snapshot(snapshot_path)
    store = Store(db_path)
    app = FastAPI(title='Portfolio Lab', version='0.1.0')

    @app.exception_handler(ApiError)
    async def _api_error(_, exc):
        return error(exc.status, exc.code, exc.message, exc.index)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_, exc):
        # e.g. /api/scenarios/abc — keep the single error shape for framework-level validation too
        return error(422, 'INVALID_REQUEST', '请求参数格式错误')

    def run(ops):
        try:
            state = engine.simulate(snap, ops)
        except engine.OpError as e:
            raise ApiError(422, e.code, e.message, e.index) from None
        return present.valuation(snap, engine.valuate(snap, state))

    original = lambda: present.valuation(snap, engine.valuate(snap, engine.original_state(snap)))

    def opened(s):
        if s['snapshot_id'] != snap.snapshot_id:
            raise ApiError(409, 'SNAPSHOT_MISMATCH', f"方案基于快照 {s['snapshot_id']}，当前快照为 {snap.snapshot_id}")
        return {**s, 'original': original(), 'simulated': run(s['ops'])}

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/portfolio')
    def portfolio():
        return {'portfolio': {'id': snap.portfolio_id, 'name': snap.name},
                'snapshot': {'id': snap.snapshot_id, 'at': snap.snapshot_at, 'currency': snap.currency},
                'thresholds': {'instrument': present.pct(snap.instrument_threshold),
                               'industry': present.pct(snap.industry_threshold)},
                'instruments': [{'symbol': i.symbol, 'name': i.name, 'price': present.money(i.price_cents)}
                                for i in snap.instruments.values()],
                'valuation': original()}

    @app.post('/api/simulate')
    async def simulate(request: Request):
        ops = ops_of(await json_body(request))
        return {'ops': ops, 'original': original(), 'simulated': run(ops)}

    @app.post('/api/scenarios', status_code=201)
    async def save(request: Request):
        body = await json_body(request)
        ops = ops_of(body)
        name = body.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= NAME_MAX:
            raise ApiError(422, 'INVALID_NAME', f'方案名去除首尾空格后须为 1–{NAME_MAX} 个字符')
        if not ops:
            raise ApiError(422, 'EMPTY_SCENARIO', '空方案不能保存，请至少添加一笔操作')
        run(ops)  # validate before persisting: invalid scenarios never reach the database
        return opened(store.add(name.strip(), snap.snapshot_id, ops))

    @app.get('/api/scenarios')
    def scenarios():
        return store.list()

    @app.get('/api/scenarios/{scenario_id}')
    def scenario(scenario_id: int):
        s = store.get(scenario_id)
        if s is None:
            raise ApiError(404, 'NOT_FOUND', f'方案 {scenario_id} 不存在')
        return opened(s)

    @app.api_route('/api/{rest:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def api_404(rest):
        raise ApiError(404, 'NOT_FOUND', f'接口 /api/{rest} 不存在')

    if (DIST / 'index.html').is_file() and (DIST / 'assets').is_dir():  # production: serve the built SPA
        app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

        @app.get('/{rest:path}', include_in_schema=False)
        def spa(rest: str):
            return FileResponse(DIST / 'index.html')

    return app

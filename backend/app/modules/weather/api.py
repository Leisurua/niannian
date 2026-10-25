from fastapi import APIRouter, Depends, Query, Request, Response

from app.modules.weather.service import WeatherService
from app.platform.authentication import current_identity

router = APIRouter(prefix='/v1/weather', tags=['Weather'])


@router.get('/cities', operation_id='searchWeatherCities')
async def cities(request: Request, response: Response, q: str = Query(min_length=2, max_length=80), actor=Depends(current_identity)):
    response.headers['Cache-Control'] = 'no-store'
    return await getattr(request.app.state, 'weather_service', WeatherService()).cities(q)


@router.get('/current', operation_id='getCurrentWeather')
async def current(request: Request, response: Response, city_id: int = Query(gt=0, le=2147483647), actor=Depends(current_identity)):
    response.headers['Cache-Control'] = 'no-store'
    return await getattr(request.app.state, 'weather_service', WeatherService()).current(city_id)

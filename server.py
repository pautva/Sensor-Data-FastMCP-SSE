#!/usr/bin/env python3

from fastmcp import FastMCP
import httpx
import json
import os
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

# BGS FROST Server API base URL
BGS_API_BASE = 'https://sensors.bgs.ac.uk/FROST-Server/v1.1'

mcp = FastMCP(
    name="BGS Sensor API",
    instructions="Provides access to the British Geological Survey FROST Server API for sensor data discovery and observations."
)

async def make_api_request(endpoint: str, params: Dict[str, Any] = None) -> Any:
    """Make request to BGS FROST API"""
    if params is None:
        params = {}
    
    url = f"{BGS_API_BASE}/{endpoint}"
    query_params = {}
    
    # Add common OData parameters
    if 'limit' in params:
        query_params['$top'] = str(params['limit'])
    if 'filter' in params:
        query_params['$filter'] = params['filter']
    if 'expand' in params:
        query_params['$expand'] = params['expand']
    if 'orderby' in params:
        query_params['$orderby'] = params['orderby']
    if 'select' in params:
        query_params['$select'] = params['select']
    if 'skip' in params:
        query_params['$skip'] = str(params['skip'])
    if 'count' in params:
        query_params['$count'] = 'true'
    
    # Format-specific parameters
    if params.get('format') == 'geojson':
        query_params['$resultFormat'] = 'GeoJSON'
    elif params.get('format') == 'csv':
        query_params['$resultFormat'] = 'CSV'
    
    if query_params:
        url += '?' + urlencode(query_params)
    
    headers = {
        'Accept': 'text/csv' if params.get('format') == 'csv' else 'application/json',
        'User-Agent': 'BGS-FastMCP-Server/1.0.0'
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        if params.get('format') == 'csv':
            return response.text
        
        return response.json()

def build_location_filter(location_filter: str) -> Optional[str]:
    """Build OData location filter"""
    if not location_filter or ',' not in location_filter:
        return None
    
    parts = location_filter.split(',')
    if len(parts) == 4:
        # Bounding box: lat1,lng1,lat2,lng2
        lat1, lng1, lat2, lng2 = [float(p.strip()) for p in parts]
        return f"geo.intersects(location, geography'POLYGON(({lng1} {lat1}, {lng2} {lat1}, {lng2} {lat2}, {lng1} {lat2}, {lng1} {lat1}))')"
    elif len(parts) == 3:
        # Point with radius: lat,lng,radius_km
        lat, lng, radius = [float(p.strip()) for p in parts]
        radius_meters = radius * 1000
        return f"geo.distance(location, geography'POINT({lng} {lat})') le {radius_meters}"
    
    return None

@mcp.tool
async def search(query: str) -> dict:
    """Search for sensors/things with the specified query.
    
    Args:
        query: Search query string
        
    Returns:
        Dictionary with 'results' key containing list of matching sensors.
        Each result includes id, title, text snippet, and URL.
    """
    if not query or not query.strip():
        return {"results": []}
    
    params = {
        'limit': 20,
        'expand': 'Locations,Datastreams',
        'count': True,
        'filter': f"(contains(tolower(name), '{query.lower()}') or contains(tolower(description), '{query.lower()}'))"
    }
    
    data = await make_api_request('Things', params)
    
    results = []
    for sensor in data.get('value', []):
        # Create text snippet from description and location
        location_info = ""
        if sensor.get('Locations'):
            loc = sensor['Locations'][0]
            coords = loc['location']['coordinates']
            location_info = f" Located at {loc['name']} ({coords[1]:.4f}, {coords[0]:.4f})"
        
        datastream_info = ""
        if sensor.get('Datastreams'):
            ds_count = len(sensor['Datastreams'])
            datastream_info = f" Has {ds_count} datastream{'s' if ds_count != 1 else ''}"
        
        text_snippet = f"{sensor['description'][:200]}{location_info}{datastream_info}"
        
        result = {
            "id": str(sensor['@iot.id']),
            "title": sensor['name'],
            "text": text_snippet,
            "url": f"{BGS_API_BASE}/Things({sensor['@iot.id']})"
        }
        results.append(result)
    
    return {"results": results}

@mcp.tool
async def fetch(id: str) -> dict:
    """Retrieve complete sensor details by ID.
    
    Args:
        id: Sensor ID (Thing ID) to fetch
        
    Returns:
        Complete sensor details with id, title, full text content, URL, and metadata
    """
    if not id:
        raise ValueError("Sensor ID is required")
    
    # Fetch sensor details with full expansion
    params = {
        'expand': 'Locations,Datastreams($expand=ObservedProperty,Sensor)'
    }
    
    data = await make_api_request(f'Things({id})', params)
    
    # Build comprehensive text content
    text_parts = []
    text_parts.append(f"Name: {data['name']}")
    text_parts.append(f"Description: {data['description']}")
    
    # Add location information
    if data.get('Locations'):
        for loc in data['Locations']:
            coords = loc['location']['coordinates']
            text_parts.append(f"\nLocation: {loc['name']}")
            text_parts.append(f"Coordinates: {coords[1]:.6f}, {coords[0]:.6f}")
            text_parts.append(f"Location Description: {loc['description']}")
    
    # Add datastream information
    if data.get('Datastreams'):
        text_parts.append(f"\nDatastreams ({len(data['Datastreams'])}):")  
        for ds in data['Datastreams']:
            text_parts.append(f"- {ds['name']}: {ds['description']}")
            unit = ds.get('unitOfMeasurement', {})
            if unit:
                text_parts.append(f"  Unit: {unit.get('name', 'N/A')} ({unit.get('symbol', '')})")
            
            # Add observed property info
            obs_prop = ds.get('ObservedProperty', {})
            if obs_prop:
                text_parts.append(f"  Observed Property: {obs_prop.get('name', 'N/A')}")
                text_parts.append(f"  Definition: {obs_prop.get('definition', 'N/A')}")
    
    # Add properties if available
    if data.get('properties'):
        text_parts.append(f"\nProperties: {json.dumps(data['properties'], indent=2)}")
    
    full_text = "\n".join(text_parts)
    
    result = {
        "id": str(data['@iot.id']),
        "title": data['name'],
        "text": full_text,
        "url": f"{BGS_API_BASE}/Things({data['@iot.id']})",
        "metadata": {
            "location_count": len(data.get('Locations', [])),
            "datastream_count": len(data.get('Datastreams', [])),
            "properties": data.get('properties')
        }
    }
    
    return result

# Additional tools for comprehensive API access
@mcp.tool
async def search_sensors(
    query: Optional[str] = None,
    limit: int = 20,
    filter: Optional[str] = None,
    location_filter: Optional[str] = None,
    format: str = 'json'
) -> str:
    """Alias for search function - search and discover sensors/things with advanced filtering"""
    return await search(query, limit, filter, location_filter, format)

@mcp.tool
async def get_sensor_details(
    sensor_id: str,
    include_datastreams: bool = True,
    include_locations: bool = True,
    include_observations: bool = False
) -> str:
    """Alias for fetch function - get comprehensive details about a specific sensor"""
    return await fetch(sensor_id, include_datastreams, include_locations, include_observations)

@mcp.tool
async def get_datastreams(
    sensor_id: Optional[str] = None,
    property_name: Optional[str] = None,
    unit_name: Optional[str] = None,
    limit: int = 20,
    filter: Optional[str] = None
) -> str:
    """Get datastreams with filtering and search capabilities"""
    endpoint = f'Things({sensor_id})/Datastreams' if sensor_id else 'Datastreams'
    
    params = {
        'limit': limit,
        'expand': 'Thing,ObservedProperty,Sensor',
        'count': True
    }
    
    filters = []
    
    if property_name:
        filters.append(f"contains(tolower(ObservedProperty/name), '{property_name.lower()}')")
    
    if unit_name:
        filters.append(f"contains(tolower(unitOfMeasurement/name), '{unit_name.lower()}')")
    
    if filter:
        filters.append(filter)
    
    if filters:
        params['filter'] = ' and '.join(filters)
    
    data = await make_api_request(endpoint, params)
    
    result = {
        'message': f"Found {len(data.get('value', []))} datastreams",
        'total_count': data.get('@iot.count', len(data.get('value', []))),
        'datastreams': [
            {
                'id': ds['@iot.id'],
                'name': ds['name'],
                'description': ds['description'],
                'unit': {
                    'name': ds.get('unitOfMeasurement', {}).get('name'),
                    'symbol': ds.get('unitOfMeasurement', {}).get('symbol'),
                    'definition': ds.get('unitOfMeasurement', {}).get('definition')
                },
                'observed_property': {
                    'id': ds.get('ObservedProperty', {}).get('@iot.id'),
                    'name': ds.get('ObservedProperty', {}).get('name'),
                    'definition': ds.get('ObservedProperty', {}).get('definition'),
                    'description': ds.get('ObservedProperty', {}).get('description')
                },
                'sensor': {
                    'id': ds.get('Thing', {}).get('@iot.id'),
                    'name': ds.get('Thing', {}).get('name')
                },
                'hardware': {
                    'id': ds.get('Sensor', {}).get('@iot.id'),
                    'name': ds.get('Sensor', {}).get('name'),
                    'description': ds.get('Sensor', {}).get('description')
                }
            } for ds in data.get('value', [])
        ]
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_observations(
    datastream_id: Optional[str] = None,
    sensor_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    format: str = 'json',
    aggregate: Optional[str] = None
) -> str:
    """Get observations with advanced time and value filtering"""
    if datastream_id:
        endpoint = f'Datastreams({datastream_id})/Observations'
    elif sensor_id:
        endpoint = f'Things({sensor_id})/Datastreams/Observations'
    else:
        endpoint = 'Observations'
    
    params = {
        'limit': limit,
        'orderby': 'phenomenonTime desc',
        'expand': 'Datastream($expand=ObservedProperty,Thing)',
        'count': True,
        'format': format
    }
    
    filters = []
    if start_time and end_time:
        filters.append(f'phenomenonTime ge {start_time} and phenomenonTime le {end_time}')
    elif start_time:
        filters.append(f'phenomenonTime ge {start_time}')
    elif end_time:
        filters.append(f'phenomenonTime le {end_time}')
    
    if filters:
        params['filter'] = ' and '.join(filters)
    
    data = await make_api_request(endpoint, params)
    
    if format == 'csv':
        return data
    
    observations = [
        {
            'id': obs['@iot.id'],
            'result': obs['result'],
            'phenomenon_time': obs['phenomenonTime'],
            'result_time': obs.get('resultTime'),
            'quality': obs.get('resultQuality'),
            'datastream': {
                'id': obs.get('Datastream', {}).get('@iot.id'),
                'name': obs.get('Datastream', {}).get('name'),
                'unit': obs.get('Datastream', {}).get('unitOfMeasurement'),
                'property': obs.get('Datastream', {}).get('ObservedProperty', {}).get('name'),
                'sensor_name': obs.get('Datastream', {}).get('Thing', {}).get('name')
            }
        } for obs in data.get('value', [])
    ]
    
    result = {
        'message': f"Found {len(observations)} observations",
        'total_count': data.get('@iot.count', len(observations)),
        'time_range': {
            'start': observations[-1]['phenomenon_time'] if observations else None,
            'end': observations[0]['phenomenon_time'] if observations else None
        },
        'aggregation': aggregate or 'none',
        'observations': observations
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_locations(
    bbox: Optional[str] = None,
    point: Optional[str] = None,
    limit: int = 20,
    format: str = 'geojson'
) -> str:
    """Get sensor locations with geographic filtering"""
    params = {
        'limit': limit,
        'expand': 'Things($expand=Datastreams)',
        'count': True,
        'format': format
    }
    
    filters = []
    
    if bbox:
        loc_filter = build_location_filter(bbox)
        if loc_filter:
            filters.append(loc_filter)
    
    if point:
        loc_filter = build_location_filter(point)
        if loc_filter:
            filters.append(loc_filter)
    
    if filters:
        params['filter'] = ' and '.join(filters)
    
    data = await make_api_request('Locations', params)
    
    if format == 'geojson':
        return json.dumps(data)
    
    result = {
        'message': f"Found {len(data.get('value', []))} locations",
        'total_count': data.get('@iot.count', len(data.get('value', []))),
        'locations': [
            {
                'id': loc['@iot.id'],
                'name': loc['name'],
                'description': loc['description'],
                'encoding_type': loc['encodingType'],
                'geometry': {
                    'type': loc['location']['type'],
                    'coordinates': loc['location']['coordinates']
                },
                'sensors': [
                    {
                        'id': thing['@iot.id'],
                        'name': thing['name'],
                        'description': thing['description'],
                        'datastream_count': len(thing.get('Datastreams', []))
                    } for thing in loc.get('Things', [])
                ]
            } for loc in data.get('value', [])
        ]
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_observed_properties(
    search: Optional[str] = None,
    limit: int = 50
) -> str:
    """Get all available measurement types/properties"""
    params = {
        'limit': limit,
        'count': True
    }
    
    if search:
        params['filter'] = f"contains(tolower(name), '{search.lower()}') or contains(tolower(description), '{search.lower()}')"
    
    data = await make_api_request('ObservedProperties', params)
    
    result = {
        'message': f"Found {len(data.get('value', []))} observed properties",
        'total_count': data.get('@iot.count', len(data.get('value', []))),
        'properties': [
            {
                'id': prop['@iot.id'],
                'name': prop['name'],
                'definition': prop['definition'],
                'description': prop['description']
            } for prop in data.get('value', [])
        ]
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_sensors_hardware(
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = 20
) -> str:
    """Get physical sensor hardware information"""
    params = {
        'limit': limit,
        'count': True
    }
    
    filters = []
    
    if manufacturer:
        filters.append(f"contains(tolower(name), '{manufacturer.lower()}') or contains(tolower(description), '{manufacturer.lower()}')")
    
    if model:
        filters.append(f"contains(tolower(name), '{model.lower()}') or contains(tolower(description), '{model.lower()}')")
    
    if filters:
        params['filter'] = ' and '.join(filters)
    
    data = await make_api_request('Sensors', params)
    
    result = {
        'message': f"Found {len(data.get('value', []))} sensors",
        'total_count': data.get('@iot.count', len(data.get('value', []))),
        'sensors': [
            {
                'id': sensor['@iot.id'],
                'name': sensor['name'],
                'description': sensor['description'],
                'encoding_type': sensor['encodingType'],
                'metadata': sensor['metadata']
            } for sensor in data.get('value', [])
        ]
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_features_of_interest(
    search: Optional[str] = None,
    geometry_type: Optional[str] = None,
    limit: int = 20
) -> str:
    """Get features of interest (what is being observed)"""
    params = {
        'limit': limit,
        'count': True
    }
    
    filters = []
    
    if search:
        filters.append(f"contains(tolower(name), '{search.lower()}') or contains(tolower(description), '{search.lower()}')")
    
    if geometry_type:
        filters.append(f"feature/type eq '{geometry_type}'")
    
    if filters:
        params['filter'] = ' and '.join(filters)
    
    data = await make_api_request('FeaturesOfInterest', params)
    
    result = {
        'message': f"Found {len(data.get('value', []))} features of interest",
        'total_count': data.get('@iot.count', len(data.get('value', []))),
        'features': [
            {
                'id': foi['@iot.id'],
                'name': foi['name'],
                'description': foi['description'],
                'encoding_type': foi['encodingType'],
                'geometry': {
                    'type': foi.get('feature', {}).get('type'),
                    'coordinates': foi.get('feature', {}).get('coordinates')
                }
            } for foi in data.get('value', [])
        ]
    }
    
    return json.dumps(result, indent=2)

@mcp.tool
async def get_api_info() -> str:
    """Get BGS FROST API capabilities and metadata"""
    try:
        data = await make_api_request('')
        
        result = {
            'api_info': {
                'base_url': BGS_API_BASE,
                'version': '1.1',
                'server_name': 'BGS FROST Server',
                'description': 'British Geological Survey Sensor Things API',
                'endpoints': [
                    {
                        'name': endpoint['name'],
                        'url': endpoint['url']
                    } for endpoint in data.get('value', [])
                ],
                'capabilities': data.get('serverSettings', {}).get('conformance', []),
                'mqtt_endpoints': data.get('serverSettings', {}).get(
                    'http://www.opengis.net/spec/iot_sensing/1.1/req/create-observations-via-mqtt/observations-creation',
                    {}
                ).get('endpoints', [])
            }
        }
        
        return json.dumps(result, indent=2)
    except:
        result = {
            'error': 'Could not retrieve API information',
            'base_url': BGS_API_BASE,
            'message': 'BGS FROST Server - British Geological Survey Sensor Things API'
        }
        
        return json.dumps(result, indent=2)

if __name__ == "__main__":
    import asyncio
    port = int(os.environ.get("PORT", 8000))
    # Use FastMCP's built-in SSE transport for ChatGPT compatibility
    mcp.run(transport="sse", host="0.0.0.0", port=port)
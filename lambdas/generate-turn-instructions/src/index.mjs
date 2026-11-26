/**
 * Lambda Function: generate-turn-instructions
 * 
 * Purpose: Generate turn-by-turn navigation instructions from a route geometry
 */

import https from 'https';

// Get Mapbox token from environment variable
const MAPBOX_TOKEN = process.env.MAPBOX_ACCESS_TOKEN;

// Debug logging
console.log('Mapbox token loaded:', MAPBOX_TOKEN ? `${MAPBOX_TOKEN.substring(0, 20)}... (${MAPBOX_TOKEN.length} chars)` : 'NOT SET');

/**
 * Make HTTPS request to Mapbox Directions API
 */
function httpsRequest(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode === 200) {
          resolve(JSON.parse(data));
        } else {
          reject(new Error(`Mapbox API error: ${res.statusCode} - Response: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

/**
 * Extract key points from route geometry for Mapbox API
 * FIXED: Ensures we never exceed 25 waypoints
 */
function extractKeyCoordinates(coordinates) {
  if (!coordinates || coordinates.length < 2) {
    throw new Error('Invalid route geometry: need at least 2 coordinates');
  }

  // Mapbox hard limit is 25 waypoints
  const MAX_WAYPOINTS = 25;

  // If route has fewer points than limit, use all of them
  if (coordinates.length <= MAX_WAYPOINTS) {
    return coordinates;
  }

  // Otherwise, sample evenly
  const points = [];
  
  // Always include first point
  points.push(coordinates[0]);
  
  // Calculate how many intermediate points we can include
  // -2 because we're reserving spots for first and last
  const intermediateCount = MAX_WAYPOINTS - 2;
  
  // Calculate step size to evenly sample the route
  const step = (coordinates.length - 1) / (intermediateCount + 1);
  
  // Sample intermediate points
  for (let i = 1; i <= intermediateCount; i++) {
    const index = Math.round(i * step);
    // Make sure we don't accidentally grab the last point
    if (index < coordinates.length - 1) {
      points.push(coordinates[index]);
    }
  }
  
  // Always include last point
  points.push(coordinates[coordinates.length - 1]);
  
  console.log(`Sampled ${coordinates.length} coordinates down to ${points.length} waypoints`);
  
  return points;
}

/**
 * Generate turn instructions from route geometry
 */
async function generateInstructions(routeGeometry) {
  if (!MAPBOX_TOKEN) {
    throw new Error('MAPBOX_ACCESS_TOKEN environment variable not set');
  }

  // Parse geometry if it's a string
  let geometry = routeGeometry;
  if (typeof routeGeometry === 'string') {
    geometry = JSON.parse(routeGeometry);
  }

  // Extract coordinates from geometry
  let coordinates;
  if (geometry.type === 'LineString') {
    coordinates = geometry.coordinates;
  } else if (geometry.type === 'Feature' && geometry.geometry?.type === 'LineString') {
    coordinates = geometry.geometry.coordinates;
  } else if (geometry.type === 'FeatureCollection' && geometry.features?.[0]?.geometry?.type === 'LineString') {
    coordinates = geometry.features[0].geometry.coordinates;
  } else {
    throw new Error('Invalid geometry type. Expected LineString or Feature with LineString geometry');
  }

  // Extract key coordinates for the API call
  const points = extractKeyCoordinates(coordinates);
  
  // Build Mapbox Directions API URL
  const coordinatesString = points.map(p => `${p[0]},${p[1]}`).join(';');
  
  const url = `https://api.mapbox.com/directions/v5/mapbox/driving/${coordinatesString}` +
    `?geometries=geojson` +
    `&steps=true` +
    `&banner_instructions=true` +
    `&voice_instructions=true` +
    `&access_token=${MAPBOX_TOKEN}`;

  console.log(`Requesting directions for ${points.length} waypoints`);

  // Call Mapbox API
  const response = await httpsRequest(url);

  if (!response.routes || response.routes.length === 0) {
    throw new Error('No routes returned from Mapbox API');
  }

  const route = response.routes[0];
  const instructions = [];

  // Extract turn-by-turn instructions from legs
  if (route.legs) {
    for (const leg of route.legs) {
      if (leg.steps) {
        for (const step of leg.steps) {
          instructions.push({
            distance: step.distance,
            duration: step.duration,
            instruction: step.maneuver.instruction,
            maneuver: {
              type: step.maneuver.type,
              modifier: step.maneuver.modifier,
              location: step.maneuver.location,
              bearing_after: step.maneuver.bearing_after,
              bearing_before: step.maneuver.bearing_before
            },
            name: step.name,
            voiceInstructions: step.voiceInstructions?.map(vi => ({
              distanceAlongGeometry: vi.distanceAlongGeometry,
              announcement: vi.announcement,
              ssmlAnnouncement: vi.ssmlAnnouncement
            })) || []
          });
        }
      }
    }
  }

  console.log(`Generated ${instructions.length} turn instructions`);

  return instructions;
}

/**
 * Lambda handler
 */
export const handler = async (event) => {
  console.log('Event:', JSON.stringify(event, null, 2));

  try {
    // Parse request body
    let body;
    if (event.body) {
      body = typeof event.body === 'string' ? JSON.parse(event.body) : event.body;
    } else {
      body = event;
    }

    if (!body.routeGeometry) {
      return {
        statusCode: 400,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        },
        body: JSON.stringify({
          error: 'Missing required field: routeGeometry'
        })
      };
    }

    // Generate instructions
    const instructions = await generateInstructions(body.routeGeometry);

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({
        instructions: instructions,
        count: instructions.length
      })
    };

  } catch (error) {
    console.error('Error:', error);
    
    return {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({
        error: error.message,
        type: error.name
      })
    };
  }
};
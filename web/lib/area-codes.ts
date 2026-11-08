// US area code -> the metro it belongs to. Used to place a scam text on the map
// from its sender number. Area codes can be spoofed, so these origins are low confidence.
type Metro = { city: string; state: string; lat: number; lng: number };

const M = (city: string, state: string, lat: number, lng: number): Metro => ({ city, state, lat, lng });

const NYC = M('New York', 'NY', 40.7128, -74.006);
const LA = M('Los Angeles', 'CA', 34.0522, -118.2437);
const DAL = M('Dallas', 'TX', 32.7767, -96.797);
const HOU = M('Houston', 'TX', 29.7604, -95.3698);
const CHI = M('Chicago', 'IL', 41.8781, -87.6298);
const MIA = M('Miami', 'FL', 25.7617, -80.1918);
const ATL = M('Atlanta', 'GA', 33.749, -84.388);
const PHX = M('Phoenix', 'AZ', 33.4484, -112.074);
const BOS = M('Boston', 'MA', 42.3601, -71.0589);
const SF = M('San Francisco', 'CA', 37.7749, -122.4194);
const DC = M('Washington', 'DC', 38.9072, -77.0369);

const AREA_CODES: Record<string, Metro> = {
  // New York
  '212': NYC, '646': NYC, '332': NYC, '917': NYC, '718': NYC, '347': NYC, '929': NYC,
  '516': M('Long Island', 'NY', 40.7891, -73.135), '631': M('Long Island', 'NY', 40.7891, -73.135),
  '716': M('Buffalo', 'NY', 42.8864, -78.8784), '585': M('Rochester', 'NY', 43.1566, -77.6088),
  '201': M('Jersey City', 'NJ', 40.7178, -74.0431), '973': M('Newark', 'NJ', 40.7357, -74.1724),
  '215': M('Philadelphia', 'PA', 39.9526, -75.1652), '267': M('Philadelphia', 'PA', 39.9526, -75.1652),
  '412': M('Pittsburgh', 'PA', 40.4406, -79.9959),
  // New England
  '617': BOS, '857': BOS, '781': BOS, '508': M('Worcester', 'MA', 42.2626, -71.8023),
  '401': M('Providence', 'RI', 41.824, -71.4128), '860': M('Hartford', 'CT', 41.7658, -72.6734),
  '203': M('New Haven', 'CT', 41.3083, -72.9279),
  // Mid-Atlantic and Southeast
  '202': DC, '301': M('Silver Spring', 'MD', 38.9907, -77.0261), '410': M('Baltimore', 'MD', 39.2904, -76.6122),
  '703': M('Arlington', 'VA', 38.8816, -77.091), '571': M('Arlington', 'VA', 38.8816, -77.091),
  '757': M('Virginia Beach', 'VA', 36.8529, -75.978), '804': M('Richmond', 'VA', 37.5407, -77.436),
  '704': M('Charlotte', 'NC', 35.2271, -80.8431), '980': M('Charlotte', 'NC', 35.2271, -80.8431),
  '919': M('Raleigh', 'NC', 35.7796, -78.6382), '843': M('Charleston', 'SC', 32.7765, -79.9311),
  '404': ATL, '470': ATL, '678': ATL, '770': ATL,
  '615': M('Nashville', 'TN', 36.1627, -86.7816), '901': M('Memphis', 'TN', 35.1495, -90.049),
  '205': M('Birmingham', 'AL', 33.5186, -86.8104), '504': M('New Orleans', 'LA', 29.9511, -90.0715),
  '502': M('Louisville', 'KY', 38.2527, -85.7585),
  // Florida
  '305': MIA, '786': MIA, '954': M('Fort Lauderdale', 'FL', 26.1224, -80.1373),
  '561': M('West Palm Beach', 'FL', 26.7153, -80.0534), '407': M('Orlando', 'FL', 28.5383, -81.3792),
  '321': M('Orlando', 'FL', 28.5383, -81.3792), '813': M('Tampa', 'FL', 27.9506, -82.4572),
  '727': M('St. Petersburg', 'FL', 27.7676, -82.6403), '904': M('Jacksonville', 'FL', 30.3322, -81.6557),
  // Midwest
  '312': CHI, '773': CHI, '872': CHI, '708': CHI, '847': M('Evanston', 'IL', 42.0451, -87.6877),
  '313': M('Detroit', 'MI', 42.3314, -83.0458), '248': M('Troy', 'MI', 42.6064, -83.1498),
  '216': M('Cleveland', 'OH', 41.4993, -81.6944), '614': M('Columbus', 'OH', 39.9612, -82.9988),
  '513': M('Cincinnati', 'OH', 39.1031, -84.512), '317': M('Indianapolis', 'IN', 39.7684, -86.1581),
  '414': M('Milwaukee', 'WI', 43.0389, -87.9065), '612': M('Minneapolis', 'MN', 44.9778, -93.265),
  '314': M('St. Louis', 'MO', 38.627, -90.1994), '816': M('Kansas City', 'MO', 39.0997, -94.5786),
  '402': M('Omaha', 'NE', 41.2565, -95.9345),
  // Texas and South Central
  '214': DAL, '469': DAL, '972': DAL, '945': DAL, '817': M('Fort Worth', 'TX', 32.7555, -97.3308),
  '682': M('Fort Worth', 'TX', 32.7555, -97.3308), '713': HOU, '281': HOU, '832': HOU, '346': HOU,
  '512': M('Austin', 'TX', 30.2672, -97.7431), '737': M('Austin', 'TX', 30.2672, -97.7431),
  '210': M('San Antonio', 'TX', 29.4241, -98.4936), '726': M('San Antonio', 'TX', 29.4241, -98.4936),
  '915': M('El Paso', 'TX', 31.7619, -106.485), '405': M('Oklahoma City', 'OK', 35.4676, -97.5164),
  '918': M('Tulsa', 'OK', 36.154, -95.9928), '501': M('Little Rock', 'AR', 34.7465, -92.2896),
  // Mountain
  '602': PHX, '480': M('Mesa', 'AZ', 33.4152, -111.8315), '623': PHX,
  '520': M('Tucson', 'AZ', 32.2226, -110.9747), '702': M('Las Vegas', 'NV', 36.1699, -115.1398),
  '725': M('Las Vegas', 'NV', 36.1699, -115.1398), '303': M('Denver', 'CO', 39.7392, -104.9903),
  '720': M('Denver', 'CO', 39.7392, -104.9903), '801': M('Salt Lake City', 'UT', 40.7608, -111.891),
  '505': M('Albuquerque', 'NM', 35.0844, -106.6504),
  // West Coast
  '213': LA, '310': LA, '323': LA, '424': LA, '818': LA, '626': M('Pasadena', 'CA', 34.1478, -118.1445),
  '562': M('Long Beach', 'CA', 33.7701, -118.1937), '714': M('Anaheim', 'CA', 33.8366, -117.9143),
  '909': M('San Bernardino', 'CA', 34.1083, -117.2898), '951': M('Riverside', 'CA', 33.9806, -117.3755),
  '619': M('San Diego', 'CA', 32.7157, -117.1611), '858': M('San Diego', 'CA', 32.7157, -117.1611),
  '415': SF, '628': SF, '510': M('Oakland', 'CA', 37.8044, -122.2712),
  '408': M('San Jose', 'CA', 37.3382, -121.8863), '916': M('Sacramento', 'CA', 38.5816, -121.4944),
  '559': M('Fresno', 'CA', 36.7378, -119.7871), '206': M('Seattle', 'WA', 47.6062, -122.3321),
  '253': M('Tacoma', 'WA', 47.2529, -122.4443), '425': M('Bellevue', 'WA', 47.6101, -122.2015),
  '503': M('Portland', 'OR', 45.5152, -122.6784), '808': M('Honolulu', 'HI', 21.3069, -157.8583),
  '907': M('Anchorage', 'AK', 61.2181, -149.9003),
  // Regional
  '956': M('McAllen', 'TX', 26.2034, -98.23), '806': M('Lubbock', 'TX', 33.5779, -101.8552),
  '432': M('Midland', 'TX', 31.9973, -102.0779), '830': M('New Braunfels', 'TX', 29.703, -98.1245),
  '239': M('Fort Myers', 'FL', 26.6406, -81.8723), '336': M('Greensboro', 'NC', 36.0726, -79.792),
  '910': M('Fayetteville', 'NC', 35.0527, -78.8784), '479': M('Fayetteville', 'AR', 36.0626, -94.1574),
  // Outside the US but on the +1 plan
  '876': M('Kingston', 'Jamaica', 17.9712, -76.7936),
};

/** Metro for a US phone number (+1XXXXXXXXXX or 10 digits), or null for short codes and unknown codes. */
export function metroForNumber(number: string): Metro | null {
  const digits = number.replace(/\D/g, '');
  const ten = digits.length === 11 && digits[0] === '1' ? digits.slice(1) : digits;
  if (ten.length !== 10) return null;
  return AREA_CODES[ten.slice(0, 3)] ?? null;
}

/** Small, stable offset (about +/- 0.15 degrees) so a metro's heat spreads into a hotspot instead of one dot. */
export function jitter(seed: string): [number, number] {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  const a = ((h >>> 0) % 1000) / 1000;
  const b = ((h >>> 10) % 1000) / 1000;
  return [(a - 0.5) * 0.3, (b - 0.5) * 0.3];
}

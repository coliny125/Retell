require('dotenv').config();
const express = require('express');
const crypto = require('crypto');
const axios = require('axios');
const app = express();

app.use(express.json());

// Add CORS for Railway
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, X-Retell-Signature');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  next();
});

// Health check endpoint
app.get('/', (req, res) => {
  res.json({ 
    status: 'OK', 
    message: 'Retell Restaurant Agent with Google Places API',
    timestamp: new Date().toISOString(),
    endpoints: [
      '/webhook/search_restaurants',
      '/webhook/get_restaurant_details', 
      '/webhook/check_availability'
    ]
  });
});

app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

// Verify Retell signature
function verifyRetellSignature(req, res, next) {
  const signature = req.headers['x-retell-signature'];
  
  if (!process.env.RETELL_API_SECRET_KEY) {
    console.warn('RETELL_API_SECRET_KEY not set - skipping signature verification');
    return next();
  }
  
  if (!signature) {
    return res.status(401).json({ error: 'Missing signature' });
  }
  
  const body = JSON.stringify(req.body);
  const expectedSignature = crypto
    .createHmac('sha256', process.env.RETELL_API_SECRET_KEY)
    .update(body)
    .digest('hex');
  
  if (signature !== expectedSignature) {
    return res.status(401).json({ error: 'Invalid signature' });
  }
  next();
}

// Google Places API helper functions
const GOOGLE_PLACES_API_KEY = process.env.GOOGLE_PLACES_API_KEY;
const PLACES_BASE_URL = 'https://maps.googleapis.com/maps/api/place';

// Convert price range to Google Places price level
function convertPriceRange(priceRange) {
  const priceMap = {
    '$': 1,
    '$$': 2, 
    '$$$': 3,
    '$$$$': 4
  };
  return priceMap[priceRange] || null;
}

// Format price level back to dollar signs
function formatPriceLevel(priceLevel) {
  const priceMap = {
    1: '$',
    2: '$$',
    3: '$$$', 
    4: '$$$$'
  };
  return priceMap[priceLevel] || 'Price not available';
}

// Search for restaurants using Google Places API
async function searchRestaurants(location, cuisine = null, priceRange = null, partySize = 2) {
  try {
    console.log(`Searching restaurants: ${location}, ${cuisine}, ${priceRange}, ${partySize}`);
    
    if (!GOOGLE_PLACES_API_KEY) {
      return 'Google Places API key is not configured. Please add GOOGLE_PLACES_API_KEY to environment variables.';
    }

    // Step 1: Find location coordinates using Geocoding API
    const geocodeUrl = `https://maps.googleapis.com/maps/api/geocode/json`;
    const geocodeResponse = await axios.get(geocodeUrl, {
      params: {
        address: location,
        key: GOOGLE_PLACES_API_KEY
      }
    });

    if (!geocodeResponse.data.results.length) {
      return `I couldn't find the location "${location}". Please try a more specific location like "Manhattan, NY" or "Downtown Boston".`;
    }

    const { lat, lng } = geocodeResponse.data.results[0].geometry.location;
    const formattedLocation = geocodeResponse.data.results[0].formatted_address;

    // Step 2: Search for restaurants using Places Nearby Search
    let searchQuery = 'restaurant';
    if (cuisine) {
      searchQuery = `${cuisine} restaurant`;
    }

    const searchUrl = `${PLACES_BASE_URL}/nearbysearch/json`;
    const searchParams = {
      location: `${lat},${lng}`,
      radius: 5000, // 5km radius
      type: 'restaurant',
      keyword: searchQuery,
      key: GOOGLE_PLACES_API_KEY
    };

    // Add price level filter if specified
    const priceLevel = convertPriceRange(priceRange);
    if (priceLevel) {
      searchParams.minprice = priceLevel;
      searchParams.maxprice = priceLevel;
    }

    const searchResponse = await axios.get(searchUrl, { params: searchParams });
    
    if (!searchResponse.data.results.length) {
      return `I couldn't find any restaurants matching your criteria in ${location}. Try a broader search or different cuisine type.`;
    }

    // Process and format results
    const restaurants = searchResponse.data.results
      .slice(0, 5) // Limit to top 5
      .map(place => ({
        name: place.name,
        rating: place.rating || 'No rating',
        priceLevel: place.price_level ? formatPriceLevel(place.price_level) : 'Price not available',
        address: place.vicinity,
        isOpen: place.opening_hours?.open_now,
        placeId: place.place_id,
        types: place.types.filter(type => type !== 'establishment' && type !== 'point_of_interest')
      }));

    // Format response
    let response_text = `Here are ${restaurants.length} great restaurants I found in ${formattedLocation}:\n\n`;
    
    restaurants.forEach((restaurant, index) => {
      response_text += `${index + 1}. **${restaurant.name}**\n`;
      response_text += `   • Rating: ${restaurant.rating} stars\n`;
      response_text += `   • Price: ${restaurant.priceLevel}\n`;
      response_text += `   • Location: ${restaurant.address}\n`;
      
      if (restaurant.isOpen !== undefined) {
        response_text += `   • Currently: ${restaurant.isOpen ? 'Open' : 'Closed'}\n`;
      }
      
      if (restaurant.types.length > 0) {
        const cuisineTypes = restaurant.types
          .filter(type => type.includes('food') || type === 'restaurant')
          .map(type => type.replace('_', ' ').replace('food', '').trim())
          .filter(type => type.length > 0);
        
        if (cuisineTypes.length > 0) {
          response_text += `   • Type: ${cuisineTypes.join(', ')}\n`;
        }
      }
      
      response_text += '\n';
    });

    response_text += 'Would you like more details about any of these restaurants, or should I check availability for a specific one?';

    return response_text;

  } catch (error) {
    console.error('Restaurant search error:', error.message);
    
    if (error.response?.status === 403) {
      return 'I\'m having trouble accessing restaurant data. Please check that the Google Places API is properly configured.';
    }
    
    return `I'm having trouble searching for restaurants in ${location} right now. Please try again in a moment.`;
  }
}

// Get detailed restaurant information
async function getRestaurantDetails(restaurantName, location) {
  try {
    console.log(`Getting details for: ${restaurantName} in ${location}`);
    
    if (!GOOGLE_PLACES_API_KEY) {
      return 'Google Places API key is not configured. Please add GOOGLE_PLACES_API_KEY to environment variables.';
    }

    // Step 1: Search for the specific restaurant
    const searchUrl = `${PLACES_BASE_URL}/textsearch/json`;
    const searchResponse = await axios.get(searchUrl, {
      params: {
        query: `${restaurantName} ${location}`,
        type: 'restaurant',
        key: GOOGLE_PLACES_API_KEY
      }
    });

    if (!searchResponse.data.results.length) {
      return `I couldn't find "${restaurantName}" in ${location}. Please check the spelling or try a different restaurant name.`;
    }

    const restaurant = searchResponse.data.results[0];
    const placeId = restaurant.place_id;

    // Step 2: Get detailed information using Place Details API
    const detailsUrl = `${PLACES_BASE_URL}/details/json`;
    const detailsResponse = await axios.get(detailsUrl, {
      params: {
        place_id: placeId,
        fields: 'name,rating,price_level,formatted_address,formatted_phone_number,opening_hours,website,reviews,types,photos',
        key: GOOGLE_PLACES_API_KEY
      }
    });

    const details = detailsResponse.data.result;

    // Format detailed response
    let response_text = `Here are the details for **${details.name}**:\n\n`;
    
    // Basic info
    response_text += `📍 **Address**: ${details.formatted_address}\n`;
    
    if (details.rating) {
      response_text += `⭐ **Rating**: ${details.rating} stars\n`;
    }
    
    if (details.price_level) {
      response_text += `💰 **Price Range**: ${formatPriceLevel(details.price_level)}\n`;
    }
    
    if (details.formatted_phone_number) {
      response_text += `📞 **Phone**: ${details.formatted_phone_number}\n`;
    }
    
    if (details.website) {
      response_text += `🌐 **Website**: ${details.website}\n`;
    }

    // Cuisine type
    if (details.types) {
      const cuisineTypes = details.types
        .filter(type => 
          type.includes('food') || 
          type === 'restaurant' || 
          type === 'cafe' ||
          type.includes('bakery') ||
          type.includes('bar')
        )
        .map(type => type.replace('_', ' ').replace('food', '').trim())
        .filter(type => type.length > 0);
      
      if (cuisineTypes.length > 0) {
        response_text += `🍽️  **Cuisine**: ${cuisineTypes.join(', ')}\n`;
      }
    }

    // Hours
    if (details.opening_hours) {
      response_text += `\n⏰ **Hours**:\n`;
      details.opening_hours.weekday_text.forEach(day => {
        response_text += `   ${day}\n`;
      });
    }

    // Recent reviews
    if (details.reviews && details.reviews.length > 0) {
      response_text += `\n📝 **Recent Review**:\n`;
      const topReview = details.reviews[0];
      response_text += `   "${topReview.text.substring(0, 150)}${topReview.text.length > 150 ? '...' : ''}"\n`;
      response_text += `   - ${topReview.author_name} (${topReview.rating} stars)\n`;
    }

    response_text += `\nWould you like me to check availability for ${details.name}, or do you need information about other restaurants?`;

    return response_text;

  } catch (error) {
    console.error('Restaurant details error:', error.message);
    
    if (error.response?.status === 403) {
      return 'I\'m having trouble accessing restaurant details. Please check that the Google Places API is properly configured.';
    }
    
    return `I'm having trouble getting details for ${restaurantName}. Please try again or check the restaurant's website directly.`;
  }
}

// Check availability and provide booking guidance
async function checkAvailability(restaurantName, location, date, time, partySize = 2) {
  try {
    console.log(`Checking availability: ${restaurantName}, ${date}, ${time}, ${partySize} people`);
    
    if (!GOOGLE_PLACES_API_KEY) {
      return 'Google Places API key is not configured. Please add GOOGLE_PLACES_API_KEY to environment variables.';
    }

    // Get restaurant details first
    const searchUrl = `${PLACES_BASE_URL}/textsearch/json`;
    const searchResponse = await axios.get(searchUrl, {
      params: {
        query: `${restaurantName} ${location}`,
        type: 'restaurant',
        key: GOOGLE_PLACES_API_KEY
      }
    });

    if (!searchResponse.data.results.length) {
      return `I couldn't find "${restaurantName}" in ${location}. Please check the spelling or try a different restaurant name.`;
    }

    const restaurant = searchResponse.data.results[0];
    const placeId = restaurant.place_id;

    // Get detailed info including phone and website
    const detailsUrl = `${PLACES_BASE_URL}/details/json`;
    const detailsResponse = await axios.get(detailsUrl, {
      params: {
        place_id: placeId,
        fields: 'name,formatted_address,formatted_phone_number,website,opening_hours',
        key: GOOGLE_PLACES_API_KEY
      }
    });

    const details = detailsResponse.data.result;

    // Format the date nicely
    const dateObj = new Date(date);
    const dateFormatted = dateObj.toLocaleDateString('en-US', { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });

    let response_text = `🍽️  **Reservation for ${details.name}**\n`;
    response_text += `📅 ${dateFormatted} at ${time} for ${partySize} ${partySize === 1 ? 'person' : 'people'}\n\n`;

    // Check if restaurant is open on that day/time
    let hoursInfo = '';
    if (details.opening_hours?.weekday_text) {
      const dayOfWeek = dateObj.getDay();
      const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const requestedDay = dayNames[dayOfWeek];
      
      const dayHours = details.opening_hours.weekday_text.find(day => 
        day.toLowerCase().includes(requestedDay.toLowerCase())
      );
      
      if (dayHours) {
        hoursInfo = `📍 **${requestedDay} Hours**: ${dayHours.split(': ')[1]}\n\n`;
      }
    }

    response_text += hoursInfo;

    response_text += `**Here's how to make your reservation:**\n\n`;

    // Prioritize direct booking methods
    if (details.formatted_phone_number) {
      response_text += `📞 **Call directly**: ${details.formatted_phone_number}\n`;
      response_text += `   This is often the fastest way to check availability and make a reservation.\n\n`;
    }

    if (details.website) {
      response_text += `🌐 **Restaurant website**: ${details.website}\n`;
      response_text += `   Many restaurants have online reservation systems on their website.\n\n`;
    }

    response_text += `🍴 **OpenTable**: Visit OpenTable.com and search for "${details.name}"\n`;
    response_text += `   Popular platform for restaurant reservations.\n\n`;

    response_text += `📱 **Other apps**: Try Resy, Yelp Reservations, or Google Maps\n\n`;

    // Add timing advice
    const hour = parseInt(time.split(':')[0]);
    if (hour >= 19 && hour <= 20) {
      response_text += `⚠️  **Tip**: ${time} is peak dinner time. Consider booking early or having backup times like 6:00 PM or 8:30 PM.\n\n`;
    }

    if (partySize >= 6) {
      response_text += `👥 **Large party tip**: For ${partySize} people, calling directly is often better than online booking.\n\n`;
    }

    response_text += `Would you like me to search for alternative restaurants in ${location}, or help you with anything else?`;

    return response_text;

  } catch (error) {
    console.error('Availability check error:', error.message);
    
    if (error.response?.status === 403) {
      return 'I\'m having trouble accessing restaurant information. Please check that the Google Places API is properly configured.';
    }
    
    return `I'm having trouble checking availability for ${restaurantName}. I recommend calling them directly or visiting their website.`;
  }
}

// Webhook endpoints
app.post('/webhook/search_restaurants', verifyRetellSignature, async (req, res) => {
  try {
    const { name, args } = req.body;
    console.log('Restaurant search request:', args);

    const { location, cuisine, price_range, party_size } = args;

    if (!location) {
      return res.json('I need to know where you\'d like to search for restaurants. What city or area are you interested in?');
    }

    const results = await searchRestaurants(location, cuisine, price_range, party_size);
    res.json(results);

  } catch (error) {
    console.error('Search restaurants webhook error:', error);
    res.json('Sorry, I encountered an error while searching for restaurants. Please try again.');
  }
});

app.post('/webhook/get_restaurant_details', verifyRetellSignature, async (req, res) => {
  try {
    const { name, args } = req.body;
    console.log('Restaurant details request:', args);

    const { restaurant_name, location } = args;

    if (!restaurant_name || !location) {
      return res.json('I need both the restaurant name and location to get details. Can you provide both?');
    }

    const details = await getRestaurantDetails(restaurant_name, location);
    res.json(details);

  } catch (error) {
    console.error('Restaurant details webhook error:', error);
    res.json('Sorry, I encountered an error while getting restaurant details. Please try again.');
  }
});

app.post('/webhook/check_availability', verifyRetellSignature, async (req, res) => {
  try {
    const { name, args } = req.body;
    console.log('Availability check request:', args);

    const { restaurant_name, location, date, time, party_size } = args;

    if (!restaurant_name || !location || !date || !time) {
      return res.json('I need the restaurant name, location, date, and time to check availability. Can you provide all of those details?');
    }

    const availability = await checkAvailability(restaurant_name, location, date, time, party_size);
    res.json(availability);

  } catch (error) {
    console.error('Availability check webhook error:', error);
    res.json('Sorry, I encountered an error while checking availability. Please try again.');
  }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📍 Health check: http://localhost:${PORT}/`);
  console.log(`🍽️  Restaurant webhooks with Google Places API ready!`);
  
  if (!GOOGLE_PLACES_API_KEY) {
    console.warn('⚠️  WARNING: GOOGLE_PLACES_API_KEY not found in environment variables');
  } else {
    console.log('✅ Google Places API key configured');
  }
});

module.exports = app;

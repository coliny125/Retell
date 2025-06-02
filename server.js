require('dotenv').config();
const express = require('express');
const crypto = require('crypto');
const axios = require('axios');
const cheerio = require('cheerio');
const app = express();

app.use(express.json());

// Add CORS for Railway
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, X-Retell-Signature');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  next();
});

// Health check endpoint (Railway needs this)
app.get('/', (req, res) => {
  res.json({ 
    status: 'OK', 
    message: 'Retell Restaurant Agent is running',
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

// Restaurant search function
async function searchRestaurants(location, cuisine = null, priceRange = null, partySize = 2) {
  try {
    console.log(`Searching restaurants: ${location}, ${cuisine}, ${priceRange}, ${partySize}`);
    
    let searchUrl = `https://www.opentable.com/s/?covers=${partySize}&dateTime=2024-01-15T19%3A00%3A00&size=${partySize}&query=${encodeURIComponent(location)}`;
    
    if (cuisine) {
      searchUrl += `&cuisine=${encodeURIComponent(cuisine)}`;
    }

    const response = await axios.get(searchUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      },
      timeout: 10000
    });

    const $ = cheerio.load(response.data);
    const restaurants = [];

    $('.rest-row-info').each((i, element) => {
      if (i >= 5) return false;

      const name = $(element).find('.rest-row-name').text().trim();
      const cuisineType = $(element).find('.rest-row-meta').first().text().trim();
      const priceLevel = $(element).find('.rest-row-pricing').text().trim();
      const rating = $(element).find('.star-rating-score').text().trim();
      const neighborhood = $(element).find('.rest-row-meta').last().text().trim();

      if (name) {
        restaurants.push({
          name,
          cuisine: cuisineType,
          price: priceLevel,
          rating,
          neighborhood
        });
      }
    });

    if (restaurants.length === 0) {
      return `I couldn't find any restaurants matching your criteria in ${location}. You might want to try a broader search or different location.`;
    }

    let response_text = `Here are some great restaurants I found in ${location}:\n\n`;
    
    restaurants.forEach((restaurant, index) => {
      response_text += `${index + 1}. ${restaurant.name}`;
      if (restaurant.cuisine) response_text += ` - ${restaurant.cuisine}`;
      if (restaurant.price) response_text += ` (${restaurant.price})`;
      if (restaurant.rating) response_text += ` • ${restaurant.rating} stars`;
      if (restaurant.neighborhood) response_text += ` • ${restaurant.neighborhood}`;
      response_text += '\n';
    });

    response_text += '\nWould you like more details about any of these restaurants, or should I check availability for a specific one?';

    return response_text;

  } catch (error) {
    console.error('Restaurant search error:', error.message);
    return `I'm having trouble searching for restaurants right now. Please try again in a moment, or you can visit OpenTable directly to search.`;
  }
}

async function getRestaurantDetails(restaurantName, location) {
  try {
    console.log(`Getting details for: ${restaurantName} in ${location}`);
    
    const searchUrl = `https://www.opentable.com/s/?query=${encodeURIComponent(restaurantName + ' ' + location)}`;
    
    const response = await axios.get(searchUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });

    const $ = cheerio.load(response.data);
    
    const firstResult = $('.rest-row-info').first();
    if (firstResult.length === 0) {
      return `I couldn't find detailed information for ${restaurantName} in ${location}. The restaurant might not be available on OpenTable or the name might be slightly different.`;
    }

    const name = firstResult.find('.rest-row-name').text().trim();
    const cuisine = firstResult.find('.rest-row-meta').first().text().trim();
    const price = firstResult.find('.rest-row-pricing').text().trim();
    const rating = firstResult.find('.star-rating-score').text().trim();
    const neighborhood = firstResult.find('.rest-row-meta').last().text().trim();

    let details = `Here are the details for ${name}:\n\n`;
    details += `• Cuisine: ${cuisine}\n`;
    if (price) details += `• Price Range: ${price}\n`;
    if (rating) details += `• Rating: ${rating} stars\n`;
    if (neighborhood) details += `• Location: ${neighborhood}\n`;
    
    details += `\nWould you like me to check availability for a specific date and time?`;

    return details;

  } catch (error) {
    console.error('Restaurant details error:', error.message);
    return `I'm having trouble getting details for ${restaurantName}. You can visit OpenTable directly to see more information about this restaurant.`;
  }
}

async function checkAvailability(restaurantName, location, date, time, partySize = 2) {
  try {
    console.log(`Checking availability: ${restaurantName}, ${date}, ${time}, ${partySize} people`);
    
    let response_text = `I found that checking real-time availability requires going directly to the restaurant's OpenTable page. `;
    response_text += `For ${restaurantName} in ${location} on ${date} at ${time} for ${partySize} people:\n\n`;
    response_text += `I recommend visiting OpenTable.com and searching for "${restaurantName} ${location}" to see live availability and make a reservation. `;
    response_text += `You can also try calling the restaurant directly for immediate availability.\n\n`;
    response_text += `Would you like me to search for alternative restaurants in the same area, or help you with anything else?`;

    return response_text;

  } catch (error) {
    console.error('Availability check error:', error.message);
    return `I'm having trouble checking availability right now. I recommend visiting OpenTable.com directly or calling ${restaurantName} to check for availability on ${date} at ${time}.`;
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
  console.log(`🍽️  Restaurant webhooks ready!`);
});

# README.md
# RetellAI Restaurant Phone Agent

This is a Flask-based webhook service for RetellAI that integrates with Google Places API to help users find restaurants and check their availability.

## Features

- Search restaurants by location and cuisine type
- Get detailed restaurant information including:
  - Ratings and price levels
  - Current open/closed status
  - Phone numbers for reservations
  - Operating hours
  - Website information

## Setup Instructions

### 1. Get API Keys

- **Google Places API Key**: 
  1. Go to [Google Cloud Console](https://console.cloud.google.com/)
  2. Create a new project or select existing
  3. Enable "Places API"
  4. Create credentials (API Key)
  5. Restrict the key to Places API for security

- **RetellAI API Key**:
  1. Sign up at [RetellAI](https://retell.ai/)
  2. Navigate to API Keys section
  3. Generate a new API key

### 2. Deploy to Railway

1. Fork or clone this repository
2. Sign up at [Railway](https://railway.app/)
3. Create a new project from GitHub repo
4. Add environment variables in Railway:
   - `GOOGLE_PLACES_API_KEY`
   - `RETELL_API_KEY`
5. Railway will automatically deploy your app

### 3. Configure RetellAI

1. In RetellAI dashboard, create a new agent
2. Add custom functions:

**Function 1: search_restaurants**
```json
{
  "name": "search_restaurants",
  "description": "Search for restaurants in a specific location",
  "parameters": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "City or area to search in"
      },
      "cuisine": {
        "type": "string",
        "description": "Type of cuisine (optional)"
      }
    },
    "required": ["location"]
  }
}
```

**Function 2: get_restaurant_details**
```json
{
  "name": "get_restaurant_details",
  "description": "Get detailed information about a specific restaurant",
  "parameters": {
    "type": "object",
    "properties": {
      "restaurant_name": {
        "type": "string",
        "description": "Name of the restaurant"
      },
      "location": {
        "type": "string",
        "description": "Location to help identify the restaurant"
      }
    },
    "required": ["restaurant_name"]
  }
}
```

3. Set your webhook URL to: `https://your-app-name.railway.app/webhook`
4. Configure the agent's conversation flow and test

## Usage Example

User: "Find me Italian restaurants in San Francisco"
Agent: "I found 5 restaurants serving Italian cuisine in San Francisco..."

User: "Tell me more about the first one"
Agent: "Restaurant Name has a rating of 4.5 stars. It's moderate. The restaurant is currently open..."

## Local Development

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with your API keys
4. Run: `python app.py`
5. Use ngrok for testing with RetellAI: `ngrok http 5000`

## Customization

- Modify `search_restaurants()` to change search radius or result limits
- Add more fields in `get_restaurant_details()` for additional information
- Enhance `format_restaurant_info()` for better speech output
- Add new functions for features like:
  - Making reservations (integrate with OpenTable API)
  - Getting directions
  - Checking wait times
  - Reading reviews

## Troubleshooting

- **No results found**: Check if location is specific enough
- **API errors**: Verify your Google Places API key has proper permissions
- **Webhook not responding**: Check Railway logs for errors
- **Rate limits**: Google Places API has usage quotas - monitor in Google Cloud Console

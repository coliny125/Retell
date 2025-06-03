import os
import json
from flask import Flask, request, jsonify
from datetime import datetime
import requests
from typing import Dict, List, Any

app = Flask(__name__)

# Configuration
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
RETELL_API_KEY = os.environ.get('RETELL_API_KEY')

class RestaurantAgent:
    def __init__(self):
        self.places_base_url = "https://maps.googleapis.com/maps/api/place"
        
    def search_restaurants(self, location: str, cuisine: str = None, radius: int = 5000) -> List[Dict]:
        """Search for restaurants using Google Places API"""
        
        # Text search endpoint
        search_url = f"{self.places_base_url}/textsearch/json"
        
        query = f"restaurants in {location}"
        if cuisine:
            query = f"{cuisine} restaurants in {location}"
            
        params = {
            'query': query,
            'radius': radius,
            'type': 'restaurant',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        try:
            response = requests.get(search_url, params=params)
            data = response.json()
            
            if data.get('status') == 'OK':
                restaurants = []
                for place in data.get('results', [])[:5]:  # Limit to top 5
                    restaurants.append({
                        'name': place.get('name'),
                        'place_id': place.get('place_id'),
                        'address': place.get('formatted_address'),
                        'rating': place.get('rating'),
                        'price_level': place.get('price_level'),
                        'open_now': place.get('opening_hours', {}).get('open_now', None)
                    })
                return restaurants
            else:
                return []
        except Exception as e:
            print(f"Error searching restaurants: {e}")
            return []
    
    def get_restaurant_details(self, place_id: str) -> Dict:
        """Get detailed information about a specific restaurant"""
        
        details_url = f"{self.places_base_url}/details/json"
        
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_phone_number,opening_hours,website,rating,price_level,formatted_address',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        try:
            response = requests.get(details_url, params=params)
            data = response.json()
            
            if data.get('status') == 'OK':
                result = data.get('result', {})
                
                # Process opening hours
                opening_hours = result.get('opening_hours', {})
                hours_text = opening_hours.get('weekday_text', [])
                is_open = opening_hours.get('open_now', None)
                
                return {
                    'name': result.get('name'),
                    'phone': result.get('formatted_phone_number'),
                    'address': result.get('formatted_address'),
                    'website': result.get('website'),
                    'rating': result.get('rating'),
                    'price_level': result.get('price_level'),
                    'is_open_now': is_open,
                    'hours': hours_text
                }
            else:
                return {}
        except Exception as e:
            print(f"Error getting restaurant details: {e}")
            return {}
    
    def format_restaurant_info(self, restaurant: Dict) -> str:
        """Format restaurant information for speech output"""
        
        info = f"{restaurant['name']} "
        
        if restaurant.get('rating'):
            info += f"has a rating of {restaurant['rating']} stars. "
        
        if restaurant.get('price_level'):
            price_desc = ['inexpensive', 'moderate', 'expensive', 'very expensive']
            price_idx = min(restaurant['price_level'] - 1, 3)
            info += f"It's {price_desc[price_idx]}. "
        
        if restaurant.get('is_open_now') is not None:
            status = "currently open" if restaurant['is_open_now'] else "currently closed"
            info += f"The restaurant is {status}. "
        
        return info

agent = RestaurantAgent()

@app.route('/webhook', methods=['POST'])
def retell_webhook():
    """Main webhook endpoint for RetellAI"""
    
    data = request.json
    
    # Extract the function call details
    function_name = data.get('function_name')
    arguments = data.get('arguments', {})
    
    response_data = {
        'response': '',
        'success': True
    }
    
    try:
        if function_name == 'search_restaurants':
            location = arguments.get('location')
            cuisine = arguments.get('cuisine')
            
            if not location:
                response_data['response'] = "I need a location to search for restaurants. Could you please tell me which city or area you're interested in?"
                response_data['success'] = False
            else:
                restaurants = agent.search_restaurants(location, cuisine)
                
                if restaurants:
                    response_text = f"I found {len(restaurants)} restaurants"
                    if cuisine:
                        response_text += f" serving {cuisine} cuisine"
                    response_text += f" in {location}. "
                    
                    for i, rest in enumerate(restaurants, 1):
                        response_text += f"\n{i}. {rest['name']}"
                        if rest.get('rating'):
                            response_text += f" - {rest['rating']} stars"
                        if rest.get('open_now') is not None:
                            status = "open" if rest['open_now'] else "closed"
                            response_text += f" - currently {status}"
                    
                    response_text += "\n\nWould you like more details about any of these restaurants?"
                    response_data['response'] = response_text
                else:
                    response_data['response'] = f"I couldn't find any restaurants in {location}. Could you try a different location or be more specific?"
                    response_data['success'] = False
        
        elif function_name == 'get_restaurant_details':
            restaurant_name = arguments.get('restaurant_name')
            location = arguments.get('location')
            
            if not restaurant_name:
                response_data['response'] = "Which restaurant would you like to know more about?"
                response_data['success'] = False
            else:
                # First search for the restaurant to get its place_id
                restaurants = agent.search_restaurants(location, restaurant_name)
                
                if restaurants:
                    # Get details for the first match
                    place_id = restaurants[0]['place_id']
                    details = agent.get_restaurant_details(place_id)
                    
                    if details:
                        response_text = agent.format_restaurant_info(details)
                        
                        if details.get('phone'):
                            response_text += f"Their phone number is {details['phone']}. "
                        
                        if details.get('website'):
                            response_text += "They have a website available. "
                        
                        response_text += "Would you like me to provide the phone number so you can make a reservation?"
                        response_data['response'] = response_text
                    else:
                        response_data['response'] = "I couldn't get the details for that restaurant. Let me try searching again."
                        response_data['success'] = False
                else:
                    response_data['response'] = f"I couldn't find {restaurant_name}. Could you provide more details or check the spelling?"
                    response_data['success'] = False
        
        else:
            response_data['response'] = "I can help you search for restaurants or get details about specific restaurants. What would you like to know?"
            response_data['success'] = False
            
    except Exception as e:
        print(f"Error processing request: {e}")
        response_data['response'] = "I encountered an error while processing your request. Please try again."
        response_data['success'] = False
    
    return jsonify(response_data)

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'RetellAI Restaurant Agent',
        'status': 'active',
        'endpoints': {
            '/webhook': 'POST - RetellAI webhook endpoint',
            '/health': 'GET - Health check endpoint'
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'restaurant-agent'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

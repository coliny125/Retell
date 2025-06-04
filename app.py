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

# Add startup check
if not GOOGLE_PLACES_API_KEY:
    print("WARNING: GOOGLE_PLACES_API_KEY not set in environment variables!")
else:
    print(f"Google Places API Key loaded: {GOOGLE_PLACES_API_KEY[:10]}...")

class RestaurantAgent:
    def __init__(self):
        self.places_base_url = "https://maps.googleapis.com/maps/api/place"
        
    def search_restaurants(self, location: str, cuisine: str = None, radius: int = 5000) -> List[Dict]:
        """Search for restaurants using Google Places API"""
        
        if not GOOGLE_PLACES_API_KEY:
            print("ERROR: Google Places API Key not found!")
            return []
        
        # Text search endpoint
        search_url = f"{self.places_base_url}/textsearch/json"
        
        query = f"restaurants in {location}"
        if cuisine:
            query = f"{cuisine} restaurants in {location}"
            
        params = {
            'query': query,
            'type': 'restaurant',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        print(f"Searching Google Places API...")
        print(f"Query: {query}")
        
        try:
            response = requests.get(search_url, params=params)
            print(f"API Response Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"API Request Failed: {response.text}")
                return []
            
            data = response.json()
            status = data.get('status', 'UNKNOWN')
            print(f"API Response Status: {status}")
            
            if status == 'REQUEST_DENIED':
                print(f"API Error Message: {data.get('error_message', 'No error message')}")
                return []
            
            if status == 'OK' and 'results' in data:
                restaurants = []
                results = data.get('results', [])
                print(f"Found {len(results)} results from Google Places")
                
                for place in results[:5]:  # Limit to top 5
                    # Extract data matching Google's actual response format
                    restaurant_data = {
                        'name': place.get('name', 'Unknown'),
                        'place_id': place.get('place_id', ''),
                        'address': place.get('formatted_address', 'Address not available'),
                        'rating': place.get('rating', 0),
                        'price_level': place.get('price_level', None),  # May not be present
                        'open_now': place.get('opening_hours', {}).get('open_now', None)
                    }
                    restaurants.append(restaurant_data)
                    print(f"Added: {restaurant_data['name']} - Rating: {restaurant_data['rating']}")
                
                return restaurants
            else:
                print(f"No results found. Full response: {json.dumps(data, indent=2)}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"Network error calling Google Places API: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
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
    
    print("\n" + "="*50)
    print("WEBHOOK CALLED")
    print("="*50)
    
    try:
        # Get and log the raw request data
        raw_data = request.get_data(as_text=True)
        print(f"Raw request body: {raw_data}")
        
        # Parse JSON
        data = request.json
        print(f"Parsed JSON: {json.dumps(data, indent=2)}")
        
        # Extract function name and arguments according to RetellAI docs
        function_name = data.get('function_name')
        arguments = data.get('arguments', {})
        
        print(f"Function: {function_name}")
        print(f"Arguments: {arguments}")
        
        if function_name == 'search_restaurants':
            location = arguments.get('location')
            cuisine = arguments.get('cuisine')
            
            if not location:
                response = {
                    'response': "I need a location to search for restaurants. Could you please tell me which city or area you're interested in?"
                }
                print(f"Sending response: {response}")
                return jsonify(response)
            
            print(f"Calling search_restaurants with location={location}, cuisine={cuisine}")
            restaurants = agent.search_restaurants(location, cuisine)
            
            if restaurants:
                response_text = f"I found {len(restaurants)}"
                if cuisine:
                    response_text += f" {cuisine}"
                response_text += f" restaurants in {location}:\n\n"
                
                for i, rest in enumerate(restaurants, 1):
                    response_text += f"{i}. {rest['name']}"
                    if rest.get('rating'):
                        response_text += f" - {rest['rating']} stars"
                    if rest.get('open_now') is not None:
                        status = "open now" if rest['open_now'] else "closed now"
                        response_text += f" - {status}"
                    response_text += "\n"
                
                response_text += "\nWould you like more details about any of these restaurants?"
                
                response = {'response': response_text}
                print(f"Sending successful response with {len(restaurants)} restaurants")
                return jsonify(response)
            else:
                response = {
                    'response': f"I couldn't find any {cuisine + ' ' if cuisine else ''}restaurants in {location}. This might be due to an API issue or the location might need to be more specific. Could you try again with a different search?"
                }
                print(f"No restaurants found, sending response: {response}")
                return jsonify(response)
        
        elif function_name == 'get_restaurant_details':
            restaurant_name = arguments.get('restaurant_name')
            location = arguments.get('location', '')
            
            if not restaurant_name:
                response = {
                    'response': "Which restaurant would you like to know more about? Please provide the restaurant name."
                }
                return jsonify(response)
            
            print(f"Getting details for restaurant: {restaurant_name} in {location}")
            
            # Search for the restaurant to get its place_id
            search_query = f"{restaurant_name} {location}" if location else restaurant_name
            restaurants = agent.search_restaurants(search_query)
            
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
                    
                    response = {'response': response_text}
                    return jsonify(response)
                else:
                    response = {
                        'response': "I found the restaurant but couldn't retrieve its detailed information. Would you like me to try again?"
                    }
                    return jsonify(response)
            else:
                response = {
                    'response': f"I couldn't find {restaurant_name}. Could you provide more details about its location or check the spelling?"
                }
                return jsonify(response)
        
        else:
            response = {
                'response': f"I received an unknown function: {function_name}. I can help you search for restaurants or get details about specific restaurants. What would you like to know?"
            }
            print(f"Unknown function, sending response: {response}")
            return jsonify(response)
            
    except Exception as e:
        print(f"ERROR in webhook: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        response = {
            'response': "I encountered an error while processing your request. Please try again."
        }
        return jsonify(response)

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

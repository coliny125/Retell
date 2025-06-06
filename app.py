import os
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Any
import uuid
import time

app = Flask(__name__)

# Configuration
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
RETELL_API_KEY = os.environ.get('RETELL_API_KEY')
RETELL_PHONE_NUMBER = os.environ.get('RETELL_PHONE_NUMBER', '+14157774444')  # Your RetellAI number
RESTAURANT_CALLER_AGENT_ID = os.environ.get('RESTAURANT_CALLER_AGENT_ID')  # Your second agent

# Add startup check
if not GOOGLE_PLACES_API_KEY:
    print("WARNING: GOOGLE_PLACES_API_KEY not set in environment variables!")
else:
    print(f"Google Places API Key loaded: {GOOGLE_PLACES_API_KEY[:10]}...")

if not RETELL_API_KEY:
    print("WARNING: RETELL_API_KEY not set in environment variables!")

if not RESTAURANT_CALLER_AGENT_ID:
    print("WARNING: RESTAURANT_CALLER_AGENT_ID not set - outbound calling won't work!")

# In-memory storage for call tracking (in production, use a database)
active_reservations = {}

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
        
        # Request MORE fields including reviews, photos, and additional details
        params = {
            'place_id': place_id,
            'fields': (
                'name,formatted_phone_number,opening_hours,website,rating,'
                'price_level,formatted_address,business_status,user_ratings_total,'
                'reviews,photos,editorial_summary,serves_beer,serves_wine,'
                'delivery,dine_in,takeout,reservable,wheelchair_accessible_entrance'
            ),
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
                
                # Process reviews
                reviews = []
                for review in result.get('reviews', [])[:3]:  # Get top 3 reviews
                    reviews.append({
                        'author': review.get('author_name', 'Anonymous'),
                        'rating': review.get('rating', 0),
                        'text': review.get('text', ''),
                        'time': review.get('relative_time_description', '')
                    })
                
                # Get photo references (up to 3)
                photo_refs = []
                for photo in result.get('photos', [])[:3]:
                    photo_refs.append(photo.get('photo_reference'))
                
                return {
                    'name': result.get('name'),
                    'phone': result.get('formatted_phone_number'),
                    'address': result.get('formatted_address'),
                    'website': result.get('website'),
                    'rating': result.get('rating'),
                    'user_ratings_total': result.get('user_ratings_total'),
                    'price_level': result.get('price_level'),
                    'is_open_now': is_open,
                    'hours': hours_text,
                    'business_status': result.get('business_status'),
                    'editorial_summary': result.get('editorial_summary', {}).get('overview'),
                    'reviews': reviews,
                    'photos': photo_refs,
                    'serves_beer': result.get('serves_beer'),
                    'serves_wine': result.get('serves_wine'),
                    'delivery': result.get('delivery'),
                    'dine_in': result.get('dine_in'),
                    'takeout': result.get('takeout'),
                    'reservable': result.get('reservable'),
                    'wheelchair_accessible': result.get('wheelchair_accessible_entrance')
                }
            else:
                return {}
        except Exception as e:
            print(f"Error getting restaurant details: {e}")
            return {}
    
    def format_restaurant_info(self, restaurant: Dict) -> str:
        """Format restaurant information for speech output"""
        
        info = f"{restaurant['name']} "
        
        if restaurant.get('rating') and restaurant.get('user_ratings_total'):
            info += f"has a rating of {restaurant['rating']} stars based on {restaurant['user_ratings_total']} reviews. "
        elif restaurant.get('rating'):
            info += f"has a rating of {restaurant['rating']} stars. "
        
        if restaurant.get('price_level'):
            price_desc = ['inexpensive', 'moderate', 'expensive', 'very expensive']
            price_idx = min(restaurant['price_level'] - 1, 3)
            info += f"It's {price_desc[price_idx]}. "
        
        if restaurant.get('is_open_now') is not None:
            status = "currently open" if restaurant['is_open_now'] else "currently closed"
            info += f"The restaurant is {status}. "
        
        # Add service options
        services = []
        if restaurant.get('dine_in'):
            services.append("dine-in")
        if restaurant.get('takeout'):
            services.append("takeout")
        if restaurant.get('delivery'):
            services.append("delivery")
        if services:
            info += f"They offer {', '.join(services)}. "
        
        if restaurant.get('reservable'):
            info += "Reservations are available. "
        
        # Add editorial summary if available
        if restaurant.get('editorial_summary'):
            info += f"\n\nHere's what Google says: {restaurant['editorial_summary']} "
        
        # Add top reviews
        if restaurant.get('reviews'):
            info += "\n\nHere are some recent customer reviews:\n"
            for i, review in enumerate(restaurant['reviews'], 1):
                info += f"\n{i}. {review['author']} rated it {review['rating']} stars"
                if review['time']:
                    info += f" {review['time']}"
                info += f" and said: \"{review['text'][:150]}{'...' if len(review['text']) > 150 else ''}\""
        
        return info
    
    def format_phone_number_e164(self, phone: str) -> str:
        """Convert phone number to E.164 format for RetellAI"""
        # Remove all non-digit characters
        phone_digits = ''.join(filter(str.isdigit, phone))
        
        # Assume US number if 10 digits without country code
        if len(phone_digits) == 10:
            return f"+1{phone_digits}"
        elif len(phone_digits) == 11 and phone_digits.startswith('1'):
            return f"+{phone_digits}"
        else:
            # Try to use as-is with + prefix
            return f"+{phone_digits}"
    
    def make_reservation_call(self, restaurant_name: str, date: str, time: str, party_size: int, 
                            customer_name: str, customer_phone: str, location: str = None, 
                            special_requests: str = None) -> Dict:
        """Initiates an outbound call to make a reservation"""
        
        if not RETELL_API_KEY or not RESTAURANT_CALLER_AGENT_ID:
            return {
                'success': False,
                'message': "I'm not configured to make outbound calls. Please call the restaurant directly."
            }
        
        # Validate customer information
        if not customer_name or not customer_phone:
            return {
                'success': False,
                'message': "I need your name and phone number to make the reservation. Could you please provide them?"
            }
        
        # First, find the restaurant and get its phone number
        search_query = f"{restaurant_name} {location}" if location else restaurant_name
        restaurants = self.search_restaurants(search_query)
        
        if not restaurants:
            return {
                'success': False,
                'message': f"I couldn't find {restaurant_name}. Could you provide more details about its location?"
            }
        
        # Get restaurant details
        place_id = restaurants[0]['place_id']
        details = self.get_restaurant_details(place_id)
        
        if not details or not details.get('phone'):
            return {
                'success': False,
                'message': f"I found {restaurant_name} but couldn't get their phone number. Would you like to try another restaurant?"
            }
        
        # Format phone number for API
        phone_e164 = self.format_phone_number_e164(details['phone'])
        
        # Create a unique reservation ID
        reservation_id = str(uuid.uuid4())
        
        # Store reservation details
        active_reservations[reservation_id] = {
            'restaurant_name': details['name'],
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'date': date,
            'time': time,
            'party_size': party_size,
            'special_requests': special_requests,
            'status': 'calling',
            'created_at': datetime.now().isoformat()
        }
        
        # Make the API call to RetellAI
        headers = {
            'Authorization': f'Bearer {RETELL_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Prepare dynamic variables for the restaurant caller agent
        dynamic_variables = {
            'restaurant_name': details['name'],
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'date': date,
            'time': time,
            'party_size': str(party_size),
            'special_requests': special_requests or 'none'
        }
        
        data = {
            'from_number': RETELL_PHONE_NUMBER,
            'to_number': phone_e164,
            'agent_id': RESTAURANT_CALLER_AGENT_ID,
            'metadata': {
                'reservation_id': reservation_id,
                'type': 'restaurant_reservation',
                'customer_name': customer_name,
                'customer_phone': customer_phone
            },
            'dynamic_variables': dynamic_variables
        }
        
        try:
            response = requests.post(
                'https://api.retellai.com/v2/create-phone-call',
                headers=headers,
                json=data
            )
            
            if response.status_code in [200, 201]:
                call_data = response.json()
                active_reservations[reservation_id]['call_id'] = call_data.get('call_id')
                
                return {
                    'success': True,
                    'reservation_id': reservation_id,
                    'message': f"I'm calling {details['name']} now to make a reservation for {customer_name}, "
                             f"party of {party_size} on {date} at {time}. "
                             f"I'll let you know as soon as I have confirmation. This usually takes 1-2 minutes."
                }
            else:
                print(f"RetellAI API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'message': "I encountered an error trying to call the restaurant. Would you like me to provide their number so you can call directly?"
                }
                
        except Exception as e:
            print(f"Error making outbound call: {e}")
            return {
                'success': False,
                'message': "I couldn't complete the call. Would you like the restaurant's phone number instead?"
            }
    
    def check_reservation_status(self, reservation_id: str) -> Dict:
        """Check the status of a reservation call"""
        
        if reservation_id not in active_reservations:
            return {
                'found': False,
                'message': "I couldn't find that reservation. It may have expired or the ID is incorrect."
            }
        
        reservation = active_reservations[reservation_id]
        status = reservation['status']
        
        if status == 'calling':
            return {
                'found': True,
                'status': 'calling',
                'message': f"I'm still on the call with {reservation['restaurant_name']}. I'll have an update for you shortly."
            }
        elif status == 'confirmed':
            return {
                'found': True,
                'status': 'confirmed',
                'message': f"Great news! Your reservation at {reservation['restaurant_name']} is confirmed for "
                         f"{reservation['customer_name']}, party of {reservation['party_size']} on {reservation['date']} at {reservation['time']}. "
                         f"They have your phone number {reservation['customer_phone']} on file. "
                         f"{reservation.get('confirmation_details', '')}"
            }
        elif status == 'failed':
            return {
                'found': True,
                'status': 'failed',
                'message': f"I couldn't make the reservation at {reservation['restaurant_name']}. "
                         f"{reservation.get('failure_reason', 'The restaurant may be fully booked or closed.')} "
                         f"Would you like me to try another restaurant?"
            }
        else:
            return {
                'found': True,
                'status': status,
                'message': f"The reservation status is: {status}"
            }

agent = RestaurantAgent()

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'RetellAI Restaurant Agent',
        'status': 'active',
        'endpoints': {
            '/webhook': 'POST - RetellAI webhook endpoint',
            '/health': 'GET - Health check endpoint',
            '/retell-webhook': 'POST - RetellAI call status webhook'
        }
    })

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
        
        # RetellAI might send the function name in different ways
        # Check multiple possible field names
        function_name = (
            data.get('function_name') or 
            data.get('name') or 
            data.get('tool_name') or
            data.get('function') or
            data.get('tool')
        )
        
        # Arguments might also be in different fields
        arguments = (
            data.get('arguments') or 
            data.get('args') or 
            data.get('parameters') or 
            data.get('params') or
            {}
        )
        
        # If still no function name, check if it's nested
        if not function_name and 'function' in data:
            if isinstance(data['function'], dict):
                function_name = data['function'].get('name')
                arguments = data['function'].get('arguments', {})
        
        print(f"Extracted function: {function_name}")
        print(f"Extracted arguments: {arguments}")
        
        # If we still can't find the function name, log all keys
        if not function_name:
            print(f"Could not find function name. Available keys: {list(data.keys())}")
            print(f"Full data structure: {json.dumps(data, indent=2)}")
        
        # List all supported functions for debugging
        supported_functions = ['search_restaurants', 'get_restaurant_details', 'make_reservation_call', 'check_reservation_status']
        print(f"Checking if '{function_name}' is in supported functions: {supported_functions}")
        
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
                        response_text += f"\n\nTheir phone number is {details['phone']}. Would you like me to repeat that?"
                    
                    if details.get('website'):
                        response_text += f" They also have a website for online reservations. "
                    
                    if details.get('hours'):
                        response_text += "\n\nWould you like to hear their hours of operation?"
                    
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
        
        elif function_name == 'make_reservation_call':
            restaurant_name = arguments.get('restaurant_name')
            date = arguments.get('date')
            time = arguments.get('time')
            party_size = arguments.get('party_size', 2)
            customer_name = arguments.get('customer_name')
            customer_phone = arguments.get('customer_phone')
            location = arguments.get('location')
            special_requests = arguments.get('special_requests')
            
            if not restaurant_name:
                response = {
                    'response': "Which restaurant would you like me to call for a reservation?"
                }
                return jsonify(response)
            
            if not date or not time:
                response = {
                    'response': f"I need to know when you'd like to dine at {restaurant_name}. What date and time would you prefer?"
                }
                return jsonify(response)
            
            if not customer_name or not customer_phone:
                response = {
                    'response': "I'll need your name and phone number to make the reservation. This is so the restaurant can contact you if needed. Could you please provide them?"
                }
                return jsonify(response)
            
            print(f"Making reservation call for {customer_name} at {restaurant_name} on {date} at {time} for {party_size} people")
            
            result = agent.make_reservation_call(
                restaurant_name, date, time, party_size, 
                customer_name, customer_phone, location, special_requests
            )
            
            if result['success']:
                # Store the reservation ID in the response for tracking
                response = {
                    'response': result['message'],
                    'metadata': {
                        'reservation_id': result['reservation_id']
                    }
                }
            else:
                response = {'response': result['message']}
            
            return jsonify(response)
        
        elif function_name == 'check_reservation_status':
            reservation_id = arguments.get('reservation_id')
            
            if not reservation_id:
                # If no reservation ID provided, check if there's a recent one
                recent_reservations = sorted(
                    [(k, v) for k, v in active_reservations.items()],
                    key=lambda x: x[1]['created_at'],
                    reverse=True
                )
                
                if recent_reservations:
                    reservation_id = recent_reservations[0][0]
                    print(f"Using most recent reservation: {reservation_id}")
                else:
                    response = {
                        'response': "I don't have any active reservation calls. Would you like me to make a new reservation?"
                    }
                    return jsonify(response)
            
            status = agent.check_reservation_status(reservation_id)
            response = {'response': status['message']}
            return jsonify(response)
        
        else:
            # List all available functions for clarity
            available_functions = [
                'search_restaurants', 
                'get_restaurant_details', 
                'make_reservation_call', 
                'check_reservation_status'
            ]
            
            response = {
                'response': f"I received an unknown function: {function_name}. I can help you with these functions: {', '.join(available_functions)}. What would you like to do?"
            }
            print(f"Unknown function '{function_name}'. Available: {available_functions}")
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

@app.route('/retell-webhook', methods=['POST'])
def retell_call_webhook():
    """Webhook to receive call status updates from RetellAI"""
    
    try:
        data = request.json
        event_type = data.get('event')
        
        print(f"Received RetellAI webhook event: {event_type}")
        print(f"Data: {json.dumps(data, indent=2)}")
        
        if event_type == 'call_ended':
            call_data = data.get('call', {})
            metadata = call_data.get('metadata', {})
            
            # Check if this was a reservation call
            if metadata.get('type') == 'restaurant_reservation':
                reservation_id = metadata.get('reservation_id')
                
                if reservation_id and reservation_id in active_reservations:
                    # Analyze the call transcript to determine success
                    transcript = call_data.get('transcript', '')
                    
                    # Simple keyword analysis (in production, use better NLP)
                    confirmed_keywords = ['confirmed', 'booked', 'see you', 'all set', 'reservation for']
                    failed_keywords = ['fully booked', 'no availability', 'closed', 'cannot', "can't"]
                    
                    transcript_lower = transcript.lower()
                    
                    # Check if customer name was mentioned in confirmation
                    customer_name = active_reservations[reservation_id].get('customer_name', '')
                    
                    if any(keyword in transcript_lower for keyword in confirmed_keywords):
                        active_reservations[reservation_id]['status'] = 'confirmed'
                        confirmation_msg = f"The restaurant confirmed your reservation."
                        
                        # Check if they mentioned the customer name
                        if customer_name.lower() in transcript_lower:
                            confirmation_msg += f" They have the reservation under {customer_name}."
                        
                        confirmation_msg += f" Call duration: {call_data.get('duration_seconds', 0)} seconds."
                        active_reservations[reservation_id]['confirmation_details'] = confirmation_msg
                    elif any(keyword in transcript_lower for keyword in failed_keywords):
                        active_reservations[reservation_id]['status'] = 'failed'
                        active_reservations[reservation_id]['failure_reason'] = (
                            "The restaurant couldn't accommodate your reservation request."
                        )
                    else:
                        # Unclear outcome
                        active_reservations[reservation_id]['status'] = 'unclear'
                        active_reservations[reservation_id]['notes'] = (
                            "The call ended but I couldn't determine if the reservation was confirmed. "
                            "You may want to call the restaurant directly."
                        )
                    
                    # Store the transcript for reference
                    active_reservations[reservation_id]['transcript'] = transcript
                    
                    print(f"Updated reservation {reservation_id} status to: {active_reservations[reservation_id]['status']}")
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error in retell webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'restaurant-agent'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

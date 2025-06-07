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
            elif function_name == 'transfer_to_restaurant':
            restaurant_name = arguments.get('restaurant_name')
            date = arguments.get('date')
            time = arguments.get('time')
            party_size = arguments.get('party_size', 2)
            customer_name = arguments.get('customer_name')
            customer_phone = arguments.get('customer_phone')
            location = arguments.get('location')
            
            if not all([restaurant_name, date, time, customer_name, customer_phone]):
                response = {
                    'response': "I need all your details (name, phone, date, time) to transfer you to the restaurant."
                }
                return jsonify(response)
            
            result = agent.prepare_transfer_to_restaurant(
                restaurant_name, date, time, party_size,
                customer_name, customer_phone, location
            )
            
            if result['success']:
                # RetellAI will handle the transfer when it sees transfer_phone_number
                response = {
                    'response': result['message'],
                    'transfer_phone_number': result['transfer_phone_number']
                }
            else:
                response = {'response': result['message']}
            
            return jsonify(response)
        
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
        
        if not place_id:
            print("ERROR: No place_id provided")
            return {}
            
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
        
        print(f"Getting details for place_id: {place_id}")
        
        try:
            # Add timeout to prevent hanging
            response = requests.get(details_url, params=params, timeout=10)
            print(f"Google Places Details API Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"API Error: {response.text}")
                return {}
                
            data = response.json()
            
            if data.get('status') == 'OK':
                result = data.get('result', {})
                
                # Safely process opening hours
                opening_hours = result.get('opening_hours', {})
                hours_text = opening_hours.get('weekday_text', [])
                is_open = opening_hours.get('open_now', None)
                
                # Safely process reviews
                reviews = []
                try:
                    for review in result.get('reviews', [])[:3]:  # Get top 3 reviews
                        reviews.append({
                            'author': review.get('author_name', 'Anonymous'),
                            'rating': review.get('rating', 0),
                            'text': review.get('text', ''),
                            'time': review.get('relative_time_description', '')
                        })
                except Exception as e:
                    print(f"Error processing reviews: {e}")
                
                # Safely get photo references
                photo_refs = []
                try:
                    for photo in result.get('photos', [])[:3]:
                        if photo.get('photo_reference'):
                            photo_refs.append(photo.get('photo_reference'))
                except Exception as e:
                    print(f"Error processing photos: {e}")
                
                # Build response with safe defaults
                details_dict = {
                    'name': result.get('name', 'Unknown'),
                    'phone': result.get('formatted_phone_number'),
                    'address': result.get('formatted_address'),
                    'website': result.get('website'),
                    'rating': result.get('rating'),
                    'user_ratings_total': result.get('user_ratings_total'),
                    'price_level': result.get('price_level'),
                    'is_open_now': is_open,
                    'hours': hours_text,
                    'business_status': result.get('business_status'),
                    'editorial_summary': result.get('editorial_summary', {}).get('overview') if isinstance(result.get('editorial_summary'), dict) else None,
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
                
                print(f"Successfully got details for: {details_dict['name']}")
                return details_dict
            else:
                print(f"Google Places API returned status: {data.get('status')}")
                print(f"Error message: {data.get('error_message', 'No error message')}")
                return {}
        except requests.exceptions.Timeout:
            print("ERROR: Google Places API request timed out")
            return {}
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Network error getting restaurant details: {e}")
            return {}
        except Exception as e:
            print(f"ERROR: Unexpected error getting restaurant details: {e}")
            import traceback
            print(traceback.format_exc())
            return {}
    
    def format_restaurant_info(self, restaurant: Dict) -> str:
        """Format restaurant information for speech output"""
        
        if not restaurant:
            return "I couldn't retrieve the restaurant details."
            
        try:
            info = f"{restaurant.get('name', 'This restaurant')} "
            
            if restaurant.get('rating') and restaurant.get('user_ratings_total'):
                info += f"has a rating of {restaurant['rating']} stars based on {restaurant['user_ratings_total']} reviews. "
            elif restaurant.get('rating'):
                info += f"has a rating of {restaurant['rating']} stars. "
            
            if restaurant.get('price_level'):
                price_desc = ['inexpensive', 'moderate', 'expensive', 'very expensive']
                price_idx = min(int(restaurant['price_level']) - 1, 3)
                if price_idx >= 0:
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
            if restaurant.get('reviews') and len(restaurant['reviews']) > 0:
                info += "\n\nHere are some recent customer reviews:\n"
                for i, review in enumerate(restaurant['reviews'], 1):
                    try:
                        review_text = review.get('text', '')
                        if review_text:
                            truncated_text = review_text[:150] + '...' if len(review_text) > 150 else review_text
                            info += f"\n{i}. {review.get('author', 'A customer')} rated it {review.get('rating', 'N/A')} stars"
                            if review.get('time'):
                                info += f" {review['time']}"
                            info += f' and said: "{truncated_text}"'
                    except Exception as e:
                        print(f"Error formatting review: {e}")
                        continue
            
            return info
            
        except Exception as e:
            print(f"Error formatting restaurant info: {e}")
            import traceback
            print(traceback.format_exc())
            return f"I found {restaurant.get('name', 'the restaurant')} but had trouble formatting the details."
    
    def format_phone_number_e164(self, phone: str) -> str:
        """Convert phone number to E.164 format for RetellAI"""
        if not phone:
            print("WARNING: No phone number provided")
            return None
            
        print(f"Formatting phone number: {phone}")
        
        # Remove all non-digit characters
        phone_digits = ''.join(filter(str.isdigit, phone))
        print(f"Digits only: {phone_digits}")
        
        # Assume US number if 10 digits without country code
        if len(phone_digits) == 10:
            formatted = f"+1{phone_digits}"
        elif len(phone_digits) == 11 and phone_digits.startswith('1'):
            formatted = f"+{phone_digits}"
        else:
            # Try to use as-is with + prefix
            formatted = f"+{phone_digits}"
            
        print(f"Formatted to E.164: {formatted}")
        return formatted
    
    def make_reservation_call(self, restaurant_name: str, date: str, time: str, party_size: int, 
                            customer_name: str, customer_phone: str, location: str = None, 
                            special_requests: str = None, caller_call_id: str = None) -> Dict:
        """Initiates an outbound call to make a reservation"""
        
        print(f"make_reservation_call called with: restaurant={restaurant_name}, date={date}, time={time}")
        print(f"Environment check: RETELL_API_KEY={'SET' if RETELL_API_KEY else 'NOT SET'}")
        print(f"Environment check: RESTAURANT_CALLER_AGENT_ID={RESTAURANT_CALLER_AGENT_ID or 'NOT SET'}")
        print(f"Environment check: RETELL_PHONE_NUMBER={RETELL_PHONE_NUMBER or 'NOT SET'}")
        
        if not RETELL_API_KEY:
            return {
                'success': False,
                'message': "I'm not configured with a RetellAI API key. Please set RETELL_API_KEY environment variable."
            }
            
        if not RESTAURANT_CALLER_AGENT_ID:
            return {
                'success': False,
                'message': "I'm not configured with a Restaurant Caller Agent ID. Please set RESTAURANT_CALLER_AGENT_ID environment variable."
            }
            
        if not RETELL_PHONE_NUMBER:
            return {
                'success': False,
                'message': "I'm not configured with a phone number. Please set RETELL_PHONE_NUMBER environment variable."
            }
        
        # Validate customer information
        if not customer_name or not customer_phone:
            return {
                'success': False,
                'message': "I need your name and phone number to make the reservation. Could you please provide them?"
            }
        
        # First, find the restaurant and get its phone number
        search_query = f"{restaurant_name} {location}" if location else restaurant_name
        print(f"Searching for restaurant: {search_query}")
        
        # Handle test case
        if restaurant_name.lower() == "test" or restaurant_name.lower() == "test restaurant":
            print("TEST MODE: Using test restaurant details")
            details = {
                'name': 'Test Restaurant',
                'phone': '(626) 698-9990'  # Use a real test number you control
            }
            phone_e164 = '+16266989990'  # This is what will be DIALED
        else:
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
        
        print(f"Restaurant found: {details['name']}")
        print(f"Restaurant phone (original): {details['phone']}")
        print(f"Restaurant phone (E.164): {phone_e164}")
        
        # Create a unique reservation ID
        reservation_id = str(uuid.uuid4())
        
        # Store reservation details with caller's call ID for real-time updates
        active_reservations[reservation_id] = {
            'restaurant_name': details['name'],
            'restaurant_phone': phone_e164,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'date': date,
            'time': time,
            'party_size': party_size,
            'special_requests': special_requests,
            'status': 'calling',
            'created_at': datetime.now().isoformat(),
            'caller_call_id': caller_call_id  # Track which caller to update
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
        
        print(f"Dynamic variables being sent: {json.dumps(dynamic_variables, indent=2)}")
        
        # Prepare the API call data
        data = {
            'from_number': RETELL_PHONE_NUMBER,
            'to_number': phone_e164,
            'agent_id': RESTAURANT_CALLER_AGENT_ID,
            'metadata': {
                'reservation_id': reservation_id,
                'type': 'restaurant_reservation',
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'caller_call_id': caller_call_id
            },
            'retell_llm_dynamic_variables': dynamic_variables  # Changed from 'dynamic_variables'
        }
        
        print(f"Making RetellAI API call:")
        print(f"URL: https://api.retellai.com/v2/create-phone-call")
        print(f"Headers: {headers}")
        print(f"Data: {json.dumps(data, indent=2)}")
        
        try:
            response = requests.post(
                'https://api.retellai.com/v2/create-phone-call',  # v2 is the correct endpoint
                headers=headers,
                json=data
            )
            
            print(f"RetellAI API Response Code: {response.status_code}")
            print(f"RetellAI API Response: {response.text}")
            
            if response.status_code in [200, 201]:
                call_data = response.json()
                active_reservations[reservation_id]['call_id'] = call_data.get('call_id')
                
                # Start a background check for updates (in production, use proper async)
                def check_and_notify():
                    time.sleep(60)  # Wait 60 seconds
                    status = self.check_reservation_status(reservation_id)
                    # Here you would trigger an update to the caller
                    print(f"Reservation {reservation_id} status: {status}")
                
                # In production, use proper async handling
                # threading.Thread(target=check_and_notify).start()
                
                return {
                    'success': True,
                    'reservation_id': reservation_id,
                    'call_id': call_data.get('call_id'),  # Return the call ID
                    'message': f"I'm calling {details['name']} now to make a reservation for {customer_name}, "
                             f"party of {party_size} on {date} at {time}. "
                             f"I'll update you as soon as the call completes. In the meantime, "
                             f"feel free to ask me anything else or say 'check my reservation' for an update."
                }
            else:
                print(f"RetellAI API error: {response.status_code} - {response.text}")
                error_msg = "I encountered an error trying to call the restaurant."
                
                # Parse specific error messages
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg += f" Error: {error_data['message']}"
                except:
                    pass
                    
                return {
                    'success': False,
                    'message': f"{error_msg} Would you like me to provide their number so you can call directly?"
                }
                
        except Exception as e:
            print(f"Error making outbound call: {e}")
            return {
                'success': False,
                'message': "I couldn't complete the call. Would you like the restaurant's phone number instead?"
            }
    
    def check_reservation_status(self, reservation_id: str, force_refresh: bool = True) -> Dict:
        """Check the status of a reservation call"""
        
        print(f"Checking reservation status for ID: {reservation_id}")
        print(f"Active reservations: {list(active_reservations.keys())}")
        print(f"Reservation details: {active_reservations.get(reservation_id, 'NOT FOUND')}")
        
        if reservation_id not in active_reservations:
            return {
                'found': False,
                'message': "I couldn't find that reservation. It may have expired or the ID is incorrect."
            }
        
        reservation = active_reservations[reservation_id]
        status = reservation['status']
        
        # ALWAYS check if we have a call_id and force_refresh is True
        if 'call_id' in reservation and force_refresh:
            print(f"Force checking call status for {reservation['call_id']}")
            
            # Try to get call status from RetellAI API
            headers = {
                'Authorization': f'Bearer {RETELL_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            try:
                response = requests.get(
                    f'https://api.retellai.com/v2/get-call/{reservation["call_id"]}',
                    headers=headers
                )
                
                if response.ok:
                    call_data = response.json()
                    print(f"Got call data: {call_data.get('call_status')}")
                    
                    # If call ended, analyze transcript
                    if call_data.get('call_status') in ['ended', 'analyzed']:
                        transcript = call_data.get('transcript', '')
                        print(f"Call ended, analyzing transcript: {transcript[:200]}...")
                        
                        # Analyze transcript
                        transcript_lower = transcript.lower()
                        if any(word in transcript_lower for word in ['confirmed', 'booked', 'see you', 'all set', 'reservation for']):
                            reservation['status'] = 'confirmed'
                            reservation['confirmation_details'] = "The restaurant confirmed your reservation."
                        elif any(word in transcript_lower for word in ['fully booked', 'no availability', 'closed', 'cannot']):
                            reservation['status'] = 'failed'
                            reservation['failure_reason'] = "The restaurant couldn't accommodate your reservation."
                        else:
                            reservation['status'] = 'unclear'
                            reservation['notes'] = "The call ended but the outcome is unclear."
                        
                        reservation['transcript'] = transcript
                        reservation['manual_check'] = True
                        status = reservation['status']  # Update status variable
            except Exception as e:
                print(f"Error manually checking call status: {e}")
        
        # Return status message based on current state
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

    def prepare_transfer_to_restaurant(self, restaurant_name: str, date: str, time: str, 
                                      party_size: int, customer_name: str, customer_phone: str,
                                      location: str = None) -> Dict:
        """Prepare to transfer the call to restaurant with context"""
        
        # Find restaurant and get phone
        search_query = f"{restaurant_name} {location}" if location else restaurant_name
        restaurants = self.search_restaurants(search_query)
        
        if not restaurants:
            return {
                'success': False,
                'message': f"I couldn't find {restaurant_name}. Could you provide more details?"
            }
        
        # Get details
        place_id = restaurants[0]['place_id']
        details = self.get_restaurant_details(place_id)
        
        if not details or not details.get('phone'):
            return {
                'success': False,
                'message': f"I found {restaurant_name} but couldn't get their phone number."
            }
        
        # Format phone for transfer
        phone_e164 = self.format_phone_number_e164(details['phone'])
        
        # Prepare transfer message
        transfer_message = (
            f"I'm going to transfer you to {details['name']} now. "
            f"When they answer, you can make your reservation for {party_size} people "
            f"on {date} at {time}. Your name is {customer_name} and your phone is {customer_phone}. "
            f"I'll stay on the line to help if needed."
        )
        
        return {
            'success': True,
            'transfer_phone_number': phone_e164,
            'message': transfer_message
        }

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
        supported_functions = ['search_restaurants', 'get_restaurant_details', 'make_reservation_call', 'check_reservation_status', 'transfer_to_restaurant']
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
                place_id = restaurants[0].get('place_id')
                
                if not place_id:
                    response = {
                        'response': f"I found {restaurant_name} but couldn't get its details. Please try again."
                    }
                    return jsonify(response)
                
                print(f"Getting details for place_id: {place_id}")
                details = agent.get_restaurant_details(place_id)
                
                if details:
                    try:
                        response_text = agent.format_restaurant_info(details)
                        
                        if details.get('phone'):
                            response_text += f"\n\nTheir phone number is {details['phone']}. Would you like me to repeat that?"
                        
                        if details.get('website'):
                            response_text += f" They also have a website for online reservations. "
                        
                        if details.get('hours'):
                            response_text += "\n\nWould you like to hear their hours of operation?"
                        
                        response = {'response': response_text}
                        return jsonify(response)
                    except Exception as e:
                        print(f"Error formatting restaurant details: {e}")
                        response = {
                            'response': f"I found {restaurant_name} but had trouble processing the details. The restaurant is rated {details.get('rating', 'N/A')} stars."
                        }
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
            
            # Get the current call ID from the request data
            caller_call_id = data.get('call_id') or data.get('call', {}).get('call_id')
            
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
                customer_name, customer_phone, location, special_requests,
                caller_call_id=caller_call_id  # Pass the current call ID
            )
            
            if result['success']:
                # Store the reservation ID and call ID for tracking
                response = {
                    'response': result['message'] + "\n\nI'll check back with you in about a minute to let you know if they confirmed your reservation.",
                    'metadata': {
                        'reservation_id': result['reservation_id'],
                        'call_id': result.get('call_id')  # Store call ID for manual checking
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
                'check_reservation_status',
                'transfer_to_restaurant'
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

@app.route('/test-places-api', methods=['GET'])
def test_places_api():
    """Test Google Places API is working"""
    
    if not GOOGLE_PLACES_API_KEY:
        return jsonify({'error': 'Google Places API key not set'}), 500
    
    # Test with a known restaurant
    test_query = request.args.get('query', 'Pizza in New York')
    
    try:
        # Test search
        search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            'query': test_query,
            'key': GOOGLE_PLACES_API_KEY
        }
        
        search_response = requests.get(search_url, params=params, timeout=5)
        search_data = search_response.json()
        
        result = {
            'search_status': search_data.get('status'),
            'search_results_count': len(search_data.get('results', [])),
            'api_key_first_10': GOOGLE_PLACES_API_KEY[:10] + '...'
        }
        
        if search_data.get('status') == 'OK' and search_data.get('results'):
            # Try to get details for first result
            first_place = search_data['results'][0]
            place_id = first_place.get('place_id')
            
            if place_id:
                details_url = f"https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {
                    'place_id': place_id,
                    'fields': 'name,rating,formatted_phone_number',
                    'key': GOOGLE_PLACES_API_KEY
                }
                
                details_response = requests.get(details_url, params=details_params, timeout=5)
                details_data = details_response.json()
                
                result['details_status'] = details_data.get('status')
                if details_data.get('status') == 'OK':
                    result['sample_restaurant'] = details_data.get('result', {})
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e), 'api_key_set': bool(GOOGLE_PLACES_API_KEY)}), 500

@app.route('/force-check-all', methods=['GET'])
def force_check_all():
    """Force check all calling reservations"""
    updated = []
    
    for res_id, reservation in active_reservations.items():
        if reservation['status'] == 'calling' and 'call_id' in reservation:
            # Force check this reservation
            result = agent.check_reservation_status(res_id, force_refresh=True)
            updated.append({
                'reservation_id': res_id,
                'old_status': 'calling',
                'new_status': active_reservations[res_id]['status'],
                'restaurant': reservation['restaurant_name']
            })
    
    return jsonify({
        'checked': len(updated),
        'updated_reservations': updated
    })

@app.route('/test-last-call', methods=['GET'])
def test_last_call():
    """Check the status of the most recent call"""
    
    # Get the most recent reservation
    if not active_reservations:
        return jsonify({'error': 'No active reservations'})
    
    recent_reservation = sorted(
        active_reservations.items(),
        key=lambda x: x[1]['created_at'],
        reverse=True
    )[0]
    
    reservation_id, reservation = recent_reservation
    call_id = reservation.get('call_id')
    
    if not call_id:
        return jsonify({'error': 'No call_id found for recent reservation'})
    
    # Check call status via API
    headers = {
        'Authorization': f'Bearer {RETELL_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(
            f'https://api.retellai.com/v2/get-call/{call_id}',
            headers=headers
        )
        
        if response.ok:
            call_data = response.json()
            return jsonify({
                'reservation_id': reservation_id,
                'call_id': call_id,
                'call_status': call_data.get('call_status'),
                'duration': call_data.get('duration_seconds'),
                'end_timestamp': call_data.get('end_timestamp'),
                'transcript_length': len(call_data.get('transcript', '')),
                'transcript_preview': call_data.get('transcript', '')[:200] + '...' if call_data.get('transcript') else 'No transcript',
                'stored_status': reservation['status'],
                'webhook_received': reservation.get('webhook_received', False)
            })
        else:
            return jsonify({'error': 'Failed to get call', 'details': response.text})
            
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/check-call/<call_id>', methods=['GET'])
def check_call_status(call_id):
    """Manually check a call's status using RetellAI API"""
    headers = {
        'Authorization': f'Bearer {RETELL_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(
            f'https://api.retellai.com/v2/get-call/{call_id}',
            headers=headers
        )
        
        if response.ok:
            call_data = response.json()
            
            # Update reservation if this was a reservation call
            metadata = call_data.get('metadata', {})
            if metadata.get('type') == 'restaurant_reservation':
                reservation_id = metadata.get('reservation_id')
                if reservation_id and reservation_id in active_reservations:
                    # Manually trigger the same logic as webhook
                    transcript = call_data.get('transcript', '')
                    
                    # Analyze transcript
                    if 'confirmed' in transcript.lower():
                        active_reservations[reservation_id]['status'] = 'confirmed'
                    elif 'fully booked' in transcript.lower():
                        active_reservations[reservation_id]['status'] = 'failed'
                    
                    active_reservations[reservation_id]['transcript'] = transcript
            
            return jsonify({
                'call_id': call_id,
                'status': call_data.get('call_status'),
                'duration': call_data.get('duration_seconds'),
                'transcript_preview': call_data.get('transcript', '')[:200] + '...',
                'metadata': metadata
            })
        else:
            return jsonify({'error': 'Failed to get call status', 'details': response.text}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/webhook-test', methods=['POST', 'GET'])
def webhook_test():
    """Test endpoint to log any webhook calls"""
    print("\n" + "="*50)
    print("WEBHOOK TEST ENDPOINT HIT")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    if request.method == 'POST':
        print(f"Body: {request.get_data(as_text=True)}")
    print("="*50 + "\n")
    return jsonify({'status': 'received'}), 200

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
                    
                    # IMPORTANT: Send update to the original caller
                    # Get the caller's call ID from the reservation
                    caller_call_id = active_reservations[reservation_id].get('caller_call_id')
                    
                    if caller_call_id and RETELL_API_KEY:
                        # Use RetellAI API to send a message to the active call
                        try:
                            update_headers = {
                                'Authorization': f'Bearer {RETELL_API_KEY}',
                                'Content-Type': 'application/json'
                            }
                            
                            # Prepare a message based on status
                            if active_reservations[reservation_id]['status'] == 'confirmed':
                                update_message = (
                                    f"Great news! I just finished speaking with {active_reservations[reservation_id]['restaurant_name']}. "
                                    f"Your reservation is confirmed for {active_reservations[reservation_id]['party_size']} people "
                                    f"on {active_reservations[reservation_id]['date']} at {active_reservations[reservation_id]['time']}."
                                )
                            else:
                                update_message = (
                                    f"I just finished speaking with {active_reservations[reservation_id]['restaurant_name']}. "
                                    f"Unfortunately, they couldn't accommodate your reservation request. "
                                    f"Would you like me to try another restaurant?"
                                )
                            
                            # Send update to the caller
                            # Note: This endpoint might not exist - check RetellAI docs
                            update_data = {
                                'call_id': caller_call_id,
                                'message': update_message
                            }
                            
                            # This is a hypothetical endpoint - RetellAI might not support this
                            # update_response = requests.post(
                            #     f'https://api.retellai.com/v2/update-call',
                            #     headers=update_headers,
                            #     json=update_data
                            # )
                            
                            print(f"Would send update to caller: {update_message}")
                            
                        except Exception as e:
                            print(f"Error sending update to caller: {e}")
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error in retell webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/debug-reservations', methods=['GET'])
def debug_reservations():
    """Debug endpoint to check active reservations"""
    return jsonify({
        'active_reservations_count': len(active_reservations),
        'reservation_ids': list(active_reservations.keys()),
        'reservations': {
            k: {
                'status': v.get('status'),
                'restaurant': v.get('restaurant_name'),
                'customer': v.get('customer_name'),
                'date_time': f"{v.get('date')} at {v.get('time')}",
                'created_at': v.get('created_at')
            }
            for k, v in active_reservations.items()
        }
    })

@app.route('/test-dynamic-variables', methods=['GET'])
def test_dynamic_variables():
    """Test endpoint to verify dynamic variables work"""
    
    if not RETELL_API_KEY or not RESTAURANT_CALLER_AGENT_ID:
        return jsonify({'error': 'Missing API key or agent ID'}), 500
    
    headers = {
        'Authorization': f'Bearer {RETELL_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # Test with dynamic variables
    test_data = {
        'from_number': RETELL_PHONE_NUMBER or '+14157774444',
        'to_number': '+15551234567',  # Safe test number
        'agent_id': RESTAURANT_CALLER_AGENT_ID,
        'retell_llm_dynamic_variables': {  # Changed from 'dynamic_variables'
            'restaurant_name': 'Test Restaurant',
            'customer_name': 'Test Customer',
            'customer_phone': '555-111-2222',
            'date': 'tomorrow',
            'time': '7:00 PM',
            'party_size': '2',
            'special_requests': 'none'
        },
        'metadata': {'test': True}
    }
    
    try:
        response = requests.post(
            'https://api.retellai.com/v2/create-phone-call',
            headers=headers,
            json=test_data
        )
        
        return jsonify({
            'status_code': response.status_code,
            'response': response.json() if response.status_code in [200, 201] else response.text,
            'retell_llm_dynamic_variables_sent': test_data['retell_llm_dynamic_variables']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/test-outbound-call', methods=['GET'])
def test_outbound_call():
    """Test endpoint to verify RetellAI outbound calling setup"""
    
    if not RETELL_API_KEY:
        return jsonify({'error': 'RETELL_API_KEY not set'}), 500
    
    if not RESTAURANT_CALLER_AGENT_ID:
        return jsonify({'error': 'RESTAURANT_CALLER_AGENT_ID not set'}), 500
    
    # Test API call to RetellAI
    headers = {
        'Authorization': f'Bearer {RETELL_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # Try to validate the agent exists
    test_data = {
        'from_number': RETELL_PHONE_NUMBER or '+14157774444',
        'to_number': '+14157774445',  # Test number
        'agent_id': RESTAURANT_CALLER_AGENT_ID,
        'metadata': {'test': True}
    }
    
    try:
        # Try different API endpoints
        endpoints = [
            'https://api.retellai.com/create-phone-call',
            'https://api.retellai.com/v1/create-phone-call',
            'https://api.retellai.com/v2/create-phone-call'
        ]
        
        results = {}
        for endpoint in endpoints:
            response = requests.post(endpoint, headers=headers, json=test_data)
            results[endpoint] = {
                'status_code': response.status_code,
                'response': response.text[:200]  # First 200 chars
            }
        
        return jsonify({
            'api_key_preview': f"{RETELL_API_KEY[:10]}...",
            'agent_id': RESTAURANT_CALLER_AGENT_ID,
            'phone_number': RETELL_PHONE_NUMBER,
            'test_results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug-env', methods=['GET'])
def debug_env():
    """Debug endpoint to check environment variables"""
    return jsonify({
        'RETELL_API_KEY_set': bool(RETELL_API_KEY),
        'RETELL_API_KEY_preview': f"{RETELL_API_KEY[:10]}..." if RETELL_API_KEY else "NOT SET",
        'RESTAURANT_CALLER_AGENT_ID_set': bool(RESTAURANT_CALLER_AGENT_ID),
        'RESTAURANT_CALLER_AGENT_ID': RESTAURANT_CALLER_AGENT_ID or "NOT SET",
        'RETELL_PHONE_NUMBER': RETELL_PHONE_NUMBER or "NOT SET"
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'restaurant-agent'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

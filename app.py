import os
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Any
import uuid
import time
from dataclasses import dataclass, asdict
from enum import Enum

app = Flask(__name__)

# Configuration
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
RETELL_API_KEY = os.environ.get('RETELL_API_KEY')
RETELL_PHONE_NUMBER = os.environ.get('RETELL_PHONE_NUMBER', '+14157774444')  # Your RetellAI number
RESTAURANT_CALLER_AGENT_ID = os.environ.get('RESTAURANT_CALLER_AGENT_ID')  # Your second agent
INBOUND_AGENT_ID = os.environ.get('INBOUND_AGENT_ID')  # Your inbound agent ID

# Add startup check
if not GOOGLE_PLACES_API_KEY:
    print("WARNING: GOOGLE_PLACES_API_KEY not set in environment variables!")
else:
    print(f"Google Places API Key loaded: {GOOGLE_PLACES_API_KEY[:10]}...")

if not RETELL_API_KEY:
    print("WARNING: RETELL_API_KEY not set in environment variables!")

if not RESTAURANT_CALLER_AGENT_ID:
    print("WARNING: RESTAURANT_CALLER_AGENT_ID not set - outbound calling won't work!")

if not INBOUND_AGENT_ID:
    print("WARNING: INBOUND_AGENT_ID not set - status updates may not work optimally!")

# Enhanced reservation status system
class ReservationStatus(Enum):
    INITIATED = "initiated"
    CALLING_RESTAURANT = "calling_restaurant"
    SPEAKING_WITH_RESTAURANT = "speaking_with_restaurant"
    CHECKING_AVAILABILITY = "checking_availability"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    RESTAURANT_BUSY = "restaurant_busy"
    NO_ANSWER = "no_answer"
    ERROR = "error"

@dataclass
class ReservationRequest:
    reservation_id: str
    customer_name: str
    phone_number: str
    restaurant_name: str
    restaurant_phone: str
    date: str
    time: str
    party_size: int
    special_requests: str = None
    status: ReservationStatus = ReservationStatus.INITIATED
    inbound_call_id: str = None
    outbound_call_id: str = None
    created_at: datetime = None
    updated_at: datetime = None
    status_history: List[Dict] = None
    transcript: str = ""
    confirmation_details: str = ""
    failure_reason: str = ""

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.status_history is None:
            self.status_history = []

# Enhanced in-memory storage with status tracking
active_reservations = {}
pending_updates = {}  # call_id -> list of status messages

class ReservationCoordinator:
    def __init__(self):
        self.reservations = active_reservations
        self.pending_updates = pending_updates
    
    def create_reservation(self, customer_name: str, phone_number: str, 
                          restaurant_name: str, restaurant_phone: str,
                          date: str, time: str, party_size: int,
                          special_requests: str = None, inbound_call_id: str = None) -> str:
        """Create a new reservation request"""
        reservation_id = str(uuid.uuid4())
        
        reservation = ReservationRequest(
            reservation_id=reservation_id,
            customer_name=customer_name,
            phone_number=phone_number,
            restaurant_name=restaurant_name,
            restaurant_phone=restaurant_phone,
            date=date,
            time=time,
            party_size=party_size,
            special_requests=special_requests,
            inbound_call_id=inbound_call_id
        )
        
        self.reservations[reservation_id] = reservation
        self._add_status_history(reservation_id, ReservationStatus.INITIATED, 
                               "Reservation request created")
        
        return reservation_id
    
    def update_reservation_status(self, reservation_id: str, status: ReservationStatus, 
                                details: str, call_id: str = None) -> bool:
        """Update reservation status with details"""
        if reservation_id not in self.reservations:
            return False
        
        reservation = self.reservations[reservation_id]
        old_status = reservation.status
        reservation.status = status
        reservation.updated_at = datetime.now()
        
        # Track which call made this update
        if call_id and call_id == reservation.outbound_call_id:
            update_source = "outbound_agent"
        elif call_id and call_id == reservation.inbound_call_id:
            update_source = "inbound_agent"
        else:
            update_source = "system"
        
        self._add_status_history(reservation_id, status, details, update_source)
        
        # Add pending update for the other agent
        self._queue_update_for_other_agent(reservation, call_id, status, details)
        
        print(f"Reservation {reservation_id} status updated: {old_status.value} -> {status.value}")
        print(f"Details: {details}")
        
        return True
    
    def get_pending_updates(self, call_id: str) -> List[str]:
        """Get and clear pending updates for a specific call"""
        updates = self.pending_updates.get(call_id, [])
        if call_id in self.pending_updates:
            del self.pending_updates[call_id]
        return updates
    
    def set_outbound_call_id(self, reservation_id: str, call_id: str) -> bool:
        """Associate outbound call ID with reservation"""
        if reservation_id not in self.reservations:
            return False
        
        self.reservations[reservation_id].outbound_call_id = call_id
        return True
    
    def get_reservation_by_call_id(self, call_id: str) -> Dict:
        """Find reservation by inbound or outbound call ID"""
        for reservation in self.reservations.values():
            if reservation.inbound_call_id == call_id or reservation.outbound_call_id == call_id:
                return asdict(reservation)
        return None
    
    def _add_status_history(self, reservation_id: str, status: ReservationStatus, 
                           details: str, source: str = "system"):
        """Add entry to status history"""
        reservation = self.reservations[reservation_id]
        reservation.status_history.append({
            "timestamp": datetime.now().isoformat(),
            "status": status.value,
            "details": details,
            "source": source
        })
    
    def _queue_update_for_other_agent(self, reservation: ReservationRequest, 
                                    current_call_id: str, status: ReservationStatus, details: str):
        """Queue update for the other agent (inbound or outbound)"""
        target_call_id = None
        
        if current_call_id == reservation.inbound_call_id:
            # Update came from inbound agent, notify outbound agent
            target_call_id = reservation.outbound_call_id
        elif current_call_id == reservation.outbound_call_id:
            # Update came from outbound agent, notify inbound agent
            target_call_id = reservation.inbound_call_id
        
        if target_call_id:
            if target_call_id not in self.pending_updates:
                self.pending_updates[target_call_id] = []
            
            update_message = self._format_status_message(status, details, 
                                                       current_call_id == reservation.outbound_call_id)
            self.pending_updates[target_call_id].append(update_message)
    
    def _format_status_message(self, status: ReservationStatus, details: str, 
                             from_outbound: bool) -> str:
        """Format status update message for agents"""
        if from_outbound:
            # Message for inbound agent about outbound progress
            status_messages = {
                ReservationStatus.CALLING_RESTAURANT: f"I'm calling the restaurant now. {details}",
                ReservationStatus.SPEAKING_WITH_RESTAURANT: f"I'm speaking with the restaurant. {details}",
                ReservationStatus.CHECKING_AVAILABILITY: f"The restaurant is checking availability. {details}",
                ReservationStatus.CONFIRMED: f"Great news! Your reservation is confirmed. {details}",
                ReservationStatus.DECLINED: f"I'm sorry, the restaurant cannot accommodate your request. {details}",
                ReservationStatus.RESTAURANT_BUSY: f"The restaurant line is busy. {details}",
                ReservationStatus.NO_ANSWER: f"The restaurant is not answering. {details}",
                ReservationStatus.ERROR: f"There was an issue with the booking. {details}"
            }
        else:
            # Message for outbound agent about inbound updates
            status_messages = {
                ReservationStatus.INITIATED: f"Customer update: {details}",
            }
        
        return status_messages.get(status, f"Status update: {details}")

# Global coordinator instance
coordinator = ReservationCoordinator()

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
        
        # Create a new reservation using the coordinator
        reservation_id = coordinator.create_reservation(
            customer_name=customer_name,
            phone_number=customer_phone,
            restaurant_name=details['name'],
            restaurant_phone=phone_e164,
            date=date,
            time=time,
            party_size=party_size,
            special_requests=special_requests,
            inbound_call_id=caller_call_id
        )
        
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
            'special_requests': special_requests or 'none',
            'reservation_id': reservation_id  # Pass reservation ID to outbound agent
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
                outbound_call_id = call_data.get('call_id')
                
                # Associate outbound call ID with reservation
                coordinator.set_outbound_call_id(reservation_id, outbound_call_id)
                
                # Update status to calling
                coordinator.update_reservation_status(
                    reservation_id=reservation_id,
                    status=ReservationStatus.CALLING_RESTAURANT,
                    details=f"Outbound call initiated to {details['name']}",
                    call_id=outbound_call_id
                )
                
                return {
                    'success': True,
                    'reservation_id': reservation_id,
                    'message': f"I'm calling {details['name']} now to make a reservation for {customer_name}, "
                             f"party of {party_size} on {date} at {time}. "
                             f"I'll update you as soon as the call progresses. Please hold on."
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
    
    def check_reservation_status(self, reservation_id: str) -> Dict:
        """Check the status of a reservation call"""
        
        if reservation_id not in active_reservations:
            return {
                'found': False,
                'message': "I couldn't find that reservation. It may have expired or the ID is incorrect."
            }
        
        reservation = active_reservations[reservation_id]
        status = reservation.status
        
        if status == ReservationStatus.CALLING_RESTAURANT:
            return {
                'found': True,
                'status': 'calling',
                'message': f"I'm still trying to reach {reservation.restaurant_name}. Please hold on."
            }
        elif status == ReservationStatus.SPEAKING_WITH_RESTAURANT:
            return {
                'found': True,
                'status': 'speaking',
                'message': f"I'm currently speaking with {reservation.restaurant_name} about your reservation."
            }
        elif status == ReservationStatus.CHECKING_AVAILABILITY:
            return {
                'found': True,
                'status': 'checking',
                'message': f"The restaurant is checking their availability for your requested time."
            }
        elif status == ReservationStatus.CONFIRMED:
            return {
                'found': True,
                'status': 'confirmed',
                'message': f"Great news! Your reservation at {reservation.restaurant_name} is confirmed for "
                         f"{reservation.customer_name}, party of {reservation.party_size} on {reservation.date} at {reservation.time}. "
                         f"They have your phone number {reservation.phone_number} on file. "
                         f"{reservation.confirmation_details}"
            }
        elif status == ReservationStatus.DECLINED:
            return {
                'found': True,
                'status': 'declined',
                'message': f"I couldn't make the reservation at {reservation.restaurant_name}. "
                         f"{reservation.failure_reason} "
                         f"Would you like me to try another restaurant?"
            }
        else:
            return {
                'found': True,
                'status': status.value,
                'message': f"The reservation status is: {status.value}"
            }

agent = RestaurantAgent()

# =============================================================================
# FUNCTION DEFINITIONS FOR AGENTS
# =============================================================================

# Functions for INBOUND agent (customer-facing)
def create_new_reservation(customer_name: str, phone_number: str, 
                          restaurant_name: str, date: str, time: str, 
                          party_size: int, location: str = "", 
                          special_requests: str = "", call_id: str = "") -> str:
    """Create a new reservation request and initiate the booking process."""
    try:
        result = agent.make_reservation_call(
            restaurant_name=restaurant_name,
            date=date,
            time=time,
            party_size=party_size,
            customer_name=customer_name,
            customer_phone=phone_number,
            location=location,
            special_requests=special_requests,
            caller_call_id=call_id
        )
        
        return result['message']
        
    except Exception as e:
        return f"I apologize, there was an error creating your reservation request. Please try again. Error: {str(e)}"

def check_reservation_status_updates(call_id: str) -> str:
    """Check for any status updates from the outbound agent."""
    try:
        # Get any pending updates for this call
        updates = coordinator.get_pending_updates(call_id)
        
        if updates:
            # Return the most recent update
            return updates[-1]
        
        # If no pending updates, check if we can find the reservation by call ID
        reservation_data = coordinator.get_reservation_by_call_id(call_id)
        if reservation_data:
            status = reservation_data['status']
            if status == 'calling_restaurant':
                return "I'm still trying to reach the restaurant. Please hold on."
            elif status == 'speaking_with_restaurant':
                return "I'm currently speaking with the restaurant about your reservation."
            elif status == 'checking_availability':
                return "The restaurant is checking their availability for your requested time."
            elif status == 'confirmed':
                return "Your reservation has been confirmed!"
            elif status == 'declined':
                return "Unfortunately, the restaurant cannot accommodate your request."
        
        return "I'm still working on your reservation. Let me continue checking."
        
    except Exception as e:
        return "Let me continue working on your reservation. I'll have an update shortly."

def get_reservation_final_status(reservation_id: str) -> str:
    """Get the final status of a reservation for the customer."""
    try:
        result = agent.check_reservation_status(reservation_id)
        return result['message']
            
    except Exception as e:
        return "I'm still working on getting you a final answer about your reservation."

# Functions for OUTBOUND agent (restaurant-facing)
def start_restaurant_call(reservation_id: str, call_id: str) -> str:
    """Indicate that the outbound call to the restaurant has started."""
    try:
        coordinator.set_outbound_call_id(reservation_id, call_id)
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.CALLING_RESTAURANT,
            details=f"Outbound call initiated to restaurant",
            call_id=call_id
        )
        return "Call status updated. Beginning restaurant outreach."
        
    except Exception as e:
        return f"Error updating call status: {str(e)}"

def restaurant_answered(reservation_id: str, call_id: str) -> str:
    """Indicate that the restaurant has answered the phone."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.SPEAKING_WITH_RESTAURANT,
            details="Restaurant representative answered the phone",
            call_id=call_id
        )
        return "Status updated - now speaking with restaurant."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def restaurant_checking_availability(reservation_id: str, call_id: str, details: str = "") -> str:
    """Indicate that the restaurant is checking availability."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.CHECKING_AVAILABILITY,
            details=details or "Restaurant is checking availability in their system",
            call_id=call_id
        )
        return "Status updated - restaurant is checking availability."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def reservation_confirmed_by_restaurant(reservation_id: str, call_id: str, 
                                      confirmation_details: str = "") -> str:
    """Indicate that the restaurant has confirmed the reservation."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.CONFIRMED,
            details=confirmation_details or "Restaurant confirmed the reservation",
            call_id=call_id
        )
        
        # Update the reservation object with confirmation details
        if reservation_id in active_reservations:
            active_reservations[reservation_id].confirmation_details = confirmation_details
        
        return "Excellent! Reservation confirmed. Status updated."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def reservation_declined_by_restaurant(reservation_id: str, call_id: str, 
                                     reason: str = "") -> str:
    """Indicate that the restaurant cannot accommodate the reservation."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.DECLINED,
            details=reason or "Restaurant cannot accommodate the requested time",
            call_id=call_id
        )
        
        # Update the reservation object with failure reason
        if reservation_id in active_reservations:
            active_reservations[reservation_id].failure_reason = reason
        
        return "Status updated - reservation declined by restaurant."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def restaurant_line_busy(reservation_id: str, call_id: str) -> str:
    """Indicate that the restaurant line is busy."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.RESTAURANT_BUSY,
            details="Restaurant phone line is busy, will retry",
            call_id=call_id
        )
        return "Restaurant line is busy. Status updated."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def restaurant_no_answer(reservation_id: str, call_id: str) -> str:
    """Indicate that the restaurant is not answering."""
    try:
        coordinator.update_reservation_status(
            reservation_id=reservation_id,
            status=ReservationStatus.NO_ANSWER,
            details="Restaurant is not answering the phone",
            call_id=call_id
        )
        return "Restaurant not answering. Status updated."
        
    except Exception as e:
        return f"Error updating status: {str(e)}"

def get_reservation_details(reservation_id: str) -> str:
    """Get the details of the reservation to share with the restaurant."""
    try:
        if reservation_id not in active_reservations:
            return "Error: Could not find reservation details."
        
        reservation = active_reservations[reservation_id]
        
        details = f"""Reservation Details:
- Customer: {reservation.customer_name}
- Date: {reservation.date}
- Time: {reservation.time}
- Party Size: {reservation.party_size} people"""
        
        if reservation.special_requests:
            details += f"\n- Special Requests: {reservation.special_requests}"
        
        return details.strip()
        
    except Exception as e:
        return f"Error retrieving reservation details: {str(e)}"

# Function registries for different agents
INBOUND_AGENT_FUNCTIONS = {
    "create_new_reservation": create_new_reservation,
    "check_reservation_status_updates": check_reservation_status_updates,
    "get_reservation_final_status": get_reservation_final_status,
}

OUTBOUND_AGENT_FUNCTIONS = {
    "start_restaurant_call": start_restaurant_call,
    "restaurant_answered": restaurant_answered,
    "restaurant_checking_availability": restaurant_checking_availability,
    "reservation_confirmed_by_restaurant": reservation_confirmed_by_restaurant,
    "reservation_declined_by_restaurant": reservation_declined_by_restaurant,
    "restaurant_line_busy": restaurant_line_busy,
    "restaurant_no_answer": restaurant_no_answer,
    "get_reservation_details": get_reservation_details,
}

def get_functions_for_agent(agent_id):
    """Get the appropriate function registry based on agent type"""
    if is_inbound_agent(agent_id):
        return INBOUND_AGENT_FUNCTIONS
    else:
        return OUTBOUND_AGENT_FUNCTIONS

def is_inbound_agent(agent_id):
    """Determine if this is an inbound agent based on agent ID"""
    if INBOUND_AGENT_ID and agent_id == INBOUND_AGENT_ID:
        return True
    if RESTAURANT_CALLER_AGENT_ID and agent_id == RESTAURANT_CALLER_AGENT_ID:
        return False
    # Fallback to naming convention
    return 'inbound' in agent_id.lower() or agent_id.endswith('_in')

# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'RetellAI Restaurant Agent with Status Updates',
        'status': 'active',
        'endpoints': {
            '/webhook': 'POST - RetellAI webhook endpoint',
            '/health': 'GET - Health check endpoint',
            '/retell-webhook': 'POST - RetellAI call status webhook'
        }
    })

@app.route('/webhook', methods=['POST'])
def retell_webhook():
    """Enhanced webhook endpoint for RetellAI with function calling support"""
    
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
        
        # Get agent ID and call ID for function routing
        agent_id = data.get('agent_id', '')
        call_id = data.get('call_id', '')
        
        # Check if this is a function call
        if 'tool_calls' in data:
            return handle_function_calls(data, agent_id, call_id)
        
        # Check for function name in different possible fields
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
        
        # If we have a function call, handle it
        if function_name:
            return handle_single_function_call(function_name, arguments, agent_id, call_id, data)
        
        # Handle original restaurant search functions for backward compatibility
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
        
        # If no function was called, handle as regular conversation
        return handle_conversation(data, agent_id, call_id)
            
    except Exception as e:
        print(f"ERROR in webhook: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        response = {
            'response': "I encountered an error while processing your request. Please try again."
        }
        return jsonify(response)

def handle_function_calls(data, agent_id, call_id):
    """Handle multiple function calls from either agent"""
    try:
        tool_calls = data.get('tool_calls', [])
        results = []
        
        for tool_call in tool_calls:
            function_name = tool_call.get('function', {}).get('name')
            function_args = tool_call.get('function', {}).get('arguments', {})
            tool_call_id = tool_call.get('id')
            
            # Determine which function registry to use
            functions = get_functions_for_agent(agent_id)
            
            if function_name in functions:
                try:
                    # Add call_id to function arguments if not present
                    if 'call_id' in functions[function_name].__code__.co_varnames:
                        function_args['call_id'] = call_id
                    
                    # Execute the function
                    result = functions[function_name](**function_args)
                    
                    results.append({
                        "tool_call_id": tool_call_id,
                        "result": result
                    })
                    
                except Exception as e:
                    print(f"Function execution error: {str(e)}")
                    results.append({
                        "tool_call_id": tool_call_id,
                        "result": f"Error executing function: {str(e)}"
                    })
            else:
                results.append({
                    "tool_call_id": tool_call_id,
                    "result": f"Function {function_name} not found"
                })
        
        return jsonify({
            "results": results,
            "response_id": data.get('response_id', 1)
        })
        
    except Exception as e:
        print(f"Function call handling error: {str(e)}")
        return jsonify({
            "response": "I encountered an issue processing that request. Let me try again.",
            "response_id": data.get('response_id', 1)
        }), 500

def handle_single_function_call(function_name, arguments, agent_id, call_id, data):
    """Handle a single function call"""
    try:
        # Determine which function registry to use
        functions = get_functions_for_agent(agent_id)
        
        if function_name in functions:
            # Add call_id to function arguments if the function expects it
            if 'call_id' in functions[function_name].__code__.co_varnames:
                arguments['call_id'] = call_id
            
            # Execute the function
            result = functions[function_name](**arguments)
            
            return jsonify({
                'response': result,
                'response_id': data.get('response_id', 1)
            })
        else:
            # Handle legacy functions for backward compatibility
            return handle_legacy_functions(function_name, arguments, data)
            
    except Exception as e:
        print(f"Single function call error: {str(e)}")
        return jsonify({
            'response': f"I encountered an error: {str(e)}",
            'response_id': data.get('response_id', 1)
        }), 500

def handle_legacy_functions(function_name, arguments, data):
    """Handle legacy function calls for backward compatibility"""
    if function_name == 'make_reservation_call':
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
                key=lambda x: x[1].created_at,
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
            'create_new_reservation',
            'check_reservation_status_updates',
            'get_reservation_final_status'
        ]
        
        response = {
            'response': f"I received an unknown function: {function_name}. I can help you with these functions: {', '.join(available_functions)}. What would you like to do?"
        }
        print(f"Unknown function '{function_name}'. Available: {available_functions}")
        return jsonify(response)

def handle_conversation(data, agent_id, call_id):
    """Handle regular conversation for both agents"""
    try:
        transcript = data.get('transcript', [])
        
        # Determine agent type and generate appropriate response
        if is_inbound_agent(agent_id):
            response = handle_inbound_conversation(transcript, call_id)
        else:
            response = handle_outbound_conversation(transcript, call_id)
        
        return jsonify({
            "response": response,
            "response_id": data.get('response_id', 1)
        })
        
    except Exception as e:
        print(f"Conversation handling error: {str(e)}")
        return jsonify({
            "response": "I apologize for the confusion. Could you please repeat that?",
            "response_id": data.get('response_id', 1)
        }), 500

def handle_inbound_conversation(transcript, call_id):
    """Handle conversation logic for inbound agent (customer-facing)"""
    if not transcript:
        return "Hello! I'm here to help you make a restaurant reservation. What restaurant would you like me to call for you?"
    
    last_message = transcript[-1].get('content', '').lower()
    
    # Check for status update requests
    if any(phrase in last_message for phrase in ['status', 'update', 'how is it going', 'what\'s happening']):
        # The agent should call check_reservation_status_updates function
        return "Let me check on the status of your reservation for you."
    
    # Regular conversation flow
    return "I understand. Let me help you with that restaurant reservation."

def handle_outbound_conversation(transcript, call_id):
    """Handle conversation logic for outbound agent (restaurant-facing)"""
    if not transcript:
        return "Hello, I'm calling to make a reservation. May I speak with someone who handles reservations?"
    
    # The outbound agent should be calling appropriate status update functions
    # based on the restaurant's responses
    return "Thank you. Let me get the reservation details for you."

@app.route('/retell-webhook', methods=['POST'])
def retell_call_webhook():
    """Enhanced webhook to receive call status updates from RetellAI"""
    
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
                    reservation = active_reservations[reservation_id]
                    customer_name = reservation.customer_name
                    
                    if any(keyword in transcript_lower for keyword in confirmed_keywords):
                        coordinator.update_reservation_status(
                            reservation_id=reservation_id,
                            status=ReservationStatus.CONFIRMED,
                            details="Restaurant confirmed the reservation via phone call"
                        )
                        
                        confirmation_msg = f"The restaurant confirmed your reservation."
                        
                        # Check if they mentioned the customer name
                        if customer_name.lower() in transcript_lower:
                            confirmation_msg += f" They have the reservation under {customer_name}."
                        
                        confirmation_msg += f" Call duration: {call_data.get('duration_seconds', 0)} seconds."
                        reservation.confirmation_details = confirmation_msg
                        
                    elif any(keyword in transcript_lower for keyword in failed_keywords):
                        coordinator.update_reservation_status(
                            reservation_id=reservation_id,
                            status=ReservationStatus.DECLINED,
                            details="Restaurant could not accommodate the reservation request"
                        )
                        reservation.failure_reason = (
                            "The restaurant couldn't accommodate your reservation request."
                        )
                    else:
                        # Unclear outcome
                        coordinator.update_reservation_status(
                            reservation_id=reservation_id,
                            status=ReservationStatus.ERROR,
                            details="Call ended but outcome unclear"
                        )
                    
                    # Store the transcript for reference
                    reservation.transcript = transcript
                    
                    print(f"Updated reservation {reservation_id} status to: {reservation.status}")
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error in retell webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Additional test endpoints remain the same...
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

@app.route('/reservation-status/<reservation_id>', methods=['GET'])
def get_reservation_status_endpoint(reservation_id):
    """HTTP endpoint to check reservation status (for testing/debugging)"""
    
    status = agent.check_reservation_status(reservation_id)
    if status['found']:
        return jsonify(status)
    else:
        return jsonify({"error": "Reservation not found"}), 404

@app.route('/debug-reservations', methods=['GET'])
def debug_reservations():
    """Debug endpoint to check active reservations"""
    reservations_data = {}
    for res_id, reservation in active_reservations.items():
        reservations_data[res_id] = {
            'customer_name': reservation.customer_name,
            'restaurant_name': reservation.restaurant_name,
            'status': reservation.status.value,
            'created_at': reservation.created_at.isoformat(),
            'inbound_call_id': reservation.inbound_call_id,
            'outbound_call_id': reservation.outbound_call_id
        }
    
    return jsonify({
        'active_reservations': reservations_data,
        'pending_updates': pending_updates
    })

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
        'INBOUND_AGENT_ID_set': bool(INBOUND_AGENT_ID),
        'INBOUND_AGENT_ID': INBOUND_AGENT_ID or "NOT SET",
        'RETELL_PHONE_NUMBER': RETELL_PHONE_NUMBER or "NOT SET"
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'restaurant-agent-with-status-updates'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

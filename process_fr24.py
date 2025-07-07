#!/usr/bin/env python3
"""
Process FlightRadar24 JSON files from schedule/ directory and convert to CSV.
Extracts flight information: departure airport, arrival airport, departure datetime, arrival datetime, flight number.
"""

import json
import csv
import os
from datetime import datetime
from pathlib import Path


def timestamp_to_datetime(timestamp, offset):
    """Convert timestamp and offset to datetime string."""
    # Timestamp is in seconds, offset is in seconds (negative for UTC-4)
    utc_timestamp = timestamp - offset
    dt = datetime.fromtimestamp(utc_timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def process_arrivals(data, airport_code, flights_data):
    """Process arrivals data from JSON."""
    arrivals = data.get('arrivals', {})
    
    for country, country_data in arrivals.items():
        airports = country_data.get('airports', {})
        
        for departure_airport, airport_info in airports.items():
            flights = airport_info.get('flights', {})
            
            for flight_number, flight_data in flights.items():
                utc_data = flight_data.get('utc', {})
                
                for date, schedule in utc_data.items():
                    timestamp = schedule.get('timestamp')
                    offset = schedule.get('offset')
                    time_str = schedule.get('time')
                    
                    if timestamp and offset is not None:
                        arrival_datetime = timestamp_to_datetime(timestamp, offset)
                        
                        # For arrivals, we need to find the corresponding departure
                        # For now, we'll store the arrival info and match later
                        flight_key = (flight_number, date)
                        if flight_key not in flights_data:
                            flights_data[flight_key] = {
                                'flight_number': flight_number,
                                'date': date,
                                'departure_airport': departure_airport,
                                'arrival_airport': airport_code,
                                'departure_datetime': None,
                                'arrival_datetime': arrival_datetime
                            }
                        else:
                            flights_data[flight_key]['arrival_datetime'] = arrival_datetime
                            flights_data[flight_key]['arrival_airport'] = airport_code


def process_departures(data, airport_code, flights_data):
    """Process departures data from JSON."""
    departures = data.get('departures', {})
    
    for country, country_data in departures.items():
        airports = country_data.get('airports', {})
        
        for arrival_airport, airport_info in airports.items():
            flights = airport_info.get('flights', {})
            
            for flight_number, flight_data in flights.items():
                utc_data = flight_data.get('utc', {})
                
                for date, schedule in utc_data.items():
                    timestamp = schedule.get('timestamp')
                    offset = schedule.get('offset')
                    time_str = schedule.get('time')
                    
                    if timestamp and offset is not None:
                        departure_datetime = timestamp_to_datetime(timestamp, offset)
                        
                        flight_key = (flight_number, date)
                        if flight_key not in flights_data:
                            flights_data[flight_key] = {
                                'flight_number': flight_number,
                                'date': date,
                                'departure_airport': airport_code,
                                'arrival_airport': arrival_airport,
                                'departure_datetime': departure_datetime,
                                'arrival_datetime': None
                            }
                        else:
                            flights_data[flight_key]['departure_datetime'] = departure_datetime
                            flights_data[flight_key]['departure_airport'] = airport_code


def process_json_files():
    """Process all JSON files in the schedule directory."""
    schedule_dir = Path('schedule')
    flights_data = {}
    
    if not schedule_dir.exists():
        print("Error: schedule/ directory not found")
        return
    
    json_files = list(schedule_dir.glob('*.json'))
    if not json_files:
        print("Error: No JSON files found in schedule/ directory")
        return
    
    print(f"Processing {len(json_files)} JSON files...")
    
    for json_file in json_files:
        airport_code = json_file.stem  # filename without extension
        print(f"Processing {json_file.name}...")
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Process both arrivals and departures
            process_arrivals(data, airport_code, flights_data)
            process_departures(data, airport_code, flights_data)
            
        except json.JSONDecodeError as e:
            print(f"Error parsing {json_file.name}: {e}")
        except Exception as e:
            print(f"Error processing {json_file.name}: {e}")
    
    return flights_data


def write_csv(flights_data, output_file='flights.csv'):
    """Write flights data to CSV file."""
    if not flights_data:
        print("No flight data to write")
        return
    
    # Filter out incomplete records (missing departure or arrival info)
    complete_flights = []
    for flight_info in flights_data.values():
        if (flight_info['departure_airport'] and 
            flight_info['arrival_airport'] and 
            flight_info['departure_datetime'] and 
            flight_info['arrival_datetime']):
            complete_flights.append(flight_info)
    
    print(f"Writing {len(complete_flights)} complete flight records to {output_file}")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'departure_airport', 
            'arrival_airport', 
            'departure_datetime', 
            'arrival_datetime', 
            'flight_number'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        
        # Sort flights by departure datetime
        complete_flights.sort(key=lambda x: x['departure_datetime'])
        
        for flight in complete_flights:
            writer.writerow({
                'departure_airport': flight['departure_airport'],
                'arrival_airport': flight['arrival_airport'],
                'departure_datetime': flight['departure_datetime'],
                'arrival_datetime': flight['arrival_datetime'],
                'flight_number': flight['flight_number']
            })


def main():
    """Main function."""
    print("FlightRadar24 JSON to CSV Converter")
    print("=" * 40)
    
    # Process all JSON files
    flights_data = process_json_files()
    
    if flights_data:
        # Write to CSV
        write_csv(flights_data)
        print("Conversion completed successfully!")
    else:
        print("No flight data found to process")


if __name__ == "__main__":
    main()
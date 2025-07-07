#!/usr/bin/env python3
"""
Convert flight schedule JSON and airports CSV into a consolidated CSV format
with departure airport, arrival airport, flight number, departure time, arrival time
for flights
"""

import json
import csv
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

def load_airports_mapping(csv_file: str) -> Dict[str, str]:
    """Load airport ID to code mapping from CSV file."""
    id_to_code = {}
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_to_code[row['airport_id']] = row['airport_code']
    return id_to_code

def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, '%Y-%m-%d')

def get_weekday_from_date(date: datetime) -> int:
    """Get weekday number where Monday=0, Sunday=6."""
    return date.weekday()

def date_falls_on_schedule_days(date: datetime, schedule: Dict) -> bool:
    """Check if a date falls on the days specified in the schedule."""
    weekday = get_weekday_from_date(date)
    day_map = {
        0: 'mo',  # Monday
        1: 'tu',  # Tuesday
        2: 'we',  # Wednesday
        3: 'th',  # Thursday
        4: 'fr',  # Friday
        5: 'sa',  # Saturday
        6: 'su'   # Sunday
    }
    
    day_key = day_map[weekday]
    return schedule.get(day_key, '0') == '1'

def generate_flight_dates(schedule: Dict, start_date: datetime, end_date: datetime) -> List[datetime]:
    """Generate all dates when a flight operates within the given date range."""
    flight_dates = []
    
    # Parse schedule date range
    datefrom = parse_date(schedule['datefrom'])
    dateto = parse_date(schedule['dateto'])
    
    # Find overlap between schedule period and our target period
    overlap_start = max(datefrom, start_date)
    overlap_end = min(dateto, end_date)
    
    # If no overlap, return empty list
    if overlap_start > overlap_end:
        return flight_dates
    
    # Generate dates within the overlap period
    current_date = overlap_start
    while current_date <= overlap_end:
        if date_falls_on_schedule_days(current_date, schedule):
            flight_dates.append(current_date)
        current_date += timedelta(days=1)
    
    return flight_dates

def convert_schedule_to_csv(json_file: str, airports_csv: str, output_csv: str):
    """Convert schedule JSON to CSV format."""
    
    # Load airport mapping
    print("Loading airport mapping...")
    id_to_code = load_airports_mapping(airports_csv)
    
    # Load schedule data
    print("Loading schedule data...")
    with open(json_file, 'r') as f:
        schedule_data = json.load(f)
    
    # Define target date range
    start_date = datetime(2025, 7, 15)
    end_date = datetime(2025, 12, 31)
    
    print(f"Processing flights from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Prepare output data
    flights = []
    
    # Process each route
    for dep_airport_id, destinations in schedule_data.items():
        dep_airport_code = id_to_code.get(dep_airport_id)
        
        if not dep_airport_code:
            print(f"Warning: No airport code found for departure airport ID {dep_airport_id}")
            continue
        
        for arr_airport_id, flight_schedules in destinations.items():
            arr_airport_code = id_to_code.get(arr_airport_id)
            
            if not arr_airport_code:
                print(f"Warning: No airport code found for arrival airport ID {arr_airport_id}")
                continue
            
            # Process each flight schedule
            for schedule in flight_schedules:
                flight_number = schedule['flightnumber'].strip()
                dep_time = schedule['deptime']
                arr_time = schedule['destime']
                
                # Generate all dates this flight operates
                flight_dates = generate_flight_dates(schedule, start_date, end_date)
                
                # Create entry for each flight date
                for flight_date in flight_dates:
                    # Handle flights that arrive the next day (crossing midnight)
                    dep_datetime = datetime.combine(flight_date.date(), 
                                                  datetime.strptime(dep_time, '%H:%M:%S').time())
                    arr_datetime = datetime.combine(flight_date.date(), 
                                                  datetime.strptime(arr_time, '%H:%M:%S').time())
                    
                    # If arrival time is earlier than departure time, it's next day
                    if arr_datetime < dep_datetime:
                        arr_datetime += timedelta(days=1)
                    
                    flights.append({
                        'departure_airport': dep_airport_code,
                        'arrival_airport': arr_airport_code,
                        'flight_number': flight_number,
                        'departure_time': dep_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                        'arrival_time': arr_datetime.strftime('%Y-%m-%d %H:%M:%S')
                    })
    
    # Remove duplicates (in case there are any)
    print(f"Generated {len(flights)} flight entries")
    
    # Convert to DataFrame for easier deduplication
    df = pd.DataFrame(flights)
    df_unique = df.drop_duplicates().sort_values(by=['departure_airport', 'arrival_airport', 'flight_number', 'departure_time'])
    
    print(f"After removing duplicates: {len(df_unique)} unique flight entries")
    
    # Write to CSV
    print(f"Writing to {output_csv}...")
    df_unique.to_csv(output_csv, index=False)
    
    print("Conversion completed successfully!")

def main():
    """Main function."""
    json_file = 'fc_schedule.json'
    airports_csv = 'airports.csv'
    output_csv = 'flights.csv'
    
    try:
        convert_schedule_to_csv(json_file, airports_csv, output_csv)
    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    main()

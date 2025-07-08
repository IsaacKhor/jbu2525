#!/usr/bin/env pypy3

import datetime
from datetime import datetime as dt
import csv
from collections import deque

stime = dt(2025, 9, 20)
etime = dt(2025, 12, 30)
min_layover = datetime.timedelta(minutes=60)
max_layover = datetime.timedelta(hours=18)
max_trip_duration = datetime.timedelta(days=3)
num_dest_airports = 25
max_num_flights = 35
min_trip_airports = 4
regional_arrival_cutoff = datetime.time(20, 0)
overnight_threshold = datetime.timedelta(hours=3)
overnight_check_time = datetime.time(3, 0)
allowed_overnight_airports = ['RDU', 'DCA', 'MCO']

start_airport = 'BOS'
regional_end = ['PVD', 'ORH']
end_airports = [start_airport] + regional_end

flight_graph = {}


class Flight:
    def __init__(self, src, dst, fnum, dtime, atime):
        self.src = src
        self.dst = dst
        self.fnum = fnum
        self.dtime = dtime
        self.atime = atime

    def __repr__(self):
        return f"Flight({self.src} -> {self.dst}, {self.fnum}, {self.dtime}, {self.atime})"


def build_flight_graph(csv_file):
    # CSV format:
    # departure_airport,arrival_airport,flight_number,departure_time,arrival_time
    flight_graph = {}
    with open(csv_file, 'r') as f:
        reader = csv.reader(f, delimiter=',')
        next(reader)  # Skip header row
        for row in reader:
            src, dst, fnum, dept_timestr, arr_timestr = row
            dtime = dt.strptime(dept_timestr, '%Y-%m-%d %H:%M:%S')
            atime = dt.strptime(arr_timestr, '%Y-%m-%d %H:%M:%S')

            if dtime < stime or atime > etime:
                continue

            flight = Flight(src, dst, fnum, dtime, atime)
            if src not in flight_graph:
                flight_graph[src] = []
            flight_graph[src].append(flight)
    return flight_graph


def get_valid_outgoing(incoming, graph):
    ret = []
    cur = incoming.dst
    for outgoing in graph[cur]:
        layover = outgoing.dtime - incoming.atime

        if min_layover >= layover or layover >= max_layover:
            continue

        # Check if overnight and if airport is allowed
        # overnight meaning over overnight check threshold and layover period contains overnight_check_time
        if layover > overnight_threshold:
            overnight_check_datetime = dt.combine(
                outgoing.atime.date(), overnight_check_time)
            if incoming.atime <= overnight_check_datetime <= outgoing.dtime:
                if cur not in allowed_overnight_airports:
                    continue
        ret.append(outgoing)

    return ret


def is_valid_endpoint(flight):
    if flight.dst not in end_airports:
        return False

    if flight.atime > etime or flight.dtime < stime:
        return False

    if flight.dst in regional_end:
        # For regional airports, check if arrival time is before cutoff
        if flight.atime.time() > regional_arrival_cutoff:
            return False

    return True


def print_trip(trip):
    num_unique = set(flight.dst for flight in trip)
    print(f"Trip: {len(trip)} flights, {len(num_unique)} destinations:")
    for i, flight in enumerate(trip):
        if i < len(trip) - 1:  # Not the last flight
            next_flight = trip[i + 1]
            layover = next_flight.dtime - flight.atime
            print(f"  {flight.src} -> {flight.dst} ({flight.fnum}) "
                  f"{flight.dtime.strftime('%m.%d %H:%M')} -> "
                  f"{flight.atime.strftime('%m.%d %H:%M')} "
                  f"[layover: {layover}]")
        else:  # Last flight
            print(f"  {flight.src} -> {flight.dst} ({flight.fnum}) "
                  f"{flight.dtime.strftime('%m.%d %H:%M')} -> "
                  f"{flight.atime.strftime('%m.%d %H:%M')}")
    print(f"  Total duration: {trip[-1].atime - trip[0].dtime}")
    airports = set([flight.src for flight in trip] + [trip[-1].dst])
    print(f"  Airports visited: {sorted(airports)}")


def main():
    graph = build_flight_graph('flights.csv')

    # BFS to find trips optimizing for number of airports visited
    q = deque()
    valid = []

    # Initialize with flights from start airport
    if start_airport in graph:
        for flight in graph[start_airport]:
            if flight.dtime.date() >= stime.date():
                q.append(([flight], {flight.dst}))

    i = 0
    while q:
        i += 1
        if i % 10_000 == 0:
            print(f".", end='', flush=True)
        if i % 500_000 == 0:
            print(f"={i} done; {len(valid)} valid; {len(q)} queue")
        if i % 1_000_000 == 0 and valid:
            best_trip, _, _ = max(valid, key=lambda x: (
                len(x[1]), -x[2].total_seconds()))
            print_trip(best_trip)
            print()

        cur_trip, visited_airports = q.popleft()

        # Check if current trip is a valid endpoint
        if is_valid_endpoint(cur_trip[-1]):
            if len(visited_airports) >= min_trip_airports:
                # Check if there's already a shorter trip with the same airports
                should_add = True
                for old_trip, old_aps, old_dur in valid:
                    cur_aps = {flight.dst for flight in cur_trip}
                    if old_aps == cur_aps:
                        cur_dur = cur_trip[-1].atime - cur_trip[0].dtime
                        if cur_dur >= old_dur:
                            should_add = False
                            break

                if should_add:
                    dur = cur_trip[-1].atime - cur_trip[0].dtime
                    valid.append((cur_trip.copy(), visited_airports, dur))

        # Continue searching if we haven't reached max flights
        if len(cur_trip) < max_num_flights:
            # Check total trip duration
            trip_duration = cur_trip[-1].atime - cur_trip[0].dtime
            if trip_duration <= max_trip_duration:
                # Get valid outgoing flights
                if cur_trip[-1].dst in graph:
                    for next_flight in get_valid_outgoing(cur_trip[-1], graph):
                        new_visited = visited_airports | {next_flight.dst}
                        q.append((cur_trip + [next_flight], new_visited))

    # Sort by number of unique airports visited (descending)
    valid.sort(key=lambda x: x[1], reverse=True)

    # Display results
    print(f"Found {len(valid)} valid trips:")
    for i, (trip, num_airports) in enumerate(valid):
        print_trip(trip)


if __name__ == "__main__":
    main()

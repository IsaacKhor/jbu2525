#!/usr/bin/env pypy3

import datetime
from datetime import datetime as dt
import csv
from collections import deque
import multiprocessing as mp
from multiprocessing import Pool
import math
import itertools

num_parallel = mp.cpu_count() - 1
dest_cap = 25
min_dest_airports = 15
max_dup_airports = 2
# end_airports = ['RDU', 'AVL', 'ISM']
end_airports = ['BOS', 'PVD', 'ORH']
allowed_overnight_airports = ['RDU', 'DCA', 'BUF', 'PVD', 'PIT']

infile = 'flights.csv'
stime = dt(2025, 8, 1)
etime = dt(2025, 11, 21)
latest_start_time = dt(2025, 10, 15)
min_day_layover = datetime.timedelta(minutes=50)
max_day_layover = datetime.timedelta(hours=5)
# min_night_layover = datetime.timedelta(hours=7)
max_night_layover = datetime.timedelta(hours=18)
max_plan_dur = datetime.timedelta(days=28)
regional_arrival_earliest = datetime.time(6, 0)
regional_arrival_latest = datetime.time(21, 0)
home_arrival_cutoff = datetime.time(23, 00)
overnight_threshold = datetime.timedelta(hours=3)
overnight_check_time = datetime.time(3, 0)
min_trip_gap = datetime.timedelta(days=3)
max_trip_gap = datetime.timedelta(days=7)

start_airport = end_airports[0]
regional_end = end_airports[1:]
end_airports = [start_airport] + regional_end
regional_endtime_exempt = []
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

    def __lt__(self, other):
        return self.dtime < other.dtime


def is_overnight(incoming, outgoing):
    # Check if the layover is overnight
    layover = outgoing.dtime - incoming.atime
    if layover > overnight_threshold:
        overnight_check_datetime = dt.combine(
            outgoing.dtime.date(), overnight_check_time)
        return incoming.atime <= overnight_check_datetime <= outgoing.dtime
    return False


class ValidPlan:
    def __init__(self, flights, airports, total_dur, effective_dur):
        self.flights = flights
        self.airports = airports
        self.total_dur = total_dur
        self.total_days = calc_days_taken(flights)
        self.effective_dur = effective_dur
        self.num_overnights = sum(1 for i in range(len(flights) - 1)
                                  if is_overnight(flights[i], flights[i + 1]))

    def __repr__(self):
        return f"ValidPlan(flights={len(self.flights)}, airports={len(self.airports)}, total_duration={self.total_dur}, effective_duration={self.effective_dur})"

    def __str__(self):
        ret = ""
        ret += (f"Plan: {len(self.flights)} flights, {len(self.airports)} destinations:\n")
        for i, flight in enumerate(self.flights):
            if i < len(self.flights) - 1:  # Not the last flight
                next_flight = self.flights[i + 1]
                layover = next_flight.dtime - flight.atime
                ret += (f"  {flight.src} -> {flight.dst} (B6 {flight.fnum:04d}) "
                        f"{flight.dtime.strftime('%m.%d %H:%M')} -> "
                        f"{flight.atime.strftime('%m.%d %H:%M')} "
                        f"[layover: {layover}{' (night)' if is_overnight(flight, next_flight) else ''}]\n")
            else:  # Last flight
                ret += (f"  {flight.src} -> {flight.dst} (B6 {flight.fnum:04d}) "
                        f"{flight.dtime.strftime('%m.%d %H:%M')} -> "
                        f"{flight.atime.strftime('%m.%d %H:%M')}\n")
        ret += (f"  Total duration: {self.total_dur}\n"
                f"  Effective duration: {self.effective_dur}\n"
                f"  Days taken: {self.total_days}\n"
                f"  Overnight layovers: {self.num_overnights}\n"
                f"  Airports visited: {sorted(self.airports)}\n")
        return ret


def build_city_graph(csv_file) -> dict[str, list[Flight]]:
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

            flight = Flight(src, dst, int(fnum), dtime, atime)
            if src not in flight_graph:
                flight_graph[src] = []
            flight_graph[src].append(flight)
    return flight_graph


def get_valid_outgoing(incoming, city_graph):
    ret = []
    cur = incoming.dst
    for outgoing in city_graph[cur]:
        layover = outgoing.dtime - incoming.atime
        if not (min_day_layover <= layover <= max_night_layover):
            continue

        if is_overnight(incoming, outgoing):
            # If overnight, disallow if too long or not in allowed airports
            if layover > max_night_layover or incoming.dst not in allowed_overnight_airports:
                continue
        else:
            if layover > max_day_layover:
                continue

        ret.append(outgoing)
    return ret


def build_flight_graph(city_graph):
    ret = {}
    for flight in itertools.chain.from_iterable(city_graph.values()):
        outgoing = get_valid_outgoing(flight, city_graph)
        ret[flight] = sorted(outgoing, reverse=True)
    return ret


def calc_days_taken(flights):
    days = {flight.dtime.date() for flight in flights}
    days |= {flight.atime.date() for flight in flights}
    return len(days)


def calc_effective_duration(flights):
    # count total duration except start airport layovers exceeding min_trip_gap
    dur = datetime.timedelta(0)
    for i, flight in enumerate(flights):
        dur += flight.atime - flight.dtime
        if i < len(flights) - 1:
            next_flight = flights[i + 1]
            layover_duration = next_flight.dtime - flight.atime
            # Only add layover if not at start airport or regional
            if flight.dst not in end_airports or layover_duration <= min_trip_gap:
                dur += layover_duration
    return dur


def get_new_bos_outgoing(intime, city_graph):
    ret = []
    for outgoing in city_graph[start_airport]:
        gap = outgoing.dtime - intime
        if min_trip_gap <= gap <= max_trip_gap:
            ret.append(outgoing)
    return ret


def is_valid_endpoint(flight):
    if flight.dst not in end_airports:
        return False

    if flight.dst in regional_end:
        # For regional airports, check if arrival time is before cutoff
        if flight.dst in regional_endtime_exempt or flight.dst == start_airport:
            return regional_arrival_earliest < flight.atime.time() < home_arrival_cutoff
        else:
            return regional_arrival_earliest < flight.atime.time() < regional_arrival_latest

    return True


def is_better_plan(old_plan: ValidPlan, new_plan: ValidPlan):
    # compare in order: # of destinations, # of days used, # of flights + overnight layovers, effective duration
    old_tupl = (-min(len(old_plan.airports), dest_cap),
                old_plan.total_days,
                len(old_plan.flights) + old_plan.num_overnights,
                old_plan.effective_dur)
    new_tupl = (-min(len(new_plan.airports), dest_cap),
                new_plan.total_days,
                len(new_plan.flights) + new_plan.num_overnights,
                new_plan.effective_dur)
    return new_tupl < old_tupl


def trip_numdays(trip):
    if not trip:
        return 0
    start_date = trip[0].dtime.date()
    end_date = trip[-1].atime.date()
    return (end_date - start_date).days + 1


def calc_trip_dur(trip):
    return trip[-1].atime - trip[0].dtime


def search_from_chunk(chunk_data):
    """Process a chunk of initial flights"""
    chunk_flights, chunk_id, city_graph, flight_graph = chunk_data
    q = deque()

    # Initialize with flights from this chunk
    for flight in chunk_flights:
        q.appendleft(([flight], {flight.dst}))

    best_plan = None
    i = 0
    while q:
        i += 1
        if i % 1_000_000_000 == 0:
            print(
                f"Chunk {chunk_id}: {i/1_000_000_000}B processed. {len(q)} items in queue", flush=True)

        cur_plan, visited_airports = q.pop()
        cur_flight = cur_plan[-1]

        if cur_flight.atime - cur_plan[0].dtime > max_plan_dur or len(cur_plan) > len(visited_airports) + max_dup_airports:
            continue

        # Check if current trip is a valid endpoint
        if is_valid_endpoint(cur_flight):
            # are we done yet
            if len(visited_airports) >= min_dest_airports:
                new_plan = ValidPlan(
                    flights=cur_plan.copy(),
                    airports=visited_airports,
                    total_dur=calc_trip_dur(cur_plan),
                    effective_dur=calc_effective_duration(cur_plan)
                )
                if not best_plan or is_better_plan(best_plan, new_plan):
                    best_plan = new_plan
                    print(f"\nChunk {chunk_id} new best: {best_plan}")
            # we're not done, start new trip
            if len(visited_airports) < dest_cap:
                for flight in get_new_bos_outgoing(cur_flight.atime, city_graph):
                    new_visited = visited_airports | {flight.dst}
                    q.append((cur_plan + [flight], new_visited))

        for next_flight in flight_graph[cur_flight]:
            # manually prune out turn-arounds in the first half of the plan
            if len(cur_plan) < min_dest_airports / 2 and next_flight.dst == cur_plan[-1].src:
                continue
            # ban heading back to start airport before the end
            if len(cur_plan) < min_dest_airports and next_flight.dst == start_airport:
                continue
            new_visited = visited_airports | {next_flight.dst}
            q.append((cur_plan + [next_flight], new_visited))

    print(f"\nChunk {chunk_id}: processed {i} items, best plan:\n{best_plan}")
    return best_plan


def bench_one():
    city_graph = build_city_graph(infile)
    flight_graph = build_flight_graph(city_graph)
    print(f'Build flight graph, starting search')
    return search_from_chunk(
        (list(city_graph[start_airport]), 0, city_graph, flight_graph))


def main():
    print("Building city graph...")
    city_graph = build_city_graph(infile)
    print(f"City graph built with {len(city_graph)} airports.")
    flight_graph = build_flight_graph(city_graph)
    conns = sum(len(v) for v in flight_graph.values())
    print(f"Flight graph: {len(flight_graph)} flights, {conns} connections.")

    # Get all initial flights from start airport
    initial_flights = []
    for flight in city_graph[start_airport]:
        if latest_start_time.date() >= flight.dtime.date() >= stime.date():
            initial_flights.append(flight)

    print(f"Found {len(initial_flights)} initial flights from {start_airport}")

    chunk_size = math.ceil(len(initial_flights) / num_parallel)
    chunks = []

    for i in range(0, len(initial_flights), chunk_size):
        chunk = initial_flights[i:i + chunk_size]
        if chunk:  # Only add non-empty chunks
            chunks.append((chunk, i // chunk_size, city_graph, flight_graph))

    print(f"Partitioned into {len(chunks)} chunks of size ~{chunk_size}")

    # Process chunks in parallel
    results = []
    if num_parallel <= 1:
        results = [bench_one()]
    else:
        with Pool(processes=min(num_parallel, mp.cpu_count())) as pool:
            print(
                f"Starting parallel processing with {num_parallel} processes...")
            results = pool.map(search_from_chunk, chunks)

    # Find the best plan across all chunks
    best_plan = None
    for plan in results:
        if plan and (not best_plan or is_better_plan(best_plan, plan)):
            best_plan = plan

    print(
        f"\nSearch complete. Best plan found across all chunks:\n{best_plan}")


if __name__ == "__main__":
    main()

#!/usr/bin/env pypy3

import datetime
from datetime import datetime as dt
import csv
from collections import deque
import multiprocessing as mp
from multiprocessing import Pool
import math

min_dest_airports = 20
max_dup_airports = 5

stime = dt(2025, 9, 20)
etime = dt(2025, 12, 21)
latest_start_time = dt(2025, 11, 30)
min_layover = datetime.timedelta(minutes=50)
max_layover = datetime.timedelta(hours=18)
max_plan_dur = datetime.timedelta(days=45)
regional_arrival_cutoff = datetime.time(20, 0)
# home_arrival_cutoff = datetime.time(23, 30)
overnight_threshold = datetime.timedelta(hours=3)
overnight_check_time = datetime.time(3, 0)
min_trip_gap = datetime.timedelta(days=3)
max_trip_gap = datetime.timedelta(days=28)
allowed_overnight_airports = ['RDU', 'DCA', 'MCO', 'PVD', 'PIT']

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


class ValidPlan:
    def __init__(self, flights, airports, total_dur, effective_dur):
        self.flights = flights
        self.airports = airports
        self.total_dur = total_dur
        self.total_days = calc_days_taken(flights)
        self.effective_dur = effective_dur

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
                        f"[layover: {layover}]\n")
            else:  # Last flight
                ret += (f"  {flight.src} -> {flight.dst} (B6 {flight.fnum:04d}) "
                        f"{flight.dtime.strftime('%m.%d %H:%M')} -> "
                        f"{flight.atime.strftime('%m.%d %H:%M')}\n")
        ret += (f"  Total duration: {self.total_dur}\n"
                f"  Effective duration: {self.effective_dur}\n"
                f"  Days taken: {self.total_days}\n"
                f"  Airports visited: {sorted(self.airports)}\n")
        return ret


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

            flight = Flight(src, dst, int(fnum), dtime, atime)
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
            # Only add layover if not at start airport
            if flight.dst != start_airport or layover_duration <= min_trip_gap:
                dur += layover_duration
    return dur


def get_new_bos_outgoing(intime, graph):
    ret = []
    for outgoing in graph[start_airport]:
        gap = outgoing.dtime - intime
        if min_trip_gap <= gap <= max_trip_gap:
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


def is_better_plan(old_plan: ValidPlan, new_plan: ValidPlan):
    # compare in order: # of destinations, # of days, # of flights, effective duration
    # destinations is capped at 25
    old_dest = min(len(old_plan.airports), 25)
    new_dest = min(len(new_plan.airports), 25)

    old_tupl = (old_dest, old_plan.total_days,
                len(old_plan.flights), old_plan.effective_dur)
    new_tupl = (new_dest, new_plan.total_days,
                len(new_plan.flights), new_plan.effective_dur)
    return new_tupl > old_tupl


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
    chunk_flights, chunk_id = chunk_data
    graph = build_flight_graph('flights.csv')
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
                f"Chunk {chunk_id}: {i//1_000_000_000}B processed", flush=True)

        cur_plan, visited_airports = q.pop()

        # Check if current trip is a valid endpoint
        if is_valid_endpoint(cur_plan[-1]):
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
                    print(
                        f"\nChunk {chunk_id} - Best plan so far: {best_plan}")
            # we're not done, start new trip
            else:
                for flight in get_new_bos_outgoing(cur_plan[-1].atime, graph):
                    new_visited = visited_airports | {flight.dst}
                    q.append((cur_plan + [flight], new_visited))

        # Continue searching if we haven't reached max duplicates
        if len(cur_plan) < len(visited_airports) + max_dup_airports:
            # Check total trip duration
            trip_duration = cur_plan[-1].atime - cur_plan[0].dtime
            if trip_duration <= max_plan_dur:
                # Get valid outgoing flights
                if cur_plan[-1].dst in graph:
                    for next_flight in reversed(get_valid_outgoing(cur_plan[-1], graph)):
                        new_visited = visited_airports | {next_flight.dst}
                        q.append((cur_plan + [next_flight], new_visited))

    print(
        f"\nChunk {chunk_id} complete. Processed {i} items. Best plan: {best_plan}")
    return best_plan


def main():
    print("Building flight graph...")
    graph = build_flight_graph('flights.csv')

    # Get all initial flights from start airport
    initial_flights = []
    for flight in graph[start_airport]:
        if latest_start_time.date() >= flight.dtime.date() >= stime.date():
            initial_flights.append(flight)

    print(f"Found {len(initial_flights)} initial flights from {start_airport}")

    num_parallel = mp.cpu_count()
    # Partition into 128 chunks
    chunk_size = math.ceil(len(initial_flights) / num_parallel)
    chunks = []

    for i in range(0, len(initial_flights), chunk_size):
        chunk = initial_flights[i:i + chunk_size]
        if chunk:  # Only add non-empty chunks
            chunks.append((chunk, i // chunk_size))

    print(f"Partitioned into {len(chunks)} chunks of size ~{chunk_size}")

    # Process chunks in parallel
    with Pool(processes=min(num_parallel, mp.cpu_count())) as pool:
        print(
            f"Starting parallel processing with {pool._processes} processes...")
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

#include "absl/container/flat_hash_map.h"
#include "absl/flags/flag.h"
#include "absl/flags/parse.h"
#include "absl/time/civil_time.h"
#include "absl/time/time.h"
#include "fmt/core.h"
#include "rapidcsv.h"
#include <_abort.h>
#include <algorithm>
#include <csignal>
#include <ctime>
#include <deque>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

using u8 = uint8_t;
using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;
using tp = absl::Time;
using str = std::string;
template <typename T> using vec = std::vector<T>;
template <typename K, typename V> using umap = std::unordered_map<K, V>;
template <typename T> using sptr = std::shared_ptr<T>;

const u32 DEST_CAP = 25;
const u32 MIN_DESTS = 15;
const u32 MAX_DUP_DESTS = 3;
const auto MAX_TRIP_DURATION = absl::Hours(7 * 24);

// Configuration constants
const auto START_TIME =
    absl::FromCivil(absl::CivilHour(2025, 9, 16), absl::UTCTimeZone());
const auto END_TIME =
    absl::FromCivil(absl::CivilHour(2025, 12, 15), absl::UTCTimeZone());
const auto MIN_DAY_LAYOVER = absl::Minutes(50);
const auto MAX_DAY_LAYOVER = absl::Hours(18);
const auto MIN_NIGHT_LAYOVER = absl::Hours(8);
const auto MAX_NIGHT_LAYOVER = absl::Hours(18);
const auto MIN_HOME_LAYOVER = absl::Hours(3 * 24 + 6);
const auto MAX_HOME_LAYOVER = absl::Hours(7 * 24);

// const u32 REGIONAL_ARRIVAL_CUTOFF_HOUR = 20;
const auto OVERNIGHT_THRESHOLD = absl::Hours(3);
const u32 OVERNIGHT_CHECK_HOUR = 3;

const str START_AIRPORT = "BOS";
const vec<str> REGIONAL_END = {"PVD", "ORH"};
const vec<str> ALLOWED_OVERNIGHT_AIRPORTS = {"RDU", "DCA", "BUF", "PVD", "PIT"};

auto timezone_lookup(str city) -> absl::TimeZone
{
    absl::TimeZone tz;
    if (city == "ABQ" || city == "DEN")
        absl::LoadTimeZone("America/Phoenix", &tz);
    else if (city == "BQN" || city == "PSE" || city == "SJU" || city == "STT" ||
             city == "STX")
        absl::LoadTimeZone("America/Puerto_Rico", &tz);
    else if (city == "DFW" || city == "DTW" || city == "IAH" || city == "MSY" ||
             city == "MKE" || city == "ORD")
        absl::LoadTimeZone("America/Chicago", &tz);
    else if (city == "LAS" || city == "PHX" || city == "LAX")
        absl::LoadTimeZone("America/Los_Angeles", &tz);
    else
        absl::LoadTimeZone("America/New_York", &tz);
    return tz;
}

struct Flight {
    str src;
    str dst;
    u16 fnum;
    absl::Duration dur;

    tp dep_time;
    tp arr_time;
    absl::CivilDay dep_day;
    absl::CivilDay arr_day;
    absl::TimeZone dep_tz;
    absl::TimeZone arr_tz;

    auto to_string() const -> str
    {
        return fmt::format("{:>4}: {} -> {}, {} -> {}, {}", fnum, src, dst,
                           absl::FormatTime("%m.%d %H:%M", dep_time, dep_tz),
                           absl::FormatTime("%m.%d %H:%M", arr_time, arr_tz),
                           absl::FormatDuration(dur));
    }

    auto is_valid_end() const -> bool
    {
        if (dst != START_AIRPORT || !absl::c_linear_search(REGIONAL_END, dst))
            return false;
        // TODO check regional arrival cutoff time
        return true;
    }

    auto is_overnight_to(Flight &oth) -> bool
    {
        assert(this->dst == oth.src);
        auto layover = oth.dep_time - this->arr_time;
        if (layover < OVERNIGHT_THRESHOLD)
            return false;

        // check if the layover is overnight at the shared airport
        auto cday = this->arr_day;
        auto compare_point = absl::FromCivil(
            absl::CivilHour(cday.year(), cday.month(), cday.day(),
                            OVERNIGHT_CHECK_HOUR, 0),
            this->arr_tz);

        return this->arr_time <= compare_point && oth.dep_time >= compare_point;
    }
};

class Plan : public std::enable_shared_from_this<Plan>
{
  public:
    sptr<Plan> prev;     // previous plan in the chain
    Flight *last_flight; // last flight in the plan
    u8 num_flights;      // total number of flights
    u8 unique_dest;      // unique airports
    u8 num_days;         // whole days used
    absl::Duration dur;  // total trip duration

    static auto new_root(Flight *f)
    {
        auto ret = std::make_shared<Plan>();
        ret->prev = nullptr;
        ret->last_flight = f;
        ret->num_flights = 1;
        ret->unique_dest = 1;
        ret->num_days = 1;
        ret->dur = f->dur;
        return ret;
    }

    auto new_append(Flight *nxt)
    {
        auto ret = std::make_shared<Plan>();
        ret->prev = shared_from_this();
        ret->last_flight = nxt;
        ret->num_flights = (u8)(this->num_flights + 1);
        ret->unique_dest = (u8)(this->unique_dest + 1);
        ret->num_days = this->num_days;
        ret->dur = this->dur + nxt->dur;

        // search through all previous flights to see if this airport is new
        // and adjust unique_dest accordingly
        // for (auto &f : this->flights) {
        //     if (f->dst != nxt->dst)
        //         continue;
        //     ret.unique_dest--;
        //     break;
        // }

        Plan *p = this;
        while ((p = p->prev.get()) != nullptr) {
            if (p->last_flight->dst != nxt->dst)
                continue;
            ret->unique_dest--;
            break;
        }

        // check if we hit a new day
        if (nxt->dep_day != this->last_flight->arr_day)
            ret->num_days++;
        if (nxt->arr_day != nxt->dep_day)
            ret->num_days++;

        // adjust duration for layover if it's not the home city
        if (nxt->src != START_AIRPORT) {
            auto layover = nxt->dep_time - this->last_flight->arr_time;
            ret->dur += layover;
        }
        return ret;
    }

    auto is_better(const Plan &other) const -> bool
    {
        // compare in order:
        // - most unique destinations
        // - fewest days taken
        // - fewest flights + overnight layovers (TODO)
        // - shortest effective duration
        if (this->unique_dest != other.unique_dest)
            return this->unique_dest > other.unique_dest;
        if (this->num_days != other.num_days)
            return this->num_days < other.num_days;
        if (this->num_flights != other.num_flights)
            return this->num_flights < other.num_flights;
        return this->dur < other.dur;
    }

    auto to_string() const -> str
    {
        vec<Flight *> flight_list;
        for (auto p = this; p != nullptr; p = p->prev.get())
            flight_list.push_back(p->last_flight);
        std::reverse(flight_list.begin(), flight_list.end());

        str flight_str;
        for (u32 i = 0; i < flight_list.size() - 1; ++i) {
            flight_str += flight_list[i]->to_string();
            auto layover =
                flight_list[i + 1]->dep_time - flight_list[i]->arr_time;
            flight_str +=
                fmt::format(" [layover: {}]\n", absl::FormatDuration(layover));
        }
        flight_str += flight_list.back()->to_string() + "\n";

        return fmt::format("Plan: {} flights, {} destinations, {} days taken, "
                           "{} effective duration\n{}",
                           num_flights, unique_dest, num_days,
                           absl::FormatDuration(dur), flight_str);
    }
};

using CityGraph = umap<str, vec<Flight>>;
using FlightGraph = umap<Flight *, vec<Flight *>>;
const str TIME_FORMAT = "%Y-%m-%d %H:%M:%S";

auto build_city_graph(const str &filename) -> CityGraph
{
    rapidcsv::Document doc(filename);
    CityGraph city_graph;

    for (u32 i = 0; i < doc.GetRowCount(); ++i) {
        Flight f;
        f.src = doc.GetCell<str>("departure_airport", i);
        f.dst = doc.GetCell<str>("arrival_airport", i);
        f.fnum = (u16)doc.GetCell<u32>("flight_number", i);

        auto depart_tz = timezone_lookup(f.src);
        auto arrive_tz = timezone_lookup(f.dst);
        absl::ParseTime(TIME_FORMAT, doc.GetCell<str>("departure_time", i),
                        depart_tz, &f.dep_time, nullptr);
        absl::ParseTime(TIME_FORMAT, doc.GetCell<str>("arrival_time", i),
                        arrive_tz, &f.arr_time, nullptr);
        f.dur = f.arr_time - f.dep_time;

        f.dep_day = absl::ToCivilDay(f.dep_time, depart_tz);
        f.arr_day = absl::ToCivilDay(f.arr_time, arrive_tz);

        if (!city_graph.contains(f.src))
            city_graph[f.src] = vec<Flight>();
        if (f.dep_time > START_TIME && f.arr_time < END_TIME)
            city_graph[f.src].push_back(f);
    }

    return city_graph;
}

auto get_valid_outgoing(Flight &inc, CityGraph &graph) -> vec<Flight *>
{
    vec<Flight *> ret;
    for (auto &f : graph[inc.dst]) {
        // skip flights that depart before the arrival of the incoming flight
        if (f.dep_time < inc.arr_time)
            continue;

        // skip flights with too short or too long layovers
        auto layover = f.dep_time - inc.arr_time;
        if (inc.is_overnight_to(f) &&
            (layover < MIN_NIGHT_LAYOVER || layover > MAX_NIGHT_LAYOVER ||
             !absl::c_linear_search(ALLOWED_OVERNIGHT_AIRPORTS, f.src)))
            continue;
        else if (layover < MIN_DAY_LAYOVER || layover > MAX_DAY_LAYOVER)
            continue;

        ret.push_back(&f);
    }
    std::sort(ret.begin(), ret.end(),
              [](Flight *a, Flight *b) { return a->dep_time > b->dep_time; });
    return ret;
}

auto get_outgoing_new_trip(Flight &inc, CityGraph &g) -> vec<Flight *>
{
    assert(inc.dst == START_AIRPORT);

    // get all flights from the start airport that depart after START_TIME
    vec<Flight *> ret;
    for (auto &f : g[START_AIRPORT]) {
        if (f.dep_time >= inc.dep_time + MIN_HOME_LAYOVER &&
            f.dep_time <= inc.dep_time + MAX_HOME_LAYOVER)
            ret.push_back(&f);
    }
    std::sort(ret.begin(), ret.end(),
              [](Flight *a, Flight *b) { return a->dep_time < b->dep_time; });
    return ret;
}

auto build_flight_graph(CityGraph &city_graph) -> FlightGraph
{
    FlightGraph ret;
    for (auto &[_, flights] : city_graph)
        for (auto &f : flights)
            ret[&f] = get_valid_outgoing(f, city_graph);

    return ret;
}

auto search(u32 worker_num, CityGraph &cg, FlightGraph &fg,
            vec<Flight *> &start_q) -> Plan
{
    Plan best;
    std::deque<sptr<Plan>> q;
    for (auto start_flight : start_q)
        q.push_front(Plan::new_root(start_flight));

    u64 i = 0;
    while (!q.empty()) {
        // report progress
        i++;
        if (i % 10'000'000 == 0) {
            fmt::print(".");
            fflush(stdout);
        }
        if (i % 1'000'000'000 == 0)
            fmt::print("Worker {}: processed {}B, {} in queue\n", worker_num,
                       i / 1'000'000'000, q.size());

        auto cur = q.back();
        q.pop_back();

        // abandon path if it violates constraints
        if (cur->dur > MAX_TRIP_DURATION ||
            cur->num_flights > cur->unique_dest + MAX_DUP_DESTS)
            continue;

        // check if we're done with a trip, either completely or if we
        // should start a new one
        if (cur->last_flight->is_valid_end()) {
            if (cur->unique_dest >= MIN_DESTS && cur->is_better(best)) {
                best = *cur;
                fmt::print("New best plan found:\n{}\n", best.to_string());
            }

            // should we start a new trip?
            if (cur->unique_dest < DEST_CAP)
                for (auto &nxt : get_outgoing_new_trip(*cur->last_flight, cg))
                    q.push_back(cur->new_append(nxt));
        }

        // continue searching
        for (auto nxt : fg[cur->last_flight]) {
            // do some manual pruning

            // 1. no turn-arounds in the first half of the journey
            if (cur->num_flights < DEST_CAP / 2 &&
                nxt->dst == cur->last_flight->src)
                continue;

            // 2. no going back to start airport until 2nd half
            if (cur->num_flights < DEST_CAP / 2 && nxt->src == START_AIRPORT)
                continue;

            // append the next flight to the current plan
            q.push_back(cur->new_append(nxt));
        }
    }

    return best;
}

ABSL_FLAG(u32, num_workers, 0,
          "Number of workers to use for parallel search. 0 to use all cores.");

int main(int argc, char **argv)
{
    absl::ParseCommandLine(argc, argv);
    fmt::print("Current working directory: {}\n",
               std::filesystem::current_path().string());

    fmt::print("Building city graph...\n");
    auto city_graph = build_city_graph("flights.csv");
    fmt::print("Building flight graph...\n");
    auto flight_graph = build_flight_graph(city_graph);

    fmt::print("Starting search...\n");

    auto workers = absl::GetFlag(FLAGS_num_workers);
    if (workers == 0)
        workers = std::thread::hardware_concurrency() - 1;

    vec<Flight *> starting_flights;
    for (auto &f : city_graph[START_AIRPORT])
        if (f.dep_time >= START_TIME && f.dep_time <= END_TIME)
            starting_flights.push_back(&f);

    auto num_each = starting_flights.size() / workers;
    fmt::println("Starting {} workers, each with {} flights...", workers,
                 num_each);

    vec<std::jthread> threads;
    if (workers == 1) {
        // if only one worker, just run the search directly
        auto best = search(0, city_graph, flight_graph, starting_flights);
        fmt::print("Best plan found:\n{}\n", best.to_string());
        return 0;
    }

    for (u32 i = 0; i < workers; ++i) {
        threads.emplace_back([&, i]() {
            vec<Flight *> chunk;
            auto start_idx = i * num_each;
            auto end_idx =
                std::min(start_idx + num_each, starting_flights.size());
            for (auto j = start_idx; j < end_idx; ++j)
                chunk.push_back(starting_flights[j]);

            auto best = search(i, city_graph, flight_graph, chunk);
            fmt::print("Worker {} finished with best plan:\n{}\n", i,
                       best.to_string());
        });
    }

    for (auto &t : threads)
        t.join();

    return 0;
}

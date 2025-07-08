#include "absl/container/flat_hash_map.h"
#include "absl/container/flat_hash_set.h"
#include "absl/time/time.h"
#include "fmt/core.h"
#include "rapidcsv.h"
#include <algorithm>
#include <chrono>
#include <ctime>
#include <deque>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_set>
#include <vector>

using u8 = uint8_t;
using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;
using tp = absl::Time;
using str = std::string;
template <typename T> using vec = std::vector<T>;
template <typename T> using uset = absl::flat_hash_set<T>;
template <typename K, typename V> using umap = absl::flat_hash_map<K, V>;

// Configuration constants
const auto MIN_LAYOVER = absl::Minutes(50);
const auto MAX_LAYOVER = absl::Hours(18);
const auto MAX_TRIP_DURATION = absl::Hours(72);
const u32 NUM_DEST_AIRPORTS = 25;
const u32 MAX_NUM_FLIGHTS = 35;
const u32 MIN_TRIP_AIRPORTS = 4;

const u32 REGIONAL_ARRIVAL_CUTOFF_HOUR = 20;
const u32 REGIONAL_ARRIVAL_CUTOFF_MINUTE = 0;
const auto OVERNIGHT_THRESHOLD = absl::Hours(3);
const u32 OVERNIGHT_CHECK_HOUR = 3;
const u32 OVERNIGHT_CHECK_MINUTE = 0;

const str START_AIRPORT = "BOS";
const vec<str> REGIONAL_END = {"PVD", "ORH"};
const uset<str> ALLOWED_OVERNIGHT_AIRPORTS = {"RDU", "DCA", "MCO"};

struct Flight {
    str src;
    str dst;
    u16 fnum;
    tp depart;
    tp arrive;
    absl::Duration dur;
};

struct Plan {
    Plan *prev; // previous flight in trip; nullptr for first flight
    Flight &flight;

    u8 flights;         // total number of flights
    u8 unique_dest;     // unique airports
    u8 num_days;        // whole days used
    absl::Duration dur; // total trip duration

    static Plan new_append(Plan &old, Flight &f)
    {
        Plan ret{
            .prev = &old,
            .flight = f,
            .flights = (u8)(old.flights + 1),
        };

        return ret;
    }
};
